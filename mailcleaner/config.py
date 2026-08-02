from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir

from .models import AppState, OvhAccount

APP_NAME = "MailCleaner Zacoka"
APP_AUTHOR = "Zacoka"
APP_ID = "com.zacoka.mailcleaner"

DATA_DIR = Path(user_data_dir(APP_NAME, APP_AUTHOR))
CONFIG_DIR = Path(user_config_dir(APP_NAME, APP_AUTHOR))
STATE_FILE = CONFIG_DIR / "state.json"
GOOGLE_TOKEN_FILE = DATA_DIR / "google_token.json"
MICROSOFT_TOKEN_FILE = DATA_DIR / "microsoft_cache.bin"
OVH_KEYRING_SERVICE = "MailCleaner Zacoka OVH"


def ensure_directories() -> None:
    for folder in (DATA_DIR, CONFIG_DIR):
        folder.mkdir(parents=True, exist_ok=True)


def default_state() -> AppState:
    ensure_directories()
    return AppState(
        google_token_path=str(GOOGLE_TOKEN_FILE),
        microsoft_token_path=str(MICROSOFT_TOKEN_FILE),
    )


def _state_to_dict(state: AppState) -> dict:
    payload = asdict(state)
    payload["ovh_accounts"] = [asdict(account) for account in state.ovh_accounts]
    return payload


def save_state(state: AppState) -> None:
    ensure_directories()
    STATE_FILE.write_text(json.dumps(_state_to_dict(state), ensure_ascii=False, indent=2), encoding="utf-8")


def load_state() -> AppState:
    if not STATE_FILE.exists():
        return default_state()
    payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    ovh_accounts = [OvhAccount(**account) for account in payload.get("ovh_accounts", [])]
    return AppState(
        google_credentials_path=payload.get("google_credentials_path", ""),
        google_token_path=payload.get("google_token_path") or str(GOOGLE_TOKEN_FILE),
        microsoft_client_id=payload.get("microsoft_client_id", ""),
        microsoft_tenant=payload.get("microsoft_tenant", "common"),
        microsoft_token_path=payload.get("microsoft_token_path") or str(MICROSOFT_TOKEN_FILE),
        ovh_accounts=ovh_accounts,
        message_limit=int(payload.get("message_limit", 100)),
        unread_only=bool(payload.get("unread_only", False)),
    )

