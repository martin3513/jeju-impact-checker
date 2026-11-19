"""총괄(오케스트레이터): 단계 순서는 코드가 정하고, 각 단계의 판단을 기록한다.

① 접수(LLM 또는 양식) → ② 데이터 안내·점검 → ③ 설계(처리군 확인·대조군 선택) → ④ 추정 → ⑤ 검증(위약·민감도·반대 설명·신호등)
→ ⑥ 작성·반출(보고서·반출 문안)
"""
from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import checks, config as C, export_guard, llm, report
from .effect import Spec, estimate
from .loaders import Panel, wide


def norm_name(s: str) -> str:
    s = unicodedata.normalize("NFC", str(s))
    return re.sub(r"[\s()\[\]·.\-_/]", "", s)


def match_units(units: list[str], keywords: list[str]) -> list[tuple[str, str]]:
    """정류소 이름 정규화 대응표: (단위 이름, 일치한 검색어)."""
    out = []
    for u in units:
        nu = norm_name(u)
        for k in keywords:
            if k and norm_name(k) in nu:
                out.append((u, k))
                break
    return out


def months_needed(spec: Spec) -> list[str]:
    """센터 화면은 1개월 단위로 내려받으므로, 사전기간·위약 기간을 포함한 월 목록."""
    a = spec.event_start - pd.Timedelta(days=spec.history_days + spec.pre_days)
    b = spec.event_end + pd.Timedelta(days=14)
    return [p.strftime("%Y-%m") for p in pd.period_range(a, b, freq="M")]


def download_guide(spec: Spec, datasets: list[str]) -> str:
    m = months_needed(spec)
    return (f"[센터 데이터 받기 안내]\n- 데이터: {', '.join(datasets)}\n- 기간: {m[0]} ~ {m[-1]} ({len(m)}개월, 화면에서 1개월씩 조회·내려받기)\n"
            f"- 조건: 읍면동·정류소 조건 없이 전체(대조군을 고르려면 다른 지역 자료도 필요)\n\n"
            f"[운영자 사전 다운로드 요청문]\n안녕하세요. 제주 임팩트 체커로 「{spec.event_start:%Y-%m-%d}~{spec.event_end:%Y-%m-%d}」 행사·정책 효과를 분석하려 합니다. "
            f"{', '.join(datasets)} 자료를 {m[0]}부터 {m[-1]}까지 월별 파일로 미리 내려받아 '요청파일' 폴더에 넣어 주시기 바랍니다.")


@dataclass
class Analysis:
    question: str
    spec: Spec
    panel: Panel
    result: object
    flags: list
    verdict: object
    summary_rows: dict
    guard: object
    narrative: str
    narrative_src: str
    figures: list[tuple[Path, str]] = field(default_factory=list)
    docx: Path | None = None
    export_reason: str = ""
    export_memo: str = ""
    log: list[str] = field(default_factory=list)
    alt_result: object = None


