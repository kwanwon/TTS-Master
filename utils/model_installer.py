import os
import sys
from PyQt6.QtCore import QThread, pyqtSignal

class ModelInstallerThread(QThread):
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, repo_id, parent=None):
        super().__init__(parent)
        self.repo_id = repo_id

    def _check_local_cache(self) -> str | None:
        """Hugging Face 글로벌 캐시에 이미 모델이 설치되어 있는지 즉시 확인"""
        try:
            # 기본 캐시 경로 (~/.cache/huggingface/hub)
            cache_dir = os.path.expanduser(os.environ.get("HF_HOME", "~/.cache/huggingface/hub"))
            # Hugging Face 저장 폴더 규격: "Qwen/Qwen3-..." -> "models--Qwen--Qwen3-..."
            folder_name = "models--" + self.repo_id.replace("/", "--")
            model_dir = os.path.join(cache_dir, folder_name)
            
            if os.path.exists(model_dir):
                snapshots_dir = os.path.join(model_dir, "snapshots")
                if os.path.exists(snapshots_dir) and os.listdir(snapshots_dir):
                    # 가장 최근 스냅샷 디렉토리
                    snaps = os.listdir(snapshots_dir)
                    latest_snap = os.path.join(snapshots_dir, snaps[0])
                    return latest_snap
        except Exception:
            pass
        return None

    def run(self):
        try:
            # 1. 이미 설치되어 있는지 사전 검사 (중복 다운로드 완전 방지)
            cached_path = self._check_local_cache()
            if cached_path:
                self.log.emit("기존 설치된 Qwen3 모델을 감지했습니다. (중복 다운로드 생략)")
                self.progress.emit(100)
                self.finished_signal.emit(True, cached_path)
                return

            self.log.emit(f"모델 다운로드 준비 중: {self.repo_id}")
            self.progress.emit(10)
            
            # 2. huggingface_hub 임포트 확인 (절대 sys.executable -m pip 실행 금지!)
            try:
                from huggingface_hub import snapshot_download
            except ImportError:
                self.log.emit("huggingface_hub 패키지가 없습니다.")
                self.finished_signal.emit(False, "huggingface_hub 패키지가 번들에 포함되지 않았습니다.")
                return
                
            self.progress.emit(30)
            self.log.emit("모델 가중치 다운로드 진행 중...")
            
            # 3. 다운로드 실행 (이미 있는 파일은 resume_download로 건너뜀)
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
