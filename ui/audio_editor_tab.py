import os
import pygame
import shutil
import math
import uuid
import time
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QFileDialog, QMessageBox, QProgressBar, QApplication, QSlider, QTextEdit,
    QSizePolicy, QSplitter, QListWidgetItem, QDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from ui.daw_timeline import DAWTimeline, AssetListWidget
from utils.effects_generator import ensure_default_effects
from ui.shuttle_run_dialog import ShuttleRunDialog
from ui.sparring_dialog import SparringDialog

class AudioProcessorThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str, str)
    
    def __init__(self, mode, params):
        super().__init__()
        self.mode = mode
        self.params = params
        
    def run(self):
        try:
            from pydub import AudioSegment
            if self.mode in ("mix", "preview"):
                timeline_data = self.params['timeline']
                output_file = self.params['output']
                track_vols = self.params.get('track_vols', [1.0, 1.0, 1.0])
                
                self.progress.emit(10)
                bgm = AudioSegment.silent(duration=1000) # 기본 캔버스
                    
                timeline_data.sort(key=lambda x: x['time'])
                self.progress.emit(30)
                
                for idx, item in enumerate(timeline_data):
                    if not os.path.exists(item['file']): continue
                    overlay_audio = AudioSegment.from_file(item['file'])
                    
                    t_vol = track_vols[item['track']]
                    if t_vol <= 0.01:
                        continue # 볼륨 0인 경우 패스
                        
                    clip_db = 0
                    if t_vol != 1.0:
                        import math
                        clip_db = 20 * math.log10(max(t_vol, 0.01))
                        
                    total_db = item['vol'] + clip_db
                    if total_db != 0:
                        overlay_audio = overlay_audio + total_db
                        
                    insert_ms = int(item['time'] * 1000)
                    end_time_ms = insert_ms + len(overlay_audio)
                    if end_time_ms > len(bgm):
                        silence_needed = end_time_ms - len(bgm)
                        bgm = bgm + AudioSegment.silent(duration=silence_needed)
                        
                    bgm = bgm.overlay(overlay_audio, position=insert_ms)
                    prog = 30 + int(60 * (idx + 1) / len(timeline_data))
                    self.progress.emit(prog)
                
                self.progress.emit(95)
                bgm.export(output_file, format=output_file.split('.')[-1])
                self.progress.emit(100)
                
                if self.mode == "preview":
                    self.finished.emit("preview_success", output_file)
                else:
                    self.finished.emit("success", f"믹싱이 성공적으로 완료되었습니다:\n{output_file}")
                
        except Exception as e:
            self.finished.emit("error", f"오류 발생:\n{str(e)}")

class TTSAssetThread(QThread):
    finished = pyqtSignal(str, str, str) # status, info (file_path or error_msg), text
    
    def __init__(self, tts_engine, text, speed, save_path):
        super().__init__()
        self.tts_engine = tts_engine
        self.text = text
        self.speed = speed
        self.save_path = save_path
        
    def run(self):
        try:
            # 1. 모델/엔진 사전 로드
            if not self.tts_engine.load_model():
                err_msg = getattr(self.tts_engine, 'last_error', '') or "TTS 엔진 로드에 실패했습니다."
                self.finished.emit("error", err_msg, self.text)
                return

            # 2. 오디오 합성 실행
            audio_data = self.tts_engine.generate_audio(self.text, speed=self.speed)
            if audio_data:
                os.makedirs(os.path.dirname(self.save_path), exist_ok=True)
                audio_data.export(self.save_path, format="wav")
                self.finished.emit("success", self.save_path, self.text)
            else:
                err_msg = getattr(self.tts_engine, 'last_error', '')
                if not err_msg:
                    err_msg = "오디오 생성에 실패했습니다.\n선택한 음성의 참조 파일이 없거나 엔진 설정 오류입니다.\n'Edge-TTS (초고음질 온라인)' 엔진을 선택해 보세요."
                self.finished.emit("error", err_msg, self.text)
        except Exception as e:
            self.finished.emit("error", f"생성 중 에러 발생: {e}", self.text)

