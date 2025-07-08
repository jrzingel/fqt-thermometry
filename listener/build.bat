@echo off
rmdir /s /q build
rmdir /s /q dist
del listener.spec

set PATH=%PATH%;C:\Users\z5653624\AppData\Local\anaconda3\Scripts

call activate thermometry-3-8

pyinstaller.exe -c -F -i app_icon.ico listener.py

move /Y ".\dist\*.exe" ".\"
rmdir /s /q build
rmdir /s /q dist
del listener.spec

call conda deactivate