"""대체 경로용: 가상 패널(요일·계절·공통 추세·단위별 추세·포아송 잡음)에서 가짜 효과 되찾기 시험. 허브 743 시험이 있으면 그것을 우선 쓴다."""
import numpy as np
import pandas as pd
from _hub import ENGINE  # noqa: F401  (impact_engine 경로 등록)
from impact_engine import config as C
from impact_engine.effect import Spec, estimate, inject_effect
from _hub import record, save_figure
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["font.family"] = "Malgun Gothic"; plt.rcParams["axes.unicode_minus"] = False

SRC = "가상 패널(impact_engine 시험용 생성 규칙, 단위 300개·900일)"
rng = np.random.default_rng(C.SEED)
idx = pd.date_range("2023-01-01", periods=900)
dow = np.array([1.0, 1.02, 1.0, 1.01, 1.08, 0.85, 0.7])
season = 1 + 0.15 * np.sin(2 * np.pi * np.arange(900) / 365)
common = np.exp(np.cumsum(rng.normal(0, 0.01, 900)))
cols = {}
for i in range(300):
    lam = rng.uniform(40, 800) * dow[idx.day_of_week] * season * common * np.exp(np.cumsum(rng.normal(0, 0.004, 900)))
    cols[f"S{i:03d}"] = rng.poisson(lam).astype(float)
w = pd.DataFrame(cols, index=idx)
rows = []
for lv in (0.0, 0.1, 0.2, 0.3):
    for _ in range(100):
        d = pd.Timestamp("2024-09-01") + pd.Timedelta(days=int(rng.integers(0, 250)))
        units = list(rng.choice(w.columns, size=3, replace=False))
        r = estimate(inject_effect(w, units, d, d + pd.Timedelta(days=4), lv), Spec(d, d + pd.Timedelta(days=4), units, n_space=0))
        rows.append((lv * 100, r.effect_pct, r.ci_low_pct, r.ci_high_pct, r.p_time))
df = pd.DataFrame(rows, columns=["true", "est", "lo", "hi", "p"])
err = (df.est - df.true).abs()
cover = ((df.lo <= df.true) & (df.true <= df.hi)).mean() * 100
fp = (df[df.true == 0].p < 0.05).mean() * 100
pw = ((df[df.true == 20].p < 0.05) & (df[df.true == 20].est > 0)).mean() * 100
record("recsyn_mae_pp", round(float(err.mean()), 2), display=f"{err.mean():.1f}%p", source=SRC)
record("recsyn_cover_pct", round(float(cover), 1), display=f"{cover:.0f}%", source=SRC)
record("recsyn_falsepos_pct", round(float(fp), 1), display=f"{fp:.0f}%", source=SRC)
record("recsyn_power20_pct", round(float(pw), 1), display=f"{pw:.0f}%", source=SRC)
record("recsyn_n_runs", len(df), display=f"{len(df)}회", source=SRC)
pw10 = ((df[df.true == 10].p < 0.05) & (df[df.true == 10].est > 0)).mean() * 100
record("recsyn_power10_pct", round(float(pw10), 1), display=f"{pw10:.0f}%", source=SRC)

fig, ax = plt.subplots(figsize=(7.5, 3.4))
lv = [0, 10, 20, 30]
ax.boxplot([df.loc[df.true == x, "est"] for x in lv], positions=lv, widths=4, showfliers=False)
for x in lv:
    g = df.loc[df.true == x, "est"]
    ax.scatter(np.full(len(g), x) + rng.normal(0, 0.8, len(g)), g, s=5, alpha=0.3, color="#1565c0")
ax.plot([-3, 33], [-3, 33], ls="--", color="#c62828", lw=1, label="정답(심은 효과)")
ax.set_xlabel("심은 가짜 효과(%)"); ax.set_ylabel("Agent가 추정한 효과(%)"); ax.set_xticks(lv)
ax.legend(frameon=False, fontsize=8)
ax.set_title(f"가짜 효과 되찾기 시험(가상 패널, 수준별 100회, 평균 오차 {err.mean():.1f}%p)", fontsize=10)
fig.tight_layout()
save_figure("fig_recovery", fig, "가짜 효과 되찾기 시험: 가상 패널(가상 단위 300개·900일)에 0·10·20·30% 효과를 심고 Agent가 되찾은 값(점=1회, 상자=사분위)", required=True)
