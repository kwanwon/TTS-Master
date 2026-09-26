"""
Shuttle Run Generator Dialog (실내 셔틀런 음원 자동 생성 마법사)
Interactive dialog for martial arts gyms / sports clubs to configure distance, age,
stages, BGM, signal sound, auto-ducking, and stage transition voice cues.
"""

import os
import uuid
import asyncio
import math
from typing import Optional, Dict, Any, List
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QRadioButton,
    QButtonGroup, QSpinBox, QCheckBox, QFileDialog, QMessageBox, QComboBox,
    QProgressBar, QGroupBox, QScrollArea, QWidget, QApplication, QSlider
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

from core.shuttle_run_engine import ShuttleRunEngine
from utils.effects_generator import ensure_default_effects
from pydub import AudioSegment


def vol_pct_to_db(pct: int) -> float:
    """선형 퍼센트(%) 볼륨을 데시벨(dB)로 변환 (0% -> -60dB 무음, 100% -> 0dB)"""
    if pct <= 0:
        return -60.0
    return round(20.0 * math.log10(pct / 100.0), 2)


class ShuttleRunWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str, dict)

    def __init__(self, config: dict, tts_engine=None):
        super().__init__()
        self.config = config
        self.tts_engine = tts_engine

    def run(self):
        try:
            self.progress.emit(5, "설정값 검증 및 신호음 준비 중...")
            ensure_default_effects()

            distance = self.config.get("distance", 10.0)
            preset_key = self.config.get("preset_key", "elementary_low")
            target_stages = self.config.get("target_stages", 10)
            signal_type = self.config.get("signal_type", "beep")
            use_voice = self.config.get("use_voice", True)
            voice_speaker = self.config.get("voice_speaker", "선히 (한국어 여성, 추천)")
            auto_ducking = self.config.get("auto_ducking", True)
            countdown_enabled = self.config.get("countdown_enabled", True)

            # 볼륨 커스텀 설정 읽기 (선형 % -> dB 변환)
            bgm_vol_pct = self.config.get("bgm_vol_pct", 70)
            sig_vol_pct = self.config.get("sig_vol_pct", 120)
            voice_vol_pct = self.config.get("voice_vol_pct", 130)
            duck_db = self.config.get("duck_db", -8.0)

            bgm_vol_db = vol_pct_to_db(bgm_vol_pct)
            sig_vol_db = vol_pct_to_db(sig_vol_pct)
            voice_vol_db = vol_pct_to_db(voice_vol_pct)

            # 1. 신호음 에셋 로드
            signal_file_map = {
                "beep": os.path.join("effects", "beep.wav"),
                "whistle": os.path.join("effects", "whistle.wav"),
                "drum": os.path.join("effects", "drum.wav")
            }
            sig_path = signal_file_map.get(signal_type, os.path.join("effects", "beep.wav"))
            if not os.path.exists(sig_path):
                ensure_default_effects()
            signal_audio = AudioSegment.from_file(sig_path)
            stage_bell_path = os.path.join("effects", "stage_bell.wav")
            stage_bell_audio = AudioSegment.from_file(stage_bell_path) if os.path.exists(stage_bell_path) else None
            countdown_path = os.path.join("effects", "countdown.wav")
            countdown_audio = AudioSegment.from_file(countdown_path) if os.path.exists(countdown_path) else None

            # 2. 카운트다운 시작 딜레이 계산
            start_delay = 5.0 if countdown_enabled else 1.5

            # 3. 셔틀런 단계별 타임스탬프 계산
            self.progress.emit(15, "생체역학적 인터벌 시간 계산 중...")
            schedule = ShuttleRunEngine.calculate_stage_schedule(
                distance=distance,
                preset_key=preset_key,
                target_stages=target_stages,
                stage_duration_sec=60.0,
                start_delay_sec=start_delay
            )

            # 4. 단계별 음성 멘트 생성 (옵션)
            voice_clips = []
            os.makedirs(os.path.join("projects", "temp_tts"), exist_ok=True)
            
            if use_voice:
                for idx, stage_info in enumerate(schedule):
                    st = stage_info["stage"]
                    pct = 20 + int(35 * (idx / len(schedule)))
                    self.progress.emit(pct, f"{st}단계 음성 안내 생성 중...")
                    
                    if st == 1:
                        text = "1단계 출발입니다. 준비하세요!"
                    else:
                        text = f"{st}단계입니다. 조금 더 빠르게 달립니다!"

                    v_path = os.path.join("projects", "temp_tts", f"shuttle_stage_{st}_{uuid.uuid4().hex[:6]}.wav")
                    generated = False

                    # TTS 생성 시도 (Edge-TTS 또는 로컬 tts_engine)
                    try:
                        import edge_tts
                        import io
                        voice_id = "ko-KR-SunHiNeural"
                        if "인준" in voice_speaker:
                            voice_id = "ko-KR-InJoonNeural"
                        elif "현수" in voice_speaker:
                            voice_id = "ko-KR-HyunsuMultilingualNeural"
                            
                        async def _gen(t, v, p):
                            comm = edge_tts.Communicate(t, v)
                            buf = io.BytesIO()
                            async for chunk in comm.stream():
                                if chunk['type'] == 'audio':
                                    buf.write(chunk['data'])
                            buf.seek(0)
                            AudioSegment.from_file(buf, format="mp3").export(p, format="wav")

                        asyncio.run(_gen(text, voice_id, v_path))
                        generated = True
                    except Exception as e_voice:
                        print(f"[Shuttle] Edge-TTS direct fail: {e_voice}, falling back to bell")

                    if generated and os.path.exists(v_path):
                        v_dur = len(AudioSegment.from_file(v_path)) / 1000.0
                        # Insert voice cue 1.5s before or right at stage start
                        cue_time = max(0.0, stage_info["stage_start_sec"] - 1.5) if st > 1 else max(0.0, start_delay - 3.5)
                        voice_clips.append({
                            "text": f"[{st}단계 멘트] {text}",
                            "file": v_path,
                            "time": cue_time,
                            "duration": v_dur,
                            "track": 2,
                            "vol": voice_vol_db
                        })

            # 5. 타임라인 클립 데이터 구성 (트랙 분리: 0=BGM, 1=신호음, 2=음성/효과음)
            self.progress.emit(60, "타임라인 트랙 데이터 구성 중...")
            timeline_clips = []
            duck_segments = []

            # 카운트다운 클립
            if countdown_enabled and countdown_audio:
                timeline_clips.append({
                    "text": "[출발 카운트다운] 3-2-1 출발!",
                    "file": countdown_path,
                    "time": max(0.0, start_delay - 3.6),
                    "duration": len(countdown_audio) / 1000.0,
                    "track": 2,
                    "vol": sig_vol_db
                })
                duck_segments.append((int(max(0.0, start_delay - 3.6) * 1000), int(start_delay * 1000)))

            # 신호음 및 벨소리 클립
            for stage_info in schedule:
                st = stage_info["stage"]
                # 단계 상승 차임벨 (2단계 이상 시작 시점)
                if st > 1 and stage_bell_audio:
                    bell_time = stage_info["stage_start_sec"] - 1.2
                    if bell_time > 0:
                        timeline_clips.append({
                            "text": f"[{st}단계] 딩동 차임벨",
                            "file": stage_bell_path,
                            "time": bell_time,
                            "duration": len(stage_bell_audio) / 1000.0,
                            "track": 2,
                            "vol": sig_vol_db
                        })

                # 비프/휘슬 신호음들
                sig_dur = len(signal_audio) / 1000.0
                for b_idx, b_time in enumerate(stage_info["beeps"]):
                    timeline_clips.append({
                        "text": f"[{st}단계-{b_idx+1}회] 신호음",
                        "file": sig_path,
                        "time": b_time,
                        "duration": sig_dur,
                        "track": 1,
                        "vol": sig_vol_db
                    })
                    # Ducking segment around beep
                    s_ms = int(b_time * 1000)
                    e_ms = s_ms + int(sig_dur * 1000) + 150
                    duck_segments.append((s_ms, e_ms))

            # 음성 멘트 클립 합류
            for vc in voice_clips:
                timeline_clips.append({
                    "text": vc["text"],
                    "file": vc["file"],
                    "time": vc["time"],
                    "duration": vc["duration"],
                    "track": 2,
                    "vol": voice_vol_db
                })
                s_ms = int(vc["time"] * 1000)
                e_ms = s_ms + int(vc["duration"] * 1000)
                duck_segments.append((s_ms, e_ms))

            # 6. BGM 트랙 준비 및 길이 맞춤 (다중 BGM 크로스페이드 & 루핑)
            self.progress.emit(75, "배경음악(BGM) 믹싱 및 오토 덕킹 처리 중...")
            total_duration_sec = schedule[-1]["stage_end_sec"] + 5.0
            total_duration_ms = int(total_duration_sec * 1000)

            bgm_clip_path = ""
            bgm_paths = self.config.get("bgm_paths", [])
            if not bgm_paths and self.config.get("bgm_path"):
                bgm_paths = [self.config["bgm_path"]]

            valid_bgm = [p for p in bgm_paths if os.path.exists(p)]
            if valid_bgm:
                bgm_raw = ShuttleRunEngine.build_seamless_bgm(
                    valid_bgm,
                    target_duration_ms=total_duration_ms,
                    crossfade_ms=2000
                )

                # 사용자 지정 BGM 볼륨 적용
                if bgm_vol_db != 0.0:
                    bgm_raw = bgm_raw + bgm_vol_db

                # 오토 덕킹 적용
                if auto_ducking and duck_db != 0.0:
                    bgm_raw = ShuttleRunEngine.apply_auto_ducking(bgm_raw, duck_segments, duck_db=duck_db)

                # 덕킹된 BGM 임시 저장
                bgm_clip_path = os.path.join("projects", "temp_tts", f"shuttle_bgm_{uuid.uuid4().hex[:6]}.wav")
                bgm_raw.export(bgm_clip_path, format="wav")

                # BGM 클립을 타임라인 트랙 0에 추가
                bgm_label = f"[BGM {len(valid_bgm)}곡] {os.path.basename(valid_bgm[0])} 외" if len(valid_bgm) > 1 else f"[BGM] {os.path.basename(valid_bgm[0])}"
                timeline_clips.insert(0, {
                    "text": f"{bgm_label} (볼륨 {bgm_vol_pct}%)",
                    "file": bgm_clip_path,
                    "time": 0.0,
                    "duration": total_duration_sec,
                    "track": 0,
                    "vol": 0.0
                })

            # 7. 즉시 합성된 단일 오디오 파일 생성 (Direct Mix)
            self.progress.emit(90, "최종 셔틀런 오디오 합성 중...")
            master_canvas = AudioSegment.silent(duration=total_duration_ms)
            
            for item in timeline_clips:
                if not os.path.exists(item["file"]):
                    continue
                seg = AudioSegment.from_file(item["file"])
                vol_db = item.get("vol", 0.0)
                if vol_db != 0:
                    seg = seg + vol_db
                ins_ms = int(item["time"] * 1000)
                master_canvas = master_canvas.overlay(seg, position=ins_ms)

            # 마스터링
            try:
                master_canvas = normalize(master_canvas)
            except Exception:
                pass

            output_master_path = os.path.join(
                "projects", "temp_tts",
                f"ShuttleRun_{int(distance)}m_{target_stages}stages_{uuid.uuid4().hex[:6]}.wav"
            )
            master_canvas.export(output_master_path, format="wav")

            self.progress.emit(100, "완료!")
            result_data = {
                "schedule": schedule,
                "timeline_clips": timeline_clips,
                "master_audio_path": output_master_path,
                "total_duration_sec": total_duration_sec,
                "distance": distance,
                "target_stages": target_stages
            }
            self.finished.emit(True, "셔틀런 음원이 성공적으로 생성되었습니다.", result_data)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.finished.emit(False, f"셔틀런 생성 중 오류 발생: {str(e)}", {})


