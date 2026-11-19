@echo off
chcp 65001 > nul
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (echo 먼저 install.bat 을 실행하세요. & pause & exit /b 1)
echo 제주 임팩트 체커를 시작합니다. 잠시 뒤 브라우저가 열립니다(닫으려면 이 창에서 Ctrl+C).
start "" http://127.0.0.1:8501
.venv\Scripts\python -m streamlit run app.py
