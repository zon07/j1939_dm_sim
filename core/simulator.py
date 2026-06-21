# simulator.py
"""Имитатор ошибок DM1 для PCAN"""

import can
import can.interfaces.pcan
import time
import threading
import json
import os
from typing import List, Optional, Dict, Tuple
from dataclasses import asdict

from core.dtc import DTC


# Конфигурация
J1939_PGN_DM1 = 0xFECA
J1939_PGN_TP_CM = 0xECFF
J1939_PGN_TP_DT = 0xEBFF
J1939_PRIORITY = 6
CAN_SEND_INTERVAL_MS = 1000
TP_DT_INTERVAL_MS = 200
DEFAULT_SAVE_FILE = "dtc_list.json"
CONFIG_FILE = "config.json"


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
    
    def add_dtc(self, spn: int, fmi: int) -> Tuple[bool, str]:
        with self.lock:
            if len(self.dtc_list) >= 445:
                return False, "Достигнут максимум ошибок (445)"
            
            for dtc in self.dtc_list:
                if dtc.spn == spn and dtc.fmi == fmi:
                    return False, f"Ошибка SPN={spn}, FMI={fmi} уже существует"
            
            self.dtc_list.append(DTC(spn=spn, fmi=fmi))
            # Сортируем список после добавления
            self._sort_dtc_list()
            return True, "OK"
    
    def _sort_dtc_list(self):
        """Сортировка списка ошибок по SPN, затем по FMI"""
        self.dtc_list.sort(key=lambda x: (x.spn, x.fmi))
    
    def remove_dtc(self, index: int) -> bool:
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
    
    def toggle_dtc_enabled(self, index: int) -> bool:
        """Включить/выключить конкретную ошибку"""
        with self.lock:
            if 0 <= index < len(self.dtc_list):
                self.dtc_list[index].enabled = not self.dtc_list[index].enabled
                return True
            return False
    
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
            # Берем только включенные ошибки
            dtc_list = [dtc for dtc in self.dtc_list if dtc.enabled]
        
        if not self.errors_enabled or not dtc_list:
            # Пустое сообщение - лампы фиксированные 0x00, 0xFF
            self._send_dm1_single(0, 0, empty=True)
        elif len(dtc_list) == 1:
            dtc = dtc_list[0]
            # Если это реальная ошибка SPN=0, FMI=0 - лампы из чекбоксов
            self._send_dm1_single(dtc.spn, dtc.fmi, empty=False)
        else:
            self._send_dm1_bam(dtc_list)
    
    def _send_dm1_single(self, spn: int, fmi: int, empty: bool = False):
        if not self.bus:
            return
        
        lamp_byte0, lamp_byte1 = self.get_lamp_bytes()
        
        # Только для пустого сообщения (нет ошибок) - фиксированные лампы
        if empty:
            lamp_byte0 = 0x00
            lamp_byte1 = 0x00
        
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
    
    def auto_save(self):
        """Автоматическое сохранение в DEFAULT_SAVE_FILE"""
        if self.save_to_file(DEFAULT_SAVE_FILE):
            # Не выводить сообщение, чтобы не засорять статусбар
            pass
        else:
            print(f"⚠️ Ошибка автосохранения в {DEFAULT_SAVE_FILE}")

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
                # Сортируем после загрузки
                self._sort_dtc_list()
            return True
        except Exception as e:
            print(f"Ошибка загрузки: {e}")
            return False
