# 제주 임팩트 체커 (Jeju Impact Checker)

축제·행사·정책의 날짜와 장소(또는 대상)를 넣으면, 비슷한 흐름의 **대조 정류소·대조 이용자 유형**과 비교해
'그날 그곳에서만 늘어난 몫(순효과)'을 계산하고, **우연인지 검사(위약검정)** 해 신뢰도 신호등과 반출 가능한 결과보고서를 만드는 AI Agent입니다.

> 결과는 방문객 수를 대신하지 않습니다. 데이터가 재는 것(버스 이용 등)의 순증분으로 주최 측 추산·정책 성과를 교차 점검합니다.

「제주 AI·빅데이터 활용 AI Agent 개발 챌린지」(제주테크노파크) 제출작.

---

## 1. 실행 환경

| 항목 | 내용 |
|---|---|
| 운영체제 | Windows 11 (센터 PC: i7-8700 / GTX 1060 / RAM 32GB). GPU는 쓰지 않습니다. |
| Python | 3.13 (python.org 공식 설치본. 설치 화면 아래 **"Add python.exe to PATH"** 체크. `install.bat`은 함께 설치되는 `py` 런처를 씁니다) |
| 브라우저 | Chrome 또는 Edge (화면 1920×1080 기준) |
| 실행 방식 | 이 PC 안에서 로컬 웹 서버(127.0.0.1:8501)를 띄우고 브라우저로 접속. 외부에서 접속할 수 없습니다. |
| 디스크 | 설치 약 0.5GB(.venv) + 허브 버스 파일 약 1.1GB(선택) + 캐시 수십 MB |

### 외부 접속 주소 (센터 허용 목록 등록용)
| 주소 | 용도 | 없으면 |
|---|---|---|
| `pypi.org`, `files.pythonhosted.org` | 설치 때 패키지 내려받기(1회) | 설치 불가 |
| `api.anthropic.com` | Claude API(질문 해석·문장 작성, 선택) | 규칙 기반(입력 양식·고정 문장)으로 자동 전환 |
| `jejudatahub.net` | 허브 공개 파일 내려받기(브라우저, 1회) | 센터 CSV·가상 데이터로만 분석 |

## 2. 설치 (비전공자용, 약 10분)

1. **Python 3.13 설치**: https://www.python.org/downloads/ 에서 Windows installer(64-bit)를 받아 실행 → 첫 화면 아래
   "Add python.exe to PATH" 체크 → **Install Now**.
2. 이 폴더(`jeju_impact_checker`)를 원하는 곳(예: `C:\jeju_impact_checker`)에 압축 해제합니다. 경로에 한글이 있어도 됩니다.
3. 폴더 안의 **`install.bat`** 을 두 번 누릅니다. 가상환경(.venv)을 만들고 `requirements-lock.txt`의 패키지를 설치합니다(인터넷 필요, 3~5분).
   - 끝나면 "설치 완료" 문구가 나오고 `.env` 파일이 생깁니다.
4. (선택) Claude API를 쓰려면 `.env` 를 메모장으로 열어 `ANTHROPIC_API_KEY=` 뒤에 키를 붙여 넣고 저장합니다(아래 4장).

수동 설치(명령 프롬프트):
```bat
cd C:\jeju_impact_checker
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-lock.txt
copy .env.example .env
```

### 의존성(직접 쓰는 패키지, 버전 고정)
| 패키지 | 버전 | 용도 | 라이선스 |
|---|---|---|---|
| streamlit | 1.67.0 | 화면(로컬 웹앱) | Apache-2.0 |
| pandas | 3.1.1 | 표 계산 | BSD-3-Clause |
| numpy | 2.5.5 | 수치 계산 | BSD-3-Clause |
| matplotlib | 3.11.2 | 그림(PNG) | PSF 기반(matplotlib License) |
| python-docx | 1.2.0 | 결과보고서 DOCX | MIT |
| anthropic | 2.9.0 | Claude API 공식 SDK | MIT |
| pyarrow | 26.0.1 | streamlit 표 표시 | Apache-2.0 |
전체 고정 목록(하위 의존성 포함): `requirements-lock.txt`.

