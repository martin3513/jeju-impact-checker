@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo [1/3] Python 확인
py -3.13 --version || (echo Python 3.13 이 필요합니다. 매뉴얼 1장을 보세요. & pause & exit /b 1)
echo [2/3] 가상환경 만들기(.venv)
py -3.13 -m venv .venv || (echo 가상환경 생성 실패 & pause & exit /b 1)
echo [3/3] 패키지 설치(인터넷 필요, 3~5분)
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements-lock.txt || (echo 패키지 설치 실패 & pause & exit /b 1)
if not exist .env copy .env.example .env > nul
echo 설치 완료. run.bat 을 두 번 눌러 실행하세요.
pause
