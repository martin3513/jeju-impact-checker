"""제주 임팩트 체커 — 축제·행사·정책의 '진짜 효과'를 대조군과 비교해 검증하는 AI Agent (로컬 웹앱).

실행: run.bat (또는 `streamlit run app.py`) → 브라우저 http://localhost:8501
"""
from __future__ import annotations

import datetime as dt
import os
import shutil
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from impact_engine import config as C, llm
from impact_engine.effect import Spec
from impact_engine.loaders import (detect_dataset, load_center_files, load_hub_cached, load_weather, Panel)
from impact_engine.pipeline import run, match_units, download_guide

ROOT = Path(__file__).resolve().parent
DATA_HUB = ROOT / "data" / "hub"
DATA_SAMPLE = ROOT / "data" / "sample_center"
CACHE = ROOT / "data" / "cache"
WORK = ROOT / "work"          # 이용자가 올린 센터 CSV와 결과(삭제 대상)


def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


load_env()
st.set_page_config(page_title="제주 임팩트 체커", page_icon=":material/insights:", layout="wide")

ss = st.session_state
ss.setdefault("spec", None)
ss.setdefault("analysis", None)
ss.setdefault("session_dir", WORK / dt.datetime.now().strftime("%Y%m%d_%H%M%S"))


def md(text: str) -> str:
    """마크다운으로 보일 문장에서 '~'(날짜·구간 범위)가 취소선으로 바뀌지 않게."""
    return str(text).replace("~", r"\~")


def purge_old(hours: int = 12):
    """결과 보관이 꺼져 있으면, 앱을 열 때 오래된 작업 폴더를 지운다."""
    if WORK.exists():
        for d in WORK.iterdir():
            if d.is_dir() and time.time() - d.stat().st_mtime > hours * 3600:
                shutil.rmtree(d, ignore_errors=True)


# ---------------- 사이드바: 설정·삭제 ----------------
with st.sidebar:
    st.header("설정")
    keep = st.toggle("결과 보관(ON이면 작업 폴더를 남김)", value=os.environ.get("IMPACT_KEEP_RESULTS", "off").lower() == "on",
                     help="센터 운영 원칙: 퇴실 시 반출 승인 외 자료는 삭제. OFF면 앱을 열 때 12시간 지난 작업 폴더를 지웁니다.")
    if not keep:
        purge_old()
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    st.caption(f"Claude API: {'연결 설정됨' if has_key else '키 없음 → 규칙 기반으로 동작'} · 모델 {llm.model_name()}")
    use_llm = st.toggle("Claude로 질문 해석·문장 작성", value=has_key, disabled=not has_key)
    if st.button("이번 작업 결과 모두 삭제", type="secondary", width="stretch"):
        shutil.rmtree(ss.session_dir, ignore_errors=True)
        for k in ("analysis", "spec", "panel"):
            ss.pop(k, None)
        st.success("작업 폴더와 결과를 지웠습니다.")
    st.divider()
    st.caption("Claude에는 질문 문장(숫자 가림)·행사 목록·분석 단위 종류, 문장 작성 때는 값 이름·신호등만 보냅니다. "
               "숫자 값·CSV 행·인원·금액 원값은 보내지 않고 이 PC가 계산해 채웁니다.")
    if llm.USAGE.calls:
        st.caption(f"Claude 호출 {llm.USAGE.calls}회 · 입력 {llm.USAGE.input_tokens:,} · 출력 {llm.USAGE.output_tokens:,} 토큰")

st.title(":material/insights: 제주 임팩트 체커")
st.caption("축제·행사·정책의 날짜와 장소를 넣으면, 비슷한 대조 정류소·지역과 비교해 '그날 그곳에서만 늘어난 몫(순효과)'을 계산하고 "
           "우연인지 검사합니다. 결과는 방문객 수가 아니라 데이터가 재는 것(버스 이용 등)의 변화입니다.")

step1, step2, step3, step4 = st.tabs(["① 묻기", "② 자료 넣기", "③ 결과·신호등", "④ 반출·보고서"])

