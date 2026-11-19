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
# 화면 디자인(A안)과 같은 색: 처리군 청록, 대조군 회청, 행사 기간 연한 청록
TREATED, CONTROL, EVENT_SPAN, BAND, INK, GRID = "#00766D", "#526782", "#D3ECE8", "#E6EDF1", "#102A40", "#D9E2E7"
PLACEBO, ACTUAL = "#BCCAD2", "#B33942"
plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#9FB1BD",
                     "axes.labelcolor": INK, "text.color": INK, "xtick.color": INK, "ytick.color": INK,
                     "axes.titleweight": "bold", "axes.axisbelow": True, "grid.color": GRID, "grid.linewidth": 0.6,
                     "legend.frameon": False})

LIGHT_COLOR = {"초록": "#2C713E", "노랑": "#956000", "빨강": "#B33942"}


def fig_event_study(result, spec, title: str, path: Path) -> Path:
    es = result.event_study
    fig, ax = plt.subplots(figsize=(8, 3.6), dpi=150)
    ax.axvspan(spec.event_start, spec.event_end, color=EVENT_SPAN, alpha=0.9, label="행사·정책 기간")
    lo, hi = es["band_low_pct"].iloc[0], es["band_high_pct"].iloc[0]
    if np.isfinite(lo) and np.isfinite(hi):
        ax.axhspan(lo, hi, color=BAND, alpha=0.9, label="평소 하루 변동 범위(95%)")
    ax.axhline(0, color=CONTROL, lw=0.8)
    ax.grid(axis="y")
    ax.plot(es["date"], es["effect_pct"], marker="o", ms=3, color=TREATED, lw=1.8, label="일별 순효과(대조군 대비)")
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
    ax.axvspan(spec.event_start, spec.event_end, color=EVENT_SPAN, alpha=0.9)
    ax.grid(axis="y")
    if as_index:  # 반출 불가 자료: 반사실 평균=100 지수로
        base = s["counterfactual"].mean()
        ax.plot(s["date"], s["treated"] / base * 100, color=TREATED, lw=1.8, label="실측(지수)")
        ax.plot(s["date"], s["counterfactual"] / base * 100, color=CONTROL, ls="--", lw=1.5, label="대조군으로 만든 반사실(지수)")
        ax.set_ylabel("지수(반사실 평균=100)")
    else:
        ax.plot(s["date"], s["treated"], color=TREATED, lw=1.8, label="처리군 실측")
        ax.plot(s["date"], s["counterfactual"], color=CONTROL, ls="--", lw=1.5, label="대조군으로 만든 반사실")
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
        ax.hist(np.expm1(result.placebo_time_dist) * 100, bins=30, color=PLACEBO, label="행사 없던 날의 가짜 효과")
    ax.axvline(result.effect_pct, color=ACTUAL, lw=2, label=f"실제 행사 {result.effect_pct:+.1f}%")
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

    from docx.oxml.ns import qn

    doc = Document()
    # 화면과 같은 색·글꼴: 본문 맑은 고딕, 제목 남색·청록(한글 글꼴이 제목에도 적용되게 eastAsia까지 지정)
    for name, size, color in (("Normal", 10, "102A40"), ("Heading 1", 16, "0A223C"),
                              ("Heading 2", 13, "075F63"), ("Heading 3", 11.5, "075F63")):
        sty = doc.styles[name]
        sty.font.name = "맑은 고딕"
        sty.font.size = Pt(size)
        sty.font.color.rgb = RGBColor.from_string(color)
        fonts = sty.element.get_or_add_rPr().get_or_add_rFonts()
        for attr in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
            fonts.attrib.pop(qn("w:" + attr), None)
        for attr in ("ascii", "hAnsi", "eastAsia"):
            fonts.set(qn("w:" + attr), "맑은 고딕")
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
