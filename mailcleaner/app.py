from __future__ import annotations

import csv
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Callable

import keyring
from PySide6.QtCore import QObject, Qt, QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .config import APP_NAME, DATA_DIR, OVH_KEYRING_SERVICE, default_state, ensure_directories, load_state, save_state
from .models import AppState, MailMessage, OvhAccount
from .providers import GmailProvider, MicrosoftProvider, OvhProvider, build_providers


class TaskRunner(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, job: Callable[[], object]) -> None:
        super().__init__()
        self._job = job

    def run(self) -> None:  # noqa: D401 - Qt entry point
        try:
            self.succeeded.emit(self._job())
        except Exception:
            self.failed.emit(traceback.format_exc())


class MailCleanerApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        ensure_directories()
        self.state = load_state()
        self.messages: list[MailMessage] = []
        self.runners: list[TaskRunner] = []
        self.provider_cache: dict[str, object] = {}
        self.setWindowTitle(APP_NAME)
        self.resize(1480, 900)
        self._build_ui()
        self._refresh_account_views()
        self.refresh_messages(silent=True)

    def _build_ui(self) -> None:
        tabs = QTabWidget()
        tabs.addTab(self._build_inbox_tab(), "Boîte")
        tabs.addTab(self._build_accounts_tab(), "Comptes")
        tabs.addTab(self._build_about_tab(), "À propos")
        self.setCentralWidget(tabs)
        self.statusBar().showMessage("Prêt")

    def _build_inbox_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        toolbar = QFrame()
        toolbar_layout = QGridLayout(toolbar)
        self.provider_filter = QComboBox()
        self.provider_filter.addItems(["Tous", "Google", "Microsoft", "OVH"])
        self.provider_filter.currentTextChanged.connect(lambda _: self.refresh_messages())
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Rechercher dans l'objet, l'expéditeur ou l'aperçu")
        self.search_box.returnPressed.connect(self.refresh_messages)
        self.unread_only = QCheckBox("Non lus uniquement")
        self.unread_only.toggled.connect(lambda _: self.refresh_messages())
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(10, 500)
        self.limit_spin.setValue(self.state.message_limit)
        self.limit_spin.valueChanged.connect(self._persist_limit)
        refresh_button = QPushButton("Actualiser")
        refresh_button.clicked.connect(self.refresh_messages)
        archive_button = QPushButton("Archiver la sélection")
        archive_button.clicked.connect(self.archive_selected)
        delete_button = QPushButton("Supprimer la sélection")
        delete_button.clicked.connect(self.delete_selected)
        export_button = QPushButton("Exporter CSV")
        export_button.clicked.connect(self.export_csv)
        open_data = QPushButton("Ouvrir le dossier de données")
        open_data.clicked.connect(self.open_data_folder)

        toolbar_layout.addWidget(QLabel("Fournisseur"), 0, 0)
        toolbar_layout.addWidget(self.provider_filter, 1, 0)
        toolbar_layout.addWidget(QLabel("Recherche"), 0, 1)
        toolbar_layout.addWidget(self.search_box, 1, 1)
        toolbar_layout.addWidget(QLabel("Limite"), 0, 2)
        toolbar_layout.addWidget(self.limit_spin, 1, 2)
        toolbar_layout.addWidget(self.unread_only, 1, 3)
        toolbar_layout.addWidget(refresh_button, 1, 4)
        toolbar_layout.addWidget(archive_button, 1, 5)
        toolbar_layout.addWidget(delete_button, 1, 6)
        toolbar_layout.addWidget(export_button, 1, 7)
        toolbar_layout.addWidget(open_data, 1, 8)
        layout.addWidget(toolbar)

        splitter = QSplitter()
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            ["", "Source", "Compte", "Expéditeur", "Objet", "Date", "Taille", "Non lu", "PJ"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._show_selected_message)
        splitter.addWidget(self.table)

        details_panel = QWidget()
        details_layout = QVBoxLayout(details_panel)
        self.details_title = QLabel("Sélectionnez un message pour voir les détails.")
        self.details_title.setWordWrap(True)
        self.details_body = QTextEdit()
        self.details_body.setReadOnly(True)
        details_layout.addWidget(self.details_title)
        details_layout.addWidget(self.details_body)
        splitter.addWidget(details_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)
        return tab

    def _build_accounts_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        grid = QGridLayout()
        layout.addLayout(grid)

        google_box = QGroupBox("Google OAuth")
        google_form = QFormLayout(google_box)
        self.google_credentials = QLineEdit(self.state.google_credentials_path)
        browse_google = QPushButton("Choisir le JSON")
        browse_google.clicked.connect(self.choose_google_credentials)
        google_path_row = QHBoxLayout()
        google_path_row.addWidget(self.google_credentials)
        google_path_row.addWidget(browse_google)
        google_widget = QWidget()
        google_widget.setLayout(google_path_row)
        self.google_connect = QPushButton("Connexion Google")
        self.google_connect.clicked.connect(self.connect_google)
        self.google_status = QLabel("Non connecté")
        google_form.addRow("Fichier credentials", google_widget)
        google_form.addRow(self.google_connect)
        google_form.addRow("État", self.google_status)
        grid.addWidget(google_box, 0, 0)

        microsoft_box = QGroupBox("Microsoft OAuth")
        microsoft_form = QFormLayout(microsoft_box)
        self.microsoft_client_id = QLineEdit(self.state.microsoft_client_id)
        self.microsoft_tenant = QLineEdit(self.state.microsoft_tenant)
        self.microsoft_connect = QPushButton("Connexion Microsoft")
        self.microsoft_connect.clicked.connect(self.connect_microsoft)
        self.microsoft_status = QLabel("Non connecté")
        microsoft_form.addRow("ID client", self.microsoft_client_id)
        microsoft_form.addRow("Tenant", self.microsoft_tenant)
        microsoft_form.addRow(self.microsoft_connect)
        microsoft_form.addRow("État", self.microsoft_status)
        grid.addWidget(microsoft_box, 0, 1)

        ovh_box = QGroupBox("OVH IMAP")
        ovh_form = QFormLayout(ovh_box)
        self.ovh_email = QLineEdit()
        self.ovh_server = QComboBox()
        self.ovh_server.setEditable(True)
        self.ovh_server.addItems(["ssl0.ovh.net", "imap.mail.ovh.net"])
        self.ovh_port = QSpinBox()
        self.ovh_port.setRange(1, 65535)
        self.ovh_port.setValue(993)
        self.ovh_password = QLineEdit()
        self.ovh_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.ovh_label = QLineEdit()
        add_ovh = QPushButton("Ajouter / mettre à jour")
        add_ovh.clicked.connect(self.save_ovh_account)
        test_ovh = QPushButton("Tester OVH")
        test_ovh.clicked.connect(self.test_ovh_account)
        buttons = QHBoxLayout()
        buttons.addWidget(add_ovh)
        buttons.addWidget(test_ovh)
        buttons_widget = QWidget()
        buttons_widget.setLayout(buttons)
        ovh_form.addRow("Adresse e-mail", self.ovh_email)
        ovh_form.addRow("Serveur", self.ovh_server)
        ovh_form.addRow("Port", self.ovh_port)
        ovh_form.addRow("Mot de passe", self.ovh_password)
        ovh_form.addRow("Libellé", self.ovh_label)
        ovh_form.addRow(buttons_widget)
        grid.addWidget(ovh_box, 1, 0, 1, 2)

        accounts_box = QGroupBox("Comptes OVH enregistrés")
        accounts_layout = QVBoxLayout(accounts_box)
        self.ovh_list = QListWidget()
        remove_ovh = QPushButton("Supprimer le compte sélectionné")
        remove_ovh.clicked.connect(self.remove_selected_ovh)
        accounts_layout.addWidget(self.ovh_list)
        accounts_layout.addWidget(remove_ovh)
        layout.addWidget(accounts_box)
        layout.addStretch(1)
        return tab

    def _build_about_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        label = QLabel(
            "MailCleaner Zacoka est une application de bureau PySide6 pour connecter Gmail, "
            "Microsoft 365/Outlook et des boîtes OVH via IMAP.\n\n"
            f"Données locales: {DATA_DIR}"
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch(1)
        return tab

    def _persist_limit(self, value: int) -> None:
        self.state.message_limit = value
        save_state(self.state)

    def _selected_provider_name(self) -> str:
        return self.provider_filter.currentText()

    def _matching_messages(self) -> list[MailMessage]:
        provider_name = self._selected_provider_name()
        search = self.search_box.text().strip().lower()
        unread_only = self.unread_only.isChecked()
        results: list[MailMessage] = []
        for message in self.messages:
            if provider_name != "Tous" and message.provider != provider_name:
                continue
            if unread_only and not message.unread:
                continue
            if search and search not in " ".join([message.subject, message.sender, message.preview]).lower():
                continue
            results.append(message)
        return results

    def _selected_rows(self) -> list[int]:
        rows = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                rows.append(row)
        return rows

    def _message_at_row(self, row: int) -> MailMessage:
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _provider_for_message(self, message: MailMessage):
        if message.provider == "Google":
            return self.provider_cache.get("Google")
        if message.provider == "Microsoft":
            return self.provider_cache.get("Microsoft")
        return self.provider_cache.get(message.account)

    def _refresh_account_views(self) -> None:
        self.google_credentials.setText(self.state.google_credentials_path)
        self.microsoft_client_id.setText(self.state.microsoft_client_id)
        self.microsoft_tenant.setText(self.state.microsoft_tenant)
        self.ovh_list.clear()
        for account in self.state.ovh_accounts:
            label = account.label or account.email
            item = QListWidgetItem(f"{label}  •  {account.server}:{account.port}")
            item.setData(Qt.ItemDataRole.UserRole, account.email)
            self.ovh_list.addItem(item)

    def run_job(self, job: Callable[[], object], on_success: Callable[[object], None], message: str) -> None:
        self.statusBar().showMessage(message)
        runner = TaskRunner(job)
        self.runners.append(runner)

        def success(result: object) -> None:
            if runner in self.runners:
                self.runners.remove(runner)
            on_success(result)

        def failure(details: str) -> None:
            if runner in self.runners:
                self.runners.remove(runner)
            self.statusBar().showMessage("Erreur")
            QMessageBox.critical(self, APP_NAME, details)

        runner.succeeded.connect(success)
        runner.failed.connect(failure)
        runner.finished.connect(runner.deleteLater)
        runner.start()

    def choose_google_credentials(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choisir credentials.json", "", "JSON (*.json)")
        if path:
            self.google_credentials.setText(path)
            self.state.google_credentials_path = path
            save_state(self.state)

    def connect_google(self) -> None:
        self.state.google_credentials_path = self.google_credentials.text().strip()
        self.state.message_limit = self.limit_spin.value()
        save_state(self.state)

        def job() -> str:
            provider = GmailProvider(self.state.google_credentials_path, self.state.google_token_path)
            provider.authenticate()
            return provider

        self.run_job(
            job,
            lambda provider: (self.provider_cache.__setitem__("Google", provider), self._set_status(self.google_status, "Google connecté")),
            "Connexion Google...",
        )

    def connect_microsoft(self) -> None:
        self.state.microsoft_client_id = self.microsoft_client_id.text().strip()
        self.state.microsoft_tenant = self.microsoft_tenant.text().strip() or "common"
        save_state(self.state)

        def job() -> str:
            provider = MicrosoftProvider(self.state.microsoft_client_id, self.state.microsoft_tenant, self.state.microsoft_token_path)
            provider.authenticate()
            return provider

        self.run_job(
            job,
            lambda provider: (self.provider_cache.__setitem__("Microsoft", provider), self._set_status(self.microsoft_status, "Microsoft connecté")),
            "Connexion Microsoft...",
        )

    def save_ovh_account(self) -> None:
        email_address = self.ovh_email.text().strip()
        server = self.ovh_server.currentText().strip()
        password = self.ovh_password.text()
        if not email_address or not server or not password:
            QMessageBox.warning(self, APP_NAME, "Veuillez renseigner l'adresse, le serveur et le mot de passe OVH.")
            return
        account = OvhAccount(
            email=email_address,
            server=server,
            port=int(self.ovh_port.value()),
            label=self.ovh_label.text().strip(),
        )
        existing = [item for item in self.state.ovh_accounts if item.email != account.email]
        existing.append(account)
        self.state.ovh_accounts = existing
        keyring.set_password(OVH_KEYRING_SERVICE, account.email, password)
        save_state(self.state)
        self._refresh_account_views()
        self.ovh_password.clear()
        QMessageBox.information(self, APP_NAME, f"Compte OVH enregistré pour {account.email}.")

    def test_ovh_account(self) -> None:
        email_address = self.ovh_email.text().strip()
        if not email_address:
            QMessageBox.warning(self, APP_NAME, "Saisissez d'abord une adresse OVH.")
            return
        account = OvhAccount(
            email=email_address,
            server=self.ovh_server.currentText().strip(),
            port=int(self.ovh_port.value()),
            label=self.ovh_label.text().strip(),
        )

        def job() -> str:
            provider = OvhProvider(account)
            provider.authenticate()
            return provider

        self.run_job(
            job,
            lambda provider: (
                self.provider_cache.__setitem__(account.email, provider),
                QMessageBox.information(self, APP_NAME, f"OVH connecté: {account.email}"),
            ),
            "Test OVH...",
        )

    def remove_selected_ovh(self) -> None:
        current = self.ovh_list.currentItem()
        if not current:
            return
        email_address = current.data(Qt.ItemDataRole.UserRole)
        self.state.ovh_accounts = [account for account in self.state.ovh_accounts if account.email != email_address]
        try:
            keyring.delete_password(OVH_KEYRING_SERVICE, email_address)
        except Exception:
            pass
        save_state(self.state)
        self._refresh_account_views()

    def refresh_messages(self, silent: bool = False) -> None:
        self.state.message_limit = self.limit_spin.value()
        self.state.unread_only = self.unread_only.isChecked()
        save_state(self.state)

        def job() -> list[MailMessage]:
            providers = build_providers(self.state)
            provider_cache: dict[str, object] = {}
            collected: list[MailMessage] = []
            provider_name = self._selected_provider_name()
            query = self.search_box.text().strip()
            unread_only = self.unread_only.isChecked()
            limit = self.limit_spin.value()
            for provider in providers:
                if provider.provider_name == "Google":
                    provider_cache["Google"] = provider
                elif provider.provider_name == "Microsoft":
                    provider_cache["Microsoft"] = provider
                elif isinstance(provider, OvhProvider):
                    provider_cache[provider.account.email] = provider
                messages = provider.list_messages(limit=limit, unread_only=unread_only, query=query)
                for message in messages:
                    if provider_name != "Tous" and message.provider != provider_name:
                        continue
                    collected.append(message)
            collected.sort(key=lambda message: message.received_at, reverse=True)
            return collected, provider_cache

        def success(result: tuple[list[MailMessage], dict[str, object]]) -> None:
            messages, provider_cache = result
            self.provider_cache = provider_cache
            self.messages = messages
            self._populate_table(messages)
            self.statusBar().showMessage(f"{len(messages)} message(s) chargés")
            if not silent:
                self._show_message_text("Actualisation terminée.")

        self.run_job(job, success, "Chargement des messages...")

    def _populate_table(self, messages: list[MailMessage]) -> None:
        self.table.setRowCount(0)
        self.table.setRowCount(len(messages))
        for row, message in enumerate(messages):
            checkbox = QTableWidgetItem()
            checkbox.setFlags(checkbox.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            checkbox.setCheckState(Qt.CheckState.Unchecked)
            checkbox.setData(Qt.ItemDataRole.UserRole, message)
            self.table.setItem(row, 0, checkbox)
            values = [
                message.provider,
                message.account,
                message.sender,
                message.subject,
                message.received_at,
                f"{message.size_bytes // 1024} Ko",
                "Oui" if message.unread else "Non",
                "Oui" if message.has_attachments else "Non",
            ]
            for index, value in enumerate(values, start=1):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, message)
                self.table.setItem(row, index, item)
        self.table.resizeColumnsToContents()

    def _show_selected_message(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            self._show_message_text("")
            return
        message = self._message_at_row(rows[0].row())
        self.details_title.setText(f"{message.subject}  |  {message.sender}")
        body = [
            f"Source: {message.provider}",
            f"Compte: {message.account}",
            f"Reçu: {message.received_at}",
            f"Taille: {message.size_bytes} octets",
            f"Non lu: {'oui' if message.unread else 'non'}",
            f"Pièces jointes: {'oui' if message.has_attachments else 'non'}",
            "",
            message.preview or "(Aperçu vide)",
        ]
        self.details_body.setPlainText("\n".join(body))

    def _show_message_text(self, text: str) -> None:
        self.details_title.setText("Détails")
        self.details_body.setPlainText(text)

    def _selected_messages(self) -> list[MailMessage]:
        messages: list[MailMessage] = []
        for row in self._selected_rows():
            messages.append(self._message_at_row(row))
        return messages

    def _provider_actions(self, messages: list[MailMessage]) -> dict[object, list[str]]:
        grouped: dict[object, list[str]] = {}
        for message in messages:
            provider = self._provider_for_message(message)
            if not provider:
                continue
            grouped.setdefault(provider, []).append(message.message_id)
        return grouped

    def archive_selected(self) -> None:
        messages = self._selected_messages()
        if not messages:
            return

        def job() -> str:
            for provider, ids in self._provider_actions(messages).items():
                provider.archive(ids)
            return f"{len(messages)} message(s) archivés"

        self.run_job(job, lambda result: self.refresh_messages(silent=True), "Archivage...")

    def delete_selected(self) -> None:
        messages = self._selected_messages()
        if not messages:
            return

        def job() -> str:
            for provider, ids in self._provider_actions(messages).items():
                provider.delete(ids)
            return f"{len(messages)} message(s) supprimés"

        self.run_job(job, lambda result: self.refresh_messages(silent=True), "Suppression...")

    def export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exporter CSV", str(DATA_DIR / "mailcleaner-export.csv"), "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["provider", "account", "sender", "subject", "received_at", "size_bytes", "unread", "has_attachments", "preview"])
            for message in self._matching_messages():
                writer.writerow([
                    message.provider,
                    message.account,
                    message.sender,
                    message.subject,
                    message.received_at,
                    message.size_bytes,
                    "yes" if message.unread else "no",
                    "yes" if message.has_attachments else "no",
                    message.preview,
                ])
        QMessageBox.information(self, APP_NAME, f"Export CSV créé: {path}")

    def open_data_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(DATA_DIR)))

    def _set_status(self, label: QLabel, text: str) -> None:
        label.setText(text)
        self.statusBar().showMessage(text, 5000)


def create_application() -> QApplication:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("Zacoka")
    return app
