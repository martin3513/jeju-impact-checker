import numpy as np, pandas as pd
from impact_engine.effect import Spec, estimate, inject_effect

def synth(n_units=120, days=900, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-01-01", periods=days)
    dow = np.array([1.0, 1.02, 1.0, 1.01, 1.08, 0.85, 0.7])
    season = 1 + 0.15 * np.sin(2 * np.pi * np.arange(days) / 365)
    common = np.exp(np.cumsum(rng.normal(0, 0.01, days)))
    cols = {}
    for i in range(n_units):
        base = rng.uniform(40, 800)
        own = np.exp(np.cumsum(rng.normal(0, 0.004, days)))
        lam = base * dow[idx.day_of_week] * season * common * own
        cols[f"S{i:03d}"] = rng.poisson(lam).astype(float)
    return pd.DataFrame(cols, index=idx)

def test_recovers_20pct():
    w = synth(seed=5)
    t = ["S001", "S002", "S003"]
    w2 = inject_effect(w, t, "2025-03-10", "2025-03-14", 0.20)
    res = estimate(w2, Spec("2025-03-10", "2025-03-14", t, n_space=100))
    print(res.effect_pct, res.ci_low_pct, res.ci_high_pct, res.p_time, res.p_space, res.attempts)
    assert 10 < res.effect_pct < 30
    assert res.p_time < 0.05

def test_null_no_effect():
    w = synth(seed=5)
    t = ["S010", "S011"]
    res = estimate(w, Spec("2025-03-10", "2025-03-14", t, n_space=100))
    print(res.effect_pct, res.p_time)
    assert abs(res.effect_pct) < 10
