"""
Sparring & Kicking Training Dialog (스파링 발차기 트레이닝 음원 생성 마법사)
Supports customized training for dojos:
- 1:1, 1:2, 1:3 Relay kicking (다자간 미트 순환)
- Reaction kicking (스텝 & 실전 반사 반응)
- Combo interval kicking (스텝 + 콤비네이션 연타)
- Sparring round simulator (정규 스파링 라운드)

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
    QProgressBar, QGroupBox, QScrollArea, QWidget, QLineEdit, QTextEdit, QTabWidget, QApplication, QSlider
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from core.sparring_training_engine import SparringTrainingEngine, CIRCUIT_INTERVAL_THEMES
from core.shuttle_run_engine import ShuttleRunEngine
from utils.effects_generator import ensure_default_effects
from pydub import AudioSegment
from pydub.effects import normalize


def vol_pct_to_db(pct: int) -> float:
    """선형 퍼센트(%) 볼륨을 데시벨(dB)로 변환 (0% -> -60dB 무음, 100% -> 0dB)"""
    if pct <= 0:
        return -60.0
    return round(20.0 * math.log10(pct / 100.0), 2)


def trim_audio_silence(seg: AudioSegment, threshold: float = -42.0) -> AudioSegment:
    """TTS 음성의 앞쪽 무음은 타이트하게 자르되, 뒤쪽은 말끝 여운(모음/자음 감쇄)이 잘리지 않도록 안전 여백(300ms)을 보존함"""
    try:
        from pydub.silence import detect_leading_silence
        lead = detect_leading_silence(seg, silence_threshold=threshold)
        trail = detect_leading_silence(seg.reverse(), silence_threshold=threshold)
        # 말끝이 툭 끊기지 않도록 뒤쪽 무음 중 300ms를 안전하게 남김
        safe_trail = max(0, trail - 300)
        end_idx = max(lead, len(seg) - safe_trail)
        trimmed = seg[lead:end_idx]
        return trimmed if len(trimmed) >= 80 else seg
    except Exception:
        return seg


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
            events = schedule_data.get("events", [])
            duck_segments = schedule_data.get("duck_segments", [])
            total_duration_sec = schedule_data.get("total_duration_sec", 0.0)
            total_duration_ms = int(total_duration_sec * 1000)

            # 2. 음성 멘트 및 카운트다운 합성 (Edge-TTS 활용)
            use_voice = self.params.get("use_voice", True)
            voice_speaker = self.params.get("voice_speaker", "선히")
            voice_id = "ko-KR-SunHiNeural"
            if "인준" in voice_speaker:
                voice_id = "ko-KR-InJoonNeural"
            elif "현수" in voice_speaker:
                voice_id = "ko-KR-HyunsuMultilingualNeural"

            os.makedirs(os.path.join("projects", "temp_tts"), exist_ok=True)
            voice_cache = {}

            is_female = "선히" in voice_speaker or "여성" in voice_speaker
            en_voice = "en-US-JennyNeural" if is_female else "en-US-GuyNeural"

            # 2-1. 카운트다운 오디오 준비 (영어 본토 발음 및 한국어 지원)
            countdown_events = [ev for ev in events if ev["type"] == "countdown"]
            if countdown_events:
                cd_style = self.params.get("countdown_style", "en_321")
                cd_file = None

                # Helper for word-by-word stepped countdown with 1.5s (1500ms) delay
                async def _synth_stepped_cd(words: List[str], voice: str, rate: str = "+0%") -> AudioSegment:
                    silence_gap = AudioSegment.silent(duration=1500)
                    segs = []
                    for w in words:
                        comm = edge_tts.Communicate(w, voice, rate=rate)
                        buf = io.BytesIO()
                        async for chunk in comm.stream():
                            if chunk['type'] == 'audio':
                                buf.write(chunk['data'])
                        buf.seek(0)
                        s = trim_audio_silence(AudioSegment.from_file(buf, format="mp3"))
                        segs.append(s)
                    full = segs[0]
                    for s in segs[1:]:
                        full = full + silence_gap + s
                    return full

                if cd_style == "beep":
                    self.progress.emit(10, "전자 비프음 카운트다운(3박자 띡-띡-띡) 준비 중...")
                    cd_beeps = os.path.join("effects", "countdown_beeps.wav")
                    if os.path.exists(cd_beeps):
                        cd_file = cd_beeps
                elif cd_style == "en_ready":
                    self.progress.emit(10, "영어 카운트다운(Are you ready? Ready! Three, Two, One) 1.5초 간격 생성 중...")
                    cd_path = os.path.join("projects", "temp_tts", f"sparring_cd_en_ready_{uuid.uuid4().hex[:6]}.wav")
                    try:
                        import edge_tts, io
                        async def _synth_cd():
                            full_seg = await _synth_stepped_cd(["Are you ready? Ready!", "Three", "Two", "One"], en_voice, rate="+5%")
                            full_seg.export(cd_path, format="wav")
                        asyncio.run(_synth_cd())
                        if os.path.exists(cd_path):
                            cd_file = cd_path
                    except Exception as e_cd:
                        print(f"[SparringWorker] countdown TTS fail: {e_cd}")
                elif cd_style == "ko_ready":
                    self.progress.emit(10, "한국어 카운트다운(준비되었나요? 준비! 셋, 둘, 하나) 1.5초 간격 생성 중...")
                    cd_path = os.path.join("projects", "temp_tts", f"sparring_cd_ko_ready_{uuid.uuid4().hex[:6]}.wav")
                    try:
                        import edge_tts, io
                        async def _synth_cd():
                            full_seg = await _synth_stepped_cd(["준비되었나요? 준비!", "셋", "둘", "하나"], voice_id, rate="+5%")
                            full_seg.export(cd_path, format="wav")
                        asyncio.run(_synth_cd())
                        if os.path.exists(cd_path):
                            cd_file = cd_path
                    except Exception as e_cd:
                        print(f"[SparringWorker] countdown TTS fail: {e_cd}")
                elif cd_style == "ko_321":
                    self.progress.emit(10, "한국어 카운트다운(셋, 둘, 하나) 1.5초 간격 생성 중...")
                    cd_path = os.path.join("projects", "temp_tts", f"sparring_cd_ko_321_{uuid.uuid4().hex[:6]}.wav")
                    try:
                        import edge_tts, io
                        async def _synth_cd():
                            full_seg = await _synth_stepped_cd(["셋", "둘", "하나"], voice_id, rate="+5%")
                            full_seg.export(cd_path, format="wav")
                        asyncio.run(_synth_cd())
                        if os.path.exists(cd_path):
                            cd_file = cd_path
                    except Exception as e_cd:
                        print(f"[SparringWorker] countdown TTS fail: {e_cd}")
                else:  # en_321 기본값 (본토 영어 발음)
                    self.progress.emit(10, "영어 본토 발음 카운트다운(Three, Two, One) 1.5초 간격 생성 중...")
                    cd_path = os.path.join("projects", "temp_tts", f"sparring_cd_en_321_{uuid.uuid4().hex[:6]}.wav")
                    try:
                        import edge_tts, io
                        async def _synth_cd():
                            full_seg = await _synth_stepped_cd(["Three", "Two", "One"], en_voice, rate="+5%")
                            full_seg.export(cd_path, format="wav")
                        asyncio.run(_synth_cd())
                        if os.path.exists(cd_path):
                            cd_file = cd_path
                    except Exception as e_cd:
                        print(f"[SparringWorker] countdown TTS fail: {e_cd}")

                if cd_file and os.path.exists(cd_file):
                    dur = len(AudioSegment.from_file(cd_file)) / 1000.0
                    for cev in countdown_events:
                        cev["sound_file"] = cd_file
                        cev["duration"] = dur

            # 2-2. 본 구령 음성 합성
            voice_events = [ev for ev in events if ev["type"] == "voice"]
            for idx, ev in enumerate(voice_events):
                pct = 15 + int(45 * ((idx + 1) / max(len(voice_events), 1)))
                text = ev["text"]
                # Clean text for TTS (remove [bracketed tags])
                clean_text = text
                if "[" in text and "]" in text:
                    parts = text.split("]", 1)
                    clean_text = parts[1].strip() if len(parts) > 1 and parts[1].strip() else parts[0].strip("[")

                # 혹시라도 포함되었을 수 있는 '출발' 단어 완전 제거
                clean_text = clean_text.replace("출발!", "").replace("출발", "").strip()

                self.progress.emit(pct, f"훈련 구령 음성 합성 중 ({idx+1}/{len(voice_events)}): {clean_text[:12]}...")

                if clean_text in voice_cache:
                    ev["sound_file"] = voice_cache[clean_text]["file"]
                    ev["duration"] = voice_cache[clean_text]["duration"]
                else:
                    v_path = os.path.join("projects", "temp_tts", f"sparring_v_{uuid.uuid4().hex[:6]}.wav")
                    try:
                        import edge_tts
                        import io
                        import re

                        # 텍스트가 영문 전용(한글 미포함)일 경우 미국 본토 원어민 성우(en_voice) 적용!
                        has_korean = bool(re.search(r'[가-힣]', clean_text))
                        has_english = bool(re.search(r'[a-zA-Z]', clean_text))
                        target_voice = en_voice if (has_english and not has_korean) else voice_id
                        rate_val = "+10%" if (has_english and not has_korean) else "+0%"

                        async def _synth(t, v, path):
                            comm = edge_tts.Communicate(t, v, rate=rate_val)
                            buf = io.BytesIO()
                            async for chunk in comm.stream():
                                if chunk['type'] == 'audio':
                                    buf.write(chunk['data'])
                            buf.seek(0)
                            raw_seg = AudioSegment.from_file(buf, format="mp3")
                            trimmed_seg = trim_audio_silence(raw_seg)
                            trimmed_seg.export(path, format="wav")

                        asyncio.run(_synth(clean_text, target_voice, v_path))
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

            # 2-3. 실제 오디오 실측 길이를 기반으로 동적 타임라인 체이닝 및 1.0초 정밀 딜레이 정렬
            # (사용자 요청: B선수 명칭/기술 발성 종료를 실제 오디오 길이로 확인 후 정확히 1.0초 딜레이 후 신호음 배치, 말 잘림 원천 방지)
            events.sort(key=lambda x: x["time"])

            for i in range(len(events) - 1):
                curr_ev = events[i]
                next_ev = events[i + 1]

                curr_dur = curr_ev.get("duration", 0.5)
                curr_end = curr_ev["time"] + curr_dur
                curr_type = curr_ev.get("type", "")
                next_type = next_ev.get("type", "")
                next_text = next_ev.get("text", "")

                # 1) 다자간 릴레이 타격 신호음(삑~익!)인 경우:
                # 선수 호출 및 기술 설명 음성이 완전히 끝난 후 정확히 1.0초 뒤에 신호음이 울리도록 동적 정렬!
                if "타격 신호음" in next_text and curr_type == "voice":
                    target_next_time = round(curr_end + 1.0, 2)
                    delta = round(target_next_time - next_ev["time"], 2)
                    if abs(delta) > 0.01:
                        for j in range(i + 1, len(events)):
                            events[j]["time"] = round(events[j]["time"] + delta, 2)

                # 2) 기타 구령 음성 직후 신호음/트리거인 경우: 최소 1.0초 딜레이 보장
                elif curr_type == "voice" and next_type in ("beep", "signal", "whistle"):
                    min_target_time = round(curr_end + 1.0, 2)
                    if next_ev["time"] < min_target_time:
                        delta = round(min_target_time - next_ev["time"], 2)
                        for j in range(i + 1, len(events)):
                            events[j]["time"] = round(events[j]["time"] + delta, 2)

                # 3) 사전 안내나 카운트다운 음성 직후 다음 이벤트: 최소 0.8초 안전 간격 확보
                elif curr_type in ("voice", "countdown"):
                    min_target_time = round(curr_end + 0.8, 2)
                    if next_ev["time"] < min_target_time:
                        delta = round(min_target_time - next_ev["time"], 2)
                        for j in range(i + 1, len(events)):
                            events[j]["time"] = round(events[j]["time"] + delta, 2)

                # 4) 신호음 직후 다음 이벤트: 최소 0.05초 확보하여 오디오 중첩 방지
                elif curr_type in ("beep", "signal", "whistle", "bell"):
                    min_target_time = round(curr_end + 0.05, 2)
                    if next_ev["time"] < min_target_time:
                        delta = round(min_target_time - next_ev["time"], 2)
                        for j in range(i + 1, len(events)):
                            events[j]["time"] = round(events[j]["time"] + delta, 2)

            # 2-4. 타임라인 재정렬에 맞춘 오토덕킹 구간(duck_segments) 및 전체 재생시간 재계산
            # ⭐ 사용자 요청: 비프음/신호음/휘슬/벨은 모두 0dB(감쇄 없음)로 음악을 온전히 유지하고,
            # 오직 음성(TTS 안내 및 구령) 시에만 오토덕킹이 작동하도록 처리 (음악 끊김/렉 방지)
            duck_segments = []
            for ev in events:
                ev_type = ev.get("type", "")
                is_voice = (ev_type == "voice")
                if ev_type == "countdown" and ev.get("cd_style") != "beep":
                    is_voice = True

                if is_voice:
                    st_ms = int(ev["time"] * 1000)
                    dur_ms = int(ev.get("duration", 0.5) * 1000)
                    duck_segments.append((st_ms, st_ms + dur_ms + 200))

            if events:
                last_ev = events[-1]
                last_end_sec = last_ev["time"] + last_ev.get("duration", 1.0)
                total_duration_sec = round(last_end_sec + 2.0, 2)
                total_duration_ms = int(total_duration_sec * 1000)

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
                    clip_vol = voice_vol_db if ev.get("type") in ("voice", "countdown") else sig_vol_db
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
                "mode_name": SparringTrainingEngine.TRAINING_MODES.get(self.mode, {}).get("name", "스파링 훈련"),
                "timeline_clips": timeline_clips,
                "master_audio_path": output_master_path,
                "total_duration_sec": total_duration_sec
            }
            self.finished.emit(True, "스파링 훈련 음원이 성공적으로 생성되었습니다.", result_data)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.finished.emit(False, f"음원 생성 중 오류 발생: {str(e)}", {})


class SparringDialog(QDialog):
    """스파링 훈련 음원 생성 마법사 UI 다이얼로그"""

    def __init__(self, parent=None, tts_engine=None):
        super().__init__(parent)
        self.tts_engine = tts_engine
        self.setWindowTitle("🥋 스파링 & 기능성 인터벌 마법사 (HIIT·순발력·민첩성·대련)")
        self.resize(720, 800)
        self.bgm_playlist: List[str] = []
        self.generated_result = None

        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # 상단 안내 배너
        header_box = QGroupBox()
        header_box.setStyleSheet("background-color: #fdf2f8; border: 1px solid #fbcfe8; border-radius: 8px; padding: 6px;")
        hb_layout = QVBoxLayout(header_box)
        title_lbl = QLabel("🥋 맞춤형 실전 스파링 & 기능성 인터벌(HIIT) 훈련 음원 마법사")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #9d174d;")
        desc_lbl = QLabel(
            "오늘의 훈련 목표(기능성 서킷 인터벌, 1:1/1:2/1:3 릴레이 미트, 스텝 반응, 연타 콤보, 스파링 라운드)에 맞춰\n"
            "순발력, 민첩성, 근력, 반사신경, 발차기 기술과 수준별(유치부 한영믹스/초등부/원어민) 구령을 자동 합성합니다."
        )
        desc_lbl.setStyleSheet("color: #475569; font-size: 12px;")
        hb_layout.addWidget(title_lbl)
        hb_layout.addWidget(desc_lbl)
        main_layout.addWidget(header_box)

        # 스크롤 영역 생성 (작은 화면에서도 하단 버튼이 잘리지 않고 전체 스크롤 지원)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)

        # 5가지 훈련 모드 탭 (기능성 인터벌 신설)
        self.tabs = QTabWidget()

        # ── 탭 0: 🔥 기능성 서킷 인터벌 (HIIT & Tabata) ──
        tab_circuit = QWidget()
        l_circuit = QVBoxLayout(tab_circuit)

        circuit_info = QLabel("💡 [실전 복합 콤보 루프(Flow Loop) 방식]: 세트당 단순 1동작이 아닙니다. 15~20초 운동 시간 동안 [기초 체력(점프/버피) ➔ 실전 발차기 ➔ 회전낙법/점프턴]을 1세트로 묶어 전력으로 무한 반복하고 10초 휴식하는, 도장 실전 대련에 최적화된 복합 서킷 인터벌입니다.")
        circuit_info.setStyleSheet("background-color: #fff1f2; border: 1px solid #fecdd3; border-radius: 6px; padding: 6px 10px; font-weight: bold; color: #be123c; font-size: 12px;")
        l_circuit.addWidget(circuit_info)

        # 1. 훈련 테마 선택
        g_c_theme = QGroupBox("1. 서킷 인터벌 훈련 테마 선택")
        l_ct = QVBoxLayout(g_c_theme)
        self.combo_circuit_theme = QComboBox()
        self.combo_circuit_theme.addItem("🥋 [대련 실전 & 낙법 협응 콤보] 점프·발차기·회전낙법 무한 루프", "power_agility")
        self.combo_circuit_theme.addItem("⚡ [순발력 & 민첩성 폭발 콤보] 버피·점프턴·나래차기 순환 루프", "agility_power_combo")
        self.combo_circuit_theme.addItem("🏃‍♂️ [스파링 풋워크 & 반사신경 콤보] 스텝·카운터킥·회전낙법 루프", "footwork_reaction_combo")
        self.combo_circuit_theme.addItem("💪 [근지구력 & 심폐 협응 파워 콤보] 푸시업·복근·연타킥 전신 서킷", "strength_endurance_combo")
        self.combo_circuit_theme.currentIndexChanged.connect(self._on_circuit_theme_changed)
        l_ct.addWidget(self.combo_circuit_theme)
        l_circuit.addWidget(g_c_theme)

        # 2. 연령/수준별 맞춤 구령 언어 선택
        g_c_lang = QGroupBox("2. 연령/수준별 맞춤 구령 언어")
        l_cl = QVBoxLayout(g_c_lang)
        self.combo_circuit_lang = QComboBox()
        self.combo_circuit_lang.addItem("👶 유치부·7세 미만 기초 [한-영 단어 믹스] (한국어 + 핵심 영어단어 조합)", "mix_kids")
        self.combo_circuit_lang.addItem("🎒 초등부 순차 구령 [한국어 선행 + 쉬운 영어] (동작 후 영어 멘트)", "dual_step")
        self.combo_circuit_lang.addItem("🇰🇷 일반부·정규 도장 [표준 한국어 구령]", "kr")
        self.combo_circuit_lang.addItem("🇺🇸 상급반·국제 지도 [원어민 영어 전용 Full English]", "en_advanced")
        self.combo_circuit_lang.currentIndexChanged.connect(self._on_circuit_lang_changed)
        l_cl.addWidget(self.combo_circuit_lang)
        l_circuit.addWidget(g_c_lang)

        # 3. 시간 및 세트 설정
        g_c_time = QGroupBox("3. 인터벌 시간 및 세트 설정")
        l_ctime = QVBoxLayout(g_c_time)

        h_ct1 = QHBoxLayout()
        h_ct1.addWidget(QLabel("운동(전력) 시간:"))
        self.sp_circuit_work = QSpinBox()
        self.sp_circuit_work.setRange(5, 120)
        self.sp_circuit_work.setValue(20)
        self.sp_circuit_work.setSuffix(" 초")
        h_ct1.addWidget(self.sp_circuit_work)

        h_ct1.addWidget(QLabel("휴식(숨고르기) 시간:"))
        self.sp_circuit_rest = QSpinBox()
        self.sp_circuit_rest.setRange(5, 60)
        self.sp_circuit_rest.setValue(10)
        self.sp_circuit_rest.setSuffix(" 초")
        h_ct1.addWidget(self.sp_circuit_rest)

        h_ct1.addWidget(QLabel("총 세트 수:"))
        self.sp_circuit_sets = QSpinBox()
        self.sp_circuit_sets.setRange(1, 30)
        self.sp_circuit_sets.setValue(8)
        self.sp_circuit_sets.setSuffix(" 세트")
        h_ct1.addWidget(self.sp_circuit_sets)
        l_ctime.addLayout(h_ct1)

        # 빠른 프리셋 버튼
        h_c_preset = QHBoxLayout()
        h_c_preset.addWidget(QLabel("⚡ 빠른 세팅:"))
        btn_tabata = QPushButton("타바타 정석 (20초/10초/8세트)")
        btn_tabata.clicked.connect(lambda: self._set_circuit_time_preset(20, 10, 8))
        btn_speed = QPushButton("도장 스피드 (15초/10초/6세트)")
        btn_speed.clicked.connect(lambda: self._set_circuit_time_preset(15, 10, 6))
        btn_power = QPushButton("체력 강화 (30초/15초/8세트)")
        btn_power.clicked.connect(lambda: self._set_circuit_time_preset(30, 15, 8))
        h_c_preset.addWidget(btn_tabata)
        h_c_preset.addWidget(btn_speed)
        h_c_preset.addWidget(btn_power)
        l_ctime.addLayout(h_c_preset)
        l_circuit.addWidget(g_c_time)

        # 4. 세부 훈련 동작 구성 및 사범 지도 팁
        g_c_moves = QGroupBox("4. 세트별 복합 콤보 루틴 구성 및 사범 지도 팁 (직접 편집 가능)")
        l_cm = QVBoxLayout(g_c_moves)

        # 진행 방식 선택 (종목 순환 vs 단일 종목 집중 반복)
        h_cm_mode = QHBoxLayout()
        h_cm_mode.addWidget(QLabel("🎯 진행 방식:"))
        self.rb_circuit_cycle = QRadioButton("🔄 세트마다 종목 순환 (1번➔2번➔3번 콤보 순환)")
        self.rb_circuit_single = QRadioButton("🎯 단일 종목 집중 반복 (1세트 설명 후 2세트부터 설명 없이 3,2,1로 즉시 진행)")
        self.rb_circuit_cycle.setChecked(True)
        h_cm_mode.addWidget(self.rb_circuit_cycle)
        h_cm_mode.addWidget(self.rb_circuit_single)
        h_cm_mode.addStretch()
        l_cm.addLayout(h_cm_mode)

        self.txt_circuit_moves = QTextEdit()
        self.txt_circuit_moves.setMaximumHeight(170)
        l_cm.addWidget(self.txt_circuit_moves)

        lbl_moves_hint = QLabel("※ 위 콤보 내용을 직접 추가/수정/삭제할 수 있으며, 실제 음원에 그대로 반영됩니다. '종목 순환'은 매 세트 콤보를 호명하며 진행되고, '단일 종목 집중 반복'은 1세트에서만 1번 콤보를 설명하고 2세트부터는 설명 없이 준비 3,2,1로 빠르게 진행됩니다.")
        lbl_moves_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        l_cm.addWidget(lbl_moves_hint)
        l_circuit.addWidget(g_c_moves)
        l_circuit.addStretch()

        self.tabs.addTab(tab_circuit, "🔥 기능성 서킷 인터벌 (HIIT)")

        # ── 탭 1: 1:1, 1:2, 1:3 릴레이 미트 ──
        tab_relay = QWidget()
        l_relay = QVBoxLayout(tab_relay)

        # 실전 훈련 시퀀스 흐름 안내
        relay_flow_info = QLabel("💡 동작 흐름: [선수 호명 및 기술 설명] ➔ (0.25초) ➔ [🔔 삑! 타격 신호음] ➔ [타격] ➔ [🗣️ '선수 교대! B선수 준비!'] (절대 '출발' 단어 없음)")
        relay_flow_info.setStyleSheet("background-color: #fdf4ff; border: 1px solid #f5d0fe; border-radius: 6px; padding: 6px 10px; font-weight: bold; color: #86198f; font-size: 12px;")
        l_relay.addWidget(relay_flow_info)
        
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

        g_relay_t = QGroupBox("시간 및 실전 훈련 설정")
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

        h_rt1.addWidget(QLabel("설명 후 준비 대기 시간:"))
        self.sp_relay_prep_wait = QSpinBox()
        self.sp_relay_prep_wait.setRange(0, 60)
        self.sp_relay_prep_wait.setValue(10)
        self.sp_relay_prep_wait.setSuffix(" 초")
        self.sp_relay_prep_wait.setToolTip("사전 설명 음성 후 받기자들이 암미트/손미트를 착용하고 위치를 잡는 준비 대기 시간입니다. (0초 설정 시 대기 없이 즉시 시작)")
        h_rt1.addWidget(self.sp_relay_prep_wait)

        h_rt1.addWidget(QLabel("전체 세트:"))
        self.sp_relay_cycles = QSpinBox()
        self.sp_relay_cycles.setRange(1, 10)
        self.sp_relay_cycles.setValue(3)
        self.sp_relay_cycles.setSuffix(" 세트")
        h_rt1.addWidget(self.sp_relay_cycles)
        l_rt.addLayout(h_rt1)

        # 릴레이 훈련 기술 템플릿 선택 드롭다운
        h_rt_tmpl = QHBoxLayout()
        h_rt_tmpl.addWidget(QLabel("📋 실전 훈련 템플릿:"))
        self.combo_relay_template = QComboBox()
        self.combo_relay_template.addItem("🥋 [실전 3인 방족술/미트] 1번: 잡고 몸통 밀기 / 2번: 암미트 전진 몸통 / 3번: 손미트 상단 끊어차기", "tmpl_bangjok")
        self.combo_relay_template.addItem("⚡ [실전 스파링 콤보 1] A선수: 백스텝 받아차기 교차 상단 / B선수: 전진 몸통 후 사이드 왼발 상단", "tmpl_combo1")
        self.combo_relay_template.addItem("🎯 [카운터 & 반격 콤보] 1번: 앞발 컷트 후 뒷발 상단 / 2번: 사이드 스텝 뒤차기 카운터", "tmpl_counter")
        self.combo_relay_template.addItem("🛡️ [단일 기술 집중] 백스텝 후 받아차기 교차 상단", "tmpl_single")
        self.combo_relay_template.addItem("🔥 [연타 콤보] 1연타, 2연타, 3연타, 나래차기 연타", "tmpl_speed")
        self.combo_relay_template.currentIndexChanged.connect(self._on_relay_template_changed)
        h_rt_tmpl.addWidget(self.combo_relay_template, stretch=1)
        l_rt.addLayout(h_rt_tmpl)

        # 1. 훈련 종합 설명 & 받기자 미트 착용 행동요령 (사전 안내 다중 행 입력)
        l_rt.addWidget(QLabel("📢 훈련 종합 설명 & 받기자 미트 착용 행동요령 (시작 전 사전 안내 음성):"))
        self.txt_relay_intro = QTextEdit()
        self.txt_relay_intro.setFixedHeight(75)
        self.txt_relay_intro.setPlaceholderText("시작 전 선수와 받기자들에게 송출할 종합 훈련 안내 및 미트 착용 요령을 입력하세요 (엔터로 줄바꿈 가능)")
        self.txt_relay_intro.setPlainText("1번 방족술 - 한손 잡고 반대손 몸통 밀기. 2번 방족술 모션으로 전진 스텝 후 뒷발 몸통 차기! 2번 받기자 암미트 착용, 3번 조금씩 거리 좁히며 빠른발 상단 끊어차기!, 3번 받기자 손미트 착용, 빠르게 준비해 주세요. 플레이어는 패턴을 숙지해 주세요.")
        l_rt.addWidget(self.txt_relay_intro)

        lbl_prep_hint = QLabel("※ 설명 음성이 끝난 뒤 위 '설명 후 준비 대기 시간(n초)' 동안 받기자들이 미트를 착용하고, '모두 준비가 되었나요?' 안내 후 2초 뒤 본 훈련이 시작됩니다.")
        lbl_prep_hint.setStyleSheet("color: #2563eb; font-size: 11px; font-weight: 500;")
        l_rt.addWidget(lbl_prep_hint)

        # 2. 실제 진행 시 선수별 지시 기술명 (엔터 줄바꿈 입력)
        l_rt.addWidget(QLabel("🥊 실제 진행 시 선수별 지시 기술명 (줄바꿈(엔터)으로 선수별 개별 기술 구분):"))
        self.txt_relay_cue = QTextEdit()
        self.txt_relay_cue.setFixedHeight(75)
        self.txt_relay_cue.setPlaceholderText("각 줄마다 선수가 타격할 기술명을 입력하세요.\n예:\n한손 잡고 반대손 몸통 밀기\n전진 스텝 후 뒷발 몸통 차기\n조금씩 거리 좁히며 빠른발 상단 끊어차기")
        self.txt_relay_cue.setPlainText("한손 잡고 반대손 몸통 밀기\n전진 스텝 후 뒷발 몸통 차기\n조금씩 거리 좁히며 빠른발 상단 끊어차기")
        l_rt.addWidget(self.txt_relay_cue)

        lbl_relay_hint = QLabel("※ 줄바꿈(엔터)으로 입력 시 1:2 / 1:3 릴레이에서 [첫번째 선수], [두번째 선수], [세번째 선수]에게 차례로 개별 기술을 각각 지시합니다.")
        lbl_relay_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        l_rt.addWidget(lbl_relay_hint)

        l_relay.addWidget(g_relay_t)
        l_relay.addStretch()
        self.tabs.addTab(tab_relay, "🔄 1:1 / 1:2 / 1:3 릴레이 미트")

        # ── 탭 2: 스텝 & 받아차기/반응 훈련 ──
        tab_reaction = QWidget()
        l_reac = QVBoxLayout(tab_reaction)
        
        # 실전 훈련 시퀀스 안내 배너
        reac_info = QLabel("🎯 동작 순서: [기술 지시 (예: 1연타!)] ➔ [랜덤 초 긴장 대기] ➔ [신호음/구령 (삑! / 시작! / GO!)] 발차기 타격! ➔ [복귀 대기]")
        reac_info.setStyleSheet("background-color: #eff6ff; border: 1px solid #bfdbfe; border-radius: 6px; padding: 6px 10px; font-weight: bold; color: #1e40af; font-size: 12px;")
        l_reac.addWidget(reac_info)

        g_reac_t = QGroupBox("1. 훈련 시간, 복귀 템포 및 랜덤 긴장 대기")
        l_rct = QVBoxLayout(g_reac_t)
        
        # 1행: 총 훈련 시간 & 타격 후 다음 구령까지 복귀 대기
        h_rct1 = QHBoxLayout()
        h_rct1.addWidget(QLabel("총 훈련 시간:"))
        self.sp_reac_dur = QSpinBox()
        self.sp_reac_dur.setRange(30, 600)
        self.sp_reac_dur.setValue(120)
        self.sp_reac_dur.setSuffix(" 초")
        h_rct1.addWidget(self.sp_reac_dur)

        h_rct1.addWidget(QLabel("타격 후 복귀 대기:"))
        self.sp_reac_recovery = QDoubleSpinBox()
        self.sp_reac_recovery.setRange(0.2, 5.0)
        self.sp_reac_recovery.setSingleStep(0.1)
        self.sp_reac_recovery.setValue(0.8)
        self.sp_reac_recovery.setSuffix(" 초")
        self.sp_reac_recovery.setToolTip("비프음으로 발차기 타격 후 착지하여 다음 구령이 나올 때까지의 준비 시간입니다. (스피드 연타는 0.4~0.6초 추천)")
        h_rct1.addWidget(self.sp_reac_recovery)
        l_rct.addLayout(h_rct1)

        # 2행: 랜덤 긴장 대기 (지시어 방송 후 비프음이 울릴 때까지)
        h_rct2 = QHBoxLayout()
        h_rct2.addWidget(QLabel("랜덤 긴장 대기:"))
        self.sp_reac_min = QDoubleSpinBox()
        self.sp_reac_min.setRange(0.3, 15.0)
        self.sp_reac_min.setSingleStep(0.2)
        self.sp_reac_min.setValue(1.0)
        self.sp_reac_min.setSuffix("초 ~ ")
        self.sp_reac_max = QDoubleSpinBox()
        self.sp_reac_max.setRange(0.5, 20.0)
        self.sp_reac_max.setSingleStep(0.2)
        self.sp_reac_max.setValue(2.5)
        self.sp_reac_max.setSuffix("초")
        h_rct2.addWidget(self.sp_reac_min)
        h_rct2.addWidget(self.sp_reac_max)
        l_rct.addLayout(h_rct2)

        # 3행: 훈련 템포 빠른 프리셋 버튼 3종
        h_presets = QHBoxLayout()
        h_presets.addWidget(QLabel("⚡ 템포 프리셋:"))
        
        btn_preset_speed = QPushButton("🚀 초고속 스피드 연타 (많이 차기)")
        btn_preset_speed.setStyleSheet("background-color: #fee2e2; color: #991b1b; font-weight: bold; border-radius: 4px; padding: 4px 8px;")
        btn_preset_speed.clicked.connect(lambda: self._apply_reac_preset(rec=0.5, min_w=0.6, max_w=1.6))
        
        btn_preset_standard = QPushButton("🥋 실전 스파링 (표준)")
        btn_preset_standard.setStyleSheet("background-color: #e0f2fe; color: #0369a1; font-weight: bold; border-radius: 4px; padding: 4px 8px;")
        btn_preset_standard.clicked.connect(lambda: self._apply_reac_preset(rec=0.8, min_w=1.0, max_w=2.5))

        btn_preset_tactical = QPushButton("🛡️ 전술 카운터 (여유)")
        btn_preset_tactical.setStyleSheet("background-color: #f1f5f9; color: #334155; font-weight: bold; border-radius: 4px; padding: 4px 8px;")
        btn_preset_tactical.clicked.connect(lambda: self._apply_reac_preset(rec=1.5, min_w=2.5, max_w=5.0))

        h_presets.addWidget(btn_preset_speed)
        h_presets.addWidget(btn_preset_standard)
        h_presets.addWidget(btn_preset_tactical)
        l_rct.addLayout(h_presets)

        # 4행: 실시간 예상 타격 횟수 배너
        self.lbl_reac_est = QLabel()
        self.lbl_reac_est.setStyleSheet("color: #047857; font-weight: bold; font-size: 12px; background: #ecfdf5; padding: 6px 10px; border-radius: 4px; border: 1px solid #a7f3d0;")
        l_rct.addWidget(self.lbl_reac_est)

        self.sp_reac_dur.valueChanged.connect(self._update_reaction_estimate)
        self.sp_reac_recovery.valueChanged.connect(self._update_reaction_estimate)
        self.sp_reac_min.valueChanged.connect(self._update_reaction_estimate)
        self.sp_reac_max.valueChanged.connect(self._update_reaction_estimate)
        self._update_reaction_estimate()

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
        self.combo_reac_signal.addItem("🗣️ 음성 구령: \"Let's Go!\" (미국 본토 발음)", "voice_letsgo")
        self.combo_reac_signal.addItem("🗣️ 음성 구령: \"Ready, Go!\" (미국 본토 발음)", "voice_readygo")
        self.combo_reac_signal.addItem("🗣️ 음성 구령: '탕!'", "voice_bang")
        self.combo_reac_signal.addItem("🎲 랜덤 믹스 (휘슬 / 비프 / 시작! / Let's Go! 무작위)", "random_mix")
        l_sig.addWidget(self.combo_reac_signal, stretch=1)
        l_reac.addWidget(g_reac_sig)

        # 3. 명령어 템플릿 프리셋 선택 및 직접 편집
        g_reac_cues = QGroupBox("3. 기술 지시 구령 및 템플릿")
        l_rcc = QVBoxLayout(g_reac_cues)
        
        h_tmpl = QHBoxLayout()
        h_tmpl.addWidget(QLabel("📋 훈련 템플릿 선택:"))
        self.combo_cues_template = QComboBox()
        self.combo_cues_template.addItem("🥋 [실전 스파링 콤보] 백스텝 후 받아차기 교차 상단!, 전진 몸통차기 후 사이드 왼발 상단!, 앞발 컷트 후 뒷발 상단!, 사이드 스텝 후 뒤차기!", "백스텝 후 받아차기 교차 상단!, 전진 몸통차기 후 사이드 왼발 상단!, 앞발 컷트 후 뒷발 돌려차기 상단!, 사이드 스텝 후 뒤차기 카운터!")
        self.combo_cues_template.addItem("⚡ [스피드 연타] 1연타!, 2연타!, 3연타!, 앞발 나래차기!", "1연타!, 2연타!, 3연타!, 앞발 나래차기!")
        self.combo_cues_template.addItem("🛡️ [받아차기 / 카운터] 백스텝 받아차기!, 뒤차기 카운터!, 앞발 컷트!, 맞받아치기!", "백스텝 받아차기!, 뒤차기 카운터!, 앞발 컷트!, 맞받아치기!")
        self.combo_cues_template.addItem("🏃‍♂️ [기본기 순발력] 앞차기!, 돌려차기!, 내려찍기!, 옆차기!", "앞차기!, 돌려차기!, 내려찍기!, 옆차기!")
        self.combo_cues_template.currentIndexChanged.connect(self._on_cues_template_changed)
        h_tmpl.addWidget(self.combo_cues_template, stretch=1)
        l_rcc.addLayout(h_tmpl)

        h_input = QHBoxLayout()
        h_input.addWidget(QLabel("✏️ 적용 구령 목록:"))
        self.txt_reac_cues = QLineEdit("백스텝 후 받아차기 교차 상단!, 전진 몸통차기 후 사이드 왼발 상단!, 앞발 컷트 후 뒷발 돌려차기 상단!, 사이드 스텝 후 뒤차기 카운터!")
        self.txt_reac_cues.setPlaceholderText("쉼표로 구분하여 자유롭게 기술명을 입력하세요")
        h_input.addWidget(self.txt_reac_cues, stretch=1)
        l_rcc.addLayout(h_input)

        lbl_hint = QLabel("※ 스텝 중 위 기술명이 먼저 제시되고, 무작위 대기 시간 후 신호음(삑!)에 즉시 반응 타격합니다. ('출발' 단어 없음)")
        lbl_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        l_rcc.addWidget(lbl_hint)
        l_reac.addWidget(g_reac_cues)
        l_reac.addStretch()
        self.tabs.addTab(tab_reaction, "⚡ 스텝 & 실전 반응")

        # ── 탭 3: 스텝 + 콤비 연타 인터벌 ──
        tab_combo = QWidget()
        l_combo = QVBoxLayout(tab_combo)
        
        # 1. 스텝 및 연타 시간 설정
        g_combo_set = QGroupBox("1. 스텝 및 연타 시간 설정")
        l_cbs = QVBoxLayout(g_combo_set)
        h_cbs1 = QHBoxLayout()
        h_cbs1.addWidget(QLabel("스텝 유지 시간:"))
        self.sp_combo_step = QSpinBox()
        self.sp_combo_step.setRange(3, 60)
        self.sp_combo_step.setValue(8)
        self.sp_combo_step.setSuffix(" 초")
        h_cbs1.addWidget(self.sp_combo_step)

        h_cbs1.addWidget(QLabel("전력 연타 시간:"))
        self.sp_combo_strike = QSpinBox()
        self.sp_combo_strike.setRange(2, 30)
        self.sp_combo_strike.setValue(4)
        self.sp_combo_strike.setSuffix(" 초")
        h_cbs1.addWidget(self.sp_combo_strike)

        h_cbs1.addWidget(QLabel("총 세트 수:"))
        self.sp_combo_sets = QSpinBox()
        self.sp_combo_sets.setRange(1, 30)
        self.sp_combo_sets.setValue(6)
        self.sp_combo_sets.setSuffix(" 세트")
        h_cbs1.addWidget(self.sp_combo_sets)
        l_cbs.addLayout(h_cbs1)
        l_combo.addWidget(g_combo_set)

        # 2. 신호음 설정 (타격 시작음 및 연타 종료 구령/신호 선택)
        g_combo_signals = QGroupBox("2. 타격 시작 신호 및 연타 종료 신호 (선택)")
        l_csig = QVBoxLayout(g_combo_signals)
        
        h_cs1 = QHBoxLayout()
        h_cs1.addWidget(QLabel("타격 시작 신호음:"))
        self.combo_start_signal = QComboBox()
        self.combo_start_signal.addItem("📢 경기용 심판 휘슬 (호각 삐익~!)", "whistle")
        self.combo_start_signal.addItem("🔔 전자 비프음 (880Hz 삑~익!)", "beep")
        self.combo_start_signal.addItem("🥁 웅장한 대북 타격음 (쿵!)", "drum")
        h_cs1.addWidget(self.combo_start_signal, stretch=1)
        l_csig.addLayout(h_cs1)

        h_cs2 = QHBoxLayout()
        h_cs2.addWidget(QLabel("연타 종료 신호:"))
        self.combo_stop_signal = QComboBox()
        self.combo_stop_signal.addItem("🥋 음성: '갈려!' (태권도 경기 공식 구령 - 강력 추천)", "voice_kalyeo")
        self.combo_stop_signal.addItem("🛑 음성: '중지!' (전통 태권도/격투기 구령)", "voice_stop")
        self.combo_stop_signal.addItem("✋ 음성: '그만!' (명확한 정지 구령)", "voice_end")
        self.combo_stop_signal.addItem("🔔 전자 비프음 (종료 알림 비프)", "beep")
        self.combo_stop_signal.addItem("📢 심판 호각 (짧은 종료 휘슬)", "whistle")
        h_cs2.addWidget(self.combo_stop_signal, stretch=1)
        l_csig.addLayout(h_cs2)
        l_combo.addWidget(g_combo_signals)

        # 3. 스텝 지시 구령 목록 (세트마다 순서대로 지시)
        g_combo_steps = QGroupBox("3. 스텝 지시 구령 (세트마다 순환 지시)")
        l_cst = QVBoxLayout(g_combo_steps)
        
        h_tmpl_step = QHBoxLayout()
        h_tmpl_step.addWidget(QLabel("📋 스텝 템플릿:"))
        self.combo_step_tmpl = QComboBox()
        self.combo_step_tmpl.addItem("🥋 [실전 스파링 6스텝] 제자리 ➔ 앞뒤 ➔ 업다운 ➔ 앞발 ➔ 뒷발 ➔ 앞발 발바꿔", 
            "제자리 스텝, 앞뒤 스텝, 업다운 스텝, 앞발 스텝, 뒷발 스텝, 앞발 스텝 발바꿔")
        self.combo_step_tmpl.addItem("⚡ [스피드 순발력] 제자리 ➔ 사이드 ➔ 지그재그 ➔ 앞발 발바꿔 ➔ 페이크",
            "제자리 스텝, 사이드 스텝, 지그재그 스텝, 앞발 스텝 발바꿔, 페이크 스텝")
        self.combo_step_tmpl.addItem("🛡️ [거리 조절 & 방어] 앞뒤 ➔ 제자리 ➔ 백스텝 후 전진 ➔ 사이드",
            "앞뒤 스텝, 제자리 스텝, 백스텝 후 전진, 사이드 스텝")
        self.combo_step_tmpl.currentIndexChanged.connect(self._on_step_tmpl_changed)
        h_tmpl_step.addWidget(self.combo_step_tmpl, stretch=1)
        l_cst.addLayout(h_tmpl_step)

        h_step_txt = QHBoxLayout()
        h_step_txt.addWidget(QLabel("✏️ 적용 스텝 목록:"))
        self.txt_combo_steps = QLineEdit("제자리 스텝, 앞뒤 스텝, 업다운 스텝, 앞발 스텝, 뒷발 스텝, 앞발 스텝 발바꿔")
        self.txt_combo_steps.setPlaceholderText("쉼표로 구분하여 자유롭게 스텝 종류를 입력하세요")
        h_step_txt.addWidget(self.txt_combo_steps, stretch=1)
        l_cst.addLayout(h_step_txt)
        l_combo.addWidget(g_combo_steps)

        # 4. 집중 훈련 발차기/공격 기술 설정 (사전 안내 방송 및 훈련 목표)
        g_combo_kicks = QGroupBox("4. 집중 훈련 발차기/공격 기술 (사전 안내 및 타격 목표)")
        l_ckk = QVBoxLayout(g_combo_kicks)
        
        h_tmpl_kick = QHBoxLayout()
        h_tmpl_kick.addWidget(QLabel("📋 공격 기술 템플릿:"))
        self.combo_kick_tmpl = QComboBox()
        self.combo_kick_tmpl.addItem("🥋 [실전 스파링 콤보] 전진 몸통 후 사이드 상단, 백스텝 후 받아차기/교차 상단, 전진 몸통 3연타",
            "전진 몸통공격 후 사이드 스텝 상단, 백스텝 후 뒷발 받아차기 공격과 교차 상단 공격, 전진 몸통 3연타")
        self.combo_kick_tmpl.addItem("⚡ [스피드 연타 공격] 빠른 원투 몸통연타 후 상단 돌려차기, 앞발 나래차기 후 뒷발 상단, 제자리 3연타",
            "빠른 원투 몸통연타 후 상단 돌려차기, 앞발 나래차기 후 뒷발 상단, 제자리 3연타")
        self.combo_kick_tmpl.addItem("🛡️ [카운터 & 반격 공격] 백스텝 후 받아차기, 앞발 컷트 후 뒤차기 카운터, 사이드 빠지며 상단 공격",
            "백스텝 후 받아차기, 앞발 컷트 후 뒤차기 카운터, 사이드 빠지며 상단 공격")
        self.combo_kick_tmpl.addItem("🏃‍♂️ [기본 공격 연타] 몸통 돌려차기 2연타, 앞발 컷트 후 뒷발 상단, 전진 3연타",
            "몸통 돌려차기 2연타, 앞발 컷트 후 뒷발 상단, 전진 3연타")
        self.combo_kick_tmpl.currentIndexChanged.connect(self._on_kick_tmpl_changed)
        h_tmpl_kick.addWidget(self.combo_kick_tmpl, stretch=1)
        l_ckk.addLayout(h_tmpl_kick)

        h_kick_txt = QHBoxLayout()
        h_kick_txt.addWidget(QLabel("✏️ 집중 훈련 기술:"))
        self.txt_combo_kicks = QLineEdit("전진 몸통공격 후 사이드 스텝 상단, 백스텝 후 뒷발 받아차기 공격과 교차 상단 공격, 전진 몸통 3연타")
        self.txt_combo_kicks.setPlaceholderText("쉼표로 구분하여 자유롭게 집중 공격 기술을 입력하세요")
        h_kick_txt.addWidget(self.txt_combo_kicks, stretch=1)
        l_ckk.addLayout(h_kick_txt)

        h_kick_mode = QHBoxLayout()
        h_kick_mode.addWidget(QLabel("📢 기술 안내 방식:"))
        self.combo_kick_mode = QComboBox()
        self.combo_kick_mode.addItem("📢 시작 전 사전 안내에서만 종합 설명 (본 훈련은 스텝 지시에만 집중 - 추천)", "intro_only")
        self.combo_kick_mode.addItem("🗣️ 시작 전 사전 안내 + 매 세트 스텝 지시 시 기술명 함께 호명", "each_set")
        h_kick_mode.addWidget(self.combo_kick_mode, stretch=1)
        l_ckk.addLayout(h_kick_mode)

        lbl_step_hint = QLabel("※ 앞부분 시작 설명에서 어떤 발차기 공격을 집중적으로 할 것인지 명확히 안내한 후, 본 훈련에서는 군더더기 없이 [스텝 지시] ➔ [삐익(신호음)] ➔ [전력 연타] ➔ [갈려/중지/종료음] 순서로 실전 스파링 훈련이 진행됩니다.")
        lbl_step_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        l_ckk.addWidget(lbl_step_hint)
        l_combo.addWidget(g_combo_kicks)
        l_combo.addStretch()
        self.tabs.addTab(tab_combo, "🔥 스텝 + 콤비네이션 연타")

        # ── 탭 4: 정규 스파링 라운드 ──
        tab_round = QWidget()
        l_rnd = QVBoxLayout(tab_round)
        g_rnd_set = QGroupBox("스파링 라운드 시간 설정")
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
        self.tabs.addTab(tab_round, "🥊 정규 스파링 라운드")

        content_layout.addWidget(self.tabs)

        # ── 공통 설정 (BGM, 화자, 오토덕킹, 카운트다운) ──
        common_group = QGroupBox("🎵 배경음악(BGM) 및 구령/신호음 옵션")
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

        # 시작 전 안내 및 카운트다운 설정
        h_intro_opts = QHBoxLayout()
        self.cb_intro = QCheckBox("시작 전 기술 설명 및 준비 안내 음성 포함")
        self.cb_intro.setChecked(True)
        self.cb_countdown = QCheckBox("카운트다운 포함")
        self.cb_countdown.setChecked(True)
        h_intro_opts.addWidget(self.cb_intro)
        h_intro_opts.addWidget(self.cb_countdown)

        h_intro_opts.addWidget(QLabel("카운트다운 구령:"))
        self.combo_cd_style = QComboBox()
        self.combo_cd_style.addItem("🇺🇸 영어 본토 발음 (Three, Two, One)", "en_321")
        self.combo_cd_style.addItem("🏆 영어 스포츠 구령 (Are you ready? Ready! Three, Two, One)", "en_ready")
        self.combo_cd_style.addItem("🇰🇷 한국어 친근한 구령 (준비되었나요? 준비! 셋, 둘, 하나)", "ko_ready")
        self.combo_cd_style.addItem("🥋 한국어 표준 구령 (셋, 둘, 하나)", "ko_321")
        self.combo_cd_style.addItem("🔔 전자 비프음 3회 (띡-띡-띡)", "beep")
        h_intro_opts.addWidget(self.combo_cd_style)
        l_common.addLayout(h_intro_opts)

        # 화자 및 오토덕킹
        h_opts = QHBoxLayout()
        self.cb_ducking = QCheckBox("🎵 BGM 오토 덕킹 (음성 구령 시 음악 감쇄, 비프/신호음은 음악 0dB 유지)")
        self.cb_ducking.setChecked(True)
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

        # 훈련 종료 후 휴식/대기 안내 멘트 설정 (사용자 요청: 정렬 대신 물 한잔 및 다음 지시 대기/휴식)
        h_outro = QVBoxLayout()
        h_outro_top = QHBoxLayout()
        h_outro_top.addWidget(QLabel("🏁 훈련 종료 멘트 (휴식/대기 안내):"))
        self.combo_outro_tmpl = QComboBox()
        self.combo_outro_tmpl.addItem("💧 [물 한잔 & 대기] 물 한잔 마시고 호흡 가다듬으며 다음 지시 대기",
            "훈련 종료! 모두 수고하셨습니다! 물 한잔 마시고 호흡을 가다듬으며 다음 지시를 위해 잠시 대기하세요.")
        self.combo_outro_tmpl.addItem("☕ [자유 휴식 & 호흡] 호흡 가다듬고 잠시 자유롭게 휴식",
            "훈련 종료! 수고하셨습니다! 호흡 가다듬고 잠시 자유롭게 휴식하세요.")
        self.combo_outro_tmpl.addItem("⏳ [다음 훈련 대기] 땀 닦고 물 마시며 다음 훈련을 위해 대기",
            "훈련 종료! 모두 수고하셨습니다! 땀 닦고 물 마시며 다음 훈련을 위해 제자리에서 대기하세요.")
        self.combo_outro_tmpl.currentIndexChanged.connect(self._on_outro_tmpl_changed)
        h_outro_top.addWidget(self.combo_outro_tmpl, stretch=1)
        h_outro.addLayout(h_outro_top)

        self.txt_outro_ment = QLineEdit("훈련 종료! 모두 수고하셨습니다! 물 한잔 마시고 호흡을 가다듬으며 다음 지시를 위해 잠시 대기하세요.")
        self.txt_outro_ment.setPlaceholderText("훈련 종료 후 송출될 휴식 및 대기 안내 멘트를 자유롭게 입력하세요")
        h_outro.addWidget(self.txt_outro_ment)
        l_common.addLayout(h_outro)

        content_layout.addWidget(common_group)

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
        self.combo_duck_level.addItem("부드러운 감쇄 (-4 dB) - 음악 비트 유지 [강력 추천]", -4.0)
        self.combo_duck_level.addItem("보통 감쇄 (-6 dB) - 균형 잡힌 사운드", -6.0)
        self.combo_duck_level.addItem("강한 감쇄 (-10 dB) - 구령 집중", -10.0)
        self.combo_duck_level.addItem("오토덕킹 끄기 (0 dB 감쇄 없음 - 음악 원본 유지)", 0.0)
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

        content_layout.addWidget(vol_group)

        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll, stretch=1)

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

        # 서킷 훈련 텍스트 초기화
        self._update_circuit_moves_text()

    def _set_circuit_time_preset(self, work: int, rest: int, sets: int):
        self.sp_circuit_work.setValue(work)
        self.sp_circuit_rest.setValue(rest)
        self.sp_circuit_sets.setValue(sets)

    def _on_circuit_theme_changed(self, idx):
        self._update_circuit_moves_text()

    def _on_circuit_lang_changed(self, idx):
        self._update_circuit_moves_text()

    def _update_circuit_moves_text(self):
        theme_key = self.combo_circuit_theme.currentData() or "power_agility"
        lang_mode = self.combo_circuit_lang.currentData() or "mix_kids"
        theme_data = CIRCUIT_INTERVAL_THEMES.get(theme_key, CIRCUIT_INTERVAL_THEMES.get("power_agility", {}))
        exercises = theme_data.get("exercises", [])

        lang_field = "mix" if lang_mode == "mix_kids" else ("dual" if lang_mode == "dual_step" else ("en" if lang_mode == "en_advanced" else "kr"))

        lines = []
        for i, ex in enumerate(exercises, 1):
            text = ex.get(lang_field, ex.get("kr", ""))
            tip = ex.get("tip", "")
            lines.append(f"{i}번 콤보: {text}\n   ➔ [지도 팁]: {tip}\n")

        self.txt_circuit_moves.setPlainText("\n".join(lines).strip())

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

    def _on_relay_template_changed(self, idx):
        tmpl_key = self.combo_relay_template.currentData()
        templates = {
            "tmpl_bangjok": (
                "1번 방족술 - 한손 잡고 반대손 몸통 밀기. 2번 방족술 모션으로 전진 스텝 후 뒷발 몸통 차기! 2번 받기자 암미트 착용, 3번 조금씩 거리 좁히며 빠른발 상단 끊어차기!, 3번 받기자 손미트 착용, 빠르게 준비해 주세요. 플레이어는 패턴을 숙지해 주세요.",
                "한손 잡고 반대손 몸통 밀기\n전진 스텝 후 뒷발 몸통 차기\n조금씩 거리 좁히며 빠른발 상단 끊어차기"
            ),
            "tmpl_combo1": (
                "지금부터 실전 스파링 발차기 릴레이 훈련을 시작합니다. 지시하는 기술을 듣고 신호음에 맞춰 빠르고 정확하게 타격하세요. 모두 준비해 주세요!",
                "백스텝 후 받아차기 교차 상단\n전진 몸통차기 후 사이드 왼발 상단"
            ),
            "tmpl_counter": (
                "지금부터 카운터 반격 스파링 훈련을 시작합니다. 상대의 움직임을 읽고 정확한 타이밍에 카운터를 꽂으세요. 모두 준비해 주세요!",
                "앞발 컷트 후 뒷발 상단\n사이드 빠지며 뒤차기 카운터"
            ),
            "tmpl_single": (
                "지금부터 단일 기술 집중 스파링 훈련을 시작합니다. 신호음에 맞춰 폭발적인 스피드로 타격하세요. 모두 준비해 주세요!",
                "백스텝 후 받아차기 교차 상단"
            ),
            "tmpl_speed": (
                "지금부터 스피드 연타 스파링 훈련을 시작합니다. 쉬지 않고 전력으로 미트를 타격하세요. 모두 준비해 주세요!",
                "1연타\n2연타\n3연타\n나래차기 연타"
            )
        }
        if tmpl_key in templates:
            intro_t, cues_t = templates[tmpl_key]
            self.txt_relay_intro.setPlainText(intro_t)
            self.txt_relay_cue.setPlainText(cues_t)

    def _on_step_tmpl_changed(self, idx):
        tmpl_data = self.combo_step_tmpl.currentData()
        if tmpl_data:
            self.txt_combo_steps.setText(tmpl_data)

    def _on_kick_tmpl_changed(self, idx):
        tmpl_data = self.combo_kick_tmpl.currentData()
        if tmpl_data:
            self.txt_combo_kicks.setText(tmpl_data)

    def _on_outro_tmpl_changed(self, idx):
        tmpl_data = self.combo_outro_tmpl.currentData()
        if tmpl_data:
            self.txt_outro_ment.setText(tmpl_data)

    def set_vol_preset(self, bgm: int, sig: int, voice: int, duck_idx: int):
        self.slider_bgm_vol.setValue(bgm)
        self.slider_sig_vol.setValue(sig)
        self.slider_voice_vol.setValue(voice)
        self.combo_duck_level.setCurrentIndex(duck_idx)

    def _apply_reac_preset(self, rec: float, min_w: float, max_w: float):
        self.sp_reac_recovery.setValue(rec)
        self.sp_reac_min.setValue(min_w)
        self.sp_reac_max.setValue(max_w)
        self._update_reaction_estimate()

    def _update_reaction_estimate(self):
        try:
            total_sec = float(self.sp_reac_dur.value())
            rec_sec = float(self.sp_reac_recovery.value())
            min_sec = float(self.sp_reac_min.value())
            max_sec = float(self.sp_reac_max.value())
            if min_sec > max_sec:
                min_sec = max_sec

            # 시작 멘트(약 3.8초) 및 마무리 벨(약 3초) 제외한 실훈련 시간
            usable_sec = max(10.0, total_sec - 6.8)
            cue_sec = 0.9      # 짧은 구령 발성 시간
            trigger_sec = 0.3  # 타격 신호음(비프/휘슬) 시간

            avg_wait = (min_sec + max_sec) / 2.0
            cycle_avg = cue_sec + avg_wait + trigger_sec + rec_sec
            cycle_fast = cue_sec + min_sec + trigger_sec + rec_sec
            cycle_slow = cue_sec + max_sec + trigger_sec + rec_sec

            est_avg = max(1, int(usable_sec / cycle_avg))
            est_min = max(1, int(usable_sec / cycle_slow))
            est_max = max(1, int(usable_sec / cycle_fast))

            if hasattr(self, 'lbl_reac_est') and self.lbl_reac_est:
                self.lbl_reac_est.setText(
                    f"⚡ 예상 타격 횟수: 약 {est_avg}회 ({est_min}~{est_max}회)  |  "
                    f"1회당 평균 약 {cycle_avg:.1f}초  |  비프음 후 다음 구령까지 {rec_sec:.1f}초 대기"
                )
        except Exception:
            pass

    def start_generation(self):
        current_tab_idx = self.tabs.currentIndex()
        mode_map = {0: "circuit", 1: "relay", 2: "reaction", 3: "combo", 4: "rounds"}
        mode = mode_map.get(current_tab_idx, "circuit")

        duck_db_val = self.combo_duck_level.currentData()
        if duck_db_val is None:
            duck_db_val = -8.0

        params = {
            "intro_enabled": self.cb_intro.isChecked(),
            "countdown_enabled": self.cb_countdown.isChecked(),
            "countdown_style": self.combo_cd_style.currentData() or "en_321",
            "auto_ducking": self.cb_ducking.isChecked(),
            "voice_speaker": self.voice_combo.currentText(),
            "use_voice": True,
            "bgm_vol_pct": self.slider_bgm_vol.value(),
            "sig_vol_pct": self.slider_sig_vol.value(),
            "voice_vol_pct": self.slider_voice_vol.value(),
            "duck_db": duck_db_val,
            "outro_text": self.txt_outro_ment.text().strip()
        }

        if mode == "circuit":
            params["work_sec"] = float(self.sp_circuit_work.value())
            params["rest_sec"] = float(self.sp_circuit_rest.value())
            params["sets_count"] = self.sp_circuit_sets.value()
            params["theme_key"] = self.combo_circuit_theme.currentData() or "power_agility"
            params["language_mode"] = self.combo_circuit_lang.currentData() or "mix_kids"
            params["circuit_mode_type"] = "single" if hasattr(self, 'rb_circuit_single') and self.rb_circuit_single.isChecked() else "cycle"
            params["custom_routine_text"] = self.txt_circuit_moves.toPlainText().strip()

        elif mode == "relay":
            fighters = 2 if self.rb_relay_11.isChecked() else (3 if self.rb_relay_12.isChecked() else 4)
            params["fighters_count"] = fighters
            params["strike_sec"] = float(self.sp_relay_strike.value())
            params["change_sec"] = float(self.sp_relay_change.value())
            params["prep_wait_sec"] = float(self.sp_relay_prep_wait.value())
            params["cycles"] = self.sp_relay_cycles.value()
            params["intro_text"] = self.txt_relay_intro.toPlainText().strip()
            params["cue_text"] = self.txt_relay_cue.toPlainText().strip() or "백스텝 후 받아차기 교차 상단"

        elif mode == "reaction":
            params["duration_sec"] = float(self.sp_reac_dur.value())
            params["min_interval"] = float(self.sp_reac_min.value())
            params["max_interval"] = float(self.sp_reac_max.value())
            params["recovery_sec"] = float(self.sp_reac_recovery.value())
            raw_cues = self.txt_reac_cues.text().split(",")
            params["cues"] = [c.strip() for c in raw_cues if c.strip()]
            params["signal_sound"] = self.combo_reac_signal.currentData()

        elif mode == "combo":
            params["step_sec"] = float(self.sp_combo_step.value())
            params["combo_sec"] = float(self.sp_combo_strike.value())
            params["sets_count"] = self.sp_combo_sets.value()
            raw_steps = self.txt_combo_steps.text().split(",")
            params["step_types"] = [s.strip() for s in raw_steps if s.strip()]
            params["start_signal"] = self.combo_start_signal.currentData() or "whistle"
            params["stop_signal"] = self.combo_stop_signal.currentData() or "voice_kalyeo"
            raw_kicks = self.txt_combo_kicks.text().split(",")
            params["kick_types"] = [k.strip() for k in raw_kicks if k.strip()]
            params["kick_announce_mode"] = self.combo_kick_mode.currentData() or "intro_only"

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
                "🎉 맞춤 스파링 & 발차기 훈련 음원이 성공적으로 생성되었습니다!\n\n"
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
                        f"스파링훈련_{result_data['mode']}_{dur_m}분{dur_s}초.wav",
                        "Audio Files (*.wav *.mp3)",
                        options=QFileDialog.Option.DontUseNativeDialog
                    )
                    if save_path:
                        import shutil
                        if not os.path.splitext(save_path)[1]:
                            save_path += ".wav"
                        shutil.copy(result_data["master_audio_path"], save_path)
                        QMessageBox.information(self, "저장 완료", f"파일이 성공적으로 저장되었습니다:\n{save_path}")
                self.accept()
        else:
            self.status_lbl.setText(f"❌ {msg}")
            QMessageBox.critical(self, "생성 실패", msg)
