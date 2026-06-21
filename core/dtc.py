# dtc.py
"""Модели данных для DM1 симулятора"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple


@dataclass
class DTC:
    """Diagnostic Trouble Code"""
    spn: int
    fmi: int
    enabled: bool = True  # Флаг включения/отключения ошибки
    
    def to_bytes(self) -> bytes:
        """Преобразование в 4 байта DM1"""
        spn_lsb = self.spn & 0xFF
        spn_mid = (self.spn >> 8) & 0xFF
        spn_msb = (self.spn >> 16) & 0x07
        fmi_byte = (spn_msb << 5) | (self.fmi & 0x1F)
        return bytes([spn_lsb, spn_mid, fmi_byte, 0xFF])
    
    def to_dict(self) -> dict:
        return {"spn": self.spn, "fmi": self.fmi, "enabled": self.enabled}
    
    @classmethod
    def from_dict(cls, data: dict) -> 'DTC':
        return cls(
            spn=data["spn"], 
            fmi=data["fmi"],
            enabled=data.get("enabled", True)  # Обратная совместимость
        )