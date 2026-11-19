"""가짜 효과 되찾기 시험: 허브 743(실제 정류소 일 이용)에서 행사 없는 정류소·기간에 크기를 아는 효과를 심고 되찾는지 잰다."""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from _hub import panel
from impact_engine import config as C
from impact_engine.effect import Spec, estimate, inject_effect
from impact_engine.loaders import wide
from _hub import record, save_figure

plt.rcParams["font.family"] = "Malgun Gothic"; plt.rcParams["axes.unicode_minus"] = False
SRC = "input/hub (743 이용자 유형별 버스정류소 이용 인원 현황)"
p = panel("hub_743")
w = wide(p.df)
span = w.loc["2024-01-01":"2025-10-20"]
keep = span.columns[(span.mean() >= 50) & (span.notna().mean() >= 0.95)]
w = w[keep]
rng = np.random.default_rng(C.SEED)
ev_windows = [(pd.Timestamp(e["start"]) - pd.Timedelta(days=7), pd.Timestamp(e["end"]) + pd.Timedelta(days=7)) for e in C.EVENTS if e["kind"] != "정책"]
starts = pd.date_range("2024-06-01", "2025-10-14")
LEVELS, N, LEN = [0.0, 0.10, 0.20, 0.30], 100, 5
rows = []
for lv in LEVELS:
    done = 0
    while done < N:
        d = starts[rng.integers(len(starts))]
        e = d + pd.Timedelta(days=LEN - 1)
        if any(not (e < a or d > b) for a, b in ev_windows):
            continue
        units = list(rng.choice(keep, size=3, replace=False))
        w2 = inject_effect(w, units, d, e, lv)
        try:
            r = estimate(w2, Spec(d, e, units, n_space=0))
        except ValueError:
            continue
        rows.append({"true": lv * 100, "est": r.effect_pct, "lo": r.ci_low_pct, "hi": r.ci_high_pct, "p": r.p_time, "pre_ok": r.pretrend_ok})
        done += 1
df = pd.DataFrame(rows)
df.to_csv("analysis/recovery_runs.csv", index=False, encoding="utf-8-sig")
df["err"] = df["est"] - df["true"]
df["cover"] = (df["lo"] <= df["true"]) & (df["true"] <= df["hi"])
df["detect"] = (df["p"] < 0.05) & (df["est"] > 0)
z = df[df["true"] == 0]
record("rec_n_stations", len(keep), display=f"{len(keep):,}개", source=SRC)
record("rec_n_runs", len(df), display=f"{len(df):,}회", source=SRC)
record("rec_mae_pp", round(float(df["err"].abs().mean()), 2), display=f"{df['err'].abs().mean():.1f}%p", source=SRC)
record("rec_bias_pp", round(float(df["err"].mean()), 2), display=f"{df['err'].mean():+.1f}%p", source=SRC)
record("rec_cover_pct", round(float(df["cover"].mean() * 100), 1), display=f"{df['cover'].mean()*100:.0f}%", source=SRC)
record("rec_falsepos_pct", round(float((z["p"] < 0.05).mean() * 100), 1), display=f"{(z['p']<0.05).mean()*100:.0f}%", source=SRC)
for lv in (10, 20, 30):
    g = df[df["true"] == lv]
    record(f"rec_power{lv}_pct", round(float(g["detect"].mean() * 100), 1), display=f"{g['detect'].mean()*100:.0f}%", source=SRC)
    record(f"rec_mae{lv}_pp", round(float(g["err"].abs().mean()), 2), display=f"{g['err'].abs().mean():.1f}%p", source=SRC)
record("rec_pretrend_ok_pct", round(float(df["pre_ok"].mean() * 100), 1), display=f"{df['pre_ok'].mean()*100:.0f}%", source=SRC)

fig, ax = plt.subplots(figsize=(7.5, 3.6))
data = [df.loc[df["true"] == lv * 100, "est"] for lv in LEVELS]
ax.boxplot(data, positions=[lv * 100 for lv in LEVELS], widths=4, showfliers=False)
for lv in LEVELS:
    g = df.loc[df["true"] == lv * 100, "est"]
    ax.scatter(np.full(len(g), lv * 100) + rng.normal(0, 0.8, len(g)), g, s=6, alpha=0.35, color="#1565c0")
ax.plot([-3, 33], [-3, 33], ls="--", color="#c62828", lw=1, label="정답(심은 효과)")
ax.set_xlabel("심은 가짜 효과(%)"); ax.set_ylabel("Agent가 추정한 효과(%)")
ax.set_xticks([0, 10, 20, 30]); ax.legend(frameon=False, fontsize=8)
ax.set_title(f"가짜 효과 되찾기 시험(실제 정류소 {len(keep):,}개, 수준별 {N}회)", fontsize=10)
fig.tight_layout()
save_figure("fig_recovery", fig, "가짜 효과 되찾기 시험: 허브 743 실제 정류소 자료에 0·10·20·30% 효과를 심고 Agent가 되찾은 값(점=1회, 상자=사분위)", required=True)
