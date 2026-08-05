from __future__ import annotations

import csv
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Callable

import keyring
from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, QUrl
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
from .providers import GmailProvider, MicrosoftProvider, OvhProvider, build_providers, describe_google_credentials


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
        self.setObjectName("MainWindow")
        self._build_ui()
        self._refresh_account_views()
        QTimer.singleShot(0, lambda: self.refresh_messages(silent=True))

    def _build_ui(self) -> None:
        tabs = QTabWidget()
        tabs.addTab(self._build_inbox_tab(), "Boîte")
        tabs.addTab(self._build_accounts_tab(), "Comptes")
        tabs.addTab(self._build_about_tab(), "À propos")
        self.setCentralWidget(tabs)
        self.statusBar().showMessage("Prêt")
        self.setStyleSheet(
            """
            QMainWindow#MainWindow {
                background: #17191d;
                color: #f4f6f8;
            }
            QWidget {
                color: #f4f6f8;
                font-size: 13px;
            }
            QTabWidget::pane {
                border: 0;
                background: #17191d;
            }
            QTabBar::tab {
                background: #22262c;
                color: #cbd5df;
                padding: 10px 18px;
                margin-right: 6px;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }
            QTabBar::tab:selected {
                background: #2f343b;
                color: white;
            }
            QGroupBox {
                background: #22262c;
                border: 1px solid #3a4048;
                border-radius: 16px;
                margin-top: 18px;
                padding: 16px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 16px;
                top: 6px;
                padding: 0 8px;
                color: #ffffff;
                font-weight: 700;
            }
            QPushButton {
                background: #3a4048;
                color: white;
                border: 1px solid #4a5058;
                border-radius: 12px;
                padding: 10px 16px;
                min-height: 18px;
            }
            QPushButton:hover {
                background: #454b54;
            }
            QPushButton:pressed {
                background: #2e333a;
            }
            QPushButton#primaryButton {
                background: #4f7cff;
                border-color: #4f7cff;
                font-weight: 700;
            }
            QPushButton#primaryButton:hover {
                background: #638aff;
            }
            QPushButton#googleButton {
                background: white;
                color: #1f1f1f;
                font-weight: 700;
                min-height: 42px;
                font-size: 15px;
                border-radius: 999px;
            }
            QPushButton#googleButton:hover {
                background: #f2f2f2;
            }
            QPushButton#emailButton {
                background: transparent;
                color: #f4f6f8;
                border: 1px solid #5a6470;
                min-height: 42px;
                font-size: 14px;
                border-radius: 999px;
            }
            QPushButton#emailButton:hover {
                background: #2a2f36;
            }
            QPushButton#dangerButton {
                background: #6f2f34;
                border-color: #8a4047;
            }
            QLineEdit, QComboBox, QSpinBox, QTextEdit, QTableWidget {
                background: #1f2329;
                color: #f4f6f8;
                border: 1px solid #3a4048;
                border-radius: 10px;
                padding: 8px 10px;
                selection-background-color: #4f7cff;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus {
                border: 1px solid #4f7cff;
            }
            QTableWidget {
                gridline-color: #323842;
            }
            QHeaderView::section {
                background: #272b31;
                color: #d9e1ea;
                border: 0;
                padding: 8px 10px;
                font-weight: 600;
            }
            QStatusBar {
                background: #17191d;
                color: #cbd5df;
            }
            QLabel#heroTitle {
                font-size: 26px;
                font-weight: 800;
                color: white;
            }
            QLabel#heroSubtitle {
                color: #b0bac6;
                font-size: 13px;
            }
            QFrame#connectionBanner {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2d67f8, stop:1 #6a8cff);
                border-radius: 20px;
                padding: 22px;
            }
            QLabel#bannerTitle {
                color: white;
                font-size: 20px;
                font-weight: 800;
            }
            QLabel#bannerSubtitle {
                color: rgba(255, 255, 255, 0.88);
                font-size: 13px;
            }
            QLabel#googleGlyph {
                color: #4285f4;
                background: white;
                border-radius: 999px;
                min-width: 44px;
                min-height: 44px;
                max-width: 44px;
                max-height: 44px;
                font-size: 26px;
                font-weight: 900;
            }
            QLabel#microsoftGlyph {
                color: white;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f25022, stop:1 #7fba00);
                border-radius: 14px;
                min-width: 44px;
                min-height: 44px;
                max-width: 44px;
                max-height: 44px;
                font-size: 24px;
                font-weight: 900;
            }
            QLabel#sectionLabel {
                color: #b0bac6;
                text-transform: uppercase;
                letter-spacing: 1.5px;
                font-size: 10px;
                font-weight: 700;
            }
            QLabel#statusPill {
                background: #1f2329;
                border: 1px solid #3a4048;
                border-radius: 999px;
                padding: 6px 12px;
                color: #b0bac6;
                font-weight: 700;
            }
            QLabel#statusPill[connected="true"] {
                color: #9bffba;
                border-color: #2a5c3d;
                background: #183024;
            }
            """
        )

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
        layout.setSpacing(18)

        hero = QWidget()
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Connexions")
        title.setObjectName("heroTitle")
        subtitle = QLabel(
            "Connecte Gmail, Microsoft et OVH avec une zone de connexion claire, "
            "puis garde les identifiants en local de façon sécurisée."
        )
        subtitle.setObjectName("heroSubtitle")
        hero_layout.addWidget(title)
        hero_layout.addWidget(subtitle)
        layout.addWidget(hero)

        banner = QFrame()
        banner.setObjectName("connectionBanner")
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(18, 18, 18, 18)
        banner_layout.setSpacing(16)
        google_mark = QLabel("G")
        google_mark.setObjectName("googleGlyph")
        google_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        banner_text = QVBoxLayout()
        banner_title = QLabel("Se connecter à tes boîtes")
        banner_title.setObjectName("bannerTitle")
        banner_subtitle = QLabel(
            "Google, Microsoft et OVH apparaissent dans un panneau unique, "
            "avec une expérience simple et rapide."
        )
        banner_subtitle.setObjectName("bannerSubtitle")
        banner_subtitle.setWordWrap(True)
        banner_text.addWidget(banner_title)
        banner_text.addWidget(banner_subtitle)
        banner_layout.addWidget(google_mark)
        banner_layout.addLayout(banner_text, 1)
        layout.addWidget(banner)

        cards = QGridLayout()
        cards.setHorizontalSpacing(16)
        cards.setVerticalSpacing(16)
        layout.addLayout(cards)

        google_box = self._build_google_card()
        microsoft_box = self._build_microsoft_card()
        cards.addWidget(google_box, 0, 0)
        cards.addWidget(microsoft_box, 0, 1)

        ovh_box = self._build_ovh_card()
        layout.addWidget(ovh_box)

        accounts_box = QGroupBox("Comptes OVH enregistrés")
        accounts_layout = QVBoxLayout(accounts_box)
        self.ovh_list = QListWidget()
        self.ovh_list.setMinimumHeight(180)
        remove_ovh = QPushButton("Supprimer le compte sélectionné")
        remove_ovh.setObjectName("dangerButton")
        remove_ovh.clicked.connect(self.remove_selected_ovh)
        accounts_layout.addWidget(self.ovh_list)
        accounts_layout.addWidget(remove_ovh)
        layout.addWidget(accounts_box)
        layout.addStretch(1)
        return tab

    def _status_pill(self, text: str) -> QLabel:
        pill = QLabel(text)
        pill.setObjectName("statusPill")
        pill.setProperty("connected", False)
        return pill

    def _build_google_card(self) -> QGroupBox:
        box = QGroupBox("Google OAuth")
        form = QVBoxLayout(box)
        form.setSpacing(14)

        header = QLabel("Connexion Google")
        header.setObjectName("sectionLabel")
        form.addWidget(header)

        quick_row = QHBoxLayout()
        quick_row.setContentsMargins(0, 0, 0, 0)
        google_mark = QLabel("G")
        google_mark.setObjectName("googleGlyph")
        google_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        quick_text = QVBoxLayout()
        quick_title = QLabel("Continuer avec Google")
        quick_title.setObjectName("bannerTitle")
        quick_subtitle = QLabel("Authentification sécurisée via le navigateur.")
        quick_subtitle.setObjectName("bannerSubtitle")
        quick_subtitle.setWordWrap(True)
        quick_text.addWidget(quick_title)
        quick_text.addWidget(quick_subtitle)
        quick_row.addWidget(google_mark)
        quick_row.addLayout(quick_text, 1)
        form.addLayout(quick_row)

        self.google_credentials = QLineEdit(self.state.google_credentials_path)
        self.google_credentials.setPlaceholderText("credentials.json")
        browse_google = QPushButton("Choisir le JSON")
        browse_google.clicked.connect(self.choose_google_credentials)
        google_path_row = QHBoxLayout()
        google_path_row.setContentsMargins(0, 0, 0, 0)
        google_path_row.addWidget(self.google_credentials, 1)
        google_path_row.addWidget(browse_google)
        form.addLayout(google_path_row)

        self.google_connect = QPushButton("Continuer avec Google")
        self.google_connect.setObjectName("googleButton")
        self.google_connect.clicked.connect(self.connect_google)
        form.addWidget(self.google_connect)

        email_button = QPushButton("S'identifier avec un e-mail")
        email_button.setObjectName("emailButton")
        email_button.clicked.connect(self.choose_google_credentials)
        form.addWidget(email_button)

        google_hint = QLabel(
            "Important: le fichier credentials Google doit venir d'un client OAuth "
            "de type Application de bureau. Si tu utilises un client Web, il faut "
            "autoriser exactement l'URI locale de redirection."
        )
        google_hint.setWordWrap(True)
        google_hint.setStyleSheet("color: #b0bac6; font-size: 12px;")
        form.addWidget(google_hint)

        self.google_status = self._status_pill("Non connecté")
        form.addWidget(self.google_status)
        return box

    def _build_microsoft_card(self) -> QGroupBox:
        box = QGroupBox("Microsoft OAuth")
        form = QVBoxLayout(box)
        form.setSpacing(14)

        header = QLabel("Connexion Microsoft")
        header.setObjectName("sectionLabel")
        form.addWidget(header)

        quick_row = QHBoxLayout()
        quick_row.setContentsMargins(0, 0, 0, 0)
        microsoft_mark = QLabel("M")
        microsoft_mark.setObjectName("microsoftGlyph")
        microsoft_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        quick_text = QVBoxLayout()
        quick_title = QLabel("Continuer avec Microsoft")
        quick_title.setObjectName("bannerTitle")
        quick_subtitle = QLabel("Authentification via le navigateur avec MSAL.")
        quick_subtitle.setObjectName("bannerSubtitle")
        quick_subtitle.setWordWrap(True)
        quick_text.addWidget(quick_title)
        quick_text.addWidget(quick_subtitle)
        quick_row.addWidget(microsoft_mark)
        quick_row.addLayout(quick_text, 1)
        form.addLayout(quick_row)

        self.microsoft_client_id = QLineEdit(self.state.microsoft_client_id)
        self.microsoft_client_id.setPlaceholderText("ID client Azure / Microsoft")
        self.microsoft_tenant = QLineEdit(self.state.microsoft_tenant)
        self.microsoft_tenant.setPlaceholderText("common")

        form.addWidget(self.microsoft_client_id)
        form.addWidget(self.microsoft_tenant)

        self.microsoft_connect = QPushButton("Continuer avec Microsoft")
        self.microsoft_connect.setObjectName("primaryButton")
        self.microsoft_connect.clicked.connect(self.connect_microsoft)
        form.addWidget(self.microsoft_connect)

        helper = QLabel("Astuce: laisse le tenant sur common si tu veux te connecter avec un compte perso.")
        helper.setWordWrap(True)
        helper.setStyleSheet("color: #b0bac6; font-size: 12px;")
        form.addWidget(helper)

        self.microsoft_status = self._status_pill("Non connecté")
        form.addWidget(self.microsoft_status)
        return box

    def _build_ovh_card(self) -> QGroupBox:
        box = QGroupBox("OVH IMAP")
        form = QVBoxLayout(box)
        form.setSpacing(12)

        header = QLabel("Connexion OVH")
        header.setObjectName("sectionLabel")
        form.addWidget(header)

        self.ovh_email = QLineEdit()
        self.ovh_email.setPlaceholderText("Adresse e-mail")
        self.ovh_server = QComboBox()
        self.ovh_server.setEditable(True)
        self.ovh_server.addItems(["ssl0.ovh.net", "imap.mail.ovh.net"])
        self.ovh_port = QSpinBox()
        self.ovh_port.setRange(1, 65535)
        self.ovh_port.setValue(993)
        self.ovh_password = QLineEdit()
        self.ovh_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.ovh_password.setPlaceholderText("Mot de passe")
        self.ovh_label = QLineEdit()
        self.ovh_label.setPlaceholderText("Libellé")

        form.addWidget(self.ovh_email)
        form.addWidget(self.ovh_server)
        form.addWidget(self.ovh_port)
        form.addWidget(self.ovh_password)
        form.addWidget(self.ovh_label)

        buttons = QHBoxLayout()
        add_ovh = QPushButton("Ajouter / mettre à jour")
        add_ovh.setObjectName("primaryButton")
        add_ovh.clicked.connect(self.save_ovh_account)
        test_ovh = QPushButton("Tester OVH")
        test_ovh.clicked.connect(self.test_ovh_account)
        buttons.addWidget(add_ovh)
        buttons.addWidget(test_ovh)
        form.addLayout(buttons)
        return box

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
        self._set_connected(self.google_status, bool(self.state.google_credentials_path), "Prêt pour Google" if self.state.google_credentials_path else "Non connecté")
        self._set_connected(self.microsoft_status, bool(self.state.microsoft_client_id), "Prêt pour Microsoft" if self.state.microsoft_client_id else "Non connecté")

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

    def choose_google_credentials(self) -> bool:
        path, _ = QFileDialog.getOpenFileName(self, "Choisir credentials.json", "", "JSON (*.json)")
        if path:
            self.google_credentials.setText(path)
            self.state.google_credentials_path = path
            save_state(self.state)
            return True
        return False

    def connect_google(self) -> None:
        self.state.google_credentials_path = self.google_credentials.text().strip()
        if not self.state.google_credentials_path:
            if not self.choose_google_credentials():
                return
            self.state.google_credentials_path = self.google_credentials.text().strip()
        if not Path(self.state.google_credentials_path).exists():
            QMessageBox.warning(self, APP_NAME, "Le fichier credentials Google est introuvable.")
            return
        try:
            description = describe_google_credentials(self.state.google_credentials_path)
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        if description["kind"] == "web":
            redirect_uris = ", ".join(description["redirect_uris"]) or "(aucune)"
            if not any(uri.startswith("http://localhost") or uri.startswith("http://127.0.0.1") for uri in description["redirect_uris"]):
                QMessageBox.warning(
                    self,
                    APP_NAME,
                    "Ce JSON Google est de type Web et ne contient pas de redirection locale.\n\n"
                    f"URI trouvées:\n{redirect_uris}\n\n"
                    "Pour cette app de bureau, crée plutôt un client OAuth de type Application de bureau "
                    "ou ajoute une URI localhost comme http://localhost:8080/ dans Google Cloud Console.",
                )
                return
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
        if not self.state.microsoft_client_id:
            QMessageBox.warning(self, APP_NAME, "Renseigne l'ID client Microsoft avant de te connecter.")
            return
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
        self._set_connected(label, "connecté" in text.lower() or "prêt" in text.lower(), text)
        self.statusBar().showMessage(text, 5000)

    def _set_connected(self, label: QLabel, connected: bool, text: str) -> None:
        label.setProperty("connected", connected)
        label.setText(text)
        label.style().unpolish(label)
        label.style().polish(label)
        label.update()


def create_application() -> QApplication:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("Zacoka")
    return app
