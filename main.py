# main.py
"""DM1 Simulator - Главное приложение"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import can
import os
from typing import Dict

from dtc import DTC
from simulator import DM1Simulator, ConfigManager, build_can_id, J1939_PGN_DM1
from gui_widgets import LampBitCheckboxes
from help_text import HELP_TEXT, ABOUT_TEXT

# Версия программы
VERSION = "1.2.1"
DEFAULT_SAVE_FILE = "dtc_list.json"


class DM1SimulatorGUI:
    """GUI приложения"""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        
        # Загружаем конфигурацию
        self.config = ConfigManager.load_config()
        
        # Устанавливаем геометрию окна из конфига
        geometry = self.config.get("window_geometry", "610x800+100+50")
        self.root.geometry(geometry)
        
        self.root.title(f"DM1 Simulator - PCAN v{VERSION}")
        self.root.minsize(300, 350)
        self.root.resizable(True, True)
        
        self.simulator = DM1Simulator()
        
        # Переменные
        self.selected_channel = tk.StringVar(value=self.config.get("last_channel", ""))
        self.selected_sa = tk.StringVar(value=self.config.get("last_sa", "0x00"))
        self.selected_bitrate = tk.StringVar(value=self.config.get("last_bitrate", "250000"))
        self.spn_var = tk.StringVar(value="0")
        self.fmi_var = tk.StringVar(value="0")
        
        # Переменные для лампочек
        self.lamp_vars = {
            'MIL_L': tk.StringVar(value="0b11"),
            'RSL_L': tk.StringVar(value="0b11"),
            'AWL_L': tk.StringVar(value="0b11"),
            'PL_L': tk.StringVar(value="0b11"),
            'MIL_F': tk.StringVar(value="0b11"),
            'RSL_F': tk.StringVar(value="0b11"),
            'AWL_F': tk.StringVar(value="0b11"),
            'PL_F': tk.StringVar(value="0b11")
        }
        
        # Создаем меню
        self.create_menu()
        
        self.create_widgets()
        self.scan_channels()
        self.load_default_file()
        
        # Привязываем событие изменения размера окна
        self.root.bind("<Configure>", self.on_window_resize)
    
    def create_menu(self):
        """Создание главного меню"""
        menubar = tk.Menu(        self.root,
        bg='#f0f0f0',                   # Фон меню
        fg='#000000',                   # Цвет текста
        activebackground='#cce8ff',     # Фон при наведении
        activeforeground='#000000',     # Цвет текста при наведении
        relief='raised',                  # Рельеф (приподнятое)
        bd=1,                             # Толщина рамки
        borderwidth=1)
        self.root.config(menu=menubar)
        
        # Меню "Справка"
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Справка", menu=help_menu)
        help_menu.add_command(label="Помощь", command=self.show_help)
        help_menu.add_separator()
        help_menu.add_command(label="О программе", command=self.show_about)
    
    def show_help(self):
        """Показать окно помощи"""
        help_window = tk.Toplevel(self.root)
        help_window.title("Помощь")
        help_window.geometry("550x500+200+100")
        help_window.minsize(400, 300)
        
        # Фрейм с прокруткой
        frame = ttk.Frame(help_window)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        scrollbar = ttk.Scrollbar(frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        text_widget = tk.Text(frame, wrap=tk.WORD, yscrollcommand=scrollbar.set, font=("Segoe UI", 10))
        text_widget.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=text_widget.yview)
        
        text_widget.insert("1.0", HELP_TEXT)
        text_widget.config(state=tk.DISABLED)
        
        # Функция копирования
        def copy_text():
            try:
                text_widget.clipboard_clear()
                text_widget.clipboard_append(text_widget.selection_get())
            except tk.TclError:
                pass
        
        # Контекстное меню
        def show_context_menu(event):
            context_menu.post(event.x_root, event.y_root)
        
        context_menu = tk.Menu(help_window, tearoff=0)
        context_menu.add_command(label="Копировать", command=copy_text)
        text_widget.bind("<Button-3>", show_context_menu)
        
        # Горячие клавиши для копирования (работает с любой раскладкой)
        text_widget.bind("<Control-c>", lambda e: copy_text())
        text_widget.bind("<Control-C>", lambda e: copy_text())  # Для Caps Lock
        text_widget.bind("<Control-с>", lambda e: copy_text())  # Русская 'с' (строчная)
        text_widget.bind("<Control-С>", lambda e: copy_text())  # Русская 'С' (заглавная)
        
        # Кнопка закрыть
        btn_frame = ttk.Frame(help_window)
        btn_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(btn_frame, text="Закрыть", command=help_window.destroy, width=15).pack()
    
    def show_about(self):
        """Показать окно 'О программе'"""
        about_window = tk.Toplevel(self.root)
        about_window.title("О программе")
        about_window.geometry("350x250+300+200")
        about_window.resizable(False, False)
        
        # Основной фрейм
        frame = ttk.Frame(about_window, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Название
        title_label = ttk.Label(frame, text="DM1 Simulator", font=("Segoe UI", 16, "bold"))
        title_label.pack(pady=(0, 5))
        
        # Версия
        version_label = ttk.Label(frame, text=f"Версия {VERSION}", font=("Segoe UI", 10))
        version_label.pack(pady=(0, 5))
        
        # Разделитель
        ttk.Separator(frame, orient="horizontal").pack(fill=tk.X, pady=5)
        
        # Описание
        desc_label = ttk.Label(frame, text=ABOUT_TEXT, justify=tk.LEFT, font=("Segoe UI", 9))
        desc_label.pack(pady=5)
        
        # Кнопка закрыть
        ttk.Button(frame, text="OK", command=about_window.destroy, width=15).pack(pady=10)
    
    def on_window_resize(self, event=None):
        """Сохраняем геометрию окна при изменении"""
        if event and event.widget == self.root:
            # Сохраняем только если окно видимо и не свернуто
            if self.root.winfo_viewable():
                geometry = self.root.geometry()
                self.config["window_geometry"] = geometry
    
    def create_widgets(self):
        """Создание виджетов"""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # === Секция подключения ===
        conn_frame = ttk.LabelFrame(main_frame, text="Подключение к PCAN", padding="10")
        conn_frame.pack(fill=tk.X, pady=5)
        
        row1 = ttk.Frame(conn_frame)
        row1.pack(fill=tk.X, pady=2)
        
        ttk.Label(row1, text="Канал:").pack(side=tk.LEFT, padx=5)
        self.channel_combo = ttk.Combobox(row1, textvariable=self.selected_channel, width=20, state="readonly")
        self.channel_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(row1, text="Обновить", command=self.scan_channels, width=10).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(row1, text="Скорость:").pack(side=tk.LEFT, padx=(20, 5))
        bitrate_combo = ttk.Combobox(row1, textvariable=self.selected_bitrate, 
                                    values=["250000", "500000"], width=8, state="readonly")
        bitrate_combo.pack(side=tk.LEFT, padx=5)
        
        self.connect_btn = ttk.Button(row1, text="Подключиться", command=self.toggle_connection, width=14)
        self.connect_btn.pack(side=tk.LEFT, padx=10)
        
        # === Секция SA ===
        sa_frame = ttk.LabelFrame(main_frame, text="Настройка SA", padding="10")
        sa_frame.pack(fill=tk.X, pady=5)
        
        row2 = ttk.Frame(sa_frame)
        row2.pack(fill=tk.X)
        
        ttk.Label(row2, text="SA (0x00-0xFF):").pack(side=tk.LEFT, padx=5)
        
        sa_values = [f"0x{i:02X}" for i in range(256)]
        self.sa_combo = ttk.Combobox(row2, textvariable=self.selected_sa, values=sa_values, width=8, state="readonly")
        self.sa_combo.pack(side=tk.LEFT, padx=5)
        self.sa_combo.set(self.config.get("last_sa", "0x00"))
        
        ttk.Label(row2, text="Пример ID:").pack(side=tk.LEFT, padx=(20, 5))
        self.id_example_label = ttk.Label(row2, text="0x18FECA00", foreground="blue", font=("Courier", 10, "bold"))
        self.id_example_label.pack(side=tk.LEFT, padx=5)
        
        self.start_btn = ttk.Button(row2, text="Старт", command=self.toggle_sending, width=10)
        self.start_btn.pack(side=tk.LEFT, padx=10)
        self.start_btn.config(state=tk.DISABLED)
        
        self.status_label = ttk.Label(row2, text="● Остановлен", foreground="red")
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        self.sa_combo.bind('<<ComboboxSelected>>', self.on_sa_changed)
        
        # === Секция лампочек DM1 (первые 2 байта) ===
        lamps_frame = ttk.LabelFrame(main_frame, text="DM1 Lamp Status (первые 2 байта)", padding="10")
        lamps_frame.pack(fill=tk.X, pady=5)
        
        lamps_container = ttk.Frame(lamps_frame)
        lamps_container.pack(fill=tk.X)
        
        self.lamp_widget = LampBitCheckboxes(lamps_container, self.lamp_vars, self.on_lamp_changed)
        
        lamp_preview_frame = ttk.Frame(lamps_frame)
        lamp_preview_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Label(lamp_preview_frame, text="Текущие байты:").pack(side=tk.LEFT, padx=5)
        self.lamp_preview_label = ttk.Label(lamp_preview_frame, text="Байт1: 0xFF  Байт2: 0xFF", 
                                            font=("Courier", 10, "bold"), foreground="darkblue")
        self.lamp_preview_label.pack(side=tk.LEFT, padx=10)
        
        ttk.Button(lamp_preview_frame, text="Сбросить", command=self.reset_lamps).pack(side=tk.RIGHT, padx=5)
        
        # === Секция добавления ошибок ===
        add_frame = ttk.LabelFrame(main_frame, text="Добавить ошибку", padding="10")
        add_frame.pack(fill=tk.X, pady=5)
        
        row3 = ttk.Frame(add_frame)
        row3.pack(fill=tk.X, pady=2)
        
        ttk.Label(row3, text="SPN (0-524287):").pack(side=tk.LEFT, padx=5)
        spn_entry = ttk.Entry(row3, textvariable=self.spn_var, width=12)
        spn_entry.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(row3, text="FMI (0-31):").pack(side=tk.LEFT, padx=5)
        fmi_entry = ttk.Entry(row3, textvariable=self.fmi_var, width=6)
        fmi_entry.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(row3, text="Добавить", command=self.add_error, width=10).pack(side=tk.LEFT, padx=10)
        
        self.limit_label = ttk.Label(row3, text="", foreground="orange")
        self.limit_label.pack(side=tk.LEFT, padx=10)
        
        # === Секция списка ошибок ===
        list_frame = ttk.LabelFrame(main_frame, text="Список ошибок", padding="10")
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        list_container = ttk.Frame(list_frame)
        list_container.pack(fill=tk.BOTH, expand=True)
        
        columns = ("#", "SPN", "FMI", "Данные (hex)", "Вкл")
        self.errors_tree = ttk.Treeview(list_container, columns=columns, show="headings", height=9)
        
        self.errors_tree.heading("#", text="#")
        self.errors_tree.heading("SPN", text="SPN")
        self.errors_tree.heading("FMI", text="FMI")
        self.errors_tree.heading("Данные (hex)", text="Данные (hex)")
        self.errors_tree.heading("Вкл", text="Вкл")
        
        # Устанавливаем ширину колонок
        self.errors_tree.column("#", width=40, anchor=tk.CENTER)
        self.errors_tree.column("SPN", width=100, anchor=tk.CENTER)
        self.errors_tree.column("FMI", width=80, anchor=tk.CENTER)
        self.errors_tree.column("Данные (hex)", width=200, anchor=tk.CENTER)
        self.errors_tree.column("Вкл", width=50, anchor=tk.CENTER)
        
        scrollbar_tree = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.errors_tree.yview)
        self.errors_tree.configure(yscrollcommand=scrollbar_tree.set)
        
        self.errors_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar_tree.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Двойной клик для переключения статуса ошибки
        self.errors_tree.bind("<Double-1>", self.toggle_dtc_from_tree)
        
        btn_frame = ttk.Frame(list_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(btn_frame, text="Удалить", command=self.remove_selected_error, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Очистить", command=self.clear_errors, width=12).pack(side=tk.LEFT, padx=2)
        
        self.errors_enabled_var = tk.BooleanVar(value=True)
        self.errors_toggle_btn = ttk.Button(btn_frame, text="Выключить", 
                                            command=self.toggle_errors_enabled, width=12)
        self.errors_toggle_btn.pack(side=tk.LEFT, padx=2)
        
        ttk.Button(btn_frame, text="💾 Сохранить", command=self.save_list, width=13).pack(side=tk.RIGHT, padx=2)
        ttk.Button(btn_frame, text="📂 Загрузить", command=self.load_list, width=13).pack(side=tk.RIGHT, padx=2)
        
        self.errors_status_label = ttk.Label(btn_frame, text="🟢 Включен", foreground="green")
        self.errors_status_label.pack(side=tk.LEFT, padx=10)
        
        info_frame = ttk.Frame(main_frame)
        info_frame.pack(fill=tk.X, pady=5)
        
        self.info_label = ttk.Label(info_frame, text="Ошибок: 0 | Режим: нет ошибок (SPN=0, FMI=0)", foreground="blue")
        self.info_label.pack(side=tk.LEFT)
        
        self.send_count_label = ttk.Label(info_frame, text="Отправлено: 0", foreground="green")
        self.send_count_label.pack(side=tk.RIGHT)
        
        self.send_count = 0
        
        status_frame = ttk.Frame(self.root)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.status_bar = ttk.Label(status_frame, text="Готов", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.version_label = ttk.Label(status_frame, text=f"v{VERSION}", relief=tk.SUNKEN, anchor=tk.E, width=10)
        self.version_label.pack(side=tk.RIGHT, fill=tk.X)
        
        self.update_lamp_preview()
    
    def reset_lamps(self):
        """Сброс всех лампочек в значение 0"""
        for key in self.lamp_vars:
            self.lamp_vars[key].set("0b00")
        # Обновляем чекбоксы
        self.lamp_widget.update_checkboxes_from_values()
        # Обновляем значения в simulator
        self.update_lamp_values()
        self.update_lamp_preview()
        self.status_bar.config(text="✅ Лампочки сброшены в 00")
    
    def on_lamp_changed(self, event=None):
        self.update_lamp_values()
        self.update_lamp_preview()
    
    def update_lamp_values(self):
        for key, var in self.lamp_vars.items():
            value_str = var.get()
            if value_str:
                if value_str.startswith("0b"):
                    value = int(value_str[2:], 2)
                else:
                    try:
                        value = int(value_str)
                    except ValueError:
                        value = 3
                self.simulator.set_lamp_value(key, value)
    
    def update_lamp_preview(self):
        self.update_lamp_values()
        byte0, byte1 = self.simulator.get_lamp_bytes()
        self.lamp_preview_label.config(text=f"Байт1: 0x{byte0:02X}  Байт2: 0x{byte1:02X}")
    
    def toggle_errors_enabled(self):
        self.simulator.set_errors_enabled(not self.simulator.errors_enabled)
        self.update_errors_status()
        self.status_bar.config(text=f"Список ошибок: {'🟢 Включен' if self.simulator.errors_enabled else '🔴 Выключен'}")
        self.update_error_list()
    
    def update_errors_status(self):
        if self.simulator.errors_enabled:
            self.errors_toggle_btn.config(text="Выключить")
            self.errors_status_label.config(text="🟢 Включен", foreground="green")
        else:
            self.errors_toggle_btn.config(text="Включить")
            self.errors_status_label.config(text="🔴 Выключен", foreground="red")
    
    def toggle_selected_dtc(self):
        """Переключение статуса выбранной ошибки"""
        selected = self.errors_tree.selection()
        if not selected:
            messagebox.showinfo("Информация", "Выберите ошибку для переключения")
            return
        
        item = selected[0]
        # Сохраняем индекс до обновления
        index = self.errors_tree.index(item)
        
        if self.simulator.toggle_dtc_enabled(index):
            self.update_error_list()
            # Восстанавливаем выделение на той же строке
            children = self.errors_tree.get_children()
            if index < len(children):
                self.errors_tree.selection_set(children[index])
                self.errors_tree.focus(children[index])
            dtc = self.simulator.dtc_list[index]
            status = "включена" if dtc.enabled else "выключена"
            self.status_bar.config(text=f"✅ Ошибка #{index+1} {status}")
    
    def toggle_dtc_from_tree(self, event):
        """Обработка двойного клика по строке списка"""
        self.toggle_selected_dtc()
    
    def save_list(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=DEFAULT_SAVE_FILE
        )
        if filename:
            if self.simulator.save_to_file(filename):
                self.status_bar.config(text=f"✅ Список сохранен в {os.path.basename(filename)}")
            else:
                messagebox.showerror("Ошибка", "Не удалось сохранить список")
    
    def load_list(self):
        filename = filedialog.askopenfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=DEFAULT_SAVE_FILE
        )
        if filename:
            if self.simulator.load_from_file(filename):
                for key, value in self.simulator.lamp_status.items():
                    binary_str = f"0b{value:02b}"
                    self.lamp_vars[key].set(binary_str)
                # Обновляем чекбоксы
                self.lamp_widget.update_checkboxes_from_values()
                self.update_lamp_preview()
                self.update_error_list()
                self.update_errors_status()
                self.status_bar.config(text=f"✅ Список загружен из {os.path.basename(filename)}")
                self.update_send_mode_info()
            else:
                messagebox.showerror("Ошибка", "Не удалось загрузить список")
    
    def load_default_file(self):
        if os.path.exists(DEFAULT_SAVE_FILE):
            if self.simulator.load_from_file(DEFAULT_SAVE_FILE):
                for key, value in self.simulator.lamp_status.items():
                    binary_str = f"0b{value:02b}"
                    self.lamp_vars[key].set(binary_str)
                # Обновляем чекбоксы
                self.lamp_widget.update_checkboxes_from_values()
                self.update_lamp_preview()
                self.update_error_list()
                self.update_errors_status()
                self.update_send_mode_info()
                self.status_bar.config(text=f"📂 Загружен список из {DEFAULT_SAVE_FILE}")
    
    def update_send_mode_info(self):
        with self.simulator.lock:
            dtc_list = self.simulator.dtc_list.copy()
            errors_enabled = self.simulator.errors_enabled
        
        enabled_dtc = [dtc for dtc in dtc_list if dtc.enabled]
        count = len(dtc_list)
        enabled_count = len(enabled_dtc)
        
        if not errors_enabled:
            mode = "🔴 СПИСОК ВЫКЛЮЧЕН - отправляется нулевое сообщение"
        elif enabled_count == 0:
            mode = "нет включенных ошибок (SPN=0, FMI=0)"
        elif enabled_count == 1:
            mode = "одиночное сообщение"
        else:
            total_bytes = 2 + enabled_count * 4
            total_packets = (total_bytes + 6) // 7
            mode = f"BAM ({enabled_count} ошибок, {total_packets} пакетов)"
        
        self.info_label.config(text=f"Ошибок: {count} (вкл: {enabled_count}) | Режим: {mode}")
        
        if count >= 400:
            self.limit_label.config(text=f"⚠️ {count}/445", foreground="red")
        elif count >= 300:
            self.limit_label.config(text=f"⚠️ {count}/445", foreground="orange")
        else:
            self.limit_label.config(text=f"{count}/445", foreground="green")
    
    def scan_channels(self):
        channels = []
        try:
            configs = can.detect_available_configs(interfaces=['pcan'])
            for config in configs:
                channels.append(config['channel'])
        except Exception as e:
            print(f"Ошибка сканирования: {e}")
        
        if channels:
            self.channel_combo['values'] = channels
            # Если сохраненный канал есть в списке, выбираем его
            if self.selected_channel.get() in channels:
                self.channel_combo.set(self.selected_channel.get())
            else:
                self.selected_channel.set(channels[0])
        else:
            self.channel_combo['values'] = []
            self.status_bar.config(text="❌ Нет PCAN устройств")
    
    def toggle_connection(self):
        if self.simulator.connected:
            self.disconnect()
        else:
            self.connect()
    
    def connect(self):
        channel = self.selected_channel.get()
        if not channel:
            messagebox.showerror("Ошибка", "Выберите CAN канал")
            return
        
        bitrate = int(self.selected_bitrate.get())
        
        if self.simulator.connect(channel, bitrate):
            self.connect_btn.config(text="Отключиться")
            self.status_bar.config(text=f"✅ Подключено к {channel}")
            self.start_btn.config(state=tk.NORMAL)
            self.update_id_example()
            # Сохраняем последний канал и битрейт
            self.config["last_channel"] = channel
            self.config["last_bitrate"] = str(bitrate)
        else:
            messagebox.showerror("Ошибка", "Не удалось подключиться")
    
    def disconnect(self):
        self.simulator.stop_sending()
        self.simulator.disconnect()
        self.connect_btn.config(text="Подключиться")
        self.start_btn.config(state=tk.DISABLED)
        self.start_btn.config(text="Старт")
        self.status_label.config(text="● Остановлен", foreground="red")
        self.status_bar.config(text="Отключено")
        self.send_count = 0
        self.send_count_label.config(text="Отправлено: 0")
    
    def on_sa_changed(self, event=None):
        self.update_id_example()
        
        if self.simulator.connected:
            sa_str = self.selected_sa.get()
            if sa_str:
                sa = int(sa_str, 16)
                self.simulator.set_sa(sa)
                self.status_bar.config(text=f"SA: {sa_str}")
        
        # Сохраняем выбранный SA
        self.config["last_sa"] = self.selected_sa.get()
    
    def update_id_example(self):
        sa_str = self.selected_sa.get()
        if sa_str:
            sa = int(sa_str, 16)
            can_id = build_can_id(J1939_PGN_DM1, sa)
            self.id_example_label.config(text=f"0x{can_id:08X}")
    
    def toggle_sending(self):
        if self.simulator.send_thread_running:
            self.stop_sending()
        else:
            self.start_sending()
    
    def start_sending(self):
        if not self.simulator.connected:
            messagebox.showerror("Ошибка", "Сначала подключитесь к CAN")
            return
        
        sa_str = self.selected_sa.get()
        if not sa_str:
            messagebox.showerror("Ошибка", "Выберите SA")
            return
        
        sa = int(sa_str, 16)
        self.simulator.set_sa(sa)
        
        if self.simulator.start_sending():
            self.start_btn.config(text="Стоп")
            self.status_label.config(text="● Отправка...", foreground="green")
            self.status_bar.config(text="🔄 Отправка DM1 сообщений")
            self.send_count = 0
            self.send_count_label.config(text="Отправлено: 0")
            self.update_send_count()
            self.sa_combo.config(state="disabled")
        else:
            messagebox.showerror("Ошибка", "Не удалось запустить отправку")
            self.sa_combo.config(state="enabled")
    
    def stop_sending(self):
        self.simulator.stop_sending()
        self.start_btn.config(text="Старт")
        self.status_label.config(text="● Остановлен", foreground="red")
        self.status_bar.config(text="Отправка остановлена")
        self.sa_combo.config(state="enabled")
    
    def update_send_count(self):
        if self.simulator.send_thread_running:
            self.send_count += 1
            self.send_count_label.config(text=f"Отправлено: {self.send_count}")
            self.root.after(1000, self.update_send_count)
    
    def add_error(self):
        try:
            spn = int(self.spn_var.get())
            fmi = int(self.fmi_var.get())
        except ValueError:
            messagebox.showerror("Ошибка", "Введите корректные числа")
            return
        
        if spn < 0 or spn > 524287:
            messagebox.showerror("Ошибка", "SPN должен быть от 0 до 524287")
            return
        
        if fmi < 0 or fmi > 31:
            messagebox.showerror("Ошибка", "FMI должен быть от 0 до 31")
            return
        
        success, msg = self.simulator.add_dtc(spn, fmi)
        if success:
            self.update_error_list()
            self.spn_var.set("0")
            self.fmi_var.set("0")
            self.status_bar.config(text=f"✅ Добавлена ошибка SPN={spn}, FMI={fmi}")
        else:
            messagebox.showinfo("Информация", msg)
    
    def remove_selected_error(self):
        selected = self.errors_tree.selection()
        if not selected:
            messagebox.showinfo("Информация", "Выберите ошибку для удаления")
            return
        
        item = selected[0]
        index = self.errors_tree.index(item)
        
        if self.simulator.remove_dtc(index):
            self.update_error_list()
            self.status_bar.config(text=f"✅ Ошибка удалена")
    
    def clear_errors(self):
        if self.simulator.dtc_list:
            self.simulator.clear_dtc()
            self.update_error_list()
            self.status_bar.config(text="🧹 Список ошибок очищен")
    
    def update_error_list(self):
        # Сохраняем текущее выделение
        selected_items = self.errors_tree.selection()
        selected_index = None
        if selected_items:
            selected_index = self.errors_tree.index(selected_items[0])
        
        # Очищаем список
        for item in self.errors_tree.get_children():
            self.errors_tree.delete(item)
        
        with self.simulator.lock:
            dtc_list = self.simulator.dtc_list.copy()
            errors_enabled = self.simulator.errors_enabled
        
        # Сортируем для отображения
        dtc_list_sorted = sorted(dtc_list, key=lambda x: (x.spn, x.fmi))
        
        for idx, dtc in enumerate(dtc_list_sorted, 1):
            dtc_bytes = DTC(spn=dtc.spn, fmi=dtc.fmi).to_bytes()
            hex_str = ' '.join([f'{b:02X}' for b in dtc_bytes])
            status = "✅" if dtc.enabled else "❌"
            self.errors_tree.insert("", tk.END, values=(idx, dtc.spn, dtc.fmi, hex_str, status))
        
        # Восстанавливаем выделение
        if selected_index is not None:
            children = self.errors_tree.get_children()
            if selected_index < len(children):
                self.errors_tree.selection_set(children[selected_index])
                self.errors_tree.focus(children[selected_index])
        
        self.update_send_mode_info()
        self.update_errors_status()
    
    def on_closing(self):
        # Сохраняем геометрию перед закрытием
        geometry = self.root.geometry()
        self.config["window_geometry"] = geometry
        ConfigManager.save_config(self.config)
        
        self.simulator.save_to_file(DEFAULT_SAVE_FILE)
        self.simulator.stop_sending()
        self.simulator.disconnect()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = DM1SimulatorGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()