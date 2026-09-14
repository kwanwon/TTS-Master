#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto-Updater Module for TTS Master
- Checks GitHub Releases for new versions
- Based on Naver Blog Automation updater architecture
- Non-blocking asynchronous checks
"""

import os
import sys
import json
import logging
import requests
from typing import Optional, Dict, Any, Tuple
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QMessageBox

class UpdateCheckThread(QThread):
    update_available = pyqtSignal(dict)  # Emits release info dict if newer
    check_finished = pyqtSignal(bool, str) # has_update, current_or_error
    
    def __init__(self, current_version: str, repo_owner: str, repo_name: str):
        super().__init__()
        self.current_version = current_version
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        
    def run(self):
        try:
            url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases/latest"
            headers = {"Accept": "application/vnd.github.v3+json"}
            resp = requests.get(url, headers=headers, timeout=5)
            
            if resp.status_code == 200:
                data = resp.json()
                tag_name = data.get("tag_name", "").lstrip("v")
                
                if self._is_newer(tag_name, self.current_version):
                    self.update_available.emit({
                        "version": tag_name,
                        "name": data.get("name", tag_name),
                        "body": data.get("body", ""),
                        "html_url": data.get("html_url", ""),
                        "assets": data.get("assets", [])
                    })
                    self.check_finished.emit(True, tag_name)
                    return
                else:
                    self.check_finished.emit(False, "최신 버전입니다.")
                    return
            elif resp.status_code == 404:
                self.check_finished.emit(False, "등록된 릴리즈가 없습니다.")
                return
            else:
                self.check_finished.emit(False, f"서버 응답 오류 (HTTP {resp.status_code})")
                return
        except Exception as e:
            self.check_finished.emit(False, str(e))
            
    def _is_newer(self, latest_ver: str, curr_ver: str) -> bool:
        """Compares semver versions (e.g. 1.0.1 > 1.0.0)."""
        try:
            def parse(v):
                return [int(x) for x in v.split(".")]
            return parse(latest_ver) > parse(curr_ver)
        except Exception:
            return latest_ver != curr_ver and bool(latest_ver)

class AutoUpdater:
    """Handles update check and user notification."""
    
    DEFAULT_OWNER = "kwanwon"
    DEFAULT_REPO = "TTS-Master"
    
    def __init__(self, parent_widget=None, repo_owner: str = None, repo_name: str = None):
        self.parent = parent_widget
        self.repo_owner = repo_owner or self.DEFAULT_OWNER
        self.repo_name = repo_name or self.DEFAULT_REPO
        self.current_version = self._load_version()
        self.thread = None
        
    def _load_version(self) -> str:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        vfile = os.path.join(base_dir, "version.json")
        if os.path.exists(vfile):
            try:
                with open(vfile, "r", encoding="utf-8") as f:
                    return json.load(f).get("version", "1.0.0")
            except Exception:
                pass
        return "1.0.0"
        
    def check_for_updates_async(self, show_no_update_dialog: bool = False):
        """Non-blocking check on program startup."""
        self.thread = UpdateCheckThread(self.current_version, self.repo_owner, self.repo_name)
        self.thread.update_available.connect(self._on_update_available)
        if show_no_update_dialog:
            self.thread.check_finished.connect(self._on_check_finished)
        self.thread.start()
        
    def _on_update_available(self, release_info: dict):
        new_ver = release_info.get("version")
        body = release_info.get("body", "새로운 업데이트가 출시되었습니다.")
        url = release_info.get("html_url")
        
        msg = (
            f"새로운 버전({new_ver})이 출시되었습니다!\n"
            f"현재 버전: {self.current_version}\n\n"
            f"[업데이트 내용]\n{body[:300]}\n\n"
            f"지금 다운로드 페이지로 이동하시겠습니까?"
        )
        
        reply = QMessageBox.question(
            self.parent,
            "🚀 새 버전 발견",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        
        if reply == QMessageBox.StandardButton.Yes and url:
            import webbrowser
            webbrowser.open(url)
            
    def _on_check_finished(self, has_update: bool, msg: str):
        if not has_update and self.parent:
            QMessageBox.information(self.parent, "업데이트 확인", f"현재 최신 버전({self.current_version})을 사용 중입니다.")
