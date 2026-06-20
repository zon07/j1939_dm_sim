# dm1_simulator.py
"""Имитатор ошибок DM1 для PCAN"""

import tkinter as tk
from tkinter import ttk, messagebox
import can
import time
import threading
from dataclasses import dataclass
from typing import List, Optional

# Конфигурация
J1939_PGN_DM1 = 0xFECA
J1939_PGN_TP_CM = 0xECFF  # Изменено с 0xEC00
J1939_PGN_TP_DT = 0xEBFF  # Изменено с 0xEB00
J1939_PRIORITY = 6
CAN_SEND_INTERVAL_MS = 1000  # 1 секунда между началами DM1
TP_DT_INTERVAL_MS = 200  # 200 мс между пакетами TP.DT


@dataclass
class DTC:
    """Diagnostic Trouble Code"""
    spn: int
    fmi: int
    
    def to_bytes(self) -> bytes:
        """Преобразование в 4 байта DM1"""
        # SPN: 19 бит (0-524287)
        # FMI: 5 бит (0-31)
        spn_lsb = self.spn & 0xFF
        spn_mid = (self.spn >> 8) & 0xFF
        spn_msb = (self.spn >> 16) & 0x07  # 3 бита SPN
        fmi_byte = (spn_msb << 5) | (self.fmi & 0x1F)
        return bytes([spn_lsb, spn_mid, fmi_byte, 0xFF])


def build_can_id(pgn: int, sa: int) -> int:
    """Формирование 29-битного CAN ID"""
    # (Priority << 26) | (PGN << 8) | SA
    return (J1939_PRIORITY << 26) | (pgn << 8) | (sa & 0xFF)


