import sys
import os
import signal
import tempfile
import multiprocessing
import platform
import utils.edge_tts_patch  # Microsoft Edge-TTS 2026 엔드포인트 및 날짜 파싱 전역 패치

# 1. 앱 전역 실행 환경 및 작업 디렉토리 초기화 (macOS Finder 실행 시 CWD='/' Read-only 에러 원천 방지)
if getattr(sys, 'frozen', False):
    if platform.system() == "Windows":
        APP_DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "AIMaster_TTS")
    else:
        APP_DATA_DIR = os.path.join(os.path.expanduser("~"), ".aimaster_tts")
else:
    APP_DATA_DIR = os.path.dirname(os.path.abspath(__file__))

# Windows 및 macOS GUI 실행 시 ffmpeg 및 실행 경로 자동 보정
app_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
meipass_dir = getattr(sys, '_MEIPASS', '')
extra_paths = [
    app_dir,
    os.path.join(app_dir, "bin"),
    meipass_dir,
    os.path.join(meipass_dir, "bin"),
    "/opt/homebrew/bin",
    "/opt/homebrew/sbin",
    "/usr/local/bin",
    "/usr/bin",
    "/bin",
    "/usr/sbin",
    "/sbin",
    os.path.join(APP_DATA_DIR, "bin")
]
current_path = os.environ.get("PATH", "")
for p in extra_paths:
    if p and os.path.exists(p) and p not in current_path:
        current_path = f"{p}{os.pathsep}{current_path}"
os.environ["PATH"] = current_path

# pydub ffmpeg / ffprobe 위치 자동 탐지 및 주입 (번들된 ffmpeg 최우선)
try:
    import shutil
    import pydub
    from pydub.utils import which

    ffmpeg_bin = None
    ffprobe_bin = None

    # 1. 앱 번들 디렉토리 우선 탐색
    for candidate_dir in [app_dir, os.path.join(app_dir, "bin"), meipass_dir]:
        if candidate_dir and os.path.exists(candidate_dir):
            for f_name in ["ffmpeg.exe", "ffmpeg"]:
                fp = os.path.join(candidate_dir, f_name)
                if os.path.exists(fp):
                    ffmpeg_bin = fp
                    break
            for f_name in ["ffprobe.exe", "ffprobe"]:
                fp = os.path.join(candidate_dir, f_name)
                if os.path.exists(fp):
                    ffprobe_bin = fp
                    break
        if ffmpeg_bin and ffprobe_bin:
            break

    # 2. 시스템 PATH 폴백 탐색
    if not ffmpeg_bin:
        ffmpeg_bin = shutil.which("ffmpeg") or which("ffmpeg")
    if not ffprobe_bin:
        ffprobe_bin = shutil.which("ffprobe") or which("ffprobe")

    if ffmpeg_bin:
        pydub.AudioSegment.converter = ffmpeg_bin
        print(f"[Init] ffmpeg detected: {ffmpeg_bin}")
    if ffprobe_bin:
        pydub.AudioSegment.ffprobe = ffprobe_bin
        print(f"[Init] ffprobe detected: {ffprobe_bin}")
except Exception as e:
    print(f"[Init] ffmpeg setup warning: {e}")

# SSL 루트 인증서 경로 설정 (PyInstaller macOS 환경에서 Edge-TTS / HTTPS 통신 오류 원천 차단)
try:
    import certifi
    ca_bundle = certifi.where()
    if os.path.exists(ca_bundle):
        os.environ["SSL_CERT_FILE"] = ca_bundle
        os.environ["REQUESTS_CA_BUNDLE"] = ca_bundle
        print(f"[Init] SSL CA bundle configured: {ca_bundle}")
except Exception as e_cert:
    print(f"[Init] certifi setup warning: {e_cert}")

try:
    os.makedirs(APP_DATA_DIR, exist_ok=True)
    os.makedirs(os.path.join(APP_DATA_DIR, "projects", "temp_tts"), exist_ok=True)
    os.makedirs(os.path.join(APP_DATA_DIR, "effects"), exist_ok=True)
    os.makedirs(os.path.join(APP_DATA_DIR, "voice_samples"), exist_ok=True)
    os.chdir(APP_DATA_DIR)
except Exception as e:
    print(f"[Init] Working directory setup error: {e}")

# 모듈 검색 경로 설정
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    sys.path.insert(0, sys._MEIPASS)