### 서명 없는 Python 확장 모듈(.pyd): 센터 보안정책 허용 등록 목록
센터 PC는 디지털 서명이 없는 확장 모듈 실행을 막을 수 있습니다. 아래 패키지는 `.pyd` 확장 모듈을 포함하므로 `.venv\Lib\site-packages\` 아래 해당 폴더의 허용 등록이 필요합니다.
`pandas`, `numpy`, `pyarrow`, `matplotlib`, `PIL`(pillow), `lxml`, `fontTools`, `contourpy`, `kiwisolver`, `charset_normalizer`, `markupsafe`, `pydantic_core`, `jiter`, `rpds`, `websockets`, `google`(protobuf)
함께 딸린 DLL 폴더: `numpy.libs`, `pandas.libs`, `pyarrow.libs` (모두 `.venv\Lib\site-packages\` 아래)

## 3. 실행

- **`run.bat`** 을 두 번 누르면 서버가 켜지고 브라우저가 `http://127.0.0.1:8501` 로 열립니다. 끄려면 검은 창에서 `Ctrl + C`.
- 수동: `.venv\Scripts\python -m streamlit run app.py`

## 4. 환경변수(.env)

| 이름 | 기본 | 설명 |
|---|---|---|
| `ANTHROPIC_API_KEY` | (비움) | Claude API 키. 비우면 Claude 없이 규칙 기반으로 동작합니다. |
| `ANTHROPIC_MODEL` | `claude-opus-5-5` | 사용할 모델. 비용을 줄이려면 `claude-haiku-5-5` 또는 `claude-sonnet-5-5` 로 한 줄만 바꿉니다. |
| `IMPACT_LLM` | `on` | `off` 면 키가 있어도 Claude를 쓰지 않습니다. |
| `IMPACT_LLM_FALLBACK` | `on` | Opus·Sonnet 5.5에서 안전 분류기가 드물게 거절하면 Anthropic 서버가 다른 Claude 모델로 다시 실행. `off` 로 끔. |
| `IMPACT_KEEP_RESULTS` | `off` | `on` 이면 작업 폴더(`work/`)를 지우지 않습니다. |

세 모델(claude-haiku-5-5·claude-sonnet-5-5·claude-opus-5-5) 모두 실제 호출로 질문 해석·되묻기·문장 작성이 동작함을 확인했습니다(2026-11-18).
1회 분석 비용(모델별 3회 실측 평균 토큰 × 공식 요금): 질문 1회(해석+작성) 기준 Haiku 약 0.0013달러, Sonnet 약 0.012달러, Opus 약 0.039달러. 측정값은 `analysis/llm_usage_20261119.json`(측정 스크립트 `analysis/measure_llm_usage.py`, 비용 발생).

API 키 발급: https://platform.claude.com → 로그인 → API Keys → Create Key. 키는 `.env` 에만 두고 화면·보고서에 나오지 않습니다.
실제 센터 운영 시 키는 센터 담당자가 `.env` 에 넣고, 일반 이용자에게 보이지 않게 합니다.
※ 심사용 평가 키는 제출 ZIP의 `docs/평가용_API키.txt` 에 별도로 넣었습니다(사용 한도 설정, 평가 종료 후 폐기).

## 5. 사용자 매뉴얼 (화면 4단계)

### ① 묻기
- **행사·정책 목록에서 고르기**: 내장 목록(탐라문화제 2024·2025, 서귀포칠십리축제 2025, 들불축제 2025, 청소년 버스 무료화 등)에서 고르면 날짜·장소 검색어가 채워집니다.
- **질문으로 묻기**: "2025년 탐라문화제가 탑동 일대 버스 이용을 얼마나 늘렸나요?"처럼 씁니다. Claude가 분석 명세로 바꾸고, 빠진 값이 있으면 되묻습니다.
  - **질문에 센터 자료의 실제 집계 값을 쓰지 마세요.** 세 자리 이상 숫자는 자동으로 가린 뒤 보내지만, 두 자리 이하 숫자는 가리지 않습니다.
