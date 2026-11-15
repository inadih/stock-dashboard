@echo off
cd /d "%~dp0"
".venv\Scripts\streamlit.exe" run app.py --browser.gatherUsageStats false
