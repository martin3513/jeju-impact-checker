"""제주데이터허브 상세 화면에 공개된 표본 행(743·561·512, 2019-01-01 일부)으로 판별·읽기 시험.
전체 파일(수백 MB)로는 시험하지 않았다(참가자가 내려받지 못함)."""
from pathlib import Path
from impact_engine.loaders import detect_dataset, load_hub_743, load_hub_561, load_hub_512

FX = Path(__file__).parent.parent / "data" / "hub_sample"   # 앱 화면의 '표본 미리보기'와 같은 파일


def test_detect_hub_files():
    assert detect_dataset(FX / "hub_743_sample.csv").dataset == "hub_743"
    assert detect_dataset(FX / "hub_561_sample.csv").dataset == "hub_561"
    assert detect_dataset(FX / "hub_512_sample.csv").dataset == "hub_512"


def test_load_hub_743_strips_station_names_and_sums_user_types():
    p = load_hub_743(FX / "hub_743_sample.csv")
    assert p.exportable_raw and p.unit_kind == "정류소"
    assert all(u == u.strip() for u in p.df["unit"])          # 정류소 이름 뒤 공백 제거
    assert p.df["date"].dt.strftime("%Y%m%d").eq("20190101").all()
    assert (p.df["value"] > 0).all()


def test_load_hub_561_by_user_type_and_route():
    p = load_hub_561(FX / "hub_561_sample.csv")
    assert set(p.df["unit"]) <= {"어린이", "일반", "청소년"}
    r = load_hub_561(FX / "hub_561_sample.csv", unit="route")
    assert all("-" not in u for u in r.df["unit"])             # 101-1 → 101


def test_load_hub_512_with_bom_header():
    p = load_hub_512(FX / "hub_512_sample.csv")
    assert len(p.df) > 0 and p.unit_kind == "이용자 유형"
