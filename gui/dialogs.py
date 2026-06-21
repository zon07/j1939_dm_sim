"""Диалоговые окна приложения"""

import tkinter as tk
from tkinter import ttk
from resources.help_text import HELP_TEXT, ABOUT_TEXT


class HelpDialog:
    """Окно помощи"""
    
    def __init__(self, parent):
        self.window = tk.Toplevel(parent)
        self.window.title("Помощь")
        self.window.geometry("550x500+200+100")
        self.window.minsize(400, 300)
        
        frame = ttk.Frame(self.window)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        scrollbar = ttk.Scrollbar(frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        text_widget = tk.Text(frame, wrap=tk.WORD, yscrollcommand=scrollbar.set, font=("Segoe UI", 10))
        text_widget.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=text_widget.yview)
        
        text_widget.insert("1.0", HELP_TEXT)
        text_widget.config(state=tk.DISABLED)
        
        def copy_text():
            try:
                text_widget.clipboard_clear()
                text_widget.clipboard_append(text_widget.selection_get())
            except tk.TclError:
                pass
        
        def show_context_menu(event):
            context_menu.post(event.x_root, event.y_root)
        
        context_menu = tk.Menu(self.window, tearoff=0)
        context_menu.add_command(label="Копировать", command=copy_text)
        text_widget.bind("<Button-3>", show_context_menu)
        text_widget.bind("<Control-c>", lambda e: copy_text())
        text_widget.bind("<Control-C>", lambda e: copy_text())
        text_widget.bind("<Control-с>", lambda e: copy_text())
        text_widget.bind("<Control-С>", lambda e: copy_text())
        
        btn_frame = ttk.Frame(self.window)
        btn_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(btn_frame, text="Закрыть", command=self.window.destroy, width=15).pack()


class AboutDialog:
    """Окно 'О программе'"""
    
    def __init__(self, parent, version: str):
        self.window = tk.Toplevel(parent)
        self.window.title("О программе")
        self.window.geometry("350x250+300+200")
        self.window.resizable(False, False)
        
        frame = ttk.Frame(self.window, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        
        title_label = ttk.Label(frame, text="DM1 Simulator", font=("Segoe UI", 16, "bold"))
        title_label.pack(pady=(0, 5))
        
        version_label = ttk.Label(frame, text=f"Версия {version}", font=("Segoe UI", 10))
        version_label.pack(pady=(0, 5))
        
        ttk.Separator(frame, orient="horizontal").pack(fill=tk.X, pady=5)
        
        desc_label = ttk.Label(frame, text=ABOUT_TEXT, justify=tk.LEFT, font=("Segoe UI", 9))
        desc_label.pack(pady=5)
        
        ttk.Button(frame, text="OK", command=self.window.destroy, width=15).pack(pady=10)