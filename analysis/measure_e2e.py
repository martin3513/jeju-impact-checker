"""Claude 켬 상태의 1회 분석 소요 시간 실측(가상 데이터 사례 A): 질문 해석 + 계산(대조군·추정·위약) + 문장 작성.
사람이 입력·확인하는 시간은 빼고 잰다. 실행: .venv\Scripts\python analysis\measure_e2e.py (.env 키 필요, 비용 발생)"""
import json, os, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())
from impact_engine import llm, config as C
from impact_engine.loaders import load_center_files
from impact_engine.effect import Spec
from impact_engine.pipeline import run, match_units
runs = []
for i in range(3):
    t0 = time.perf_counter()
    spec_j, _ = llm.parse_question("2025년 탐라문화제 기간에 탑동 일대 버스 이용이 정말 늘었나요?", C.EVENTS, ["정류소", "이용자 유형", "읍면동"])
    t1 = time.perf_counter()
    p = load_center_files(sorted((ROOT / "data" / "sample_center" / "3-04").glob("*.csv")))
    t2 = time.perf_counter()
    kw = ["탑동", "탐라문화광장", "산지천", "동문"]
    a = run(p, Spec("2025-10-10", "2025-10-14", [u for u, _ in match_units(sorted(p.df.unit.unique()), kw)]),
            "가상 행사(탑동 일대)", ROOT / "work" / "e2e", title="가상 행사(탑동 일대)", place_keywords=kw, use_llm=True, annual=True, make_docx=True)
    t3 = time.perf_counter()
    runs.append({"해석_초": round(t1 - t0, 1), "자료불러오기_초": round(t2 - t1, 1), "분석·문장·보고서_초": round(t3 - t2, 1),
                 "합계_초": round(t3 - t0, 1), "문장": a.narrative_src, "모델": llm.model_name()})
    print(runs[-1])
out = {"measured_at": time.strftime("%Y-%m-%d"), "조건": "가상 센터 데이터(정류소 40곳), 사례 A 설정, Claude 켬, 사람 입력 시간 제외", "runs": runs}
(ROOT / "analysis" / "e2e_timing_20261119.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
