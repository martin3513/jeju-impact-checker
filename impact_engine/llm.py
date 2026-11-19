"""Claude API 연결(선택). 키가 없거나 막히면 None을 돌려주고, 호출하는 쪽은 규칙·고정 문장으로 대신한다.

보안 경계(기획서 4장과 같음)
  보낸다  : (질문 해석) 이용자 질문 문장(실값으로 보이는 숫자는 가림), 내장 행사 목록 이름·날짜(공개 자료), 분석 단위 종류
            (문장 작성) 값의 이름(자리표시자)·행사 이름(숫자 가림)·신호등 색 — 숫자 값은 '숫자값'으로 바꿔 보내고 로컬이 채움
  보내지 않음: CSV 행, 인원·건수·금액 원값, 정류소·읍면동별 원자료
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

DEFAULT_MODEL = "claude-opus-5-5"
API_HOST = "api.anthropic.com"

_NUM_RE = re.compile(r"(?<![\d.])(\d{1,3}(,\d{3})+|\d{3,})(?![\d.])")
_DATE_RE = re.compile(r"(19|20)\d{2}([-./년]\s?\d{1,2})?([-./월]\s?\d{1,2})?")


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    log: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)   # 실제로 응답한 모델(서버 대체 포함)
    per_call: list[dict] = field(default_factory=list)  # 호출별 {kind, model, in, out}


USAGE = Usage()


def mask_values(text: str) -> tuple[str, int]:
    """날짜·연도가 아닌 세 자리 이상 숫자(실제 값일 수 있음)를 가린다."""
    dates = [m.span() for m in _DATE_RE.finditer(text)]

    def in_date(span):
        return any(a <= span[0] and span[1] <= b for a, b in dates)

    out, n, last = [], 0, 0
    for m in _NUM_RE.finditer(text):
        if in_date(m.span()):
            continue
        out.append(text[last:m.start()])
        out.append("[숫자 가림]")
        last = m.end()
        n += 1
    out.append(text[last:])
    return "".join(out), n


def client():
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key or os.environ.get("IMPACT_LLM", "on").lower() == "off":
        return None
    try:
        import anthropic
        return anthropic.Anthropic(api_key=key, timeout=60.0, max_retries=2)
    except Exception:
        return None


def model_name() -> str:
    return os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _call(system: str, user: str, schema: dict | None = None, effort: str = "low", max_tokens: int = 4000,
          kind: str = "") -> str | None:
    c = client()
    if c is None:
        return None
    import anthropic
    body = {"output_config": {"effort": effort}}
    if schema is not None:
        body["output_config"]["format"] = {"type": "json_schema", "schema": schema}
    fallback_on = os.environ.get("IMPACT_LLM_FALLBACK", "on").lower() != "off"
    if fallback_on and model_name() in ("claude-opus-5-5", "claude-sonnet-5-5", "claude-opus-5", "claude-fable-5-2", "claude-fable-5-1"):
        body["fallbacks"] = "default"      # 서버 쪽 거절 대체(안전 분류기가 거절하면 다른 모델로 다시 실행)
        headers = {"anthropic-beta": "server-side-fallback-2026-07-01"}
    else:
        headers = None
    try:
        r = c.messages.create(model=model_name(), max_tokens=max_tokens, system=system,
                              messages=[{"role": "user", "content": user}],
                              extra_body=body, extra_headers=headers)
    except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.APIStatusError) as e:
        USAGE.log.append(f"LLM 호출 실패 → 규칙 기반으로 대신함: {type(e).__name__}")
        return None
    USAGE.calls += 1
    USAGE.models.append(getattr(r, "model", model_name()))
    USAGE.per_call.append({"kind": kind, "model": getattr(r, "model", model_name()),
                           "in": getattr(r.usage, "input_tokens", 0) or 0, "out": getattr(r.usage, "output_tokens", 0) or 0})
    USAGE.input_tokens += getattr(r.usage, "input_tokens", 0) or 0
    USAGE.output_tokens += getattr(r.usage, "output_tokens", 0) or 0
    if r.stop_reason == "refusal":
        USAGE.log.append("LLM 거절 → 규칙 기반으로 대신함")
        return None
    return next((b.text for b in r.content if b.type == "text"), None)


SPEC_SCHEMA = {
    "type": "object",
    "properties": {
        "event_name": {"type": "string"},
        "start": {"type": "string", "description": "YYYY-MM-DD 또는 빈 문자열"},
        "end": {"type": "string", "description": "YYYY-MM-DD 또는 빈 문자열"},
        "place_keywords": {"type": "array", "items": {"type": "string"}},
        "analysis": {"type": "string", "enum": ["정류소", "이용자 유형", "읍면동"]},
        "treated_user_type": {"type": "string"},
        "control_user_type": {"type": "string"},
        "clarify": {"type": "string", "description": "빠진 정보가 있으면 이용자에게 되물을 한 문장, 없으면 빈 문자열"},
    },
    "required": ["event_name", "start", "end", "place_keywords", "analysis", "treated_user_type", "control_user_type", "clarify"],
    "additionalProperties": False,
}


def parse_question(question: str, events: list[dict], unit_kinds: list[str]) -> tuple[dict | None, str]:
    """자연어 질문 → 분석 명세. (명세, 안내문) — LLM이 없으면 (None, 이유)."""
    masked, n = mask_values(question)
    note = f"질문에 있던 숫자 {n}개는 실제 값일 수 있어 가린 뒤 보냈습니다." if n else ""
    ev_lines = "\n".join(f"- {e['name']} | {e['start']}~{e['end']} | {e.get('place', '')}" for e in events[:120])
    system = ("너는 제주 행사·정책 효과 분석의 접수 담당이다. 이용자 질문을 분석 명세 JSON으로 바꾼다. "
              "행사 목록에 있으면 그 날짜·장소를 쓰고, 날짜·장소를 알 수 없으면 비워 두고 clarify에 되물을 한 문장을 쓴다. "
              "place_keywords는 버스 정류소 이름에 들어갈 만한 짧은 지명(예: 탑동, 탐라문화광장)이다. "
              "정책이 특정 이용자층(예: 청소년)을 대상으로 하면 analysis='이용자 유형'으로 하고 처리·대조 유형을 쓴다.")
    user = f"[분석 가능한 단위] {', '.join(unit_kinds)}\n[행사 목록(공개 자료)]\n{ev_lines}\n\n[질문]\n{masked}"
    txt = _call(system, user, SPEC_SCHEMA, effort="low", max_tokens=2000, kind="해석")
    if txt is None:
        return None, "Claude API를 쓸 수 없어 입력 양식으로 진행합니다." + (" " + note if note else "")
    try:
        spec = json.loads(txt)
    except json.JSONDecodeError:
        return None, "질문 해석에 실패해 입력 양식으로 진행합니다."
    return spec, note


def _numbers(s: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", s))


def write_narrative(facts: dict, fallback: str) -> tuple[str, str]:
    """점검을 통과한 응용집계(facts)만 보내 보고서 문단을 받는다. 숫자는 자리표시자로 쓰게 한 뒤 로컬이 채우고,
    자리표시자 밖 숫자가 있으면 고정 문장(fallback)을 쓴다. (본문, 출처표시)"""
    keys = ", ".join("{" + k + "}" for k in facts)
    system = ("너는 지자체 행사·정책 효과 보고서의 작성 담당이다. 주어진 값만 근거로 한국어 보고서 문단 3~5문장을 쓴다. "
              "숫자는 절대 직접 쓰지 말고 반드시 제공된 자리표시자(예: {effect})로만 쓴다. 자리표시자 값에는 단위(%)가 이미 들어 있다. "
              "자리표시자 바로 뒤에 '은(는)'처럼 조사를 병기하지 말고, 조사가 필요 없게 문장을 짠다. "
              "'대조군으로 만든 반사실과 비교한 순변화'라는 뜻을 살리고, 초록이어도 '효과가 확정됐다'고 단정하지 말고 "
              "'우연 범위를 벗어난 순증으로 볼 근거가 있다' 수준으로 쓴다. 노랑은 '판단 유보 요소가 있다', 빨강은 '우연과 구별되지 않는다'고 쓴다. "
              "'방문객 수'라고 쓰지 말고 데이터가 재는 것(예: 버스 이용)으로 쓴다. 한계 1문장을 포함한다.")
    # 행사 이름·측정 이름·신호등 색만 그대로, 나머지 값(효과·구간·p값 등)은 '숫자값'으로 가려 보낸다
    shown = {k: (v if k in ("event", "measure", "light") else "숫자값") for k, v in facts.items()}
    user = f"[사용할 자리표시자] {keys}\n[값의 뜻(숫자는 가림)]\n{json.dumps(shown, ensure_ascii=False)}"
    txt = _call(system, user, None, effort="medium", max_tokens=3000, kind="작성")
    if not txt:
        return fallback, "고정 문장"
    def fmt(k, v):
        if isinstance(v, float):
            return f"{v:.3f}" if k.startswith("p") else f"{v:,.1f}"
        return v
    try:
        filled = txt.format(**{k: fmt(k, v) for k, v in facts.items()})
    except (KeyError, IndexError, ValueError):
        return fallback, "고정 문장(자리표시자 오류)"
    allowed = set().union(*[_numbers(str(fmt(k, v))) for k, v in facts.items()]) | {"95"}
    stray = _numbers(txt.replace("{", " {")) - allowed
    stray = {x for x in stray if not re.search(r"\{[^}]*" + re.escape(x), txt)}
    if stray:
        return fallback, "고정 문장(LLM이 확인되지 않은 숫자를 씀)"
    return filled, f"Claude({USAGE.models[-1] if USAGE.models else model_name()})"
