#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Serial Authentication Module for TTS Master
- Connects to Render server (aimaster-serial.onrender.com)
- Collects cross-platform hardware information (Windows & macOS)
- Handles caching and offline grace periods
"""

import os
import sys
import json
import base64
import socket
import platform
import subprocess
import logging
from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict, Any
import requests

class SerialAuth:
    """Manages serial validation against the Render license server."""
    
    SERVER_URL = "https://aimaster-serial.onrender.com"
    
    def __init__(self):
        self.config_dir = self._get_config_dir()
        os.makedirs(self.config_dir, exist_ok=True)
        self.config_file = os.path.join(self.config_dir, "serial_config.json")
        self.log_file = os.path.join(self.config_dir, "serial_auth.log")
        self._setup_logging()
        
    def _get_config_dir(self) -> str:
        """Returns standard application config directory based on OS."""
        if platform.system() == "Windows":
            base = os.environ.get("APPDATA", os.path.expanduser("~"))
            return os.path.join(base, "AIMaster_TTS")
        else:
            return os.path.join(os.path.expanduser("~"), ".aimaster_tts")
            
    def _setup_logging(self):
        self.logger = logging.getLogger("SerialAuth")
        if not self.logger.handlers:
            self.logger.setLevel(logging.INFO)
            handler = logging.FileHandler(self.log_file, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
            self.logger.addHandler(handler)
            
    def get_device_info(self) -> Dict[str, Any]:
        """Collects cross-platform device hardware and OS info."""
        device_info = {
            "hostname": "unknown",
            "ip_address": "0.0.0.0",
            "os_name": platform.system(),
            "os_version": platform.version(),
            "processor": platform.processor() or "Unknown",
            "registration_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        try:
            hostname = socket.gethostname()
            device_info["hostname"] = hostname
            device_info["ip_address"] = socket.gethostbyname(hostname)
        except Exception:
            pass
            
        system = platform.system()
        if system == "Darwin":  # macOS
            device_info["system_manufacturer"] = "Apple"
            try:
                model = subprocess.check_output(["sysctl", "-n", "hw.model"], timeout=2).decode("utf-8").strip()
                device_info["system_model"] = model
            except Exception:
                device_info["system_model"] = "Mac"
            try:
                proc = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], timeout=2).decode("utf-8").strip()
                device_info["processor"] = proc
            except Exception:
                pass
            try:
                mem_bytes = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], timeout=2).strip())
                device_info["total_memory"] = f"{mem_bytes / (1024**3):.2f}GB"
            except Exception:
                device_info["total_memory"] = "8.00GB"
        elif system == "Windows":
            device_info["system_manufacturer"] = "PC"
            device_info["system_model"] = "Windows PC"
            try:
                import psutil
                memory = psutil.virtual_memory()
                device_info["total_memory"] = f"{memory.total / (1024**3):.2f}GB"
            except Exception:
                device_info["total_memory"] = "8.00GB"
                
        return device_info

    def _obfuscate(self, text: str) -> str:
        """Simple obfuscation for storing sensitive license strings."""
        if not text:
            return ""
        return base64.b64encode(text.encode("utf-8")).decode("ascii")

    def _deobfuscate(self, text: str) -> str:
        """Decodes obfuscated string."""
        if not text:
            return ""
        try:
            return base64.b64decode(text.encode("ascii")).decode("utf-8")
        except Exception:
            return text

    def load_config(self) -> Dict[str, Any]:
        """Loads cached serial configuration."""
        default_config = {
            "serial_number": "",
            "last_validation": "",
            "expiry_date": "",
            "status": ""
        }
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "serial_number" in data:
                        data["serial_number"] = self._deobfuscate(data["serial_number"])
                    return {**default_config, **data}
            except Exception as e:
                self.logger.error(f"Failed to load config: {e}")
        return default_config

    def save_config(self, serial: str, status: str = "", expiry_date: str = ""):
        """Saves serial configuration with obfuscation."""
        try:
            data = {
                "serial_number": self._obfuscate(serial),
                "last_validation": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": status,
                "expiry_date": expiry_date
            }
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save config: {e}")

    def clear_config(self):
        """Clears cached serial."""
        try:
            if os.path.exists(self.config_file):
                os.remove(self.config_file)
        except Exception as e:
            self.logger.error(f"Failed to clear config: {e}")

    def validate(self, serial_number: str) -> Tuple[bool, str, Optional[str]]:
        """
        Validates serial against Render server (/api/validate).
        Retries up to 3 times to handle Render free-tier cold boot sleep.
        Returns: (is_valid, message, expiry_date)
        """
        serial = serial_number.strip()
        if not serial:
            return False, "시리얼 번호를 입력해주세요.", None
            
        device_info = self.get_device_info()
        payload = {
            "serial_number": serial,
            "device_info": device_info
        }
        
        timeouts = [5, 25, 30]
        last_error = None
        
        for attempt in range(len(timeouts)):
            timeout_sec = timeouts[attempt]
            try:
                self.logger.info(f"Server validation attempt {attempt+1}/3 (timeout: {timeout_sec}s)")
                response = requests.post(
                    f"{self.SERVER_URL}/api/validate",
                    json=payload,
                    timeout=timeout_sec
                )
                
                if response.status_code == 200:
                    data = response.json()
                    status = data.get("status", "사용중")
                    expiry_date = data.get("expiry_date", "")
                    
                    if status == "만료됨":
                        self.clear_config()
                        return False, "시리얼 번호가 만료되었습니다.", expiry_date
                    elif status == "블랙리스트":
                        self.clear_config()
                        return False, "블랙리스트에 등록된 시리얼 번호입니다.", None
                    
                    self.save_config(serial, status=status, expiry_date=expiry_date)
                    warning = data.get("warning")
                    if warning:
                        msg = f"{warning} (만료일: {expiry_date})"
                    else:
                        msg = "시리얼 번호 인증에 성공했습니다."
                    return True, msg, expiry_date
                    
                else:
                    try:
                        err_msg = response.json().get("error", "인증에 실패했습니다.")
                    except Exception:
                        err_msg = f"서버 오류가 발생했습니다. (HTTP {response.status_code})"
                    return False, err_msg, None
                    
            except requests.exceptions.RequestException as e:
                last_error = str(e)
                self.logger.warning(f"Connection attempt {attempt+1} failed: {e}")
                
        cached = self.load_config()
        if cached.get("serial_number") == serial and cached.get("last_validation"):
            try:
                last_valid = datetime.strptime(cached["last_validation"], "%Y-%m-%d %H:%M:%S")
                if datetime.now() - last_valid < timedelta(days=7):
                    self.logger.info("Offline grace period allowed.")
                    return True, "오프라인 모드로 인증되었습니다. (서버 연결 불가)", cached.get("expiry_date")
            except Exception:
                pass
                
        return False, "서버에 연결할 수 없습니다. 인터넷 연결을 확인해주세요.", None

    def is_serial_valid(self) -> Tuple[bool, str]:
        """Checks if a valid serial is already cached and still valid."""
        config = self.load_config()
        serial = config.get("serial_number", "").strip()
        if not serial:
            return False, "등록된 시리얼 번호가 없습니다."
        return self.validate(serial)[:2]
