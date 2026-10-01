"""
Warmup, Stretching & Mobility Dialog (준비운동·스트레칭·요가 음원 마법사)
Author: Gemini & Antigravity
Provides an intuitive UI for dojo masters and fitness trainers:
- 5 Pre-built routines (Standard full, Quick express, Warmup & Agility, Flexibility, Yoga/Pilates)
- Korean & Easy Kids English dual-language selection
- Detailed coach instruction vs Fast cue-only mode toggle
- Rich tooltips (말풍선 도움말) on all controls for extreme ease of use
- Movement checklist editor (Add, Remove, Reorder, Edit cue texts)
- Tempo BPM slider (60~110 BPM)
- Auto-ducking BGM mixing & Direct timeline loading / WAV export
"""

import os
import io
import math
import copy
import json
import asyncio
from typing import Optional, Dict, Any, List
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QRadioButton,
    QButtonGroup, QSpinBox, QSlider, QCheckBox, QFileDialog, QMessageBox, QComboBox,
    QProgressBar, QGroupBox, QScrollArea, QWidget, QLineEdit, QTextEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QApplication
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

import edge_tts
from pydub import AudioSegment
from pydub.effects import normalize

from core.warmup_engine import (
    WarmupEngine, ROUTINE_PRESETS, MASTER_MOVEMENTS, START_CUES, END_CUES
)
from core.shuttle_run_engine import ShuttleRunEngine
from utils.effects_generator import ensure_default_effects


def vol_pct_to_db(pct: int) -> float:
    """선형 퍼센트(%) 볼륨을 데시벨(dB)로 변환"""
    if pct <= 0:
        return -60.0
    return round(20.0 * math.log10(pct / 100.0), 2)


def trim_audio_silence(seg: AudioSegment, threshold: float = -42.0) -> AudioSegment:
    """TTS 음성의 앞뒤 불필요한 무음을 정밀 제거하되 말끝 250ms 여백 보존"""
    try:
        from pydub.silence import detect_leading_silence
        lead = detect_leading_silence(seg, silence_threshold=threshold)
        trail = detect_leading_silence(seg.reverse(), silence_threshold=threshold)
        safe_trail = max(0, trail - 250)
        return seg[lead:len(seg) - safe_trail] if len(seg) > (lead + safe_trail) else seg
    except Exception:
        return seg