# ---------------- ① 묻기 ----------------
with step1:
    mode = st.segmented_control("어떻게 시작할까요?", ["행사·정책 목록에서 고르기", "질문으로 묻기"], default="행사·정책 목록에서 고르기") or "행사·정책 목록에서 고르기"
    ev_names = {e["name"]: e for e in C.EVENTS}
    preset = {}
    if mode == "행사·정책 목록에서 고르기":
        name = st.selectbox("행사·정책", list(ev_names))
        preset = ev_names[name]
    else:
        q = st.text_area("질문", placeholder="예: 2025년 탐라문화제가 탑동 일대 버스 이용을 얼마나 늘렸나요?", height=80,
                         help="센터 자료의 실제 집계 값은 쓰지 마세요. 세 자리 이상 숫자는 자동으로 가려 보냅니다.")

        def parse(text: str):
            if use_llm:
                spec_j, note = llm.parse_question(text, C.EVENTS, ["정류소", "이용자 유형", "읍면동"])
            else:
                spec_j, note = None, "Claude를 쓰지 않아 아래 양식에 직접 입력해 주세요."
            ss["parse_note"] = note
            ss["clarify"] = (spec_j or {}).get("clarify", "")
            if spec_j:
                ss["parsed"] = {"name": spec_j["event_name"], "start": spec_j["start"], "end": spec_j["end"],
                                "place_keywords": spec_j["place_keywords"], "analysis": spec_j["analysis"],
                                "treated_user_type": spec_j.get("treated_user_type") or "",
                                "control_user_type": spec_j.get("control_user_type") or "", "question": q}

        if st.button("질문 해석하기", disabled=not q):
            ss["ask_round"], ss["qa_history"] = 0, []
            parse(q)
        if ss.get("parse_note"):
            st.info(md(ss["parse_note"]))
        if ss.get("clarify"):
            if ss.get("ask_round", 0) < 2:
                st.warning(md(ss["clarify"]), title=f"확인 질문 {ss.get('ask_round', 0) + 1}/2")
                ans = st.text_input("답", key=f"clarify_ans_{ss.get('ask_round', 0)}")
                if st.button("답하고 다시 해석", disabled=not ans, key=f"clarify_btn_{ss.get('ask_round', 0)}"):
                    ss["qa_history"] = ss.get("qa_history", []) + [(ss["clarify"], ans)]
                    ss["ask_round"] = ss.get("ask_round", 0) + 1
                    parse(q + "\n" + "\n".join(f"[확인 질문] {c}\n[답] {a}" for c, a in ss["qa_history"]))
                    st.rerun()
            else:
                st.warning("확인 질문을 두 번 했습니다. 아래 양식에서 직접 고쳐 주세요.")
        preset = ss.get("parsed", {})
    st.subheader("분석 명세 (확인·수정)")
    c1, c2, c3 = st.columns([2, 1, 1])
    ev_title = c1.text_input("행사·정책 이름", value=preset.get("name", ""))
    try:
        d0 = pd.Timestamp(preset.get("start") or "2025-10-10").date()
        d1 = pd.Timestamp(preset.get("end") or preset.get("start") or "2025-10-14").date()
    except Exception:
        d0 = d1 = dt.date(2025, 10, 10)
    start = c2.date_input("시작일", d0)
    end = c3.date_input("종료일", d1)
    default_unit = "이용자 유형" if preset.get("treated_user_type") else "정류소"
    unit_kind = st.segmented_control("비교 단위", ["정류소", "이용자 유형", "읍면동"],
                                     default=preset.get("analysis") or default_unit) or default_unit
    kw = st.text_input("장소 검색어(쉼표로 구분, 정류소·읍면동 이름에 들어갈 말)", value=", ".join(preset.get("place_keywords", [])))
    question = preset.get("question") or f"{ev_title}이(가) {kw or '대상'}의 이용을 얼마나 바꿨나?"
    tu = cu = ""
    if unit_kind == "이용자 유형":
        cc1, cc2 = st.columns(2)
        tu = cc1.text_input("처리군 이용자 유형", value=preset.get("treated_user_type") or "청소년")
        cu = cc2.text_input("대조군 이용자 유형", value=preset.get("control_user_type") or "일반")
    annual = st.toggle("해마다 열리는 행사(전년 같은 시기를 위약검정에서 뺌)", value=(preset.get("kind", "축제").startswith("축제")))
    road = st.segmented_control("행사 중 도로 통제·임시 정류소·셔틀 운행이 있었나요?", ["모름", "없음", "있음"], default="모름") or "모름"
    if ev_title and "t_start" not in ss:
        ss["t_start"] = time.time()   # 묻기 시작 시각(질문→결과 소요 시간 측정)
    ss.spec = {"title": ev_title, "start": pd.Timestamp(start), "end": pd.Timestamp(end), "unit_kind": unit_kind,
               "keywords": [k.strip() for k in kw.split(",") if k.strip()], "treated_user_type": tu, "control_user_type": cu,
               "road": {"모름": None, "없음": False, "있음": True}[road], "question": question, "annual": annual}
    st.success("명세가 준비되었습니다. ② 데이터 넣기로 가세요.") if ev_title else None

