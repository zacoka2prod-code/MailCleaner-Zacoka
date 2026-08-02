from __future__ import annotations

import email
import imaplib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.header import decode_header
from email.message import Message
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable

import keyring
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from msal import PublicClientApplication, SerializableTokenCache

from .config import MICROSOFT_TOKEN_FILE, OVH_KEYRING_SERVICE
from .models import AppState, MailMessage, OvhAccount

GOOGLE_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
MICROSOFT_SCOPES = ["Mail.ReadWrite", "offline_access", "User.Read"]


def _decode_mime(value: str | None) -> str:
    if not value:
        return ""
    parts = []
    for chunk, encoding in decode_header(value):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(encoding or "utf-8", errors="replace"))
        else:
            parts.append(chunk)
    return "".join(parts).strip()


def _normalize_preview(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact[:220]


def _message_date(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone().isoformat(timespec="minutes")
    except Exception:
        return value


def _guess_has_attachments(message: Message) -> bool:
    if message.get_content_disposition() == "attachment":
        return True
    for part in message.walk():
        if part.get_content_disposition() == "attachment":
            return True
    return False


def _body_preview(message: Message) -> str:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain" and part.get_content_disposition() != "attachment":
                payload = part.get_payload(decode=True)
                if payload:
                    return _normalize_preview(payload.decode(part.get_content_charset() or "utf-8", errors="replace"))
    payload = message.get_payload(decode=True)
    if payload:
        return _normalize_preview(payload.decode(message.get_content_charset() or "utf-8", errors="replace"))
    return ""


def _message_size(message: Message, fallback: int = 0) -> int:
    try:
        return len(message.as_bytes())
    except Exception:
        return fallback


class GmailProvider:
    provider_name = "Google"

    def __init__(self, credentials_path: str, token_path: str) -> None:
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        self._creds: Credentials | None = None

    def authenticate(self) -> str:
        if not self.credentials_path.exists():
            raise FileNotFoundError("Le fichier credentials.json Google est introuvable.")
        if self.token_path.exists():
            self._creds = Credentials.from_authorized_user_file(str(self.token_path), GOOGLE_SCOPES)
        if not self._creds or not self._creds.valid:
            if self._creds and self._creds.expired and self._creds.refresh_token:
                self._creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_path), GOOGLE_SCOPES)
                self._creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(self._creds.to_json(), encoding="utf-8")
        return "Google connecté"

    def _service(self):
        if not self._creds:
            self.authenticate()
        assert self._creds is not None
        return build("gmail", "v1", credentials=self._creds, cache_discovery=False)

    def list_messages(self, limit: int, unread_only: bool = False, query: str = "") -> list[MailMessage]:
        service = self._service()
        search = query.strip()
        if unread_only:
            search = f"{search} is:unread".strip()
        params = {"userId": "me", "maxResults": limit}
        if search:
            params["q"] = search
        response = service.users().messages().list(**params).execute()
        messages: list[MailMessage] = []
        for entry in response.get("messages", []):
            message = service.users().messages().get(
                userId="me",
                id=entry["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date", "To"],
            ).execute()
            headers = {item["name"].lower(): item["value"] for item in message.get("payload", {}).get("headers", [])}
            label_ids = set(message.get("labelIds", []))
            messages.append(
                MailMessage(
                    provider=self.provider_name,
                    account="me@gmail.com",
                    message_id=message["id"],
                    subject=headers.get("subject") or "(Sans sujet)",
                    sender=headers.get("from") or "",
                    recipient=headers.get("to") or "",
                    received_at=_message_date(headers.get("date")),
                    size_bytes=int(message.get("sizeEstimate") or 0),
                    unread="UNREAD" in label_ids,
                    has_attachments=bool(message.get("payload", {}).get("parts")),
                    preview=_normalize_preview(message.get("snippet", "")),
                    folder="INBOX",
                )
            )
        return messages

    def archive(self, message_ids: Iterable[str]) -> None:
        service = self._service()
        for message_id in message_ids:
            service.users().messages().modify(userId="me", id=message_id, body={"removeLabelIds": ["INBOX"]}).execute()

    def delete(self, message_ids: Iterable[str]) -> None:
        service = self._service()
        for message_id in message_ids:
            service.users().messages().trash(userId="me", id=message_id).execute()


