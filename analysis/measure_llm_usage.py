"""Claude 호출 토큰 실측(모델별 3회): 질문 해석 1회 + 문장 작성 1회를 반복해 호출별 평균 토큰을 남긴다.
실행: .venv\Scripts\python analysis\measure_llm_usage.py  (.env 의 ANTHROPIC_API_KEY 필요, 비용 발생)"""
import json, os, statistics, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())
from impact_engine import llm, config as C
QUESTION = "작년 탐라문화제 기간에 탑동 일대 버스 이용이 1,234명쯤 늘었다던데 진짜 효과가 있었나요?"
FACTS = {"event": "제64회 탐라문화제", "measure": "버스 이용 인원", "effect": "+16.8%", "ci": "+13.3%~+21.4%",
         "p_time": "0.004", "light": "초록"}
REPEAT = 3
out = {"measured_at": time.strftime("%Y-%m-%d"), "question": QUESTION, "repeat": REPEAT,
       "method": "llm.parse_question(질문, 내장 행사 목록, 단위 종류) 1회 + llm.write_narrative(값 이름·신호등) 1회를 모델별 3번 반복, "
                 "응답 usage.input_tokens/output_tokens(출력에는 adaptive thinking 사고 토큰 포함)",
       "per_call": {}, "raw": {}}
for m in ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"]:
    os.environ["ANTHROPIC_MODEL"] = m
    llm.USAGE.per_call.clear()
    for _ in range(REPEAT):
        llm.parse_question(QUESTION, C.EVENTS, ["정류소", "이용자 유형", "읍면동"])
        llm.write_narrative(FACTS, "고정 문장")
    calls = list(llm.USAGE.per_call)
    out["raw"][m] = calls
    avg = []
    for kind in ("해석", "작성"):
        cs = [c for c in calls if c["kind"] == kind]
        avg.append({"kind": kind, "model": m, "in": round(statistics.mean(c["in"] for c in cs)),
                    "out": round(statistics.mean(c["out"] for c in cs)),
                    "out_min": min(c["out"] for c in cs), "out_max": max(c["out"] for c in cs), "n": len(cs)})
    out["per_call"][m] = avg
    print(m, avg)
dest = ROOT / "analysis" / "llm_usage_20261119.json"
dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("저장:", dest.name)
