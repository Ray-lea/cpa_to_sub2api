from __future__ import annotations

from app.ui import ConverterMainWindow
from app.ui.main_window import build_application


def main() -> int:
    app = build_application()
    window = ConverterMainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