class MicrosoftProvider:
    provider_name = "Microsoft"

    def __init__(self, client_id: str, tenant: str, token_path: str) -> None:
        self.client_id = client_id.strip()
        self.tenant = tenant.strip() or "common"
        self.token_path = Path(token_path)
        self._cache = SerializableTokenCache()
        self._app: PublicClientApplication | None = None
        if self.token_path.exists():
            self._cache.deserialize(self.token_path.read_text(encoding="utf-8"))

    def _application(self) -> PublicClientApplication:
        if self._app is None:
            self._app = PublicClientApplication(
                client_id=self.client_id,
                authority=f"https://login.microsoftonline.com/{self.tenant}",
                token_cache=self._cache,
            )
        return self._app

    def _save_cache(self) -> None:
        if self._cache.has_state_changed:
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(self._cache.serialize(), encoding="utf-8")

    def authenticate(self) -> str:
        if not self.client_id:
            raise ValueError("L'ID client Microsoft est requis.")
        app = self._application()
        accounts = app.get_accounts()
        result = app.acquire_token_silent(MICROSOFT_SCOPES, account=accounts[0] if accounts else None)
        if not result:
            result = app.acquire_token_interactive(MICROSOFT_SCOPES, prompt="select_account")
        if "access_token" not in result:
            raise RuntimeError(result.get("error_description") or "Échec de l'authentification Microsoft.")
        self._save_cache()
        return "Microsoft connecté"

    def _headers(self) -> dict[str, str]:
        app = self._application()
        accounts = app.get_accounts()
        result = app.acquire_token_silent(MICROSOFT_SCOPES, account=accounts[0] if accounts else None)
        if not result:
            result = app.acquire_token_interactive(MICROSOFT_SCOPES, prompt="select_account")
        if "access_token" not in result:
            raise RuntimeError(result.get("error_description") or "Impossible d'obtenir un jeton Microsoft.")
        self._save_cache()
        return {"Authorization": f"Bearer {result['access_token']}"}

    def _folder_id(self, names: Iterable[str], headers: dict[str, str]) -> str | None:
        response = requests.get("https://graph.microsoft.com/v1.0/me/mailFolders", headers=headers, timeout=30)
        response.raise_for_status()
        for folder in response.json().get("value", []):
            display_name = str(folder.get("displayName", "")).lower()
            if any(display_name == candidate.lower() for candidate in names):
                return folder.get("id")
        return None

    def list_messages(self, limit: int, unread_only: bool = False, query: str = "") -> list[MailMessage]:
        headers = self._headers()
        url = (
            "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages"
            "?$top={limit}&$orderby=receivedDateTime desc"
            "&$select=id,subject,from,receivedDateTime,isRead,hasAttachments,size,bodyPreview,toRecipients"
        ).format(limit=limit)
        if unread_only:
            url += "&$filter=isRead eq false"
        response = requests.get(url, headers=headers, timeout=45)
        response.raise_for_status()
        messages: list[MailMessage] = []
        query_lower = query.lower().strip()
        for item in response.json().get("value", []):
            sender = item.get("from", {}).get("emailAddress", {})
            recipient_values = [entry.get("emailAddress", {}).get("address", "") for entry in item.get("toRecipients", [])]
            preview = item.get("bodyPreview", "") or ""
            subject = item.get("subject") or "(Sans sujet)"
            sender_line = " ".join(filter(None, [sender.get("name"), sender.get("address")]))
            combined = " ".join([subject, sender_line, preview]).lower()
            if query_lower and query_lower not in combined:
                continue
            messages.append(
                MailMessage(
                    provider=self.provider_name,
                    account="Outlook",
                    message_id=item["id"],
                    subject=subject,
                    sender=sender_line,
                    recipient=", ".join([value for value in recipient_values if value]),
                    received_at=str(item.get("receivedDateTime", ""))[:19].replace("T", " "),
                    size_bytes=int(item.get("size") or 0),
                    unread=not bool(item.get("isRead", False)),
                    has_attachments=bool(item.get("hasAttachments")),
                    preview=_normalize_preview(preview),
                    folder="Inbox",
                )
            )
        return messages

    def _move(self, message_ids: Iterable[str], target_names: Iterable[str]) -> None:
        headers = self._headers()
        folder_id = self._folder_id(target_names, headers)
        if not folder_id:
            raise RuntimeError(f"Dossier Microsoft introuvable: {', '.join(target_names)}")
        for message_id in message_ids:
            response = requests.post(
                f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/move",
                headers={**headers, "Content-Type": "application/json"},
                json={"destinationId": folder_id},
                timeout=30,
            )
            response.raise_for_status()

    def archive(self, message_ids: Iterable[str]) -> None:
        self._move(message_ids, ["Archive", "Archives", "Archived"])

    def delete(self, message_ids: Iterable[str]) -> None:
        self._move(message_ids, ["Deleted Items", "Trash", "Corbeille", "DeletedItems"])


