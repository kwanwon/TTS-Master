"""
Sparring & Kicking Training Dialog (겨루기 & 발차기 트레이닝 음원 생성 마법사)
Supports customized training for dojos:
- 1:1, 1:2, 1:3 Relay kicking (다자간 미트 순환)
- Reaction kicking (스텝 & 1연타/2연타/받아차기 반사 반응)
- Combo interval kicking (스텝 + 콤비네이션 연타)
- Sparring round simulator (정규 겨루기 라운드)

Allows full customization of cues, times, BGM playlist, and auto-ducking.
"""

import os
import uuid
import asyncio
import math
from typing import Optional, Dict, Any, List
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QRadioButton,
    QButtonGroup, QSpinBox, QDoubleSpinBox, QCheckBox, QFileDialog, QMessageBox, QComboBox,
    QProgressBar, QGroupBox, QScrollArea, QWidget, QLineEdit, QTabWidget, QApplication, QSlider
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from core.sparring_training_engine import SparringTrainingEngine
from core.shuttle_run_engine import ShuttleRunEngine
from utils.effects_generator import ensure_default_effects
from pydub import AudioSegment
from pydub.effects import normalize


def vol_pct_to_db(pct: int) -> float:
    """선형 퍼센트(%) 볼륨을 데시벨(dB)로 변환 (0% -> -60dB 무음, 100% -> 0dB)"""
    if pct <= 0:
        return -60.0
    return round(20.0 * math.log10(pct / 100.0), 2)


class SparringWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str, dict)

    def __init__(self, mode: str, params: dict, bgm_paths: List[str], tts_engine=None):
        super().__init__()
        self.mode = mode
        self.params = params
        self.bgm_paths = bgm_paths
        self.tts_engine = tts_engine

    def run(self):
        try:
            self.progress.emit(5, "훈련 타임테이블 계산 및 신호음 준비 중...")
            ensure_default_effects()

            # 1. 훈련 스케줄 계산
            schedule_data = SparringTrainingEngine.generate_training_schedule(self.mode, self.params)
            events = schedule_data["events"]
            duck_segments = schedule_data["duck_segments"]
            total_duration_sec = schedule_data["total_duration_sec"]
            total_duration_ms = int(total_duration_sec * 1000)

            # 2. 음성 멘트 합성 (Edge-TTS 활용)
            use_voice = self.params.get("use_voice", True)
            voice_speaker = self.params.get("voice_speaker", "선히")
            voice_id = "ko-KR-SunHiNeural"
            if "인준" in voice_speaker:
                voice_id = "ko-KR-InJoonNeural"
            elif "현수" in voice_speaker:
                voice_id = "ko-KR-HyunsuMultilingualNeural"

            os.makedirs(os.path.join("projects", "temp_tts"), exist_ok=True)
            voice_cache = {}

            voice_events = [ev for ev in events if ev["type"] == "voice"]
            for idx, ev in enumerate(voice_events):
                pct = 15 + int(45 * ((idx + 1) / max(len(voice_events), 1)))
                text = ev["text"]
                # Clean text for TTS (remove [bracketed tags])
                clean_text = text
                if "[" in text and "]" in text:
                    parts = text.split("]", 1)
                    clean_text = parts[1].strip() if len(parts) > 1 and parts[1].strip() else parts[0].strip("[")

                self.progress.emit(pct, f"구령 음성 합성 중 ({idx+1}/{len(voice_events)}): {clean_text[:12]}...")

                if clean_text in voice_cache:
                    ev["sound_file"] = voice_cache[clean_text]["file"]
                    ev["duration"] = voice_cache[clean_text]["duration"]
                else:
                    v_path = os.path.join("projects", "temp_tts", f"sparring_v_{uuid.uuid4().hex[:6]}.wav")
                    try:
                        import edge_tts
                        import io

                        async def _synth(t, v, path):
                            comm = edge_tts.Communicate(t, v)
                            buf = io.BytesIO()
                            async for chunk in comm.stream():
                                if chunk['type'] == 'audio':
                                    buf.write(chunk['data'])
                            buf.seek(0)
                            AudioSegment.from_file(buf, format="mp3").export(path, format="wav")

                        asyncio.run(_synth(clean_text, voice_id, v_path))
                        if os.path.exists(v_path):
                            v_dur = len(AudioSegment.from_file(v_path)) / 1000.0
                            voice_cache[clean_text] = {"file": v_path, "duration": v_dur}
                            ev["sound_file"] = v_path
                            ev["duration"] = v_dur
                    except Exception as e:
                        print(f"[SparringWorker] TTS synth fail for '{clean_text}': {e}")
                        # Fallback to beep if TTS fails
                        ev["sound_file"] = os.path.join("effects", "beep.wav")
                        ev["duration"] = 0.25

            # 3. 타임라인 클립 구성
            self.progress.emit(65, "타임라인 트랙 데이터 구성 중...")
            bgm_vol_pct = self.params.get("bgm_vol_pct", 70)
            sig_vol_pct = self.params.get("sig_vol_pct", 120)
            voice_vol_pct = self.params.get("voice_vol_pct", 130)
            duck_db = self.params.get("duck_db", -8.0)

            bgm_vol_db = vol_pct_to_db(bgm_vol_pct)
            sig_vol_db = vol_pct_to_db(sig_vol_pct)
            voice_vol_db = vol_pct_to_db(voice_vol_pct)

            timeline_clips = []
            for ev in events:
                f_path = ev.get("sound_file", "")
                if f_path and os.path.exists(f_path):
                    clip_vol = voice_vol_db if ev.get("type") == "voice" else sig_vol_db
                    timeline_clips.append({
                        "text": ev["text"],
                        "file": f_path,
                        "time": round(ev["time"], 2),
                        "duration": ev.get("duration", 0.5),
                        "track": ev.get("track", 1),
                        "vol": clip_vol
                    })

            # 4. 다중 BGM 크로스페이드 및 오토 덕킹
            self.progress.emit(80, "배경음악(BGM) 믹싱 및 오토 덕킹 처리 중...")
            bgm_clip_path = ""
            valid_bgm = [p for p in self.bgm_paths if os.path.exists(p)]
            auto_ducking = self.params.get("auto_ducking", True)

            if valid_bgm:
                bgm_raw = ShuttleRunEngine.build_seamless_bgm(
                    valid_bgm,
                    target_duration_ms=total_duration_ms,
                    crossfade_ms=2000
                )
                if bgm_vol_db != 0.0:
                    bgm_raw = bgm_raw + bgm_vol_db

                if auto_ducking and duck_db != 0.0:
                    bgm_raw = ShuttleRunEngine.apply_auto_ducking(bgm_raw, duck_segments, duck_db=duck_db)

                bgm_clip_path = os.path.join("projects", "temp_tts", f"sparring_bgm_{uuid.uuid4().hex[:6]}.wav")
                bgm_raw.export(bgm_clip_path, format="wav")

                bgm_label = f"[BGM {len(valid_bgm)}곡] {os.path.basename(valid_bgm[0])} 외" if len(valid_bgm) > 1 else f"[BGM] {os.path.basename(valid_bgm[0])}"
                timeline_clips.insert(0, {
                    "text": f"{bgm_label} (볼륨 {bgm_vol_pct}%)",
                    "file": bgm_clip_path,
                    "time": 0.0,
                    "duration": total_duration_sec,
                    "track": 0,
                    "vol": 0.0
                })

            # 5. 완성본 오디오 합성 (Mastering)
            self.progress.emit(92, "최종 음원 믹싱 및 마스터링 중...")
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

            try:
                master_canvas = normalize(master_canvas)
            except Exception:
                pass

            output_master_path = os.path.join(
                "projects", "temp_tts",
                f"Sparring_{self.mode}_{uuid.uuid4().hex[:6]}.wav"
            )
            master_canvas.export(output_master_path, format="wav")

            self.progress.emit(100, "완료!")
            result_data = {
                "mode": self.mode,
                "mode_name": SparringTrainingEngine.TRAINING_MODES.get(self.mode, {}).get("name", "겨루기/발차기 훈련"),
                "timeline_clips": timeline_clips,
                "master_audio_path": output_master_path,
                "total_duration_sec": total_duration_sec
            }
            self.finished.emit(True, "겨루기/발차기 훈련 음원이 성공적으로 생성되었습니다.", result_data)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.finished.emit(False, f"음원 생성 중 오류 발생: {str(e)}", {})