class ShuttleRunDialog(QDialog):
    """실내 셔틀런 음원 자동 생성 마법사 UI 다이얼로그"""

    def __init__(self, parent=None, tts_engine=None):
        super().__init__(parent)
        self.tts_engine = tts_engine
        self.setWindowTitle("🏃‍♂️ 실내 셔틀런 음원 자동 생성 마법사 (Shuttle Run Generator)")
        self.resize(680, 700)
        self.bgm_playlist: List[str] = []
        self.generated_result = None

        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # 타이틀 안내 배너
        header_box = QGroupBox()
        header_box.setStyleSheet("background-color: #f0f7ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 6px;")
        hb_layout = QVBoxLayout(header_box)
        title_lbl = QLabel("🏃‍♂️ 실내 셔틀런 (왕복달리기) 음원 자동 생성기")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #1e3a8a;")
        desc_lbl = QLabel(
            "도장 실내 규격(5m/10m)에 맞춰 정확한 물리학적 턴 감속 및 인터벌 시간을 자동 계산하고,\n"
            "여러 곡의 BGM(크로스페이드)과 신호음, 단계별 안내 멘트를 오토 덕킹(Auto-Ducking)으로 완벽하게 합성합니다."
        )
        desc_lbl.setStyleSheet("color: #475569; font-size: 12px;")
        hb_layout.addWidget(title_lbl)
        hb_layout.addWidget(desc_lbl)
        main_layout.addWidget(header_box)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)

        # 1. 거리 선택
        dist_group = QGroupBox("1. 왕복 측정 거리 선택 (실내 / 실외)")
        dist_layout = QHBoxLayout()
        self.dist_btn_group = QButtonGroup(self)
        self.rb_dist_5 = QRadioButton("5m (실내 초소형/유치부 특화)")
        self.rb_dist_10 = QRadioButton("10m (도장 실내 표준, 추천)")
        self.rb_dist_20 = QRadioButton("20m (야외/체육관 공인 규격)")
        self.rb_dist_10.setChecked(True)
        
        self.dist_btn_group.addButton(self.rb_dist_5, 5)
        self.dist_btn_group.addButton(self.rb_dist_10, 10)
        self.dist_btn_group.addButton(self.rb_dist_20, 20)
        
        dist_layout.addWidget(self.rb_dist_5)
        dist_layout.addWidget(self.rb_dist_10)
        dist_layout.addWidget(self.rb_dist_20)
        dist_group.setLayout(dist_layout)
        content_layout.addWidget(dist_group)

        # 2. 연령 대상 및 시작 속도
        age_group = QGroupBox("2. 연령 대상 (시작 속도 및 턴 감속 적용)")
        age_layout = QVBoxLayout()
        self.age_btn_group = QButtonGroup(self)
        self.rb_age_kinder = QRadioButton("유치부 (6.5 km/h 시작, 턴 감속 0.75초 고려)")
        self.rb_age_low = QRadioButton("초등 저학년 (8.0 km/h 시작, 턴 감속 0.5초 표준)")
        self.rb_age_high = QRadioButton("초등 고학년 및 청소년 (8.5 km/h 시작, 공인 페이서)")
        self.rb_age_low.setChecked(True)

        self.age_btn_group.addButton(self.rb_age_kinder, 1)
        self.age_btn_group.addButton(self.rb_age_low, 2)
        self.age_btn_group.addButton(self.rb_age_high, 3)

        age_layout.addWidget(self.rb_age_kinder)
        age_layout.addWidget(self.rb_age_low)
        age_layout.addWidget(self.rb_age_high)
        age_group.setLayout(age_layout)
        content_layout.addWidget(age_group)

        # 3. 목표 단계
        stage_group = QGroupBox("3. 목표 단계 설정")
        stage_layout = QHBoxLayout()
        stage_layout.addWidget(QLabel("완주 목표 단계:"))
        self.stage_spin = QSpinBox()
        self.stage_spin.setRange(1, 15)
        self.stage_spin.setValue(8)
        self.stage_spin.setSuffix(" 단계 (기본 8단계 약 8분)")
        self.stage_spin.setFixedWidth(200)
        stage_layout.addWidget(self.stage_spin)
        stage_layout.addStretch()
        stage_group.setLayout(stage_layout)
        content_layout.addWidget(stage_group)

        # 4. 배경음악(BGM) 선택 (여러 곡 다중 선택 지원)
        bgm_group = QGroupBox("4. 배경음악 (BGM) 선택 (여러 곡 선택 시 자동 크로스페이드 연결)")
        bgm_layout = QVBoxLayout()
        h_bgm_btns = QHBoxLayout()
        btn_browse_bgm = QPushButton("📁 음악 파일 추가 (다중 선택 가능)...")
        btn_browse_bgm.clicked.connect(self.browse_bgm)
        btn_clear_bgm = QPushButton("❌ 전체 제거")
        btn_clear_bgm.clicked.connect(self.clear_bgm)
        h_bgm_btns.addWidget(btn_browse_bgm)
        h_bgm_btns.addWidget(btn_clear_bgm)
        h_bgm_btns.addStretch()
        bgm_layout.addLayout(h_bgm_btns)

        self.bgm_label = QLabel("선택된 음악 없음 (효과음만 생성)")
        self.bgm_label.setStyleSheet("color: #64748b; font-style: italic; padding: 4px;")
        self.bgm_label.setWordWrap(True)
        bgm_layout.addWidget(self.bgm_label)
        bgm_group.setLayout(bgm_layout)
        content_layout.addWidget(bgm_group)

        # 5. 신호음 종류 선택
        sig_group = QGroupBox("5. 신호음 (턴 비프음) 종류 선택")
        sig_layout = QHBoxLayout()
        self.sig_combo = QComboBox()
        self.sig_combo.addItem("🔔 기본 전자 비프음 (880Hz 선명한 공인 비프)", "beep")
        self.sig_combo.addItem("📢 경기용 심판 휘슬 (2500Hz 고주파 호각)", "whistle")
        self.sig_combo.addItem("🥁 웅장한 대북/타격음 (기합 및 절도 있는 타격)", "drum")
        
        btn_preview_sig = QPushButton("🎧 효과음 미리듣기")
        btn_preview_sig.clicked.connect(self.preview_signal_sound)
        
        sig_layout.addWidget(self.sig_combo, stretch=1)
        sig_layout.addWidget(btn_preview_sig)
        sig_group.setLayout(sig_layout)
        content_layout.addWidget(sig_group)

        # 6. 개별 음량(BGM / 비프음 / TTS) 및 오토덕킹 밸런스 커스텀
        vol_group = QGroupBox("6. 🎚️ 개별 음량(BGM / 비프음 / TTS) 및 오토덕킹 커스텀")
        vol_group.setStyleSheet("QGroupBox { font-weight: bold; color: #1e3a8a; }")
        vol_layout = QVBoxLayout()

        # 볼륨 슬라이더 1: 배경음악(BGM)
        h_v1 = QHBoxLayout()
        h_v1.addWidget(QLabel("🎵 배경음악(BGM) 음량:"))
        self.slider_bgm_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_bgm_vol.setRange(0, 150)
        self.slider_bgm_vol.setValue(70)
        self.lbl_bgm_vol = QLabel("70%")
        self.lbl_bgm_vol.setFixedWidth(45)
        self.slider_bgm_vol.valueChanged.connect(lambda v: self.lbl_bgm_vol.setText(f"{v}%"))
        h_v1.addWidget(self.slider_bgm_vol)
        h_v1.addWidget(self.lbl_bgm_vol)
        vol_layout.addLayout(h_v1)

        # 볼륨 슬라이더 2: 비프/신호음
        h_v2 = QHBoxLayout()
        h_v2.addWidget(QLabel("🔔 신호음(비프/휘슬) 음량:"))
        self.slider_sig_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_sig_vol.setRange(20, 200)
        self.slider_sig_vol.setValue(120)
        self.lbl_sig_vol = QLabel("120%")
        self.lbl_sig_vol.setFixedWidth(45)
        self.slider_sig_vol.valueChanged.connect(lambda v: self.lbl_sig_vol.setText(f"{v}%"))
        h_v2.addWidget(self.slider_sig_vol)
        h_v2.addWidget(self.lbl_sig_vol)
        vol_layout.addLayout(h_v2)

        # 볼륨 슬라이더 3: TTS 음성 구령
        h_v3 = QHBoxLayout()
        h_v3.addWidget(QLabel("🗣️ 음성 구령(TTS) 음량:"))
        self.slider_voice_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_voice_vol.setRange(20, 200)
        self.slider_voice_vol.setValue(130)
        self.lbl_voice_vol = QLabel("130%")
        self.lbl_voice_vol.setFixedWidth(45)
        self.slider_voice_vol.valueChanged.connect(lambda v: self.lbl_voice_vol.setText(f"{v}%"))
        h_v3.addWidget(self.slider_voice_vol)
        h_v3.addWidget(self.lbl_voice_vol)
        vol_layout.addLayout(h_v3)

        # 덕킹 강도 & 프리셋
        h_v4 = QHBoxLayout()
        h_v4.addWidget(QLabel("📉 오토덕킹 강도:"))
        self.combo_duck_level = QComboBox()
        self.combo_duck_level.addItem("보통 감쇄 (-8 dB) - 기본 추천", -8.0)
        self.combo_duck_level.addItem("강한 감쇄 (-12 dB) - 신호음/구령 극대화", -12.0)
        self.combo_duck_level.addItem("부드러운 감쇄 (-4 dB) - 음악 비트 유지", -4.0)
        self.combo_duck_level.addItem("최대 감쇄 (-16 dB) - 음악 거의 음소거", -16.0)
        self.combo_duck_level.addItem("오토덕킹 끄기 (0 dB 감쇄 없음)", 0.0)
        h_v4.addWidget(self.combo_duck_level)

        btn_preset_default = QPushButton("기본 밸런스")
        btn_preset_music = QPushButton("음악 중심")
        btn_preset_voice = QPushButton("구령·신호 극대화")
        btn_preset_default.clicked.connect(lambda: self.set_vol_preset(70, 120, 130, 0))
        btn_preset_music.clicked.connect(lambda: self.set_vol_preset(100, 130, 120, 2))
        btn_preset_voice.clicked.connect(lambda: self.set_vol_preset(50, 160, 160, 1))
        h_v4.addWidget(btn_preset_default)
        h_v4.addWidget(btn_preset_music)
        h_v4.addWidget(btn_preset_voice)
        vol_layout.addLayout(h_v4)

        vol_group.setLayout(vol_layout)
        content_layout.addWidget(vol_group)

        # 7. 음성 안내 및 시작 카운트다운 옵션
        opt_group = QGroupBox("7. 음성 안내 및 시작 카운트다운 옵션")
        opt_layout = QVBoxLayout()
        
        self.cb_countdown = QCheckBox("시작 전 '3-2-1 출발!' 카운트다운 효과음 포함")
        self.cb_countdown.setChecked(True)
        opt_layout.addWidget(self.cb_countdown)

        h_voice = QHBoxLayout()
        self.cb_voice = QCheckBox("단계 상승 시 음성 안내 멘트 송출 ('N단계입니다. 더 빠르게 달립니다!')")
        self.cb_voice.setChecked(True)
        self.voice_combo = QComboBox()
        self.voice_combo.addItems([
            "선히 (한국어 여성, 표준 아나운서)",
            "인준 (한국어 남성, 또렷한 구령)",
            "현수 (한국어 남성, 차분한 코칭)"
        ])
        h_voice.addWidget(self.cb_voice)
        h_voice.addWidget(self.voice_combo)
        opt_layout.addLayout(h_voice)

        self.cb_ducking = QCheckBox("🎵 BGM 오토 덕킹(Auto-Ducking) 적용 (신호음 및 멘트 송출 시 BGM 자동 감쇄)")
        self.cb_ducking.setChecked(True)
        opt_layout.addWidget(self.cb_ducking)

        opt_group.setLayout(opt_layout)
        content_layout.addWidget(opt_group)

        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll, stretch=1)

        # 진행바 및 상태 레이블
        self.status_lbl = QLabel("설정을 완료한 후 아래 [생성하기] 버튼을 누르세요.")
        self.status_lbl.setStyleSheet("color: #2563eb; font-weight: bold;")
        main_layout.addWidget(self.status_lbl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # 하단 액션 버튼
        btn_box = QHBoxLayout()
        self.btn_generate = QPushButton("🚀 셔틀런 음원 생성하기")
        self.btn_generate.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 20px;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #1d4ed8; }
        """)
        self.btn_generate.clicked.connect(self.start_generation)

        btn_cancel = QPushButton("닫기")
        btn_cancel.clicked.connect(self.reject)
        
        btn_box.addStretch()
        btn_box.addWidget(self.btn_generate)
        btn_box.addWidget(btn_cancel)
        main_layout.addLayout(btn_box)

    def browse_bgm(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "배경음악(BGM) 다중 선택 (여러 곡 가능)", "",
            "Audio Files (*.mp3 *.wav *.ogg *.m4a)",
            options=QFileDialog.Option.DontUseNativeDialog
        )
        if file_paths:
            for fp in file_paths:
                if fp not in self.bgm_playlist:
                    self.bgm_playlist.append(fp)
            self._update_bgm_label()

    def _update_bgm_label(self):
        if not self.bgm_playlist:
            self.bgm_label.setText("선택된 음악 없음 (효과음만 생성)")
            self.bgm_label.setStyleSheet("color: #64748b; font-style: italic; padding: 4px;")
        else:
            names = [os.path.basename(p) for p in self.bgm_playlist]
            if len(names) <= 3:
                display_str = ", ".join(names)
            else:
                display_str = f"{names[0]}, {names[1]} 외 {len(names)-2}곡"
            self.bgm_label.setText(f"🎶 총 {len(self.bgm_playlist)}곡 선택됨: {display_str} (자연스러운 크로스페이드 연결)")
            self.bgm_label.setStyleSheet("color: #16a34a; font-weight: bold; padding: 4px;")

    def clear_bgm(self):
        self.bgm_playlist = []
        self._update_bgm_label()

    def preview_signal_sound(self):
        sig_type = self.sig_combo.currentData()
        file_path = os.path.join("effects", f"{sig_type}.wav")
        if not os.path.exists(file_path):
            ensure_default_effects()
        if os.path.exists(file_path):
            try:
                import pygame
                pygame.mixer.init()
                sound = pygame.mixer.Sound(file_path)
                sound.play()
            except Exception as e:
                QMessageBox.warning(self, "미리듣기 실패", f"효과음 재생 실패: {e}")

    def set_vol_preset(self, bgm: int, sig: int, voice: int, duck_idx: int):
        self.slider_bgm_vol.setValue(bgm)
        self.slider_sig_vol.setValue(sig)
        self.slider_voice_vol.setValue(voice)
        self.combo_duck_level.setCurrentIndex(duck_idx)

    def start_generation(self):
        dist_val = self.dist_btn_group.checkedId()
        age_id = self.age_btn_group.checkedId()
        preset_map = {1: "kinder", 2: "elementary_low", 3: "elementary_high_teen"}
        preset_key = preset_map.get(age_id, "elementary_low")

        duck_db_val = self.combo_duck_level.currentData()
        if duck_db_val is None:
            duck_db_val = -8.0

        config = {
            "distance": float(dist_val),
            "preset_key": preset_key,
            "target_stages": self.stage_spin.value(),
            "bgm_paths": list(self.bgm_playlist),
            "bgm_path": self.bgm_playlist[0] if self.bgm_playlist else "",
            "signal_type": self.sig_combo.currentData(),
            "use_voice": self.cb_voice.isChecked(),
            "voice_speaker": self.voice_combo.currentText(),
            "auto_ducking": self.cb_ducking.isChecked(),
            "countdown_enabled": self.cb_countdown.isChecked(),
            "bgm_vol_pct": self.slider_bgm_vol.value(),
            "sig_vol_pct": self.slider_sig_vol.value(),
            "voice_vol_pct": self.slider_voice_vol.value(),
            "duck_db": duck_db_val
        }

        self.btn_generate.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_lbl.setText("셔틀런 음원 계산 및 합성 중입니다. 잠시만 기다려주세요...")

        self.worker = ShuttleRunWorker(config, tts_engine=self.tts_engine)
        self.worker.progress.connect(self.on_worker_progress)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

    def on_worker_progress(self, val: int, msg: str):
        self.progress_bar.setValue(val)
        self.status_lbl.setText(msg)

    def on_worker_finished(self, success: bool, msg: str, result_data: dict):
        self.btn_generate.setEnabled(True)
        self.progress_bar.setVisible(False)

        if success:
            self.generated_result = result_data
            self.status_lbl.setText("✅ 셔틀런 음원 생성 완료!")
            
            # 사용자에게 로드 및 저장 옵션 제공
            reply = QMessageBox.question(
                self,
                "셔틀런 음원 생성 완료",
                "🎉 실내 셔틀런 음원이 성공적으로 생성되었습니다!\n\n"
                f"- 총 거리: {result_data['distance']}m\n"
                f"- 총 단계: {result_data['target_stages']}단계 (소요 시간: 약 {int(result_data['total_duration_sec']//60)}분 {int(result_data['total_duration_sec']%60)}초)\n\n"
                "지금 바로 음악 편집기 타임라인에 트랙별(BGM/신호음/멘트)로 로드하시겠습니까?\n"
                "(로드 후 타임라인에서 재생 및 추가 미세 편집이 가능합니다.)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.accept()
            else:
                # 직접 저장할 것인지 문의
                save_reply = QMessageBox.question(
                    self, "파일 직접 저장",
                    "합성된 완성본 오디오(WAV)를 파일로 바로 저장하시겠습니까?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if save_reply == QMessageBox.StandardButton.Yes:
                    save_path, _ = QFileDialog.getSaveFileName(
                        self, "셔틀런 음원 저장",
                        f"실내셔틀런_{int(result_data['distance'])}m_{result_data['target_stages']}단계.wav",
                        "Audio Files (*.wav *.mp3)",
                        options=QFileDialog.Option.DontUseNativeDialog
                    )
                    if save_path:
                        import shutil
                        shutil.copy(result_data["master_audio_path"], save_path)
                        QMessageBox.information(self, "저장 완료", f"파일이 성공적으로 저장되었습니다:\n{save_path}")
                self.accept()
        else:
            self.status_lbl.setText(f"❌ {msg}")
            QMessageBox.critical(self, "생성 실패", msg)