# ---------------- ② 데이터 넣기 ----------------
with step2:
    sp = ss.spec
    src = st.segmented_control("자료", ["제주데이터허브 공개 파일(data/hub 폴더)", "센터 CSV 올리기·폴더", "가상 센터 데이터로 시연"],
                               default="가상 센터 데이터로 시연") or "가상 센터 데이터로 시연"
    panel = None
    weather = None
    if src.startswith("제주데이터허브"):
        DATA_HUB.mkdir(parents=True, exist_ok=True)
        files = sorted(DATA_HUB.glob("*.csv"))
        if not files:
            st.warning(f"{DATA_HUB} 폴더에 허브 파일(743·561·512)을 넣어 주세요. 받는 방법은 사용자 매뉴얼을 보세요.")
        dets = [(f, detect_dataset(f)) for f in files]
        st.dataframe(pd.DataFrame([{"파일": f.name, "판별": d.title, "일치도": round(d.score, 2)} for f, d in dets]), hide_index=True,
                     alt="허브 폴더의 파일과 판별 결과")
        want = "hub_561" if sp and sp["unit_kind"] == "이용자 유형" else "hub_743"
        cand = [f for f, d in dets if d.dataset == want]
        if cand and st.button("불러오기(처음 한 번은 1~3분)", type="primary"):
            with st.spinner("큰 파일을 '일×단위' 합계로 줄이는 중…"):
                kwargs = {"unit": "user_type"} if want == "hub_561" else {}
                ss.panel = load_hub_cached(cand[0], want, CACHE, **kwargs)
    elif src.startswith("센터 CSV"):
        st.info("센터 화면에서 1개월씩 내려받은 같은 종류의 CSV 여러 개를 함께 올리세요(정류소별 이용 3-04, 탐나는전 1-32, 유동인구 4-11).")
        if sp:
            st.code(download_guide(Spec(sp["start"], sp["end"], ["-"]), ["버스 정류소별 이용 현황(3-04)"]), language=None)
        up = st.file_uploader("CSV 파일", type=["csv"], accept_multiple_files=True)
        wfile = st.file_uploader("(선택) 일일 날씨 5-02 CSV", type=["csv"], accept_multiple_files=True)
        if up and st.button("불러오기", type="primary"):
            d = ss.session_dir / "upload"
            d.mkdir(parents=True, exist_ok=True)
            paths = []
            for f in up:
                p = d / f.name
                p.write_bytes(f.getvalue())
                paths.append(p)
            ss.panel = load_center_files(paths)
            if wfile:
                wp = []
                for f in wfile:
                    p = d / ("w_" + f.name)
                    p.write_bytes(f.getvalue())
                    wp.append(p)
                ss.weather = pd.concat([load_weather(p) for p in wp]).groupby("date", as_index=False).mean()
    else:
        st.info("가상 센터 데이터: 공개 명세서 v13 컬럼 구조로 만든 지어낸 값입니다. 2025-10-10~14 탑동 일대 정류소(가상)에 +15% 효과를 심어 두었습니다.")
        if st.button("가상 데이터 불러오기", type="primary"):
            if not (DATA_SAMPLE / "3-04").exists():
                from impact_engine.synth import make_sample
                make_sample(DATA_SAMPLE)
            ss.panel = load_center_files(sorted((DATA_SAMPLE / "3-04").glob("*.csv")))
            ss.weather = pd.concat([load_weather(p) for p in sorted((DATA_SAMPLE / "5-02").glob("*.csv"))]).groupby("date", as_index=False).mean()
    panel: Panel | None = ss.get("panel")
    if panel is not None:
        st.success(f"불러옴: {panel.title} · {panel.unit_kind} {panel.df['unit'].nunique():,}개 · "
                   f"{panel.df['date'].min():%Y-%m-%d} ~ {panel.df['date'].max():%Y-%m-%d} · 원본 반출 {'가능' if panel.exportable_raw else '불가(응용집계만)'}")
        units = sorted(panel.df["unit"].unique())
        if sp and sp["unit_kind"] == "이용자 유형":
            treated = [u for u in units if u == sp["treated_user_type"]]
            controls_only = [u for u in units if u == sp["control_user_type"]]
            st.write(f"처리군: {treated or '없음'} · 대조군: {controls_only or '없음'}")
            ss.treated, ss.exclude = treated, [u for u in units if u not in treated + controls_only]
        else:
            m = match_units(units, sp["keywords"] if sp else [])
            st.markdown("**처리군 확인**: 장소 검색어와 이름이 맞는 단위입니다. 빼거나 도로 통제로 따로 볼 곳을 표시하세요.")
            tbl = pd.DataFrame({"단위": [u for u, _ in m], "일치한 검색어": [k for _, k in m], "처리군에 넣기": True, "도로 통제·임시 정류소": False})
            add = st.multiselect("목록에 없는 단위 추가", [u for u in units if u not in tbl["단위"].tolist()])
            if add:
                tbl = pd.concat([tbl, pd.DataFrame({"단위": add, "일치한 검색어": "직접 추가", "처리군에 넣기": True, "도로 통제·임시 정류소": False})])
            ed = st.data_editor(tbl, hide_index=True, width="stretch", disabled=["단위", "일치한 검색어"], alt="처리군 후보 단위 목록")
            ss.treated = ed.loc[ed["처리군에 넣기"] & ~ed["도로 통제·임시 정류소"], "단위"].tolist()
            ss.road_units = ed.loc[ed["도로 통제·임시 정류소"], "단위"].tolist()
            ss.exclude = ed.loc[ed["도로 통제·임시 정류소"], "단위"].tolist() + [u for u in tbl["단위"] if u not in ss.treated]
            st.caption(f"처리군 {len(ss.treated)}개 · 대조군 후보에서 빼는 단위 {len(ss.exclude)}개(파급·통제 우려)")

