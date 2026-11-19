"""데이터 불러오기: 제주데이터허브 공개 파일과 제주빅데이터센터 CSV를 '일 × 단위' 표준 패널로 바꾼다.

표준 패널(long): columns = [date(datetime64), unit(str), value(float)]
  - unit: 정류소 이름, 노선 번호, 이용자 유형, 읍면동 등 분석 단위
"""
from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

SCHEMA_PATH = Path(__file__).with_name("center_schema.json")
MASK_RE = re.compile(r"^\*+$")


def center_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _read_head(path: Path, nbytes: int = 65536) -> tuple[str, str]:
    raw = Path(path).read_bytes()[:nbytes]
    for enc in ("utf-8-sig", "cp949"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8"


def sniff_columns(path: Path) -> tuple[list[str], str]:
    """첫 줄 머리글과 인코딩."""
    text, enc = _read_head(path)
    first = text.splitlines()[0] if text else ""
    cols = next(iter(pd.read_csv(io.StringIO(first), header=None, dtype=str).values.tolist()), [])
    cols = [str(c).strip().lstrip("﻿") for c in cols]
    return cols, enc


# ---- 허브 공개 파일 머리글 ----
HUB_SIGNATURES = {
    "hub_743": {"base_date", "station_name", "user_type", "user_count"},
    "hub_561": {"base_date", "act_type", "bus_number", "user_type", "user_count"},
    "hub_512": {"기준일", "요일", "시간대", "이용자 유형", "이용자 수"},
}
HUB_TITLES = {
    "hub_743": "이용자 유형별 버스정류소 이용 인원 현황(제주데이터허브)",
    "hub_561": "일별 버스 승차 인원 수 현황(제주데이터허브)",
    "hub_512": "일별 시간대별 버스 승차 인원 수 현황(제주데이터허브)",
}


@dataclass
class Detected:
    dataset: str            # hub_743 / 3-04 / 1-32 / unknown …
    title: str
    score: float            # 머리글 일치 정도(0~1)
    encoding: str
    columns: list[str] = field(default_factory=list)
    export: str = ""        # 반출 가능/불가능 표기(센터 데이터)


def detect_dataset(path: Path) -> Detected:
    """머리글로 데이터 종류를 판별한다(허브 3종 + 센터 명세서 71종)."""
    cols, enc = sniff_columns(path)
    cs = set(cols)
    best = Detected("unknown", "알 수 없는 파일", 0.0, enc, cols)
    for key, sig in HUB_SIGNATURES.items():
        score = len(cs & sig) / len(sig | cs) if cs else 0
        if sig <= cs and score > best.score:
            best = Detected(key, HUB_TITLES[key], score, enc, cols, "공개 데이터")
    for did, spec in center_schema().items():
        sig = set(spec.get("csv_columns") or [])
        if not sig:
            continue
        score = len(cs & sig) / len(sig | cs)
        if score > best.score and score >= 0.6:
            best = Detected(did, spec["title"], score, enc, cols, spec.get("export") or "")
    return best


def _to_num(s: pd.Series) -> pd.Series:
    """가림값('*', '**')과 NA를 결측으로, 나머지는 숫자로."""
    s = s.astype(str).str.strip()
    s = s.mask(s.str.match(MASK_RE) | s.isin(["NA", "NULL", "", "nan"]))
    return pd.to_numeric(s.str.replace(",", "", regex=False), errors="coerce")


def _to_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s.astype(str).str.strip().str[:8], format="%Y%m%d", errors="coerce")