def run(panel: Panel, spec: Spec, question: str, out_dir: Path, *, title: str | None = None,
        weather: pd.DataFrame | None = None, place_keywords: list[str] | None = None,
        road_control: bool | None = None, make_docx: bool = True, use_llm: bool = True,
        road_units: list[str] | None = None, annual: bool = False,
        purpose: str = "행사·정책 성과 평가 보고서 작성", where: str = "기관 내부 결과보고서") -> Analysis:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log: list[str] = [f"[접수] {question}", f"[데이터] {panel.title} · 단위 {panel.unit_kind} · {panel.df['unit'].nunique():,}개 · "
                      f"{panel.df['date'].min():%Y-%m-%d}~{panel.df['date'].max():%Y-%m-%d}"]
    log += [f"[데이터] {n}" for n in panel.notes]
    w = wide(panel.df)
    # 다른 내장 행사는 위약에서 피한다
    t0 = time.perf_counter()
    kws = set(place_keywords or [])
    # 위약에서 피할 다른 행사: 전역 정책, 그리고 장소 검색어가 겹치는 행사만(다른 지역 축제는 처리군에 영향이 적어 빼지 않음)
    spec.avoid_dates = list(spec.avoid_dates) + [(pd.Timestamp(e["start"]), pd.Timestamp(e["end"])) for e in C.EVENTS
                                                  if pd.Timestamp(e["start"]) != spec.event_start
                                                  and (e["kind"] == "정책" or (kws & set(e["place_keywords"])))]
    if annual:  # 해마다 열리는 행사: 전년 같은 시기(±7일, 위약 제외 규칙이 앞뒤 7일을 더함)를 위약에서 뺀다
        for k in (1, 2):
            spec.avoid_dates.append((spec.event_start - pd.Timedelta(days=364 * k), spec.event_end - pd.Timedelta(days=364 * k)))
        log.append("[설계] 해마다 열리는 행사로 보고 전년·전전년 같은 시기(±7일)를 위약검정에서 뺌")
    res = estimate(w, spec, log=log)
    log.append(f"[시간] 대조군 선택·추정·위약검정 {time.perf_counter() - t0:.1f}초")
    alt = None
    if road_units:  # 도로 통제·임시 정류소를 넣은 처리군으로 한 번 더(두 결과를 나란히)
        from copy import deepcopy
        s2 = deepcopy(spec)
        s2.treated = sorted(set(spec.treated) | set(road_units))
        s2.exclude = [u for u in spec.exclude if u not in road_units]
        try:
            alt = estimate(w, s2, log=[])
            log.append(f"[민감도] 도로 통제·임시 정류소 {len(road_units)}곳을 처리군에 넣으면 {alt.effect_pct:+.1f}% "
                       f"(뺀 기본 결과 {res.effect_pct:+.1f}%)")
        except ValueError as e:
            log.append(f"[민감도] 통제 정류소 포함 계산 실패: {e}")
    events_df = pd.DataFrame([{"name": e["name"], "start": e["start"], "end": e["end"], "place": e["place"]}
                              for e in C.EVENTS if pd.Timestamp(e["start"]) != spec.event_start])
    flags = checks.confounder_flags(spec, res, events_df, weather, w[spec.treated].sum(axis=1, min_count=1),
                                    place_keywords, road_control)
    v = checks.verdict(res, flags)
    log.append(f"[검증] 신호등 {v.light}: {v.reason}")
    rows, grep = export_guard.guard_result(res, panel.exportable_raw)
    rows = {"분석 대상": f"{panel.unit_kind} {len(spec.treated)}개 vs 대조 {len(res.controls)}개", **rows,
            "평행추세 점검": "통과" if res.pretrend_ok else "불통과", "민감도(부호 일치)": "예" if res.sens_sign_ok else "아니오"}
    if alt is not None:
        rows["통제 정류소 포함 시 효과(%)"] = round(alt.effect_pct, 1)

    measure = panel.measure
    facts = {"event": title or question, "measure": measure, "effect": f"{res.effect_pct:+.1f}%",
             "ci": f"{res.ci_low_pct:+.1f}%~{res.ci_high_pct:+.1f}%", "p_time": f"{res.p_time:.3f}", "light": v.light}
    fb = (f"{title or '이 행사·정책'} 기간 처리군의 {measure}은 비슷한 흐름의 대조군으로 만든 반사실보다 {res.effect_pct:+.1f}% "
          f"달랐다(95% 구간 {res.ci_low_pct:+.1f}~{res.ci_high_pct:+.1f}%). 과거 행사 없던 날에 같은 계산을 반복했을 때 이만큼 차이 날 확률은 "
          f"{res.p_time:.3f}이며 신뢰도 신호등은 '{v.light}'이다. 이 값은 {measure}의 변화이며 방문객 수를 직접 나타내지 않는다.")
    facts["event"] = llm.mask_values(str(facts["event"]))[0]
    if use_llm:
        narrative, src = llm.write_narrative(facts, fb)
    else:
        narrative, src = fb, "고정 문장"
    log.append(f"[작성] 문장: {src}")

    tag = re.sub(r"[^0-9A-Za-z가-힣]+", "_", title or "analysis")[:40]
    figs = [(report.fig_event_study(res, spec, f"{title or ''}: 일별 순효과", out_dir / f"{tag}_event_study.png"),
             "그림 1. 일별 순효과(대조군 대비). 회색 띠는 행사 없던 날의 평소 하루 변동 범위"),
            (report.fig_series(res, spec, "실측과 반사실", out_dir / f"{tag}_series.png", as_index=not panel.exportable_raw),
             "그림 2. 처리군 실측과 대조군으로 만든 반사실"),
            (report.fig_placebo(res, out_dir / f"{tag}_placebo.png"), "그림 3. 시점 위약검정 분포와 실제 효과")]
    titles = [panel.title]
    method = "Python(pandas) 비율 이중차분·사건연구·위약검정(제주 임팩트 체커)"
    processing = ["대조군 대비 증감률·지수(응용집계) 산출"] + ([] if panel.exportable_raw else ["인원·금액 원값 제외"])
    ereason = export_guard.export_request_text(titles, title or question, method, processing, purpose, where)
    ememo = export_guard.check_memo(titles, method, [grep], purpose)
    limits = [f"결과는 {measure}의 변화이며 방문객 수를 대신하지 않는다.",
              *([] if weather is not None else ["날씨 자료를 넣지 않아 강수·강풍 점검을 하지 않았다(센터 5-02 일일 날씨 CSV를 넣으면 점검)."]),
              "대조군이 행사 영향을 받았거나(파급) 같은 기간 다른 요인이 처리군에만 작용했다면 효과가 틀릴 수 있다.",
              "도로 통제·임시 정류소·셔틀 운행은 정류소 이용을 기계적으로 바꿀 수 있다."]
    controls_text = (", ".join(res.controls) if panel.exportable_raw else f"대조 단위 {len(res.controls)}개(이름·값 비공개)")
    docx_path = None
    if make_docx:
        docx_path = report.build_docx(out_dir / f"{tag}_report.docx", title=f"{title or '행사·정책'} 순효과 분석", question=question,
                                      verdict=v, summary_rows=rows, narrative=narrative, narrative_src=src, figures=figs,
                                      controls_text=controls_text, decision_log=log, flags=flags, limits=limits,
                                      export_memo=ememo, export_reason=ereason, data_sources=[panel.title])
    log.append(f"[시간] 전체 {time.perf_counter() - t0:.1f}초")
    return Analysis(question, spec, panel, res, flags, v, rows, grep, narrative, src, figs, docx_path, ereason, ememo, log, alt)
