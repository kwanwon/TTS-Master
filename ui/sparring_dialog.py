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
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QRadioButton,
    QButtonGroup, QSpinBox, QDoubleSpinBox, QCheckBox, QFileDialog, QMessageBox, QComboBox,
    QProgressBar, QGroupBox, QScrollArea, QWidget, QLineEdit, QTextEdit, QTabWidget, QApplication, QSlider,
    QInputDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from core.sparring_training_engine import SparringTrainingEngine, CIRCUIT_INTERVAL_THEMES, clean_speech_text
from core.shuttle_run_engine import ShuttleRunEngine
from core.ai_generator import AIGenerator, extract_text_from_file, fetch_text_from_url, load_common_settings
from ui.ai_settings_dialog import GlobalAISettingsDialog
from utils.effects_generator import ensure_default_effects
from utils.hangul_composer import bind_hangul_composer, compose_hangul_jamo
import utils.edge_tts_patch  # Microsoft Edge-TTS 2026 엔드포인트 패치
from pydub import AudioSegment
from pydub.effects import normalize


class CompatibleTextEdit(QTextEdit):
    """
    넓고 시원한 멀티라인 입력을 지원하면서도 QLineEdit의 .text() / .setText() 인터페이스와
    100% 호환되며, macOS 한글 자모 분리('ㅅㅡㅍㅏㄹㅣㅇ') 실시간 자동 조합이 내장된 스마트 위젯.
    """
    returnPressed = pyqtSignal()

    def __init__(self, initial_text: str = "", parent=None):
        super().__init__(parent)
        bind_hangul_composer(self)
        if initial_text:
            self.setPlainText(initial_text)

    def insertFromMimeData(self, source):
        if source.hasText():
            self.insertPlainText(compose_hangul_jamo(source.text()))
        else:
            super().insertFromMimeData(source)

    def text(self) -> str:
        return compose_hangul_jamo(self.toPlainText())

    def setText(self, val: str):
        self.setPlainText(val or "")


class AICircuitWorker(QThread):
    """비동기 AI 전 탭(서킷/릴레이/반응/콤비/라운드) 즉석 템플릿 생성 및 한글 수정분 현장 영어·설명 재맞춤 워커"""
    finished_ok = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(
        self,
        prompt: str,
        lang_mode: str,
        mode_type: str = "cycle",
        doc_text: str = "",
        refine_mode: bool = False,
        edited_moves_text: str = "",
        current_theme_title: str = "",
        current_intro_text: str = "",
        tab_mode: str = "circuit",
        current_fields: Optional[Dict[str, Any]] = None,
        parent=None
    ):
        super().__init__(parent)
        self.prompt = prompt
        self.lang_mode = lang_mode
        self.mode_type = mode_type
        self.doc_text = doc_text
        self.refine_mode = refine_mode
        self.edited_moves_text = edited_moves_text
        self.current_theme_title = current_theme_title
        self.current_intro_text = current_intro_text
        self.tab_mode = tab_mode
        self.current_fields = dict(current_fields) if current_fields else {}
        if edited_moves_text and "moves_text" not in self.current_fields:
            self.current_fields["moves_text"] = edited_moves_text
            self.current_fields["formatted_moves"] = edited_moves_text
        if current_intro_text and "intro_text" not in self.current_fields:
            self.current_fields["intro_text"] = current_intro_text
        if current_theme_title and "theme_title" not in self.current_fields:
            self.current_fields["theme_title"] = current_theme_title
        if "mode_type" not in self.current_fields:
            self.current_fields["mode_type"] = mode_type

    def run(self):
        try:
            gen = AIGenerator()
            res = gen.generate_or_refine_sparring_tab(
                tab_mode=self.tab_mode,
                user_prompt=self.prompt,
                lang_mode=self.lang_mode,
                document_text=self.doc_text,
                refine_mode=self.refine_mode,
                current_fields=self.current_fields,
            )
            res["tab_mode"] = self.tab_mode
            self.finished_ok.emit(res)
        except Exception as e:
            self.failed.emit(str(e))


class NoScrollComboBox(QComboBox):
    """
    마우스 휠 스크롤에 의한 원치 않는 값 변경 오작동을 방지하는 콤보박스.
    마우스 휠 이벤트 발생 시 이벤트를 무시(ignore)하여 부모 스크롤 영역으로 전달하고,
    클릭하여 드롭다운 팝업 목록이 열렸을 때만 항목 선택이 가능하도록 합니다.
    """
    def wheelEvent(self, event):
        event.ignore()


def vol_pct_to_db(pct: int) -> float:
    """
    청감 인지 곡선(Perceptual Curve)을 적용하여 볼륨 슬라이더 조작 시 귀로 확연히 체감되도록 변환
    - 0% -> -60dB (무음)
    - 50% -> -8.4dB (확연히 절반 수준으로 감쇄)
    - 70% -> -4.3dB (차분하고 안정적인 배경음)
    - 100% -> 0.0dB (기준 볼륨)
    - 120% -> +2.85dB (귀로 뚜렷하게 느껴지는 증폭)
    - 130% -> +4.10dB (음악을 뚫고 나오는 우렁찬 발성)
    - 150% -> +6.34dB (강력한 강조)
    - 200% -> +10.84dB (극대화)
    """
    if pct <= 0:
        return -60.0
    if pct == 100:
        return 0.0
    if pct < 100:
        return round(28.0 * math.log10(pct / 100.0), 2)
    else:
        return round(36.0 * math.log10(pct / 100.0), 2)


def trim_audio_silence(seg: AudioSegment, threshold: float = -52.0) -> AudioSegment:
    """
    TTS 음성의 앞쪽 무음은 깔끔히 자르되 초성(예: '모두'의 'ㅁ')이 잘리지 않도록 180ms 안전 버퍼를 확보하고,
    뒤쪽은 말끝 여운(예: '~세요', '~다' 감쇄음)이 툭 끊기지 않도록 800ms 안전 여백을 넉넉히 보장합니다.
    """
    try:
        from pydub.silence import detect_leading_silence
        lead = detect_leading_silence(seg, silence_threshold=threshold)
        trail = detect_leading_silence(seg.reverse(), silence_threshold=threshold)
        safe_lead = max(0, lead - 180)
        safe_trail = max(0, trail - 800)
        end_idx = max(safe_lead + 80, len(seg) - safe_trail)
        trimmed = seg[safe_lead:end_idx]
        return trimmed if len(trimmed) >= 80 else seg
    except Exception:
        return seg


