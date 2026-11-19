import json
from impact_engine import llm


def test_narrative_sends_no_numbers(monkeypatch):
    sent = {}

    def fake_call(system, user, schema=None, effort="low", max_tokens=4000, kind=""):
        sent["user"] = user
        return "{event} 기간 {measure}은 반사실보다 {effect} 달랐고 구간은 {ci}, p는 {p_time}, 신호등 {light}."
    monkeypatch.setattr(llm, "_call", fake_call)
    facts = {"event": "제64회 탐라문화제", "measure": "버스 이용 인원", "effect": "+16.8%", "ci": "+13.3%~+21.4%",
             "p_time": "0.004", "light": "초록"}
    text, src = llm.write_narrative(facts, "고정")
    assert "16.8" not in sent["user"] and "0.004" not in sent["user"] and "13.3" not in sent["user"]
    assert "+16.8%" in text and "0.004" in text and src.startswith("Claude")


def test_stray_number_falls_back(monkeypatch):
    monkeypatch.setattr(llm, "_call", lambda *a, **k: "{event}에서 {effect} 늘어 약 500명이 더 탔다.")
    text, src = llm.write_narrative({"event": "행사", "effect": "+5.0%"}, "고정")
    assert text == "고정"
