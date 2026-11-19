"""반출 점검: 제주빅데이터센터 데이터 반출 정책(2026.09.01 개정)과 운영진 안내를 규칙으로 옮긴 것.

- 원본 반출 가능 데이터(버스 3-01~3-06, 날씨 5-xx, 허브 공개 파일)는 그대로 둔다.
- 반출 불가 데이터(카드·탐나는전·유동인구 등)는
  ① 단순집계(합계·평균·인원·건수·금액)는 10 미만 값이 있으면 블라인드('10 미만')하고,
  ② 가린 칸이 합계·나머지 칸으로 다시 계산되지 않게 한 칸 더 가리며(2차 가림),
  ③ 가능하면 증감률·지수 같은 응용집계로 바꿔 내보낸다.
- 반출 신청 사유문과 점검 메모 초안을 만든다(최종 승인은 센터 심사).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

THRESHOLD = 10
BLIND = "10 미만"
SECONDARY = "가림(역산 방지)"


@dataclass
class GuardReport:
    exportable: bool
    actions: list[str] = field(default_factory=list)
    blinded_cells: int = 0
    secondary_cells: int = 0


def guard_table(df: pd.DataFrame, count_cols: list[str], raw_exportable: bool,
                total_row: str | None = None) -> tuple[pd.DataFrame, GuardReport]:
    """표의 인원·건수·금액 열을 점검해 반출 가능한 표로 바꾼다."""
    rep = GuardReport(exportable=True)
    if raw_exportable:
        rep.actions.append("원본 반출 가능 데이터: 가림 없이 내보냄")
        return df.copy(), rep
    out = df.copy().astype(object)
    num = df[count_cols].apply(pd.to_numeric, errors="coerce")
    small = (num < THRESHOLD) & num.notna()
    rep.blinded_cells = int(small.values.sum())
    for c in count_cols:
        out.loc[small[c], c] = BLIND
    # 2차 가림: 합계 행이 있고 어떤 열에서 가린 칸이 1개뿐이면, 그 열에서 가장 작은 다른 칸을 더 가린다
    if total_row is not None and total_row in df.index:
        for c in count_cols:
            body = small[c].drop(index=total_row)
            if body.sum() == 1:
                cand = num[c].drop(index=[total_row] + list(body[body].index)).dropna()
                if len(cand):
                    k = cand.idxmin()
                    out.loc[k, c] = SECONDARY
                    rep.secondary_cells += 1
    if rep.blinded_cells:
        rep.actions.append(f"10 미만 값 {rep.blinded_cells}칸 블라인드")
    if rep.secondary_cells:
        rep.actions.append(f"합계로 역산되지 않도록 {rep.secondary_cells}칸 추가 가림")
    if not rep.actions:
        rep.actions.append("10 미만 값 없음")
    return out, rep


def to_applied(series_obs: float, series_cf: float) -> dict:
    """원값 대신 응용집계(증감률·지수)로."""
    if not (np.isfinite(series_obs) and np.isfinite(series_cf)) or series_cf <= 0:
        return {"증감률(%)": None, "지수(반사실=100)": None}
    return {"증감률(%)": round((series_obs / series_cf - 1) * 100, 1), "지수(반사실=100)": round(series_obs / series_cf * 100, 1)}


def guard_result(result, raw_exportable: bool) -> tuple[dict, GuardReport]:
    """분석 결과 요약을 반출 가능한 형태로: 원본 반출 불가면 인원·금액 원값을 빼고 증감률·지수·p값만 남긴다."""
    rep = GuardReport(exportable=True)
    s = result.summary()
    keep = {"효과(%)": round(s["effect_pct"], 1), "95% 구간(%)": f"{s['ci_low_pct']:.1f} ~ {s['ci_high_pct']:.1f}",
            "시점 위약 p값": round(s["p_time"], 3) if s["p_time"] == s["p_time"] else None,
            "지역 위약 p값": None if s["p_space"] is None else round(s["p_space"], 3),
            "대조 단위 수": len(s["controls"])}
    if raw_exportable:
        keep["순증(실측−반사실)"] = None if s["net_count"] is None else round(s["net_count"])
        rep.actions.append("원본 반출 가능 데이터: 순증 인원 포함")
    else:
        keep.update({k: v for k, v in to_applied(s["observed_total"], s["counterfactual_total"]).items()})
        rep.actions.append("반출 불가 데이터: 인원·금액 원값 제외, 증감률·지수(응용집계)만 표시")
        rep.actions.append("대조 단위 이름은 묶음 수만 표시(개별 단위 값 비공개)")
    return keep, rep


def export_request_text(dataset_titles: list[str], question: str, method: str, processing: list[str],
                        purpose: str, where: str) -> str:
    """운영진 안내 형식: '(도구·분석 방법)으로 분석 후 (가공 처리)로 가공하여 (내용)의 보고서 작성 및 (어디)에 활용'."""
    return (f"[활용 사유]\n「{' / '.join(dataset_titles)}」를 {method}으로 분석한 뒤 "
            f"{', '.join(processing)}로 가공하여 「{question}」에 대한 순효과 분석 보고서를 작성하고, {where}에 활용하고자 합니다.\n"
            f"[활용 목적] {purpose}")


def check_memo(dataset_titles: list[str], method: str, guard_reports: list[GuardReport], purpose: str) -> str:
    acts = sorted({a for g in guard_reports for a in g.actions})
    return "\n".join([
        "[반출 점검 메모]",
        f"1. 원본 데이터: {', '.join(dataset_titles)}",
        f"2. 분석·가공 방법: {method}",
        "3. 비식별 처리: " + ("; ".join(acts) if acts else "해당 없음"),
        "4. 역산 점검: " + ("가린 칸이 합계로 다시 계산되지 않도록 2차 가림을 적용했습니다. "
                           if any(g.secondary_cells for g in guard_reports) else "")
        + ("인원·금액 원값을 담지 않아 역산할 원값이 없습니다(증감률·지수만)."
           if any("원값 제외" in a for g in guard_reports for a in g.actions)
           else "원본 반출 가능 데이터로, 역산 제한 대상이 아닙니다."),
        "5. 그림: PNG로 내보내며 그림 안 수치는 위 표와 같은 기준을 따릅니다.",
        f"6. 활용 목적: {purpose}",
        "※ 최종 반출 가능 여부는 제주빅데이터센터 심사로 결정됩니다.",
    ])
