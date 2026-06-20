# dm1_simulator.py
"""Имитатор ошибок DM1 для PCAN"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import can
import time
import threading
import json
import os
from dataclasses import dataclass, asdict
from typing import List, Optional

# Версия программы
VERSION = "1.0.0"

# Конфигурация
J1939_PGN_DM1 = 0xFECA
J1939_PGN_TP_CM = 0xECFF
J1939_PGN_TP_DT = 0xEBFF
J1939_PRIORITY = 6
CAN_SEND_INTERVAL_MS = 1000
TP_DT_INTERVAL_MS = 200
DEFAULT_SAVE_FILE = "dtc_list.json"


@dataclass
class DTC:
    """Diagnostic Trouble Code"""
    spn: int
    fmi: int
    
    def to_bytes(self) -> bytes:
        """Преобразование в 4 байта DM1"""
        spn_lsb = self.spn & 0xFF
        spn_mid = (self.spn >> 8) & 0xFF
        spn_msb = (self.spn >> 16) & 0x07
        fmi_byte = (spn_msb << 5) | (self.fmi & 0x1F)
        return bytes([spn_lsb, spn_mid, fmi_byte, 0xFF])
    
    def to_dict(self) -> dict:
        return {"spn": self.spn, "fmi": self.fmi}
    
    @classmethod
    def from_dict(cls, data: dict) -> 'DTC':
        return cls(spn=data["spn"], fmi=data["fmi"])


def build_can_id(pgn: int, sa: int) -> int:
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
        self.errors_enabled = True
        
        # Лампочки (первые 2 байта DM1)
        self.lamp_status = {
            'MIL_L': 3,
            'RSL_L': 3,
            'AWL_L': 3,
            'PL_L': 3,
            'MIL_F': 3,
            'RSL_F': 3,
            'AWL_F': 3,
            'PL_F': 3
        }
    
    def set_lamp_value(self, lamp_name: str, value: int):
        if lamp_name in self.lamp_status and 0 <= value <= 3:
            self.lamp_status[lamp_name] = value
    
    def get_lamp_bytes(self) -> tuple:
        byte0 = 0
        byte0 |= (self.lamp_status['MIL_L'] & 0x03) << 6
        byte0 |= (self.lamp_status['RSL_L'] & 0x03) << 4
        byte0 |= (self.lamp_status['AWL_L'] & 0x03) << 2
        byte0 |= (self.lamp_status['PL_L'] & 0x03) << 0
        
        byte1 = 0
        byte1 |= (self.lamp_status['MIL_F'] & 0x03) << 6
        byte1 |= (self.lamp_status['RSL_F'] & 0x03) << 4
        byte1 |= (self.lamp_status['AWL_F'] & 0x03) << 2
        byte1 |= (self.lamp_status['PL_F'] & 0x03) << 0
        
        return byte0, byte1
    
    def set_lamp_status_from_dict(self, lamp_data: dict):
        """Установка значений лампочек из словаря"""
        for key, value in lamp_data.items():
            if key in self.lamp_status and 0 <= value <= 3:
                self.lamp_status[key] = value
    
    def connect(self, channel: str, bitrate: int) -> bool:
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
        self.current_sa = sa
    
    def set_dtc_list(self, dtc_list: List[DTC]):
        with self.lock:
            self.dtc_list = dtc_list.copy()
    
    def add_dtc(self, spn: int, fmi: int):
        with self.lock:
            if len(self.dtc_list) >= 445:
                return False, "Достигнут максимум ошибок (445)"
            
            for dtc in self.dtc_list:
                if dtc.spn == spn and dtc.fmi == fmi:
                    return False, f"Ошибка SPN={spn}, FMI={fmi} уже существует"
            
            self.dtc_list.append(DTC(spn=spn, fmi=fmi))
            return True, "OK"
    
    def remove_dtc(self, index: int):
        with self.lock:
            if 0 <= index < len(self.dtc_list):
                del self.dtc_list[index]
                return True
            return False
    
    def clear_dtc(self):
        with self.lock:
            self.dtc_list.clear()
    
    def set_errors_enabled(self, enabled: bool):
        self.errors_enabled = enabled
    
    def start_sending(self):
        if not self.connected or self.current_sa is None:
            return False
        
        if self.send_thread_running:
            return True
        
        self.send_thread_running = True
        self.send_thread = threading.Thread(target=self._send_loop, daemon=True)
        self.send_thread.start()
        return True
    
    def stop_sending(self):
        self.send_thread_running = False
    
    def _send_loop(self):
        while self.send_thread_running and self.connected:
            start_time = time.time()
            
            try:
                self._send_current_dm1()
            except Exception as e:
                print(f"Ошибка отправки: {e}")
            
            elapsed = time.time() - start_time
            sleep_time = max(0, CAN_SEND_INTERVAL_MS / 1000.0 - elapsed)
            if sleep_time > 0 and self.send_thread_running:
                time.sleep(sleep_time)
    
    def _send_current_dm1(self):
        with self.lock:
            dtc_list = self.dtc_list.copy()
        
        if not self.errors_enabled or not dtc_list:
            self._send_dm1_single(0, 0)
        elif len(dtc_list) == 1:
            dtc = dtc_list[0]
            self._send_dm1_single(dtc.spn, dtc.fmi)
        else:
            self._send_dm1_bam(dtc_list)
    
    def _send_dm1_single(self, spn: int, fmi: int):
        if not self.bus:
            return
        
        lamp_byte0, lamp_byte1 = self.get_lamp_bytes()
        
        # Если SPN=0 и FMI=0, то байт 0 = 0x00, байт 1 = 0xFF
        if spn == 0 and fmi == 0:
            lamp_byte0 = 0x00
            lamp_byte1 = 0xFF
        
        spn_lsb = spn & 0xFF
        spn_mid = (spn >> 8) & 0xFF
        spn_msb = (spn >> 16) & 0x07
        fmi_byte = (spn_msb << 5) | (fmi & 0x1F)
        
        data = bytearray(8)
        data[0] = lamp_byte0
        data[1] = lamp_byte1
        data[2] = spn_lsb
        data[3] = spn_mid
        data[4] = fmi_byte
        data[5] = 0xFF
        data[6] = 0xFF
        data[7] = 0xFF
        
        can_id = build_can_id(J1939_PGN_DM1, self.current_sa)
        
        msg = can.Message(
            arbitration_id=can_id,
            data=bytes(data),
            is_extended_id=True,
            dlc=8
        )
        
        try:
            self.bus.send(msg)
            print(f"DM1: ID=0x{can_id:08X}, SPN={spn}, FMI={fmi}, Lamps=0x{lamp_byte0:02X}{lamp_byte1:02X}")
        except Exception as e:
            print(f"Ошибка отправки DM1: {e}")
    
    def _send_dm1_bam(self, dtc_list: List[DTC]):
        if not self.bus:
            return
        
        lamp_byte0, lamp_byte1 = self.get_lamp_bytes()
        
        data = bytearray(2)
        data[0] = lamp_byte0
        data[1] = lamp_byte1
        
        for dtc in dtc_list:
            data.extend(dtc.to_bytes())
        
        if len(data) > 1785:
            data = data[:1785]
            print(f"⚠️ Данные обрезаны до 1785 байт")
        
        total_bytes = len(data)
        total_packets = (total_bytes + 6) // 7
        
        self._send_tp_cm(total_bytes, total_packets)
        
        packet_number = 1
        for i in range(0, total_bytes, 7):
            chunk = data[i:i+7]
            self._send_tp_dt(packet_number, chunk)
            packet_number += 1
            if i + 7 < total_bytes:
                time.sleep(TP_DT_INTERVAL_MS / 1000.0)
        
        print(f"BAM отправлен: {len(dtc_list)} ошибок, {total_packets} пакетов")
    
    def _send_tp_cm(self, total_bytes: int, total_packets: int):
        data = bytearray(8)
        data[0] = 0x20
        data[1] = total_bytes & 0xFF
        data[2] = (total_bytes >> 8) & 0xFF
        data[3] = total_packets & 0xFF
        data[4] = 0xFF
        data[5] = J1939_PGN_DM1 & 0xFF
        data[6] = (J1939_PGN_DM1 >> 8) & 0xFF
        data[7] = (J1939_PGN_DM1 >> 16) & 0xFF
        
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
        packet_data = bytearray(8)
        packet_data[0] = packet_number & 0xFF
        
        for i, byte in enumerate(data[:7]):
            packet_data[i + 1] = byte
        
        for i in range(len(data) + 1, 8):
            packet_data[i] = 0xFF
        
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
    
    def save_to_file(self, filename: str) -> bool:
        """Сохранение списка ошибок и настроек лампочек в файл JSON"""
        try:
            with self.lock:
                data = {
                    "dtc_list": [dtc.to_dict() for dtc in self.dtc_list],
                    "errors_enabled": self.errors_enabled,
                    "lamp_status": self.lamp_status.copy()
                }
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Ошибка сохранения: {e}")
            return False
    
    def load_from_file(self, filename: str) -> bool:
        """Загрузка списка ошибок и настроек лампочек из файла JSON"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            with self.lock:
                self.dtc_list = [DTC.from_dict(dtc) for dtc in data.get("dtc_list", [])]
                self.errors_enabled = data.get("errors_enabled", True)
                if "lamp_status" in data:
                    self.set_lamp_status_from_dict(data["lamp_status"])
            return True
        except Exception as e:
            print(f"Ошибка загрузки: {e}")
            return False


