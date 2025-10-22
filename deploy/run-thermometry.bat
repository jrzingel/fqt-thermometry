@echo off

:: Activate environment
cd C:\Users\User\thermometry
call .venv\Scripts\activate.bat

:: Run
uv run all | C:\Users\User\thermometry\rotatelogs.exe -l -T "C:\Users\User\thermometry\logs\alerts.%%A.log" 86400

pause