class SparringDialog(QDialog):
    """겨루기 & 발차기 트레이닝 음원 생성 마법사 UI 다이얼로그"""

    def __init__(self, parent=None, tts_engine=None):
        super().__init__(parent)
        self.tts_engine = tts_engine
        self.setWindowTitle("🥋 겨루기 & 미트 발차기 트레이닝 음원 마법사")
        self.resize(700, 750)
        self.bgm_playlist: List[str] = []
        self.generated_result = None

        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # 상단 안내 배너
        header_box = QGroupBox()
        header_box.setStyleSheet("background-color: #fdf2f8; border: 1px solid #fbcfe8; border-radius: 8px; padding: 6px;")
        hb_layout = QVBoxLayout(header_box)
        title_lbl = QLabel("🥋 맞춤형 겨루기 스텝 & 미트 발차기 훈련 음원 생성기")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #9d174d;")
        desc_lbl = QLabel(
            "오늘의 훈련 목표(1:1 받아차기, 1·2연타, 1:2/1:3 순환 미트, 겨루기 라운드)에 맞춰\n"
            "구령과 신호음, 신나는 BGM을 자유자재로 설정하고 오토덕킹으로 깔끔하게 자동 합성합니다."
        )
        desc_lbl.setStyleSheet("color: #475569; font-size: 12px;")
        hb_layout.addWidget(title_lbl)
        hb_layout.addWidget(desc_lbl)
        main_layout.addWidget(header_box)

        # 4가지 훈련 모드 탭
        self.tabs = QTabWidget()

        # ── 탭 1: 1:1, 1:2, 1:3 릴레이 미트 ──
        tab_relay = QWidget()
        l_relay = QVBoxLayout(tab_relay)
        
        g_relay_f = QGroupBox("선수 인원 구성")
        hl_rf = QHBoxLayout(g_relay_f)
        self.rb_relay_11 = QRadioButton("1 : 1 교대 (A선수 ↔ B선수)")
        self.rb_relay_12 = QRadioButton("1 : 2 교대 (3인 1조 로테이션)")
        self.rb_relay_13 = QRadioButton("1 : 3 교대 (4인 1조 로테이션)")
        self.rb_relay_11.setChecked(True)
        hl_rf.addWidget(self.rb_relay_11)
        hl_rf.addWidget(self.rb_relay_12)
        hl_rf.addWidget(self.rb_relay_13)
        l_relay.addWidget(g_relay_f)

        g_relay_t = QGroupBox("시간 및 훈련 설정")
        l_rt = QVBoxLayout(g_relay_t)
        
        h_rt1 = QHBoxLayout()
        h_rt1.addWidget(QLabel("타자당 타격 시간:"))
        self.sp_relay_strike = QSpinBox()
        self.sp_relay_strike.setRange(5, 60)
        self.sp_relay_strike.setValue(15)
        self.sp_relay_strike.setSuffix(" 초")
        h_rt1.addWidget(self.sp_relay_strike)

        h_rt1.addWidget(QLabel("선수 교대(준비) 시간:"))
        self.sp_relay_change = QSpinBox()
        self.sp_relay_change.setRange(2, 15)
        self.sp_relay_change.setValue(3)
        self.sp_relay_change.setSuffix(" 초")
        h_rt1.addWidget(self.sp_relay_change)
        l_rt.addLayout(h_rt1)

        h_rt2 = QHBoxLayout()
        h_rt2.addWidget(QLabel("전체 순환 세트 수:"))
        self.sp_relay_cycles = QSpinBox()
        self.sp_relay_cycles.setRange(1, 10)
        self.sp_relay_cycles.setValue(3)
        self.sp_relay_cycles.setSuffix(" 세트")
        h_rt2.addWidget(self.sp_relay_cycles)

        h_rt2.addWidget(QLabel("공격 구령/기술명:"))
        self.txt_relay_cue = QLineEdit("받아차기")
        self.txt_relay_cue.setPlaceholderText("예: 받아차기, 1연타, 나래차기 등")
        h_rt2.addWidget(self.txt_relay_cue)
        l_rt.addLayout(h_rt2)
        l_relay.addWidget(g_relay_t)
        l_relay.addStretch()
        self.tabs.addTab(tab_relay, "🔄 1:1 / 1:2 / 1:3 릴레이 미트")

        # ── 탭 2: 스텝 & 받아차기/반응 훈련 ──
        tab_reaction = QWidget()
        l_reac = QVBoxLayout(tab_reaction)
        
        # 실전 훈련 시퀀스 안내 배너
        reac_info = QLabel("🎯 동작 순서: [기술 지시 (예: 1연타!)] ➔ [랜덤 초(3~8초) 긴장 대기] ➔ [신호음/구령 (삑! / 시작! / GO!)] 발차기 타격!")
        reac_info.setStyleSheet("background-color: #eff6ff; border: 1px solid #bfdbfe; border-radius: 6px; padding: 6px 10px; font-weight: bold; color: #1e40af; font-size: 12px;")
        l_reac.addWidget(reac_info)

        g_reac_t = QGroupBox("1. 훈련 시간 및 랜덤 긴장 대기 간격")
        l_rct = QVBoxLayout(g_reac_t)
        h_rct1 = QHBoxLayout()
        h_rct1.addWidget(QLabel("총 훈련 시간:"))
        self.sp_reac_dur = QSpinBox()
        self.sp_reac_dur.setRange(30, 600)
        self.sp_reac_dur.setValue(120)
        self.sp_reac_dur.setSuffix(" 초 (2분)")
        h_rct1.addWidget(self.sp_reac_dur)

        h_rct1.addWidget(QLabel("랜덤 긴장 대기:"))
        self.sp_reac_min = QDoubleSpinBox()
        self.sp_reac_min.setRange(1.0, 15.0)
        self.sp_reac_min.setValue(3.0)
        self.sp_reac_min.setSuffix("초 ~ ")
        self.sp_reac_max = QDoubleSpinBox()
        self.sp_reac_max.setRange(2.0, 20.0)
        self.sp_reac_max.setValue(8.0)
        self.sp_reac_max.setSuffix("초")
        h_rct1.addWidget(self.sp_reac_min)
        h_rct1.addWidget(self.sp_reac_max)
        l_rct.addLayout(h_rct1)
        l_reac.addWidget(g_reac_t)

        # 2. 발차기 출발/타격 신호음 종류 선택
        g_reac_sig = QGroupBox("2. 발차기 출발/타격 신호 (트리거)")
        l_sig = QHBoxLayout(g_reac_sig)
        l_sig.addWidget(QLabel("타격 신호음:"))
        self.combo_reac_signal = QComboBox()
        self.combo_reac_signal.addItem("📢 경기용 심판 휘슬 (호각)", "whistle")
        self.combo_reac_signal.addItem("🔔 전자 비프음 (880Hz 삑~익)", "beep")
        self.combo_reac_signal.addItem("🥁 웅장한 대북 타격음 (쿵)", "drum")
        self.combo_reac_signal.addItem("🗣️ 음성 구령: '시작!'", "voice_start")
        self.combo_reac_signal.addItem("🗣️ 음성 구령: 'GO!'", "voice_go")
        self.combo_reac_signal.addItem("🗣️ 음성 구령: '탕!'", "voice_bang")
        self.combo_reac_signal.addItem("🎲 랜덤 믹스 (휘슬 / 비프 / 시작! / GO! 무작위)", "random_mix")
        l_sig.addWidget(self.combo_reac_signal, stretch=1)
        l_reac.addWidget(g_reac_sig)

        # 3. 명령어 템플릿 프리셋 선택 및 직접 편집
        g_reac_cues = QGroupBox("3. 기술 지시 구령 및 템플릿")
        l_rcc = QVBoxLayout(g_reac_cues)
        
        h_tmpl = QHBoxLayout()
        h_tmpl.addWidget(QLabel("📋 훈련 템플릿 선택:"))
        self.combo_cues_template = QComboBox()
        self.combo_cues_template.addItem("⚡ [템플릿 1] 연타 공격 (1연타, 2연타, 3연타, 나래차기)", "1연타!, 2연타!, 3연타!, 앞발 나래차기!")
        self.combo_cues_template.addItem("🛡️ [템플릿 2] 받아차기 / 카운터 (받아차기, 카운터, 뒤차기, 컷트)", "받아차기!, 카운터!, 뒤차기!, 앞발 컷트!")
        self.combo_cues_template.addItem("🥋 [템플릿 3] 실전 겨루기 (돌려차기, 앞발 찍기, 뒤후리기, 찌르기)", "돌려차기!, 앞발 찍기!, 뒤후리기!, 찌르기!")
        self.combo_cues_template.addItem("🏃‍♂️ [템플릿 4] 기본 순발력 (앞차기, 돌려차기, 내려찍기, 옆차기)", "앞차기!, 돌려차기!, 내려찍기!, 옆차기!")
        self.combo_cues_template.currentIndexChanged.connect(self._on_cues_template_changed)
        h_tmpl.addWidget(self.combo_cues_template, stretch=1)
        l_rcc.addLayout(h_tmpl)

        h_input = QHBoxLayout()
        h_input.addWidget(QLabel("✏️ 적용 구령 목록:"))
        self.txt_reac_cues = QLineEdit("1연타!, 2연타!, 3연타!, 앞발 나래차기!")
        self.txt_reac_cues.setPlaceholderText("쉼표로 구분하여 자유롭게 기술명을 입력하세요")
        h_input.addWidget(self.txt_reac_cues, stretch=1)
        l_rcc.addLayout(h_input)

        lbl_hint = QLabel("※ 스텝 중 위 기술명이 먼저 제시되고, 무작위 대기 시간(3~8초) 후 신호음(삑!/시작!)에 즉시 발차기합니다.")
        lbl_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        l_rcc.addWidget(lbl_hint)
        l_reac.addWidget(g_reac_cues)
        l_reac.addStretch()
        self.tabs.addTab(tab_reaction, "⚡ 스텝 & 받아차기 반응")

        # ── 탭 3: 스텝 + 콤비 연타 인터벌 ──
        tab_combo = QWidget()
        l_combo = QVBoxLayout(tab_combo)
        
        g_combo_set = QGroupBox("스텝 및 연타 시간 설정")
        l_cbs = QVBoxLayout(g_combo_set)
        h_cbs1 = QHBoxLayout()
        h_cbs1.addWidget(QLabel("스텝 유지 시간:"))
        self.sp_combo_step = QSpinBox()
        self.sp_combo_step.setRange(4, 30)
        self.sp_combo_step.setValue(8)
        self.sp_combo_step.setSuffix(" 초")
        h_cbs1.addWidget(self.sp_combo_step)

        h_cbs1.addWidget(QLabel("전력 연타 시간:"))
        self.sp_combo_strike = QSpinBox()
        self.sp_combo_strike.setRange(2, 20)
        self.sp_combo_strike.setValue(4)
        self.sp_combo_strike.setSuffix(" 초")
        h_cbs1.addWidget(self.sp_combo_strike)

        h_cbs1.addWidget(QLabel("총 세트 수:"))
        self.sp_combo_sets = QSpinBox()
        self.sp_combo_sets.setRange(2, 20)
        self.sp_combo_sets.setValue(6)
        self.sp_combo_sets.setSuffix(" 세트")
        h_cbs1.addWidget(self.sp_combo_sets)
        l_cbs.addLayout(h_cbs1)
        l_combo.addWidget(g_combo_set)

        g_combo_types = QGroupBox("콤비네이션 연타 구령 (세트마다 순환)")
        l_cbt = QVBoxLayout(g_combo_types)
        self.txt_combo_types = QLineEdit("1연타, 2연타, 3연타, 나래차기 연타")
        l_cbt.addWidget(self.txt_combo_types)
        l_combo.addWidget(g_combo_types)
        l_combo.addStretch()
        self.tabs.addTab(tab_combo, "🔥 스텝 + 콤비네이션 연타")

        # ── 탭 4: 정규 겨루기 라운드 ──
        tab_round = QWidget()
        l_rnd = QVBoxLayout(tab_round)
        g_rnd_set = QGroupBox("라운드 시간 설정")
        l_rnds = QHBoxLayout(g_rnd_set)
        
        l_rnds.addWidget(QLabel("1라운드 경기 시간:"))
        self.sp_rnd_time = QSpinBox()
        self.sp_rnd_time.setRange(30, 300)
        self.sp_rnd_time.setValue(90)
        self.sp_rnd_time.setSuffix(" 초 (1분 30초)")
        l_rnds.addWidget(self.sp_rnd_time)

        l_rnds.addWidget(QLabel("라운드 간 휴식:"))
        self.sp_rnd_rest = QSpinBox()
        self.sp_rnd_rest.setRange(10, 120)
        self.sp_rnd_rest.setValue(30)
        self.sp_rnd_rest.setSuffix(" 초")
        l_rnds.addWidget(self.sp_rnd_rest)

        l_rnds.addWidget(QLabel("총 라운드:"))
        self.sp_rnd_count = QSpinBox()
        self.sp_rnd_count.setRange(1, 10)
        self.sp_rnd_count.setValue(3)
        self.sp_rnd_count.setSuffix(" 라운드")
        l_rnds.addWidget(self.sp_rnd_count)
        l_rnd.addWidget(g_rnd_set)
        l_rnd.addStretch()
        self.tabs.addTab(tab_round, "🥊 정규 겨루기 라운드")

        main_layout.addWidget(self.tabs)

        # ── 공통 설정 (BGM, 화자, 오토덕킹) ──
        common_group = QGroupBox("🎵 배경음악(BGM) 및 효과음/음성 옵션")
        l_common = QVBoxLayout(common_group)

        # BGM 다중 선택
        h_bgm = QHBoxLayout()
        btn_add_bgm = QPushButton("📁 음악 파일 추가 (다중 선택 가능)...")
        btn_add_bgm.clicked.connect(self.browse_bgm)
        btn_clr_bgm = QPushButton("❌ 전체 제거")
        btn_clr_bgm.clicked.connect(self.clear_bgm)
        h_bgm.addWidget(btn_add_bgm)
        h_bgm.addWidget(btn_clr_bgm)
        h_bgm.addStretch()
        l_common.addLayout(h_bgm)

        self.bgm_label = QLabel("선택된 음악 없음 (효과음과 구령만 생성)")
        self.bgm_label.setStyleSheet("color: #64748b; font-style: italic;")
        l_common.addWidget(self.bgm_label)

        # 음성 화자 및 오토덕킹
        h_opts = QHBoxLayout()
        self.cb_countdown = QCheckBox("시작 전 카운트다운(3-2-1) 포함")
        self.cb_countdown.setChecked(True)
        self.cb_ducking = QCheckBox("🎵 BGM 오토 덕킹(신호 시 음악 -8dB 감쇄)")
        self.cb_ducking.setChecked(True)
        h_opts.addWidget(self.cb_countdown)
        h_opts.addWidget(self.cb_ducking)

        h_opts.addWidget(QLabel("구령 화자:"))
        self.voice_combo = QComboBox()
        self.voice_combo.addItems([
            "선히 (한국어 여성, 또렷함)",
            "인준 (한국어 남성, 힘찬 구령 추천)",
            "현수 (한국어 남성, 다국어)"
        ])
        self.voice_combo.setCurrentIndex(1)  # 인준 기본
        h_opts.addWidget(self.voice_combo)
        l_common.addLayout(h_opts)

        main_layout.addWidget(common_group)

        # ── 개별 음량 및 오토덕킹 밸런스 커스텀 ──
        vol_group = QGroupBox("🎚️ 개별 음량(BGM / 비프음 / TTS 구령) 및 오토덕킹 커스텀")
        vol_group.setStyleSheet("QGroupBox { font-weight: bold; color: #9d174d; }")
        vol_layout = QVBoxLayout(vol_group)

        # 1. BGM 볼륨
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

        # 2. 신호음 볼륨
        h_v2 = QHBoxLayout()
        h_v2.addWidget(QLabel("🔔 신호음(호각/비프/벨) 음량:"))
        self.slider_sig_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_sig_vol.setRange(20, 200)
        self.slider_sig_vol.setValue(120)
        self.lbl_sig_vol = QLabel("120%")
        self.lbl_sig_vol.setFixedWidth(45)
        self.slider_sig_vol.valueChanged.connect(lambda v: self.lbl_sig_vol.setText(f"{v}%"))
        h_v2.addWidget(self.slider_sig_vol)
        h_v2.addWidget(self.lbl_sig_vol)
        vol_layout.addLayout(h_v2)

        # 3. 음성 구령 볼륨
        h_v3 = QHBoxLayout()
        h_v3.addWidget(QLabel("🗣️ 훈련 구령(TTS) 음량:"))
        self.slider_voice_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_voice_vol.setRange(20, 200)
        self.slider_voice_vol.setValue(130)
        self.lbl_voice_vol = QLabel("130%")
        self.lbl_voice_vol.setFixedWidth(45)
        self.slider_voice_vol.valueChanged.connect(lambda v: self.lbl_voice_vol.setText(f"{v}%"))
        h_v3.addWidget(self.slider_voice_vol)
        h_v3.addWidget(self.lbl_voice_vol)
        vol_layout.addLayout(h_v3)

        # 4. 덕킹 강도 & 프리셋
        h_v4 = QHBoxLayout()
        h_v4.addWidget(QLabel("📉 오토덕킹 강도:"))
        self.combo_duck_level = QComboBox()
        self.combo_duck_level.addItem("보통 감쇄 (-8 dB) - 기본 추천", -8.0)
        self.combo_duck_level.addItem("강한 감쇄 (-12 dB) - 신호음/구령 극대화", -12.0)
        self.combo_duck_level.addItem("부드러운 감쇄 (-4 dB) - 음악 비트 유지", -4.0)
        self.combo_duck_level.addItem("최대 감쇄 (-16 dB) - 음악 일시 거의 음소거", -16.0)
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

        main_layout.addWidget(vol_group)

        # 상태 안내 및 진행바
        self.status_lbl = QLabel("원하는 훈련 탭을 선택하고 세부 값을 조정한 뒤 [생성하기]를 누르세요.")
        self.status_lbl.setStyleSheet("color: #9d174d; font-weight: bold;")
        main_layout.addWidget(self.status_lbl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # 액션 버튼
        btn_box = QHBoxLayout()
        self.btn_generate = QPushButton("🚀 맞춤 훈련 음원 생성하기")
        self.btn_generate.setStyleSheet("""
            QPushButton {
                background-color: #be185d;
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 20px;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #9d174d; }
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
            self.bgm_label.setText("선택된 음악 없음 (효과음과 구령만 생성)")
            self.bgm_label.setStyleSheet("color: #64748b; font-style: italic;")
        else:
            names = [os.path.basename(p) for p in self.bgm_playlist]
            if len(names) <= 3:
                display_str = ", ".join(names)
            else:
                display_str = f"{names[0]}, {names[1]} 외 {len(names)-2}곡"
            self.bgm_label.setText(f"🎶 총 {len(self.bgm_playlist)}곡 선택됨: {display_str} (자연스러운 크로스페이드)")
            self.bgm_label.setStyleSheet("color: #be185d; font-weight: bold;")

    def clear_bgm(self):
        self.bgm_playlist = []
        self._update_bgm_label()

    def _on_cues_template_changed(self, idx):
        tmpl_data = self.combo_cues_template.currentData()
        if tmpl_data:
            self.txt_reac_cues.setText(tmpl_data)

    def set_vol_preset(self, bgm: int, sig: int, voice: int, duck_idx: int):
        self.slider_bgm_vol.setValue(bgm)
        self.slider_sig_vol.setValue(sig)
        self.slider_voice_vol.setValue(voice)
        self.combo_duck_level.setCurrentIndex(duck_idx)

    def start_generation(self):
        current_tab_idx = self.tabs.currentIndex()
        mode_map = {0: "relay", 1: "reaction", 2: "combo", 3: "rounds"}
        mode = mode_map.get(current_tab_idx, "relay")

        duck_db_val = self.combo_duck_level.currentData()
        if duck_db_val is None:
            duck_db_val = -8.0

        params = {
            "countdown_enabled": self.cb_countdown.isChecked(),
            "auto_ducking": self.cb_ducking.isChecked(),
            "voice_speaker": self.voice_combo.currentText(),
            "use_voice": True,
            "bgm_vol_pct": self.slider_bgm_vol.value(),
            "sig_vol_pct": self.slider_sig_vol.value(),
            "voice_vol_pct": self.slider_voice_vol.value(),
            "duck_db": duck_db_val
        }

        if mode == "relay":
            fighters = 2 if self.rb_relay_11.isChecked() else (3 if self.rb_relay_12.isChecked() else 4)
            params["fighters_count"] = fighters
            params["strike_sec"] = float(self.sp_relay_strike.value())
            params["change_sec"] = float(self.sp_relay_change.value())
            params["cycles"] = self.sp_relay_cycles.value()
            params["cue_text"] = self.txt_relay_cue.text().strip() or "받아차기"

        elif mode == "reaction":
            params["duration_sec"] = float(self.sp_reac_dur.value())
            params["min_interval"] = float(self.sp_reac_min.value())
            params["max_interval"] = float(self.sp_reac_max.value())
            raw_cues = self.txt_reac_cues.text().split(",")
            params["cues"] = [c.strip() for c in raw_cues if c.strip()]
            params["signal_sound"] = self.combo_reac_signal.currentData()

        elif mode == "combo":
            params["step_sec"] = float(self.sp_combo_step.value())
            params["combo_sec"] = float(self.sp_combo_strike.value())
            params["sets_count"] = self.sp_combo_sets.value()
            raw_types = self.txt_combo_types.text().split(",")
            params["combo_types"] = [t.strip() for t in raw_types if t.strip()]

        elif mode == "rounds":
            params["round_sec"] = float(self.sp_rnd_time.value())
            params["rest_sec"] = float(self.sp_rnd_rest.value())
            params["total_rounds"] = self.sp_rnd_count.value()

        self.btn_generate.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_lbl.setText("맞춤 훈련 음원 합성 중입니다. 잠시만 기다려주세요...")

        self.worker = SparringWorker(mode, params, self.bgm_playlist, tts_engine=self.tts_engine)
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
            self.status_lbl.setText("✅ 훈련 음원 생성 완료!")
            
            dur_m = int(result_data['total_duration_sec'] // 60)
            dur_s = int(result_data['total_duration_sec'] % 60)
            
            reply = QMessageBox.question(
                self,
                "훈련 음원 생성 완료",
                "🎉 맞춤 겨루기/발차기 훈련 음원이 성공적으로 생성되었습니다!\n\n"
                f"- 모드: {SparringTrainingEngine.TRAINING_MODES.get(result_data['mode'], {}).get('name', '맞춤 훈련')}\n"
                f"- 총 재생 시간: {dur_m}분 {dur_s}초\n\n"
                "지금 바로 음악 편집기 타임라인에 트랙별(BGM/신호음/구령)로 로드하시겠습니까?\n"
                "(로드 후 타임라인에서 재생 및 미세 편집이 가능합니다.)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.accept()
            else:
                save_reply = QMessageBox.question(
                    self, "파일 직접 저장",
                    "합성된 완성본 오디오(WAV)를 파일로 바로 저장하시겠습니까?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if save_reply == QMessageBox.StandardButton.Yes:
                    save_path, _ = QFileDialog.getSaveFileName(
                        self, "훈련 음원 저장",
                        f"발차기훈련_{result_data['mode']}_{dur_m}분{dur_s}초.wav",
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
