@echo off
rmdir /s /q build
rmdir /s /q dist
del watchdog.spec

set PATH=%PATH%;C:\Users\z5653624\AppData\Local\anaconda3\Scripts

call activate thermometry-3-8

pyinstaller.exe -c -F -i watchdog.ico watchdog.py

copy /Y ".\dist\*.exe" ".\"
rmdir /s /q build
rmdir /s /q dist
del watchdog.spec

call conda deactivate