import sys
import os
import signal
import socket
import multiprocessing

# 현재 디렉토리를 경로에 추가하여 모듈 임포트가 가능하게 함
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox
from PyQt6.QtCore import Qt
from ui.layout import MainWindow
from core.serial_auth import SerialAuth
from ui.serial_auth_dialog import SerialAuthDialog
from utils.auto_updater import AutoUpdater

SINGLE_INSTANCE_PORT = 49281
_instance_socket = None

def ensure_single_instance() -> bool:
    """프로그램 중복 실행 방지 (Local Socket Guard)"""
    global _instance_socket
    try:
        _instance_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _instance_socket.bind(('127.0.0.1', SINGLE_INSTANCE_PORT))
        _instance_socket.listen(1)
        return True
    except OSError:
        return False

def main():
    # 0. PyInstaller 서브프로세스 재실행 방지 (가장 중요)
    multiprocessing.freeze_support()

    # 터미널에서 Ctrl+C를 눌렀을 때 macOS 에러창(예기치 않게 종료)이 뜨지 않도록 안전한 종료 처리
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    app = QApplication(sys.argv)
    
    # 중복 실행 방지: 이미 실행 중인 경우 즉시 종료
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

    # 1. 시리얼 인증 사전 검사
    serial_auth = SerialAuth()
    cached = serial_auth.load_config()
    is_valid = False
    
    # 캐시된 시리얼이 있는 경우 백그라운드 유효성 검증
    if cached.get("serial_number"):
        is_valid, msg = serial_auth.is_serial_valid()
        
    # 캐시된 시리얼이 없거나 검증 실패 시 모달 다이얼로그 호출
    if not is_valid:
        dialog = SerialAuthDialog(serial_auth=serial_auth)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            # 사용자가 인증 창을 닫았거나 취소한 경우 앱 종료
            sys.exit(0)

    # 2. 메인 윈도우 실행
    window = MainWindow()
    window.show()
    
    # 3. 비동기 자동 업데이트 확인 (네이버 자동화 방식 적용)
    try:
        updater = AutoUpdater(parent_widget=window)
        updater.check_for_updates_async(show_no_update_dialog=False)
    except Exception as e:
        print(f"[Updater] Update check skipped: {e}")
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
