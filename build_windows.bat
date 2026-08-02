@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -m pip install -r requirements.txt
py -m PyInstaller --noconfirm --clean "MailCleaner_Zacoka.spec"
echo.
echo Application créée dans dist\MailCleaner_Zacoka\MailCleaner_Zacoka.exe
pause
