from streamlit.testing.v1 import AppTest


def test_app_runs_with_sample_data():
    at = AppTest.from_file("../app.py", default_timeout=120).run()
    assert not at.exception
    # ② 가상 데이터 불러오기 → ③ 분석 실행
    btns = {b.label: b for b in at.button}
    btns["가상 데이터 불러오기"].click().run()
    assert not at.exception
    btns = {b.label: b for b in at.button}
    btns["분석 실행"].click().run()
    assert not at.exception
    md = " ".join(m.value for m in at.markdown)
    assert "신뢰도 신호등" in md