- 비교 단위(정류소 / 이용자 유형), 장소 검색어, 도로 통제 여부, 해마다 열리는 행사 여부를 확인합니다.

### ② 데이터 넣기
| 자료 | 넣는 방법 |
|---|---|
| 제주데이터허브 공개 파일 | jejudatahub.net 로그인 → 데이터 상세 → 프로젝트 담기 → 파일 내려받기. `data/hub/` 폴더에 CSV를 넣습니다. 743 「이용자 유형별 버스정류소 이용 인원 현황」(정류소 분석), 561 「일별 버스 승차 인원 수 현황」(이용자 유형 분석). 처음 한 번은 1~3분 걸리고 이후는 캐시로 몇 초. |
| 센터 CSV | 센터 화면에서 1개월씩 내려받은 같은 종류 파일(예: 3-04 정류소별 이용 현황)을 여러 개 함께 올립니다. 필요한 월 목록과 '운영자 사전 다운로드 요청문'이 화면에 나옵니다. |
| 가상 센터 데이터 | 시연용. 공개 명세서 구조로 만든 지어낸 값(탑동 일대 가상 정류소에 +15% 효과를 심음). |
- 파일 종류는 머리글로 자동 판별합니다(허브 3종, 센터 명세서 v13의 71종).
- **처리군 확인 표**: 장소 검색어와 이름이 맞는 정류소가 나옵니다. 빼거나 '도로 통제·임시 정류소'로 표시하세요. 표시한 정류소는 기본 결과에서 빠지고, 넣은 결과가 함께 계산됩니다.

### ③ 결과 보기
- 신뢰도 신호등(초록·노랑·빨강), 순효과(%)·95% 구간·우연일 확률(p)·순증 인원(원본 반출 가능 자료만), 그림 3개, 반대 설명 점검(겹치는 행사·날씨·공휴일·자료 공백·도로 통제·크기 이상·기록 방식 변화), 판단 기록.

| 신호등 | 판정 규칙(`impact_engine/config.py`) |
|---|---|
| 초록 | 시점 위약 p < 0.05, 지역 위약 p < 0.10(계산된 경우), 평행추세 통과, 민감도 부호 일치, '경고' 없음 |
| 노랑 | 효과 여지는 있으나 위 조건 일부 미충족(이유 표시) |
| 빨강 | 시점 위약 p ≥ 0.10, 우연과 구별되지 않음(판단 보류) |

### ④ 내보내기
- 결과보고서(DOCX), 그림(PNG), 반출 신청 사유문·점검 메모(TXT). 반출 신청은 센터 시스템에서 이용자가 직접 합니다.
- 사이드바 **"이번 작업 결과 모두 삭제"** 로 올린 파일·결과를 지웁니다. 결과 보관 OFF(기본)면 앱을 열 때 12시간 지난 작업 폴더를 자동 삭제합니다.

## 6. 보존·삭제 (센터 탑재 조건)
| 폴더 | 내용 | 보존 |
|---|---|---|
| `work/<시각>/` | 이용자가 올린 센터 CSV, 결과 그림·보고서 | 기본 삭제(보관 OFF: 12시간 후 자동, 버튼 즉시) |
| `data/cache/` | 허브 **공개** 파일의 '일×정류소' 합계 캐시 | 보존(속도용). 센터 데이터는 캐시하지 않음 |
| `data/hub/` | 허브 공개 원본 CSV | 운영자 판단 |

## 7. 보안 경계(LLM)
- Claude에 **보내는 것**: ① 질문 해석: 질문 문장(세 자리 이상 숫자 가림), 내장 행사 목록(공개 자료), 분석 단위 종류. ② 문장 작성: 값의 이름(자리표시자)·행사 이름(숫자 가림)·신호등 색. **숫자 값은 보내지 않고** 이 PC가 문장에 채웁니다.
- **보내지 않는 것**: CSV 행, 인원·건수·금액 원값, 정류소·읍면동별 원자료.
- Claude 문장은 숫자를 자리표시자로만 쓰게 하고, 이 PC가 계산값을 채운 뒤 확인되지 않은 숫자가 있으면 고정 문장으로 바꿉니다.