class DM1Simulator:
    """Имитатор отправки DM1 сообщений"""
    
    def __init__(self):
        self.bus = None
        self.connected = False
        self.current_sa = None
        self.dtc_list: List[DTC] = []
        self.send_thread_running = False
        self.send_thread = None
        self.lock = threading.Lock()
    
    def connect(self, channel: str, bitrate: int) -> bool:
        """Подключение к CAN шине"""
        try:
            self.bus = can.interface.Bus(
                interface='pcan',
                channel=channel,
                bitrate=bitrate
            )
            self.connected = True
            return True
        except Exception as e:
            print(f"Ошибка подключения: {e}")
            return False
    
    def disconnect(self):
        """Отключение от CAN шины"""
        self.send_thread_running = False
        if self.send_thread:
            self.send_thread.join(timeout=1)
            self.send_thread = None
        
        if self.bus:
            try:
                self.bus.shutdown()
            except:
                pass
            self.bus = None
        
        self.connected = False
        print("CAN отключен")
    
    def set_sa(self, sa: int):
        """Установка SA"""
        self.current_sa = sa
    
    def set_dtc_list(self, dtc_list: List[DTC]):
        """Установка списка ошибок"""
        with self.lock:
            self.dtc_list = dtc_list.copy()
    
    def add_dtc(self, spn: int, fmi: int):
        """Добавление ошибки"""
        with self.lock:
            # Проверяем, нет ли уже такой ошибки
            for dtc in self.dtc_list:
                if dtc.spn == spn and dtc.fmi == fmi:
                    return False
            self.dtc_list.append(DTC(spn=spn, fmi=fmi))
            return True
    
    def remove_dtc(self, index: int):
        """Удаление ошибки по индексу"""
        with self.lock:
            if 0 <= index < len(self.dtc_list):
                del self.dtc_list[index]
                return True
            return False
    
    def clear_dtc(self):
        """Очистка списка ошибок"""
        with self.lock:
            self.dtc_list.clear()
    
    def start_sending(self):
        """Запуск отправки сообщений"""
        if not self.connected or self.current_sa is None:
            return False
        
        if self.send_thread_running:
            return True
        
        self.send_thread_running = True
        self.send_thread = threading.Thread(target=self._send_loop, daemon=True)
        self.send_thread.start()
        return True
    
    def stop_sending(self):
        """Остановка отправки"""
        self.send_thread_running = False
    
    def _send_loop(self):
        """Цикл отправки DM1 сообщений с фиксированным интервалом 1 секунда между началами"""
        while self.send_thread_running and self.connected:
            start_time = time.time()
            
            try:
                self._send_current_dm1()
            except Exception as e:
                print(f"Ошибка отправки: {e}")
            
            # Вычисляем время, затраченное на отправку
            elapsed = time.time() - start_time
            # Спим оставшееся время до 1 секунды
            sleep_time = max(0, CAN_SEND_INTERVAL_MS / 1000.0 - elapsed)
            if sleep_time > 0 and self.send_thread_running:
                time.sleep(sleep_time)
    
    def _send_current_dm1(self):
        """Отправка текущего DM1 сообщения"""
        with self.lock:
            dtc_list = self.dtc_list.copy()
        
        if not dtc_list:
            # Отправляем сообщение "нет ошибок": SPN=0, FMI=0
            self._send_dm1_single(0, 0)
        elif len(dtc_list) == 1:
            # Одиночное сообщение
            dtc = dtc_list[0]
            self._send_dm1_single(dtc.spn, dtc.fmi)
        else:
            # Множественные ошибки - BAM
            self._send_dm1_bam(dtc_list)
    
    def _send_dm1_single(self, spn: int, fmi: int):
        """Отправка одиночного сообщения DM1"""
        if not self.bus:
            return
        
        # Формат: 8 байт
        # Байт 0-1: лампочки (FF FF)
        # Байт 2: LSB SPN
        # Байт 3: Middle SPN
        # Байт 4: FMI + MSB SPN
        # Байт 5-7: FF FF FF
        
        spn_lsb = spn & 0xFF
        spn_mid = (spn >> 8) & 0xFF
        spn_msb = (spn >> 16) & 0x07
        fmi_byte = (spn_msb << 5) | (fmi & 0x1F)
        
        data = bytearray(8)
        data[0] = 0xFF
        data[1] = 0xFF
        data[2] = spn_lsb
        data[3] = spn_mid
        data[4] = fmi_byte
        data[5] = 0xFF
        data[6] = 0xFF
        data[7] = 0xFF
        
        # Формируем CAN ID: 0x18FECA[SA]
        can_id = build_can_id(J1939_PGN_DM1, self.current_sa)
        
        msg = can.Message(
            arbitration_id=can_id,
            data=bytes(data),
            is_extended_id=True,
            dlc=8
        )
        
        try:
            self.bus.send(msg)
            print(f"DM1: ID=0x{can_id:08X}, SPN={spn}, FMI={fmi}")
        except Exception as e:
            print(f"Ошибка отправки DM1: {e}")
    
    def _send_dm1_bam(self, dtc_list: List[DTC]):
        """Отправка множественных ошибок через BAM"""
        if not self.bus:
            return
        
        # Формируем данные: 2 байта лампочек + 4 байта на каждую ошибку
        data = bytearray(2)  # FF FF
        data[0] = 0xFF
        data[1] = 0xFF
        
        for dtc in dtc_list:
            data.extend(dtc.to_bytes())
        
        # Ограничиваем до 1785 байт (максимум для BAM)
        if len(data) > 1785:
            data = data[:1785]
        
        total_bytes = len(data)
        total_packets = (total_bytes + 6) // 7  # 7 байт данных на пакет
        
        # Отправляем TP.CM (BAM Announcement)
        self._send_tp_cm(total_bytes, total_packets)
        
        # Отправляем TP.DT пакеты с интервалом 200 мс
        packet_number = 1
        for i in range(0, total_bytes, 7):
            chunk = data[i:i+7]
            self._send_tp_dt(packet_number, chunk)
            packet_number += 1
            if i + 7 < total_bytes:  # Не ждем после последнего пакета
                time.sleep(TP_DT_INTERVAL_MS / 1000.0)
        
        print(f"BAM отправлен: {len(dtc_list)} ошибок, {total_packets} пакетов")
    
    def _send_tp_cm(self, total_bytes: int, total_packets: int):
        """Отправка TP.CM (Connection Management)"""
        # Формат BAM (8 байт):
        # Байт 0: 0x20 (BAM команда)
        # Байт 1-2: Общее количество байт данных (LSB, MSB)
        # Байт 3: Количество пакетов
        # Байт 4: 0xFF (резерв)
        # Байт 5-7: PGN (LSB, Middle, MSB)
        
        data = bytearray(8)
        data[0] = 0x20  # BAM
        data[1] = total_bytes & 0xFF
        data[2] = (total_bytes >> 8) & 0xFF
        data[3] = total_packets & 0xFF
        data[4] = 0xFF
        data[5] = J1939_PGN_DM1 & 0xFF
        data[6] = (J1939_PGN_DM1 >> 8) & 0xFF
        data[7] = (J1939_PGN_DM1 >> 16) & 0xFF
        
        # Формируем CAN ID: 0x18ECFF[SA] (PGN 0xECFF)
        can_id = build_can_id(J1939_PGN_TP_CM, self.current_sa)
        
        msg = can.Message(
            arbitration_id=can_id,
            data=bytes(data),
            is_extended_id=True,
            dlc=8
        )
        
        try:
            self.bus.send(msg)
            print(f"TP.CM: ID=0x{can_id:08X}, bytes={total_bytes}, packets={total_packets}")
        except Exception as e:
            print(f"Ошибка отправки TP.CM: {e}")
    
    def _send_tp_dt(self, packet_number: int, data: bytes):
        """Отправка TP.DT (Data Transfer)"""
        # Формат: байт 0 = номер пакета, байты 1-7 = данные
        packet_data = bytearray(8)
        packet_data[0] = packet_number & 0xFF
        
        for i, byte in enumerate(data[:7]):
            packet_data[i + 1] = byte
        
        # Если данных меньше 7, заполняем FF
        for i in range(len(data) + 1, 8):
            packet_data[i] = 0xFF
        
        # Формируем CAN ID: 0x18EBFF[SA] (PGN 0xEBFF)
        can_id = build_can_id(J1939_PGN_TP_DT, self.current_sa)
        
        msg = can.Message(
            arbitration_id=can_id,
            data=bytes(packet_data),
            is_extended_id=True,
            dlc=8
        )
        
        try:
            self.bus.send(msg)
        except Exception as e:
            print(f"Ошибка отправки TP.DT: {e}")


