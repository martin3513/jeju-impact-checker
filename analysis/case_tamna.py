"""탐라문화제 2024·2025: 행사장 주변 정류소 대 대조 정류소(허브 743 실제 자료)."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from _hub import panel
from impact_engine import config as C
from impact_engine.effect import Spec
from impact_engine.pipeline import run, match_units
from impact_engine.loaders import wide
from _hub import record, save_figure

plt.rcParams["font.family"] = "Malgun Gothic"; plt.rcParams["axes.unicode_minus"] = False
SRC = "input/hub (743)"
p = panel("hub_743")
w = wide(p.df)
units = sorted(p.df["unit"].unique())
ev = {e["id"]: e for e in C.EVENTS}
notes = []
best = None
for key, eid in (("tamna24", "tamna63"), ("tamna25", "tamna64")):
    e = ev[eid]
    m = match_units(units, e["place_keywords"])
    span = w.loc[:e["start"]].tail(120)
    treated = [u for u, _ in m if u in span and span[u].mean() >= 20]
    notes.append(f"{e['name']} 처리군 {len(treated)}개: " + ", ".join(treated))
    a = run(p, Spec(e["start"], e["end"], treated), f"{e['name']}이 행사장 주변 정류소 버스 이용을 얼마나 바꿨나", Path("analysis/out"),
            title=e["name"], place_keywords=e["place_keywords"], road_control=None, make_docx=False, use_llm=False, annual=True)
    r = a.result
    record(f"case_{key}_pct", round(r.effect_pct, 1), display=f"{r.effect_pct:+.1f}%", source=SRC)
    record(f"case_{key}_ci", f"{r.ci_low_pct:+.1f}~{r.ci_high_pct:+.1f}%", display=f"{r.ci_low_pct:+.1f}~{r.ci_high_pct:+.1f}%", source=SRC)
    record(f"case_{key}_p", round(r.p_time, 3), display=f"{r.p_time:.3f}", source=SRC)
    record(f"case_{key}_pspace", None if r.p_space is None else round(r.p_space, 3), display="-" if r.p_space is None else f"{r.p_space:.3f}", source=SRC)
    record(f"case_{key}_net", None if r.net_count is None else round(r.net_count), display="-" if r.net_count is None else f"{r.net_count:+,.0f}명", source=SRC)
    record(f"case_{key}_ntreated", len(treated), display=f"{len(treated)}개", source=SRC)
    record(f"case_{key}_ncontrols", len(r.controls), display=f"{len(r.controls)}개", source=SRC)
    record(f"case_{key}_light", a.verdict.light, display=a.verdict.light, source=SRC)
    record(f"case_{key}_pretrend", "통과" if r.pretrend_ok else "불통과", display="통과" if r.pretrend_ok else "불통과", source=SRC)
    notes.append(f"  결과 {r.effect_pct:+.1f}% ({r.ci_low_pct:+.1f}~{r.ci_high_pct:+.1f}), p={r.p_time:.3f}, 신호등 {a.verdict.light}; " + " / ".join(a.log[-4:]))
    if key == "tamna25":
        best = (a, e)
Path("analysis/case_tamna_notes.md").write_text("\n".join(notes), encoding="utf-8")
a, e = best
es = a.result.event_study
fig, ax = plt.subplots(figsize=(8, 3.4))
ax.axvspan(a.spec.event_start, a.spec.event_end, color="#ffe0b2", alpha=0.8, label="축제 기간")
lo, hi = es["band_low_pct"].iloc[0], es["band_high_pct"].iloc[0]
if np.isfinite(lo):
    ax.axhspan(lo, hi, color="#e0e0e0", alpha=0.9, label="평소 하루 변동 범위(95%)")
ax.axhline(0, color="#555", lw=0.8)
ax.plot(es["date"], es["effect_pct"], marker="o", ms=3, color="#1565c0", label="일별 순효과(대조 정류소 대비)")
ax.set_ylabel("대조군 대비 버스 이용 변화(%)")
ax.set_title(f"{e['name']} — 행사장 주변 정류소 {a.result.effect_pct:+.1f}% (신호등 {a.verdict.light})", fontsize=10)
ax.legend(fontsize=8, frameon=False, loc="upper left")
fig.autofmt_xdate(); fig.tight_layout()
save_figure("fig_hero", fig, f"{e['name']} 기간 행사장 주변 정류소의 일별 버스 이용 순효과(허브 743 실제 자료, 대조 정류소 대비)", required=True)