## 8. 재현(심사용)
```bat
.venv\Scripts\python -m pytest -q tests
```
- `tests/test_effect.py`: 크기를 아는 가짜 효과(20%)를 심어 되찾는지, 효과가 없을 때 거짓 양성이 없는지.
- `tests/test_app.py`: 가상 데이터로 화면 ①~③이 오류 없이 돌아가는지(Streamlit AppTest).
- `tests/test_guard.py`, `tests/test_llm_boundary.py`: 반출 판정·10 미만 블라인드·2차 가림, 숫자 가림, Claude에 숫자가 가지 않는지.
- `tests/test_hub_format.py`: 제주데이터허브 상세 화면에 공개된 표본 행(743·561·512 각 20행)으로 파일 판별·읽기(정류소 이름 공백 정리, 노선 번호, BOM 머리글). 전체 파일로는 시험하지 못했습니다.
- 모두 15개. 시험은 `tests/conftest.py`가 Claude를 꺼 두어 `.env`에 키가 있어도 API를 부르지 않습니다(실제 호출 확인은 `analysis/measure_llm_usage.py`, `analysis/measure_e2e.py`).
- 난수는 `config.SEED = 20261120` 으로 고정됩니다.

기획서 수치 재현(`analysis/`, 결과는 `analysis/out/`):
```bat
.venv\Scripts\python analysis\demo_synth.py        & rem 가상 데이터 시연 A·B·C (기획서 01·07장)
.venv\Scripts\python analysis\recovery_synth.py    & rem 가상 패널 되찾기 시험 400회 (07장)
.venv\Scripts\python analysis\recovery_test.py     & rem 허브 743 실제 정류소 되찾기 시험 (data/hub 필요)
.venv\Scripts\python analysis\case_tamna.py        & rem 탐라문화제 2024·2025 (data/hub 743 필요)
.venv\Scripts\python analysis\case_youth.py        & rem 청소년 버스 무료화 (data/hub 561·512 필요)
```

## 9. 오류·제약사항
| 증상 | 원인·대처 |
|---|---|
| "대조군 후보가 없습니다" | 행사 전 56일·행사 기간에 자료가 90% 이상 있고 하루 평균 20명 이상인 단위가 없음. 기간을 확인하거나 더 넓은 지역 자료를 넣으세요. |
| "처리군 단위가 자료에 없습니다" | 처리군 표의 이름이 자료에 없음. 장소 검색어를 바꾸세요. |
| Claude 문장 대신 고정 문장이 나옴 | 키 없음·네트워크 차단·거절. 계산과 신호등은 그대로입니다. |
| 허브 파일 불러오기가 느림 | 743은 약 624MB. 처음 한 번만 1~3분, 이후 캐시 사용. |
| 결과가 매우 큼(±60% 이상) | 요금·집계 방식 변경, 임시 정류소·우회 운행 가능성 경고가 함께 뜹니다. |
- 결과는 버스 이용 등 **데이터가 재는 것의 변화**이며 방문객 수가 아닙니다.
- 대조군이 행사 영향을 받았거나(파급) 같은 기간 처리군에만 작용한 다른 요인이 있으면 효과가 틀릴 수 있습니다(반대 설명 점검으로 확인).
- 허브 버스 파일은 2025-10 하순까지 수록되어 그 뒤 행사는 센터 자료로 분석해야 합니다.

## 10. 사용 AI·외부 자료·오픈소스
- AI 모델: Anthropic Claude(`claude-opus-5-5` 기본, 설정으로 변경). 역할: 질문 해석·되묻기·보고서 문장 작성. 계산·판정에는 쓰지 않습니다.
- 개발 도구: Claude Code(코드 작성 보조).
- 데이터: 제주데이터허브 공개 데이터(743·561·512, 제공처 제주빅데이터센터), 제주빅데이터센터 데이터 명세서 v13(공개, 컬럼 사전 `impact_engine/center_schema.json`). 데이터 활용 명세: `docs/데이터_활용_명세.md`.
- 오픈소스: 2장 표. 각 라이선스를 따릅니다.
#   j e j u - i m p a c t - c h e c k e r -  
 