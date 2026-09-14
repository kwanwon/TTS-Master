import sys
from PyQt6.QtCore import QThread, pyqtSignal

class ModelInstallerThread(QThread):
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, repo_id, parent=None):
        super().__init__(parent)
        self.repo_id = repo_id

    def run(self):
        try:
            self.log.emit(f"모델 다운로드 시작: {self.repo_id}")
            self.progress.emit(10)
            
            # huggingface_hub 가 설치되어 있는지 확인하고 다운로드 진행
            try:
                from huggingface_hub import snapshot_download
            except ImportError:
                self.log.emit("huggingface_hub 패키지가 필요합니다. 다운로드를 시도합니다...")
                import subprocess
                subprocess.check_call([sys.executable, "-m", "pip", "install", "huggingface_hub"])
                from huggingface_hub import snapshot_download
                
            self.progress.emit(30)
            
            # 다운로드 실행 (이미 있으면 빠르게 스킵됨)
            model_path = snapshot_download(
                repo_id=self.repo_id,
                local_files_only=False,
                resume_download=True,
                max_workers=4
            )
            
            self.progress.emit(100)
            self.log.emit("다운로드 완료!")
            self.finished_signal.emit(True, model_path)
            
        except Exception as e:
            self.log.emit(f"오류 발생: {str(e)}")
            self.finished_signal.emit(False, str(e))