def make_suggested_filename(mode: str, params: dict, duration_sec: float) -> str:
    """
    훈련 모드, 인원, 세트수, 기술명에 맞춰 직관적인 한글 파일명 생성
    예: 1대1_앞차기_10세트.wav, 2대1_앞차기_돌려차기_3세트.wav
    """
    import re
    dur_m = int(duration_sec // 60)
    dur_s = int(duration_sec % 60)

    if mode == "relay":
        f_count = params.get("fighters_count", 2)
        match_type = "1대1" if f_count == 2 else ("2대1" if f_count == 3 else f"{f_count-1}대1")

        cue_raw = params.get("cue_text", "미트훈련")
        cues_list = [c.strip() for line in str(cue_raw).splitlines() for c in line.split(",") if c.strip()]
        if cues_list:
            cleaned_cues = [re.sub(r'[^\w가-힣]', '', c) for c in cues_list[:2]]
            cue_str = "_".join([c for c in cleaned_cues if c])
        else:
            cue_str = "미트훈련"
        if not cue_str:
            cue_str = "미트훈련"

        cycles = params.get("cycles", 3)
        return f"{match_type}_{cue_str}_{cycles}세트.wav"

    elif mode == "reaction":
        total_sec = params.get("duration_sec", 120.0)
        t_m = int(total_sec // 60)
        t_s = int(total_sec % 60)
        time_str = f"{t_m}분" if t_s == 0 else f"{t_m}분{t_s}초"
        return f"반응훈련_스텝카운터_{time_str}.wav"

    elif mode == "combo":
        raw_kicks = params.get("kick_types", [])
        kick_list = [re.sub(r'[^\w가-힣]', '', k.strip()) for k in raw_kicks if k and k.strip()] if isinstance(raw_kicks, list) else [re.sub(r'[^\w가-힣]', '', k.strip()) for k in str(raw_kicks).split(",") if k.strip()]
        kick_str = "_".join(kick_list[:2]) if kick_list else "스텝연타"
        rounds = params.get("rounds", 3)
        return f"콤비네이션_{kick_str}_{rounds}라운드.wav"

    elif mode == "rounds":
        total_rounds = params.get("total_rounds", 3)
        round_sec = params.get("round_sec", 90.0)
        r_m = int(round_sec // 60)
        r_s = int(round_sec % 60)
        time_label = f"{r_m}분" if r_s == 0 else f"{r_m}분{r_s}초"

        round_type = params.get("round_type", "real")
        if round_type == "shadow":
            type_label = "섀도우스파링"
        elif round_type == "promise":
            promise_det = params.get("promise_detail", "").strip()
            if promise_det:
                clean_prom = re.sub(r'[^\w가-힣]', '', promise_det)
                type_label = f"약속스파링_{clean_prom}"
            else:
                type_label = "약속스파링"
        elif round_type == "attack_defense":
            type_label = "공수스파링_A공격B방어"
        else:
            type_label = "실전스파링"

        return f"{type_label}_{total_rounds}라운드_{time_label}.wav"

    elif mode == "circuit":
        custom_title = params.get("theme_title", "").strip()
        if custom_title:
            cleaned_title = re.sub(r'[^\w가-힣]', '', custom_title)[:12]
            theme_str = cleaned_title if cleaned_title else "맞춤서킷"
        else:
            theme_key = params.get("theme_key", params.get("theme", "power_agility"))
            theme_names = {
                "power_agility": "대련실전낙법",
                "agility_power_combo": "순발력민첩성",
                "footwork_reaction_combo": "풋워크카운터",
                "strength_endurance_combo": "근지구력파워",
                "core_balance_kicks": "코어밸런스"
            }
            theme_str = theme_names.get(theme_key, "서킷콤보")
        sets_count = params.get("sets_count", params.get("cycles", 8))
        return f"서킷인터벌_{theme_str}_{sets_count}세트.wav"

    else:
        return f"스파링훈련_{mode}_{dur_m}분{dur_s}초.wav"


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
            sparring_cache_dir = os.path.join("projects", "temp_tts", "sparring_cache")
            os.makedirs(sparring_cache_dir, exist_ok=True)

            countdown_events = [ev for ev in events if ev["type"] == "countdown"]
            if countdown_events:
                cd_style = self.params.get("countdown_style", "en_321")
                cd_file = None

                # Helper for word-by-word stepped countdown with 1.5s (1500ms) delay
                async def _synth_stepped_cd(words: List[str], voice: str, rate: str = "+0%") -> AudioSegment:
                    silence_gap = AudioSegment.silent(duration=1500)
                    segs = []
                    for w in words:
                        seg = None
                        for attempt in range(3):
                            try:
                                comm = edge_tts.Communicate(w, voice, rate=rate)
                                buf = io.BytesIO()
                                async for chunk in comm.stream():
                                    if chunk['type'] == 'audio':
                                        buf.write(chunk['data'])
                                buf.seek(0)
                                s = trim_audio_silence(AudioSegment.from_file(buf, format="mp3"))
                                seg = s
                                break
                            except Exception:
                                await asyncio.sleep(0.15)
                        if seg is None and os.name == 'posix':
                            try:
                                import subprocess
                                tmp_aiff = os.path.join("projects", "temp_tts", f"sparring_cd_word_{uuid.uuid4().hex[:4]}.aiff")
                                say_voice = "Yuna" if any(ord(c) >= 0xAC00 and ord(c) <= 0xD7A3 for c in w) else "Samantha"
                                res = subprocess.run(["say", "-v", say_voice, "-o", tmp_aiff, w], check=False, timeout=5)
                                if res.returncode == 0 and os.path.exists(tmp_aiff):
                                    seg = trim_audio_silence(AudioSegment.from_file(tmp_aiff))
                                    if os.path.exists(tmp_aiff):
                                        os.remove(tmp_aiff)
                            except Exception:
                                pass
                        if seg is None:
                            seg = AudioSegment.silent(duration=400)
                        segs.append(seg)
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
                        if os.path.exists(cd_path) and os.path.getsize(cd_path) > 500:
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
                        if os.path.exists(cd_path) and os.path.getsize(cd_path) > 500:
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
                        if os.path.exists(cd_path) and os.path.getsize(cd_path) > 500:
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
                        if os.path.exists(cd_path) and os.path.getsize(cd_path) > 500:
                            cd_file = cd_path
                    except Exception as e_cd:
                        print(f"[SparringWorker] countdown TTS fail: {e_cd}")

                # 최종 폴백: 실패 시 비프음 카운트다운 에셋으로 무음 방지
                if not cd_file or not os.path.exists(cd_file):
                    cd_beeps = os.path.join("effects", "countdown_beeps.wav")
                    if os.path.exists(cd_beeps):
                        cd_file = cd_beeps
                    else:
                        cd_file = os.path.join("effects", "countdown.wav")

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

                # 불필요한 따옴표(' " `) 제거 (TTS 호흡 지연 및 어색한 끊김 방지)
                clean_text = clean_text.replace("'", "").replace('"', '').replace('`', '').strip()

                # 화살표 기호 정제 (TTS가 '화살표', '빼기' 등으로 발음하지 않고 자연스럽게 호흡하도록 쉼표로 변환)
                clean_text = clean_text.replace("->", ", ").replace("➔", ", ").replace("▶", ", ").replace("=>", ", ")

                # 서술어 중복 방어 정규화 (예: '됩니다.입니다' -> '됩니다.', '됩니다 입니다' -> '됩니다.')
                import re
                clean_text = re.sub(r'됩니다[\s\.]*입니다', '됩니다.', clean_text)
                clean_text = re.sub(r'합니다[\s\.]*입니다', '합니다.', clean_text)
                clean_text = re.sub(r'입니다[\s\.]*입니다', '입니다.', clean_text)
                clean_text = re.sub(r'니다[\s\.]*입니다', '니다.', clean_text)
                clean_text = re.sub(r'됩니다[\s\.]*니다', '됩니다.', clean_text)

                # 불필요한 번역 괄호 주석 제거 (예: (Times), (Time), (Repeat), (Ready) 등)
                clean_text = re.sub(r'\(\s*[A-Za-z\s]+\s*\)', '', clean_text)

                # 한국어 문맥 속 콩글리시 횟수/반복 표현 도장 표준어 정규화
                clean_text = re.sub(r'(\d+)\s*(?:타임스|타임즈|타임)\b', r'\1회', clean_text)
                clean_text = re.sub(r'무한\s*(?:리핏|리피트)\b', '무한 반복', clean_text)
                clean_text = re.sub(r'\b(?:리핏|리피트)\b', '반복', clean_text)
                clean_text = re.sub(r'레스트\s*타임\b', '휴식 시간', clean_text)
                # 한국어 문맥에서 '3회'가 '셋'이나 '셋 회'로 어색하게 읽히는 현상 원천 방지 (한자어 수사 '삼 회' 표준화)
                ko_count_map = {
                    '1': '일', '2': '이', '3': '삼', '4': '사', '5': '오',
                    '6': '육', '7': '칠', '8': '팔', '9': '구', '10': '십'
                }
                clean_text = re.sub(r'(?<!\d)([1-9]|10)\s*회(?=(?:와|과|씩|로|를|는|만|도|에|의|후|\s|$|[.,!?;:\-\)]))', lambda m: f"{ko_count_map.get(m.group(1), m.group(1))} 회", clean_text)
                clean_text = re.sub(r'\s+', ' ', clean_text).strip()

                self.progress.emit(pct, f"훈련 구령 음성 합성 중 ({idx+1}/{len(voice_events)}): {clean_text[:12]}...")

                if clean_text in voice_cache:
                    ev["sound_file"] = voice_cache[clean_text]["file"]
                    ev["duration"] = voice_cache[clean_text]["duration"]
                else:
                    # ⭐ 심판 공식 구령 처리: '갈려', '갈려! 타임!', '중지', '그만'
                    # 말끝('려')이 끊기지 않고 경기 심판처럼 당당하고 자연스러운 억양으로 발음되도록 전용 음원 최우선 사용
                    is_referee_cue = False
                    if clean_text in ("갈려! 타임!", "갈려 타임!", "갈려! 타임", "갈려~ 타임!", "갈려~! 타임!", "갈~려-! 타임!"):
                        ref_audio = os.path.join("effects", "kalyeo_time_injoon.wav" if "InJoon" in voice_id else "kalyeo_time_sunhi.wav")
                        if not os.path.exists(ref_audio):
                            ref_audio = os.path.join("effects", "kalyeo_injoon.wav" if "InJoon" in voice_id else "kalyeo_sunhi.wav")
                        if os.path.exists(ref_audio):
                            v_dur = len(AudioSegment.from_file(ref_audio)) / 1000.0
                            voice_cache[clean_text] = {"file": ref_audio, "duration": v_dur}
                            ev["sound_file"] = ref_audio
                            ev["duration"] = v_dur
                            is_referee_cue = True
                    elif clean_text in ("갈려~!", "갈려~", "갈려!", "갈려", "갈~려!", "갈~려-!") or clean_text.endswith("갈려!") or clean_text.endswith("갈려~!"):
                        referee_audio = os.path.join("effects", "kalyeo_injoon.wav" if "InJoon" in voice_id else "kalyeo_sunhi.wav")
                        if not os.path.exists(referee_audio):
                            referee_audio = os.path.join("effects", "kalyeo.wav")
                        if os.path.exists(referee_audio):
                            v_dur = len(AudioSegment.from_file(referee_audio)) / 1000.0
                            voice_cache[clean_text] = {"file": referee_audio, "duration": v_dur}
                            ev["sound_file"] = referee_audio
                            ev["duration"] = v_dur
                            is_referee_cue = True
                    elif clean_text in ("중지!", "중지"):
                        ref_audio = os.path.join("effects", "stop_injoon.wav" if "InJoon" in voice_id else "stop_sunhi.wav")
                        if not os.path.exists(ref_audio):
                            ref_audio = os.path.join("effects", "stop.wav")
                        if os.path.exists(ref_audio):
                            v_dur = len(AudioSegment.from_file(ref_audio)) / 1000.0
                            voice_cache[clean_text] = {"file": ref_audio, "duration": v_dur}
                            ev["sound_file"] = ref_audio
                            ev["duration"] = v_dur
                            is_referee_cue = True
                    elif clean_text in ("그만!", "그만"):
                        ref_audio = os.path.join("effects", "geuman_injoon.wav" if "InJoon" in voice_id else "geuman_sunhi.wav")
                        if not os.path.exists(ref_audio):
                            ref_audio = os.path.join("effects", "geuman.wav")
                        if os.path.exists(ref_audio):
                            v_dur = len(AudioSegment.from_file(ref_audio)) / 1000.0
                            voice_cache[clean_text] = {"file": ref_audio, "duration": v_dur}
                            ev["sound_file"] = ref_audio
                            ev["duration"] = v_dur
                            is_referee_cue = True

                    if is_referee_cue:
                        continue

                    v_path = os.path.join("projects", "temp_tts", f"sparring_v_{uuid.uuid4().hex[:6]}.wav")
                    import re
                    from utils.hangul_composer import compose_hangul_jamo
                    clean_text = clean_speech_text(compose_hangul_jamo(clean_text))

                    has_korean = bool(re.search(r'[가-힣]', clean_text))
                    has_english = bool(re.search(r'[a-zA-Z]', clean_text))

                    # ── [지도자 듀얼 톤 튜닝: 대화형 설명 vs 기합 구령 분리] ──
                    # 1) 대화/설명형 멘트: 인트로, 휴식, 라운드 안내, 친근한 대화체(~해요, 친구들) (+0%)
                    # 2) 구령형 멘트: 시작!, 원투!, 바꿔!, 동작 지시 등 절도 있고 텐션감 있는 기합 톤 (+8% & 컴프레서 펀치)
                    is_guidance = (
                        len(clean_text) >= 18 or 
                        any(clean_text.endswith(end) for end in ("합니다.", "입니다.", "됩니다.", "하세요.", "바랍니다.", "휴식", "휴식입니다", "준비하세요.", "해요!", "봐요!", "마셔요.")) or
                        "안내" in clean_text or "훈련은" in clean_text or "호흡을" in clean_text or "가다듬" in clean_text or "테마는" in clean_text or "라운드입니다" in clean_text or "친구들" in clean_text or "신나는" in clean_text
                    )

                    rate_val = "+0%" if is_guidance else "+8%"

                    synth_text = clean_text
                    # 구령 단문은 느낌표 강세가 없을 경우 추가하여 끊어치는 기합 유도
                    if not is_guidance and not re.search(r'[!~]$', synth_text):
                        synth_text += "!"

                    # v9 캐시 키 (숫자 한자어 발음 표준화 및 영문 횟수 통일 반영)
                    cue_type_tag = "g" if is_guidance else "c"
                    safe_cue_name = f"sp_v9_{voice_id}_{en_voice}_{cue_type_tag}_{abs(hash(synth_text))}.wav"
                    cached_cue_path = os.path.join(sparring_cache_dir, safe_cue_name)

                    generated = False
                    if os.path.exists(cached_cue_path) and os.path.getsize(cached_cue_path) > 500:
                        import shutil
                        shutil.copy(cached_cue_path, v_path)
                        generated = True
                    else:
                        for attempt in range(3):
                            try:
                                import edge_tts
                                import io
                                from pydub.effects import compress_dynamic_range, normalize

                                async def _synth_single_segment(t: str, v: str) -> AudioSegment:
                                    comm = edge_tts.Communicate(t, v, rate=rate_val)
                                    buf = io.BytesIO()
                                    async for chunk in comm.stream():
                                        if chunk['type'] == 'audio':
                                            buf.write(chunk['data'])
                                    buf.seek(0)
                                    raw_seg = AudioSegment.from_file(buf, format="mp3")
                                    return trim_audio_silence(raw_seg)

                                async def _synth_hybrid(full_text: str, path: str):
                                    # 1. 초등부 순차 이중언어 구령 (한국어 설명 - 쉬운 원어민 영어 본토 발음 분리)
                                    #    예: "[1세트] 쪼그려 점프 3회 후 나래차기! - Three jumps and double kicks! Let's go!"
                                    if " - " in full_text:
                                        parts = full_text.split(" - ", 1)
                                        ko_part = parts[0].strip()
                                        en_part = parts[1].strip()

                                        seg_ko = await _synth_single_segment(ko_part, voice_id)
                                        seg_en = await _synth_single_segment(en_part, en_voice)

                                        # 한국어와 원어민 영어 사이에 자연스러운 호흡 텀(150ms)
                                        combined = seg_ko + AudioSegment.silent(duration=150) + seg_en

                                    # 2. 순수 영어 문장: 미국 본토 원어민 화자(Guy/Jenny) 100%
                                    elif has_english and not has_korean:
                                        combined = await _synth_single_segment(full_text, en_voice)

                                    # 3. 일반 한국어 및 유치부 한-영 대화형 코칭: 한국어 지도자 화자(인준/선희)가 자연스러운 한 호흡으로 합성
                                    else:
                                        combined = await _synth_single_segment(full_text, voice_id)

                                    # ── 도장 보컬 사운드 마스터링 (명료도 & 펀치감) ──
                                    if not is_guidance and len(combined) > 80:
                                        try:
                                            combined = compress_dynamic_range(combined, threshold=-16.0, ratio=2.5, attack=5.0, release=50.0)
                                            combined = combined + 1.8
                                        except Exception:
                                            pass
                                    elif is_guidance and len(combined) > 80:
                                        try:
                                            combined = normalize(combined)
                                        except Exception:
                                            pass

                                    combined.export(path, format="wav")

                                asyncio.run(_synth_hybrid(synth_text, v_path))
                                if os.path.exists(v_path) and os.path.getsize(v_path) > 500:
                                    generated = True
                                    import shutil
                                    shutil.copy(v_path, cached_cue_path)
                                    break
                            except Exception as e_voice:
                                print(f"[SparringWorker] TTS attempt {attempt+1} fail for '{clean_text}': {e_voice}")
                                import time
                                time.sleep(0.2)

                        # macOS 로컬 네이티브 음성 합성 폴백 (오프라인 및 네트워크 오류 완벽 대응)
                        if not generated and os.name == 'posix':
                            try:
                                import subprocess
                                tmp_aiff = v_path.replace(".wav", ".aiff")
                                say_voice = "Yuna" if has_korean else "Samantha"
                                res = subprocess.run(["say", "-v", say_voice, "-o", tmp_aiff, synth_text], check=False, timeout=8)
                                if res.returncode == 0 and os.path.exists(tmp_aiff):
                                    seg = trim_audio_silence(AudioSegment.from_file(tmp_aiff))
                                    seg.export(v_path, format="wav")
                                    if os.path.exists(tmp_aiff):
                                        os.remove(tmp_aiff)
                                    generated = True
                                    import shutil
                                    shutil.copy(v_path, cached_cue_path)
                            except Exception as e_say:
                                print(f"[SparringWorker] say fallback fail: {e_say}")

                    if generated and os.path.exists(v_path):
                        v_dur = len(AudioSegment.from_file(v_path)) / 1000.0
                        voice_cache[clean_text] = {"file": v_path, "duration": v_dur}
                        ev["sound_file"] = v_path
                        ev["duration"] = v_dur
                    else:
                        print(f"[SparringWorker] Warning: Voice gen fallback used for '{clean_text}'")
                        ev["sound_file"] = os.path.join("effects", "beep.wav")
                        ev["duration"] = 0.5

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
                    duck_segments.append((st_ms, st_ms + dur_ms + 400))

            if events:
                last_ev = events[-1]
                last_end_sec = last_ev["time"] + last_ev.get("duration", 1.0)
                total_duration_sec = round(last_end_sec + 5.5, 2)
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

            # 클리핑(치직거림) 방지 피크 리미터: 피크가 -0.5dBFS를 초과할 때만 안전하게 헤드룸 확보하여 볼륨 바 밸런스 100% 보존
            if master_canvas.max_dBFS > -0.5:
                headroom_cut = master_canvas.max_dBFS - (-0.5)
                master_canvas = master_canvas - headroom_cut

            suggested_filename = make_suggested_filename(self.mode, self.params, total_duration_sec)
            clean_base = os.path.splitext(suggested_filename)[0]
            output_master_path = os.path.join(
                "projects", "temp_tts",
                f"{clean_base}_{uuid.uuid4().hex[:6]}.wav"
            )
            master_canvas.export(output_master_path, format="wav")

            self.progress.emit(100, "완료!")
            result_data = {
                "mode": self.mode,
                "mode_name": SparringTrainingEngine.TRAINING_MODES.get(self.mode, {}).get("name", "스파링 훈련"),
                "timeline_clips": timeline_clips,
                "master_audio_path": output_master_path,
                "suggested_filename": suggested_filename,
                "total_duration_sec": total_duration_sec
            }
            self.finished.emit(True, "스파링 훈련 음원이 성공적으로 생성되었습니다.", result_data)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.finished.emit(False, f"음원 생성 중 오류 발생: {str(e)}", {})


class SparringDialog(QDialog):
    """스파링 훈련 음원 생성 마법사 UI 다이얼로그 (전 탭 AI 즉석 템플릿 & 한글 수정 후 다시 생성 지원)"""

    def __init__(
        self,
        parent=None,
        tts_engine=None,
        initial_tab: int = 0,
        initial_prompt: str = "",
        initial_doc_text: str = ""
    ):
        super().__init__(parent)
        self.tts_engine = tts_engine
        self.setWindowTitle("🥋 스파링 & 기능성 인터벌 마법사 (서킷·릴레이·반응·콤비·스파링 전 탭 AI 자동생성)")
        self.resize(960, 880)
        self.bgm_playlist: List[str] = []
        self.generated_result = None
        self._ai_loaded_doc_text = initial_doc_text or ""

        self.init_ui()

        if 0 <= initial_tab < self.tabs.count():
            self.tabs.setCurrentIndex(initial_tab)
        if initial_prompt.strip():
            self.txt_ai_circuit_prompt.setText(initial_prompt.strip())
        if initial_prompt.strip() or initial_doc_text.strip():
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(180, self._on_ai_generate_circuit)

    def _make_refine_btn(self, label_text: str = "🔄 수정한 한글로 영어·설명 다시 생성") -> QPushButton:
        btn = QPushButton(label_text)
        btn.setToolTip(
            "아래 대본/기술 칸에서 한국어 동작이나 횟수만 편하게 수정한 뒤 누르면,\n"
            "수정한 한글에 맞춰 쉽고 자연스러운 현장 영어 구령과 사전 설명을 AI가 다시 완성합니다!"
        )
        btn.setStyleSheet(
            "background-color: #059669; color: white; font-weight: bold; padding: 5px 12px; border-radius: 5px; font-size: 12px;"
        )
        btn.clicked.connect(self._on_ai_refine_circuit)
        self._refine_buttons.append(btn)
        return btn

    def init_ui(self):
        self._refine_buttons: List[QPushButton] = []
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(10, 8, 10, 8)

        # ══════════════════════════════════════════════════════════════════
        # [상단 고정] 전 탭 공통 AI 즉석 템플릿 생성 & 한글 수정 후 다시 생성 컨트롤 바
        # ══════════════════════════════════════════════════════════════════
        ai_top_group = QGroupBox("🤖 [1단계] 할 운동 요구사항 입력 ➔ 현재 선택된 탭 맞춤 [즉석 템플릿 생성] (모든 탭 공통 작동)")
        ai_top_group.setStyleSheet(
            "QGroupBox { background-color: #faf5ff; border: 2px solid #8b5cf6; border-radius: 8px; margin-top: 8px; padding-top: 6px; font-weight: bold; color: #5b21b6; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; }"
        )
        l_ai_top = QVBoxLayout(ai_top_group)
        l_ai_top.setSpacing(5)
        l_ai_top.setContentsMargins(8, 6, 8, 6)

        # Row 1: 구령 언어 선택 + 통합설정 / 구글드라이브 링크 / 파일 불러오기
        h_ai_row1 = QHBoxLayout()
        lbl_lang = QLabel("🌍 구령 언어:")
        lbl_lang.setStyleSheet("font-weight: bold; color: #1e293b;")
        h_ai_row1.addWidget(lbl_lang)

        self.combo_circuit_lang = NoScrollComboBox()
        self.combo_circuit_lang.addItem("🌱 [직관 액션 구령 (유소년·초보 추천)] 횟수·동작을 짧고 명쾌하게 지시 (Two pushups! Five fast kicks! Go!)", "mix_kids")
        self.combo_circuit_lang.addItem("⚡ [자세·흐름 코칭 (중·상급 추천)] 동작 간 호흡·자세 연결 대화형 코칭 (Down for two pushups, explode up fast!)", "dual_step")
        self.combo_circuit_lang.addItem("🇰🇷 [한국어 전용] 명확한 한국어 기술 명칭 + 절도 있는 사범님 기합 구령", "kr")
        self.combo_circuit_lang.addItem("🇺🇸 [원어민 코치 풀 잉글리시] Full English Coaching (시작 안내부터 전 과정 영어)", "en_advanced")
        self.combo_circuit_lang.currentIndexChanged.connect(self._on_circuit_lang_changed)
        h_ai_row1.addWidget(self.combo_circuit_lang, stretch=1)

        self.lbl_lang_mode_desc = QLabel(
            "💡 [직관 액션 구령]: 횟수와 동작을 짧고 명확하게 외쳐 수련생이 직관적으로 바로 반응하도록 지도합니다. (유치부·초등부 추천)"
        )
        self.lbl_lang_mode_desc.setStyleSheet("color: #6b21a8; font-size: 11px; font-weight: bold; padding: 2px 4px;")

        self.btn_open_ai_settings = QPushButton("⚙️ 통합 설정 (API키/공통자료)")
        self.btn_open_ai_settings.setToolTip("Gemini API 키와 공통으로 사용할 구글 드라이브 링크·수련계획표를 설정합니다.")
        self.btn_open_ai_settings.setStyleSheet(
            "background-color: #475569; color: white; font-weight: bold; padding: 5px 10px; border-radius: 5px; font-size: 12px;"
        )
        self.btn_open_ai_settings.clicked.connect(self._on_open_ai_settings_dialog)
        h_ai_row1.addWidget(self.btn_open_ai_settings)

        self.btn_ai_circuit_link = QPushButton("🔗 구글드라이브 링크")
        self.btn_ai_circuit_link.setToolTip("구글 드라이브·문서(Docs)·시트(Sheets) 공유 링크에서 수련계획표를 바로 불러옵니다.")
        self.btn_ai_circuit_link.setStyleSheet(
            "background-color: #0d9488; color: white; font-weight: bold; padding: 5px 10px; border-radius: 5px; font-size: 12px;"
        )
        self.btn_ai_circuit_link.clicked.connect(self._on_ai_load_gdrive_link)
        h_ai_row1.addWidget(self.btn_ai_circuit_link)

        self.btn_ai_circuit_file = QPushButton("📂 파일 불러오기")
        self.btn_ai_circuit_file.setToolTip("내 컴퓨터의 수련계획표 문서(.txt, .docx, .md, .csv)를 불러와 즉석 템플릿을 만듭니다.")
        self.btn_ai_circuit_file.setStyleSheet(
            "background-color: #0284c7; color: white; font-weight: bold; padding: 5px 10px; border-radius: 5px; font-size: 12px;"
        )
        self.btn_ai_circuit_file.clicked.connect(self._on_ai_load_circuit_file)
        h_ai_row1.addWidget(self.btn_ai_circuit_file)
        l_ai_top.addLayout(h_ai_row1)
        l_ai_top.addWidget(self.lbl_lang_mode_desc)

        # Row 2: 넓은 요구사항 입력칸 + [✨ 요구사항으로 즉석 템플릿 생성] + [🔄 수정한 한글로 다시 생성]
        h_ai_row2 = QHBoxLayout()
        self.txt_ai_circuit_prompt = CompatibleTextEdit()
        self.txt_ai_circuit_prompt.setFixedHeight(54)
        self.txt_ai_circuit_prompt.setPlaceholderText(
            "💡 [여기 입력 후 우측 버튼 클릭] 원하는 훈련 내용을 편하게 적으세요! (예: 팔굽혀펴기 2회, 빠른발차기 5회, 버피 2회 / 또는 1번 잡고 밀기, 2번 암미트 몸통차기)\n"
            "   현재 선택된 탭(서킷 / 릴레이 미트 / 스텝 반응 / 콤비 연타 / 스파링 라운드)에 딱 맞는 즉석 템플릿이 아래 편집창에 바로 생성됩니다."
        )
        self.txt_ai_circuit_prompt.setStyleSheet(
            "border: 2px solid #7c3aed; border-radius: 6px; padding: 4px 8px; background-color: #ffffff; color: #111827; font-size: 13px; font-weight: bold;"
        )
        h_ai_row2.addWidget(self.txt_ai_circuit_prompt, stretch=1)

        v_ai_btns = QVBoxLayout()
        v_ai_btns.setSpacing(4)
        self.btn_ai_circuit_gen = QPushButton("✨ 요구사항으로 즉석 템플릿 생성")
        self.btn_ai_circuit_gen.setToolTip("입력한 요구사항(또는 불러온 링크·파일)에 맞춰 현재 탭의 대본 템플릿을 즉석에서 자동 생성합니다.")
        self.btn_ai_circuit_gen.setStyleSheet(
            "background-color: #7c3aed; color: white; font-weight: bold; padding: 6px 14px; border-radius: 5px; font-size: 13px;"
        )
        self.btn_ai_circuit_gen.clicked.connect(self._on_ai_generate_circuit)
        v_ai_btns.addWidget(self.btn_ai_circuit_gen)

        self.btn_ai_refine_circuit = self._make_refine_btn("🔄 수정한 한글로 영어·설명 다시 생성")
        v_ai_btns.addWidget(self.btn_ai_refine_circuit)
        h_ai_row2.addLayout(v_ai_btns)

        l_ai_top.addLayout(h_ai_row2)
        main_layout.addWidget(ai_top_group)

        # 스크롤 영역 생성
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)

        # 5가지 훈련 모드 탭
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabBar::tab { font-weight: bold; padding: 8px 14px; font-size: 13px; }")

        # ══════════════════════════════════════════════════════════════════
        # ── 탭 0: 🔥 기능성 서킷 인터벌 (HIIT & Tabata) ──
        # ══════════════════════════════════════════════════════════════════
        tab_circuit = QWidget()
        l_circuit = QVBoxLayout(tab_circuit)
        l_circuit.setSpacing(6)

        # [탭0 - 1번 (맨 위!)] 제공된 서킷 템플릿 확인 및 대본 자유 수정 (스크롤 없이 한눈에 보임!)
        g_c_moves = QGroupBox("1. [2단계] 제공된 서킷 템플릿 확인 및 대본 자유 수정 (한글만 고치고 [🔄 다시 생성]을 누르세요)")
        l_cm = QVBoxLayout(g_c_moves)
        l_cm.setSpacing(6)

        # 테마 선택 + 테마 명칭 한 줄 배치
        h_theme_top = QHBoxLayout()
        h_theme_top.addWidget(QLabel("📋 기본 테마:"))
        self.combo_circuit_theme = NoScrollComboBox()
        self.combo_circuit_theme.addItem("🥋 [실전 대련과 낙법 협응] 점프·발차기·전방낙법 루프", "power_agility")
        self.combo_circuit_theme.addItem("⚡ [순발력과 민첩성 폭발] 버피·점프턴·나래차기 루프", "agility_power_combo")
        self.combo_circuit_theme.addItem("🏃‍♂️ [스파링 풋워크와 카운터] 스텝·컷트·뒤차기 루프", "footwork_reaction_combo")
        self.combo_circuit_theme.addItem("💪 [근지구력과 전신 파워] 푸시업·복근·연타킥 서킷", "strength_endurance_combo")
        self.combo_circuit_theme.addItem("🔥 [겨루기 실전 전술 콤보] 나래차기·뒤후리기·돌개차기 루프", "taekwondo_sparring_tactics")
        self.combo_circuit_theme.addItem("✏️ [직접 입력 / AI 맞춤] 사범님 커스텀 테마", "custom")
        self.combo_circuit_theme.currentIndexChanged.connect(self._on_circuit_theme_changed)
        h_theme_top.addWidget(self.combo_circuit_theme, stretch=1)

        h_theme_top.addWidget(QLabel("✏️ 테마 명칭:"))
        self.txt_circuit_theme_title = QLineEdit("실전 대련과 낙법 협응 콤보")
        self.txt_circuit_theme_title.setPlaceholderText("훈련 테마 명칭 자유 수정")
        h_theme_top.addWidget(self.txt_circuit_theme_title, stretch=1)

        self.btn_apply_theme_title = QPushButton("👉 테마 명칭 반영")
        self.btn_apply_theme_title.setToolTip("수정한 테마 명칭을 아래 사전 설명 방송과 대본에 즉시 연결하여 반영합니다.")
        self.btn_apply_theme_title.setStyleSheet(
            "background-color: #0f766e; color: white; font-weight: bold; padding: 4px 10px; border-radius: 5px; font-size: 12px;"
        )
        self.btn_apply_theme_title.clicked.connect(self._on_apply_circuit_theme_title)
        h_theme_top.addWidget(self.btn_apply_theme_title)
        l_cm.addLayout(h_theme_top)

        self.lbl_circuit_theme_desc = QLabel(
            "🥋 [실전 대련과 낙법 협응]: 점프 발차기 후 신속한 전방낙법으로 연결하여 위기 대처 능력과 신체 협응력을 기르는 실전 훈련 루프"
        )
        self.lbl_circuit_theme_desc.setStyleSheet("color: #4338ca; font-size: 11px; font-weight: bold; padding: 1px 4px;")
        l_cm.addWidget(self.lbl_circuit_theme_desc)

        # 사전 설명 방송 (넓은 멀티라인)
        h_intro_edit = QHBoxLayout()
        lbl_intro_title = QLabel("📢 사전 설명 방송\n(자유 수정):")
        lbl_intro_title.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        h_intro_edit.addWidget(lbl_intro_title)
        self.txt_circuit_intro = CompatibleTextEdit()
        self.txt_circuit_intro.setFixedHeight(52)
        self.txt_circuit_intro.setPlaceholderText("훈련 시작 전 사범님이 설명하는 안내 멘트 (즉석 템플릿 생성 시 자동 작성되며 자유롭게 수정 가능)")
        self.txt_circuit_intro.setStyleSheet("font-size: 13px; padding: 4px 6px;")
        h_intro_edit.addWidget(self.txt_circuit_intro, stretch=1)
        l_cm.addLayout(h_intro_edit)

        # 콤보 순환 옵션 + 다시 생성 버튼 바
        h_cm_mode = QHBoxLayout()
        lbl_step2 = QLabel("✏️ 세트별 콤보 대본 편집창 (넓은 화면):")
        lbl_step2.setStyleSheet("font-weight: bold; color: #0f766e; font-size: 13px;")
        h_cm_mode.addWidget(lbl_step2)

        self.rb_circuit_cycle = QRadioButton("🔄 세트마다 종목 순환")
        self.rb_circuit_single = QRadioButton("🎯 단일 종목 집중 반복")
        self.rb_circuit_cycle.setChecked(True)
        h_cm_mode.addWidget(self.rb_circuit_cycle)
        h_cm_mode.addWidget(self.rb_circuit_single)
        h_cm_mode.addStretch()

        h_cm_mode.addWidget(self._make_refine_btn("🔄 수정한 한글로 영어·설명 다시 생성하기"))

        self.btn_shuffle_circuit = QPushButton("🎲 기본 테마 무작위")
        self.btn_shuffle_circuit.setToolTip("선택된 기본 테마에서 무작위로 4개 콤보를 추출합니다.")
        self.btn_shuffle_circuit.setStyleSheet(
            "background-color: #4f46e5; color: white; font-weight: bold; padding: 5px 10px; border-radius: 5px; font-size: 12px;"
        )
        self.btn_shuffle_circuit.clicked.connect(self._shuffle_circuit_moves)
        h_cm_mode.addWidget(self.btn_shuffle_circuit)
        l_cm.addLayout(h_cm_mode)

        # 넓고 시원한 서킷 대본 편집창
        self.txt_circuit_moves = CompatibleTextEdit()
        self.txt_circuit_moves.setMinimumHeight(210)
        self.txt_circuit_moves.setMaximumHeight(320)
        self.txt_circuit_moves.setStyleSheet("font-size: 13px; padding: 8px; line-height: 1.4;")
        self.txt_circuit_moves.textChanged.connect(self._on_circuit_moves_text_changed)
        l_cm.addWidget(self.txt_circuit_moves)

        lbl_moves_hint = QLabel(
            "💡 '1번 콤보:' 줄만 실제 스피커로 힘차게 방송되며, '➔ [지도 팁]' 줄은 음성으로 읽지 않는 사범님 참고용입니다. 한국어만 고치고 [🔄 다시 생성]을 누르면 현장 영어가 자동 완성됩니다!"
        )
        lbl_moves_hint.setStyleSheet("color: #0369a1; background-color: #f0f9ff; border: 1px solid #bae6fd; border-radius: 4px; padding: 4px 8px; font-size: 11px; font-weight: bold;")
        l_cm.addWidget(lbl_moves_hint)
        l_circuit.addWidget(g_c_moves)

        # [탭0 - 2번] 인터벌 시간 및 세트 설정
        g_c_time = QGroupBox("2. 인터벌 시간·세트 및 휴식 구령 설정")
        l_ctime = QVBoxLayout(g_c_time)
        l_ctime.setSpacing(5)

        h_ct1 = QHBoxLayout()
        h_ct1.addWidget(QLabel("⏱️ 운동(전력) 시간:"))
        self.sp_circuit_work = QSpinBox()
        self.sp_circuit_work.setRange(5, 120)
        self.sp_circuit_work.setValue(20)
        self.sp_circuit_work.setSuffix(" 초")
        self.sp_circuit_work.setFixedWidth(85)
        h_ct1.addWidget(self.sp_circuit_work)

        h_ct1.addWidget(QLabel("🧘 휴식 시간:"))
        self.sp_circuit_rest = QSpinBox()
        self.sp_circuit_rest.setRange(5, 60)
        self.sp_circuit_rest.setValue(10)
        self.sp_circuit_rest.setSuffix(" 초")
        self.sp_circuit_rest.setFixedWidth(85)
        h_ct1.addWidget(self.sp_circuit_rest)

        h_ct1.addWidget(QLabel("🔁 총 세트 수:"))
        self.sp_circuit_sets = QSpinBox()
        self.sp_circuit_sets.setRange(1, 30)
        self.sp_circuit_sets.setValue(8)
        self.sp_circuit_sets.setSuffix(" 세트")
        self.sp_circuit_sets.setFixedWidth(85)
        h_ct1.addWidget(self.sp_circuit_sets)

        btn_tabata = QPushButton("타바타(20/10/8)")
        btn_tabata.clicked.connect(lambda: self._set_circuit_time_preset(20, 10, 8))
        btn_speed = QPushButton("스피드(15/10/6)")
        btn_speed.clicked.connect(lambda: self._set_circuit_time_preset(15, 10, 6))
        btn_power = QPushButton("체력강화(30/15/8)")
        btn_power.clicked.connect(lambda: self._set_circuit_time_preset(30, 15, 8))
        h_ct1.addWidget(btn_tabata)
        h_ct1.addWidget(btn_speed)
        h_ct1.addWidget(btn_power)
        h_ct1.addStretch()
        l_ctime.addLayout(h_ct1)

        h_c_signals = QHBoxLayout()
        h_c_signals.addWidget(QLabel("🔔 세트 종료 신호:"))
        self.combo_circuit_stop_signal = NoScrollComboBox()
        self.combo_circuit_stop_signal.addItem("🥋 음성: '갈려! 휴식!' (강력 추천)", "voice_kalyeo")
        self.combo_circuit_stop_signal.addItem("🔔 경기장 차임벨 (딩~동)", "bell")
        self.combo_circuit_stop_signal.addItem("🛑 음성: '중지!'", "voice_stop")
        self.combo_circuit_stop_signal.addItem("✋ 음성: '그만!'", "voice_end")
        self.combo_circuit_stop_signal.addItem("📢 심판 호각 (휘슬)", "whistle")
        self.combo_circuit_stop_signal.addItem("🔔 전자 비프음", "beep")
        h_c_signals.addWidget(self.combo_circuit_stop_signal, stretch=1)

        h_c_signals.addWidget(QLabel("🧘 휴식 구령:"))
        self.combo_circuit_rest_style = NoScrollComboBox()
        self.combo_circuit_rest_style.addItem("🔄 Catch your breath! & Take a break! 순환 (추천)", "auto_mix")
        self.combo_circuit_rest_style.addItem("💨 Catch your breath! Deep breath!", "catch_breath")
        self.combo_circuit_rest_style.addItem("☕ Take a break! Shake your legs!", "take_break")
        self.combo_circuit_rest_style.addItem("🇰🇷 한국어 전용 휴식 멘트", "kr_only")
        self.combo_circuit_rest_style.addItem("🔇 신호음만 (멘트 생략)", "none")
        h_c_signals.addWidget(self.combo_circuit_rest_style, stretch=1)
        l_ctime.addLayout(h_c_signals)

        l_circuit.addWidget(g_c_time)
        l_circuit.addStretch()
        self.tabs.addTab(tab_circuit, "🔥 기능성 서킷 인터벌 (HIIT)")

        # ══════════════════════════════════════════════════════════════════
        # ── 탭 1: 🔄 1:1, 1:2, 1:3 릴레이 미트 ──
        # ══════════════════════════════════════════════════════════════════
        tab_relay = QWidget()
        l_relay = QVBoxLayout(tab_relay)
        l_relay.setSpacing(6)

        # [탭1 - 1번 (맨 위!)] 제공된 릴레이 미트 템플릿 확인 및 대본 자유 수정
        g_relay_script = QGroupBox("1. [2단계] 제공된 릴레이 미트 템플릿 확인 및 대본 자유 수정 (넓은 편집창)")
        l_rscript = QVBoxLayout(g_relay_script)
        l_rscript.setSpacing(6)

        h_rt_tmpl = QHBoxLayout()
        h_rt_tmpl.addWidget(QLabel("📋 기본 릴레이 템플릿:"))
        self.combo_relay_template = NoScrollComboBox()
        self.combo_relay_template.addItem("🥋 [실전 3인 방족술/미트] 플레이어: 잡고 몸통 밀기 / 1번 보조자: 암미트 전진 몸통 / 2번 보조자: 손미트 상단 끊어차기", "tmpl_bangjok")
        self.combo_relay_template.addItem("⚡ [실전 콤보 1] 플레이어: 백스텝 받아차기 교차 상단 / 보조자: 전진 몸통 후 사이드 왼발 상단", "tmpl_combo1")
        self.combo_relay_template.addItem("🎯 [카운터 & 반격 콤보] 플레이어: 앞발 컷트 후 뒷발 상단 / 보조자: 사이드 스텝 뒤차기 카운터", "tmpl_counter")
        self.combo_relay_template.addItem("🛡️ [단일 기술 집중] 백스텝 후 받아차기 교차 상단", "tmpl_single")
        self.combo_relay_template.addItem("🔥 [연타 콤보] 1연타, 2연타, 3연타, 나래차기 연타", "tmpl_speed")
        self.combo_relay_template.currentIndexChanged.connect(self._on_relay_template_changed)
        h_rt_tmpl.addWidget(self.combo_relay_template, stretch=1)
        h_rt_tmpl.addWidget(self._make_refine_btn("🔄 수정한 한글로 영어·설명 다시 생성"))
        l_rscript.addLayout(h_rt_tmpl)

        l_rscript.addWidget(QLabel("📢 훈련 종합 설명 & 보조자 미트 착용 행동요령 (시작 전 사전 안내 음성 - 자유 수정):"))
        self.txt_relay_intro = CompatibleTextEdit()
        self.txt_relay_intro.setFixedHeight(78)
        self.txt_relay_intro.setPlaceholderText("시작 전 플레이어와 보조자들에게 송출할 종합 훈련 안내 및 미트 착용 요령을 입력하세요")
        self.txt_relay_intro.setPlainText("1번 방족술 - 한손 잡고 반대손 몸통 밀기. 2번 방족술 모션으로 전진 스텝 후 뒷발 몸통 차기! 1번 보조자 암미트 착용, 2번 보조자 손미트 착용 후 조금씩 거리 좁히며 빠른발 상단 끊어차기! 보조자들은 빠르게 준비해 주시고 플레이어는 기술 패턴을 숙지해 주세요.")
        l_rscript.addWidget(self.txt_relay_intro)

        l_rscript.addWidget(QLabel("🥊 실제 진행 시 플레이어 및 보조자별 지시 기술 대본 (줄바꿈으로 플레이어/보조자별 순환 기술 구분 - 넓은 편집창):"))
        self.txt_relay_cue = CompatibleTextEdit()
        self.txt_relay_cue.setMinimumHeight(130)
        self.txt_relay_cue.setMaximumHeight(200)
        self.txt_relay_cue.setPlaceholderText("각 줄마다 플레이어 및 보조자가 타격할 기술명을 입력하세요.\n예:\n한손 잡고 반대손 몸통 밀기\n전진 스텝 후 뒷발 몸통 차기\n조금씩 거리 좁히며 빠른발 상단 끊어차기")
        self.txt_relay_cue.setPlainText("한손 잡고 반대손 몸통 밀기\n전진 스텝 후 뒷발 몸통 차기\n조금씩 거리 좁히며 빠른발 상단 끊어차기")
        l_rscript.addWidget(self.txt_relay_cue)

        lbl_relay_hint = QLabel("💡 위 보라색 [1단계] 칸에 원하는 릴레이 동작을 입력해 생성하거나, 아래 대본을 한글로 수정한 뒤 [🔄 수정한 한글로 영어·설명 다시 생성]을 누르세요!")
        lbl_relay_hint.setStyleSheet("color: #0369a1; background-color: #f0f9ff; border: 1px solid #bae6fd; border-radius: 4px; padding: 4px 8px; font-size: 11px; font-weight: bold;")
        l_rscript.addWidget(lbl_relay_hint)
        l_relay.addWidget(g_relay_script)

        # [탭1 - 2번] 인원 및 시간 설정
        g_relay_t = QGroupBox("2. 훈련 참여자 인원 구성 및 타격·교대 시간 설정")
        l_rt = QVBoxLayout(g_relay_t)
        hl_rf = QHBoxLayout()
        self.rb_relay_11 = QRadioButton("1 : 1 훈련 (플레이어 ↔ 보조자)")
        self.rb_relay_12 = QRadioButton("1 : 2 훈련 (플레이어 1명 & 보조자 1번·2번)")
        self.rb_relay_13 = QRadioButton("1 : 3 훈련 (플레이어 1명 & 보조자 1번·2번·3번)")
        self.rb_relay_11.setChecked(True)
        hl_rf.addWidget(self.rb_relay_11)
        hl_rf.addWidget(self.rb_relay_12)
        hl_rf.addWidget(self.rb_relay_13)
        l_rt.addLayout(hl_rf)

        grid_rt = QGridLayout()
        grid_rt.setHorizontalSpacing(16)
        grid_rt.setVerticalSpacing(6)

        lbl_strike = QLabel("⏱️ 1인당 타격 시간:")
        self.sp_relay_strike = QSpinBox()
        self.sp_relay_strike.setRange(5, 60)
        self.sp_relay_strike.setValue(15)
        self.sp_relay_strike.setSuffix(" 초")
        self.sp_relay_strike.setFixedWidth(85)
        grid_rt.addWidget(lbl_strike, 0, 0)
        grid_rt.addWidget(self.sp_relay_strike, 0, 1)

        lbl_change = QLabel("🔄 선수 교대 시간:")
        self.sp_relay_change = QSpinBox()
        self.sp_relay_change.setRange(2, 15)
        self.sp_relay_change.setValue(3)
        self.sp_relay_change.setSuffix(" 초")
        self.sp_relay_change.setFixedWidth(85)
        grid_rt.addWidget(lbl_change, 0, 2)
        grid_rt.addWidget(self.sp_relay_change, 0, 3)

        lbl_prep_wait = QLabel("⏳ 설명 후 준비 대기:")
        self.sp_relay_prep_wait = QSpinBox()
        self.sp_relay_prep_wait.setRange(0, 60)
        self.sp_relay_prep_wait.setValue(10)
        self.sp_relay_prep_wait.setSuffix(" 초")
        self.sp_relay_prep_wait.setFixedWidth(85)
        grid_rt.addWidget(lbl_prep_wait, 0, 4)
        grid_rt.addWidget(self.sp_relay_prep_wait, 0, 5)

        lbl_cycles = QLabel("🔁 전체 순환 세트:")
        self.sp_relay_cycles = QSpinBox()
        self.sp_relay_cycles.setRange(1, 10)
        self.sp_relay_cycles.setValue(3)
        self.sp_relay_cycles.setSuffix(" 세트")
        self.sp_relay_cycles.setFixedWidth(85)
        grid_rt.addWidget(lbl_cycles, 0, 6)
        grid_rt.addWidget(self.sp_relay_cycles, 0, 7)
        l_rt.addLayout(grid_rt)

        h_rt_sig = QHBoxLayout()
        h_rt_sig.addWidget(QLabel("🔔 타격 종료 및 교대 신호:"))
        self.combo_relay_stop_signal = NoScrollComboBox()
        self.combo_relay_stop_signal.addItem("🥋 음성: '갈려!' (태권도 경기 공식 구령 - 강력 추천)", "voice_kalyeo")
        self.combo_relay_stop_signal.addItem("🛑 음성: '중지!'", "voice_stop")
        self.combo_relay_stop_signal.addItem("✋ 음성: '그만!'", "voice_end")
        self.combo_relay_stop_signal.addItem("🔔 전자 비프음", "beep")
        self.combo_relay_stop_signal.addItem("📢 심판 호각", "whistle")
        h_rt_sig.addWidget(self.combo_relay_stop_signal, stretch=1)
        l_rt.addLayout(h_rt_sig)

        l_relay.addWidget(g_relay_t)
        l_relay.addStretch()
        self.tabs.addTab(tab_relay, "🔄 1:1 / 1:2 / 1:3 릴레이 미트")

        # ══════════════════════════════════════════════════════════════════
        # ── 탭 2: ⚡ 스텝 & 실전 반응 ──
        # ══════════════════════════════════════════════════════════════════
        tab_reaction = QWidget()
        l_reac = QVBoxLayout(tab_reaction)
        l_reac.setSpacing(6)

        # [탭2 - 1번 (맨 위!)] 기술 지시 구령 및 템플릿 편집 (넓은 편집창)
        g_reac_cues = QGroupBox("1. [2단계] 제공된 실전 반응 타격 구령 확인 및 자유 수정 (넓은 편집창)")
        l_rcc = QVBoxLayout(g_reac_cues)
        l_rcc.setSpacing(6)

        h_tmpl = QHBoxLayout()
        h_tmpl.addWidget(QLabel("📋 기본 반응 템플릿:"))
        self.combo_cues_template = NoScrollComboBox()
        self.combo_cues_template.addItem("🥋 [실전 스파링 콤보] 백스텝 받아차기 교차 상단, 전진 몸통 후 사이드 상단, 앞발 컷트 후 뒷발 상단, 사이드 뒤차기", "백스텝 후 받아차기 교차 상단!, 전진 몸통차기 후 사이드 왼발 상단!, 앞발 컷트 후 뒷발 돌려차기 상단!, 사이드 스텝 후 뒤차기 카운터!")
        self.combo_cues_template.addItem("⚡ [스피드 연타] 1연타!, 2연타!, 3연타!, 앞발 나래차기!", "1연타!, 2연타!, 3연타!, 앞발 나래차기!")
        self.combo_cues_template.addItem("🛡️ [받아차기 / 카운터] 백스텝 받아차기!, 뒤차기 카운터!, 앞발 컷트!, 맞받아치기!", "백스텝 받아차기!, 뒤차기 카운터!, 앞발 컷트!, 맞받아치기!")
        self.combo_cues_template.addItem("🏃‍♂️ [기본기 순발력] 앞차기!, 돌려차기!, 내려찍기!, 옆차기!", "앞차기!, 돌려차기!, 내려찍기!, 옆차기!")
        self.combo_cues_template.currentIndexChanged.connect(self._on_cues_template_changed)
        h_tmpl.addWidget(self.combo_cues_template, stretch=1)
        h_tmpl.addWidget(self._make_refine_btn("🔄 수정한 한글로 영어·설명 다시 생성"))
        l_rcc.addLayout(h_tmpl)

        l_rcc.addWidget(QLabel("✏️ 적용할 반응 타격 기술 구령 대본 (쉼표 또는 줄바꿈으로 구분하여 자유롭게 수정하세요):"))
        self.txt_reac_cues = CompatibleTextEdit(
            "백스텝 후 받아차기 교차 상단!, 전진 몸통차기 후 사이드 왼발 상단!, 앞발 컷트 후 뒷발 돌려차기 상단!, 사이드 스텝 후 뒤차기 카운터!"
        )
        self.txt_reac_cues.setMinimumHeight(130)
        self.txt_reac_cues.setMaximumHeight(200)
        self.txt_reac_cues.setPlaceholderText("쉼표(,) 또는 줄바꿈으로 구분하여 반응 타격 기술명을 자유롭게 입력하세요")
        l_rcc.addWidget(self.txt_reac_cues)

        lbl_hint = QLabel("💡 스텝 중 위 기술명이 먼저 방송되고, 랜덤 긴장 대기 후 신호음(삑!/시작!/Let's Go!)에 맞춰 즉시 반응 타격합니다.")
        lbl_hint.setStyleSheet("color: #0369a1; background-color: #f0f9ff; border: 1px solid #bae6fd; border-radius: 4px; padding: 4px 8px; font-size: 11px; font-weight: bold;")
        l_rcc.addWidget(lbl_hint)
        l_reac.addWidget(g_reac_cues)

        # [탭2 - 2번] 훈련 시간, 복귀 템포 및 신호음
        g_reac_t = QGroupBox("2. 훈련 시간, 랜덤 긴장 대기 및 타격 신호음 설정")
        l_rct = QVBoxLayout(g_reac_t)
        l_rct.setSpacing(5)

        h_rct1 = QHBoxLayout()
        h_rct1.addWidget(QLabel("⏱️ 총 훈련 시간:"))
        self.sp_reac_dur = QSpinBox()
        self.sp_reac_dur.setRange(30, 600)
        self.sp_reac_dur.setValue(120)
        self.sp_reac_dur.setSuffix(" 초")
        self.sp_reac_dur.setFixedWidth(85)
        h_rct1.addWidget(self.sp_reac_dur)

        h_rct1.addWidget(QLabel("🦶 타격 후 복귀 대기:"))
        self.sp_reac_recovery = QDoubleSpinBox()
        self.sp_reac_recovery.setRange(0.2, 5.0)
        self.sp_reac_recovery.setSingleStep(0.1)
        self.sp_reac_recovery.setValue(0.8)
        self.sp_reac_recovery.setSuffix(" 초")
        self.sp_reac_recovery.setFixedWidth(85)
        h_rct1.addWidget(self.sp_reac_recovery)

        h_rct1.addWidget(QLabel("🎲 랜덤 대기:"))
        self.sp_reac_min = QDoubleSpinBox()
        self.sp_reac_min.setRange(0.3, 15.0)
        self.sp_reac_min.setSingleStep(0.2)
        self.sp_reac_min.setValue(1.0)
        self.sp_reac_min.setSuffix("초~")
        self.sp_reac_min.setFixedWidth(80)
        self.sp_reac_max = QDoubleSpinBox()
        self.sp_reac_max.setRange(0.5, 20.0)
        self.sp_reac_max.setSingleStep(0.2)
        self.sp_reac_max.setValue(2.5)
        self.sp_reac_max.setSuffix("초")
        self.sp_reac_max.setFixedWidth(80)
        h_rct1.addWidget(self.sp_reac_min)
        h_rct1.addWidget(self.sp_reac_max)
        h_rct1.addStretch()
        l_rct.addLayout(h_rct1)

        h_presets = QHBoxLayout()
        h_presets.addWidget(QLabel("⚡ 템포 프리셋:"))
        btn_preset_speed = QPushButton("🚀 초고속 스피드 연타")
        btn_preset_speed.clicked.connect(lambda: self._apply_reac_preset(rec=0.5, min_w=0.6, max_w=1.6))
        btn_preset_standard = QPushButton("🥋 실전 스파링 (표준)")
        btn_preset_standard.clicked.connect(lambda: self._apply_reac_preset(rec=0.8, min_w=1.0, max_w=2.5))
        btn_preset_tactical = QPushButton("🛡️ 전술 카운터 (여유)")
        btn_preset_tactical.clicked.connect(lambda: self._apply_reac_preset(rec=1.5, min_w=2.5, max_w=5.0))
        h_presets.addWidget(btn_preset_speed)
        h_presets.addWidget(btn_preset_standard)
        h_presets.addWidget(btn_preset_tactical)
        l_rct.addLayout(h_presets)

        self.lbl_reac_est = QLabel()
        self.lbl_reac_est.setStyleSheet("color: #047857; font-weight: bold; font-size: 12px; background: #ecfdf5; padding: 4px 8px; border-radius: 4px;")
        l_rct.addWidget(self.lbl_reac_est)

        self.sp_reac_dur.valueChanged.connect(self._update_reaction_estimate)
        self.sp_reac_recovery.valueChanged.connect(self._update_reaction_estimate)
        self.sp_reac_min.valueChanged.connect(self._update_reaction_estimate)
        self.sp_reac_max.valueChanged.connect(self._update_reaction_estimate)
        self._update_reaction_estimate()

        h_sig1 = QHBoxLayout()
        h_sig1.addWidget(QLabel("⚡ 타격 시작 신호:"))
        self.combo_reac_signal = NoScrollComboBox()
        self.combo_reac_signal.addItem("📢 경기용 심판 휘슬 (호각)", "whistle")
        self.combo_reac_signal.addItem("🔔 전자 비프음 (880Hz 삑~익)", "beep")
        self.combo_reac_signal.addItem("🥁 웅장한 대북 타격음 (쿵)", "drum")
        self.combo_reac_signal.addItem("🗣️ 음성 구령: '시작!'", "voice_start")
        self.combo_reac_signal.addItem("🗣️ 음성 구령: \"Let's Go!\" (미국 본토 발음)", "voice_letsgo")
        self.combo_reac_signal.addItem("🗣️ 음성 구령: \"Ready, Go!\" (미국 본토 발음)", "voice_readygo")
        self.combo_reac_signal.addItem("🗣️ 음성 구령: '탕!'", "voice_bang")
        self.combo_reac_signal.addItem("🎲 랜덤 믹스 (휘슬 / 비프 / 시작! / Let's Go! 무작위)", "random_mix")
        h_sig1.addWidget(self.combo_reac_signal, stretch=1)

        h_sig1.addWidget(QLabel("🏁 종료 신호:"))
        self.combo_reac_stop_signal = NoScrollComboBox()
        self.combo_reac_stop_signal.addItem("🥋 음성: '갈려!' (추천)", "voice_kalyeo")
        self.combo_reac_stop_signal.addItem("🛑 음성: '중지!'", "voice_stop")
        self.combo_reac_stop_signal.addItem("✋ 음성: '그만!'", "voice_end")
        self.combo_reac_stop_signal.addItem("🔔 경기장 차임벨", "bell")
        self.combo_reac_stop_signal.addItem("📢 심판 호각", "whistle")
        self.combo_reac_stop_signal.addItem("🔔 전자 비프음", "beep")
        h_sig1.addWidget(self.combo_reac_stop_signal, stretch=1)
        l_rct.addLayout(h_sig1)

        l_reac.addWidget(g_reac_t)
        l_reac.addStretch()
        self.tabs.addTab(tab_reaction, "⚡ 스텝 & 실전 반응")

        # ══════════════════════════════════════════════════════════════════
        # ── 탭 3: 🔥 스텝 + 콤비네이션 연타 ──
        # ══════════════════════════════════════════════════════════════════
        tab_combo = QWidget()
        l_combo = QVBoxLayout(tab_combo)
        l_combo.setSpacing(6)

        # [탭3 - 1번 (맨 위!)] 제공된 스텝 & 집중 공격 기술 템플릿 확인 및 대본 수정 (넓은 편집창)
        g_combo_kicks = QGroupBox("1. [2단계] 제공된 스텝 & 집중 공격 기술 템플릿 확인 및 자유 수정 (넓은 편집창)")
        l_ckk = QVBoxLayout(g_combo_kicks)
        l_ckk.setSpacing(6)

        h_tmpl_step = QHBoxLayout()
        h_tmpl_step.addWidget(QLabel("📋 스텝 템플릿:"))
        self.combo_step_tmpl = NoScrollComboBox()
        self.combo_step_tmpl.addItem("🥋 [실전 스파링 6스텝] 제자리 ➔ 앞뒤 ➔ 업다운 ➔ 앞발 ➔ 뒷발 ➔ 앞발 발바꿔",
            "제자리 스텝, 앞뒤 스텝, 업다운 스텝, 앞발 스텝, 뒷발 스텝, 앞발 스텝 발바꿔")
        self.combo_step_tmpl.addItem("⚡ [스피드 순발력] 제자리 ➔ 사이드 ➔ 지그재그 ➔ 앞발 발바꿔 ➔ 페이크",
            "제자리 스텝, 사이드 스텝, 지그재그 스텝, 앞발 스텝 발바꿔, 페이크 스텝")
        self.combo_step_tmpl.addItem("🛡️ [거리 조절 & 방어] 앞뒤 ➔ 제자리 ➔ 백스텝 후 전진 ➔ 사이드",
            "앞뒤 스텝, 제자리 스텝, 백스텝 후 전진, 사이드 스텝")
        self.combo_step_tmpl.currentIndexChanged.connect(self._on_step_tmpl_changed)
        h_tmpl_step.addWidget(self.combo_step_tmpl, stretch=1)
        h_tmpl_step.addWidget(self._make_refine_btn("🔄 수정한 한글로 영어·설명 다시 생성"))
        l_ckk.addLayout(h_tmpl_step)

        l_ckk.addWidget(QLabel("✏️ 세트별 스텝 지시 구령 (쉼표 또는 줄바꿈으로 구분 - 넓은 편집창):"))
        self.txt_combo_steps = CompatibleTextEdit("제자리 스텝, 앞뒤 스텝, 업다운 스텝, 앞발 스텝, 뒷발 스텝, 앞발 스텝 발바꿔")
        self.txt_combo_steps.setFixedHeight(72)
        self.txt_combo_steps.setPlaceholderText("쉼표 또는 줄바꿈으로 구분하여 스텝 종류를 입력하세요")
        l_ckk.addWidget(self.txt_combo_steps)

        h_tmpl_kick = QHBoxLayout()
        h_tmpl_kick.addWidget(QLabel("📋 공격 기술 템플릿:"))
        self.combo_kick_tmpl = NoScrollComboBox()
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

        l_ckk.addWidget(QLabel("✏️ 집중 훈련 발차기/공격 기술 대본 (쉼표 또는 줄바꿈 구분 - 넓은 편집창):"))
        self.txt_combo_kicks = CompatibleTextEdit("전진 몸통공격 후 사이드 스텝 상단, 백스텝 후 뒷발 받아차기 공격과 교차 상단 공격, 전진 몸통 3연타")
        self.txt_combo_kicks.setMinimumHeight(105)
        self.txt_combo_kicks.setMaximumHeight(165)
        self.txt_combo_kicks.setPlaceholderText("쉼표 또는 줄바꿈으로 구분하여 집중 공격 기술을 입력하세요")
        l_ckk.addWidget(self.txt_combo_kicks)

        h_kick_mode = QHBoxLayout()
        h_kick_mode.addWidget(QLabel("📢 기술 안내 방식:"))
        self.combo_kick_mode = NoScrollComboBox()
        self.combo_kick_mode.addItem("🗣️ 매 세트 [스텝 + 집중 기술] 함께 호명 (실전 훈련 - 강력 추천)", "each_set")
        self.combo_kick_mode.addItem("🎯 1세트에서만 기술 설명 후 2세트부터는 스텝만 호명", "first_set_only")
        self.combo_kick_mode.addItem("📢 시작 전 사전 안내에서만 종합 설명", "intro_only")
        self.combo_kick_mode.setCurrentIndex(0)
        h_kick_mode.addWidget(self.combo_kick_mode, stretch=1)
        l_ckk.addLayout(h_kick_mode)
        l_combo.addWidget(g_combo_kicks)

        # [탭3 - 2번] 스텝 및 연타 시간·신호음 설정
        g_combo_set = QGroupBox("2. 스텝·연타 시간 및 신호음 설정")
        l_cbs = QVBoxLayout(g_combo_set)
        h_cbs1 = QHBoxLayout()
        h_cbs1.addWidget(QLabel("⏱️ 스텝 유지 시간:"))
        self.sp_combo_step = QSpinBox()
        self.sp_combo_step.setRange(3, 60)
        self.sp_combo_step.setValue(8)
        self.sp_combo_step.setSuffix(" 초")
        h_cbs1.addWidget(self.sp_combo_step)

        h_cbs1.addWidget(QLabel("🔥 전력 연타 시간:"))
        self.sp_combo_strike = QSpinBox()
        self.sp_combo_strike.setRange(2, 30)
        self.sp_combo_strike.setValue(4)
        self.sp_combo_strike.setSuffix(" 초")
        h_cbs1.addWidget(self.sp_combo_strike)

        h_cbs1.addWidget(QLabel("🔁 총 세트 수:"))
        self.sp_combo_sets = QSpinBox()
        self.sp_combo_sets.setRange(1, 30)
        self.sp_combo_sets.setValue(6)
        self.sp_combo_sets.setSuffix(" 세트")
        h_cbs1.addWidget(self.sp_combo_sets)
        h_cbs1.addStretch()
        l_cbs.addLayout(h_cbs1)

        h_cs1 = QHBoxLayout()
        h_cs1.addWidget(QLabel("📢 타격 시작 신호음:"))
        self.combo_start_signal = NoScrollComboBox()
        self.combo_start_signal.addItem("📢 경기용 심판 휘슬 (호각 삐익~!)", "whistle")
        self.combo_start_signal.addItem("🔔 전자 비프음 (880Hz 삑~익!)", "beep")
        self.combo_start_signal.addItem("🥁 웅장한 대북 타격음 (쿵!)", "drum")
        h_cs1.addWidget(self.combo_start_signal, stretch=1)

        h_cs1.addWidget(QLabel("🛑 연타 종료 신호:"))
        self.combo_stop_signal = NoScrollComboBox()
        self.combo_stop_signal.addItem("🥋 음성: '갈려!' (강력 추천)", "voice_kalyeo")
        self.combo_stop_signal.addItem("🛑 음성: '중지!'", "voice_stop")
        self.combo_stop_signal.addItem("✋ 음성: '그만!'", "voice_end")
        self.combo_stop_signal.addItem("🔔 전자 비프음", "beep")
        self.combo_stop_signal.addItem("📢 심판 호각", "whistle")
        h_cs1.addWidget(self.combo_stop_signal, stretch=1)
        l_cbs.addLayout(h_cs1)

        l_combo.addWidget(g_combo_set)
        l_combo.addStretch()
        self.tabs.addTab(tab_combo, "🔥 스텝 + 콤비네이션 연타")

        # ══════════════════════════════════════════════════════════════════
        # ── 탭 4: 🥊 정규 스파링 라운드 ──
        # ══════════════════════════════════════════════════════════════════
        tab_round = QWidget()
        l_rnd = QVBoxLayout(tab_round)
        l_rnd.setSpacing(6)

        # [탭4 - 1번 (맨 위!)] 스파링 유형 및 전술/안전 대본 자유 수정 (넓은 편집창)
        g_rnd_type = QGroupBox("1. [2단계] 스파링 유형 선택 및 전술·안전 대본 자유 수정 (넓은 편집창)")
        l_rtype = QVBoxLayout(g_rnd_type)
        l_rtype.setSpacing(6)

        h_rtype_sel = QHBoxLayout()
        h_rtype_sel.addWidget(QLabel("🥊 훈련 유형:"))
        self.combo_rnd_type = NoScrollComboBox()
        self.combo_rnd_type.addItem("🥊 실전 스파링 (자유 대련 - 경기 룰 및 종료 구령)", "real")
        self.combo_rnd_type.addItem("🏃 섀도우 스파링 (가상 상대 이미지 트레이닝 & 전신 풋워크)", "shadow")
        self.combo_rnd_type.addItem("🤝 약속 스파링 (사전 합의된 공격/방어 기술 집중 훈련)", "promise")
        self.combo_rnd_type.addItem("⚔️ 플레이어 공격 / 보조자 방어 (공수 분리 역할 훈련)", "attack_defense")
        h_rtype_sel.addWidget(self.combo_rnd_type, stretch=1)
        h_rtype_sel.addWidget(self._make_refine_btn("🔄 수정한 한글로 영어·설명 다시 생성"))
        l_rtype.addLayout(h_rtype_sel)

        self.lbl_rnd_type_desc = QLabel()
        self.lbl_rnd_type_desc.setStyleSheet("color: #475569; font-size: 11px; padding: 2px 0;")
        self.lbl_rnd_type_desc.setWordWrap(True)
        l_rtype.addWidget(self.lbl_rnd_type_desc)

        # 약속/전술 스파링 대본 (항상 보이도록 하되 유형에 따라 안내 레이블 지원)
        self.widget_promise_opt = QWidget()
        l_prom = QVBoxLayout(self.widget_promise_opt)
        l_prom.setContentsMargins(0, 2, 0, 0)
        l_prom.addWidget(QLabel("🎯 라운드별 집중 약속 기술 / 전술 지시 대본 (넓은 편집창 - 자유 수정):"))
        self.txt_promise_detail = CompatibleTextEdit()
        self.txt_promise_detail.setFixedHeight(80)
        self.txt_promise_detail.setPlaceholderText("예: 앞발 찍기 후 돌려차기, 빠른 원투 후 백스텝 카운터 (위 AI 입력창으로 생성하거나 한글로 수정 후 [🔄 다시 생성] 가능)")
        l_prom.addWidget(self.txt_promise_detail)
        l_rtype.addWidget(self.widget_promise_opt)

        # 공수 진행 방식 및 사전 설명/안전 주의사항 대본
        self.widget_atk_def_opt = QWidget()
        l_atk_def = QVBoxLayout(self.widget_atk_def_opt)
        l_atk_def.setContentsMargins(0, 2, 0, 0)

        h_atk_mode = QHBoxLayout()
        h_atk_mode.addWidget(QLabel("🔄 공수 진행 방식:"))
        self.combo_atk_def_mode = NoScrollComboBox()
        self.combo_atk_def_mode.addItem("🔁 라운드별 공수 자동 교대 (1R: 플레이어공격/보조자방어, 2R: 보조자공격/플레이어방어...)", "alternate")
        self.combo_atk_def_mode.addItem("🥋 플레이어 공격 / 보조자 방어 (전 라운드 고정)", "a_attack_only")
        self.combo_atk_def_mode.addItem("🛡️ 보조자 공격 / 플레이어 방어 (전 라운드 고정)", "b_attack_only")
        h_atk_mode.addWidget(self.combo_atk_def_mode, stretch=1)
        l_atk_def.addLayout(h_atk_mode)
        l_rtype.addWidget(self.widget_atk_def_opt)

        l_rtype.addWidget(QLabel("📢 스파링 사전 설명 및 안전 주의사항 방송 대본 (넓은 편집창 - 자유 수정):"))
        self.txt_atk_def_caution = CompatibleTextEdit(
            "스파링 시 안전에 유의하세요. 방어자는 가드를 바짝 올리고 무리한 반격을 삼가며, 공격자는 과도한 흥분을 자제하고 정확한 타격에 집중하세요. 상호 부상에 절대 주의합니다!"
        )
        self.txt_atk_def_caution.setFixedHeight(85)
        self.txt_atk_def_caution.setPlaceholderText("스파링 시작 전 송출될 전술 설명 및 안전 주의사항을 자유롭게 입력하세요")
        l_rtype.addWidget(self.txt_atk_def_caution)

        self.combo_rnd_type.currentIndexChanged.connect(self._on_rnd_type_changed)
        l_rnd.addWidget(g_rnd_type)

        # [탭4 - 2번] 스파링 라운드 시간 및 종료 신호 설정
        g_rnd_set = QGroupBox("2. 스파링 라운드 시간 및 종료 신호 설정")
        l_rnds_vbox = QVBoxLayout(g_rnd_set)
        l_rnds = QHBoxLayout()
        l_rnds.addWidget(QLabel("⏱️ 1라운드 경기 시간:"))
        self.sp_rnd_time = QSpinBox()
        self.sp_rnd_time.setRange(30, 300)
        self.sp_rnd_time.setValue(90)
        self.sp_rnd_time.setSuffix(" 초")
        self.sp_rnd_time.setFixedWidth(90)
        l_rnds.addWidget(self.sp_rnd_time)

        l_rnds.addWidget(QLabel("🧘 라운드 간 휴식:"))
        self.sp_rnd_rest = QSpinBox()
        self.sp_rnd_rest.setRange(10, 120)
        self.sp_rnd_rest.setValue(30)
        self.sp_rnd_rest.setSuffix(" 초")
        self.sp_rnd_rest.setFixedWidth(90)
        l_rnds.addWidget(self.sp_rnd_rest)

        l_rnds.addWidget(QLabel("🥊 총 라운드 수:"))
        self.sp_rnd_count = QSpinBox()
        self.sp_rnd_count.setRange(1, 10)
        self.sp_rnd_count.setValue(3)
        self.sp_rnd_count.setSuffix(" 라운드")
        self.sp_rnd_count.setFixedWidth(90)
        l_rnds.addWidget(self.sp_rnd_count)
        l_rnds.addStretch()
        l_rnds_vbox.addLayout(l_rnds)

        h_rsig1 = QHBoxLayout()
        h_rsig1.addWidget(QLabel("🔔 일반 라운드 종료:"))
        self.combo_rnd_stop_signal = NoScrollComboBox()
        self.combo_rnd_stop_signal.addItem("🥋 음성: '갈려! 타임!' (강력 추천)", "voice_kalyeo")
        self.combo_rnd_stop_signal.addItem("🛑 음성: '중지! 타임!'", "voice_stop")
        self.combo_rnd_stop_signal.addItem("✋ 음성: '그만! 타임!'", "voice_end")
        self.combo_rnd_stop_signal.addItem("🔔 경기장 공/벨 (딩~동)", "bell")
        self.combo_rnd_stop_signal.addItem("📢 심판 호각", "whistle")
        self.combo_rnd_stop_signal.addItem("🔔 전자 비프음", "beep")
        h_rsig1.addWidget(self.combo_rnd_stop_signal, stretch=1)

        h_rsig1.addWidget(QLabel("🏁 최종 라운드 종료:"))
        self.combo_rnd_final_stop_signal = NoScrollComboBox()
        self.combo_rnd_final_stop_signal.addItem("✋ 음성: '그만! 타임!' (강력 추천)", "voice_end")
        self.combo_rnd_final_stop_signal.addItem("🛑 음성: '중지! 타임!'", "voice_stop")
        self.combo_rnd_final_stop_signal.addItem("🥋 음성: '갈려! 타임!'", "voice_kalyeo")
        self.combo_rnd_final_stop_signal.addItem("🔔 경기장 공/벨", "bell")
        self.combo_rnd_final_stop_signal.addItem("📢 심판 호각", "whistle")
        self.combo_rnd_final_stop_signal.addItem("🔔 전자 비프음", "beep")
        h_rsig1.addWidget(self.combo_rnd_final_stop_signal, stretch=1)
        l_rnds_vbox.addLayout(h_rsig1)

        l_rnd.addWidget(g_rnd_set)
        l_rnd.addStretch()
        self.tabs.addTab(tab_round, "🥊 정규 스파링 라운드")

        # 초기 상태 업데이트
        self._on_rnd_type_changed()

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
        self.combo_cd_style = NoScrollComboBox()
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
        self.voice_combo = NoScrollComboBox()
        self.voice_combo.addItems([
            "선히 (한국어 여성, 또렷함)",
            "인준 (한국어 남성, 힘찬 구령 추천)",
            "현수 (한국어 남성, 다국어)"
        ])
        self.voice_combo.setCurrentIndex(1)  # 인준 기본
        h_opts.addWidget(self.voice_combo)
        l_common.addLayout(h_opts)

        # 훈련 종료 후 휴식/대기 안내 멘트 설정 (사용자 요청: 물 한잔 일변도 탈피 및 스트레칭, 제자리 대기 등 다양화)
        h_outro = QVBoxLayout()
        h_outro_top = QHBoxLayout()
        h_outro_top.addWidget(QLabel("🏁 훈련 종료 멘트 (휴식/대기 안내):"))
        self.combo_outro_tmpl = NoScrollComboBox()
        self.combo_outro_tmpl.addItem("🧘 [제자리 대기] 수고하셨습니다! 제자리에 바르게 앉아 호흡을 정돈하고 대기하세요.",
            "수고하셨습니다! 제자리에 바르게 앉아 호흡을 정돈하고 대기하세요.")
        self.combo_outro_tmpl.addItem("🤸 [전신 스트레칭] 수고하셨습니다! 가볍게 몸을 풀고 전신 스트레칭하며 쿨다운하세요.",
            "수고하셨습니다! 가볍게 몸을 풀고 전신 스트레칭하며 쿨다운하세요.")
        self.combo_outro_tmpl.addItem("🧎 [심호흡 & 릴랙스] 모두 수고하셨습니다! 다리 가볍게 털고 심호흡하며 다음 지시를 기다리세요.",
            "모두 수고하셨습니다! 다리 가볍게 털고 심호흡하며 다음 지시를 기다리세요.")
        self.combo_outro_tmpl.addItem("🥋 [상호 경례 & 장비정리] 수고하셨습니다! 양 선수 마주보고 차렷, 경례! 장비 정리 후 제자리 대기하세요.",
            "수고하셨습니다! 양 선수 마주보고 차렷, 경례! 장비 정리 후 제자리 대기하세요.")
        self.combo_outro_tmpl.addItem("💧 [수분 섭취 & 호흡] 수고하셨습니다! 물 한잔 마시고 호흡 정돈하세요.",
            "수고하셨습니다! 물 한잔 마시고 호흡 정돈하세요.")
        self.combo_outro_tmpl.addItem("🏁 [완전 종료] 오늘의 훈련이 모두 종료되었습니다. 수고하셨습니다!",
            "오늘의 훈련이 모두 종료되었습니다. 수고하셨습니다!")
        self.combo_outro_tmpl.currentIndexChanged.connect(self._on_outro_tmpl_changed)
        h_outro_top.addWidget(self.combo_outro_tmpl, stretch=1)
        h_outro.addLayout(h_outro_top)

        self.txt_outro_ment = QLineEdit("수고하셨습니다! 제자리에 바르게 앉아 호흡을 정돈하고 대기하세요.")
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
        self.combo_duck_level = NoScrollComboBox()
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

    def _on_circuit_moves_text_changed(self):
        if not getattr(self, '_programmatic_circuit_text_update', False):
            self._circuit_moves_user_modified = True
            self._ai_generated_active = False
            # 사용자가 루틴을 직접 편집하면 테마 콤보박스를 'custom'으로 자연스럽게 동기화
            if hasattr(self, 'combo_circuit_theme') and self.combo_circuit_theme.currentData() != "custom":
                self.combo_circuit_theme.blockSignals(True)
                for i in range(self.combo_circuit_theme.count()):
                    if self.combo_circuit_theme.itemData(i) == "custom":
                        self.combo_circuit_theme.setCurrentIndex(i)
                        break
                self.combo_circuit_theme.blockSignals(False)

    def _on_circuit_theme_changed(self, idx):
        selected_theme = self.combo_circuit_theme.currentData()
        theme_desc_map = {
            "power_agility": "🥋 [실전 대련과 낙법 협응]: 점프 발차기 후 신속한 전방낙법으로 연결하여 위기 대처 능력과 신체 협응력을 기르는 실전 훈련 루프",
            "agility_power_combo": "⚡ [순발력과 민첩성 폭발]: 버피와 점프턴, 빠른 나래차기로 심폐 한계를 극복하고 폭발적인 반응을 끌어올리는 루틴",
            "footwork_reaction_combo": "🏃‍♂️ [스파링 풋워크와 카운터]: 전후좌우 스텝으로 거리를 조율하고 상대 공격 시 신속한 컷트와 뒤차기로 반격하는 전술 루틴",
            "strength_endurance_combo": "💪 [근지구력과 전신 파워]: 푸시업과 복근, 지치지 않는 연속 발차기를 결합한 전신 체력 강화 루틴",
            "taekwondo_sparring_tactics": "🔥 [겨루기 실전 전술 콤보]: 나래차기 연타 후 회전 뒤후리기와 돌개차기로 이어지는 대회 실전 연속기 훈련",
            "custom": "✏️ [사범님 맞춤 테마]: 원하는 테마 명칭과 운동 루틴을 직접 입력하거나 수정 후 [👉 테마 명칭 반영] 또는 [✨ 즉석 템플릿 생성]을 누르세요."
        }
        if hasattr(self, 'lbl_circuit_theme_desc'):
            self.lbl_circuit_theme_desc.setText(theme_desc_map.get(selected_theme, ""))

        if selected_theme == "custom":
            if hasattr(self, 'txt_circuit_theme_title'):
                cur_title = self.txt_circuit_theme_title.text().strip()
                if not cur_title or any(p in cur_title for p in ["실전 대련", "대련 실전", "순발력", "스파링 풋워크", "근지구력"]):
                    self.txt_circuit_theme_title.setText("실전 맞춤형 서킷 인터벌 콤보")
                self.txt_circuit_theme_title.setFocus()
            return

        if getattr(self, '_circuit_moves_user_modified', False):
            reply = QMessageBox.question(
                self,
                "루틴 덮어쓰기 확인",
                "현재 직접 편집한 콤보 루틴 내용이 있습니다.\n새로 선택한 테마의 기본 루틴으로 덮어쓰시겠습니까?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
        self._circuit_moves_user_modified = False
        self._ai_generated_active = False
        self._update_circuit_moves_text()

    def _on_apply_circuit_theme_title(self):
        """사범님이 수정한 테마 명칭을 사전 설명 방송 및 상태창에 즉시 연결하여 반영"""
        title = self.txt_circuit_theme_title.text().strip() if hasattr(self, 'txt_circuit_theme_title') else ""
        if not title:
            title = "실전 맞춤형 서킷 인터벌 콤보"
            if hasattr(self, 'txt_circuit_theme_title'):
                self.txt_circuit_theme_title.setText(title)

        if hasattr(self, 'txt_circuit_intro'):
            new_intro = f"지금부터 {title} 인터벌 훈련을 시작합니다! 지시하는 동작에 맞춰 신속하게 다음 동작으로 연결하며 전력으로 반복하세요! 모두 준비해 주세요!"
            self.txt_circuit_intro.setPlainText(new_intro)

        if hasattr(self, 'status_lbl'):
            self.status_lbl.setText(f"✅ '{title}' 테마 명칭이 사전 설명 방송에 즉시 반영되었습니다. 이제 [🔄 수정한 한글로 영어·설명 다시 생성하기]를 누르면 일치된 영어가 생성됩니다.")

    def _on_circuit_lang_changed(self, idx):
        cur_lang = self.combo_circuit_lang.currentData() if hasattr(self, 'combo_circuit_lang') else "mix_kids"
        if hasattr(self, 'lbl_lang_mode_desc'):
            desc_map = {
                "mix_kids": "💡 [직관 액션 구령 (유소년·초보 추천)]: 횟수·동작을 짧고 명쾌하게 끊어 외쳐 수련생이 직관적으로 바로 반응합니다. (예: Two pushups! Five fast kicks! Go!)",
                "dual_step": "⚡ [자세·흐름 코칭 (중·상급 추천)]: 단순 횟수 외침을 넘어 호흡과 자세 전환을 코칭하는 대화형 현장 영어입니다. (예: Down for two pushups, explode up fast!)",
                "kr": "🇰🇷 [한국어 전용]: 또렷한 한국어 동작 설명 및 절도 있는 사범님 기합 구령으로만 진행합니다.",
                "en_advanced": "🇺🇸 [원어민 코치 풀 잉글리시]: 시작 사전 안내부터 훈련 전 과정이 100% 원어민 코치 영어로 진행됩니다."
            }
            self.lbl_lang_mode_desc.setText(desc_map.get(cur_lang, ""))

        # 만약 방금 AI로 자동 생성한 상태라면, 변경된 언어 모드로 즉시 AI 재변환
        if getattr(self, '_ai_generated_active', False) and (
            (hasattr(self, 'txt_ai_circuit_prompt') and self.txt_ai_circuit_prompt.text().strip())
            or getattr(self, '_ai_loaded_doc_text', '')
        ):
            self._on_ai_generate_circuit()
            return

        if getattr(self, '_circuit_moves_user_modified', False):
            reply = QMessageBox.question(
                self,
                "언어 변경 확인",
                "현재 직접 편집한 콤보 루틴 내용이 있습니다.\n선택한 언어의 기본 루틴으로 덮어쓰시겠습니까?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
        self._circuit_moves_user_modified = False
        self._update_circuit_moves_text()

    def _on_open_ai_settings_dialog(self):
        """AI 키·구글 드라이브 링크·공통 수련계획표를 관리하는 통합 설정창 열기"""
        dlg = GlobalAISettingsDialog(self)
        if dlg.exec():
            common = load_common_settings()
            common_doc = common.get("common_doc_text", "").strip()
            if common_doc and not getattr(self, '_ai_loaded_doc_text', ''):
                self._ai_loaded_doc_text = common_doc
            if hasattr(self, 'status_lbl'):
                self.status_lbl.setText("✅ AI 키 및 공통 수련계획표 설정이 반영되었습니다.")

    def _on_ai_load_gdrive_link(self):
        """구글 드라이브 / 구글 문서 / 구글 시트 공유 링크를 입력받아 즉시 수련계획표 로드 및 템플릿 생성"""
        common = load_common_settings()
        default_url = common.get("gdrive_url", "")
        url, ok = QInputDialog.getText(
            self,
            "🔗 구글 드라이브 / 문서 링크 불러오기",
            "구글 문서(Docs), 스프레드시트(Sheets), 드라이브 파일 공유 링크를 붙여넣으세요:\n"
            "(※ 링크가 있는 모든 사용자에게 '뷰어' 권한이 열려 있어야 합니다)",
            QLineEdit.EchoMode.Normal,
            default_url
        )
        if not ok or not url.strip():
            return

        if hasattr(self, 'status_lbl'):
            self.status_lbl.setText("⏳ 구글 드라이브 링크에서 수련계획표 내용을 불러오는 중...")
        QApplication.processEvents()

        ok_fetch, result_text = fetch_text_from_url(url.strip())
        if not ok_fetch:
            QMessageBox.warning(self, "링크 불러오기 실패", result_text)
            if hasattr(self, 'status_lbl'):
                self.status_lbl.setText("⚠️ 구글 드라이브 링크 불러오기에 실패했습니다.")
            return

        self._ai_loaded_doc_text = result_text
        if hasattr(self, 'txt_ai_circuit_prompt') and not self.txt_ai_circuit_prompt.text().strip():
            self.txt_ai_circuit_prompt.setText("[구글 드라이브 링크] 수련계획표 기반 서킷 루틴")

        self._on_ai_generate_circuit()

    def _on_ai_load_circuit_file(self):
        """수련계획표나 운동 메모 파일(.txt, .docx, .md, .csv)을 불러와 즉시 AI 서킷 대본으로 자동 생성"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "수련계획표 / 운동 메모 파일 불러오기",
            "",
            "문서 파일 (*.txt *.md *.docx *.csv *.json);;모든 파일 (*)"
        )
        if not file_path:
            return

        doc_text = extract_text_from_file(file_path)
        if not doc_text or doc_text.startswith("[파일 읽기 오류"):
            QMessageBox.warning(self, "파일 읽기 실패", f"파일 내용을 읽을 수 없습니다.\n{doc_text}")
            return

        self._ai_loaded_doc_text = doc_text
        base_name = os.path.basename(file_path)
        if hasattr(self, 'txt_ai_circuit_prompt') and not self.txt_ai_circuit_prompt.text().strip():
            self.txt_ai_circuit_prompt.setText(f"[{base_name}] 파일 기반 서킷 루틴")

        self._on_ai_generate_circuit()

    def _get_active_tab_mode(self) -> str:
        idx = self.tabs.currentIndex() if hasattr(self, 'tabs') else 0
        return {0: "circuit", 1: "relay", 2: "reaction", 3: "combo", 4: "round"}.get(idx, "circuit")

    def _collect_active_tab_fields(self, tab_mode: str) -> dict:
        if tab_mode == "circuit":
            moves = self.txt_circuit_moves.toPlainText().strip() if hasattr(self, 'txt_circuit_moves') else ""
            intro = self.txt_circuit_intro.toPlainText().strip() if hasattr(self, 'txt_circuit_intro') else ""
            theme = self.txt_circuit_theme_title.text().strip() if hasattr(self, 'txt_circuit_theme_title') else ""
            return {
                "theme_title": theme,
                "intro_text": intro,
                "formatted_moves": moves,
                "moves_text": moves,
                "mode_type": "single" if (hasattr(self, 'rb_circuit_single') and self.rb_circuit_single.isChecked()) else "cycle"
            }
        elif tab_mode == "relay":
            intro = self.txt_relay_intro.toPlainText().strip() if hasattr(self, 'txt_relay_intro') else ""
            cue = self.txt_relay_cue.toPlainText().strip() if hasattr(self, 'txt_relay_cue') else ""
            return {
                "intro_text": intro,
                "relay_intro": intro,
                "cue_text": cue,
                "relay_cues": cue,
            }
        elif tab_mode == "reaction":
            cues = self.txt_reac_cues.text().strip() if hasattr(self, 'txt_reac_cues') else ""
            return {
                "cues": cues,
                "reac_cues": cues,
            }
        elif tab_mode == "combo":
            steps = self.txt_combo_steps.text().strip() if hasattr(self, 'txt_combo_steps') else ""
            kicks = self.txt_combo_kicks.text().strip() if hasattr(self, 'txt_combo_kicks') else ""
            return {
                "step_types": steps,
                "combo_steps": steps,
                "kick_types": kicks,
                "combo_kicks": kicks,
            }
        elif tab_mode == "round":
            rnd_type = self.combo_rnd_type.currentData() if hasattr(self, 'combo_rnd_type') else "real"
            promise = self.txt_promise_detail.text().strip() if hasattr(self, 'txt_promise_detail') else ""
            caution = self.txt_atk_def_caution.text().strip() if hasattr(self, 'txt_atk_def_caution') else ""
            return {
                "round_type": rnd_type,
                "promise_detail": promise,
                "caution_text": caution,
            }
        return {}

    def _set_refine_buttons_state(self, enabled: bool, busy_text: Optional[str] = None):
        for btn in getattr(self, '_refine_buttons', []):
            btn.setEnabled(enabled)
            if busy_text:
                btn.setText(busy_text)
            else:
                btn.setText("🔄 수정한 한글로 영어·설명 다시 생성")

    def _on_ai_generate_circuit(self):
        """현재 선택된 탭에 맞춰 요구사항 타이핑 또는 첨부된 계획표/링크를 기반으로 즉석 템플릿 생성"""
        user_prompt = self.txt_ai_circuit_prompt.text().strip() if hasattr(self, 'txt_ai_circuit_prompt') else ""
        doc_text = getattr(self, '_ai_loaded_doc_text', '')
        if not doc_text:
            common = load_common_settings()
            doc_text = common.get("common_doc_text", "").strip()

        if not user_prompt and not doc_text:
            QMessageBox.information(
                self,
                "운동 요구사항 입력 안내",
                "상단 입력창에 원하는 운동 요구사항을 입력하거나 [🔗 구글드라이브] / [📂 내 파일]을 선택해 주세요.\n\n"
                "💡 입력 예시:\n"
                "• 서킷으로 팔굽혀펴기 2회, 빠른발차기 5회, 버피 2회 할거야\n"
                "• 릴레이 미트: 1세트는 원투 펀치 후 돌려차기, 2세트는 백스텝 받아차기\n"
                "• 반응 훈련: 원투, 더킹, 나래차기, 뒤차기 구령으로 구성\n"
                "• 스텝 연타: 빠른발 스텝 뛰다가 신호 울리면 3연타와 나래차기"
            )
            if hasattr(self, 'txt_ai_circuit_prompt'):
                self.txt_ai_circuit_prompt.setFocus()
            return

        tab_mode = self._get_active_tab_mode()
        lang_mode = self.combo_circuit_lang.currentData() if hasattr(self, 'combo_circuit_lang') else "mix_kids"
        lang_mode = lang_mode or "mix_kids"
        mode_type = "single" if (hasattr(self, 'rb_circuit_single') and self.rb_circuit_single.isChecked()) else "cycle"

        if hasattr(self, 'btn_ai_circuit_gen'):
            self.btn_ai_circuit_gen.setEnabled(False)
            self.btn_ai_circuit_gen.setText("⏳ 즉석 템플릿 생성 중...")
        self._set_refine_buttons_state(False)
        if hasattr(self, 'status_lbl'):
            self.status_lbl.setText("🤖 현재 탭에 맞는 즉석 템플릿(사전 설명 + 현장 구령 대본)을 생성하고 있습니다...")

        self._ai_circuit_worker = AICircuitWorker(
            prompt=user_prompt,
            tab_mode=tab_mode,
            lang_mode=lang_mode,
            mode_type=mode_type,
            doc_text=doc_text,
            refine_mode=False,
            current_fields=self._collect_active_tab_fields(tab_mode),
            parent=self
        )
        self._ai_circuit_worker.finished_ok.connect(self._on_ai_circuit_finished)
        self._ai_circuit_worker.failed.connect(self._on_ai_circuit_failed)
        self._ai_circuit_worker.start()

    def _on_ai_refine_circuit(self):
        """현재 탭에서 사용자가 한국어로 수정한 템플릿 내용을 바탕으로 현장감 있는 영어 구령과 설명을 AI가 다시 맞춰줌"""
        tab_mode = self._get_active_tab_mode()
        current_fields = self._collect_active_tab_fields(tab_mode)
        has_any_text = any(bool(str(v).strip()) for k, v in current_fields.items() if k != "round_type")
        if not has_any_text:
            QMessageBox.information(
                self,
                "수정할 템플릿 없음",
                "현재 탭의 템플릿 편집창에 동작이나 한글 설명을 먼저 입력하거나 수정해 주세요."
            )
            return

        user_prompt = self.txt_ai_circuit_prompt.text().strip() if hasattr(self, 'txt_ai_circuit_prompt') else ""
        lang_mode = self.combo_circuit_lang.currentData() if hasattr(self, 'combo_circuit_lang') else "mix_kids"
        lang_mode = lang_mode or "mix_kids"
        mode_type = "single" if (hasattr(self, 'rb_circuit_single') and self.rb_circuit_single.isChecked()) else "cycle"

        if hasattr(self, 'btn_ai_circuit_gen'):
            self.btn_ai_circuit_gen.setEnabled(False)
        self._set_refine_buttons_state(False, "⏳ 한글 수정본 재작성 중...")
        if hasattr(self, 'status_lbl'):
            self.status_lbl.setText("🔄 수정하신 한국어 동작에 맞춰 쉽고 자연스러운 현장 영어 구령과 사전 설명을 다시 생성하고 있습니다...")

        self._ai_circuit_worker = AICircuitWorker(
            prompt=user_prompt,
            tab_mode=tab_mode,
            lang_mode=lang_mode,
            mode_type=mode_type,
            refine_mode=True,
            edited_moves_text=current_fields.get("formatted_moves", ""),
            current_theme_title=current_fields.get("theme_title", ""),
            current_intro_text=current_fields.get("intro_text", ""),
            current_fields=current_fields,
            parent=self
        )
        self._ai_circuit_worker.finished_ok.connect(self._on_ai_circuit_finished)
        self._ai_circuit_worker.failed.connect(self._on_ai_circuit_failed)
        self._ai_circuit_worker.start()

    def _on_ai_circuit_finished(self, res: dict):
        if hasattr(self, 'btn_ai_circuit_gen'):
            self.btn_ai_circuit_gen.setEnabled(True)
            self.btn_ai_circuit_gen.setText("✨ 현재 탭에 즉석 템플릿 생성")
        self._set_refine_buttons_state(True)

        tab_mode = res.get("tab_mode", self._get_active_tab_mode())
        self._programmatic_circuit_text_update = True
        try:
            if tab_mode == "circuit":
                theme_title = res.get("theme_title", "").strip()
                intro_text = res.get("intro_text", "").strip()
                formatted_moves = res.get("formatted_moves", "").strip()

                if hasattr(self, 'combo_circuit_theme'):
                    self.combo_circuit_theme.blockSignals(True)
                    for i in range(self.combo_circuit_theme.count()):
                        if self.combo_circuit_theme.itemData(i) == "custom":
                            self.combo_circuit_theme.setCurrentIndex(i)
                            break
                    self.combo_circuit_theme.blockSignals(False)

                if theme_title and hasattr(self, 'txt_circuit_theme_title'):
                    self.txt_circuit_theme_title.setText(theme_title)
                if intro_text and hasattr(self, 'txt_circuit_intro'):
                    self.txt_circuit_intro.setText(intro_text)
                if formatted_moves and hasattr(self, 'txt_circuit_moves'):
                    self.txt_circuit_moves.setPlainText(formatted_moves)

                self._circuit_moves_user_modified = True
                self._ai_generated_active = True

            elif tab_mode == "relay":
                intro_text = (res.get("intro_text") or res.get("relay_intro") or "").strip()
                cue_text = (res.get("cue_text") or res.get("relay_cues") or "").strip()
                if intro_text and hasattr(self, 'txt_relay_intro'):
                    self.txt_relay_intro.setPlainText(intro_text)
                if cue_text and hasattr(self, 'txt_relay_cue'):
                    self.txt_relay_cue.setPlainText(cue_text)

            elif tab_mode == "reaction":
                cues = (res.get("cues") or res.get("reac_cues") or "").strip()
                if cues and hasattr(self, 'txt_reac_cues'):
                    self.txt_reac_cues.setText(cues)

            elif tab_mode == "combo":
                step_types = (res.get("step_types") or res.get("combo_steps") or "").strip()
                kick_types = (res.get("kick_types") or res.get("combo_kicks") or "").strip()
                if step_types and hasattr(self, 'txt_combo_steps'):
                    self.txt_combo_steps.setText(step_types)
                if kick_types and hasattr(self, 'txt_combo_kicks'):
                    self.txt_combo_kicks.setText(kick_types)

            elif tab_mode == "round":
                rnd_type = res.get("round_type", "").strip()
                promise_detail = res.get("promise_detail", "").strip()
                caution_text = res.get("caution_text", "").strip()
                if rnd_type and hasattr(self, 'combo_rnd_type'):
                    for i in range(self.combo_rnd_type.count()):
                        if self.combo_rnd_type.itemData(i) == rnd_type:
                            self.combo_rnd_type.setCurrentIndex(i)
                            break
                if promise_detail and hasattr(self, 'txt_promise_detail'):
                    self.txt_promise_detail.setText(promise_detail)
                if caution_text and hasattr(self, 'txt_atk_def_caution'):
                    self.txt_atk_def_caution.setText(caution_text)

            if hasattr(self, 'status_lbl'):
                self.status_lbl.setText(
                    "✨ 즉석 템플릿이 완성되었습니다! 편집창에서 확인·수정한 뒤 아래 [🚀 맞춤 훈련 음원 생성하기]를 누르세요."
                )
        finally:
            self._programmatic_circuit_text_update = False

    def _on_ai_circuit_failed(self, err_msg: str):
        if hasattr(self, 'btn_ai_circuit_gen'):
            self.btn_ai_circuit_gen.setEnabled(True)
            self.btn_ai_circuit_gen.setText("✨ 현재 탭에 즉석 템플릿 생성")
        self._set_refine_buttons_state(True)
        if hasattr(self, 'status_lbl'):
            self.status_lbl.setText(f"⚠️ AI 대본 생성 오류: {err_msg}")
        QMessageBox.warning(self, "AI 자동완성 오류", f"AI 대본 생성 중 오류가 발생했습니다:\n{err_msg}")

    def _shuffle_circuit_moves(self):
        """현재 테마의 풍부한 동작 라이브러리에서 무작위로 4개의 신선한 콤보를 자동 추출"""
        theme_key = self.combo_circuit_theme.currentData() or "power_agility"
        if theme_key == "custom":
            if hasattr(self, 'txt_ai_circuit_prompt') and self.txt_ai_circuit_prompt.text().strip():
                self._on_ai_generate_circuit()
                return
            QMessageBox.information(self, "커스텀 모드", "직접 입력 모드에서는 상단 AI 자동완성 칸에 원하는 동작을 입력하거나 직접 편집하실 수 있습니다.")
            return

        lang_mode = self.combo_circuit_lang.currentData() or "kr"
        lang_field = "mix" if lang_mode == "mix_kids" else ("dual" if lang_mode == "dual_step" else ("en" if lang_mode == "en_advanced" else "kr"))

        random_exercises = SparringTrainingEngine.get_random_circuit_routine(theme_key, lang_mode, count=4)
        if not random_exercises:
            return

        self._programmatic_circuit_text_update = True
        try:
            lines = []
            for i, ex in enumerate(random_exercises, 1):
                text = ex.get(lang_field, ex.get("kr", ""))
                tip = ex.get("tip", "")
                lines.append(f"{i}번 콤보: {text}\n   ➔ [지도 팁]: {tip}\n")

            self.txt_circuit_moves.setPlainText("\n".join(lines).strip())
            self._circuit_moves_user_modified = False
            self._ai_generated_active = False
        finally:
            self._programmatic_circuit_text_update = False

    def _update_circuit_moves_text(self):
        theme_key = self.combo_circuit_theme.currentData() or "power_agility"
        if theme_key == "custom":
            return

        self._programmatic_circuit_text_update = True
        try:
            lang_mode = self.combo_circuit_lang.currentData() or "kr"
            theme_data = CIRCUIT_INTERVAL_THEMES.get(theme_key, CIRCUIT_INTERVAL_THEMES.get("power_agility", {}))
            exercises = theme_data.get("exercises", [])

            lang_field = "mix" if lang_mode == "mix_kids" else ("dual" if lang_mode == "dual_step" else ("en" if lang_mode == "en_advanced" else "kr"))

            # 테마 명칭 필드 자동 동기화
            if hasattr(self, 'txt_circuit_theme_title'):
                preset_title = theme_data.get(f"name_{lang_field}", theme_data.get("name_kr", "기능성 서킷 인터벌"))
                self.txt_circuit_theme_title.setText(clean_speech_text(preset_title))

            # 사전 설명 방송 기본값 자동 동기화 (화면에 즉시 표시되어 확인 및 수정 가능)
            if hasattr(self, 'txt_circuit_intro'):
                if lang_mode in ("en", "en_advanced"):
                    default_intro = "Circuit interval training starts now! Connect your jumps, kicks, and techniques with maximum intensity. Push your limits every set! Get ready!"
                elif theme_key == "power_agility":
                    default_intro = "지금부터 실전 서킷 인터벌 훈련을 시작합니다! 이번 훈련은 점프와 발차기, 그리고 낙법 콤보를 연결하여 실전 감각과 신체 협응력을 기르는 시간입니다. 지시하는 동작에 맞춰 신속하게 다음 동작으로 연결하며 전력으로 반복하세요! 모두 준비해 주세요!"
                elif theme_key == "agility_power_combo":
                    default_intro = "지금부터 실전 서킷 인터벌 훈련을 시작합니다! 이번 훈련은 폭발적인 버피와 점프, 연속 발차기를 통해 순발력과 민첩성을 극대화하는 시간입니다. 지시하는 구령에 맞춰 끝까지 빠른 템포로 집중하세요! 모두 준비해 주세요!"
                elif theme_key == "footwork_reaction_combo":
                    default_intro = "지금부터 실전 서킷 인터벌 훈련을 시작합니다! 이번 훈련은 빠른 스텝 풋워크와 번개 같은 카운터 발차기 공방을 익히는 시간입니다. 상대의 빈틈을 노려 빠르고 정확하게 타격하세요! 모두 준비해 주세요!"
                elif theme_key == "strength_endurance_combo":
                    default_intro = "지금부터 실전 서킷 인터벌 훈련을 시작합니다! 이번 훈련은 푸시업과 복근, 그리고 연타 발차기를 묶어 전신 파워와 근지구력을 기르는 시간입니다. 지친 순간에도 바른 자세를 유지하며 한계에 도전하세요! 모두 준비해 주세요!"
                elif theme_key == "taekwondo_sparring_tactics":
                    default_intro = "지금부터 실전 서킷 인터벌 훈련을 시작합니다! 이번 훈련은 앞발 견제와 기습 회전차기 등 실전 겨루기 득점 콤보를 무한 반복하는 시간입니다. 실전 시합의 긴장감을 유지하며 전력으로 꽂아 넣으세요! 모두 준비해 주세요!"
                else:
                    default_intro = "지금부터 실전 서킷 인터벌 훈련을 시작합니다! 지시하는 동작에 맞춰 신속하게 다음 동작을 연결하며 전력으로 반복하세요! 모두 준비해 주세요!"
                self.txt_circuit_intro.setText(default_intro)

            lines = []
            # 기본 4개 콤보 표시
            display_exercises = exercises[:4] if len(exercises) >= 4 else exercises
            for i, ex in enumerate(display_exercises, 1):
                text = ex.get(lang_field, ex.get("kr", ""))
                tip = ex.get("tip", "")
                lines.append(f"{i}번 콤보: {text}\n   ➔ [지도 팁]: {tip}\n")

            self.txt_circuit_moves.setPlainText("\n".join(lines).strip())
        finally:
            self._programmatic_circuit_text_update = False

    def browse_bgm(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "배경음악(BGM) 다중 선택 (여러 곡 가능)", "",
            "Audio Files (*.mp3 *.wav *.ogg *.m4a)"
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
                "1번 방족술 - 한손 잡고 반대손 몸통 밀기. 2번 방족술 모션으로 전진 스텝 후 뒷발 몸통 차기! 1번 보조자 암미트 착용, 2번 보조자 손미트 착용 후 조금씩 거리 좁히며 빠른발 상단 끊어차기! 보조자들은 빠르게 준비해 주시고 플레이어는 기술 패턴을 숙지해 주세요.",
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

    def _on_rnd_type_changed(self):
        """정규 스파링 훈련 유형 변경 시 UI 상태 동적 전환"""
        if not hasattr(self, 'combo_rnd_type'):
            return
        rnd_type = self.combo_rnd_type.currentData()
        if rnd_type == "shadow":
            self.lbl_rnd_type_desc.setText(
                "💡 가상 상대를 이미지 트레이닝하며 전신 풋워크와 연속기를 구사합니다. "
                "라운드 시작 '제 n라운드! 준비!' 및 종료 10초 전 '전력 스퍼트!' 구령이 송출됩니다."
            )
            self.widget_promise_opt.setVisible(True)
            self.widget_atk_def_opt.setVisible(False)
        elif rnd_type == "promise":
            self.lbl_rnd_type_desc.setText(
                "💡 사전에 합의된 공격/방어 기술을 집중 훈련합니다. "
                "약속 기술을 입력하시면 사전 안내 방송에 함께 호명되어 수련생들의 집중도를 극대화합니다."
            )
            self.widget_promise_opt.setVisible(True)
            self.widget_atk_def_opt.setVisible(False)
        elif rnd_type == "attack_defense":
            self.lbl_rnd_type_desc.setText(
                "💡 플레이어는 공격, 보조자는 방어(또는 교대)를 수행하는 공수 특화 훈련입니다. "
                "라운드별로 역할을 자동 교대하거나 특정 역할을 고정하여 진행할 수 있습니다."
            )
            self.widget_promise_opt.setVisible(True)
            self.widget_atk_def_opt.setVisible(True)
        else:  # real
            self.lbl_rnd_type_desc.setText(
                "💡 실전 경기와 동일한 환경으로 양 참가자가 마주보고 자유 대련을 펼칩니다. "
                "경기 시작 휘슬, 10초 전 '공격!' 구령, 종료 시 '갈려!' 및 최종 경기 종료 멘트가 지원됩니다."
            )
            self.widget_promise_opt.setVisible(True)
            self.widget_atk_def_opt.setVisible(False)


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
            params["theme_title"] = self.txt_circuit_theme_title.text().strip() if hasattr(self, 'txt_circuit_theme_title') else ""
            params["intro_text"] = self.txt_circuit_intro.text().strip() if hasattr(self, 'txt_circuit_intro') else ""
            params["language_mode"] = self.combo_circuit_lang.currentData() or "kr"
            params["circuit_mode_type"] = "single" if hasattr(self, 'rb_circuit_single') and self.rb_circuit_single.isChecked() else "cycle"
            params["custom_routine_text"] = self.txt_circuit_moves.toPlainText().strip()
            params["stop_signal"] = self.combo_circuit_stop_signal.currentData() if hasattr(self, 'combo_circuit_stop_signal') else "voice_kalyeo"
            params["rest_style"] = self.combo_circuit_rest_style.currentData() if hasattr(self, 'combo_circuit_rest_style') else "auto_mix"

        elif mode == "relay":
            fighters = 2 if self.rb_relay_11.isChecked() else (3 if self.rb_relay_12.isChecked() else 4)
            params["fighters_count"] = fighters
            params["strike_sec"] = float(self.sp_relay_strike.value())
            params["change_sec"] = float(self.sp_relay_change.value())
            params["prep_wait_sec"] = float(self.sp_relay_prep_wait.value())
            params["cycles"] = self.sp_relay_cycles.value()
            params["intro_text"] = self.txt_relay_intro.toPlainText().strip()
            params["cue_text"] = self.txt_relay_cue.toPlainText().strip() or "백스텝 후 받아차기 교차 상단"
            params["stop_signal"] = self.combo_relay_stop_signal.currentData() if hasattr(self, 'combo_relay_stop_signal') else "voice_kalyeo"

        elif mode == "reaction":
            params["duration_sec"] = float(self.sp_reac_dur.value())
            params["min_interval"] = float(self.sp_reac_min.value())
            params["max_interval"] = float(self.sp_reac_max.value())
            params["recovery_sec"] = float(self.sp_reac_recovery.value())
            raw_cues = [c.strip() for line in self.txt_reac_cues.text().splitlines() for c in line.split(",") if c.strip()]
            params["cues"] = raw_cues or ["1연타!", "2연타!", "받아차기!", "카운터!"]
            params["signal_sound"] = self.combo_reac_signal.currentData()
            params["stop_signal"] = self.combo_reac_stop_signal.currentData() if hasattr(self, 'combo_reac_stop_signal') else "voice_kalyeo"

        elif mode == "combo":
            params["step_sec"] = float(self.sp_combo_step.value())
            params["combo_sec"] = float(self.sp_combo_strike.value())
            params["sets_count"] = self.sp_combo_sets.value()
            raw_steps = [s.strip() for line in self.txt_combo_steps.text().splitlines() for s in line.split(",") if s.strip()]
            params["step_types"] = raw_steps
            params["start_signal"] = self.combo_start_signal.currentData() or "whistle"
            params["stop_signal"] = self.combo_stop_signal.currentData() or "voice_kalyeo"
            raw_kicks = [k.strip() for line in self.txt_combo_kicks.text().splitlines() for k in line.split(",") if k.strip()]
            params["kick_types"] = raw_kicks
            params["kick_announce_mode"] = self.combo_kick_mode.currentData() or "each_set"

        elif mode == "rounds":
            params["round_sec"] = float(self.sp_rnd_time.value())
            params["rest_sec"] = float(self.sp_rnd_rest.value())
            params["total_rounds"] = self.sp_rnd_count.value()
            params["stop_signal"] = self.combo_rnd_stop_signal.currentData() if hasattr(self, 'combo_rnd_stop_signal') else "voice_kalyeo"
            params["final_stop_signal"] = self.combo_rnd_final_stop_signal.currentData() if hasattr(self, 'combo_rnd_final_stop_signal') else "voice_end"
            params["round_type"] = self.combo_rnd_type.currentData() if hasattr(self, 'combo_rnd_type') else "real"
            params["promise_detail"] = self.txt_promise_detail.text().strip() if hasattr(self, 'txt_promise_detail') else ""
            params["atk_def_mode"] = self.combo_atk_def_mode.currentData() if hasattr(self, 'combo_atk_def_mode') else "alternate"
            params["caution_text"] = self.txt_atk_def_caution.text().strip() if hasattr(self, 'txt_atk_def_caution') else ""

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
                    suggested = result_data.get("suggested_filename", f"스파링훈련_{result_data['mode']}_{dur_m}분{dur_s}초.wav")
                    save_path, _ = QFileDialog.getSaveFileName(
                        self, "훈련 음원 저장",
                        suggested,
                        "Audio Files (*.wav *.mp3)"
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
