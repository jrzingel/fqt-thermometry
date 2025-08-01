@echo off

:: Activate environment
cd C:\Users\z5653624\thermometry
call venv\Scripts\activate.bat

:: Run
cd C:\Users\z5653624\thermometry\fqt-thermometry\alarm
python -u Watchtower.py | C:\Users\z5653624\thermometry\rotatelogs.exe -l -T "C:\Users\z5653624\thermometry\logs\alerts.%%A.log" 86400

pause