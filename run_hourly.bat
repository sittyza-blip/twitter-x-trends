@echo off
REM ไฟล์นี้ให้ Windows Task Scheduler เรียก เพื่อรันแจ้งเตือน 1 รอบ
REM ตั้ง trigger เป็น Daily -> Repeat every 1 hour ก็จะแจ้งทุกชั่วโมง
cd /d "%~dp0"
".venv\Scripts\python.exe" main.py
