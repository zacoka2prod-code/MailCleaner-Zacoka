
import sys
from mailcleaner.app import MailCleanerApp
from PySide6.QtWidgets import QApplication

def main():
    application = QApplication(sys.argv)
    application.setApplicationName("MailCleaner Zacoka")
    application.setOrganizationName("Zacoka")
    window = MailCleanerApp()
    window.show()
    sys.exit(application.exec())

if __name__ == "__main__":
    main()
