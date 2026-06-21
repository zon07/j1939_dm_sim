# gui_widgets.py
"""Виджеты для GUI DM1 симулятора"""

import tkinter as tk
from tkinter import ttk
from typing import Dict, Callable


class LampBitCheckboxes:
    """Виджет для управления лампами через чекбоксы (по 2 бита на лампу)"""
    
    def __init__(self, parent, lamp_vars: Dict[str, tk.StringVar], callback: Callable):
        self.parent = parent
        self.lamp_vars = lamp_vars
        self.callback = callback
        self.checkboxes = {}
        
        self._create_widgets()
    
    def _create_widgets(self):
        # Байт 0 (L - Status)
        byte0_frame = ttk.LabelFrame(self.parent, text="Байт 1 (L - Status)", padding="5")
        byte0_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        
        lamps_byte0 = [
            ('MIL_L', 'MIL'),
            ('RSL_L', 'RSL'),
            ('AWL_L', 'AWL'),
            ('PL_L', 'PL')
        ]
        
        for idx, (lamp_name, label) in enumerate(lamps_byte0):
            frame = ttk.Frame(byte0_frame)
            frame.pack(fill=tk.X, pady=2)
            
            ttk.Label(frame, text=f"{label}:", width=6).pack(side=tk.LEFT)
            
            # Два чекбокса для двух бит
            var1 = tk.BooleanVar(value=self._get_bit_value(lamp_name, 1))
            var2 = tk.BooleanVar(value=self._get_bit_value(lamp_name, 0))
            
            cb1 = ttk.Checkbutton(frame, variable=var1, text="Бит 1", 
                                 command=lambda n=lamp_name, v=var1, pos=1: self._on_checkbox_change(n, v, pos))
            cb1.pack(side=tk.LEFT, padx=2)
            
            cb2 = ttk.Checkbutton(frame, variable=var2, text="Бит 0", 
                                 command=lambda n=lamp_name, v=var2, pos=0: self._on_checkbox_change(n, v, pos))
            cb2.pack(side=tk.LEFT, padx=2)
            
            self.checkboxes[lamp_name] = (var1, var2)
        
        # Байт 1 (F - Flash)
        byte1_frame = ttk.LabelFrame(self.parent, text="Байт 2 (F - Flash)", padding="5")
        byte1_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        
        lamps_byte1 = [
            ('MIL_F', 'MIL'),
            ('RSL_F', 'RSL'),
            ('AWL_F', 'AWL'),
            ('PL_F', 'PL')
        ]
        
        for idx, (lamp_name, label) in enumerate(lamps_byte1):
            frame = ttk.Frame(byte1_frame)
            frame.pack(fill=tk.X, pady=2)
            
            ttk.Label(frame, text=f"{label}:", width=6).pack(side=tk.LEFT)
            
            var1 = tk.BooleanVar(value=self._get_bit_value(lamp_name, 1))
            var2 = tk.BooleanVar(value=self._get_bit_value(lamp_name, 0))
            
            cb1 = ttk.Checkbutton(frame, variable=var1, text="Бит 1",
                                 command=lambda n=lamp_name, v=var1, pos=1: self._on_checkbox_change(n, v, pos))
            cb1.pack(side=tk.LEFT, padx=2)
            
            cb2 = ttk.Checkbutton(frame, variable=var2, text="Бит 0",
                                 command=lambda n=lamp_name, v=var2, pos=0: self._on_checkbox_change(n, v, pos))
            cb2.pack(side=tk.LEFT, padx=2)
            
            self.checkboxes[lamp_name] = (var1, var2)
    
    def _get_bit_value(self, lamp_name: str, bit_pos: int) -> bool:
        """Получить значение бита для лампы"""
        value_str = self.lamp_vars[lamp_name].get()
        if value_str.startswith("0b"):
            value = int(value_str[2:], 2)
        else:
            try:
                value = int(value_str)
            except ValueError:
                value = 3
        return bool((value >> bit_pos) & 1)
    
    def _on_checkbox_change(self, lamp_name: str, var: tk.BooleanVar, bit_pos: int):
        """Обработчик изменения чекбокса"""
        value_str = self.lamp_vars[lamp_name].get()
        if value_str.startswith("0b"):
            value = int(value_str[2:], 2)
        else:
            try:
                value = int(value_str)
            except ValueError:
                value = 3
        
        if var.get():
            value |= (1 << bit_pos)
        else:
            value &= ~(1 << bit_pos)
        
        self.lamp_vars[lamp_name].set(f"0b{value:02b}")
        self.callback()
    
    def update_checkboxes_from_values(self):
        """Обновить состояние чекбоксов из текущих значений lamp_vars"""
        for lamp_name in self.lamp_vars:
            var1, var2 = self.checkboxes[lamp_name]
            value_str = self.lamp_vars[lamp_name].get()
            if value_str.startswith("0b"):
                value = int(value_str[2:], 2)
            else:
                try:
                    value = int(value_str)
                except ValueError:
                    value = 3
            var1.set(bool((value >> 1) & 1))
            var2.set(bool((value >> 0) & 1))