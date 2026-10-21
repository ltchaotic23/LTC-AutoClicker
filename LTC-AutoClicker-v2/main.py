"""LTC AutoClicker Application Entry Point."""
import sys
import os

# Ensure the root directory is on sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.crash_reporter import install_crash_handler, hook_tkinter_exceptions
from src.gui import AutoclickerApp

def main():
    install_crash_handler()
    app = AutoclickerApp()
    hook_tkinter_exceptions(app)
    app.mainloop()

if __name__ == "__main__":
    main()
