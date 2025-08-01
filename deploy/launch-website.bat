@echo off

:: Activate environment
cd C:\Users\z5653624\thermometry
call venv\Scripts\activate.bat
cd C:\Users\z5653624\thermometry\fqt-thermometry

python -u -m waitress --listen="*:80" --call "flaskr:create_app" 2>&1 | C:\Users\z5653624\thermometry\rotatelogs.exe -l -T "C:\Users\z5653624\thermometry\logs\website.%%A.log" 86400

pause