class AudioEditorTab(QWidget):
    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window
        self.last_dir = ""
        self.bgm_file_path = ""
        self.bgm_length = 0
        self.current_time = 0.0
        self.is_playing = False
        self._was_playing = False
        self.processor = None
        self.auto_mix_path = os.path.join(os.getcwd(), "projects", "temp_tts", "auto_mix.wav")
        self.is_auto_mixing = False
        self.auto_mix_pending = False
        
        pygame.mixer.init()
        self.preview_channel = pygame.mixer.Channel(1)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_slider)
        
        self.auto_mix_timer = QTimer(self)
        self.auto_mix_timer.setSingleShot(True)
        self.auto_mix_timer.timeout.connect(self.request_background_mix)
        
        os.makedirs("effects", exist_ok=True)
        os.makedirs(os.path.join("projects", "temp_tts"), exist_ok=True)
        
        self.init_ui()
        
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        
        # --- 1. 상단: 플레이어 및 타임라인 뷰어 ---
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0,0,0,0)
        
        # 플레이어 컨트롤 패널
        player_layout = QHBoxLayout()
        self.bgm_lbl = QLabel("전체 타임라인 (0.0s)")
        self.bgm_lbl.setStyleSheet("font-weight: bold; color: #2980b9;")
        btn_bgm_load = QPushButton("🎵 오디오(BGM) 추가")
        btn_bgm_load.clicked.connect(self.add_bgm_track)

        # 🏃‍♂️ 실내 셔틀런 음원 자동 생성 마법사 버튼
        self.btn_shuttle_run = QPushButton("🏃‍♂️ 셔틀런 음원 마법사")
        self.btn_shuttle_run.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
                border: 1px solid #0369a1;
            }
            QPushButton:hover { background-color: #0369a1; }
        """)
        self.btn_shuttle_run.clicked.connect(self.open_shuttle_run_wizard)

        # 🥋 겨루기 & 발차기 훈련 음원 마법사 버튼
        self.btn_sparring = QPushButton("🥋 겨루기/발차기 훈련 마법사")
        self.btn_sparring.setStyleSheet("""
            QPushButton {
                background-color: #be185d;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
                border: 1px solid #9d174d;
            }
            QPushButton:hover { background-color: #9d174d; }
        """)
        self.btn_sparring.clicked.connect(self.open_sparring_wizard)
        
        self.time_lbl = QLabel("00:00.0 / 00:00.0")
        self.time_lbl.setFixedWidth(120)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.sliderPressed.connect(self.on_slider_pressed)
        self.slider.sliderReleased.connect(self.on_slider_released)
        
        self.btn_play = QPushButton("▶️ 재생")
        self.btn_pause = QPushButton("⏸️ 일시정지")
        self.btn_stop = QPushButton("⏹️ 처음으로")
        self.btn_play.clicked.connect(self.play_timeline)
        self.btn_pause.clicked.connect(self.pause_timeline)
        self.btn_stop.clicked.connect(self.stop_timeline)
        
        player_layout.addWidget(btn_bgm_load)
        player_layout.addWidget(self.btn_shuttle_run)
        player_layout.addWidget(self.btn_sparring)
        player_layout.addWidget(self.bgm_lbl)
        player_layout.addWidget(self.time_lbl)
        player_layout.addWidget(self.slider)
        player_layout.addWidget(self.btn_play)
        player_layout.addWidget(self.btn_pause)
        player_layout.addWidget(self.btn_stop)
        
        top_layout.addLayout(player_layout)

        # 트랙 볼륨 & 줌 컨트롤 패널
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setContentsMargins(0, 5, 0, 5)
        self.track_vol_sliders = []
        for i in range(3):
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(100)
            slider.setFixedWidth(80)
            slider.sliderReleased.connect(self.trigger_auto_mix)
            self.track_vol_sliders.append(slider)
            ctrl_layout.addWidget(QLabel(f"트랙 {i+1} 볼륨:"))
            ctrl_layout.addWidget(slider)
            
        ctrl_layout.addStretch()
        
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(20, 200) # 20 ~ 200 pps
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(120)
        self.zoom_slider.valueChanged.connect(self.on_zoom_changed)
        ctrl_layout.addWidget(QLabel("🔍 타임라인 줌:"))
        ctrl_layout.addWidget(self.zoom_slider)
        
        top_layout.addLayout(ctrl_layout)
        
        # 타임라인 그래픽 뷰
        self.timeline_view = DAWTimeline()
        self.timeline_view.setMaximumHeight(200) # 3 트랙에 맞춰 높이 제한
        self.timeline_view.itemDropped.connect(self.on_item_dropped_on_timeline)
        self.timeline_view.clipSplitRequested.connect(self.on_clip_split)
        self.timeline_view.clipFadeRequested.connect(self.on_clip_fade)
        self.timeline_view.clipCopyRequested.connect(self.on_clip_copy)
        self.timeline_view.clipDeleteRequested.connect(self.on_clip_delete)
        self.timeline_view.pasteRequested.connect(self.on_paste_requested)
        self.timeline_view.playheadSeek.connect(self.on_playhead_seek)
        self.timeline_view.timelineChanged.connect(self.trigger_auto_mix)
        top_layout.addWidget(self.timeline_view, stretch=0)
        
        # --- 2. 하단: 보관함 및 생성기 ---
        bottom_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0,0,0,0)
        
        # 보관함 (Asset Library)
        lib_group = QGroupBox("🗂️ 만들어둔 소리 보관함 (위 타임라인으로 드래그 하세요)")
        lib_layout = QVBoxLayout()
        self.asset_list = AssetListWidget()
        lib_layout.addWidget(self.asset_list)
        
        btn_add_ext = QPushButton("➕ 외부 효과음/오디오 불러와서 보관함에 넣기")
        btn_add_ext.clicked.connect(self.add_external_asset)
        lib_layout.addWidget(btn_add_ext)
        lib_group.setLayout(lib_layout)

        # 기본 효과음 보관함 자동 적재
        self.load_default_effects_to_library()
        
        # TTS 생성기
        gen_group = QGroupBox("✍️ 즉시 TTS 만들어서 보관함에 넣기")
        gen_layout = QVBoxLayout()
        self.insert_text = QTextEdit()
        self.insert_text.setPlaceholderText("여기에 텍스트를 입력하고 버튼을 누르세요. (예: 다 같이 준비, 하앗!)")
        
        # Mac 환경 자소 분리 및 입력 불가 버그 방지를 위해 QFont 객체로 폰트 지정
        from PyQt6.QtGui import QFont
        font = self.insert_text.font()
        font.setFamily("Apple SD Gothic Neo")
        font.setPointSize(14)
        self.insert_text.setFont(font)
        self.btn_insert = QPushButton("🎙️ TTS 생성 후 보관함에 추가")
        self.btn_insert.setStyleSheet("background-color: #f39c12; color: white; font-weight: bold; padding: 15px;")
        self.btn_insert.clicked.connect(self.generate_tts_to_asset)
        
        # 엔진 상태 표시 줄
        engine_status_layout = QHBoxLayout()
        self.engine_status_lbl = QLabel("확인 중...")
        self.engine_status_lbl.setStyleSheet("color: gray; font-size: 11px;")
        btn_reset_engine = QPushButton("⚠️ 엔진 잠금 강제 해제")
        btn_reset_engine.setStyleSheet("background-color: #c0392b; color: white; font-size: 10px; padding: 3px 6px;")
        btn_reset_engine.setToolTip("이전에 툴갈 이후 엔진이 잠기면 누르세요")
        btn_reset_engine.clicked.connect(self.force_reset_engine)
        engine_status_layout.addWidget(self.engine_status_lbl)
        engine_status_layout.addWidget(btn_reset_engine)
        
        gen_layout.addWidget(self.insert_text)
        gen_layout.addWidget(self.btn_insert)
        gen_layout.addLayout(engine_status_layout)
        gen_group.setLayout(gen_layout)
        
        # 엔진 상태 자동 갱신 타이머
        self.engine_status_timer = QTimer(self)
        self.engine_status_timer.timeout.connect(self.refresh_engine_status)
        self.engine_status_timer.start(1000)  # 1초마다 갱신
        
        bottom_layout.addWidget(lib_group, stretch=2)
        bottom_layout.addWidget(gen_group, stretch=1)
        
        # 스플리터로 상하단 크기 조절 가능하게 구성
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(top_widget)
        splitter.addWidget(bottom_widget)
        splitter.setSizes([400, 200]) # 초기 비율
        
        main_layout.addWidget(splitter, stretch=1)
        
        # --- 3. 최종 출력 ---
        export_group = QGroupBox("🚀 최종 믹싱 및 다운로드")
        export_layout = QVBoxLayout()
        h_export = QHBoxLayout()
        self.format_combo = QComboBox()
        self.format_combo.addItems(["wav", "mp3", "ogg"])
        self.btn_preview_mix = QPushButton("🎧 전체 타임라인 미리듣기")
        self.btn_preview_mix.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; padding: 10px;")
        self.btn_preview_mix.clicked.connect(self.preview_full_mix)
        self.btn_export = QPushButton("🚀 최종 믹싱 파일 저장 (Export)")
        self.btn_export.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold; padding: 10px;")
        self.btn_export.clicked.connect(self.exec_mixing)
        
        h_export.addWidget(QLabel("저장 포맷:"))
        h_export.addWidget(self.format_combo)
        h_export.addWidget(self.btn_preview_mix)
        h_export.addWidget(self.btn_export)
        export_layout.addLayout(h_export)
        self.progress_bar = QProgressBar()
        export_layout.addWidget(self.progress_bar)
        export_group.setLayout(export_layout)
        main_layout.addWidget(export_group)

    def on_zoom_changed(self, val):
        self.timeline_view._apply_zoom(val)

    def trigger_auto_mix(self):
        self.auto_mix_timer.start(500) # 0.5초 디바운스
        
    def request_background_mix(self):
        if self.is_auto_mixing:
            self.auto_mix_pending = True
            return
            
        timeline_data = self.timeline_view.get_timeline_data()
        if not timeline_data:
            # 타임라인이 비었음
            self.bgm_length = 0
            self.update_ui_time()
            if os.path.exists(self.auto_mix_path):
                os.remove(self.auto_mix_path)
            return
            
        max_len = 0.0
        for item in timeline_data:
            end_t = item['time'] + item.get('duration', 0.0)
            if end_t > max_len:
                max_len = end_t
                
        # 타임라인 UI 상 전체 길이를 max_len으로 설정하되, 최소 10초
        self.bgm_length = max(max_len, 10.0)
            
        params = {
            'timeline': timeline_data,
            'output': self.auto_mix_path,
            'track_vols': [slider.value() / 100.0 for slider in self.track_vol_sliders]
        }
        
        self.is_auto_mixing = True
        self.bgm_lbl.setText("⚙️ 오디오 믹싱 중...")
        
        self.auto_mixer = AudioProcessorThread("preview", params)
        self.auto_mixer.finished.connect(self.on_auto_mix_finished)
        self.auto_mixer.start()
        
    def on_auto_mix_finished(self, status, msg):
        self.is_auto_mixing = False
        if status == "preview_success":
            try:
                from pydub import AudioSegment
                audio = AudioSegment.from_file(self.auto_mix_path)
                self.bgm_length = len(audio) / 1000.0
                self.bgm_lbl.setText("✅ 실시간 재생 준비 완료")
                self.update_ui_time()
            except Exception:
                pass
        
        if self.auto_mix_pending:
            self.auto_mix_pending = False
            self.request_background_mix()
            
    # --- 플레이어 로직 ---
    def add_bgm_track(self):
        path, _ = QFileDialog.getOpenFileName(self, "오디오(BGM) 추가", self.last_dir, "Audio Files (*.wav *.mp3 *.ogg *.m4a)", options=QFileDialog.Option.DontUseNativeDialog)
        if path:
            self.last_dir = os.path.dirname(path)
            try:
                from pydub import AudioSegment
                audio = AudioSegment.from_file(path)
                duration_sec = len(audio) / 1000.0
                # 1번 트랙(인덱스 0)에 0.0초 위치로 추가
                self.timeline_view.add_clip(f"[BGM] {os.path.basename(path)}", path, 0.0, 0, duration_sec)
            except Exception as e:
                QMessageBox.warning(self, "오류", f"오디오 로드 실패: {e}")
                
    def format_time(self, seconds):
        m = int(seconds // 60)
        s = seconds % 60
        return f"{m:02d}:{s:04.1f}"
        
    def update_ui_time(self):
        self.time_lbl.setText(f"{self.format_time(self.current_time)} / {self.format_time(self.bgm_length)}")
        if self.bgm_length > 0 and not self.slider.isSliderDown():
            val = int((self.current_time / self.bgm_length) * 1000)
            self.slider.blockSignals(True)
            self.slider.setValue(val)
            self.slider.blockSignals(False)
            
    def play_timeline(self):
        if self.is_auto_mixing:
            QMessageBox.information(self, "알림", "오디오 믹싱이 진행 중입니다. 잠시만 기다려주세요.")
            return
        if not os.path.exists(self.auto_mix_path):
            QMessageBox.information(self, "알림", "타임라인에 재생할 클립이 없습니다.")
            return
            
        if not self.is_playing:
            pygame.mixer.music.load(self.auto_mix_path)
            # Pygame music start offset은 초 단위로 동작
            pygame.mixer.music.play(start=self.current_time)
            self.is_playing = True
            self.play_start_time = time.time()
            self.play_start_offset = self.current_time
            self.timer.start(50)
            
    def pause_timeline(self):
        if self.is_playing:
            pygame.mixer.music.pause()
            self.is_playing = False
            self.timer.stop()
        
    def stop_timeline(self):
        pygame.mixer.music.stop()
        self.is_playing = False
        self.timer.stop()
        self.current_time = 0.0
        self.update_ui_time()
        self.timeline_view.set_playhead_time(-1)
        
    def update_slider(self):
        if self.is_playing:
            elapsed = time.time() - self.play_start_time
            self.current_time = self.play_start_offset + elapsed
            if self.current_time >= self.bgm_length and self.bgm_length > 0:
                self.stop_timeline()
                return
            self.update_ui_time()
            self.timeline_view.set_playhead_time(self.current_time)
                
    def on_slider_pressed(self):
        if self.is_playing:
            self.pause_timeline()
            self._was_playing = True
        else:
            self._was_playing = False
            
    def on_slider_released(self):
        val = self.slider.value()
        self.current_time = (val / 1000.0) * self.bgm_length
        self.update_ui_time()
        self.timeline_view.set_playhead_time(self.current_time)
        if self._was_playing:
            self.play_timeline()

    # --- 에셋 관리 및 타임라인 로직 ---
    def generate_tts_to_asset(self):
        text = self.insert_text.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "경고", "생성할 텍스트를 입력하세요.")
            return
        if not self.main_window: return
            
        # 엔진이 이미 1번 탭 등에서 사용 중이면 대기 안내
        if self.main_window.tts_engine.is_busy:
            QMessageBox.warning(self, "생성 불가",
                "현재 다른 탭에서 음성을 생성하는 중입니다.\n"
                "잠시 후 다시 시도해 주세요.")
            return
            
        speed_val = self.main_window.speed_slider.value() / 10.0
        engine_name = self.main_window.engine_combo.currentText()
        voice_name = self.main_window.voice_combo.currentText()
        
        self.main_window.tts_engine.switch_engine(engine_name)
        self.main_window.tts_engine.set_voice(voice_name)
        self.main_window.tts_engine.use_api = False
        
        temp_filename = f"{uuid.uuid4().hex[:8]}.wav"
        save_path = os.path.join("projects", "temp_tts", temp_filename)
        
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.insert_text.clearFocus()
        self.insert_text.setReadOnly(True)
        self.btn_insert.setText("⚙️ 변환 중...")
        
        self.tts_thread = TTSAssetThread(self.main_window.tts_engine, text, speed_val, save_path)
        self.tts_thread.finished.connect(self.on_tts_generated)
        self.tts_thread.start()
        
    def on_tts_generated(self, status, info, text):
        try:
            QApplication.restoreOverrideCursor()
        except:
            pass
        self.insert_text.setReadOnly(False)
        
        if status == "success":
            self.add_asset_item(f"[TTS] {text}", info)
            self.insert_text.clear()
            self.btn_insert.setText("음성 변환 및 삽입")
            QMessageBox.information(self, "변환 완료", "음성 변환이 완료되어 타임라인에 삽입되었습니다!")
        else:
            self.btn_insert.setText("음성 변환 및 삽입")
            QMessageBox.warning(self, "오류", info)

    def refresh_engine_status(self):
        """1초마다 엔진 상태를 확인해서 레이블에 표시"""
        if not self.main_window:
            return
        engine = self.main_window.tts_engine
        if engine.is_busy:
            self.engine_status_lbl.setText("🔴 엔진 사용 중 (생성 중...)")
            self.engine_status_lbl.setStyleSheet("color: #e74c3c; font-size: 11px; font-weight: bold;")
        else:
            self.engine_status_lbl.setText("🟢 엔진 준비됨 (생성 가능)")
            self.engine_status_lbl.setStyleSheet("color: #27ae60; font-size: 11px;")

    def force_reset_engine(self):
        """Segfault 후 is_busy가 잠긴 경우 강제로 초기화"""
        if not self.main_window:
            return
        self.main_window.tts_engine.is_busy = False
        QApplication.restoreOverrideCursor()
        self.insert_text.setDisabled(False)
        QMessageBox.information(self, "초기화 완료",
            "엔진 잠금이 강제로 해제되었습니다.\n이제 다시 TTS 생성이 가능합니다.")

    def add_external_asset(self):
        path, _ = QFileDialog.getOpenFileName(self, "오디오 파일 선택", self.last_dir, "Audio Files (*.wav *.mp3 *.m4a)", options=QFileDialog.Option.DontUseNativeDialog)
        if path:
            self.last_dir = os.path.dirname(path)
            self.add_asset_item(f"[효과음] {os.path.basename(path)}", path)
            
    def add_asset_item(self, display_text, file_path):
        item = QListWidgetItem(display_text)
        item.setData(Qt.ItemDataRole.UserRole, file_path)
        self.asset_list.addItem(item)
        
    def on_item_dropped_on_timeline(self, text, file_path, time_sec, track_idx):
        from pydub import AudioSegment
        try:
            audio = AudioSegment.from_file(file_path)
            duration_sec = len(audio) / 1000.0
        except Exception as e:
            QMessageBox.warning(self, "오류", f"오디오 로드 실패: {e}")
            return
            
        self.timeline_view.add_clip(text, file_path, time_sec, track_idx, duration_sec)

    # --- 타임라인 컨텍스트 메뉴 핸들러 ---
    def on_clip_split(self, item):
        cut_time_sec = self.timeline_view.playhead_time - item.time_sec
        if cut_time_sec <= 0 or cut_time_sec >= item.duration_sec:
            QMessageBox.information(self, "알림", "자르기 기준선(빨간 줄)이 클립 중간에 있어야 합니다.")
            return
            
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(item.file_path)
            cut_ms = int(cut_time_sec * 1000)
            part1 = audio[:cut_ms]
            part2 = audio[cut_ms:]
            
            base_name = os.path.basename(item.file_path)
            name, ext = os.path.splitext(base_name)
            
            path1 = os.path.join(os.getcwd(), "projects", "temp_tts", f"{name}_part1_{uuid.uuid4().hex[:4]}{ext}")
            path2 = os.path.join(os.getcwd(), "projects", "temp_tts", f"{name}_part2_{uuid.uuid4().hex[:4]}{ext}")
            
            part1.export(path1, format=ext.replace(".", "") or "wav")
            part2.export(path2, format=ext.replace(".", "") or "wav")
            
            self.timeline_view.scene().removeItem(item)
            self.timeline_view.add_clip(item.text + " (1)", path1, item.time_sec, item.track_idx, cut_time_sec)
            self.timeline_view.add_clip(item.text + " (2)", path2, item.time_sec + cut_time_sec, item.track_idx, part2.duration_seconds)
            
        except Exception as e:
            QMessageBox.warning(self, "오류", f"자르기 중 오류 발생: {e}")

    def on_clip_fade(self, item, fade_type):
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(item.file_path)
            fade_ms = min(1000, len(audio))
            
            if fade_type == "in":
                audio = audio.fade_in(fade_ms)
            else:
                audio = audio.fade_out(fade_ms)
                
            base_name = os.path.basename(item.file_path)
            name, ext = os.path.splitext(base_name)
            new_path = os.path.join(os.getcwd(), "projects", "temp_tts", f"{name}_fade_{uuid.uuid4().hex[:4]}{ext}")
            
            audio.export(new_path, format=ext.replace(".", "") or "wav")
            
            self.timeline_view.scene().removeItem(item)
            self.timeline_view.add_clip(item.text, new_path, item.time_sec, item.track_idx, item.duration_sec)
            
        except Exception as e:
            QMessageBox.warning(self, "오류", f"페이드 효과 적용 중 오류 발생: {e}")

    def on_clip_copy(self, item):
        self.copied_clip = {
            "text": item.text,
            "file_path": item.file_path,
            "duration_sec": item.duration_sec
        }
        QMessageBox.information(self, "복사 완료", f"'{item.text}' 클립이 복사되었습니다.\n원하는 타임라인 빈 공간에서 우클릭 후 붙여넣으세요.")

    def on_clip_delete(self, item):
        self.timeline_view.scene().removeItem(item)
        self.timeline_view.timelineChanged.emit()

    def on_paste_requested(self, time_sec, track_idx):
        if not hasattr(self, 'copied_clip') or not self.copied_clip:
            # 타임라인 복사본이 없으면 보관함 선택 항목 시도
            selected_items = self.asset_list.selectedItems()
            if not selected_items:
                QMessageBox.information(self, "알림", "붙여넣을 클립을 먼저 복사하거나 보관함에서 선택하세요.")
                return
            item = selected_items[0]
            file_path = item.data(Qt.ItemDataRole.UserRole)
            text = item.text()
            try:
                from pydub import AudioSegment
                audio = AudioSegment.from_file(file_path)
                duration_sec = len(audio) / 1000.0
                self.timeline_view.add_clip(text, file_path, time_sec, track_idx, duration_sec)
            except Exception as e:
                QMessageBox.warning(self, "오류", f"오디오 로드 실패: {e}")
            return
            
        # 복사된 클립 붙여넣기
        c = self.copied_clip
        self.timeline_view.add_clip(c["text"] + " (복사본)", c["file_path"], time_sec, track_idx, c["duration_sec"])

    def on_playhead_seek(self, time_sec, is_release):
        self.current_time = time_sec
        self.update_ui_time()
        if is_release and self.is_playing:
            self.is_playing = False # 일시정지 상태로 만들어서 play_timeline이 동작하게 함
            self.play_timeline() # 플레이헤드 이동 시 재생 위치 재개

    # --- 믹싱 로직 ---
    def preview_full_mix(self):
        timeline_data = self.timeline_view.get_timeline_data()
        if not timeline_data:
            QMessageBox.warning(self, "경고", "배치된 클립이 없습니다.")
            return
            
        output_file = os.path.join(os.getcwd(), "projects", "temp_tts", "preview_mix.wav")
        params = {
            'timeline': timeline_data,
            'output': output_file,
            'track_vols': [slider.value() / 100.0 for slider in self.track_vol_sliders]
        }
        
        self.btn_export.setEnabled(False)
        self.btn_preview_mix.setEnabled(False)
        self.btn_preview_mix.setText("⚙️ 전체 타임라인 믹싱 중... (잠시만 기다려주세요)")
        QApplication.processEvents()
        self.processor = AudioProcessorThread("preview", params)
        self.processor.progress.connect(self.progress_bar.setValue)
        self.processor.finished.connect(self.on_process_finished)
        self.processor.start()

    def exec_mixing(self):
        timeline_data = self.timeline_view.get_timeline_data()
        if not timeline_data:
            QMessageBox.warning(self, "경고", "저장할 오디오가 없습니다.")
            return
            
        fmt = self.format_combo.currentText()
        output_file, _ = QFileDialog.getSaveFileName(self, "최종 믹싱 오디오 저장", f"{self.last_dir}/final_mixed.{fmt}", f"Audio Files (*.{fmt})", options=QFileDialog.Option.DontUseNativeDialog)
        
        if output_file:
            self.last_dir = os.path.dirname(output_file)
            params = {
                'timeline': timeline_data,
                'output': output_file,
                'track_vols': [slider.value() / 100.0 for slider in self.track_vol_sliders]
            }
            
            self.btn_export.setEnabled(False)
            self.btn_preview_mix.setEnabled(False)
            self.btn_export.setText("⚙️ 믹싱 및 저장 중... (잠시만 기다려주세요)")
            QApplication.processEvents()
            self.processor = AudioProcessorThread("mix", params)
            self.processor.progress.connect(self.progress_bar.setValue)
            self.processor.finished.connect(self.on_process_finished)
            self.processor.start()
    def on_process_finished(self, status, msg):
        self.btn_export.setEnabled(True)
        self.btn_preview_mix.setEnabled(True)
        self.btn_preview_mix.setText("🎧 전체 타임라인 미리듣기")
        self.btn_export.setText("🚀 최종 믹싱 파일 저장 (Export)")
            
        if status == "success":
            QMessageBox.information(self, "성공", "파일 저장이 완료되었습니다!\n" + msg)
        elif status == "preview_success":
            try:
                pygame.mixer.music.load(msg)
                pygame.mixer.music.play()
                self.is_playing = True
                self.current_time = 0.0
                
                from pydub import AudioSegment
                audio = AudioSegment.from_file(msg)
                self.bgm_length = len(audio) / 1000.0
                self.timer.start(100)
                self.bgm_lbl.setText("🎧 [타임라인 전체 미리듣기 재생 중]")
                QMessageBox.information(self, "미리듣기", "전체 타임라인 믹싱본이 플레이어에서 재생됩니다.")
            except Exception as e:
                QMessageBox.warning(self, "오류", f"재생 실패: {e}")
        else:
            QMessageBox.warning(self, "오류", msg)

    def load_default_effects_to_library(self):
        """기본 필수 효과음 에셋(비프음, 휘슬, 차임벨 등)을 자동 생성 및 보관함에 추가"""
        try:
            ensure_default_effects()
            effects_dir = "effects"
            if not os.path.exists(effects_dir):
                return
                
            labels = {
                "beep.wav": "🔔 [효과음] 880Hz 전자 비프음",
                "whistle.wav": "📢 [효과음] 심판 호각(휘슬)",
                "stage_bell.wav": "🎵 [효과음] 단계 상승 차임벨",
                "countdown.wav": "⏱️ [효과음] 3-2-1 출발 카운트다운",
                "drum.wav": "🥁 [효과음] 대북 타격음"
            }
            
            # 중복 추가 방지: 이미 보관함에 있는지 확인
            existing_paths = set()
            for i in range(self.asset_list.count()):
                it = self.asset_list.item(i)
                if it:
                    existing_paths.add(it.data(Qt.ItemDataRole.UserRole))

            for fname, disp_name in labels.items():
                fpath = os.path.join(effects_dir, fname)
                if os.path.exists(fpath) and fpath not in existing_paths:
                    self.add_asset_item(disp_name, fpath)
        except Exception as e:
            print(f"[AudioEditor] 기본 효과음 로드 경고: {e}")

    def open_shuttle_run_wizard(self):
        """🏃‍♂️ 실내 셔틀런 음원 자동 생성 마법사 열기 및 타임라인 로드"""
        tts_eng = self.main_window.tts_engine if self.main_window else None
        dlg = ShuttleRunDialog(parent=self, tts_engine=tts_eng)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.generated_result:
            res = dlg.generated_result
            clips = res.get("timeline_clips", [])
            if not clips:
                return

            # 기존 타임라인 정리 여부 확인
            if self.timeline_view.get_timeline_data():
                r = QMessageBox.question(
                    self, "타임라인 정리",
                    "현재 타임라인에 기존 클립들이 있습니다.\n기존 클립을 모두 지우고 새 셔틀런 음원으로 교체하시겠습니까?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if r == QMessageBox.StandardButton.Yes:
                    self.timeline_view.clear_all()

            # 클립들을 타임라인에 배치
            for c in clips:
                self.timeline_view.add_clip(
                    c["text"],
                    c["file"],
                    c["time"],
                    c["track"],
                    c["duration"]
                )

            # 플레이어 길이 및 믹싱 트리거
            self.bgm_length = res.get("total_duration_sec", 60.0)
            self.current_time = 0.0
            self.update_ui_time()
            self.trigger_auto_mix()
            
            QMessageBox.information(
                self, "로드 완료",
                f"🎉 {int(res['distance'])}m {res['target_stages']}단계 셔틀런 트랙이 타임라인에 완벽히 로드되었습니다!\n"
                "트랙 1: 배경음악(BGM) | 트랙 2: 신호음(비프/휘슬) | 트랙 3: 음성 안내 및 차임벨\n\n"
                "[▶️ 재생] 버튼을 눌러 소리를 확인해 보세요."
            )

    def open_sparring_wizard(self):
        """🥋 겨루기 & 발차기 훈련 음원 자동 생성 마법사 열기 및 타임라인 로드"""
        tts_eng = self.main_window.tts_engine if self.main_window else None
        dlg = SparringDialog(parent=self, tts_engine=tts_eng)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.generated_result:
            res = dlg.generated_result
            clips = res.get("timeline_clips", [])
            if not clips:
                return

            # 기존 타임라인 정리 여부 확인
            if self.timeline_view.get_timeline_data():
                r = QMessageBox.question(
                    self, "타임라인 정리",
                    "현재 타임라인에 기존 클립들이 있습니다.\n기존 클립을 모두 지우고 새 훈련 음원으로 교체하시겠습니까?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if r == QMessageBox.StandardButton.Yes:
                    self.timeline_view.clear_all()

            # 클립들을 타임라인에 배치
            for c in clips:
                self.timeline_view.add_clip(
                    c["text"],
                    c["file"],
                    c["time"],
                    c["track"],
                    c["duration"]
                )

            # 플레이어 길이 및 믹싱 트리거
            self.bgm_length = res.get("total_duration_sec", 60.0)
            self.current_time = 0.0
            self.update_ui_time()
            self.trigger_auto_mix()
            
            mode_name = res.get("mode_name", "겨루기/발차기 훈련")
            QMessageBox.information(
                self, "로드 완료",
                f"🎉 [{mode_name}] 트랙이 타임라인에 완벽히 로드되었습니다!\n"
                "트랙 1: 배경음악(BGM) | 트랙 2: 신호음(호각/비프) | 트랙 3: 훈련 구령 음성\n\n"
                "[▶️ 재생] 버튼을 눌러 소리를 확인해 보세요."
            )

