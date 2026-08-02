
# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys

from PyInstaller.building.build_main import Analysis, COLLECT, EXE, PYZ
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve()

datas, binaries, hiddenimports = [], [], []
for package in ("msal", "googleapiclient", "google_auth_oauthlib", "keyring", "PySide6"):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h

datas += [(str(ROOT / "README.md"), ".")]

a = Analysis(
    ["main.py"],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MailCleaner_Zacoka",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="MailCleaner_Zacoka",
)

if sys.platform == "darwin":
    from PyInstaller.building.api import BUNDLE

    app = BUNDLE(
        coll,
        name="MailCleaner Zacoka.app",
        icon=None,
        bundle_identifier="com.zacoka.mailcleaner",
    )
