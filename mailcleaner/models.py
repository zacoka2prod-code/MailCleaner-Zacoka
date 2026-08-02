from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class OvhAccount:
    email: str
    server: str
    port: int = 993
    label: str = ""


@dataclass(slots=True)
class AppState:
    google_credentials_path: str = ""
    google_token_path: str = ""
    microsoft_client_id: str = ""
    microsoft_tenant: str = "common"
    microsoft_token_path: str = ""
    ovh_accounts: list[OvhAccount] = field(default_factory=list)
    message_limit: int = 100
    unread_only: bool = False


@dataclass(slots=True)
class MailMessage:
    provider: str
    account: str
    message_id: str
    subject: str
    sender: str
    received_at: str
    size_bytes: int
    unread: bool
    has_attachments: bool
    preview: str
    folder: str = "INBOX"
    recipient: str = ""

