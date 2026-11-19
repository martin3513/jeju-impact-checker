"""분석 스크립트 공통: 제출 코드(impact_engine)를 그대로 불러 허브 파일을 읽는다.
- doc-work(기획서 작업 폴더)에서는 docagent 의 record/save_figure 로 기록한다.
- 제출 ZIP(jeju_impact_checker/analysis)에서는 analysis/out/results.json 과 PNG 로 기록한다.
"""
import json
import os
import sys
from pathlib import Path

_here = Path(__file__).resolve()
ENGINE = None
for _p in _here.parents:
    if (_p / "impact_engine").is_dir():
        ENGINE = _p
        break
    if (_p / "jeju_impact_checker" / "impact_engine").is_dir():
        ENGINE = _p / "jeju_impact_checker"
        break
sys.path.insert(0, str(ENGINE))

from impact_engine.loaders import detect_dataset, load_hub_cached  # noqa: E402

if os.environ.get("DOCAGENT_RUN_OUT"):
    from docagent.analysis_api import record, save_figure  # noqa: F401
    HUB, CACHE = Path("input/hub"), Path("analysis/cache")
else:
    OUT = ENGINE / "analysis" / "out"
    OUT.mkdir(parents=True, exist_ok=True)
    HUB, CACHE = ENGINE / "data" / "hub", ENGINE / "data" / "cache"
    os.chdir(ENGINE)

    def record(key, value, *, display=None, kind="result", source=None):
        f = OUT / "results.json"
        d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        d[key] = {"value": value, "display": display, "source": source}
        f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{key} = {display or value}")

    def save_figure(fig_id, fig, caption, *, required=True):
        path = OUT / f"{fig_id}.png"
        fig.savefig(path, dpi=200, bbox_inches="tight")
        print(f"그림 {path.name}: {caption}")
        return str(path)


def hub_file(kind: str) -> Path:
    for f in sorted(HUB.glob("*.csv")):
        if detect_dataset(f).dataset == kind:
            return f
    raise FileNotFoundError(f"{HUB} 에 {kind} 파일이 없습니다")


def panel(kind: str, **kw):
    return load_hub_cached(hub_file(kind), kind, CACHE, **kw)
