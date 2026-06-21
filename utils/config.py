"""Работа с конфигурацией"""

import json
import os

CONFIG_FILE = "config.json"


class ConfigManager:
    """Менеджер конфигурации"""
    
    @staticmethod
    def load_config() -> dict:
        """Загрузка конфигурации из файла"""
        default_config = {
            "window_geometry": "610x800+100+50",
            "last_channel": "",
            "last_sa": "0x00",
            "last_bitrate": "250000"
        }
        
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # Обновляем дефолтные значения
                    for key in default_config:
                        if key not in config:
                            config[key] = default_config[key]
                    return config
            except Exception:
                return default_config
        return default_config
    
    @staticmethod
    def save_config(config: dict):
        """Сохранение конфигурации в файл"""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения конфигурации: {e}")