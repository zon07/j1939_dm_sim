"""Главный модуль приложения"""

import tkinter as tk
from app import DM1SimulatorApp

VERSION = "1.1.0"

def main():
    root = tk.Tk()
    app = DM1SimulatorApp(root, VERSION)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()