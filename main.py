
import sys

from PySide6.QtWidgets import QApplication

from mailcleaner.app import MailCleanerApp

def main():
    application = QApplication(sys.argv)
    application.setApplicationName("MailCleaner Zacoka")
    application.setOrganizationName("Zacoka")
    window = MailCleanerApp()
    window.show()
    sys.exit(application.exec())

if __name__ == "__main__":
    main()
