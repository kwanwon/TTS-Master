import sys
import os
import signal
import tempfile
import multiprocessing
import platform

# 1. 앱 전역 실행 환경 및 작업 디렉토리 초기화 (macOS Finder 실행 시 CWD='/' Read-only 에러 원천 방지)
if getattr(sys, 'frozen', False):
    if platform.system() == "Windows":
        APP_DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "AIMaster_TTS")
    else:
        APP_DATA_DIR = os.path.join(os.path.expanduser("~"), ".aimaster_tts")
else:
    APP_DATA_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    os.makedirs(APP_DATA_DIR, exist_ok=True)
    os.makedirs(os.path.join(APP_DATA_DIR, "projects", "temp_tts"), exist_ok=True)
    os.makedirs(os.path.join(APP_DATA_DIR, "effects"), exist_ok=True)
    os.chdir(APP_DATA_DIR)
except Exception as e:
    print(f"[Init] Working directory setup error: {e}")

# 모듈 검색 경로 설정
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    sys.path.insert(0, sys._MEIPASS)

from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from ui.layout import MainWindow
from core.serial_auth import SerialAuth
from ui.serial_auth_dialog import SerialAuthDialog
from utils.auto_updater import AutoUpdater

LOCK_FILE = os.path.join(tempfile.gettempdir(), "aimaster_tts_running.lock")

def ensure_single_instance() -> bool:
    """PID 기반 안전한 중복 실행 방지 (포트 충돌 및 소켓 에러 완벽 해결)"""
    try:
        current_pid = os.getpid()
        if os.path.exists(LOCK_FILE):
            try:
                with open(LOCK_FILE, "r") as f:
                    old_pid = int(f.read().strip())
                if old_pid != current_pid:
                    # 기존 프로세스가 실제로 실행 중인지 확인
                    import psutil
                    if psutil.pid_exists(old_pid):
                        proc = psutil.Process(old_pid)
                        if "AIMaster" in proc.name() or "python" in proc.name():
                            return False
            except Exception:
                pass
                
        # 현재 PID로 락 갱신
        with open(LOCK_FILE, "w") as f:
            f.write(str(current_pid))
        return True
    except Exception:
        return True

def cleanup_lock():
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except Exception:
        pass

def main():
    # 0. PyInstaller 서브프로세스 재실행 방지 (가장 중요)
    multiprocessing.freeze_support()

    # 터미널에서 Ctrl+C를 눌렀을 때 macOS 에러창(예기치 않게 종료)이 뜨지 않도록 안전한 종료 처리
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    app = QApplication(sys.argv)
    app.aboutToQuit.connect(cleanup_lock)
    
    # 앱 전체 아이콘 설정 (은색 사자 엠블럼)
    for icon_path in [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.png"),
        os.path.join(getattr(sys, '_MEIPASS', ''), "assets", "icon.png") if hasattr(sys, '_MEIPASS') else "",
        os.path.join(os.path.expanduser("~"), ".aimaster_tts", "assets", "icon.png"),
        "assets/icon.png"
    ]:
        if icon_path and os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))
            break
    
    # 중복 실행 방지: 이미 실행 중인 경우 알림 후 종료
    if not ensure_single_instance():
        QMessageBox.warning(None, "중복 실행 방지", "AI 마스터 (TTS 컨트롤러)가 이미 실행 중입니다.\n기존에 열려 있는 창을 확인해 주세요.")
        sys.exit(0)

    # 야간 모드일 때 리스트와 버튼 글씨가 검정색으로 나오는 macOS 버그 방지
    if app.styleHints().colorScheme() == Qt.ColorScheme.Dark:
        app.setStyleSheet("""
            QListWidget, QTableWidget { background-color: #2b2b2b; color: #ffffff; }
            QPushButton { background-color: #404040; color: #ffffff; border: 1px solid #555; border-radius: 4px; padding: 5px; }
            QPushButton:hover { background-color: #505050; }
        """)

    # 1. 시리얼 인증 사전 검사 (0.001초 로컬 캐시 즉시 신뢰하여 시작 렉/슬립 대기 완전 제거)
    serial_auth = SerialAuth()
    is_valid = serial_auth.has_valid_cache()
        
    # 캐시된 시리얼이 없거나 만료된 경우에만 모달 다이얼로그 호출
    if not is_valid:
        dialog = SerialAuthDialog(serial_auth=serial_auth)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            cleanup_lock()
            sys.exit(0)

    # 2. 메인 윈도우 실행 (화면 최상단으로 강제 활성화)
    window = MainWindow()
    window.show()
    window.raise_()
    window.activateWindow()
    
    # 3. 비동기 자동 업데이트 확인 (네이버 자동화 방식 적용)
    try:
        window.updater = AutoUpdater(parent_widget=window)
        window.updater.check_for_updates_async(show_no_update_dialog=False)
    except Exception as e:
        print(f"[Updater] Update check skipped: {e}")
    
    ret = app.exec()
    cleanup_lock()
    sys.exit(ret)

if __name__ == "__main__":
    main()
