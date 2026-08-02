
import sys

from mailcleaner.app import MailCleanerApp, create_application


def main() -> None:
    application = create_application()
    window = MailCleanerApp()
    window.show()
    sys.exit(application.exec())

if __name__ == "__main__":
    main()