class WarmupSynthThread(QThread):
    """
    백그라운드 음성 합성 & 오디오 믹싱 쓰레드
    - 동작 안내 멘트 및 8박자/카운트다운 고속 캐시 합성
    - BGM 오토 더킹(Auto-Ducking) 및 신호음 믹싱
    """
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str, dict)

    def __init__(self, params: Dict[str, Any], bgm_paths: List[str], tts_engine=None):
        super().__init__()
        self.params = params
        self.bgm_paths = bgm_paths
        self.tts_engine = tts_engine

    def run(self):
        try:
            self.progress.emit(5, "준비운동 타임테이블 계산 및 신호음 점검 중...")
            ensure_default_effects()

            # 1. 타임라인 이벤트 계산
            schedule_data = WarmupEngine.build_timeline_events(self.params)
            events = schedule_data["events"]
            duck_segments = schedule_data["duck_segments"]
            total_duration_sec = schedule_data["total_duration_sec"]
            total_duration_ms = int(total_duration_sec * 1000)

            # 2. 음성 합성 설정 (한국어 및 영어)
            lang = self.params.get("language", "kr")
            speaker = self.params.get("voice_speaker", "선히(여성)")
            
            if lang == "kr":
                voice_id = "ko-KR-SunHiNeural"
                if "인준" in speaker:
                    voice_id = "ko-KR-InJoonNeural"
                elif "현수" in speaker:
                    voice_id = "ko-KR-HyunsuMultilingualNeural"
            else:
                is_female = "선히" in speaker or "여성" in speaker or "Jenny" in speaker
                voice_id = "en-US-JennyNeural" if is_female else "en-US-GuyNeural"

            os.makedirs(os.path.join("projects", "temp_tts"), exist_ok=True)
            voice_cache: Dict[str, str] = {}

            voice_events = [ev for ev in events if ev["type"] in ("voice", "count")]
            total_voice_count = len(voice_events)

            self.progress.emit(10, f"음성 멘트 및 구령 합성 시작 (총 {total_voice_count}개 구간)...")

            async def _synth_voice_text(text: str, path: str, voice: str) -> None:
                comm = edge_tts.Communicate(text, voice, rate="+5%")
                buf = io.BytesIO()
                async for chunk in comm.stream():
                    if chunk['type'] == 'audio':
                        buf.write(chunk['data'])
                buf.seek(0)
                seg = AudioSegment.from_file(buf, format="mp3")
                trimmed = trim_audio_silence(seg)
                trimmed.export(path, format="wav")

            # 루프 돌며 음성 합성 (캐시 활용으로 중복 카운트 초고속 처리)
            for idx, ev in enumerate(voice_events):
                raw_text = ev["text"].strip()
                if not raw_text:
                    continue

                cache_key = f"{voice_id}_{raw_text}"
                if cache_key in voice_cache and os.path.exists(voice_cache[cache_key]):
                    ev["sound_file"] = voice_cache[cache_key]
                else:
                    safe_filename = f"warmup_{abs(hash(cache_key))}_{idx}.wav"
                    v_path = os.path.join("projects", "temp_tts", safe_filename)
                    asyncio.run(_synth_voice_text(raw_text, v_path, voice_id))
                    voice_cache[cache_key] = v_path
                    ev["sound_file"] = v_path

                # 실제 오디오 길이로 duration 갱신
                if ev.get("sound_file") and os.path.exists(ev["sound_file"]):
                    try:
                        actual_dur = len(AudioSegment.from_file(ev["sound_file"])) / 1000.0
                        ev["duration"] = round(actual_dur, 2)
                    except Exception:
                        pass

                pct = 10 + int(45 * (idx + 1) / max(1, total_voice_count))
                self.progress.emit(pct, f"사범 구령 및 안내 음성 합성 중... ({idx+1}/{total_voice_count})")

            # 3. 효과음 파일 경로 보정
            for ev in events:
                if ev["type"] in ("bell", "beep", "whistle"):
                    s_file = ev.get("sound_file", "stage_bell.wav")
                    full_p = os.path.join("effects", s_file)
                    if os.path.exists(full_p):
                        ev["sound_file"] = full_p
                        try:
                            ev["duration"] = round(len(AudioSegment.from_file(full_p)) / 1000.0, 2)
                        except Exception:
                            pass

            # 3-1. [핵심 음성 겹침 방지 엔진]
            # 실제 측정된 물리적 오디오 길이를 기반으로 타임스탬프를 순차 재배치하여 음성 겹침/뒤엉킴 0% 보장!
            trans_gap = self.params.get("trans_gap_sec", 0.5)
            events, duck_segments, total_duration_sec = WarmupEngine.cascade_realign_events(events, trans_gap_sec=trans_gap)
            total_duration_ms = int(total_duration_sec * 1000)

            self.progress.emit(60, "배경음악(BGM) 루프 및 믹싱 캔버스 준비 중...")

            # 4. 볼륨 및 더킹 파라미터 계산
            bgm_vol_pct = self.params.get("bgm_vol_pct", 60)
            voice_vol_pct = self.params.get("voice_vol_pct", 100)
            sig_vol_pct = self.params.get("signal_vol_pct", 95)
            duck_db_val = self.params.get("duck_db", -14.0)
            auto_ducking = self.params.get("auto_ducking", True)

            bgm_vol_db = vol_pct_to_db(bgm_vol_pct)
            voice_vol_db = vol_pct_to_db(voice_vol_pct)
            sig_vol_db = vol_pct_to_db(sig_vol_pct)

            # 5. 배경음악 준비
            bgm_clip_path = None
            bgm_track_audio = AudioSegment.silent(duration=total_duration_ms)

            valid_bgm = [p for p in self.bgm_paths if os.path.exists(p)]
            if valid_bgm and bgm_vol_pct > 0:
                self.progress.emit(65, "배경음악 루프 생성 및 오토 더킹(Auto-Ducking) 적용 중...")
                bgm_raw = ShuttleRunEngine.build_seamless_bgm(
                    valid_bgm,
                    target_duration_ms=total_duration_ms,
                    crossfade_ms=2000
                )
                bgm_raw = bgm_raw + bgm_vol_db

                if auto_ducking and duck_segments:
                    bgm_raw = ShuttleRunEngine.apply_auto_ducking(bgm_raw, duck_segments, duck_db=duck_db_val)

                bgm_track_audio = bgm_raw[:total_duration_ms]
                bgm_clip_path = os.path.join("projects", "temp_tts", "warmup_bgm_track.wav")
                bgm_track_audio.export(bgm_clip_path, format="wav")

            # 6. 마스터 오디오 합성 (WAV 내보내기용)
            self.progress.emit(75, "모든 트랙(음성+신호음+BGM) 통합 마스터링 중...")
            master_canvas = bgm_track_audio

            for idx, ev in enumerate(events):
                f_path = ev.get("sound_file", "")
                if not f_path or not os.path.exists(f_path):
                    continue

                try:
                    clip_seg = AudioSegment.from_file(f_path)
                    target_db = voice_vol_db if ev["type"] in ("voice", "count") else sig_vol_db
                    if target_db != 0:
                        clip_seg = clip_seg + target_db

                    ins_ms = int(ev["time"] * 1000)
                    if ins_ms + len(clip_seg) > len(master_canvas):
                        extra = (ins_ms + len(clip_seg)) - len(master_canvas)
                        master_canvas = master_canvas + AudioSegment.silent(duration=extra)

                    master_canvas = master_canvas.overlay(clip_seg, position=ins_ms)
                except Exception:
                    pass

                p = 75 + int(20 * (idx + 1) / max(1, len(events)))
                self.progress.emit(p, f"마스터 사운드 오버레이 합성 중... ({idx+1}/{len(events)})")

            master_canvas = normalize(master_canvas)
            output_master_path = os.path.join("projects", "temp_tts", "warmup_master_audio.wav")
            master_canvas.export(output_master_path, format="wav")

            # 7. 타임라인 클립 데이터 구성
            timeline_clips = []
            if bgm_clip_path and os.path.exists(bgm_clip_path):
                timeline_clips.append({
                    "text": "🎵 [배경음악] 워밍업 & 스트레칭 BGM (오토더킹 적용)",
                    "file": bgm_clip_path,
                    "time": 0.0,
                    "track": 0,
                    "duration": total_duration_sec
                })

            for ev in events:
                f_path = ev.get("sound_file", "")
                if f_path and os.path.exists(f_path):
                    timeline_clips.append({
                        "text": ev["text"],
                        "file": f_path,
                        "time": ev["time"],
                        "track": 1 if ev["type"] in ("bell", "beep", "whistle") else 2,
                        "duration": ev.get("duration", 1.0)
                    })

            self.progress.emit(100, "준비운동 오디오 생성이 완료되었습니다!")

            result_data = {
                "total_duration_sec": total_duration_sec,
                "timeline_clips": timeline_clips,
                "master_audio_path": output_master_path,
                "routine_name": self.params.get("routine_name", "준비운동"),
                "language": lang
            }

            self.finished.emit(True, "완료", result_data)

        except Exception as e:
            self.finished.emit(False, str(e), {})


