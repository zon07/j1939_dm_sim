"""Главный класс приложения"""

import tkinter as tk
from gui.main_window import MainWindow
from core.simulator import DM1Simulator
from utils.config import ConfigManager
from resources.help_text import HELP_TEXT, ABOUT_TEXT


class DM1SimulatorApp:
    """Главное приложение"""
    
    def __init__(self, root: tk.Tk, version: str):
        self.root = root
        self.version = version
        
        # Загружаем конфигурацию
        self.config = ConfigManager.load_config()
        
        # Устанавливаем геометрию окна
        geometry = self.config.get("window_geometry", "610x800+100+50")
        self.root.geometry(geometry)
        self.root.title(f"DM1 Simulator - PCAN v{version}")
        self.root.minsize(300, 350)
        self.root.resizable(True, True)
        
        # Создаем симулятор
        self.simulator = DM1Simulator()
        
        # Создаем главное окно
        self.main_window = MainWindow(
            root, 
            self.simulator, 
            self.config,
            version,
            self.on_status_update,
            self.save_config
        )
        
        # Привязываем событие изменения размера
        self.root.bind("<Configure>", self.on_window_resize)
    
    def on_status_update(self, message: str):
        """Обновление статуса"""
        self.main_window.set_status(message)
    
    def on_window_resize(self, event=None):
        """Сохранение геометрии при изменении размера"""
        if event and event.widget == self.root and self.root.winfo_viewable():
            self.config["window_geometry"] = self.root.geometry()
    
    def save_config(self):
        """Сохранение конфигурации"""
        ConfigManager.save_config(self.config)
    
    def on_closing(self):
        """Обработка закрытия"""
        self.config["window_geometry"] = self.root.geometry()
        ConfigManager.save_config(self.config)
        self.simulator.stop_sending()
        self.simulator.disconnect()
        self.root.destroy()