class DM1SimulatorGUI:
    """GUI приложения"""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"DM1 Simulator - PCAN v{VERSION}")
        self.root.geometry("650x850")
        self.root.minsize(250, 280)
        self.root.resizable(True, True)
        
        self.simulator = DM1Simulator()
        
        # Переменные
        self.selected_channel = tk.StringVar()
        self.selected_sa = tk.StringVar(value="0x00")
        self.selected_bitrate = tk.StringVar(value="250000")
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
        
        self.create_widgets()
        self.scan_channels()
        self.load_default_file()
    
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
        self.sa_combo.set("0x00")
        
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
        
        # Заголовки с правильным выравниванием
        header_frame = ttk.Frame(lamps_frame)
        header_frame.pack(fill=tk.X, pady=(0, 5))
        
        # Левая часть (Байт 0) - отступ для выравнивания с комбобоксами
        left_header = ttk.Frame(header_frame)
        left_header.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(left_header, text="Байт 0 (L - Status)", font=("", 10, "bold"), foreground="blue").pack(anchor=tk.W, padx=(12, 0))
        
        # Правая часть (Байт 1) - отступ для выравнивания с комбобоксами
        right_header = ttk.Frame(header_frame)
        right_header.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(right_header, text="Байт 1 (F - Flash)", font=("", 10, "bold"), foreground="blue").pack(anchor=tk.W, padx=(12, 0))
        
        # Строка 1: MIL
        lamp_row1 = ttk.Frame(lamps_frame)
        lamp_row1.pack(fill=tk.X, pady=2)
        
        # Левая часть (Байт 0)
        left_frame = ttk.Frame(lamp_row1)
        left_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ttk.Label(left_frame, text="MIL_L (6-7):", width=12).pack(side=tk.LEFT)
        mil_l_combo = ttk.Combobox(left_frame, textvariable=self.lamp_vars['MIL_L'], 
                                values=["0b00", "0b01", "0b10", "0b11"], width=5, state="readonly")
        mil_l_combo.pack(side=tk.LEFT, padx=2)
        mil_l_combo.bind('<<ComboboxSelected>>', self.on_lamp_changed)
        mil_l_combo.set("0b11")  # Устанавливаем начальное значение
        
        ttk.Label(left_frame, text="RSL_L (4-5):", width=12).pack(side=tk.LEFT, padx=(10, 2))
        rsl_l_combo = ttk.Combobox(left_frame, textvariable=self.lamp_vars['RSL_L'], 
                                values=["0b00", "0b01", "0b10", "0b11"], width=5, state="readonly")
        rsl_l_combo.pack(side=tk.LEFT, padx=2)
        rsl_l_combo.bind('<<ComboboxSelected>>', self.on_lamp_changed)
        rsl_l_combo.set("0b11")  # Устанавливаем начальное значение
        
        # Правая часть (Байт 1)
        right_frame = ttk.Frame(lamp_row1)
        right_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ttk.Label(right_frame, text="MIL_F (6-7):", width=12).pack(side=tk.LEFT)
        mil_f_combo = ttk.Combobox(right_frame, textvariable=self.lamp_vars['MIL_F'], 
                                values=["0b00", "0b01", "0b10", "0b11"], width=5, state="readonly")
        mil_f_combo.pack(side=tk.LEFT, padx=2)
        mil_f_combo.bind('<<ComboboxSelected>>', self.on_lamp_changed)
        mil_f_combo.set("0b11")  # Устанавливаем начальное значение
        
        ttk.Label(right_frame, text="RSL_F (4-5):", width=12).pack(side=tk.LEFT, padx=(10, 2))
        rsl_f_combo = ttk.Combobox(right_frame, textvariable=self.lamp_vars['RSL_F'], 
                                values=["0b00", "0b01", "0b10", "0b11"], width=5, state="readonly")
        rsl_f_combo.pack(side=tk.LEFT, padx=2)
        rsl_f_combo.bind('<<ComboboxSelected>>', self.on_lamp_changed)
        rsl_f_combo.set("0b11")  # Устанавливаем начальное значение
        
        # Строка 2: AWL и PL
        lamp_row2 = ttk.Frame(lamps_frame)
        lamp_row2.pack(fill=tk.X, pady=2)
        
        # Левая часть (Байт 0)
        left_frame2 = ttk.Frame(lamp_row2)
        left_frame2.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ttk.Label(left_frame2, text="AWL_L (2-3):", width=12).pack(side=tk.LEFT)
        awl_l_combo = ttk.Combobox(left_frame2, textvariable=self.lamp_vars['AWL_L'], 
                                values=["0b00", "0b01", "0b10", "0b11"], width=5, state="readonly")
        awl_l_combo.pack(side=tk.LEFT, padx=2)
        awl_l_combo.bind('<<ComboboxSelected>>', self.on_lamp_changed)
        awl_l_combo.set("0b11")  # Устанавливаем начальное значение
        
        ttk.Label(left_frame2, text="PL_L (0-1):", width=12).pack(side=tk.LEFT, padx=(10, 2))
        pl_l_combo = ttk.Combobox(left_frame2, textvariable=self.lamp_vars['PL_L'], 
                                values=["0b00", "0b01", "0b10", "0b11"], width=5, state="readonly")
        pl_l_combo.pack(side=tk.LEFT, padx=2)
        pl_l_combo.bind('<<ComboboxSelected>>', self.on_lamp_changed)
        pl_l_combo.set("0b11")  # Устанавливаем начальное значение
        
        # Правая часть (Байт 1)
        right_frame2 = ttk.Frame(lamp_row2)
        right_frame2.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ttk.Label(right_frame2, text="AWL_F (2-3):", width=12).pack(side=tk.LEFT)
        awl_f_combo = ttk.Combobox(right_frame2, textvariable=self.lamp_vars['AWL_F'], 
                                values=["0b00", "0b01", "0b10", "0b11"], width=5, state="readonly")
        awl_f_combo.pack(side=tk.LEFT, padx=2)
        awl_f_combo.bind('<<ComboboxSelected>>', self.on_lamp_changed)
        awl_f_combo.set("0b11")  # Устанавливаем начальное значение
        
        ttk.Label(right_frame2, text="PL_F (0-1):", width=12).pack(side=tk.LEFT, padx=(10, 2))
        pl_f_combo = ttk.Combobox(right_frame2, textvariable=self.lamp_vars['PL_F'], 
                                values=["0b00", "0b01", "0b10", "0b11"], width=5, state="readonly")
        pl_f_combo.pack(side=tk.LEFT, padx=2)
        pl_f_combo.bind('<<ComboboxSelected>>', self.on_lamp_changed)
        pl_f_combo.set("0b11")  # Устанавливаем начальное значение
        
        # Отображение текущих байтов лампочек
        lamp_preview_frame = ttk.Frame(lamps_frame)
        lamp_preview_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Label(lamp_preview_frame, text="Текущие байты:").pack(side=tk.LEFT, padx=5)
        self.lamp_preview_label = ttk.Label(lamp_preview_frame, text="Байт0: 0xFF  Байт1: 0xFF", 
                                            font=("Courier", 10, "bold"), foreground="darkblue")
        self.lamp_preview_label.pack(side=tk.LEFT, padx=10)
        
        ttk.Button(lamp_preview_frame, text="Сбросить в FF", command=self.reset_lamps).pack(side=tk.RIGHT, padx=5)
        
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
        
        columns = ("#", "SPN", "FMI", "Данные (hex)")
        self.errors_tree = ttk.Treeview(list_container, columns=columns, show="headings", height=8)
        
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
        
        btn_frame = ttk.Frame(list_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(btn_frame, text="Удалить", command=self.remove_selected_error, width=15).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Очистить", command=self.clear_errors, width=15).pack(side=tk.LEFT, padx=2)
        
        self.errors_enabled_var = tk.BooleanVar(value=True)
        self.errors_toggle_btn = ttk.Button(btn_frame, text="Выключить", 
                                            command=self.toggle_errors_enabled, width=15)
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
        """Сброс всех лампочек в значение 3 (FF)"""
        for key in self.lamp_vars:
            self.lamp_vars[key].set("0b11")  # Изменено с "3" на "0b11"
        self.update_lamp_values()
        self.update_lamp_preview()
        self.status_bar.config(text="✅ Лампочки сброшены в FF")
    
    def on_lamp_changed(self, event=None):
        self.update_lamp_values()
        self.update_lamp_preview()
    
    def update_lamp_values(self):
        for key, var in self.lamp_vars.items():
            value_str = var.get()
            if value_str:
                # Парсим значение из "0bXX" формата
                if value_str.startswith("0b"):
                    value = int(value_str[2:], 2)  # Преобразуем бинарную строку в число
                else:
                    # Если вдруг сохранился старый формат
                    try:
                        value = int(value_str)
                    except ValueError:
                        value = 3  # Значение по умолчанию
                self.simulator.set_lamp_value(key, value)
    
    def update_lamp_preview(self):
        self.update_lamp_values()
        byte0, byte1 = self.simulator.get_lamp_bytes()
        self.lamp_preview_label.config(text=f"Байт0: 0x{byte0:02X}  Байт1: 0x{byte1:02X}")
    
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
                # Преобразуем числа в строки с префиксом "0b"
                for key, value in self.simulator.lamp_status.items():
                    # value: 0 -> "0b00", 1 -> "0b01", 2 -> "0b10", 3 -> "0b11"
                    binary_str = f"0b{value:02b}"
                    self.lamp_vars[key].set(binary_str)
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
                self.update_lamp_preview()
                self.update_error_list()
                self.update_errors_status()
                self.update_send_mode_info()
                self.status_bar.config(text=f"📂 Загружен список из {DEFAULT_SAVE_FILE}")
    
    def update_send_mode_info(self):
        with self.simulator.lock:
            dtc_list = self.simulator.dtc_list.copy()
            errors_enabled = self.simulator.errors_enabled
        
        count = len(dtc_list)
        
        if not errors_enabled:
            mode = "🔴 СПИСОК ВЫКЛЮЧЕН - отправляется нулевое сообщение"
        elif count == 0:
            mode = "нет ошибок (SPN=0, FMI=0)"
        elif count == 1:
            mode = "одиночное сообщение"
        else:
            total_bytes = 2 + count * 4
            total_packets = (total_bytes + 6) // 7
            mode = f"BAM ({count} ошибок, {total_packets} пакетов)"
        
        self.info_label.config(text=f"Ошибок: {count} | Режим: {mode}")
        
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
        else:
            messagebox.showerror("Ошибка", "Не удалось запустить отправку")
    
    def stop_sending(self):
        self.simulator.stop_sending()
        self.start_btn.config(text="Старт")
        self.status_label.config(text="● Остановлен", foreground="red")
        self.status_bar.config(text="Отправка остановлена")
    
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
        for item in self.errors_tree.get_children():
            self.errors_tree.delete(item)
        
        with self.simulator.lock:
            dtc_list = self.simulator.dtc_list.copy()
            errors_enabled = self.simulator.errors_enabled
        
        for idx, dtc in enumerate(dtc_list, 1):
            dtc_bytes = DTC(spn=dtc.spn, fmi=dtc.fmi).to_bytes()
            hex_str = ' '.join([f'{b:02X}' for b in dtc_bytes])
            self.errors_tree.insert("", tk.END, values=(idx, dtc.spn, dtc.fmi, hex_str))
        
        self.update_send_mode_info()
        self.update_errors_status()
    
    def on_closing(self):
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