# 기본 필수 효과음 에셋(비프, 휘슬, 차임벨, 카운트다운, 대북음) 자동 생성
try:
    from utils.effects_generator import ensure_default_effects
    ensure_default_effects(os.path.join(APP_DATA_DIR, "effects"))
except Exception as e:
    print(f"[Init] Effects generation warning: {e}")

from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from ui.layout import MainWindow
from core.serial_auth import SerialAuth
from ui.serial_auth_dialog import SerialAuthDialog
from utils.auto_updater import AutoUpdater
from utils.theme_manager import setup_theme_listener

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

def global_exception_handler(exctype, value, tb):
    """PyQt6 슬롯 예외 발생 시 macOS 강제 종료(SIGABRT) 방지 및 안전 로깅"""
    import traceback
    err_str = "".join(traceback.format_exception(exctype, value, tb))
    print("[Unhandled Exception]", err_str)
    try:
        log_path = os.path.join(APP_DATA_DIR, "crash_prevented.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n--- {exctype.__name__}: {value} ---\n{err_str}\n")
    except Exception:
        pass

sys.excepthook = global_exception_handler

def main():
    # 0. PyInstaller 서브프로세스 재실행 방지 (가장 중요)
    multiprocessing.freeze_support()

    # 터미널에서 Ctrl+C를 눌렀을 때 macOS 에러창(예기치 않게 종료)이 뜨지 않도록 안전한 종료 처리
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    app = QApplication(sys.argv)
    app.aboutToQuit.connect(cleanup_lock)
    
    # 앱 전체 아이콘 설정 (사자 엠블럼) 및 macOS 데스크톱 .app 번들 아이콘 자동 복구
    for icon_path in [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.png"),
        os.path.join(getattr(sys, '_MEIPASS', ''), "assets", "icon.png") if hasattr(sys, '_MEIPASS') else "",
        os.path.join(os.path.expanduser("~"), ".aimaster_tts", "assets", "icon.png"),
        "assets/icon.png"
    ]:
        if icon_path and os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))
            break

    if sys.platform == "darwin":
        def _ensure_mac_bundle_icon():
            try:
                import subprocess
                icns_candidates = [
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.icns"),
                    os.path.join(getattr(sys, '_MEIPASS', ''), "assets", "icon.icns") if hasattr(sys, '_MEIPASS') else "",
                ]
                icns_path = next((p for p in icns_candidates if p and os.path.exists(p)), "")
                desktop_app = os.path.expanduser("~/Desktop/AIMaster_TTS_Mac.app")
                if icns_path and os.path.exists(desktop_app):
                    icon_r = os.path.join(desktop_app, "Icon\r")
                    if not os.path.exists(icon_r) or os.path.getsize(icon_r) == 0:
                        subprocess.run([
                            "swift", "-e",
                            f'import AppKit; if let img = NSImage(contentsOfFile: "{icns_path}") {{ '
                            f'NSWorkspace.shared.setIcon(img, forFile: "{desktop_app}", options: []); '
                            f'NSWorkspace.shared.noteFileSystemChanged("{desktop_app}") }}'
                        ], check=False)
            except Exception:
                pass
        import threading
        threading.Thread(target=_ensure_mac_bundle_icon, daemon=True).start()
    
    # 중복 실행 방지: 이미 실행 중인 경우 알림 후 종료
    if not ensure_single_instance():
        QMessageBox.warning(None, "중복 실행 방지", "AI 마스터 (TTS 컨트롤러)가 이미 실행 중입니다.\n기존에 열려 있는 창을 확인해 주세요.")
        sys.exit(0)

    # 다크 모드 및 라이트 모드 실시간 자동 대응 고대비 테마 리스너 활성화
    # (macOS 네이티브 아쿠아 테마 충돌 및 QComboBox 흰 글씨/흰 배경 가림 현상 원천 차단)
    setup_theme_listener(app)

    # 앱 전체 모든 입력창(QTextEdit, QPlainTextEdit, QLineEdit) 한글 자모 분리 자동 보정 장착
    from utils.hangul_composer import install_global_hangul_composer
    install_global_hangul_composer(app)

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
    
    # 3. 비동기 자동 업데이트 확인 및 새 버전 첫 실행 팝업
    try:
        window.updater = AutoUpdater(parent_widget=window)
        window.updater.check_first_run_after_update()
        window.updater.check_for_updates_async(show_no_update_dialog=False)
    except Exception as e:
        print(f"[Updater] Update check skipped: {e}")
    
    ret = app.exec()
    cleanup_lock()
    sys.exit(ret)

if __name__ == "__main__":
    main()