class WarmupDialog(QDialog):
    """
    준비운동 & 스트레칭 마법사 다이얼로그
    - 5대 대표 루틴 원클릭 프리셋
    - 한국어 / 쉬운 영어 구령 전환
    - 상세 코칭 vs 명칭만 빠른 구령 모드
    - 동작 목록 체크박스 및 순서 변경 테이블
    - 모든 주요 컨트롤에 친절한 '말풍선 도움말' 장착
    """

    def __init__(self, parent=None, tts_engine=None):
        super().__init__(parent)
        self.tts_engine = tts_engine
        self.synth_thread: Optional[WarmupSynthThread] = None
        self.generated_result: Optional[Dict[str, Any]] = None

        self.setWindowTitle("🧘‍♂️ 준비운동·스트레칭·요가 음원 생성 마법사")
        self.resize(920, 780)

        # 현재 편집 중인 동작 리스트 (MASTER_MOVEMENTS 복사본)
        self.current_movements: List[Dict[str, Any]] = [
            copy.deepcopy(m) for m in MASTER_MOVEMENTS
        ]
        # 기본값: standard_full
        for m in self.current_movements:
            m["enabled"] = m["id"] in ROUTINE_PRESETS["standard_full"]["movement_ids"]

        self.bgm_paths: List[str] = []

        self.init_ui()
        self.apply_preset("standard_full")

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)

        # 1. 상단 안내 헤더 & 말풍선 가이드 배너
        header_box = QGroupBox("💡 준비운동 마법사 사용 가이드")
        header_layout = QVBoxLayout(header_box)
        lbl_guide = QLabel(
            "<b>[원클릭 제작 순서]</b> ① 원하는 <b>코스 프리셋</b>을 선택하세요. ➔ "
            "② <b>한국어/영어</b> 및 <b>상세/빠른 모드</b>를 고르세요. ➔ "
            "③ 하단 <b>[오디오 생성]</b> 버튼을 누르면 8박자 구령과 사범 멘트가 BGM과 함께 완벽하게 완성됩니다!<br>"
            "<span style='color: #4a90e2;'>※ 조작이 어려울 때는 마우스 커서를 올리시면 상세한 <b>말풍선 도움말</b>이 표시됩니다.</span>"
        )
        lbl_guide.setWordWrap(True)
        header_layout.addWidget(lbl_guide)
        main_layout.addWidget(header_box)

        # 2. 메인 스크롤 영역
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(14)

        # --- A. 코스 프리셋 선택 ---
        grp_preset = QGroupBox("1. 🎯 코스 프리셋 선택 및 사용자 템플릿 관리 (매일 지루하지 않은 테마)")
        grp_preset.setToolTip("수업 목적이나 요일별 테마에 맞는 준비운동 루틴을 원클릭으로 불러오거나, 나만의 템플릿을 저장/불러오기 합니다.")
        l_preset = QVBoxLayout(grp_preset)

        h_pre = QHBoxLayout()
        h_pre.addWidget(QLabel("<b>테마 프리셋:</b>"))
        self.combo_preset = QComboBox()
        self.combo_preset.setToolTip("원하는 훈련 코스를 선택하면 아래 동작 목록이 자동으로 구성됩니다.")
        for k, p in ROUTINE_PRESETS.items():
            self.combo_preset.addItem(p["name_kr"], k)
        self.combo_preset.addItem("✏️ [사용자 정의] 내 마음대로 직접 구성 (Custom)", "custom")
        self.combo_preset.currentIndexChanged.connect(self.on_preset_changed)
        h_pre.addWidget(self.combo_preset, 1)

        btn_save_tpl = QPushButton("💾 내 템플릿 저장")
        btn_save_tpl.setToolTip("현재 체크된 동작, 순서, 사범 멘트, 템포 설정을 JSON 파일로 저장하여 언제든 다시 불러올 수 있습니다.")
        btn_save_tpl.clicked.connect(self.save_custom_template)
        h_pre.addWidget(btn_save_tpl)

        btn_load_tpl = QPushButton("📂 내 템플릿 불러오기")
        btn_load_tpl.setToolTip("저장해둔 나만의 준비운동 템플릿(JSON) 파일을 불러와 즉시 세팅합니다.")
        btn_load_tpl.clicked.connect(self.load_custom_template)
        h_pre.addWidget(btn_load_tpl)

        l_preset.addLayout(h_pre)

        self.lbl_preset_desc = QLabel()
        self.lbl_preset_desc.setStyleSheet("color: #aaa; font-size: 12px; margin-left: 5px;")
        l_preset.addWidget(self.lbl_preset_desc)
        content_layout.addWidget(grp_preset)

        # --- B. 언어 및 멘트 진행 스타일 ---
        grp_style = QGroupBox("2. 🎙️ 구령 언어 & 멘트 진행 스타일")
        grp_style.setToolTip("사범님의 지도 방식과 언어를 설정합니다.")
        l_style = QVBoxLayout(grp_style)

        h_style1 = QHBoxLayout()
        # 언어 선택
        h_style1.addWidget(QLabel("<b>구령 언어:</b>"))
        self.rb_lang_kr = QRadioButton("🇰🇷 한국어 구령 (하나, 둘, 셋, 넷...)")
        self.rb_lang_kr.setChecked(True)
        self.rb_lang_kr.setToolTip("친숙하고 힘찬 한국어 사범님 8박자 구령과 지도 멘트를 사용합니다.")
        self.rb_lang_en = QRadioButton("🇺🇸 쉬운 영어 구령 (One, Two... 초등 저학년 맞춤)")
        self.rb_lang_en.setToolTip("초등 저학년도 귀로 듣고 즉시 따라 할 수 있는 쉬운 단어로 구성된 영어 구령입니다.")
        
        self.lang_group = QButtonGroup(self)
        self.lang_group.addButton(self.rb_lang_kr)
        self.lang_group.addButton(self.rb_lang_en)
        self.lang_group.buttonClicked.connect(self.on_language_changed)

        h_style1.addWidget(self.rb_lang_kr)
        h_style1.addWidget(self.rb_lang_en)
        h_style1.addStretch()
        l_style.addLayout(h_style1)

        h_style2 = QHBoxLayout()
        # 멘트 모드 선택
        h_style2.addWidget(QLabel("<b>진행 방식:</b>"))
        self.rb_mode_detailed = QRadioButton("🗣️ 자세 설명과 함께 진행 (초등부/신규 관원용)")
        self.rb_mode_detailed.setChecked(True)
        self.rb_mode_detailed.setToolTip("사범님이 동작 하나하나의 방법과 포인트를 친절하게 설명한 후 구령이 시작됩니다.")
        self.rb_mode_quick = QRadioButton("⚡ 명칭만 빠르게 진행 (선수부/상급반 쾌속 리듬)")
        self.rb_mode_quick.setToolTip("설명 없이 '무릎 돌리기, 시작!'처럼 동작 명칭만 외치고 즉시 구령으로 들어가 시간을 절약합니다.")

        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.rb_mode_detailed)
        self.mode_group.addButton(self.rb_mode_quick)
        self.mode_group.buttonClicked.connect(self.refresh_table_display)

        h_style2.addWidget(self.rb_mode_detailed)
        h_style2.addWidget(self.rb_mode_quick)
        h_style2.addStretch()
        l_style.addLayout(h_style2)

        # 템포 및 신호음
        h_style3 = QHBoxLayout()
        h_style3.addWidget(QLabel("<b>구령 템포(BPM):</b>"))
        self.slider_tempo = QSlider(Qt.Orientation.Horizontal)
        self.slider_tempo.setRange(50, 115)
        self.slider_tempo.setValue(85)
        self.slider_tempo.setToolTip("구령의 박자 빠르기를 조절합니다.\n• 60 BPM: 요가/정적 스트레칭\n• 85 BPM: 도장 표준 체조 (추천)\n• 105 BPM: 워밍업/점핑잭")
        self.lbl_tempo = QLabel("85 BPM (도장 표준)")
        self.slider_tempo.valueChanged.connect(self.on_tempo_changed)
        h_style3.addWidget(self.slider_tempo, 1)
        h_style3.addWidget(self.lbl_tempo)

        h_style3.addSpacing(20)
        h_style3.addWidget(QLabel("<b>전환 효과음:</b>"))
        self.combo_signal = QComboBox()
        self.combo_signal.addItem("🎵 맑은 차임벨 (추천)", "bell")
        self.combo_signal.addItem("🔔 전자 비프음", "beep")
        self.combo_signal.addItem("📢 심판 호각(휘슬)", "whistle")
        self.combo_signal.setToolTip("동작이 바뀔 때 울리는 신호음입니다.")
        h_style3.addWidget(self.combo_signal)
        l_style.addLayout(h_style3)

        content_layout.addWidget(grp_style)

        # --- C. 시작 & 종료 멘트 셀렉터 ---
        grp_cues = QGroupBox("3. 📣 시작 & 종료 안내 멘트 (다양한 선택형)")
        grp_cues.setToolTip("매일 같은 멘트 대신 상황에 맞게 시작 및 마무리 멘트를 자유롭게 고르거나 직접 수정할 수 있습니다.")
        l_cues = QVBoxLayout(grp_cues)

        h_c1 = QHBoxLayout()
        h_c1.addWidget(QLabel("<b>시작 멘트:</b>"))
        self.combo_start = QComboBox()
        self.combo_start.setToolTip("운동을 시작할 때 사범님이 외치는 오프닝 멘트입니다.")
        self.combo_start.currentIndexChanged.connect(self.on_start_combo_changed)
        h_c1.addWidget(self.combo_start, 1)
        l_cues.addLayout(h_c1)

        self.txt_start_cue = QLineEdit()
        self.txt_start_cue.setToolTip("선택한 시작 멘트를 필요에 따라 직접 수정할 수 있습니다.")
        l_cues.addWidget(self.txt_start_cue)

        h_c2 = QHBoxLayout()
        h_c2.addWidget(QLabel("<b>종료 멘트:</b>"))
        self.combo_end = QComboBox()
        self.combo_end.setToolTip("준비운동이 끝났을 때 관원들에게 휴식이나 다음 대기를 지시하는 멘트입니다.")
        self.combo_end.currentIndexChanged.connect(self.on_end_combo_changed)
        h_c2.addWidget(self.combo_end, 1)
        l_cues.addLayout(h_c2)

        self.txt_end_cue = QLineEdit()
        self.txt_end_cue.setToolTip("선택한 종료 멘트를 필요에 따라 직접 수정할 수 있습니다.")
        l_cues.addWidget(self.txt_end_cue)

        self.update_cue_combos()
        content_layout.addWidget(grp_cues)

        # --- D. 동작 목록 및 순서 편집기 ---
        grp_moves = QGroupBox("4. 📋 세부 동작 목록 및 순서 편집 (체크박스로 ON/OFF 가능)")
        grp_moves.setToolTip("체크박스를 끄면 해당 동작을 건너뛰며, 위/아래 버튼으로 순서를 바꿀 수 있습니다.")
        l_moves = QVBoxLayout(grp_moves)

        self.table_moves = QTableWidget()
        self.table_moves.setColumnCount(4)
        self.table_moves.setHorizontalHeaderLabels(["선택", "동작 명칭", "사범 지도/구령 멘트 (더블클릭 수정)", "구령 방식"])
        self.table_moves.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_moves.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_moves.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_moves.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_moves.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_moves.setMinimumHeight(240)
        self.table_moves.setToolTip("목록에서 동작을 클릭하고 아래 [▲ 위로] / [▼ 아래로] 버튼을 눌러 순서를 변경하세요.")
        l_moves.addWidget(self.table_moves)

        h_tbl_btn = QHBoxLayout()
        btn_up = QPushButton("▲ 위로 이동")
        btn_up.setToolTip("선택한 동작을 한 칸 위로 올립니다.")
        btn_up.clicked.connect(self.move_item_up)
        btn_down = QPushButton("▼ 아래로 이동")
        btn_down.setToolTip("선택한 동작을 한 칸 아래로 내립니다.")
        btn_down.clicked.connect(self.move_item_down)
        btn_check_all = QPushButton("전체 선택")
        btn_check_all.clicked.connect(lambda: self.toggle_all_checks(True))
        btn_uncheck_all = QPushButton("전체 해제")
        btn_uncheck_all.clicked.connect(lambda: self.toggle_all_checks(False))

        h_tbl_btn.addWidget(btn_up)
        h_tbl_btn.addWidget(btn_down)
        h_tbl_btn.addSpacing(15)
        h_tbl_btn.addWidget(btn_check_all)
        h_tbl_btn.addWidget(btn_uncheck_all)
        h_tbl_btn.addStretch()
        l_moves.addLayout(h_tbl_btn)

        content_layout.addWidget(grp_moves)

        # --- E. 배경음악(BGM) 및 오토 더킹 ---
        grp_bgm = QGroupBox("5. 🎵 배경음악(BGM) & 볼륨 설정")
        grp_bgm.setToolTip("운동 중 흘러나올 배경음악을 지정하고, 사범 멘트 시 음악이 줄어드는 더킹(Auto-Ducking)을 설정합니다.")
        l_bgm = QVBoxLayout(grp_bgm)

        h_b1 = QHBoxLayout()
        self.lbl_bgm = QLabel("배경음악: (미지정 시 무음 믹싱)")
        btn_add_bgm = QPushButton("📂 BGM 파일 추가")
        btn_add_bgm.setToolTip("컴퓨터에 있는 MP3나 WAV 음악 파일을 선택하여 배경음악으로 지정합니다.")
        btn_add_bgm.clicked.connect(self.choose_bgm)
        btn_clr_bgm = QPushButton("초기화")
        btn_clr_bgm.clicked.connect(self.clear_bgm)

        h_b1.addWidget(self.lbl_bgm, 1)
        h_b1.addWidget(btn_add_bgm)
        h_b1.addWidget(btn_clr_bgm)
        l_bgm.addLayout(h_b1)

        h_b2 = QHBoxLayout()
        self.chk_ducking = QCheckBox("구령 및 멘트 출력 시 배경음악 자동 줄임 (오토 더킹)")
        self.chk_ducking.setChecked(True)
        self.chk_ducking.setToolTip("사범님의 목소리가 나올 때 음악 소리가 부드럽게 줄어들어 구령이 또렷하게 잘 들립니다.")
        h_b2.addWidget(self.chk_ducking)
        h_b2.addStretch()
        l_bgm.addLayout(h_b2)

        # 볼륨 슬라이더들
        h_b3 = QHBoxLayout()
        h_b3.addWidget(QLabel("BGM 볼륨:"))
        self.slider_bgm = QSlider(Qt.Orientation.Horizontal)
        self.slider_bgm.setRange(0, 100)
        self.slider_bgm.setValue(60)
        h_b3.addWidget(self.slider_bgm)

        h_b3.addWidget(QLabel("사범 음성 볼륨:"))
        self.slider_voice = QSlider(Qt.Orientation.Horizontal)
        self.slider_voice.setRange(0, 100)
        self.slider_voice.setValue(100)
        h_b3.addWidget(self.slider_voice)

        l_bgm.addLayout(h_b3)
        content_layout.addWidget(grp_bgm)

        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll, 1)

        # 3. 하단 진행 바 & 액션 버튼
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("준비 완료. [타임라인으로 로드] 또는 [WAV 파일 저장]을 클릭하세요.")
        self.lbl_status.setStyleSheet("color: #4a90e2; font-weight: bold;")
        main_layout.addWidget(self.lbl_status)

        h_bottom = QHBoxLayout()
        self.btn_generate_timeline = QPushButton("🚀 타임라인으로 바로 로드 (미세 편집/재생)")
        self.btn_generate_timeline.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; padding: 10px; font-size: 13px;")
        self.btn_generate_timeline.setToolTip("합성된 모든 구령과 효과음, BGM을 음악 편집기 타임라인에 트랙별로 올려서 즉시 재생 및 수정합니다.")
        self.btn_generate_timeline.clicked.connect(lambda: self.start_generation(target="timeline"))

        self.btn_generate_wav = QPushButton("💾 완성본 WAV 파일로 직접 저장")
        self.btn_generate_wav.setStyleSheet("background-color: #1976d2; color: white; font-weight: bold; padding: 10px; font-size: 13px;")
        self.btn_generate_wav.setToolTip("타임라인을 거치지 않고 최종 믹싱된 완성 오디오 파일(WAV)로 컴퓨터에 바로 저장합니다.")
        self.btn_generate_wav.clicked.connect(lambda: self.start_generation(target="file"))

        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(self.reject)

        h_bottom.addWidget(self.btn_generate_timeline, 2)
        h_bottom.addWidget(self.btn_generate_wav, 2)
        h_bottom.addWidget(btn_close, 1)
        main_layout.addLayout(h_bottom)

        self.refresh_table_display()

    def update_cue_combos(self):
        """언어에 따라 시작 및 종료 멘트 콤보박스 갱신"""
        lang = "kr" if self.rb_lang_kr.isChecked() else "en"

        self.combo_start.blockSignals(True)
        self.combo_start.clear()
        for c in START_CUES[lang]:
            self.combo_start.addItem(c)
        self.combo_start.blockSignals(False)
        self.txt_start_cue.setText(self.combo_start.currentText())

        self.combo_end.blockSignals(True)
        self.combo_end.clear()
        for c in END_CUES[lang]:
            self.combo_end.addItem(c)
        self.combo_end.blockSignals(False)
        self.txt_end_cue.setText(self.combo_end.currentText())

    def on_language_changed(self):
        self.update_cue_combos()
        self.refresh_table_display()

    def on_start_combo_changed(self, idx):
        if idx >= 0:
            self.txt_start_cue.setText(self.combo_start.currentText())

    def on_end_combo_changed(self, idx):
        if idx >= 0:
            self.txt_end_cue.setText(self.combo_end.currentText())

    def on_tempo_changed(self, val):
        desc = "도장 표준 (추천)"
        if val < 70:
            desc = "느림 / 요가·스트레칭"
        elif val > 95:
            desc = "빠름 / 점핑잭·워밍업"
        self.lbl_tempo.setText(f"{val} BPM ({desc})")

    def on_preset_changed(self, idx):
        pkey = self.combo_preset.currentData()
        if pkey and pkey in ROUTINE_PRESETS:
            self.apply_preset(pkey)

    def apply_preset(self, pkey: str):
        if pkey not in ROUTINE_PRESETS:
            return
        pdata = ROUTINE_PRESETS[pkey]
        self.lbl_preset_desc.setText(pdata["description_kr"])
        self.slider_tempo.setValue(pdata.get("default_tempo_bpm", 85))

        active_ids = set(pdata["movement_ids"])
        # 순서도 프리셋의 movement_ids 순서대로 정렬
        m_dict = {m["id"]: m for m in self.current_movements}
        new_list = []
        for mid in pdata["movement_ids"]:
            if mid in m_dict:
                m = m_dict[mid]
                m["enabled"] = True
                new_list.append(m)

        # 나머지 동작들은 뒤에 비활성화 상태로 추가
        for m in self.current_movements:
            if m["id"] not in active_ids:
                m["enabled"] = False
                new_list.append(m)

        self.current_movements = new_list
        self.refresh_table_display()

    def refresh_table_display(self):
        """테이블 위젯에 현재 동작 목록 렌더링"""
        lang = "kr" if self.rb_lang_kr.isChecked() else "en"
        mode = "detailed" if self.rb_mode_detailed.isChecked() else "quick"

        self.table_moves.setRowCount(len(self.current_movements))

        for row, mov in enumerate(self.current_movements):
            # 0. 체크박스
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk_item.setCheckState(Qt.CheckState.Checked if mov.get("enabled", True) else Qt.CheckState.Unchecked)
            self.table_moves.setItem(row, 0, chk_item)

            # 1. 명칭
            name_text = mov.get(f"name_{lang}", mov.get("name_kr", ""))
            name_item = QTableWidgetItem(name_text)
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table_moves.setItem(row, 1, name_item)

            # 2. 사범 멘트 (더블클릭 편집 가능)
            if mode == "detailed":
                cue_text = mov.get(f"instruction_{lang}", mov.get("instruction_kr", ""))
            else:
                cue_text = mov.get(f"short_cue_{lang}", mov.get("short_cue_kr", ""))

            cue_item = QTableWidgetItem(cue_text)
            cue_item.setToolTip("더블클릭하여 멘트를 원하는 대로 직접 수정할 수 있습니다.")
            self.table_moves.setItem(row, 2, cue_item)

            # 3. 구령 방식
            ctype = mov.get("count_type", "8count_x2")
            ctype_desc = "8박자 x 2회"
            if ctype == "8count_x4":
                ctype_desc = "8박자 x 4회"
            elif ctype == "forward_back_8count":
                ctype_desc = "등배운동 (손바닥/팔꿈치/뒤로)"
            elif ctype in ("cadence_10reps", "reps_10"):
                ctype_desc = "케이던스 10회 (하나,둘,셋,하나!)"
            elif ctype == "single_rep_10":
                ctype_desc = "단일 10회 (하나!... 둘!...)"
            elif ctype == "alternate_20reps":
                ctype_desc = "교대 20회 (왼발/오른발)"
            elif ctype == "bridge_pattern":
                ctype_desc = "브릿지 (3초-3초-10초)"
            elif "hold" in ctype:
                ctype_desc = "15초 정적 유지"
            elif "breathing" in ctype:
                ctype_desc = "심호흡 안내"

            cnt_item = QTableWidgetItem(ctype_desc)
            cnt_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table_moves.setItem(row, 3, cnt_item)

    def save_table_changes_to_memory(self):
        """테이블에서 사용자가 수정한 체크박스 상태와 멘트 반영"""
        lang = "kr" if self.rb_lang_kr.isChecked() else "en"
        mode = "detailed" if self.rb_mode_detailed.isChecked() else "quick"

        for row in range(self.table_moves.rowCount()):
            if row < len(self.current_movements):
                mov = self.current_movements[row]
                chk_it = self.table_moves.item(row, 0)
                if chk_it:
                    mov["enabled"] = (chk_it.checkState() == Qt.CheckState.Checked)

                cue_it = self.table_moves.item(row, 2)
                if cue_it:
                    new_txt = cue_it.text().strip()
                    if mode == "detailed":
                        mov[f"instruction_{lang}"] = new_txt
                    else:
                        mov[f"short_cue_{lang}"] = new_txt

    def save_custom_template(self):
        """현재 편집 중인 루틴 전체(동작 목록, 순서, 멘트, 템포, 시작/종료멘트)를 JSON 템플릿 파일로 저장"""
        self.save_table_changes_to_memory()

        default_name = "나만의_준비운동_루틴.json"
        save_path, _ = QFileDialog.getSaveFileName(
            self, "나만의 준비운동 템플릿 저장",
            default_name,
            "JSON Files (*.json)",
            options=QFileDialog.Option.DontUseNativeDialog
        )
        if not save_path:
            return

        if not save_path.endswith(".json"):
            save_path += ".json"

        data = {
            "template_name": self.combo_preset.currentText(),
            "language": "kr" if self.rb_lang_kr.isChecked() else "en",
            "coaching_mode": "detailed" if self.rb_mode_detailed.isChecked() else "quick",
            "tempo_bpm": self.slider_tempo.value(),
            "signal_type": self.combo_signal.currentData() or "bell",
            "start_cue": self.txt_start_cue.text().strip(),
            "end_cue": self.txt_end_cue.text().strip(),
            "movements": self.current_movements
        }

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            QMessageBox.information(
                self, "저장 완료",
                f"🎉 나만의 준비운동 템플릿이 성공적으로 저장되었습니다!\n파일: {os.path.basename(save_path)}"
            )
        except Exception as e:
            QMessageBox.critical(self, "저장 오류", f"템플릿 저장 중 오류가 발생했습니다:\n{str(e)}")

    def load_custom_template(self):
        """외부 JSON 템플릿 파일을 불러와 UI 및 동작 리스트에 즉시 반영"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "준비운동 템플릿 불러오기",
            "",
            "JSON Files (*.json)",
            options=QFileDialog.Option.DontUseNativeDialog
        )
        if not file_path or not os.path.exists(file_path):
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            loaded_moves = data.get("movements", [])
            if not loaded_moves:
                QMessageBox.warning(self, "형식 오류", "템플릿 파일 내에 동작(movements) 데이터가 없습니다.")
                return

            self.current_movements = loaded_moves

            # 언어 복원
            if data.get("language") == "en":
                self.rb_lang_en.setChecked(True)
            else:
                self.rb_lang_kr.setChecked(True)

            # 진행 모드 복원
            if data.get("coaching_mode") == "quick":
                self.rb_mode_quick.setChecked(True)
            else:
                self.rb_mode_detailed.setChecked(True)

            # 템포 복원
            if "tempo_bpm" in data:
                self.slider_tempo.setValue(data["tempo_bpm"])

            # 신호음 복원
            if "signal_type" in data:
                idx = self.combo_signal.findData(data["signal_type"])
                if idx >= 0:
                    self.combo_signal.setCurrentIndex(idx)

            # 멘트 복원
            if "start_cue" in data:
                self.txt_start_cue.setText(data["start_cue"])
            if "end_cue" in data:
                self.txt_end_cue.setText(data["end_cue"])

            # 프리셋 콤보박스를 [사용자 정의]로 변경
            custom_idx = self.combo_preset.findData("custom")
            if custom_idx >= 0:
                self.combo_preset.blockSignals(True)
                self.combo_preset.setCurrentIndex(custom_idx)
                self.combo_preset.blockSignals(False)
            tpl_name = data.get("template_name", os.path.basename(file_path))
            self.lbl_preset_desc.setText(f"📂 외부 템플릿 로드됨: {tpl_name}")

            self.refresh_table_display()
            QMessageBox.information(
                self, "불러오기 완료",
                f"✅ '{tpl_name}' 템플릿을 성공적으로 불러왔습니다!\n동작 목록과 설정이 화면에 반영되었습니다."
            )

        except Exception as e:
            QMessageBox.critical(self, "불러오기 오류", f"템플릿 파일을 읽는 중 오류가 발생했습니다:\n{str(e)}")

    def move_item_up(self):
        row = self.table_moves.currentRow()
        if row > 0:
            self.save_table_changes_to_memory()
            self.current_movements[row - 1], self.current_movements[row] = (
                self.current_movements[row], self.current_movements[row - 1]
            )
            self.refresh_table_display()
            self.table_moves.selectRow(row - 1)

    def move_item_down(self):
        row = self.table_moves.currentRow()
        if 0 <= row < len(self.current_movements) - 1:
            self.save_table_changes_to_memory()
            self.current_movements[row], self.current_movements[row + 1] = (
                self.current_movements[row + 1], self.current_movements[row]
            )
            self.refresh_table_display()
            self.table_moves.selectRow(row + 1)

    def toggle_all_checks(self, checked: bool):
        for row in range(self.table_moves.rowCount()):
            item = self.table_moves.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    def choose_bgm(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "배경음악(BGM) 선택", "", "Audio Files (*.mp3 *.wav *.ogg *.m4a)"
        )
        if files:
            self.bgm_paths = files
            names = ", ".join([os.path.basename(f) for f in files[:2]])
            if len(files) > 2:
                names += f" 외 {len(files)-2}곡"
            self.lbl_bgm.setText(f"배경음악: {names}")

    def clear_bgm(self):
        self.bgm_paths = []
        self.lbl_bgm.setText("배경음악: (미지정 시 무음 믹싱)")

    def start_generation(self, target: str = "timeline"):
        """오디오 합성 프로세스 시작"""
        self.save_table_changes_to_memory()

        active_count = sum(1 for m in self.current_movements if m.get("enabled", True))
        if active_count == 0:
            QMessageBox.warning(self, "선택 필요", "최소 하나 이상의 동작을 체크박스로 선택해 주세요.")
            return

        lang = "kr" if self.rb_lang_kr.isChecked() else "en"
        mode = "detailed" if self.rb_mode_detailed.isChecked() else "quick"
        sig = self.combo_signal.currentData() or "bell"

        params = {
            "language": lang,
            "coaching_mode": mode,
            "tempo_bpm": self.slider_tempo.value(),
            "signal_type": sig,
            "start_cue": self.txt_start_cue.text().strip(),
            "end_cue": self.txt_end_cue.text().strip(),
            "movements": self.current_movements,
            "bgm_vol_pct": self.slider_bgm.value(),
            "voice_vol_pct": self.slider_voice.value(),
            "signal_vol_pct": 95,
            "auto_ducking": self.chk_ducking.isChecked(),
            "duck_db": -14.0,
            "routine_name": self.combo_preset.currentText(),
            "target": target
        }

        self.btn_generate_timeline.setEnabled(False)
        self.btn_generate_wav.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.lbl_status.setText("준비운동 오디오 합성 및 믹싱을 시작합니다...")

        self.synth_thread = WarmupSynthThread(params, self.bgm_paths, self.tts_engine)
        self.synth_thread.progress.connect(self.on_synth_progress)
        self.synth_thread.finished.connect(lambda ok, msg, data: self.on_synth_finished(ok, msg, data, target))
        self.synth_thread.start()

    def on_synth_progress(self, pct: int, msg: str):
        self.progress_bar.setValue(pct)
        self.lbl_status.setText(msg)

    def on_synth_finished(self, ok: bool, msg: str, data: Dict[str, Any], target: str):
        self.btn_generate_timeline.setEnabled(True)
        self.btn_generate_wav.setEnabled(True)
        self.progress_bar.setVisible(False)

        if not ok:
            self.lbl_status.setText(f"❌ 생성 실패: {msg}")
            QMessageBox.critical(self, "생성 오류", f"음원 생성 중 오류가 발생했습니다:\n{msg}")
            return

        self.generated_result = data
        dur_sec = data.get("total_duration_sec", 0.0)
        m = int(dur_sec // 60)
        s = int(dur_sec % 60)

        if target == "timeline":
            QMessageBox.information(
                self, "생성 완료",
                f"🎉 총 {m}분 {s}초 분량의 준비운동 음원이 성공적으로 생성되었습니다!\n"
                "[확인]을 누르면 음악 편집기 타임라인으로 즉시 로드됩니다."
            )
            self.accept()
        else:
            # 직접 파일 저장
            save_path, _ = QFileDialog.getSaveFileName(
                self, "준비운동 완성 음원 저장",
                f"준비운동_{data.get('routine_name', '스트레칭')}_{m}분{s}초.wav",
                "Audio Files (*.wav *.mp3)",
                options=QFileDialog.Option.DontUseNativeDialog
            )
            if save_path:
                if not os.path.splitext(save_path)[1]:
                    save_path += ".wav"
                import shutil
                shutil.copy(data["master_audio_path"], save_path)
                QMessageBox.information(self, "저장 완료", f"파일이 성공적으로 저장되었습니다:\n{save_path}")
            self.accept()