def _clean_name(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.replace(r"\s+", " ", regex=True)


@dataclass
class Panel:
    """표준 패널과 출처 정보."""
    df: pd.DataFrame                 # date, unit, value
    dataset: str
    title: str
    unit_kind: str                   # 정류소 / 이용자 유형 / 노선 / 읍면동
    measure: str                     # 버스 이용 인원 등
    exportable_raw: bool             # 원본 반출 가능 여부(반출 점검에 사용)
    notes: list[str] = field(default_factory=list)


def _read_csv(path: Path, enc: str, usecols: list[str], chunksize: int | None = None):
    return pd.read_csv(path, encoding=enc, dtype=str, usecols=usecols, chunksize=chunksize,
                       keep_default_na=False)


def load_hub_743(path: Path, by_user_type: bool = False, chunksize: int = 2_000_000) -> Panel:
    """743 정류소별 일 이용 인원 → (date, 정류소, 인원). by_user_type 이면 unit=정류소|유형."""
    det = detect_dataset(path)
    parts = []
    for ch in _read_csv(path, det.encoding, ["base_date", "station_name", "user_type", "user_count"], chunksize):
        ch["date"] = _to_date(ch["base_date"])
        ch["unit"] = _clean_name(ch["station_name"])
        if by_user_type:
            ch["unit"] = ch["unit"] + "|" + _clean_name(ch["user_type"])
        ch["value"] = _to_num(ch["user_count"])
        parts.append(ch.groupby(["date", "unit"], as_index=False)["value"].sum())
    df = pd.concat(parts).groupby(["date", "unit"], as_index=False)["value"].sum()
    return Panel(df, "hub_743", HUB_TITLES["hub_743"], "정류소", "버스 이용 인원(승차·환승 태그)", True)


def load_hub_561(path: Path, unit: str = "user_type", chunksize: int = 2_000_000) -> Panel:
    """561 노선별 일 승차 인원 → unit='user_type'(이용자 유형별 합) 또는 'route'(노선 번호별 합)."""
    det = detect_dataset(path)
    parts = []
    for ch in _read_csv(path, det.encoding, ["base_date", "act_type", "bus_number", "user_type", "user_count"], chunksize):
        ch["date"] = _to_date(ch["base_date"])
        if unit == "route":
            ch["unit"] = _clean_name(ch["bus_number"]).str.split("-").str[0]
        else:
            ch["unit"] = _clean_name(ch["user_type"])
        ch["value"] = _to_num(ch["user_count"])
        parts.append(ch.groupby(["date", "unit"], as_index=False)["value"].sum())
    df = pd.concat(parts).groupby(["date", "unit"], as_index=False)["value"].sum()
    kind = "노선" if unit == "route" else "이용자 유형"
    return Panel(df, "hub_561", HUB_TITLES["hub_561"], kind, "버스 승차 인원", True)


def load_hub_512(path: Path, unit: str = "user_type") -> Panel:
    det = detect_dataset(path)
    raw = pd.read_csv(path, encoding=det.encoding, dtype=str, keep_default_na=False)
    raw.columns = [c.strip().lstrip("﻿") for c in raw.columns]
    raw["date"] = _to_date(raw["기준일"])
    raw["unit"] = _clean_name(raw["이용자 유형"] if unit == "user_type" else raw["시간대"])
    raw["value"] = _to_num(raw["이용자 수"])
    df = raw.groupby(["date", "unit"], as_index=False)["value"].sum()
    return Panel(df, "hub_512", HUB_TITLES["hub_512"], "이용자 유형" if unit == "user_type" else "시간대",
                 "버스 승차 인원", True)


# ---- 센터 CSV (이용자가 센터 화면에서 1개월 단위로 내려받은 파일) ----
CENTER_PANELS = {
    # dataset: (날짜열, 단위열, 값열, 단위 이름, 측정 이름)
    "3-04": ("base_date", "bus_station_name", "user_count", "정류소", "버스 이용 인원"),
    "3-02": ("base_date", "bus_route_name", "user_count", "노선", "버스 이용 인원"),
    "1-32": ("base_ymd", "emd", "amount", "읍면동", "탐나는전 결제 금액"),
    "4-11": ("base_date", "emd_nm", "visit_pop_cnt", "읍면동", "방문 인구"),
    "4-10": ("base_date", "emd_nm", "visit_pop_cnt", "읍면동", "방문 인구"),
}


def load_center_files(paths: list[Path], value_col: str | None = None, filters: dict | None = None) -> Panel:
    """같은 종류의 센터 CSV 여러 개(월별 파일)를 합쳐 표준 패널로."""
    dets = [detect_dataset(p) for p in paths]
    kinds = {d.dataset for d in dets}
    if len(kinds) != 1:
        raise ValueError(f"서로 다른 종류의 파일이 섞였습니다: {sorted(kinds)}")
    did = kinds.pop()
    if did not in CENTER_PANELS:
        raise ValueError(f"효과 분석에 쓸 수 없는 데이터입니다: {did}")
    dcol, ucol, vcol, kind, measure = CENTER_PANELS[did]
    vcol = value_col or vcol
    frames = []
    for p, d in zip(paths, dets):
        raw = pd.read_csv(p, encoding=d.encoding, dtype=str, keep_default_na=False)
        raw.columns = [c.strip() for c in raw.columns]
        for k, v in (filters or {}).items():
            if k in raw.columns:
                raw = raw[raw[k].astype(str).str.strip().isin(v if isinstance(v, list) else [v])]
        frames.append(raw)
    raw = pd.concat(frames, ignore_index=True).drop_duplicates()
    out = pd.DataFrame({"date": _to_date(raw[dcol]), "unit": _clean_name(raw[ucol]), "value": _to_num(raw[vcol])})
    masked = int(out["value"].isna().sum())
    df = out.groupby(["date", "unit"], as_index=False)["value"].sum(min_count=1)
    spec = center_schema()[did]
    notes = [f"가림값·결측 {masked:,}칸은 합계에서 빠졌습니다."] if masked else []
    exportable = is_exportable(spec.get("export") or "")
    return Panel(df, did, spec["title"], kind, measure, exportable, notes)


def load_center_stations(path: Path) -> pd.DataFrame:
    """3-03 정류소 정보 → name, lon, lat (같은 이름 여러 방향은 평균 좌표)."""
    d = detect_dataset(path)
    raw = pd.read_csv(path, encoding=d.encoding, dtype=str, keep_default_na=False)
    df = pd.DataFrame({"name": _clean_name(raw["bus_station_name"]),
                       "lon": pd.to_numeric(raw["longitude"], errors="coerce"),
                       "lat": pd.to_numeric(raw["latitude"], errors="coerce")})
    return df.dropna().groupby("name", as_index=False)[["lon", "lat"]].mean()


def load_weather(path: Path) -> pd.DataFrame:
    """5-02 일일 날씨 → date, rain_mm, wind_max (관측소 평균)."""
    d = detect_dataset(path)
    raw = pd.read_csv(path, encoding=d.encoding, dtype=str, keep_default_na=False)
    df = pd.DataFrame({"date": _to_date(raw["base_date"]),
                       "rain_mm": _to_num(raw["daily_rainfall"]),
                       "wind_max": _to_num(raw["maximum_wind_speed"])})
    return df.groupby("date", as_index=False).mean(numeric_only=True)


def is_exportable(text: str) -> bool:
    """명세서 반출 표기('데이터 반출 가능'/'데이터 반출 불가능')로 원본 반출 가능 여부. '불가'가 있으면 불가."""
    t = str(text).replace(" ", "")
    return ("가능" in t) and ("불가" not in t)


def cache_path(src: Path, tag: str, cache_dir: Path) -> Path:
    st = Path(src).stat()
    return Path(cache_dir) / f"{Path(src).stem}.{tag}.{st.st_size}.{int(st.st_mtime)}.pd{pd.__version__.split('.')[0]}.pkl"


def load_hub_cached(path: Path, kind: str, cache_dir: Path, **kw) -> Panel:
    """허브 대용량 파일은 '일×단위' 합계를 캐시(공개 데이터 집계만 보존)."""
    loader = {"hub_743": load_hub_743, "hub_561": load_hub_561, "hub_512": load_hub_512}[kind]
    tag = kind + "".join(f"_{k}-{v}" for k, v in sorted(kw.items()))
    cp = cache_path(path, tag, cache_dir)
    if cp.exists():
        df = pd.read_pickle(cp)
        meta = {"hub_743": ("정류소", "버스 이용 인원(승차·환승 태그)"), "hub_561": ("이용자 유형", "버스 승차 인원"),
                "hub_512": ("이용자 유형", "버스 승차 인원")}[kind]
        unit_kind = meta[0]
        if kind == "hub_561" and kw.get("unit") == "route":
            unit_kind = "노선"
        if kind == "hub_743" and kw.get("by_user_type"):
            unit_kind = "정류소|이용자 유형"
        return Panel(df, kind, HUB_TITLES[kind], unit_kind, meta[1], True, ["캐시에서 불러옴"])
    p = loader(path, **kw)
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    p.df.to_pickle(cp)
    return p


def wide(panel_df: pd.DataFrame) -> pd.DataFrame:
    """long → 날짜 × 단위 표(빠진 날은 NaN)."""
    w = panel_df.pivot_table(index="date", columns="unit", values="value", aggfunc="sum")
    full = pd.date_range(w.index.min(), w.index.max(), freq="D")
    return w.reindex(full)


def haversine_km(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(np.radians, (lon1, lat1, lon2, lat2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))