# ---------------- ③ 결과 보기 ----------------
with step3:
    sp, panel = ss.spec, ss.get("panel")
    ready = bool(sp and panel is not None and ss.get("treated"))
    if not ready:
        st.info("①에서 행사를 정하고 ②에서 자료와 처리군을 확인하면 분석할 수 있습니다.")
    if st.button("분석 실행", type="primary", disabled=not ready):
        spec = Spec(sp["start"], sp["end"], ss.treated, exclude=ss.get("exclude", []))
        with st.spinner("대조군 고르기 → 순효과 계산 → 위약검정 → 반대 설명 점검 중…"):
            try:
                ss.analysis = run(panel, spec, sp["question"], ss.session_dir / "out", title=sp["title"], weather=ss.get("weather"),
                                  place_keywords=sp["keywords"], road_control=sp["road"], use_llm=use_llm,
                                  road_units=ss.get("road_units") or None, annual=sp.get("annual", False))
            except ValueError as e:
                st.error(f"분석할 수 없습니다: {e}")
            if ss.get("analysis") is not None and "t_start" in ss:
                ss.analysis.log.append(f"[시간] 묻기 시작부터 결과까지 {time.time() - ss['t_start']:.0f}초")
    a = ss.get("analysis")
    if a is not None:
        color = {"초록": "green", "노랑": "orange", "빨강": "red"}[a.verdict.light]
        st.markdown(f"### 신뢰도 신호등: :{color}[● {a.verdict.light}]")
        st.markdown(md(a.verdict.reason))
        r = a.result
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("순효과(대조군 대비)", f"{r.effect_pct:+.1f}%")
        m2.metric("95% 구간", f"{r.ci_low_pct:+.1f} ~ {r.ci_high_pct:+.1f}%")
        m3.metric("우연일 확률(시점 위약 p)", f"{r.p_time:.3f}")
        if a.panel.exportable_raw and r.net_count is not None:
            m4.metric("순증 인원(행사 기간 합)", f"{r.net_count:+,.0f}명")
        else:
            m4.metric("지역 위약 p", "-" if r.p_space is None else f"{r.p_space:.3f}")
        st.markdown(md(a.narrative))
        st.caption(f"문장 작성: {a.narrative_src} · 수치는 이 PC에서 계산")
        for fp, cap in a.figures:
            st.image(str(fp), caption=cap, alt=cap)
        st.subheader("반대 설명 점검")
        for f in a.flags:
            (st.warning if f.level == "경고" else st.info)(md(f"[{f.kind}] {f.text}"))
        with st.expander("판단 기록(Agent가 한 일)"):
            st.code("\n".join(a.log), language=None)
        with st.expander("요약표·대조군"):
            st.table(pd.DataFrame(a.summary_rows.items(), columns=["항목", "값"]).astype(str), alt="분석 요약표")
            st.write(", ".join(r.controls) if a.panel.exportable_raw else f"대조 단위 {len(r.controls)}개(이름·값 비공개)")

# ---------------- ④ 내보내기 ----------------
with step4:
    a = ss.get("analysis")
    if a is None:
        st.info("③에서 분석을 먼저 실행하세요.")
    else:
        st.write("반출 점검: " + "; ".join(a.guard.actions))
        if a.docx and Path(a.docx).exists():
            st.download_button("결과보고서(DOCX) 받기", Path(a.docx).read_bytes(), file_name=Path(a.docx).name, type="primary")
        cols = st.columns(len(a.figures))
        for i, (c, (fp, cap)) in enumerate(zip(cols, a.figures), 1):
            c.download_button(f"그림 {i} PNG 받기", Path(fp).read_bytes(), file_name=Path(fp).name, help=cap,
                              icon=":material/image:")
        st.text_area("반출 신청 사유문(초안)", a.export_reason, height=140)
        st.text_area("반출 점검 메모(초안)", a.export_memo, height=220)
        st.download_button("사유문·점검 메모 TXT 받기", (a.export_reason + "\n\n" + a.export_memo).encode("utf-8"),
                           file_name="반출신청_문안.txt")
        st.caption("반출 신청은 센터 시스템에서 이용자가 직접 합니다. 최종 반출 여부는 센터 심사로 결정됩니다.")
