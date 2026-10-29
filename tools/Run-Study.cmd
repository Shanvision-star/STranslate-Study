@echo off
chcp 65001 >nul
"%~dp0python\python.exe" -X utf8 "%~dp0StudyTools\study_bridge.py" run-due --send --app-dir "%~dp0."
pause