class DM1SimulatorGUI:
    """GUI приложения"""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("DM1 Simulator - PCAN")
        self.root.geometry("610x620")
        self.root.minsize(210, 220)
        self.root.resizable(True, True)
        
        self.simulator = DM1Simulator()
        
        # Переменные
        self.selected_channel = tk.StringVar()
        self.selected_sa = tk.StringVar(value="0x00")
        self.selected_bitrate = tk.StringVar(value="250000")
        self.spn_var = tk.StringVar(value="0")
        self.fmi_var = tk.StringVar(value="0")
        
        # Создаем интерфейс
        self.create_widgets()
        
        # Сканируем каналы
        self.scan_channels()
    
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
                                     values=["250000", "500000", "1000000"], width=8, state="readonly")
        bitrate_combo.pack(side=tk.LEFT, padx=5)
        
        self.connect_btn = ttk.Button(row1, text="Подключиться", command=self.toggle_connection, width=14)
        self.connect_btn.pack(side=tk.LEFT, padx=10)
        
        # === Секция SA ===
        sa_frame = ttk.LabelFrame(main_frame, text="Настройка SA", padding="10")
        sa_frame.pack(fill=tk.X, pady=5)
        
        row2 = ttk.Frame(sa_frame)
        row2.pack(fill=tk.X)
        
        ttk.Label(row2, text="SA (0x00-0xFF):").pack(side=tk.LEFT, padx=5)
        
        # Создаем список значений от 0x00 до 0xFF
        sa_values = [f"0x{i:02X}" for i in range(256)]
        self.sa_combo = ttk.Combobox(row2, textvariable=self.selected_sa, values=sa_values, width=8, state="readonly")
        self.sa_combo.pack(side=tk.LEFT, padx=5)
        self.sa_combo.set("0x00")
        
        ttk.Label(row2, text="Пример ID:").pack(side=tk.LEFT, padx=(20, 5))
        self.id_example_label = ttk.Label(row2, text="0x18FECA00", foreground="blue", font=("Courier", 10, "bold"))
        self.id_example_label.pack(side=tk.LEFT, padx=5)
        
        self.start_btn = ttk.Button(row2, text="Старт", command=self.toggle_sending, width=10)
        self.start_btn.pack(side=tk.LEFT, padx=10)
        self.start_btn.config(state=tk.DISABLED)
        
        self.status_label = ttk.Label(row2, text="● Остановлен", foreground="red")
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        # Привязываем событие изменения SA
        self.sa_combo.bind('<<ComboboxSelected>>', self.on_sa_changed)
        
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
        
        # === Секция списка ошибок ===
        list_frame = ttk.LabelFrame(main_frame, text="Список ошибок", padding="10")
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Frame для списка и кнопок
        list_container = ttk.Frame(list_frame)
        list_container.pack(fill=tk.BOTH, expand=True)
        
        # Список
        columns = ("#", "SPN", "FMI", "Данные (hex)")
        self.errors_tree = ttk.Treeview(list_container, columns=columns, show="headings", height=10)
        
        self.errors_tree.heading("#", text="#")
        self.errors_tree.heading("SPN", text="SPN")
        self.errors_tree.heading("FMI", text="FMI")
        self.errors_tree.heading("Данные (hex)", text="Данные (hex)")
        
        self.errors_tree.column("#", width=40, anchor=tk.CENTER)
        self.errors_tree.column("SPN", width=100, anchor=tk.CENTER)
        self.errors_tree.column("FMI", width=80, anchor=tk.CENTER)
        self.errors_tree.column("Данные (hex)", width=200, anchor=tk.CENTER)
        
        scrollbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.errors_tree.yview)
        self.errors_tree.configure(yscrollcommand=scrollbar.set)
        
        self.errors_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Кнопки управления списком
        btn_frame = ttk.Frame(list_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(btn_frame, text="Удалить выбранное", command=self.remove_selected_error, width=18).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Очистить список", command=self.clear_errors, width=18).pack(side=tk.LEFT, padx=5)
        
        # Информация
        info_frame = ttk.Frame(main_frame)
        info_frame.pack(fill=tk.X, pady=5)
        
        self.info_label = ttk.Label(info_frame, text="Ошибок: 0 | Режим: нет ошибок (SPN=0, FMI=0)", foreground="blue")
        self.info_label.pack(side=tk.LEFT)
        
        self.send_count_label = ttk.Label(info_frame, text="Отправлено: 0", foreground="green")
        self.send_count_label.pack(side=tk.RIGHT)
        
        self.send_count = 0
        
        # Статус бар
        self.status_bar = ttk.Label(self.root, text="Готов", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def scan_channels(self):
        """Сканирование доступных каналов"""
        channels = []
        try:
            configs = can.detect_available_configs(interfaces=['pcan'])
            for config in configs:
                channels.append(config['channel'])
        except Exception as e:
            print(f"Ошибка сканирования: {e}")
        
        if channels:
            self.channel_combo['values'] = channels
            self.selected_channel.set(channels[0])
        else:
            self.channel_combo['values'] = []
            self.status_bar.config(text="❌ Нет PCAN устройств")
    
    def toggle_connection(self):
        """Подключение/отключение"""
        if self.simulator.connected:
            self.disconnect()
        else:
            self.connect()
    
    def connect(self):
        """Подключение к CAN"""
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
        else:
            messagebox.showerror("Ошибка", "Не удалось подключиться")
    
    def disconnect(self):
        """Отключение от CAN"""
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
        """Изменение SA"""
        self.update_id_example()
        
        if self.simulator.connected:
            sa_str = self.selected_sa.get()
            if sa_str:
                sa = int(sa_str, 16)
                self.simulator.set_sa(sa)
                self.status_bar.config(text=f"SA: {sa_str}")
    
    def update_id_example(self):
        """Обновление примера CAN ID"""
        sa_str = self.selected_sa.get()
        if sa_str:
            sa = int(sa_str, 16)
            # Для DM1
            can_id = build_can_id(J1939_PGN_DM1, sa)
            self.id_example_label.config(text=f"0x{can_id:08X}")
    
    def toggle_sending(self):
        """Старт/стоп отправки"""
        if self.simulator.send_thread_running:
            self.stop_sending()
        else:
            self.start_sending()
    
    def start_sending(self):
        """Запуск отправки"""
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
            # Запускаем обновление счетчика
            self.update_send_count()
        else:
            messagebox.showerror("Ошибка", "Не удалось запустить отправку")
    
    def stop_sending(self):
        """Остановка отправки"""
        self.simulator.stop_sending()
        self.start_btn.config(text="Старт")
        self.status_label.config(text="● Остановлен", foreground="red")
        self.status_bar.config(text="Отправка остановлена")
    
    def update_send_count(self):
        """Обновление счетчика отправленных сообщений"""
        if self.simulator.send_thread_running:
            self.send_count += 1
            self.send_count_label.config(text=f"Отправлено: {self.send_count}")
            self.root.after(1000, self.update_send_count)
    
    def add_error(self):
        """Добавление ошибки в список"""
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
        
        if self.simulator.add_dtc(spn, fmi):
            self.update_error_list()
            self.spn_var.set("0")
            self.fmi_var.set("0")
            self.status_bar.config(text=f"✅ Добавлена ошибка SPN={spn}, FMI={fmi}")
        else:
            messagebox.showinfo("Информация", f"Ошибка SPN={spn}, FMI={fmi} уже существует")
    
    def remove_selected_error(self):
        """Удаление выбранной ошибки"""
        selected = self.errors_tree.selection()
        if not selected:
            messagebox.showinfo("Информация", "Выберите ошибку для удаления")
            return
        
        # Получаем индекс
        item = selected[0]
        index = self.errors_tree.index(item)
        
        if self.simulator.remove_dtc(index):
            self.update_error_list()
            self.status_bar.config(text=f"✅ Ошибка удалена")
    
    def clear_errors(self):
        """Очистка списка ошибок"""
        if self.simulator.dtc_list:
            self.simulator.clear_dtc()
            self.update_error_list()
            self.status_bar.config(text="🧹 Список ошибок очищен")
    
    def update_error_list(self):
        """Обновление списка ошибок в UI"""
        # Очищаем дерево
        for item in self.errors_tree.get_children():
            self.errors_tree.delete(item)
        
        # Добавляем ошибки
        with self.simulator.lock:
            dtc_list = self.simulator.dtc_list.copy()
        
        for idx, dtc in enumerate(dtc_list, 1):
            # Формируем hex данные
            dtc_bytes = DTC(spn=dtc.spn, fmi=dtc.fmi).to_bytes()
            hex_str = ' '.join([f'{b:02X}' for b in dtc_bytes])
            self.errors_tree.insert("", tk.END, values=(idx, dtc.spn, dtc.fmi, hex_str))
        
        # Обновляем информацию
        count = len(dtc_list)
        if count == 0:
            mode = "нет ошибок (SPN=0, FMI=0)"
        elif count == 1:
            mode = "одиночное сообщение"
        else:
            total_bytes = 2 + count * 4
            total_packets = (total_bytes + 6) // 7
            mode = f"BAM ({count} ошибок, {total_packets} пакетов)"
        
        self.info_label.config(text=f"Ошибок: {count} | Режим: {mode}")
    
    def on_closing(self):
        """Закрытие окна"""
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