"""그림(PNG)과 보고서(DOCX). 반출 정책상 그림은 PNG로 내보낸다."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

for _f in ("Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR"):
    if any(_f == f.name for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = _f
        break
plt.rcParams["axes.unicode_minus"] = False

LIGHT_COLOR = {"초록": "#1a7f37", "노랑": "#b58900", "빨강": "#c62828"}


def fig_event_study(result, spec, title: str, path: Path) -> Path:
    es = result.event_study
    fig, ax = plt.subplots(figsize=(8, 3.6), dpi=150)
    ax.axvspan(spec.event_start, spec.event_end, color="#ffe0b2", alpha=0.7, label="행사·정책 기간")
    lo, hi = es["band_low_pct"].iloc[0], es["band_high_pct"].iloc[0]
    if np.isfinite(lo) and np.isfinite(hi):
        ax.axhspan(lo, hi, color="#e0e0e0", alpha=0.8, label="평소 하루 변동 범위(95%)")
    ax.axhline(0, color="#555", lw=0.8)
    ax.plot(es["date"], es["effect_pct"], marker="o", ms=3, color="#1565c0", lw=1.5, label="일별 순효과(대조군 대비)")
    ax.set_ylabel("대조군 대비 변화(%)")
    ax.set_title(title, fontsize=11)
    ax.legend(fontsize=8, loc="upper left", frameon=False)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def fig_series(result, spec, title: str, path: Path, as_index: bool = False) -> Path:
    s = result.series
    fig, ax = plt.subplots(figsize=(8, 3.4), dpi=150)
    ax.axvspan(spec.event_start, spec.event_end, color="#ffe0b2", alpha=0.7)
    if as_index:  # 반출 불가 자료: 반사실 평균=100 지수로
        base = s["counterfactual"].mean()
        ax.plot(s["date"], s["treated"] / base * 100, color="#1565c0", label="실측(지수)")
        ax.plot(s["date"], s["counterfactual"] / base * 100, color="#9e9e9e", ls="--", label="대조군으로 만든 반사실(지수)")
        ax.set_ylabel("지수(반사실 평균=100)")
    else:
        ax.plot(s["date"], s["treated"], color="#1565c0", label="처리군 실측")
        ax.plot(s["date"], s["counterfactual"], color="#9e9e9e", ls="--", label="대조군으로 만든 반사실")
        ax.set_ylabel("하루 이용 인원")
    ax.set_title(title, fontsize=11)
    ax.legend(fontsize=8, frameon=False)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def fig_placebo(result, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(6, 3.0), dpi=150)
    if len(result.placebo_time_dist):
        ax.hist(np.expm1(result.placebo_time_dist) * 100, bins=30, color="#bdbdbd", label="행사 없던 날의 가짜 효과")
    ax.axvline(result.effect_pct, color="#c62828", lw=2, label=f"실제 행사 {result.effect_pct:+.1f}%")
    ax.set_xlabel("대조군 대비 변화(%)")
    ax.set_ylabel("횟수")
    ax.legend(fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def build_docx(path: Path, *, title: str, question: str, verdict, summary_rows: dict, narrative: str, narrative_src: str,
               figures: list[tuple[Path, str]], controls_text: str, decision_log: list[str], flags, limits: list[str],
               export_memo: str, export_reason: str, data_sources: list[str]) -> Path:
    from docx import Document
    from docx.shared import Pt, RGBColor, Cm

    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "맑은 고딕"
    st.font.size = Pt(10)
    for s in doc.sections:
        s.left_margin = s.right_margin = Cm(2.0)
        s.top_margin = s.bottom_margin = Cm(1.8)
    doc.add_heading(title, level=1)
    p = doc.add_paragraph()
    r = p.add_run(f"신뢰도 신호등: {verdict.light}  ")
    r.bold = True
    r.font.size = Pt(13)
    r.font.color.rgb = RGBColor.from_string(LIGHT_COLOR.get(verdict.light, "#333333").lstrip("#"))
    p.add_run(verdict.reason)
    doc.add_paragraph(f"질문: {question}")
    t = doc.add_table(rows=0, cols=2)
    t.style = "Light Grid Accent 1"
    for k, v in summary_rows.items():
        row = t.add_row().cells
        row[0].text, row[1].text = str(k), "-" if v is None else str(v)
    doc.add_paragraph()
    doc.add_paragraph(narrative)
    doc.add_paragraph(f"(문장 작성: {narrative_src} · 수치는 로컬 계산값)").runs[0].font.size = Pt(8)
    if figures:
        fp, cap = figures[0]
        doc.add_picture(str(fp), width=Cm(16))
        doc.add_paragraph(cap).runs[0].font.size = Pt(8)
    doc.add_page_break()
    doc.add_heading("상세", level=2)
    for fp, cap in figures[1:]:
        doc.add_picture(str(fp), width=Cm(15))
        doc.add_paragraph(cap).runs[0].font.size = Pt(8)
    doc.add_heading("반대 설명 점검", level=3)
    if flags:
        for f in flags:
            doc.add_paragraph(f"[{f.level}·{f.kind}] {f.text}", style="List Bullet")
    else:
        doc.add_paragraph("특이 사항 없음")
    doc.add_heading("대조군", level=3)
    doc.add_paragraph(controls_text)
    doc.add_heading("판단 기록", level=3)
    for line in decision_log:
        doc.add_paragraph(line, style="List Bullet")
    doc.add_heading("한계", level=3)
    for line in limits:
        doc.add_paragraph(line, style="List Bullet")
    doc.add_heading("자료 출처", level=3)
    for line in data_sources:
        doc.add_paragraph(line, style="List Bullet")
    doc.add_page_break()
    doc.add_heading("반출 신청 문안(초안)", level=2)
    doc.add_paragraph(export_reason)
    doc.add_paragraph(export_memo)
    doc.add_paragraph(f"작성: 제주 임팩트 체커 · {dt.datetime.now():%Y-%m-%d %H:%M}").runs[0].font.size = Pt(8)
    doc.save(path)
    return path
