"""Motorcycle Forensic Data Visualizer — entry point.

The application body lives in the ``motoviz`` package; this file stays as the
PyInstaller entry script (referenced from ``Motorcycle Forensic Data
Visualizer.spec``).
"""

from motoviz.main_window import main


if __name__ == "__main__":
    main()
