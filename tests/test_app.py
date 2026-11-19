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


def test_next_button_moves_to_data_tab():
    at = AppTest.from_file("../app.py", default_timeout=120).run()
    assert not at.exception
    btns = {b.label: b for b in at.button}
    btns["다음: ② 자료 넣기"].click().run()
    assert not at.exception
    assert at.session_state["step"] == "② 자료 넣기"


def test_hub_screen_shows_needed_files_and_sample():
    at = AppTest.from_file("../app.py", default_timeout=120).run()
    src = next(s for s in at.segmented_control if s.label == "자료 종류")
    src.set_value("제주데이터허브 공개 파일(data/hub 폴더)").run()
    assert not at.exception
    assert any("743번 파일" in m.value for m in at.markdown)        # 정류소 분석에 필요한 파일 안내
    assert any("판별 결과: 이용자 유형별 버스정류소 이용 인원 현황" in c.value for c in at.caption)  # 표본 미리보기


def test_next_buttons_follow_the_four_steps():
    at = AppTest.from_file("../app.py", default_timeout=120).run()
    {b.label: b for b in at.button}["가상 데이터 불러오기"].click().run()
    btns = {b.label: b for b in at.button}
    btns["다음: ③ 결과·신호등"].click().run()                 # 자료·처리군이 준비되면 ③으로
    assert at.session_state["step"] == "③ 결과·신호등"
    {b.label: b for b in at.button}["분석 실행"].click().run()
    {b.label: b for b in at.button}["다음: ④ 반출·보고서"].click().run()   # 분석이 끝나면 ④로
    assert not at.exception
    assert at.session_state["step"] == "④ 반출·보고서"
