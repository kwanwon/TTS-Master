#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto-Updater Module for TTS Master
- Checks GitHub Releases for new versions
- Automatic background download with QProgressDialog
- Automatic in-place replacement and app relaunch (macOS & Windows)
- Preserves serial license and user projects/settings
"""

import os
import sys
import json
import shutil
import zipfile
import tempfile
import logging
import requests
import subprocess
import time
from typing import Optional, Dict, Any, Tuple
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import QMessageBox, QProgressDialog, QApplication

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

class DownloadWorker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)
    
    def __init__(self, download_url: str, dest_path: str):
        super().__init__()
        self.download_url = download_url
        self.dest_path = dest_path
        self.is_cancelled = False
        
    def run(self):
        try:
            resp = requests.get(self.download_url, stream=True, timeout=30)
            if resp.status_code != 200:
                self.failed.emit(f"다운로드 서버 응답 에러 (HTTP {resp.status_code})")
                return
                
            total_length = resp.headers.get('content-length')
            if total_length is None:
                total_length = 0
            else:
                total_length = int(total_length)
                
            downloaded = 0
            with open(self.dest_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=1024 * 128):
                    if self.is_cancelled:
                        return
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_length > 0:
                            percent = int((downloaded / total_length) * 100)
                            self.progress.emit(percent)
                            
            self.finished.emit(self.dest_path)
        except Exception as e:
            self.failed.emit(str(e))
            
    def cancel(self):
        self.is_cancelled = True

class AutoUpdater:
    """Handles update check, automatic downloading, in-place replacement, and app relaunch."""
    
    DEFAULT_OWNER = "kwanwon"
    DEFAULT_REPO = "TTS-Master"
    
    def __init__(self, parent_widget=None, repo_owner: str = None, repo_name: str = None):
        self.parent = parent_widget
        self.repo_owner = repo_owner or self.DEFAULT_OWNER
        self.repo_name = repo_name or self.DEFAULT_REPO
        self.current_version = self._load_version()
        self.thread = None
        self.download_thread = None
        self.progress_dlg = None
        
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
        """Non-blocking check on program startup or manual button click."""
        self.thread = UpdateCheckThread(self.current_version, self.repo_owner, self.repo_name)
        self.thread.update_available.connect(self._on_update_available)
        if show_no_update_dialog:
            self.thread.check_finished.connect(self._on_check_finished)
        self.thread.start()
        
    def _on_update_available(self, release_info: dict):
        new_ver = release_info.get("version")
        body = release_info.get("body", "최신 기능 개선 및 안정성 향상")
        
        # OS별 적절한 Asset 파일 찾기
        target_asset = self._find_target_asset(release_info.get("assets", []))
        
        msg = (
            f"🎉 새로운 버전(v{new_ver})이 출시되었습니다!\n"
            f"현재 버전: v{self.current_version}\n\n"
            f"[업데이트 내용]\n{body[:350]}\n\n"
            f"지금 자동으로 다운로드하여 업데이트 후 재시작하시겠습니까?"
        )
        
        reply = QMessageBox.question(
            self.parent,
            "🚀 원클릭 자동 업데이트",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            if target_asset:
                self._start_download_and_install(target_asset, new_ver)
            else:
                # 적절한 zip 파일이 없는 경우 웹 브라우저로 안내
                url = release_info.get("html_url")
                if url:
                    import webbrowser
                    webbrowser.open(url)
                    
    def _find_target_asset(self, assets: list) -> Optional[dict]:
        """Finds matching zip asset for current OS."""
        if sys.platform == 'darwin':
            keywords = ["Mac", "mac", "darwin"]
        elif sys.platform == 'win32':
            keywords = ["Windows", "win", "Win"]
        else:
            keywords = ["Linux", "linux"]
            
        for a in assets:
            name = a.get("name", "")
            if name.endswith(".zip") and any(k in name for k in keywords):
                return a
                
        # fallback: any zip
        for a in assets:
            if a.get("name", "").endswith(".zip"):
                return a
        return None

    def _start_download_and_install(self, asset: dict, new_version: str):
        download_url = asset.get("browser_download_url")
        filename = asset.get("name", "update.zip")
        
        temp_dir = tempfile.mkdtemp()
        dest_zip = os.path.join(temp_dir, filename)
        
        self.progress_dlg = QProgressDialog("최신 업데이트 다운로드 중...", "취소", 0, 100, self.parent)
        self.progress_dlg.setWindowTitle("🔄 자동 업데이트")
        self.progress_dlg.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dlg.setMinimumDuration(0)
        self.progress_dlg.setValue(0)
        
        self.download_thread = DownloadWorker(download_url, dest_zip)
        self.download_thread.progress.connect(self.progress_dlg.setValue)
        self.download_thread.finished.connect(lambda path: self._on_download_complete(path, temp_dir, new_version))
        self.download_thread.failed.connect(self._on_download_failed)
        self.progress_dlg.canceled.connect(self.download_thread.cancel)
        
        self.download_thread.start()
        self.progress_dlg.show()

    def _on_download_failed(self, error_msg: str):
        if self.progress_dlg:
            self.progress_dlg.close()
        QMessageBox.critical(self.parent, "업데이트 오류", f"업데이트 다운로드 중 오류가 발생했습니다:\n{error_msg}")

    def _on_download_complete(self, zip_path: str, temp_dir: str, new_version: str):
        if self.progress_dlg:
            self.progress_dlg.setValue(100)
            self.progress_dlg.close()
            
        # 압축 해제 및 교체 실행
        success, msg = self._apply_update_and_relaunch(zip_path, temp_dir)
        if not success:
            QMessageBox.critical(self.parent, "업데이트 적용 실패", f"업데이트 교체 중 문제가 발생했습니다:\n{msg}")

    def _apply_update_and_relaunch(self, zip_path: str, temp_dir: str) -> Tuple[bool, str]:
        """Unzips and triggers restart script."""
        try:
            extract_dir = os.path.join(temp_dir, "extracted")
            os.makedirs(extract_dir, exist_ok=True)
            
            # 1. 압축 해제
            if sys.platform == 'darwin':
                subprocess.run(['unzip', '-q', '-o', zip_path, '-d', extract_dir], check=True)
            else:
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    zf.extractall(extract_dir)
                    
            # 2. 실행 환경 식별
            is_frozen = getattr(sys, 'frozen', False)
            
            if sys.platform == 'darwin':
                return self._apply_macos_bundle_update(extract_dir, temp_dir, is_frozen)
            elif sys.platform == 'win32':
                return self._apply_windows_update(extract_dir, temp_dir, is_frozen)
            else:
                return False, "지원되지 않는 운영체제입니다."
        except Exception as e:
            return False, str(e)

    def _apply_macos_bundle_update(self, extract_dir: str, temp_dir: str, is_frozen: bool) -> Tuple[bool, str]:
        """Replaces macOS .app bundle and relaunches."""
        try:
            # 1. 새로 풀린 .app 찾기
            new_app_path = None
            for item in os.listdir(extract_dir):
                if item.endswith(".app"):
                    new_app_path = os.path.join(extract_dir, item)
                    break
            if not new_app_path:
                return False, "압축 파일 내에서 .app 번들을 찾을 수 없습니다."

            # 2. 현재 실행 중인 .app 경로 확인
            if is_frozen:
                exec_path = sys.executable  # .../Contents/MacOS/AIMaster_TTS_Mac
                contents_dir = os.path.dirname(os.path.dirname(exec_path))
                current_app_bundle = os.path.dirname(contents_dir)
            else:
                # 소스코드 실행 중일 경우 바탕화면 앱으로 대상 지정
                desktop_app = os.path.expanduser("~/Desktop/AIMaster_TTS_Mac.app")
                current_app_bundle = desktop_app if os.path.exists(desktop_app) else new_app_path

            # AppTranslocation 처리
            app_name = os.path.basename(current_app_bundle)
            if "AppTranslocation" in current_app_bundle:
                for candidate in [os.path.expanduser(f"~/Desktop/{app_name}"), f"/Applications/{app_name}"]:
                    if os.path.exists(candidate):
                        current_app_bundle = candidate
                        break

            # 3. 셸 스크립트 작성
            script_path = os.path.join(temp_dir, "relaunch.sh")
            backup_trash = os.path.join(temp_dir, "old_app_backup")
            
            script_content = f"""#!/bin/bash
