import sys
import os
import shutil
import platform
import subprocess
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QPushButton, QComboBox, QListWidget,
    QGroupBox, QFileDialog, QMessageBox, QTabWidget, QScrollArea,
    QGroupBox, QFileDialog, QMessageBox, QTabWidget, QScrollArea,
    QProgressBar, QSlider, QInputDialog, QSizePolicy, QRadioButton
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

# 코어 모듈 임포트
from core.tts_engine import TTSEngine
from utils.project_manager import ProjectManager
from utils.model_installer import ModelInstallerThread
import pygame
from PyQt6.QtCore import QThread, pyqtSignal

class GenerateAudioThread(QThread):
    finished_signal = pyqtSignal(str)
    
    def __init__(self, tts_engine, text, speed_val, parent=None):
        super().__init__(parent)
        self.tts_engine = tts_engine
        self.text = text
        self.speed_val = speed_val
        
    def run(self):
        file_path = ""
        try:
            import os
            import uuid
            # 로드가 안되어 있으면 므저 스레드에서 로드 (UI 차단 방지)
            self.tts_engine.load_model()
            audio = self.tts_engine.generate_audio(self.text, speed=self.speed_val)
            if audio:
                os.makedirs(os.path.join("projects", "temp_tts"), exist_ok=True)
                temp_filename = f"gen_{uuid.uuid4().hex[:8]}.wav"
                file_path = os.path.join("projects", "temp_tts", temp_filename)
                audio.export(file_path, format="wav")
        except Exception as e:
            print("오디오 생성 오류:", e)
        finally:
            self.finished_signal.emit(file_path)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TTS 컨트롤 및 AI 마스터 운동 스케줄러 (Qwen3-TTS 탑재)")
        self.resize(1100, 850)
        
        # 앱 창 아이콘 설정
        for icon_path in [
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "icon.png"),
            os.path.join(getattr(sys, '_MEIPASS', ''), "assets", "icon.png") if hasattr(sys, '_MEIPASS') else "",
            os.path.join(os.path.expanduser("~"), ".aimaster_tts", "assets", "icon.png"),
            "assets/icon.png"
        ]:
            if icon_path and os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
                break
        
        self.tts_engine = TTSEngine()
        self.project_manager = ProjectManager()
        
        self.last_dir = ""
        self.installer_thread = None
        self.updater = None
        self.temp_playback_file = ""
        self.playback_state = "STOPPED"
        
        pygame.mixer.init()
        self.preview_channel = pygame.mixer.Channel(2) # 채널 2 사용
        
        self.custom_voice_names = {f"user{i}": f"내 목소리 {i}" for i in range(1, 11)}
        self.init_ui()
        self.connect_signals()
        self.load_saved_project()
        self.refresh_voice_status()
        
    def load_saved_project(self):
        state = self.project_manager.load_state()
        
        # UI 업데이트 중 시그널 발생(연쇄 저장 등) 방지
        self.local_input_text.blockSignals(True)
        self.api_input_text.blockSignals(True)
        self.engine_combo.blockSignals(True)
        self.voice_combo.blockSignals(True)
        self.speed_slider.blockSignals(True)
        
        if state.get("custom_voice_names"):
            self.custom_voice_names = state["custom_voice_names"]
        self.update_voice_combo_items()
        
        if state.get("local_input_text"):
            self.local_input_text.setText(state["local_input_text"])
        if state.get("api_input_text"):
            self.api_input_text.setText(state["api_input_text"])
        if state.get("last_dir"):
            self.last_dir = state["last_dir"]
        if state.get("engine_combo"):
            self.engine_combo.setCurrentText(state["engine_combo"])
        if state.get("voice_combo"):
            self.voice_combo.setCurrentText(state["voice_combo"])
        if state.get("speed_slider"):
            self.speed_slider.setValue(state["speed_slider"])
            self.on_speed_changed(state["speed_slider"])
        self.update_custom_voice_ui()
            
        self.local_input_text.blockSignals(False)
        self.api_input_text.blockSignals(False)
        self.engine_combo.blockSignals(False)
        self.voice_combo.blockSignals(False)
        self.speed_slider.blockSignals(False)
        
        # 엔진 변경 처리는 수동으로 1회 호출
        self.on_engine_changed(self.engine_combo.currentText())
            
    def auto_save_state(self):
        state_dict = {
            "local_input_text": self.local_input_text.toPlainText(),
            "api_input_text": self.api_input_text.toPlainText(),
            "last_dir": getattr(self, "last_dir", ""),
            "engine_combo": getattr(self, "engine_combo", type("Dummy",(),{"currentText":lambda: ""})).currentText(),
            "voice_combo": getattr(self, "voice_combo", type("Dummy",(),{"currentText":lambda: ""})).currentText(),
            "speed_slider": getattr(self, "speed_slider", type("Dummy",(),{"value":lambda: 10})).value(),
            "custom_voice_names": getattr(self, "custom_voice_names", {})
        }
        
        if hasattr(self, 'scheduler_tab'):
            self.scheduler_tab.save_state()
            
        import json
        import os
        try:
            os.makedirs("projects", exist_ok=True)
            with open(os.path.join("projects", "last_session.json"), "w", encoding="utf-8") as f:
                json.dump(state_dict, f, ensure_ascii=False, indent=4)
        except Exception:
            pass
            
    def init_ui(self):
        # 상단 메뉴바 구성 (도움말 -> 업데이트 확인)
        menubar = self.menuBar()
        help_menu = menubar.addMenu("도움말(&H)")
        act_update = help_menu.addAction("🔄 최신 업데이트 확인")
        act_update.triggered.connect(self.manual_check_update)
        act_about = help_menu.addAction("ℹ️ 프로그램 정보")
        act_about.triggered.connect(self.show_about_dialog)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # 최상단 헤더 바 (앱 타이틀 및 업데이트 확인 버튼)
        top_bar = QHBoxLayout()
        from utils.auto_updater import AutoUpdater
        cur_v = AutoUpdater().current_version
        title_lbl = QLabel(f"🎙️ AI 마스터 TTS 컨트롤러 (v{cur_v})")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #2563eb;")
        top_bar.addWidget(title_lbl)
        top_bar.addStretch()
        
        self.btn_check_update = QPushButton("🔄 최신 업데이트 확인")
        self.btn_check_update.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: white;
                font-weight: bold;
                padding: 4px 12px;
                border-radius: 4px;
                border: 1px solid #1d4ed8;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
        """)
        self.btn_check_update.clicked.connect(self.manual_check_update)
        top_bar.addWidget(self.btn_check_update)
        left_layout.addLayout(top_bar)
        
        self.tabs = QTabWidget()
        
        # ----------------------------------------------------
        # [탭 1] TTS 엔진 및 목소리 설정 (기존 1,3번 통합)
        # ----------------------------------------------------
        tab1 = QWidget()
        tab1_layout = QVBoxLayout(tab1)
        
        # 1. 엔진 선택 파트
        engine_group = QGroupBox("TTS 인공지능 엔진 및 모델 선택")
        engine_layout = QVBoxLayout()
        
        h_engine = QHBoxLayout()
        self.engine_combo = QComboBox()
        self.engine_combo.addItems([
            "Edge-TTS (초고음질 온라인)",
            "Qwen3-TTS (0.6B)",
            "Qwen3-TTS (1.7B)",
            "Coqui XTTS v2"
        ])
        h_engine.addWidget(QLabel("사용할 엔진:"))
        h_engine.addWidget(self.engine_combo)
        engine_layout.addLayout(h_engine)
        
        # 프로그래스바 (Qwen3 모델 다운로드용)
        self.dl_progress = QProgressBar()
        self.dl_progress.setValue(0)
        self.dl_progress.hide()
        engine_layout.addWidget(self.dl_progress)
        
        self.dl_status = QLabel("엔진을 변경하면 최초 1회 다운로드가 진행될 수 있습니다.")
        self.dl_status.setStyleSheet("color: gray;")
        engine_layout.addWidget(self.dl_status)
        
        engine_group.setLayout(engine_layout)
        tab1_layout.addWidget(engine_group)
        
        # 2. 목소리 및 속도 설정 파트
        voice_group = QGroupBox("목소리 및 출력 속도 설정")
        voice_layout = QVBoxLayout()
        
        h_voice = QHBoxLayout()
        self.voice_combo = QComboBox()
        # Items will be populated by update_voice_combo_items()
        h_voice.addWidget(QLabel("음성 선택:"))
        h_voice.addWidget(self.voice_combo)
        voice_layout.addLayout(h_voice)

        # 모델 특성 및 사용 안내 레이블
        self.voice_desc_lbl = QLabel("")
        self.voice_desc_lbl.setStyleSheet("color: #3498db; font-size: 12px; padding: 2px 4px;")
        self.voice_desc_lbl.setWordWrap(True)
        voice_layout.addWidget(self.voice_desc_lbl)
        
        h_speed = QHBoxLayout()
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setMinimum(5)  # 0.5x
        self.speed_slider.setMaximum(20) # 2.0x
        self.speed_slider.setValue(10)   # 1.0x
        self.speed_label = QLabel("속도: 1.0x")
        h_speed.addWidget(QLabel("출력 속도:"))
        h_speed.addWidget(self.speed_slider)
        h_speed.addWidget(self.speed_label)
        voice_layout.addLayout(h_speed)
        
        voice_group.setLayout(voice_layout)
        tab1_layout.addWidget(voice_group)
        
        # 3. 텍스트 입력 및 스트리밍 파트 (좌우 분할)
        split_layout = QHBoxLayout()
        
        # API 키 불러오기
        self.api_key = None
        self.settings_file = "settings.json"
        self.load_settings()

        # Enter 키 이벤트를 가로채서 바로 렌더링되도록 커스텀
        class CustomTextEdit(QTextEdit):
            def __init__(self, parent=None, layout_ref=None, is_api=False):
                super().__init__(parent)
                self.layout_ref = layout_ref
                self.is_api = is_api
            def keyPressEvent(self, event):
                from PyQt6.QtCore import Qt
                if event.key() == Qt.Key.Key_Return and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                    if self.layout_ref:
                        if self.is_api and hasattr(self.layout_ref, 'api_stream_audio_logic'):
                            self.layout_ref.api_stream_audio_logic()
                        elif not self.is_api and hasattr(self.layout_ref, 'local_stream_audio_logic'):
                            self.layout_ref.local_stream_audio_logic()
                else:
                    super().keyPressEvent(event)

        from PyQt6.QtGui import QFont

        # ==========================================
        # 3-1. 좌측: 로컬 모드 그룹
        # ==========================================
        local_group = QGroupBox("💻 로컬 모드 (오디오 파일 생성/보관함 저장)")
        local_layout = QVBoxLayout()

        guide_box = QTextEdit()
        guide_box.setReadOnly(True)
        guide_box.setMaximumHeight(160)
        guide_box.setStyleSheet(
            "background-color: #fef9e7; color: #784212; "
            "border: 1px solid #f0b429; border-radius: 5px; "
            "padding: 8px; font-size: 13px;"
        )
        guide_box.setPlainText(
            "💡 [Qwen3-TTS 0.6B 맞춤 AI 디렉팅 완벽 가이드]  (스크롤 가능)\n"
            "=" * 55 + "\n\n"
            "▶ [1] 에너지/청량조 조절\n"
            "  !  (1개) : 평언   '준비!'   → 형승님조\n"
            "  !! (2개) : 자신감  '시작!!'  → 활기찬 30\n"
            "  !!! (3개): 외침   '하앗!!!' → 고강도 외침\n"
            "  ?  : 끝 올림. '준비 됐는거야?' → 다정하게 잘 됨\n"
            "  ?! : 놀람+경고 혼합. '에?! 개하의?!' → 경트 소리\n\n"
            "▶ [2] 템포 & 휴지 (가장 중요!)\n"
            "  , (쉼표)  : 약 0.2~0.3초 숨고르기.\n"
            "    0.6B는 쉼표 없으면 문장을 너무 빠르게 읽습니다. 반드시 넣으세요!\n"
            "    예) '모아, 뛰어!!' 처럼 동작 사이에 넣기\n"
            "  ... (말줄임표): 약 0.6초 깊은 휴지. 미스터리 효과\n"
            "  \\n (줄바꿈/엔터): 약 0.25초 쉬어갑니다. 동작 교체 시 유용\n"
            "  [딜레이 3초]: 정확히 3초 무음. 음악 비트에 맞출 때 핵심!\n"
            "    예) '준비, [딜레이 2초] 시작!!'\n\n"
            "▶ [3] 한/영 혼용 및 본토 발음 팁\n"
            "  ✅ '현수' 화자: 태그 없이도 영어를 유창한 원어민 발음으로 읽어줍니다!\n"
            "  ✅ '선히'/'인준' 화자: 영어 문장을 $...$ 로 감싸면(예: $Let's go!$) 100% 미국 원어민으로 자동 전환!\n\n"
            "▶ [4] 주의사항\n"
            "  ⚠️ 한 문장이 너무 길면 호흡이 부자연스러울 수 있으니 쉼표(,)를 적극 활용하세요.\n"
            "  ✅ 숫자는 한글로: 1, 2 → '하나, 둘' / 10 → '열'"
        )
        local_layout.addWidget(guide_box)

        self.local_input_text = CustomTextEdit(layout_ref=self, is_api=False)
        self.local_input_text.setPlaceholderText("로컬 텍스트 입력 (예: 다 같이 앞차기 준비, 하앗!) [Enter: 재생 / Shift+Enter: 줄바꿈]")
        font_local = self.local_input_text.font()
        font_local.setFamily("Apple SD Gothic Neo")
        font_local.setPointSize(14)
        self.local_input_text.setFont(font_local)
        local_layout.addWidget(self.local_input_text)

        h_local_action = QHBoxLayout()
        self.local_stream_btn = QPushButton("⚙️ 로컬 렌더링 및 재생 (Enter)")
        self.local_stream_btn.setStyleSheet("background-color: #3498db; color: white; font-weight: bold; padding: 8px;")
        self.local_save_btn = QPushButton("⬇️ 오디오 파일로 저장")
        self.local_save_btn.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold; padding: 8px;")
        h_local_action.addWidget(self.local_stream_btn)
        h_local_action.addWidget(self.local_save_btn)
        local_layout.addLayout(h_local_action)

        h_local_playback = QHBoxLayout()
        self.btn_play = QPushButton("▶️ 재생")
        self.btn_pause = QPushButton("⏸️ 일시정지")
        self.btn_stop = QPushButton("⏹️ 정지")
        self.btn_play.clicked.connect(self.play_temp_audio)
        self.btn_pause.clicked.connect(self.pause_temp_audio)
        self.btn_stop.clicked.connect(self.stop_temp_audio)
        for btn in [self.btn_play, self.btn_pause, self.btn_stop]:
            btn.setStyleSheet("padding: 8px; font-weight: bold;")
            btn.setDisabled(True)
            h_local_playback.addWidget(btn)
        local_layout.addLayout(h_local_playback)

        local_group.setLayout(local_layout)
        split_layout.addWidget(local_group, stretch=1)

        # ==========================================
        # 3-2. 우측: 실시간 즉시 방송 그룹 (무료 Edge-TTS / 유료 API 겸용)
        # ==========================================
        api_group = QGroupBox("⚡ 실시간 즉시 방송 (수업 중 원클릭 송출)")
        api_group.setStyleSheet("QGroupBox { border: 2px solid #e67e22; border-radius: 5px; margin-top: 1ex; } QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top center; padding: 0 3px; color: #e67e22; font-weight: bold; }")
        api_layout = QVBoxLayout()

        api_top_layout = QHBoxLayout()
        self.api_voice_combo = QComboBox()
        self.update_api_voice_combo_items()
        
        self.api_voice_combo.currentIndexChanged.connect(self.on_api_voice_changed)
        
        self.api_key_btn = QPushButton("🔑 유료 API Key 설정")
        self.api_key_btn.setStyleSheet("background-color: #f39c12; color: white; font-weight: bold;")
        self.api_key_btn.clicked.connect(self.setup_api_key)
        
        api_top_layout.addWidget(QLabel("화자 선택:"))
        api_top_layout.addWidget(self.api_voice_combo)
        api_top_layout.addWidget(self.api_key_btn)
        api_layout.addLayout(api_top_layout)

        api_guide = QLabel("※ [무료] 화자는 키 없이 무제한 즉시 송출되며, [유료 API] 화자는 API Key가 필요합니다.")
        api_guide.setStyleSheet("color: #27ae60; font-weight: bold;")
        api_layout.addWidget(api_guide)

        self.api_input_text = CustomTextEdit(layout_ref=self, is_api=True)
        self.api_input_text.setPlaceholderText("실시간 API 텍스트 입력 (예: 다들 조용히 해주세요!) [Enter: 즉시 재생]")
        font_api = self.api_input_text.font()
        font_api.setFamily("Apple SD Gothic Neo")
        font_api.setPointSize(16) # 좀 더 크게
        self.api_input_text.setFont(font_api)
        api_layout.addWidget(self.api_input_text)

        self.api_stream_btn = QPushButton("⚡ 즉시 말하기 (Enter)")
        self.api_stream_btn.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold; padding: 12px; font-size: 16px;")
        api_layout.addWidget(self.api_stream_btn)

        self.api_stop_btn = QPushButton("⏹️ API 음성 정지")
        self.api_stop_btn.setStyleSheet("padding: 8px; font-weight: bold;")
        self.api_stop_btn.clicked.connect(self.stop_temp_audio)
        self.api_stop_btn.setDisabled(True)
        api_layout.addWidget(self.api_stop_btn)

        api_group.setLayout(api_layout)
        split_layout.addWidget(api_group, stretch=1)
        
        # 합치기
        split_container = QWidget()
        split_container.setLayout(split_layout)
        tab1_layout.addWidget(split_container, stretch=1)
        
        # 4. 목소리 복제 등록 (기존 3번 탭 컨텐츠)
        register_group = QGroupBox("내 목소리 복제 등록")
        reg_layout = QVBoxLayout()
        
        guide_label = QLabel("★ 맑은 곳에서 '크고 씩씩한 구령 톤'으로 5~10초 녹음한 파일을 등록하세요.")
        guide_label.setStyleSheet("font-weight: bold;")
        reg_layout.addWidget(guide_label)
        
        from PyQt6.QtWidgets import QScrollArea, QGridLayout
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(150)
        scroll_widget = QWidget()
        self.user_voice_layout = QGridLayout(scroll_widget)
        
        # Populated by update_custom_voice_ui
        scroll_area.setWidget(scroll_widget)
        reg_layout.addWidget(scroll_area)
        
        self.voice_status_lbl = QLabel("상태: 등록 대기중")
        reg_layout.addWidget(self.voice_status_lbl)
        register_group.setLayout(reg_layout)
        tab1_layout.addWidget(register_group)
        

        
        self.tabs.addTab(tab1, "🎙️ TTS 엔진 & 목소리 설정")
        
        # ----------------------------------------------------
        # [탭 2] AI 마스터 (자동 스케줄)
        # ----------------------------------------------------
        from ui.scheduler_tab import SchedulerTab
        self.scheduler_tab = SchedulerTab()
        self.tabs.addTab(self.scheduler_tab, "🧠 AI 마스터 (자동 스케줄)")
        
        # ----------------------------------------------------
        # [탭 3] 음악 편집기 (Audio Editor)
        # ----------------------------------------------------
        from ui.audio_editor_tab import AudioEditorTab
        self.audio_editor_tab = AudioEditorTab(main_window=self)
        self.tabs.addTab(self.audio_editor_tab, "🎵 음악 편집기")
        
        left_layout.addWidget(self.tabs)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(left_panel)
        scroll_area.setStyleSheet("QScrollArea { border: none; }")
        
        main_layout.addWidget(scroll_area)
        
    def update_voice_combo_items(self):
        current = self.voice_combo.currentText()
        self.voice_combo.blockSignals(True)
        self.voice_combo.clear()
        
        engine_name = self.engine_combo.currentText()
        if "Edge-TTS" in engine_name:
            items = [
                "선히 (한국어 여성, 기본 추천)",
                "인준 (한국어 남성, 기본 추천)",
                "현수 (한국어 남성, 다국어)",
                "Jenny (미국 영어 여성)",
                "Guy (미국 영어 남성)",
                "Nanami (일본어 여성)",
                "Xiaoxiao (중국어 여성)",
            ]
            self.voice_combo.addItems(items)
        else:
            custom_items = [f"{self.custom_voice_names.get(f'user{i}', f'내 목소리 {i}')} (voice_samples/user{i}.wav)" for i in range(1, 11)]
            self.voice_combo.addItems(custom_items + [
                "기본 남자 1 (voice_samples/male.wav)",
                "기본 여자 1 (voice_samples/female.wav)",
                "--- Qwen3 내장 기본 목소리 ---",
                "소희 (차분한 여성)",
                "라이언 (중후한 남성)",
                "에이든 (밝은 남성)",
                "오노_안나 (귀여운 여성)",
                "비비안 (활발한 여성)",
                "세레나 (친절한 여성)",
                "Uncle_Fu (엄격한 남성)",
                "딜런 (진지한 남성)",
                "에릭 (차분한 남성)"
            ])
        
        if current:
            idx = self.voice_combo.findText(current)
            if idx >= 0:
                self.voice_combo.setCurrentIndex(idx)
            else:
                self.voice_combo.setCurrentIndex(0)
        else:
            self.voice_combo.setCurrentIndex(0)
        self.voice_combo.blockSignals(False)
        self.update_voice_desc(self.voice_combo.currentText())

    def update_voice_desc(self, voice_name: str):
        """선택된 화자 및 모델에 대한 상세 설명 및 팁을 실시간 표시"""
        vn = (voice_name or "").lower()
        if "현수" in vn:
            desc = "💡 [현수 - 다국어 특화] 한국어+영어 혼용 문장에 가장 추천! 태그 없이도 영어를 유창한 원어민 발음으로 읽어줍니다."
            color = "#27ae60"
        elif "선히" in vn:
            desc = "💡 [선히 - 한국어 여성] 맑고 친절한 표준 아나운서 톤. 체육관 일반 공지, 준비운동 및 수련 안내에 가장 적합합니다."
            color = "#3498db"
        elif "인준" in vn:
            desc = "💡 [인준 - 한국어 남성] 또렷하고 신뢰감 있는 표준 남성 톤. 절도 있는 구령 및 공식 수련 방송에 추천합니다."
            color = "#3498db"
        elif "jenny" in vn or "guy" in vn:
            desc = "💡 [미국 영어 원어민] 100% 미국 본토 발음의 영문 전용 나레이션 보이스입니다."
            color = "#9b59b6"
        elif "소희" in vn:
            desc = "💡 [소희 - Qwen3 로컬 AI] 내 컴퓨터 자체 AI 모델. 인터넷 없이 동작하는 차분한 여성 보이스입니다."
            color = "#e67e22"
        elif "라이언" in vn:
            desc = "💡 [라이언 - Qwen3 로컬 AI] 내 컴퓨터 자체 AI 모델. 묵직하고 중후한 남성 보이스입니다."
            color = "#e67e22"
        elif "user" in vn or "내 목소리" in vn:
            desc = "💡 [내 목소리 복제] 1번 탭 우측 [🎤 등록] 버튼으로 등록하신 관장님의 실제 목소리 톤을 복제하여 송출합니다."
            color = "#e74c3c"
        elif "nanami" in vn:
            desc = "💡 [Nanami - 일본어] 자연스러운 일본어 원어민 음성입니다."
            color = "#1abc9c"
        elif "xiaoxiao" in vn:
            desc = "💡 [Xiaoxiao - 중국어] 자연스러운 중국어(보통화) 원어민 음성입니다."
            color = "#1abc9c"
        else:
            desc = "💡 선택하신 목소리의 고음질 음성 합성 파라미터가 적용되었습니다."
            color = "#7f8c8d"

        if hasattr(self, 'voice_desc_lbl'):
            self.voice_desc_lbl.setText(desc)
            self.voice_desc_lbl.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: bold; padding: 2px 4px;")

    def update_api_voice_combo_items(self):
        current = self.api_voice_combo.currentText()
        self.api_voice_combo.blockSignals(True)
        self.api_voice_combo.clear()
        
        # 1. 무료 Edge-TTS 화자 (API 키 불필요)
        self.api_voice_combo.addItems([
            "[무료] 선히 (Edge-TTS 여성, 추천)",
            "[무료] 인준 (Edge-TTS 남성, 추천)",
            "[무료] 현수 (Edge-TTS 남성)",
        ])
        
        # 2. 유료 알리바바 DashScope 화자
        self.api_voice_combo.addItems([
            "[유료 API] 아나운서 (여성) - 약 1.6원/100자",
            "[유료 API] 아나운서 (남성) - 약 1.6원/100자",
            "[유료 API] 어린이 (여성) - 약 1.6원/100자",
            "[유료 API] 어린이 (남성) - 약 1.6원/100자",
        ])
        
        if hasattr(self, 'custom_api_voices') and self.custom_api_voices:
            self.api_voice_combo.addItems(list(self.custom_api_voices.keys()))
            
        self.api_voice_combo.addItem("✨ 새 커스텀 보이스 추가")
        
        if current:
            idx = self.api_voice_combo.findText(current)
            if idx >= 0:
                self.api_voice_combo.setCurrentIndex(idx)
            else:
                self.api_voice_combo.setCurrentIndex(0)
        else:
            self.api_voice_combo.setCurrentIndex(0)
        self.api_voice_combo.blockSignals(False)

    def update_custom_voice_ui(self):
        # Clear existing layout
        for i in reversed(range(self.user_voice_layout.count())): 
            widget = self.user_voice_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
                
        for i in range(1, 11):
            key = f"user{i}"
            name = self.custom_voice_names.get(key, f"내 목소리 {i}")
            
            lbl = QLabel(name)
            lbl.setStyleSheet("font-weight: bold;")
            
            btn_rename = QPushButton("✏️ 이름")
            btn_rename.clicked.connect(lambda _, idx=i: self.rename_custom_voice(idx))
            
            btn_record = QPushButton("🎤 등록")
            btn_record.clicked.connect(lambda _, idx=i: self._register_speaker(self.custom_voice_names.get(f"user{idx}", f"내 목소리 {idx}"), f"user{idx}.wav"))
            
            self.user_voice_layout.addWidget(lbl, i-1, 0)
            self.user_voice_layout.addWidget(btn_rename, i-1, 1)
            self.user_voice_layout.addWidget(btn_record, i-1, 2)
            
    def rename_custom_voice(self, idx):
        key = f"user{idx}"
        old_name = self.custom_voice_names.get(key, f"내 목소리 {idx}")
        new_name, ok = QInputDialog.getText(self, "이름 변경", "새로운 이름을 입력하세요:", text=old_name)
        if ok and new_name.strip():
            self.custom_voice_names[key] = new_name.strip()
            self.update_custom_voice_ui()
            self.update_voice_combo_items()
            self.auto_save_state()
            self.refresh_voice_status()
        
    def connect_signals(self):
        self.engine_combo.currentTextChanged.connect(self.on_engine_changed)
        self.speed_slider.valueChanged.connect(self.on_speed_changed)
        
        self.local_stream_btn.clicked.connect(self.local_stream_audio_logic)
        self.local_save_btn.clicked.connect(self.on_save_audio)
        self.api_stream_btn.clicked.connect(self.api_stream_audio_logic)
        
        self.local_input_text.textChanged.connect(self.auto_save_state)
        self.api_input_text.textChanged.connect(self.auto_save_state)
        
        self.engine_combo.currentTextChanged.connect(lambda _: self.auto_save_state())
        self.voice_combo.currentTextChanged.connect(self.update_voice_desc)
        self.voice_combo.currentTextChanged.connect(lambda _: self.auto_save_state())
        self.speed_slider.valueChanged.connect(lambda _: self.auto_save_state())

    # --- 램 메모리 확인 (크로스 플랫폼) ---
    def check_system_ram(self):
        try:
            # Mac / Linux
            if platform.system() == "Darwin":
                output = subprocess.check_output(['sysctl', '-n', 'hw.memsize'])
                ram_gb = int(output.strip()) / (1024**3)
                return ram_gb
            elif platform.system() == "Windows":
                # 간단히 Windows 지원 생략 가능하지만 VBS나 wmic로 체크 가능
                output = subprocess.check_output(['wmic', 'computersystem', 'get', 'TotalPhysicalMemory'])
                ram_str = output.decode().split('\\n')[1].strip()
                ram_gb = int(ram_str) / (1024**3)
                return ram_gb
        except Exception as e:
            return 16 # 확인 불가시 안전한 16GB로 간주
        return 16
        
    def _set_ui_locked(self, locked):
        self.local_stream_btn.setDisabled(locked)
        self.local_save_btn.setDisabled(locked)
        self.api_stream_btn.setDisabled(locked)
        
        # 동적으로 생성된 버튼들 잠금 처리
        from PyQt6.QtWidgets import QPushButton
        for i in range(self.user_voice_layout.count()):
            widget = self.user_voice_layout.itemAt(i).widget()
            if isinstance(widget, QPushButton):
                widget.setDisabled(locked)
        
    def on_engine_changed(self, engine_name):
        # 1.7B 선택시 RAM 체크
        if "1.7B" in engine_name:
            ram_gb = self.check_system_ram()
            if ram_gb <= 8.5: # 8GB 램 경고
                QMessageBox.warning(
                    self, "메모리 부족 경고", 
                    f"현재 시스템의 RAM이 {ram_gb:.1f}GB로 파악됩니다.\n"
                    "Qwen3-TTS 1.7B 모델은 8GB 램 환경에서 메모리 부족(OOM)으로 앱이 종료될 위험이 있습니다.\n"
                    "안정적인 사용을 위해 0.6B 모델을 강력히 권장합니다!"
                )
                
        # TTS 엔진 프록시 변경
        self.tts_engine.switch_engine(engine_name)
        self.update_voice_combo_items()
        self.refresh_voice_status()
        
        if "Edge-TTS" in engine_name:
            self.dl_status.setText("Edge-TTS는 별도 다운로드 없이 즉시 고품질 음성을 합성합니다.")
            self.dl_status.setStyleSheet("color: #27ae60; font-weight: bold;")
            self.dl_progress.hide()
            self._set_ui_locked(False)
            return

        # 모델 설치가 필요한 Qwen 엔진의 경우 (의사코드)
        if "Qwen3" in engine_name:
            repo_id = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice" if "0.6B" in engine_name else "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
            self.dl_status.setText(f"{engine_name} 모델 가중치를 확인 및 다운로드 중입니다...")
            self.dl_status.setStyleSheet("color: blue;")
            self.dl_progress.show()
            self.dl_progress.setValue(0)
            
            # 메인스레드 차단 방지 QThread
            self._set_ui_locked(True)
            self.installer_thread = ModelInstallerThread(repo_id=repo_id)
            self.installer_thread.progress.connect(self.dl_progress.setValue)
            self.installer_thread.log.connect(lambda msg: self.dl_status.setText(msg))
            self.installer_thread.finished_signal.connect(self.on_model_download_finished)
            self.installer_thread.start()
        else:
            self.dl_status.setText("Coqui 엔진은 백그라운드에서 로컬 모델을 사용합니다.")
            self.dl_status.setStyleSheet("color: green;")
            self.dl_progress.hide()
            self._set_ui_locked(False)

    def on_model_download_finished(self, success, msg):
        self._set_ui_locked(False)
        if success:
            self.dl_status.setText(f"준비 완료! ({msg})")
            self.dl_status.setStyleSheet("color: green;")
            # 모델 로드 강제 호출
            self.tts_engine.load_model()
        else:
            self.dl_status.setText(f"설치 실패: {msg}")
            self.dl_status.setStyleSheet("color: red;")
            
    def on_speed_changed(self, value):
        speed_val = value / 10.0
        self.speed_label.setText(f"속도: {speed_val}x")
        
    def setup_api_key(self):
        from PyQt6.QtWidgets import QInputDialog, QMessageBox
        key, ok = QInputDialog.getText(self, "API Key 입력", "DashScope API Key를 입력하세요:\\n(발급받은 알리바바 클라우드 키)", text=self.api_key if self.api_key else "")
        if ok and key.strip():
            self.api_key = key.strip()
            self.save_settings()
            QMessageBox.information(self, "성공", "API Key가 저장되었습니다.")

    def load_settings(self):
        import json
        self.custom_api_voices = {}
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.api_key = data.get("api_key", None)
                    self.custom_api_voices = data.get("custom_api_voices", {})
                    # 마이그레이션: 기존 단일 커스텀 보이스가 있으면 추가
                    if "custom_api_voice_id" in data and data["custom_api_voice_id"] and not self.custom_api_voices:
                        self.custom_api_voices["기존 커스텀 보이스"] = data["custom_api_voice_id"]
            except Exception:
                pass

    def save_settings(self):
        import json
        data = {"api_key": getattr(self, 'api_key', None), "custom_api_voices": getattr(self, 'custom_api_voices', {})}
        with open(self.settings_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            
    def on_api_voice_changed(self):
        current_text = self.api_voice_combo.currentText()
        if current_text == "✨ 새 커스텀 보이스 추가":
            from PyQt6.QtWidgets import QInputDialog, QMessageBox
            
            name, ok = QInputDialog.getText(self, "커스텀 보이스 이름", "어떤 목소리인지 이름을 입력하세요:\\n(예: 운동목소리, 부드러운 목소리 등)")
            if not ok or not name.strip():
                self.update_api_voice_combo_items()
                self.api_voice_combo.setCurrentIndex(0)
                return
            name = name.strip()
            
            key, ok = QInputDialog.getText(self, "Custom Voice ID 입력", "알리바바 콘솔에서 발급받은\\nVoice ID를 입력하세요:\\n(예: cosyvoice-xxx)")
            if ok and key.strip():
                if not hasattr(self, 'custom_api_voices'):
                    self.custom_api_voices = {}
                self.custom_api_voices[name] = key.strip()
                self.save_settings()
                QMessageBox.information(self, "성공", f"'{name}' 커스텀 보이스가 추가되었습니다!")
                self.update_api_voice_combo_items()
                self.api_voice_combo.setCurrentText(name)
            else:
                self.update_api_voice_combo_items()
                self.api_voice_combo.setCurrentIndex(0)

    def local_stream_audio_logic(self):
        text = self.local_input_text.toPlainText().strip()
        if not text:
            return
            
        speed_val = self.speed_slider.value() / 10.0
        engine_name = self.engine_combo.currentText()
        self.tts_engine.switch_engine(engine_name)
        self.tts_engine.set_voice(self.voice_combo.currentText())
        self.tts_engine.use_api = False
        self.tts_engine.api_key = self.api_key

        self.local_stream_btn.setDisabled(True)
        self.local_save_btn.setDisabled(True)
        self.dl_status.setText("로컬 렌더링 중...")
        QApplication.processEvents()
        
        self.stream_thread = GenerateAudioThread(self.tts_engine, text, speed_val)
        self.stream_thread.finished_signal.connect(self._on_local_stream_finished)
        self.stream_thread.start()

    def _on_local_stream_finished(self, file_path):
        self.local_stream_btn.setDisabled(False)
        self.local_save_btn.setDisabled(False)
        if file_path:
            self.temp_playback_file = file_path
            self.dl_status.setText("✅ 로컬 렌더링 완료! 재생 중...")
            self.local_stream_btn.setText("✅ 로컬 렌더링 완료 (다시 렌더링)")
            self.btn_play.setDisabled(False)
            self.btn_pause.setDisabled(False)
            self.btn_stop.setDisabled(False)
            self.playback_state = "STOPPED"
            self.play_temp_audio()
            QApplication.processEvents()
            
            # 방금 렌더링한 내용 저장 로직용 (텍스트, 속도, 화자 일치 여부 판별)
            self.last_rendered_text = self.local_input_text.toPlainText().strip()
            self.last_rendered_speed = self.speed_slider.value() / 10.0
            self.last_rendered_voice = self.voice_combo.currentText()
        else:
            self.local_stream_btn.setText("⚙️ 로컬 렌더링 및 재생 (Enter)")
            err_msg = getattr(self.tts_engine, 'last_error', '') or "오류: 렌더링 실패."
            self.dl_status.setText(f"❌ {err_msg}")

    def api_stream_audio_logic(self):
        text = self.api_input_text.toPlainText().strip()
        if not text:
            return

        current_api_text = self.api_voice_combo.currentText()
        speed_val = self.speed_slider.value() / 10.0

        # [무료 모드] Edge-TTS 화자인 경우 API 키 없이 즉시 무료 말하기
        if "[무료]" in current_api_text or "Edge-TTS" in current_api_text:
            self.tts_engine.switch_engine("Edge-TTS (초고음질 온라인)")
            self.tts_engine.set_voice(current_api_text)
            self.tts_engine.use_api = False
            self.dl_status.setText("⚡ [무료] 실시간 음성 생성 중...")
        else:
            # [유료 모드] 알리바바 DashScope API
            if not self.api_key:
                QMessageBox.warning(self, "API Key 필요", "유료 음성을 사용하려면 DashScope API Key를 먼저 설정해주세요.\n무료 사용을 원하시면 '[무료]' 화자를 선택해 주세요.")
                self.setup_api_key()
                if not self.api_key:
                    return

            self.tts_engine.use_api = True
            self.tts_engine.api_key = self.api_key
            if hasattr(self, 'custom_api_voices') and current_api_text in self.custom_api_voices:
                self.tts_engine.api_voice_selection = "커스텀 보이스"
                self.tts_engine.custom_api_voice_id = self.custom_api_voices[current_api_text]
            else:
                self.tts_engine.api_voice_selection = current_api_text
                self.tts_engine.custom_api_voice_id = None
            self.dl_status.setText("⚡ [유료 API] 실시간 생성 중...")

        self.api_stream_btn.setDisabled(True)
        self.api_stop_btn.setDisabled(False)
        QApplication.processEvents()
        
        self.stream_thread = GenerateAudioThread(self.tts_engine, text, speed_val)
        self.stream_thread.finished_signal.connect(self._on_api_stream_finished)
        self.stream_thread.start()

    def _on_api_stream_finished(self, file_path):
        self.api_stream_btn.setDisabled(False)
        if file_path:
            self.temp_playback_file = file_path
            self.dl_status.setText("✅ API 재생 중! (자동 저장됨)")
            self.api_stream_btn.setText("⚡ API 완료 (다시 재생)")
            self.playback_state = "STOPPED"
            
            # API 자동 저장 (돈 낭비 방지)
            import os, shutil, datetime, re
            api_history_dir = os.path.join(os.getcwd(), "projects", "api_history")
            os.makedirs(api_history_dir, exist_ok=True)
            raw_text = self.api_input_text.toPlainText().strip()
            safe_text = re.sub(r'[\\/*?:"<>|\n]', "_", raw_text)[:20]
            timestamp = datetime.datetime.now().strftime("%y%m%d_%H%M%S")
            auto_save_path = os.path.join(api_history_dir, f"API_{timestamp}_{safe_text}.wav")
            try:
                shutil.copy(file_path, auto_save_path)
            except Exception as e:
                print(f"API 자동 저장 실패: {e}")
                
            self.play_temp_audio()
            QApplication.processEvents()
        else:
            self.api_stream_btn.setText("⚡ 즉시 말하기 (Enter)")
            self.dl_status.setText("❌ 오류: API 생성 실패.")

    def play_temp_audio(self):
        if not hasattr(self, 'temp_playback_file') or not self.temp_playback_file: return
        
        # 재생이 자연스럽게 끝난 경우 get_busy()는 False가 됩니다.
        if getattr(self, 'playback_state', 'STOPPED') == "STOPPED" or not pygame.mixer.music.get_busy():
            try:
                # pydub대신 pygame.mixer.music을 활용해 재생/정지/일시정지 완벽 지원
                pygame.mixer.music.load(self.temp_playback_file)
                pygame.mixer.music.play()
                self.playback_state = "PLAYING"
            except Exception as e:
                print("재생 오류:", e)
        elif getattr(self, 'playback_state', 'STOPPED') == "PAUSED":
            pygame.mixer.music.unpause()
            self.playback_state = "PLAYING"
            
    def pause_temp_audio(self):
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.pause()
            self.playback_state = "PAUSED"
        
    def stop_temp_audio(self):
        pygame.mixer.music.stop()
        self.playback_state = "STOPPED"

    def on_save_audio(self):
        text = self.local_input_text.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "경고", "텍스트를 입력해주세요.")
            return
            
        speed_val = self.speed_slider.value() / 10.0
        current_voice = self.voice_combo.currentText()
        
        default_path = os.path.join(self.last_dir, "qwen_output.wav") if self.last_dir else "qwen_output.wav"
        save_path, _ = QFileDialog.getSaveFileName(self, "오디오 저장", default_path, "WAV Files (*.wav)", options=QFileDialog.Option.DontUseNativeDialog)
        
        if not save_path:
            return
            
        self.last_dir = os.path.dirname(save_path)
        self.auto_save_state()
        
        # [핵심] 사용자가 텍스트나 설정을 바꾸지 않고 방금 미리듣기한 것을 그대로 저장하려는 경우
        if (self.temp_playback_file and os.path.exists(self.temp_playback_file) and
            hasattr(self, 'last_rendered_text') and text == getattr(self, 'last_rendered_text', '') and
            speed_val == getattr(self, 'last_rendered_speed', 1.0) and
            current_voice == getattr(self, 'last_rendered_voice', '')):
            import shutil
            shutil.copy(self.temp_playback_file, save_path)
            QMessageBox.information(self, "성공", f"방금 미리듣기 하신 완벽한 오디오를 즉시 저장했습니다!\\n{save_path}")
            return

        # 새로 렌더링이 필요한 경우
        self.tts_engine.set_voice(current_voice)
        self.tts_engine.use_api = False
        self.tts_engine.api_key = self.api_key
        self.tts_engine.load_model()
        
        self.dl_status.setText("오디오 렌더링 중... (최대 수십 초 소요)")
        QApplication.processEvents()
        
        audio = self.tts_engine.generate_audio(text, speed=speed_val)
        if audio:
            audio.export(save_path, format="wav")
            QMessageBox.information(self, "성공", f"오디오가 성공적으로 렌더링 및 저장되었습니다.\n{save_path}")
            self.dl_status.setText("저장 완료.")
            self.dl_status.setText("저장 완료.")
        else:
            QMessageBox.warning(self, "오류", "오디오 생성에 실패했습니다.")

    # --- 기존 3번 탭 목소리 관리 로직 ---
    def refresh_voice_status(self):
        engine_raw = self.engine_combo.currentText()
        if "Edge-TTS" in engine_raw:
            self.voice_status_lbl.setText("상태: 초고음질 온라인 클라우드 엔진 (별도 음성 등록 없이 즉시 사용 가능)")
            self.voice_status_lbl.setStyleSheet("color: #27ae60; font-weight: bold;")
            return

        status_text = []
        engine_name = "Qwen3" if "Qwen3" in engine_raw else "Coqui"
        
        for i in range(1, 11):
            if os.path.exists(os.path.join("voice_samples", engine_name, f"user{i}.wav")):
                name = self.custom_voice_names.get(f"user{i}", f"내 목소리 {i}")
                status_text.append(f"✅ {name} ({engine_name})")
            
        if status_text:
            self.voice_status_lbl.setText("현재 선택된 엔진에 등록됨:\n" + "\n".join(status_text))
            self.voice_status_lbl.setStyleSheet("color: green;")
        else:
            self.voice_status_lbl.setText("상태: 현재 로컬 엔진에 등록된 목소리가 없습니다.\n즉시 생성을 원하시면 'Edge-TTS' 엔진을 선택하세요.")
            self.voice_status_lbl.setStyleSheet("color: #e67e22;")
            
    def _register_speaker(self, title, dest_filename):
        file_path, _ = QFileDialog.getOpenFileName(self, f"{title} 파일 선택 (3~10초 분량)", self.last_dir, "Audio Files (*.wav *.m4a *.mp3 *.ogg)", options=QFileDialog.Option.DontUseNativeDialog)
        if file_path:
            self.last_dir = os.path.dirname(file_path)
            self.auto_save_state()
            
            engine_name = "Qwen3" if "Qwen3" in self.engine_combo.currentText() else "Coqui"
            target_dir = os.path.join("voice_samples", engine_name)
            os.makedirs(target_dir, exist_ok=True)
            dest_path = os.path.join(target_dir, dest_filename)
            
            try:
                from pydub import AudioSegment
                import noisereduce as nr
                import soundfile as sf
                import librosa
                import tempfile
                import numpy as np
                
                # 1. librosa로 오디오 로드 (단일 채널로 변환)
                y, sr = librosa.load(file_path, sr=None, mono=True)
                
                # 2. 주변 잡음(화이트 노이즈, 에어컨 소리 등) 자동 제거
                reduced_noise = nr.reduce_noise(y=y, sr=sr, stationary=True, prop_decrease=0.85)
                
                # 3. 앞뒤의 침묵 및 미세한 숨소리 쳐내기 (Trim)
                y_trimmed, _ = librosa.effects.trim(reduced_noise, top_db=25)
                
                # 임시 파일로 저장 후 pydub으로 로드
                temp_wav = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
                sf.write(temp_wav.name, y_trimmed, sr)
                audio = AudioSegment.from_file(temp_wav.name)
                os.remove(temp_wav.name)
                
                # 4. 외계어(Hallucination) 방지: 오디오 길이가 10초(10000ms)를 초과하면 앞부분 8초만 잘라냅니다.
                if len(audio) > 10000:
                    audio = audio[:8000]
                    QMessageBox.warning(self, "오디오 길이 조정", "음성 파일이 너무 깁니다 (10초 초과).\n인공지능의 '외계어 생성' 오류를 방지하기 위해 자동으로 앞부분 8초만 잘라서 등록했습니다.\n\n가장 좋은 품질을 원하신다면 잡음 없는 5~8초 길이의 명확한 음성을 새로 등록해 주세요.")
                
                # 5. 최종 깨끗해진 오디오 저장
                audio.export(dest_path, format="wav")
            except Exception as e:
                QMessageBox.critical(self, "오류", f"오디오 파일 처리 중 오류가 발생했습니다:\n{str(e)}\n\npydub/ffmpeg 설치를 확인해주세요.")
                return
                
            QMessageBox.information(self, "성공", f"{title} 목소리가 등록되었습니다!\nQwen3 엔진이 이 파일의 특징을 캐싱(추출)하여 복제합니다.")
            self.refresh_voice_status()

    def manual_check_update(self):
        from utils.auto_updater import AutoUpdater
        if not hasattr(self, 'updater') or self.updater is None:
            self.updater = AutoUpdater(parent_widget=self)
        self.updater.check_for_updates_async(show_no_update_dialog=True)
        
    def show_about_dialog(self):
        from utils.auto_updater import AutoUpdater
        v = AutoUpdater().current_version
        QMessageBox.information(
            self,
            "프로그램 정보",
            f"🎙️ AI 마스터 (TTS 컨트롤러)\n\n"
            f"• 현재 버전: v{v}\n"
            f"• 개발 및 관리: 라이온 체육관 솔루션\n"
            f"• 최신 배포: GitHub Releases 연동\n"
        )

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # --- 야간 모드 글씨 가려짐 방지 및 폰트 크기 확대 ---
    app.setStyle("Fusion")
    app.setStyleSheet("""
        * { font-size: 14px; }
        QWidget { background-color: #2b2b2b; color: #e0e0e0; }
        QLineEdit, QTextEdit, QComboBox, QListWidget, QProgressBar { background-color: #1e1e1e; color: #ffffff; border: 1px solid #555; }
        QPushButton { background-color: #404040; color: #ffffff; border: 1px solid #555; border-radius: 4px; padding: 5px; }
        QPushButton:hover { background-color: #505050; }
        QTabBar::tab { background: #3a3a3a; padding: 8px 20px; }
        QTabBar::tab:selected { background: #555555; color: #ffffff; font-weight: bold; }
        QGroupBox { border: 1px solid #555; margin-top: 1ex; }
        QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 3px; }
    """)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
