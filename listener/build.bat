@echo off
rmdir /s /q build
rmdir /s /q dist
del listener.spec

set PATH=%PATH%;C:\Users\z5653624\AppData\Local\anaconda3\Scripts

call activate thermometry

pyinstaller.exe listener.py

call conda deactivate