sleep 1.5
echo "Updating {app_name}..."

# 1. 기존 앱 백업 이동 및 새 앱 배치
rm -rf "{backup_trash}"
mv "{current_app_bundle}" "{backup_trash}"
mv "{new_app_path}" "{current_app_bundle}"

# 2. 권한 및 보안 속성 정상화
chmod -R +x "{current_app_bundle}/Contents/MacOS"
xattr -cr "{current_app_bundle}"
codesign -s - --force --deep "{current_app_bundle}" 2>/dev/null || true

# 3. 새 버전 자동 재시작
open "{current_app_bundle}"
"""
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(script_content)
            os.chmod(script_path, 0o755)
            
            QMessageBox.information(
                self.parent,
                "업데이트 완료",
                "최신 버전이 준비되었습니다.\n프로그램이 자동으로 재시작됩니다."
            )
            
            # 스크립트를 완전히 분리된 백그라운드 프로세스로 실행
            subprocess.Popen([script_path], shell=False, start_new_session=True)
            
            # 현재 앱 정상 종료
            QApplication.quit()
            sys.exit(0)
            return True, "재시작 중..."
        except Exception as e:
            return False, str(e)

    def _apply_windows_update(self, extract_dir: str, temp_dir: str, is_frozen: bool) -> Tuple[bool, str]:
        """Replaces Windows directory and relaunches."""
        try:
            if is_frozen:
                current_dir = os.path.dirname(sys.executable)
                exe_name = os.path.basename(sys.executable)
            else:
                current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                exe_name = "AIMaster_TTS_Windows.exe"

            # 압축 해제된 폴더 내의 내용물 탐색
            src_dir = extract_dir
            for item in os.listdir(extract_dir):
                sub = os.path.join(extract_dir, item)
                if os.path.isdir(sub) and ("AIMaster" in item or os.path.exists(os.path.join(sub, exe_name))):
                    src_dir = sub
                    break

            bat_path = os.path.join(temp_dir, "relaunch.bat")
            bat_content = f"""@echo off
timeout /t 2 /nobreak > nul
xcopy /E /Y /I "{src_dir}" "{current_dir}"
start "" "{os.path.join(current_dir, exe_name)}"
exit
"""
            with open(bat_path, "w", encoding="cp949") as f:
                f.write(bat_content)

            QMessageBox.information(
                self.parent,
                "업데이트 완료",
                "최신 버전이 준비되었습니다.\n프로그램이 자동으로 재시작됩니다."
            )

            subprocess.Popen(["cmd.exe", "/c", bat_path], shell=False, creationflags=subprocess.CREATE_NEW_CONSOLE if hasattr(subprocess, 'CREATE_NEW_CONSOLE') else 0)
            QApplication.quit()
            sys.exit(0)
            return True, "재시작 중..."
        except Exception as e:
            return False, str(e)

    def _on_check_finished(self, has_update: bool, msg: str):
        if not has_update and self.parent:
            QMessageBox.information(self.parent, "업데이트 확인", f"현재 최신 버전(v{self.current_version})을 사용 중입니다.")
