"""가상 센터 데이터 생성 — 참가자가 센터를 방문할 수 없어, 공개 명세서(v13) 컬럼 구조 그대로 가상 CSV를 만든다.

센터 내려받기 형식(운영진 안내): UTF-8(BOM 없음), 모든 값 큰따옴표, 결측 NA, 1개월 단위, 파일명 Results_날짜_시간.csv.
값은 모두 지어낸 것이며 실제 제주 자료가 아니다. 시연용 가상 행사(효과 +15%)를 심어 두었다.
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pandas as pd

from .loaders import center_schema

EMD = ["일도1동", "일도2동", "이도1동", "이도2동", "삼도1동", "삼도2동", "용담1동", "용담2동", "건입동", "화북동", "삼양동", "봉개동",
       "아라동", "오라동", "연동", "노형동", "외도동", "이호동", "도두동", "한림읍", "애월읍", "구좌읍", "조천읍", "한경면", "추자면",
       "우도면", "송산동", "정방동", "중앙동", "천지동", "효돈동", "영천동", "동홍동", "서홍동", "대륜동", "대천동", "중문동", "예래동",
       "대정읍", "남원읍", "성산읍", "안덕면", "표선면"]
DOW_KR = ["월", "화", "수", "목", "금", "토", "일"]


def _write_month_files(df: pd.DataFrame, date_col: str, folder: Path, columns: list[str], stamp_base: str):
    folder.mkdir(parents=True, exist_ok=True)
    ym = df[date_col].astype(str).str[:6]
    for i, (m, g) in enumerate(df.groupby(ym)):
        name = f"Results_{stamp_base}_{100000 + i:06d}.csv"
        g[columns].fillna("NA").astype(str).to_csv(folder / name, index=False, quoting=csv.QUOTE_ALL, encoding="utf-8")


def make_sample(out: Path, start="2024-08-01", end="2025-11-30", event=("2025-10-10", "2025-10-14"), lift=0.15, seed=7) -> dict:
    rng = np.random.default_rng(seed)
    out = Path(out)
    days = pd.date_range(start, end)
    ev = pd.date_range(*event)
    spec = center_schema()

    # 3-03 정류소 정보(가상 이름·좌표)
    names = ["탑동광장(가상)", "탐라문화광장(가상)", "산지천(가상)", "동문시장(가상)"] + [f"가상정류소{i:03d}" for i in range(1, 37)]
    lon = 126.52 + rng.normal(0, 0.06, len(names))
    lat = 33.49 + rng.normal(0, 0.03, len(names))
    lon[:4] = 126.525 + rng.normal(0, 0.002, 4)
    lat[:4] = 33.516 + rng.normal(0, 0.002, 4)
    st = pd.DataFrame({"serial_number": range(1, len(names) + 1), "base_date": "20251101", "bus_station_id": range(1001, 1001 + len(names)),
                       "bus_station_name": names, "bus_city_type": "시내", "longitude": lon.round(6), "latitude": lat.round(6)})
    (out / "3-03").mkdir(parents=True, exist_ok=True)
    st[spec["3-03"]["csv_columns"]].astype(str).to_csv(out / "3-03" / "Results_20251201_090000.csv", index=False,
                                                      quoting=csv.QUOTE_ALL, encoding="utf-8")

    # 3-04 정류소별 이용 현황(시간대) — 승차·일반만, 06~22시
    hours = np.arange(6, 23)
    hour_w = np.exp(-((hours - 8) ** 2) / 6) + np.exp(-((hours - 18) ** 2) / 8) + 0.35
    dow_w = np.array([1.0, 1.0, 1.0, 1.02, 1.08, 0.8, 0.65])
    season = 1 + 0.08 * np.sin(2 * np.pi * (days.day_of_year.values - 60) / 365)
    common = np.exp(np.cumsum(rng.normal(0, 0.008, len(days))))
    rows = []
    for j, (sid, nm) in enumerate(zip(st["bus_station_id"], names)):
        base = rng.uniform(60, 500)
        own = np.exp(np.cumsum(rng.normal(0, 0.004, len(days))))
        daily = base * dow_w[days.day_of_week] * season * common * own
        if j < 4:
            daily = daily * np.where(days.isin(ev), 1 + lift, 1.0)
        lam = daily[:, None] * (hour_w / hour_w.sum())[None, :]
        cnt = rng.poisson(lam)
        for di, d in enumerate(days):
            for hi, h in enumerate(hours):
                rows.append((d.strftime("%Y%m%d"), DOW_KR[d.day_of_week], int(h), sid, nm, "승차", "일반", "카드", int(cnt[di, hi])))
    b = pd.DataFrame(rows, columns=spec["3-04"]["csv_columns"])
    _write_month_files(b, "base_date", out / "3-04", spec["3-04"]["csv_columns"], "20251201")

    # 1-32 탐나는전 이용 현황(읍면동·일) — 건입동·일도1동에 가상 행사 효과
    rows = []
    biz = [("5812", "일반음식점", "음식"), ("5311", "슈퍼마켓", "유통"), ("7204", "예체능계학원", "기타")]
    for e in EMD:
        base = rng.uniform(2e6, 2e7)
        own = np.exp(np.cumsum(rng.normal(0, 0.006, len(days))))
        amt = base * dow_w[days.day_of_week] * common * own * np.where(days.isin(ev) & (e in ("건입동", "일도1동")), 1 + lift, 1)
        for di, d in enumerate(days):
            for bc, bn, ind in biz:
                a = amt[di] * rng.uniform(0.2, 0.5)
                c = max(0, int(rng.poisson(a / 15000)))
                rows.append((d.strftime("%Y%m%d"), "63000", "BCCD", "BC카드", bc, bn, ind, int(a), c, e,
                             "동문재래시장" if e == "일도1동" else "미분류"))
    t = pd.DataFrame(rows, columns=spec["1-32"]["csv_columns"])
    _write_month_files(t, "base_ymd", out / "1-32", spec["1-32"]["csv_columns"], "20251201")

    # 5-02 일일 날씨(관측소 1곳)
    wv = pd.DataFrame({"base_date": days.strftime("%Y%m%d"), "observatory_code": "184",
                       "average_temperature": (16 + 8 * np.sin(2 * np.pi * (days.day_of_year.values - 110) / 365)).round(1),
                       "lowest_temperature": "NA", "lowest_temperature_time": "NA", "highest_temperature": "NA",
                       "highest_temperature_time": "NA",
                       "daily_rainfall": np.where(rng.random(len(days)) < 0.25, rng.gamma(1.2, 8, len(days)), 0).round(1),
                       "maximum_wind_speed": rng.gamma(4, 2.2, len(days)).round(1), "maximum_wind_speed_time": "NA",
                       "average_wind_speed": rng.gamma(3, 1.2, len(days)).round(1), "maximum_wind_speed_direction": "NA"})
    _write_month_files(wv, "base_date", out / "5-02", spec["5-02"]["csv_columns"], "20251201")
    return {"stations": len(names), "days": len(days), "event": event, "lift": lift}
