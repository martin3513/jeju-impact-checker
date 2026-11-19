"""순효과 추정: 대조군 자동 선택 → 이중차분(비율 모형) → 사건연구 → 위약검정(시점·지역).

모형(비율 이중차분)
  r(t) = log(처리군 합 + 1) − log(대조군 합 + 1)
  요일 보정: 사전기간의 요일별 평균을 뺀다. 계절 보정(seasonal=True): 364일 전 같은 요일 값을 뺀다.
  효과(로그) = 행사기간 r 평균 − 사전기간 r 평균,  증감률 = exp(효과) − 1
  반사실 처리군 = (대조군 + 1)·exp(사전 기준 + 요일 보정) − 1 → 순증 인원 = Σ(실측 − 반사실)
추론: 같은 대조군으로 과거의 '행사 없던 날'에 가짜 행사를 놓고 같은 계산을 반복한 분포(위약검정)로
     p값과 95% 구간을 만든다. 지역 위약은 처리군 대신 무작위 단위 묶음을 넣는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd

from . import config as C


@dataclass
class Spec:
    event_start: pd.Timestamp
    event_end: pd.Timestamp
    treated: list[str]
    pre_days: int = C.ATTEMPTS[0][0]     # 사전기간 길이
    gap_days: int = 0                     # 사전기간과 행사 사이 띄움
    k_controls: int = C.ATTEMPTS[0][1]
    min_mean: float = C.MIN_MEAN          # 대조 후보의 사전기간 하루 평균 최소값
    min_coverage: float = C.MIN_COVERAGE
    exclude: list[str] = field(default_factory=list)   # 파급·도로 통제 우려로 대조군에서 뺄 단위
    seasonal: bool | None = None          # 364일 전 같은 요일 대비. None 이면 기간 길이로 자동
    history_days: int = C.HISTORY_DAYS    # 위약검정에 쓰는 과거 기간
    avoid_dates: list[tuple[pd.Timestamp, pd.Timestamp]] = field(default_factory=list)  # 위약에서 피할 다른 행사
    n_space: int = C.N_SPACE
    seed: int = C.SEED

    def __post_init__(self):
        self.event_start = pd.Timestamp(self.event_start)
        self.event_end = pd.Timestamp(self.event_end)
        if self.seasonal is None:
            self.seasonal = self.length > C.SEASONAL_MIN_DAYS
        if self.length > C.SEASONAL_MIN_DAYS and self.history_days < C.LONG_HISTORY_DAYS:
            self.history_days = C.LONG_HISTORY_DAYS

    @property
    def length(self) -> int:
        return int((self.event_end - self.event_start).days) + 1


def _agg(w: pd.DataFrame, units: list[str]) -> pd.Series:
    return w[units].sum(axis=1, min_count=1)


def _ratio(yt: pd.Series, yc: pd.Series, seasonal: bool) -> pd.Series:
    r = np.log1p(yt) - np.log1p(yc)
    if seasonal:
        r = r - r.shift(364)
    return r


def _dow_adjust(r: pd.Series, pre_idx: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series]:
    pre = r.reindex(pre_idx).dropna()
    dow = pre.groupby(pre.index.day_of_week).mean() - pre.mean()
    adj = r - r.index.day_of_week.map(dow.reindex(range(7)).fillna(0)).values
    return adj, dow


def _effect_at(r: pd.Series, start: pd.Timestamp, length: int, pre_days: int, gap: int) -> float:
    ev = pd.date_range(start, periods=length, freq="D")
    pre = pd.date_range(start - pd.Timedelta(days=gap + pre_days), periods=pre_days, freq="D")
    adj, _ = _dow_adjust(r, pre)
    a, b = adj.reindex(ev).dropna(), adj.reindex(pre).dropna()
    if len(a) < max(1, length * 0.6) or len(b) < pre_days * 0.6:
        return np.nan
    return float(a.mean() - b.mean())


def candidate_pool(w: pd.DataFrame, spec: Spec) -> list[str]:
    pre = pd.date_range(spec.event_start - pd.Timedelta(days=spec.gap_days + spec.pre_days), periods=spec.pre_days)
    ev = pd.date_range(spec.event_start, spec.event_end)
    blocked = set(spec.treated) | set(spec.exclude)
    wp, we = w.reindex(pre), w.reindex(ev)
    ok = (wp.notna().mean() >= spec.min_coverage) & (we.notna().mean() >= spec.min_coverage) & (wp.mean() >= spec.min_mean)
    return [u for u in ok[ok].index if u not in blocked]


def match_controls(w: pd.DataFrame, spec: Spec, pool: list[str], pre_days: int, k: int, how: str = "rmse") -> list[str]:
    """사전기간 추세가 처리군과 가장 비슷한 대조 단위 k개(벡터 계산)."""
    pre = pd.date_range(spec.event_start - pd.Timedelta(days=spec.gap_days + pre_days), periods=pre_days)
    yt = np.log1p(_agg(w, spec.treated).reindex(pre))
    yt = yt - yt.mean()
    if not pool:
        return []
    yc = np.log1p(w[pool].reindex(pre))
    yc = yc - yc.mean()
    m = yc.notna() & yt.notna().values[:, None]
    enough = m.sum() >= pre_days * 0.6
    if how == "corr":
        a = yc.where(m).sub(yc.where(m).mean())
        b = pd.DataFrame(np.repeat(yt.values[:, None], len(pool), axis=1), index=yc.index, columns=pool).where(m)
        b = b.sub(b.mean())
        c = (a * b).sum() / np.sqrt((a ** 2).sum() * (b ** 2).sum())
        score = (-c).where(enough & np.isfinite(c))
    else:
        d = yc.sub(yt, axis=0).where(m)
        score = np.sqrt((d ** 2).mean()).where(enough)
    score = score.dropna().sort_values(kind="mergesort")
    return list(score.index[:k])


def _blocked_day(d: pd.Timestamp, length: int, spec: Spec) -> bool:
    end = d + pd.Timedelta(days=length - 1)
    pad = pd.Timedelta(days=C.AVOID_PAD_DAYS)
    windows = [(spec.event_start - pad, spec.event_end + pad)] + [(pd.Timestamp(a) - pad, pd.Timestamp(b) + pad) for a, b in spec.avoid_dates]
    for a, b in windows:
        if not (end < pd.Timestamp(a) or d > pd.Timestamp(b)):
            return True
    return False


def placebo_time(r: pd.Series, spec: Spec, pre_days: int) -> np.ndarray:
    """과거 '행사 없던 날'에 같은 길이의 가짜 행사를 놓고 계산한 효과 분포."""
    lo = spec.event_start - pd.Timedelta(days=spec.history_days)
    hi = spec.event_start - pd.Timedelta(days=spec.length + 7)
    vals = []
    for d in pd.date_range(lo, hi, freq="D"):
        if _blocked_day(d, spec.length, spec):
            continue
        v = _effect_at(r, d, spec.length, pre_days, spec.gap_days)
        if np.isfinite(v):
            vals.append(v)
    return np.array(vals)


def _p_two_sided(x: float, null: np.ndarray) -> float:
    if len(null) == 0 or not np.isfinite(x):
        return np.nan
    return float((1 + np.sum(np.abs(null - np.median(null)) >= abs(x - np.median(null)))) / (1 + len(null)))


@dataclass
class Result:
    effect_log: float
    effect_pct: float
    ci_low_pct: float
    ci_high_pct: float
    p_time: float
    p_space: float | None
    pretrend_p: float
    pretrend_ok: bool
    net_count: float | None
    observed_total: float
    counterfactual_total: float
    n_placebo_time: int
    n_placebo_space: int
    controls: list[str]
    attempts: list[dict]
    sensitivity: list[dict]
    sens_sign_ok: bool
    step_change: dict
    event_study: pd.DataFrame          # date, rel_day, effect_pct, band_low_pct, band_high_pct
    series: pd.DataFrame               # date, treated, counterfactual
    placebo_time_dist: np.ndarray
    placebo_space_dist: np.ndarray

    def summary(self) -> dict:
        d = {k: v for k, v in asdict(self).items()
             if k not in ("event_study", "series", "placebo_time_dist", "placebo_space_dist")}
        return d


def estimate(w: pd.DataFrame, spec: Spec, max_attempts: int = 3, log=None) -> Result:
    """대조군 선택(최대 3회 재선택) → 효과·위약검정·사건연구."""
    log = log if log is not None else []
    missing = [u for u in spec.treated if u not in w.columns]
    if missing:
        raise ValueError(f"처리군 단위가 자료에 없습니다: {missing}")
    pool = candidate_pool(w, spec)
    if not pool:
        raise ValueError("대조군 후보가 없습니다. 기간·최소 이용량 조건을 확인하세요.")
    tries = [(spec.pre_days, spec.k_controls, C.ATTEMPTS[0][2])] + list(C.ATTEMPTS[1:])
    tries = tries[:max_attempts]
    attempts = []
    chosen = None
    for i, (pre_days, k, how) in enumerate(tries, 1):
        controls = match_controls(w, spec, pool, pre_days, min(k, len(pool)), how)
        if not controls:
            continue
        r = _ratio(_agg(w, spec.treated), _agg(w, controls), spec.seasonal)
        null = placebo_time(r, spec, pre_days)
        # 평행추세 점검: 행사 직전 같은 길이 구간에 가짜 행사를 놓고 우연 범위 안인지
        fake_start = spec.event_start - pd.Timedelta(days=spec.length + 7)
        fake = _effect_at(r, fake_start, spec.length, pre_days, spec.gap_days)
        pre_p = _p_two_sided(fake, null)
        ok = bool(np.isfinite(pre_p) and pre_p >= C.PRETREND_P)
        attempts.append({"attempt": i, "pre_days": pre_days, "k": len(controls), "match": how,
                         "pretrend_fake_pct": float(np.expm1(fake)) * 100 if np.isfinite(fake) else None,
                         "pretrend_p": pre_p, "ok": ok})
        log.append(f"[설계] 시도 {i}: 사전 {pre_days}일·대조 {len(controls)}개({how}) → 직전 가짜행사 p={pre_p:.2f} "
                   + ("통과" if ok else "불통과 → 다시 고름" if i < len(tries) else "불통과(평행추세 약함)"))
        chosen = (pre_days, controls, r, null, pre_p, ok)
        if ok:
            break
    if chosen is None:
        raise ValueError("대조군을 고르지 못했습니다.")
    pre_days, controls, r, null, pre_p, ok = chosen
    eff = _effect_at(r, spec.event_start, spec.length, pre_days, spec.gap_days)
    p_time = _p_two_sided(eff, null)
    if len(null):
        c = null - np.median(null)
        lo, hi = np.quantile(c, [0.025, 0.975])
        ci = (eff - hi, eff - lo)
    else:
        ci = (np.nan, np.nan)

    # 지역 위약검정: 처리군 대신 무작위 단위 묶음(대조군과 겹치지 않게)
    rng = np.random.default_rng(spec.seed)
    others = [u for u in pool if u not in controls]
    space = []
    n_t = len(spec.treated)
    if len(others) >= max(5, n_t):
        yc = _agg(w, controls)
        for _ in range(spec.n_space):
            s = list(rng.choice(others, size=n_t, replace=False))
            rs = _ratio(_agg(w, s), yc, spec.seasonal)
            v = _effect_at(rs, spec.event_start, spec.length, pre_days, spec.gap_days)
            if np.isfinite(v):
                space.append(v)
    space = np.array(space)
    p_space = _p_two_sided(eff, space) if len(space) >= 20 else None

    # 사건연구(행사 앞뒤 14일)와 반사실 계열
    pre = pd.date_range(spec.event_start - pd.Timedelta(days=spec.gap_days + pre_days), periods=pre_days)
    adj, dow = _dow_adjust(r, pre)
    base = adj.reindex(pre).mean()
    win = pd.date_range(spec.event_start - pd.Timedelta(days=14), spec.event_end + pd.Timedelta(days=14))
    daily = (adj.reindex(win) - base)
    hist = pd.date_range(spec.event_start - pd.Timedelta(days=spec.history_days), spec.event_start - pd.Timedelta(days=8))
    hist_dev = (adj.reindex(hist) - adj.reindex(hist).rolling(pre_days, min_periods=pre_days // 2).mean()).dropna()
    b_lo, b_hi = (np.quantile(hist_dev, [0.025, 0.975]) if len(hist_dev) > 30 else (np.nan, np.nan))
    es = pd.DataFrame({"date": win, "rel_day": (win - spec.event_start).days,
                       "effect_pct": np.expm1(daily.values) * 100,
                       "band_low_pct": np.expm1(b_lo) * 100, "band_high_pct": np.expm1(b_hi) * 100})

    yt, yc = _agg(w, spec.treated), _agg(w, controls)
    ev = pd.date_range(spec.event_start, spec.event_end)
    raw_r = _ratio(yt, yc, False)
    raw_adj, raw_dow = _dow_adjust(raw_r, pre)
    raw_base = raw_adj.reindex(pre).mean()
    dow_term = pd.Series(win.day_of_week.map(raw_dow.reindex(range(7)).fillna(0)).values, index=win)
    cf = np.expm1(np.log1p(yc.reindex(win)) + raw_base + dow_term)
    series = pd.DataFrame({"date": win, "treated": yt.reindex(win).values, "counterfactual": cf.values})
    obs_total = float(yt.reindex(ev).sum())
    cf_total = float(cf.reindex(ev).sum())
    net = None if spec.seasonal else obs_total - cf_total

    # 민감도: 사전기간 28일, 대조군 절반으로 다시 계산해 부호가 같은지
    sens = []
    for pd_days, k in ((28, max(3, len(controls) // 2)), (pre_days, max(3, len(controls) // 2))):
        cs = match_controls(w, spec, pool, pd_days, k, "rmse")
        if cs:
            rr = _ratio(_agg(w, spec.treated), _agg(w, cs), spec.seasonal)
            v = _effect_at(rr, spec.event_start, spec.length, pd_days, spec.gap_days)
            sens.append({"pre_days": pd_days, "k": len(cs), "effect_pct": float(np.expm1(v) * 100) if np.isfinite(v) else None})
    sens_ok = all(s["effect_pct"] is not None and np.sign(s["effect_pct"]) == np.sign(np.expm1(eff)) for s in sens) if sens else False

    # 계단형 기록 변화: 시작일 하루 사이 변화가 사전기간 일간 변화의 MAD 대비 지나치게 큰지
    rr0 = _ratio(yt, yc, False)
    dif = rr0.diff()
    pre_d = dif.reindex(pre).dropna()
    mad = float(np.median(np.abs(pre_d - np.median(pre_d)))) if len(pre_d) else np.nan
    jump = float(dif.get(spec.event_start, np.nan))
    step = {"jump_log": jump, "mad": mad,
            "flag": bool(np.isfinite(jump) and np.isfinite(mad) and mad > 0 and abs(jump) > C.STEP_MAD * mad)}
    log.append(f"[추정] 순효과 {np.expm1(eff)*100:+.1f}% (95% 구간 {np.expm1(ci[0])*100:+.1f}~{np.expm1(ci[1])*100:+.1f}%), "
               f"시점 위약 p={p_time:.3f}(n={len(null)})" + (f", 지역 위약 p={p_space:.3f}(n={len(space)})" if p_space is not None else ""))
    return Result(float(eff), float(np.expm1(eff) * 100), float(np.expm1(ci[0]) * 100), float(np.expm1(ci[1]) * 100),
                  p_time, p_space, float(pre_p), ok, net, obs_total, cf_total, len(null), len(space),
                  controls, attempts, sens, bool(sens_ok), step, es, series, null, space)


def inject_effect(w: pd.DataFrame, units: list[str], start, end, pct: float) -> pd.DataFrame:
    """가짜 효과 심기: 지정 단위·기간 값에 (1+pct)를 곱한다(되찾기 시험용)."""
    w2 = w.copy()
    idx = pd.date_range(start, end)
    w2.loc[w2.index.isin(idx), units] = w2.loc[w2.index.isin(idx), units] * (1 + pct)
    return w2
