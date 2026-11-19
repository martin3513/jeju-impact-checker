"""모든 시험은 Claude API를 부르지 않는다(.env 에 키가 있어도). 실제 호출 확인은 analysis/measure_llm_usage.py 로 따로 한다."""
import pytest


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    monkeypatch.setenv("IMPACT_LLM", "off")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
