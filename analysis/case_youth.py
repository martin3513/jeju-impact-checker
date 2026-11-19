"""2025-08-01 어린이·청소년 버스 무료화 가운데 청소년 효과: 561 청소년 대 일반(어린이 제외), 전년 같은 요일 대비(삼중차분)."""
from pathlib import Path
import numpy as np
import pandas as pd
from _hub import panel
from impact_engine.effect import Spec, estimate
from impact_engine.loaders import wide
from _hub import record

SRC = "input/hub (561 일별 버스 승차 인원 수 현황)"
p = panel("hub_561", unit="user_type")
w = wide(p.df)
notes = [f"이용자 유형: {list(w.columns)}", f"기간: {w.index.min():%Y-%m-%d}~{w.index.max():%Y-%m-%d}"]
last = w.index.max()
end = min(pd.Timestamp("2025-10-19"), last)
cases = {"youth": ("2025-08-01", end), "youth_term": ("2025-09-01", end), "youth_placebo24": ("2024-08-01", pd.Timestamp("2024-10-19"))}
for key, (s, e) in cases.items():
    ww = w if key != "youth_placebo24" else w.loc[:"2025-07-31"]
    spec = Spec(s, e, ["청소년"], exclude=["어린이"], seasonal=True, n_space=0, min_mean=20, k_controls=1)
    log = []
    r = estimate(ww, spec, log=log)
    record(f"case_{key}_pct", round(r.effect_pct, 1), display=f"{r.effect_pct:+.1f}%", source=SRC)
    record(f"case_{key}_ci", f"{r.ci_low_pct:+.1f}~{r.ci_high_pct:+.1f}%", display=f"{r.ci_low_pct:+.1f}~{r.ci_high_pct:+.1f}%", source=SRC)
    record(f"case_{key}_p", round(r.p_time, 3), display=f"{r.p_time:.3f}", source=SRC)
    record(f"case_{key}_step", "있음" if r.step_change["flag"] else "없음", display="있음" if r.step_change["flag"] else "없음", source=SRC)
    notes.append(f"{key}: {r.effect_pct:+.1f}% ({r.ci_low_pct:+.1f}~{r.ci_high_pct:+.1f}) p={r.p_time:.3f} controls={r.controls} step={r.step_change} " + " / ".join(log))
# 청소년·일반 일 평균(시행 전 4주·후 4주) — 반출 가능 공개 자료
for u in ("청소년", "일반"):
    if u in w:
        a = w[u].loc["2025-07-04":"2025-07-31"].mean(); b = w[u].loc["2025-08-01":"2025-08-28"].mean()
        notes.append(f"{u} 일평균 전 {a:,.0f} → 후 {b:,.0f} ({(b/a-1)*100:+.1f}%)")
Path("analysis/case_youth_notes.md").write_text("\n".join(notes), encoding="utf-8")

# 512(일별 시간대별 승차)로 같은 계산을 한 번 더 — 교차 점검
try:
    p2 = panel("hub_512", unit="user_type")
    w2 = wide(p2.df)
    if "청소년" in w2 and "일반" in w2:
        s, e = cases["youth"]
        e = min(pd.Timestamp(e), w2.index.max())
        r2 = estimate(w2, Spec(s, e, ["청소년"], exclude=[c for c in w2.columns if c not in ("청소년", "일반")],
                               seasonal=True, n_space=0, min_mean=20, k_controls=1), log=[])
        record("case_youth512_pct", round(r2.effect_pct, 1), display=f"{r2.effect_pct:+.1f}%", source="input/hub (512)")
        notes.append(f"512 교차 점검: {r2.effect_pct:+.1f}% ({r2.ci_low_pct:+.1f}~{r2.ci_high_pct:+.1f}) p={r2.p_time:.3f}")
        Path("analysis/case_youth_notes.md").write_text("\n".join(notes), encoding="utf-8")
except FileNotFoundError:
    pass
