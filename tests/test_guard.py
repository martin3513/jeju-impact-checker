import pandas as pd
from impact_engine.export_guard import guard_table, BLIND, SECONDARY
from impact_engine.llm import mask_values, write_narrative


def test_blind_and_secondary_suppression():
    df = pd.DataFrame({"인원": [120, 7, 45, 172]}, index=["가동", "나동", "다동", "합계"])
    out, rep = guard_table(df, ["인원"], raw_exportable=False, total_row="합계")
    assert out.loc["나동", "인원"] == BLIND
    assert out.loc["다동", "인원"] == SECONDARY      # 합계로 역산되지 않게 한 칸 더 가림
    assert rep.blinded_cells == 1 and rep.secondary_cells == 1


def test_exportable_raw_untouched():
    df = pd.DataFrame({"인원": [3, 5]})
    out, rep = guard_table(df, ["인원"], raw_exportable=True)
    assert out["인원"].tolist() == [3, 5]


def test_mask_values_keeps_dates():
    t, n = mask_values("2025-10-10 탐라문화제 때 1,234명에서 5678명으로 늘었나?")
    assert "2025-10-10" in t and "1,234" not in t and "5678" not in t and n == 2


def test_narrative_without_key_falls_back():
    txt, src = write_narrative({"effect_pct": 12.3, "p_time": 0.004}, "고정 문장")
    assert txt == "고정 문장"


def test_export_flag_parsing():
    from impact_engine.loaders import is_exportable, center_schema
    assert is_exportable("데이터 반출 가능")
    assert not is_exportable("데이터 반출 불가능")
    s = center_schema()
    assert not is_exportable(s["1-32"]["export"]) and not is_exportable(s["4-11"]["export"])
    assert is_exportable(s["3-04"]["export"])


def test_tamna_currency_is_not_exported_raw(tmp_path):
    from pathlib import Path
    from impact_engine.synth import make_sample
    from impact_engine.loaders import load_center_files
    from impact_engine.effect import Spec
    from impact_engine.pipeline import run
    make_sample(tmp_path / "s")
    p = load_center_files(sorted((tmp_path / "s" / "1-32").glob("*.csv")))
    assert p.exportable_raw is False
    a = run(p, Spec("2025-10-10", "2025-10-14", ["건입동", "일도1동"]), "q", tmp_path / "o", title="t", use_llm=False, make_docx=False)
    assert "순증(실측−반사실)" not in a.summary_rows and "증감률(%)" in a.summary_rows
