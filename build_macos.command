#!/bin/bash
cd "$(dirname "$0")"
python3 -m pip install -r requirements.txt
python3 -m PyInstaller --noconfirm --clean "MailCleaner_Zacoka.spec"
echo
echo "Application créée dans dist/MailCleaner Zacoka.app"
read -n 1 -s -r -p "Appuyez sur une touche pour fermer..."
