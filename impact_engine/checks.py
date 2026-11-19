"""반대 설명 점검표와 신뢰도 신호등."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from . import config as C

# 주요 공휴일(설·추석·대체·임시·선거일 포함). 출처: 「관공서의 공휴일에 관한 규정」·연도별 정부 지정 고시.
HOLIDAYS = {
    2019: ["01-01", "02-04", "02-05", "02-06", "03-01", "05-05", "05-06", "05-12", "06-06", "08-15", "09-12", "09-13", "09-14", "10-03", "10-09", "12-25"],
    2020: ["01-01", "01-24", "01-25", "01-26", "01-27", "03-01", "04-15", "04-30", "05-05", "06-06", "08-15", "08-17", "09-30", "10-01", "10-02", "10-03", "10-09", "12-25"],
    2021: ["01-01", "02-11", "02-12", "02-13", "03-01", "05-05", "05-19", "06-06", "08-15", "08-16", "09-20", "09-21", "09-22", "10-03", "10-04", "10-09", "10-11", "12-25"],
    2022: ["01-01", "01-31", "02-01", "02-02", "03-01", "03-09", "05-05", "05-08", "06-01", "06-06", "08-15", "09-09", "09-10", "09-11", "09-12", "10-03", "10-09", "10-10", "12-25"],
    2023: ["01-01", "01-21", "01-22", "01-23", "01-24", "03-01", "05-05", "05-27", "05-29", "06-06", "08-15", "09-28", "09-29", "09-30", "10-02", "10-03", "10-09", "12-25"],
    2024: ["01-01", "02-09", "02-10", "02-11", "02-12", "03-01", "04-10", "05-05", "05-06", "05-15", "06-06", "08-15", "09-16", "09-17", "09-18", "10-01", "10-03", "10-09", "12-25"],
    2025: ["01-01", "01-27", "01-28", "01-29", "01-30", "03-01", "03-03", "05-05", "05-06", "06-03", "06-06", "08-15", "10-03", "10-05", "10-06", "10-07", "10-08", "10-09", "12-25"],
    2026: ["01-01", "02-16", "02-17", "02-18", "03-01", "03-02", "05-05", "05-24", "05-25", "06-03", "06-06", "08-15", "08-17", "09-24", "09-25", "09-26", "10-03", "10-05", "10-09", "12-25"],
}


def holidays_between(a, b) -> list[pd.Timestamp]:
    a, b = pd.Timestamp(a), pd.Timestamp(b)
    out = []
    for y in range(a.year, b.year + 1):
        for md in HOLIDAYS.get(y, []):
            d = pd.Timestamp(f"{y}-{md}")
            if a <= d <= b:
                out.append(d)
    return out


@dataclass
class Flag:
    kind: str        # 겹치는 행사 / 날씨 / 공휴일 / 자료 공백 / 평행추세 / 크기 이상 / 도로 통제
    level: str       # 주의 / 경고
    text: str


@dataclass
class Verdict:
    light: str                       # 초록 / 노랑 / 빨강
    reason: str
    flags: list[Flag] = field(default_factory=list)


def confounder_flags(spec, result, events: pd.DataFrame | None = None, weather: pd.DataFrame | None = None,
                     treated_daily: pd.Series | None = None, place_keywords: list[str] | None = None,
                     road_control: bool | None = None) -> list[Flag]:
    s, e = spec.event_start, spec.event_end
    flags: list[Flag] = []
    # 1) 같은 기간 다른 행사
    if events is not None and len(events):
        ev = events.copy()
        ev["start"], ev["end"] = pd.to_datetime(ev["start"]), pd.to_datetime(ev["end"])
        near = ev[(ev["end"] >= s - pd.Timedelta(days=3)) & (ev["start"] <= e + pd.Timedelta(days=3))]
        if place_keywords:
            kw = "|".join(place_keywords)
            same_place = near[near["place"].fillna("").str.contains(kw, regex=True)]
        else:
            same_place = near.iloc[0:0]
        for _, row in same_place.iterrows():
            flags.append(Flag("겹치는 행사", "경고", f"같은 장소·기간에 「{row['name']}」({row['start']:%m-%d}~{row['end']:%m-%d})이 있어 효과가 섞일 수 있습니다."))
        others = len(near) - len(same_place)
        if others > 0:
            flags.append(Flag("겹치는 행사", "주의", f"같은 기간 도내 다른 행사 {others}건(장소 다름). 대조 정류소에도 영향이 있었는지 확인하세요."))
    # 2) 날씨(강수 10㎜ 이상·최대풍속 14㎧ 이상)
    if weather is not None and len(weather):
        wv = weather.set_index("date")
        ev_days = wv.reindex(pd.date_range(s, e))
        bad = ev_days[(ev_days["rain_mm"] >= C.RAIN_MM) | (ev_days["wind_max"] >= C.WIND_MS)]
        if len(bad):
            flags.append(Flag("날씨", "주의", f"행사 기간 {len(bad)}일에 강수 10㎜ 이상 또는 강풍(14㎧ 이상)이 있었습니다: "
                              + ", ".join(d.strftime("%m-%d") for d in bad.index)))
    # 3) 공휴일
    hol = holidays_between(s, e)
    if hol:
        flags.append(Flag("공휴일", "주의", "행사 기간에 공휴일 " + ", ".join(d.strftime("%m-%d") for d in hol)
                          + "이 있습니다. 요일 보정만으로는 공휴일 효과가 다 빠지지 않습니다."))
    pre_hol = holidays_between(s - pd.Timedelta(days=spec.pre_days), s - pd.Timedelta(days=1))
    if len(pre_hol) >= 3:
        flags.append(Flag("공휴일", "주의", f"사전기간에 공휴일 {len(pre_hol)}일(연휴)이 있어 기준선이 흔들릴 수 있습니다."))
    # 4) 자료 공백
    if treated_daily is not None:
        miss = treated_daily.reindex(pd.date_range(s - pd.Timedelta(days=spec.pre_days), e)).isna().sum()
        if miss:
            flags.append(Flag("자료 공백", "경고" if miss > 3 else "주의", f"처리군 자료가 {int(miss)}일 비어 있습니다."))
    # 5) 평행추세
    if not result.pretrend_ok:
        flags.append(Flag("평행추세", "경고", "대조군을 3번 다시 골라도 행사 직전 흐름이 처리군과 어긋났습니다(평행추세 가정 약함)."))
    # 6) 크기 이상(집계 방식 변화·임시 정류소 의심)
    if result.step_change.get("flag"):
        flags.append(Flag("기록 방식 변화", "주의", "시작일 하루 사이에 계단처럼 바뀌었습니다. 정책 효과일 수도 있지만, 요금·집계(카드 태그) 방식이 함께 바뀌었는지 확인하세요."))
    if abs(result.effect_pct) >= C.SIZE_WARN_PCT:
        flags.append(Flag("크기 이상", "경고", f"효과가 {result.effect_pct:+.0f}%로 매우 큽니다. 요금·집계 방식 변경, 임시 정류소·노선 우회가 없었는지 확인하세요."))
    # 7) 도로 통제·셔틀(이용자 확인)
    if road_control is None:
        flags.append(Flag("도로 통제", "주의", "행사 중 도로 통제·임시 정류소·셔틀버스 운영 여부를 확인하세요(정류소 이용이 기계적으로 바뀔 수 있음)."))
    elif road_control:
        flags.append(Flag("도로 통제", "경고", "도로 통제·임시 정류소가 있었습니다. 통제 정류소를 뺀 결과(기본)와 넣은 결과를 함께 보세요."))
    return flags


def verdict(result, flags: list[Flag]) -> Verdict:
    warn = [f for f in flags if f.level == "경고"]
    p_ok = result.p_time is not None and result.p_time < C.GREEN_P_TIME
    sp_ok = result.p_space is None or result.p_space < C.GREEN_P_SPACE
    if result.p_time is None or not (result.p_time < C.RED_P_TIME):
        return Verdict("빨강", "과거 '행사 없던 날'에도 이 정도 변화가 흔히 나타나 우연과 구별되지 않습니다.", flags)
    enough = result.n_placebo_time >= C.MIN_PLACEBO
    if p_ok and sp_ok and result.pretrend_ok and result.sens_sign_ok and enough and not warn:
        return Verdict("초록", "우연 범위를 벗어난 변화이고, 대조군 흐름도 행사 전까지 잘 맞았습니다.", flags)
    why = []
    if not p_ok:
        why.append("우연일 가능성(p<0.10)이 남아 있음")
    if not sp_ok:
        why.append("다른 단위(정류소·지역) 묶음에서도 비슷한 변화가 자주 나타남")
    if not result.pretrend_ok:
        why.append("행사 전 흐름이 대조군과 어긋남")
    if not result.sens_sign_ok:
        why.append("사전기간·대조군을 바꾸면 방향이 달라짐")
    if not enough:
        why.append(f"비교할 과거 '행사 없던 기간'이 {result.n_placebo_time}개로 적음")
    if warn:
        why.append("경고 " + ", ".join(sorted({f.kind for f in warn})))
    return Verdict("노랑", "효과로 볼 여지가 있으나 " + "; ".join(why) + ".", flags)
