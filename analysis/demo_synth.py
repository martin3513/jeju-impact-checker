"""가상 센터 데이터 시연(허브 실제 파일 미확보 시 대체 경로) — 제출 코드의 pipeline.run 을 그대로 돌린다.
A: 3-04 가상 정류소, 탑동 일대 4곳에 +15% 효과를 심은 2025-10-10~14(제64회 탐라문화제 날짜)
B: 같은 정류소, 효과를 심지 않은 2025-06-10~14(행사 없음) — 없는 효과를 만들어 내지 않는지
C: 1-32 가상 탐나는전(반출 불가), 건입동·일도1동 +15% — 원값 없이 증감률·지수만 내는지
값은 모두 지어낸 가상 값이다(실제 제주 자료 아님)."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from _hub import ENGINE, record, save_figure
from impact_engine.synth import make_sample
from impact_engine.loaders import load_center_files
from impact_engine.effect import Spec
from impact_engine.pipeline import run, match_units

plt.rcParams["font.family"] = "Malgun Gothic"; plt.rcParams["axes.unicode_minus"] = False
SRC = "가상 센터 데이터(impact_engine/synth.py, 공개 명세서 v13 컬럼 구조, 값은 지어낸 것)"
sample = ENGINE / "data" / "sample_center" if (ENGINE / "data" / "sample_center" / "3-04").exists() else Path("analysis/sample_center")
if not (sample / "3-04").exists():
    make_sample(sample)
bus = load_center_files(sorted((sample / "3-04").glob("*.csv")))
kw = ["탑동", "탐라문화광장", "산지천", "동문"]
treated = [u for u, _ in match_units(sorted(bus.df["unit"].unique()), kw)]
out = Path("analysis/out_demo")
cases = {
    "A": (bus, Spec("2025-10-10", "2025-10-14", treated), "가상 행사(탑동 일대, +15% 심음)", kw),
    "B": (bus, Spec("2025-06-10", "2025-06-14", treated), "행사 없는 기간(효과 안 심음)", kw),
}
tam = load_center_files(sorted((sample / "1-32").glob("*.csv")))
cases["C"] = (tam, Spec("2025-10-10", "2025-10-14", ["건입동", "일도1동"]), "가상 탐나는전(반출 불가, +15% 심음)", ["건입동"])
res = {}
for k, (p, spec, title, kws) in cases.items():
    a = run(p, spec, title, out, title=title, place_keywords=kws, make_docx=False, use_llm=False, annual=(k != "B"))
    r = a.result
    res[k] = a
    record(f"demo{k}_pct", round(r.effect_pct, 1), display=f"{r.effect_pct:+.1f}%", source=SRC)
    record(f"demo{k}_ci", f"{r.ci_low_pct:+.1f}~{r.ci_high_pct:+.1f}%", display=f"{r.ci_low_pct:+.1f}~{r.ci_high_pct:+.1f}%", source=SRC)
    record(f"demo{k}_p", round(r.p_time, 3), display=f"{r.p_time:.3f}", source=SRC)
    record(f"demo{k}_light", a.verdict.light, display=a.verdict.light, source=SRC)
    record(f"demo{k}_ntreated", len(spec.treated), display=f"{len(spec.treated)}곳", source=SRC)
    record(f"demo{k}_ncontrols", len(r.controls), display=f"{len(r.controls)}곳", source=SRC)
    record(f"demo{k}_net_shown", "표시" if "순증(실측−반사실)" in a.summary_rows else "표시 안 함(반출 불가)",
           display="표시" if "순증(실측−반사실)" in a.summary_rows else "표시 안 함(반출 불가)", source=SRC)
    secs = [l for l in a.log if l.startswith("[시간] 전체")]
    if secs:
        s = float(secs[0].split()[-1].rstrip("초"))
        approx = "약 1초" if s < 2 else f"약 {round(s)}초"   # 실행마다 0.8~1.1초로 달라져 반올림해 기록(재계산 일치)
        record(f"demo{k}_sec", approx, display=approx, source=SRC)
record("demo_lift_pct", 15, display="15%", source=SRC)
record("demo_n_stations", int(bus.df["unit"].nunique()), display=f"{bus.df['unit'].nunique()}곳", source=SRC)
record("demo_n_emd", int(tam.df["unit"].nunique()), display=f"{tam.df['unit'].nunique()}곳", source=SRC)
Path("analysis/demo_notes.md").write_text("\n\n".join(f"## {k}\n" + "\n".join(a.log) for k, a in res.items()), encoding="utf-8")

a = res["A"]; es = a.result.event_study
fig, ax = plt.subplots(figsize=(8, 3.4))
ax.axvspan(a.spec.event_start, a.spec.event_end, color="#ffe0b2", alpha=0.85, label="행사 기간(가상 효과 +15% 심음)")
lo, hi = es["band_low_pct"].iloc[0], es["band_high_pct"].iloc[0]
if np.isfinite(lo):
    ax.axhspan(lo, hi, color="#e0e0e0", alpha=0.9, label="평소 하루 변동 범위(95%)")
ax.axhline(0, color="#555", lw=0.8)
ax.plot(es["date"], es["effect_pct"], marker="o", ms=3, color="#1565c0", label="Agent가 추정한 일별 순효과")
ax.set_ylabel("대조 정류소 대비 변화(%)")
ax.set_title(f"[가상 데이터 시연, 실제 탐라문화제 결과 아님] 가상 정류소 4곳에 +15%를 심음 → Agent 추정 {a.result.effect_pct:+.1f}% · 신호등 {a.verdict.light}", fontsize=9.5)
ax.legend(fontsize=8, frameon=False, loc="upper left")
fig.autofmt_xdate(); fig.tight_layout()
save_figure("fig_hero", fig, "가상 데이터 시연: 탑동 일대 가상 정류소 4곳에 +15% 효과를 심은 뒤 Agent가 대조 정류소와 비교해 찾아낸 일별 순효과(값은 지어낸 것)", required=True)
