@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -m pip install -r requirements.txt
py -m PyInstaller --noconfirm --clean --windowed --onefile ^
  --name "MailCleaner_Zacoka" ^
  --collect-all msal ^
  --collect-all googleapiclient ^
  main.py
echo.
echo Application créée dans dist\MailCleaner_Zacoka.exe
pause