@dataclass(slots=True)
class OvhSession:
    account: OvhAccount
    password: str


class OvhProvider:
    provider_name = "OVH"

    def __init__(self, account: OvhAccount) -> None:
        self.account = account
        self.password = keyring.get_password(OVH_KEYRING_SERVICE, account.email)
        if not self.password:
            raise RuntimeError(f"Aucun mot de passe OVH enregistré pour {account.email}.")

    @property
    def _folder_candidates(self) -> list[str]:
        return ["Archive", "Archives", "INBOX.Archive", "Sent", "Trash", "Corbeille", "Deleted Items"]

    def authenticate(self) -> str:
        self._connect().logout()
        return f"OVH connecté: {self.account.email}"

    def _connect(self) -> imaplib.IMAP4_SSL:
        connection = imaplib.IMAP4_SSL(self.account.server, self.account.port)
        status, _ = connection.login(self.account.email, self.password)
        if status != "OK":
            raise RuntimeError("Impossible de se connecter à la boîte OVH.")
        return connection

    def _find_folder(self, connection: imaplib.IMAP4_SSL, wanted: Iterable[str] | str) -> str | None:
        candidates = [wanted] if isinstance(wanted, str) else list(wanted)
        status, folders = connection.list()
        if status != "OK":
            return None
        for raw in folders:
            text = raw.decode("utf-8", errors="replace")
            if any(candidate.lower() in text.lower() for candidate in candidates):
                match = re.search(r'".*?"\s+"?([^"]+)"?$', text)
                if match:
                    return match.group(1)
        return None

    def _message_matches(self, message: MailMessage, query: str, unread_only: bool) -> bool:
        if unread_only and not message.unread:
            return False
        if not query:
            return True
        haystack = " ".join([message.subject, message.sender, message.preview]).lower()
        return query.lower() in haystack

    def list_messages(self, limit: int, unread_only: bool = False, query: str = "") -> list[MailMessage]:
        connection = self._connect()
        try:
            connection.select("INBOX", readonly=True)
            status, data = connection.uid("search", None, "ALL")
            if status != "OK" or not data or not data[0]:
                return []
            uids = data[0].split()[-limit:][::-1]
            messages: list[MailMessage] = []
            for uid in uids:
                status, fetched = connection.uid("fetch", uid, "(RFC822 FLAGS)")
                if status != "OK" or not fetched or not fetched[0]:
                    continue
                raw_bytes = fetched[0][1]
                parsed = email.message_from_bytes(raw_bytes)
                flags = str(fetched[0][0])
                unread = "\\Seen" not in flags
                message = MailMessage(
                    provider=self.provider_name,
                    account=self.account.email,
                    message_id=uid.decode("utf-8"),
                    subject=_decode_mime(parsed.get("Subject")) or "(Sans sujet)",
                    sender=_decode_mime(parsed.get("From")),
                    recipient=_decode_mime(parsed.get("To")),
                    received_at=_message_date(parsed.get("Date")),
                    size_bytes=_message_size(parsed, len(raw_bytes)),
                    unread=unread,
                    has_attachments=_guess_has_attachments(parsed),
                    preview=_body_preview(parsed),
                    folder="INBOX",
                )
                if self._message_matches(message, query, unread_only):
                    messages.append(message)
            return messages
        finally:
            connection.logout()

    def _move(self, message_ids: Iterable[str], folder_name: str) -> None:
        connection = self._connect()
        try:
            connection.select("INBOX", readonly=False)
            folder = self._find_folder(connection, folder_name) or folder_name
            for message_id in message_ids:
                connection.uid("copy", message_id.encode("utf-8"), folder)
                connection.uid("store", message_id.encode("utf-8"), "+FLAGS", r"(\Deleted)")
            connection.expunge()
        finally:
            connection.logout()

    def archive(self, message_ids: Iterable[str]) -> None:
        self._move(message_ids, ["Archive", "Archives", "INBOX.Archive"])

    def delete(self, message_ids: Iterable[str]) -> None:
        self._move(message_ids, ["Trash", "Corbeille", "Deleted Items"])


def build_providers(state: AppState) -> list[object]:
    providers: list[object] = []
    if state.google_credentials_path:
        providers.append(GmailProvider(state.google_credentials_path, state.google_token_path))
    if state.microsoft_client_id:
        providers.append(MicrosoftProvider(state.microsoft_client_id, state.microsoft_tenant, state.microsoft_token_path))
    providers.extend(OvhProvider(account) for account in state.ovh_accounts)
    return providers
