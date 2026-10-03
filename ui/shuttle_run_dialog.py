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
from pydub.silence import detect_leading_silence


def vol_pct_to_db(pct: int) -> float:
    """선형 퍼센트(%) 볼륨을 데시벨(dB)로 변환 (0% -> -60dB 무음, 100% -> 0dB)"""
    if pct <= 0:
        return -60.0
    return round(20.0 * math.log10(pct / 100.0), 2)


def trim_audio_silence(seg: AudioSegment, threshold: float = -46.0) -> AudioSegment:
    """TTS 음성의 앞쪽 무음은 깔끔히 자르고, 뒤쪽은 말끝 여운이 잘리지 않도록 350ms 안전 여백과 부드러운 페이드아웃 적용"""
    try:
        lead = detect_leading_silence(seg, silence_threshold=threshold)
        trail = detect_leading_silence(seg.reverse(), silence_threshold=threshold)
        safe_trail = max(0, trail - 350)
        end_idx = max(lead, len(seg) - safe_trail)
        trimmed = seg[lead:end_idx]
        if len(trimmed) > 100:
            trimmed = trimmed.fade_out(50)
        return trimmed if len(trimmed) >= 100 else seg
    except Exception:
        return seg


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
            track_layout = self.config.get("track_layout", "single")

            # 볼륨 커스텀 설정 읽기 (선형 % -> dB 변환)
            bgm_vol_pct = self.config.get("bgm_vol_pct", 70)
            sig_vol_pct = self.config.get("sig_vol_pct", 120)
            voice_vol_pct = self.config.get("voice_vol_pct", 130)
            duck_db = self.config.get("duck_db", -8.0)

            bgm_vol_db = vol_pct_to_db(bgm_vol_pct)
            sig_vol_db = vol_pct_to_db(sig_vol_pct)
            voice_vol_db = vol_pct_to_db(voice_vol_pct)

            # 트랙 할당 (single: 트랙 2에 멘트+신호음 순차 정렬, split: 트랙 2=신호음, 트랙 3=멘트)
            if track_layout == "single":
                sig_track = 1
                voice_track = 1
                cd_track = 1
            else:
                sig_track = 1
                voice_track = 2
                cd_track = 2

            # 1. 신호음 및 카운트다운/벨 에셋 로드
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

            # 2. 단계별 음성 멘트 및 사전 안내 방송 생성
            intro_enabled = self.config.get("intro_enabled", True)
            intro_text = self.config.get("intro_text", "").strip()
            cue_style = self.config.get("cue_style", "auto")
            duck_mode = self.config.get("duck_mode", "voice_only")

            voice_durations = {}
            voice_files = {}
            voice_texts = {}
            os.makedirs(os.path.join("projects", "temp_tts"), exist_ok=True)

            is_female = "여성" in voice_speaker or "선히" in voice_speaker
            voice_id = "ko-KR-SunHiNeural"
            if "인준" in voice_speaker:
                voice_id = "ko-KR-InJoonNeural"
            elif "현수" in voice_speaker:
                voice_id = "ko-KR-HyunsuMultilingualNeural"
            en_voice = "en-US-JennyNeural" if is_female else "en-US-GuyNeural"

            import edge_tts
            import io

            # 신호음 명칭 식별 (비프음 / 휘슬 / 북)
            sig_name = "신호음"
            if signal_type == "whistle":
                sig_name = "휘슬"
            elif signal_type == "drum":
                sig_name = "북"
            elif signal_type == "beep":
                sig_name = "비프음"

            # A. 출발 전 준비 안내 방송 생성
            intro_file = ""
            intro_duration = 0.0

            if intro_enabled:
                self.progress.emit(10, "사전 안내 및 출발 준비 음성 생성 중...")
                prep_instruction = f"이제 시작하겠습니다. 준비해 주세요. {sig_name} 소리에 맞춰 출발해 주세요."
                if intro_text:
                    full_prep_text = f"{intro_text} {prep_instruction}".strip()
                else:
                    full_prep_text = prep_instruction

                intro_path = os.path.join("projects", "temp_tts", f"shuttle_prep_{uuid.uuid4().hex[:6]}.wav")
                try:
                    async def _gen_intro():
                        comm = edge_tts.Communicate(full_prep_text, voice_id, rate="+15%")
                        buf = io.BytesIO()
                        async for chunk in comm.stream():
                            if chunk['type'] == 'audio':
                                buf.write(chunk['data'])
                        buf.seek(0)
                        raw_seg = AudioSegment.from_file(buf, format="mp3")
                        trimmed_seg = trim_audio_silence(raw_seg)
                        trimmed_seg.export(intro_path, format="wav")

                    asyncio.run(_gen_intro())
                    if os.path.exists(intro_path):
                        intro_duration = len(AudioSegment.from_file(intro_path)) / 1000.0
                        intro_file = intro_path
                except Exception as e_intro:
                    print(f"[Shuttle] Prep TTS fail: {e_intro}")
                    if os.name == 'posix':
                        try:
                            import subprocess
                            tmp_aiff = intro_path.replace(".wav", ".aiff")
                            res = subprocess.run(["say", "-v", "Yuna", "-o", tmp_aiff, full_prep_text], check=False, timeout=10)
                            if res.returncode == 0 and os.path.exists(tmp_aiff):
                                seg = trim_audio_silence(AudioSegment.from_file(tmp_aiff))
                                seg.export(intro_path, format="wav")
                                if os.path.exists(tmp_aiff):
                                    os.remove(tmp_aiff)
                                intro_duration = len(AudioSegment.from_file(intro_path)) / 1000.0
                                intro_file = intro_path
                        except Exception as e_say_intro:
                            print(f"[Shuttle] Intro say fallback fail: {e_say_intro}")

            # B. 카운트다운 생성 (템플릿: 영어 321, 비프음, 한국어 준비, 영어 준비, 한국어 321)
            cd_file = ""
            cd_duration = 0.0
            cd_clip_text = "[카운트다운] Three, Two, One"

            if countdown_enabled:
                cd_style = self.config.get("countdown_style", "en_321")

                # Helper for word-by-word stepped countdown with 1.5s (1500ms) delay
                async def _synth_stepped_cd(words: list, voice: str, rate: str = "+0%") -> AudioSegment:
                    silence_gap = AudioSegment.silent(duration=1500)
                    segs = []
                    for w in words:
                        seg = None
                        for attempt in range(2):
                            try:
                                comm = edge_tts.Communicate(w, voice, rate=rate)
                                buf = io.BytesIO()
                                async for chunk in comm.stream():
                                    if chunk['type'] == 'audio':
                                        buf.write(chunk['data'])
                                buf.seek(0)
                                raw_seg = AudioSegment.from_file(buf, format="mp3")
                                seg = trim_audio_silence(raw_seg)
                                break
                            except Exception:
                                await asyncio.sleep(0.15)
                        if seg is None and os.name == 'posix':
                            try:
                                import subprocess
                                tmp_aiff = os.path.join("projects", "temp_tts", f"cd_word_{uuid.uuid4().hex[:4]}.aiff")
                                say_voice = "Yuna" if "ko" in voice else "Samantha"
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
                    self.progress.emit(12, "전자 비프음 카운트다운(3박자 띡-띡-띡) 준비 중...")
                    ensure_default_effects()
                    cd_beeps_path = os.path.join("effects", "countdown_beeps.wav")
                    if os.path.exists(cd_beeps_path):
                        cd_duration = len(AudioSegment.from_file(cd_beeps_path)) / 1000.0
                        cd_file = cd_beeps_path
                        cd_clip_text = "[카운트다운] 전자 비프음 3회 (띡-띡-띡)"
                elif cd_style == "en_ready":
                    self.progress.emit(12, "영어 스포츠 카운트다운('Are you ready? Ready! Three, Two, One') 1.5초 간격 생성 중...")
                    cd_path = os.path.join("projects", "temp_tts", f"shuttle_cd_en_ready_{uuid.uuid4().hex[:6]}.wav")
                    cd_clip_text = "[카운트다운] Are you ready? Ready! Three, Two, One (영어 본토 발음)"
                    try:
                        async def _gen_cd():
                            full_seg = await _synth_stepped_cd(["Are you ready? Ready!", "Three", "Two", "One"], en_voice, rate="+5%")
                            full_seg.export(cd_path, format="wav")

                        asyncio.run(_gen_cd())
                        if os.path.exists(cd_path):
                            cd_duration = len(AudioSegment.from_file(cd_path)) / 1000.0
                            cd_file = cd_path
                    except Exception as e_cd:
                        print(f"[Shuttle] Countdown TTS fail: {e_cd}")
                elif cd_style == "ko_ready":
                    self.progress.emit(12, "한국어 친근한 카운트다운('준비되었나요? 준비! 셋, 둘, 하나') 1.5초 간격 생성 중...")
                    cd_path = os.path.join("projects", "temp_tts", f"shuttle_cd_ko_ready_{uuid.uuid4().hex[:6]}.wav")
                    cd_clip_text = "[카운트다운] 준비되었나요? 준비! 셋, 둘, 하나"
                    try:
                        async def _gen_cd():
                            full_seg = await _synth_stepped_cd(["준비되었나요? 준비!", "셋", "둘", "하나"], voice_id, rate="+5%")
                            full_seg.export(cd_path, format="wav")

                        asyncio.run(_gen_cd())
                        if os.path.exists(cd_path):
                            cd_duration = len(AudioSegment.from_file(cd_path)) / 1000.0
                            cd_file = cd_path
                    except Exception as e_cd:
                        print(f"[Shuttle] Countdown TTS fail: {e_cd}")
                elif cd_style == "ko_321":
                    self.progress.emit(12, "한국어 카운트다운('셋, 둘, 하나') 1.5초 간격 생성 중...")
                    cd_path = os.path.join("projects", "temp_tts", f"shuttle_cd_ko_321_{uuid.uuid4().hex[:6]}.wav")
                    cd_clip_text = "[카운트다운] 셋, 둘, 하나"
                    try:
                        async def _gen_cd():
                            full_seg = await _synth_stepped_cd(["셋", "둘", "하나"], voice_id, rate="+5%")
                            full_seg.export(cd_path, format="wav")

                        asyncio.run(_gen_cd())
                        if os.path.exists(cd_path):
                            cd_duration = len(AudioSegment.from_file(cd_path)) / 1000.0
                            cd_file = cd_path
                    except Exception as e_cd:
                        print(f"[Shuttle] Countdown TTS fail: {e_cd}")
                else:  # en_321 기본값
                    self.progress.emit(12, "영어 카운트다운('Three, Two, One' 본토 발음) 1.5초 간격 생성 중...")
                    cd_path = os.path.join("projects", "temp_tts", f"shuttle_cd_en_321_{uuid.uuid4().hex[:6]}.wav")
                    cd_clip_text = "[카운트다운] Three, Two, One (영어 본토 발음)"
                    try:
                        async def _gen_cd():
                            full_seg = await _synth_stepped_cd(["Three", "Two", "One"], en_voice, rate="+5%")
                            full_seg.export(cd_path, format="wav")

                        asyncio.run(_gen_cd())
                        if os.path.exists(cd_path):
                            cd_duration = len(AudioSegment.from_file(cd_path)) / 1000.0
                            cd_file = cd_path
                    except Exception as e_cd:
                        print(f"[Shuttle] Countdown TTS fail: {e_cd}")

                # 최후 폴백
                if not cd_file and countdown_audio:
                    cd_duration = len(countdown_audio) / 1000.0
                    cd_file = countdown_path

            # C. 단계별 구령 텍스트 맵 및 성우/배속 배정 ("시작" 단어 원천 제거 및 영어 본토 발음 지원)
            cue_voice = voice_id
            if cue_style == "en_level":
                cue_text_map = {s: f"Level {s}!" for s in range(1, target_stages + 1)}
                cue_rate = "+20%"
                cue_voice = en_voice
            elif cue_style == "en_num":
                en_num_words = {1: "One!", 2: "Two!", 3: "Three!", 4: "Four!", 5: "Five!", 6: "Six!", 7: "Seven!", 8: "Eight!", 9: "Nine!", 10: "Ten!", 11: "Eleven!", 12: "Twelve!", 13: "Thirteen!", 14: "Fourteen!", 15: "Fifteen!"}
                cue_text_map = {s: en_num_words.get(s, f"{s}!") for s in range(1, target_stages + 1)}
                cue_rate = "+25%"
                cue_voice = en_voice
            elif cue_style == "dan" or (cue_style == "auto" and distance <= 5.0):
                cue_text_map = {s: f"{s}단!" for s in range(1, target_stages + 1)}
                cue_rate = "+35%"
            elif cue_style == "num":
                cue_text_map = {s: f"{s}!" for s in range(1, target_stages + 1)}
                cue_rate = "+35%"
            else:  # stage (표준 단계) - "시작" 단어 완전 제거! 오직 "1단계!", "2단계!"로만 구령
                cue_text_map = {s: f"{s}단계!" for s in range(1, target_stages + 1)}
                cue_rate = "+20%"

            cue_cache_dir = os.path.join("projects", "temp_tts", "cue_cache")
            os.makedirs(cue_cache_dir, exist_ok=True)

            if use_voice:
                for st in range(1, target_stages + 1):
                    pct = 15 + int(35 * (st / target_stages))
                    text = cue_text_map[st]
                    self.progress.emit(pct, f"{st}단계 음성 구령 생성 중 ({text})...")

                    safe_cue_name = f"{cue_voice}_{cue_style}_{st}_{abs(hash(text))}.wav"
                    cached_cue_path = os.path.join(cue_cache_dir, safe_cue_name)
                    v_path = os.path.join("projects", "temp_tts", f"shuttle_stage_{st}_{uuid.uuid4().hex[:6]}.wav")

                    generated = False
                    if os.path.exists(cached_cue_path) and os.path.getsize(cached_cue_path) > 1000:
                        import shutil
                        shutil.copy(cached_cue_path, v_path)
                        generated = True
                    else:
                        for attempt in range(3):
                            try:
                                async def _gen(t, v, p, r):
                                    comm = edge_tts.Communicate(t, v, rate=r)
                                    buf = io.BytesIO()
                                    async for chunk in comm.stream():
                                        if chunk['type'] == 'audio':
                                            buf.write(chunk['data'])
                                    buf.seek(0)
                                    raw_seg = AudioSegment.from_file(buf, format="mp3")
                                    trimmed_seg = trim_audio_silence(raw_seg)
                                    trimmed_seg.export(p, format="wav")

                                asyncio.run(_gen(text, cue_voice, v_path, cue_rate))
                                if os.path.exists(v_path) and os.path.getsize(v_path) > 500:
                                    generated = True
                                    import shutil
                                    shutil.copy(v_path, cached_cue_path)
                                    break
                            except Exception as e_voice:
                                print(f"[Shuttle] Edge-TTS direct fail (stage {st}, attempt {attempt+1}): {e_voice}")
                                import time
                                time.sleep(0.2)

                        if not generated and os.name == 'posix':
                            try:
                                import subprocess
                                tmp_aiff = v_path.replace(".wav", ".aiff")
                                say_voice = "Yuna" if "ko" in cue_voice else "Samantha"
                                res = subprocess.run(["say", "-v", say_voice, "-o", tmp_aiff, text], check=False, timeout=5)
                                if res.returncode == 0 and os.path.exists(tmp_aiff):
                                    seg = trim_audio_silence(AudioSegment.from_file(tmp_aiff))
                                    seg.export(v_path, format="wav")
                                    if os.path.exists(tmp_aiff):
                                        os.remove(tmp_aiff)
                                    generated = True
                                    import shutil
                                    shutil.copy(v_path, cached_cue_path)
                            except Exception as e_say:
                                print(f"[Shuttle] say fallback fail: {e_say}")

                    if generated and os.path.exists(v_path):
                        v_dur = len(AudioSegment.from_file(v_path)) / 1000.0
                        voice_durations[st] = v_dur
                        voice_files[st] = v_path
                        voice_texts[st] = text

            # 3. 셔틀런 단계별 타임스탬프 계산
            # 순서: [준비 안내] ➔ [카운트다운: 쓰리, 투, 원] ➔ (1초 딜레이) ➔ [1단계 구령] ➔ [첫 출발 신호음]
            self.progress.emit(55, "정밀 생체역학 및 비중복 순차 인터벌 스케줄 계산 중...")
            sig_dur = len(signal_audio) / 1000.0
            schedule = ShuttleRunEngine.calculate_stage_schedule(
                distance=distance,
                preset_key=preset_key,
                target_stages=target_stages,
                stage_duration_sec=60.0,
                start_delay_sec=5.0,
                stage_cue_durations=voice_durations if use_voice else None,
                countdown_duration=cd_duration,
                signal_duration_sec=sig_dur,
                cue_post_gap_sec=0.20 if distance <= 5.0 else 0.25,
                intro_duration_sec=intro_duration,
                countdown_delay_sec=1.0
            )

            # 4. 타임라인 클립 데이터 구성 (순차 배치 및 스마트 오토 덕킹 세그먼트 생성)
            self.progress.emit(65, "타임라인 트랙 데이터 구성 중...")
            timeline_clips = []
            duck_segments = []

            # A. 사전 안내 및 출발 준비 방송 클립
            if intro_file and intro_duration > 0:
                timeline_clips.append({
                    "text": f"[출발 준비] {sig_name} 소리에 맞춰 출발 안내",
                    "file": intro_file,
                    "time": 1.0,
                    "duration": intro_duration,
                    "track": voice_track,
                    "vol": voice_vol_db
                })
                if duck_mode in ("voice_only", "all") and auto_ducking:
                    duck_segments.append((1000, int((1.0 + intro_duration) * 1000)))

            s1 = schedule[0]

            # B. 카운트다운 클립
            if countdown_enabled and cd_file and s1.get("countdown_time_sec") is not None:
                cd_time = s1["countdown_time_sec"]
                timeline_clips.append({
                    "text": f"{cd_clip_text} (1초 후 1단계)",
                    "file": cd_file,
                    "time": cd_time,
                    "duration": cd_duration,
                    "track": cd_track,
                    "vol": sig_vol_db if cd_style == "beep" else voice_vol_db
                })
                if duck_mode in ("voice_only", "all") and auto_ducking:
                    duck_segments.append((int(cd_time * 1000), int((cd_time + cd_duration) * 1000)))

            # C. 1단계 시작 멘트 (1단계 / 1단) ➔ 바로 1단계 첫 비프음으로 연결!
            if use_voice and 1 in voice_files and s1.get("cue_time_sec") is not None:
                c_time = s1["cue_time_sec"]
                c_dur = s1["cue_duration_sec"]
                timeline_clips.append({
                    "text": f"[1단계 멘트] {voice_texts[1]}",
                    "file": voice_files[1],
                    "time": c_time,
                    "duration": c_dur,
                    "track": voice_track,
                    "vol": voice_vol_db
                })
                if duck_mode in ("voice_only", "all") and auto_ducking:
                    duck_segments.append((int(c_time * 1000), int((c_time + c_dur) * 1000)))

            # D. 단계별 신호음 및 2단계 이상 음성 구령
            for stage_info in schedule:
                st = stage_info["stage"]
                # 2단계 이상 안내 멘트 (또는 음성 없을 시 차임벨)
                if st > 1:
                    if use_voice and st in voice_files and stage_info.get("cue_time_sec") is not None:
                        c_time = stage_info["cue_time_sec"]
                        c_dur = stage_info["cue_duration_sec"]
                        timeline_clips.append({
                            "text": f"[{st}단계 멘트] {voice_texts[st]}",
                            "file": voice_files[st],
                            "time": c_time,
                            "duration": c_dur,
                            "track": voice_track,
                            "vol": voice_vol_db
                        })
                        if duck_mode in ("voice_only", "all") and auto_ducking:
                            duck_segments.append((int(c_time * 1000), int((c_time + c_dur) * 1000)))
                    elif not use_voice and stage_bell_audio:
                        bell_time = max(0.0, stage_info["stage_start_sec"] - 1.2)
                        timeline_clips.append({
                            "text": f"[{st}단계] 딩동 차임벨",
                            "file": stage_bell_path,
                            "time": bell_time,
                            "duration": len(stage_bell_audio) / 1000.0,
                            "track": sig_track,
                            "vol": sig_vol_db
                        })
                        if duck_mode in ("voice_only", "all") and auto_ducking:
                            duck_segments.append((int(bell_time * 1000), int((bell_time + len(stage_bell_audio) / 1000.0) * 1000)))

                # 비프/휘슬 신호음들
                sig_dur = len(signal_audio) / 1000.0
                total_beeps = len(stage_info["beeps"])
                for b_idx, b_time in enumerate(stage_info["beeps"]):
                    if st == 1:
                        if b_idx == 0:
                            lbl = f"[{st}단계-출발] 신호음"
                        elif b_idx == total_beeps - 1:
                            lbl = f"[{st}단계-{b_idx}회 완주] 신호음"
                        else:
                            lbl = f"[{st}단계-{b_idx}회] 신호음"
                    else:
                        shuttle_num = b_idx + 1
                        if shuttle_num == stage_info["shuttles"]:
                            lbl = f"[{st}단계-{shuttle_num}회 완주] 신호음"
                        else:
                            lbl = f"[{st}단계-{shuttle_num}회] 신호음"

                    timeline_clips.append({
                        "text": lbl,
                        "file": sig_path,
                        "time": b_time,
                        "duration": sig_dur,
                        "track": sig_track,
                        "vol": sig_vol_db
                    })
                    # 전체 덕킹(all)일 때만 비프음에 덕킹 적용! 스마트 덕킹(voice_only) 모드에서는 비프음 덕킹을 생략하여 음악이 끊김 없이 매끄럽게 흐름!
                    if duck_mode == "all" and auto_ducking:
                        s_ms = int(b_time * 1000)
                        e_ms = s_ms + int(sig_dur * 1000) + 120
                        duck_segments.append((s_ms, e_ms))

            # 클립들을 시간 순서대로 정렬 (타임라인 상 논리적 순서 보장)
            timeline_clips.sort(key=lambda x: x["time"])

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
        self.rb_dist_5 = QRadioButton("5m (초소형/스텝)")
        self.rb_dist_10 = QRadioButton("10m (도장 표준)")
        self.rb_dist_15 = QRadioButton("15m (중형 도장)")
        self.rb_dist_20 = QRadioButton("20m (체육관 공인)")
        self.rb_dist_10.setChecked(True)
        
        self.dist_btn_group.addButton(self.rb_dist_5, 5)
        self.dist_btn_group.addButton(self.rb_dist_10, 10)
        self.dist_btn_group.addButton(self.rb_dist_15, 15)
        self.dist_btn_group.addButton(self.rb_dist_20, 20)
        
        dist_layout.addWidget(self.rb_dist_5)
        dist_layout.addWidget(self.rb_dist_10)
        dist_layout.addWidget(self.rb_dist_15)
        dist_layout.addWidget(self.rb_dist_20)
        dist_group.setLayout(dist_layout)
        content_layout.addWidget(dist_group)

        # 2. 난이도 및 훈련 수준 선택 (4단계 수준별 시작 속도 및 턴 감속 적용)
        age_group = QGroupBox("2. 훈련 난이도 및 수준 선택 (수준별 시작 속도 및 턴 감속 자동 연동)")
        age_layout = QVBoxLayout()
        self.age_btn_group = QButtonGroup(self)
        self.rb_level_beginner = QRadioButton("🌱 초급 (생활체육 · 유치부 · 일반회원 취미반)  ➔ 6.0 km/h 시작, 턴 0.85초 (가장 여유롭고 안전함)")
        self.rb_level_intermediate = QRadioButton("🏃 일반선수 (초등학생 표준 · 생활체육 숙련)    ➔ 7.2 km/h 시작, 턴 0.65초 (표준 도장 체력 훈련)")
        self.rb_level_advanced = QRadioButton("🥋 전문선수 (선수부 · 중고등부 · 체대입시반)    ➔ 8.0 km/h 시작, 턴 0.50초 (고강도 시합 대비)")
        self.rb_level_pro = QRadioButton("🏆 프로선수 (공인 규격 페이서 · 엘리트 마스터) ➔ 8.5 km/h 시작, 턴 0.45초 (PAPS 공인 만점 도전)")
        self.rb_level_intermediate.setChecked(True)

        self.age_btn_group.addButton(self.rb_level_beginner, 1)
        self.age_btn_group.addButton(self.rb_level_intermediate, 2)
        self.age_btn_group.addButton(self.rb_level_advanced, 3)
        self.age_btn_group.addButton(self.rb_level_pro, 4)

        age_layout.addWidget(self.rb_level_beginner)
        age_layout.addWidget(self.rb_level_intermediate)
        age_layout.addWidget(self.rb_level_advanced)
        age_layout.addWidget(self.rb_level_pro)
        age_group.setLayout(age_layout)
        content_layout.addWidget(age_group)

        # 실시간 거리/인터벌/회전수 계산 미리보기 배너
        self.lbl_interval_preview = QLabel()
        self.lbl_interval_preview.setStyleSheet(
            "background-color: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 6px; "
            "padding: 8px 12px; font-weight: bold; color: #065f46; font-size: 13px;"
        )
        content_layout.addWidget(self.lbl_interval_preview)

        self.dist_btn_group.idToggled.connect(lambda: self.update_interval_preview())
        self.age_btn_group.idToggled.connect(lambda: self.update_interval_preview())

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
        vol_group = QGroupBox("6. 🎚️ 개별 음량(BGM / 비프음 / TTS) 및 스마트 오토덕킹 커스텀")
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

        # 덕킹 모드 & 강도 & 프리셋
        h_v4 = QHBoxLayout()
        h_v4.addWidget(QLabel("📉 덕킹 방식:"))
        self.combo_duck_mode = QComboBox()
        self.combo_duck_mode.addItem("🌟 스마트 덕킹 (음성 구령 시에만 살짝 감쇄, 비프음은 음악 유지 - 강력 추천)", "voice_only")
        self.combo_duck_mode.addItem("🎵 덕킹 끄기 (0 dB 감쇄 없음 - 음악 끊김 없이 원본 유지)", "none")
        self.combo_duck_mode.addItem("📉 전체 덕킹 (음성 구령 및 비프음 모두 감쇄)", "all")
        h_v4.addWidget(self.combo_duck_mode, stretch=1)
        vol_layout.addLayout(h_v4)

        h_v5 = QHBoxLayout()
        h_v5.addWidget(QLabel("📉 덕킹 감쇄량:"))
        self.combo_duck_level = QComboBox()
        self.combo_duck_level.addItem("부드러운 감쇄 (-4 dB) - 음악 비트 유지 [추천]", -4.0)
        self.combo_duck_level.addItem("보통 감쇄 (-6 dB)", -6.0)
        self.combo_duck_level.addItem("강한 감쇄 (-10 dB) - 구령 집중", -10.0)
        self.combo_duck_level.addItem("약한 감쇄 (-2 dB) - 아주 미세하게", -2.0)
        h_v5.addWidget(self.combo_duck_level)

        btn_preset_default = QPushButton("기본 밸런스")
        btn_preset_music = QPushButton("음악 중심 (덕킹X)")
        btn_preset_voice = QPushButton("구령·신호 극대화")
        btn_preset_default.clicked.connect(lambda: self.set_vol_preset(70, 120, 130, 0, 0))
        btn_preset_music.clicked.connect(lambda: self.set_vol_preset(90, 130, 120, 1, 0))
        btn_preset_voice.clicked.connect(lambda: self.set_vol_preset(50, 160, 160, 2, 2))
        h_v5.addWidget(btn_preset_default)
        h_v5.addWidget(btn_preset_music)
        h_v5.addWidget(btn_preset_voice)
        vol_layout.addLayout(h_v5)

        vol_group.setLayout(vol_layout)
        content_layout.addWidget(vol_group)

        # 7. 음성 안내, 사전 설명 방송 및 구령 스타일
        opt_group = QGroupBox("7. 🗣️ 음성 안내, 셔틀런 방법 사전 설명 및 구령 스타일")
        opt_layout = QVBoxLayout()
        
        # 사전 안내 방송 체크박스 및 문구 선택
        self.cb_intro_guide = QCheckBox("🏃‍♂️ 심폐지구력 셔틀런 사전 안내 방송 포함 (달리기 방법 및 요령 설명 후 시작)")
        self.cb_intro_guide.setChecked(True)
        self.cb_intro_guide.setStyleSheet("font-weight: bold; color: #1e3a8a;")
        opt_layout.addWidget(self.cb_intro_guide)

        h_intro = QHBoxLayout()
        h_intro.addWidget(QLabel("  📋 안내 방송 문구:"))
        self.combo_intro_style = QComboBox()
        self.combo_intro_style.addItem(
            "🏆 도장 표준 안내 (방법 및 호흡 요령 - 약 11초)",
            "지금부터 심폐지구력 향상을 위한 왕복 오래달리기, 셔틀런을 시작합니다. 신호음이 울리면 반대편으로 달리고, 다음 신호음이 울리기 전에 반대편 선에 도착해야 합니다. 모두 준비하시고, 출발 신호에 맞춰 출발하세요!"
        )
        self.combo_intro_style.addItem(
            "⚡ 초간결 안내 (빠른 시작 - 약 5초)",
            "지금부터 심폐지구력 셔틀런 측정을 시작합니다. 신호음에 맞춰 반대편으로 왕복 달립니다. 준비하세요!"
        )
        h_intro.addWidget(self.combo_intro_style, stretch=1)
        opt_layout.addLayout(h_intro)

        # 시작 전 카운트다운 템플릿 선택 및 안내
        h_cd = QHBoxLayout()
        self.cb_countdown = QCheckBox("시작 전 카운트다운:")
        self.cb_countdown.setChecked(True)
        self.cb_countdown.setStyleSheet("font-weight: bold; color: #1e3a8a;")

        self.combo_countdown_style = QComboBox()
        self.combo_countdown_style.addItem("🇺🇸 영어 카운트다운 ('Three, Two, One' - 본토 원어민 발음)", "en_321")
        self.combo_countdown_style.addItem("🔔 전자 비프음 (띡, 띡, 띡 - 신호음 3박자)", "beep")
        self.combo_countdown_style.addItem("🇰🇷 한국어 친근한 멘트 ('준비되었나요? 준비! 셋, 둘, 하나')", "ko_ready")
        self.combo_countdown_style.addItem("🇺🇸 영어 스포츠 멘트 ('Are you ready? Ready! Three, Two, One' - 본토 발음)", "en_ready")
        self.combo_countdown_style.addItem("🇰🇷 한국어 정통 카운트다운 ('셋, 둘, 하나')", "ko_321")
        self.combo_countdown_style.setStyleSheet("font-weight: 500;")

        btn_preview_cd = QPushButton("🎧 카운트다운 미리듣기")
        btn_preview_cd.clicked.connect(self.preview_countdown_sound)

        h_cd.addWidget(self.cb_countdown)
        h_cd.addWidget(self.combo_countdown_style, stretch=1)
        h_cd.addWidget(btn_preview_cd)
        opt_layout.addLayout(h_cd)

        # 실전 출발 시퀀스 안내 배너 (선택 템플릿에 따라 실시간 문구 갱신)
        self.seq_banner = QLabel()
        self.seq_banner.setStyleSheet("background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px; padding: 6px 10px; font-weight: bold; color: #166534; font-size: 11px;")
        opt_layout.addWidget(self.seq_banner)

        self.combo_countdown_style.currentIndexChanged.connect(self.update_countdown_banner)
        self.cb_countdown.toggled.connect(self.update_countdown_banner)

        # 단계 구령 및 성우
        h_voice = QHBoxLayout()
        self.cb_voice = QCheckBox("단계 상승 시 음성 구령 송출")
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

        # 구령 스타일 선택 (한국어 표준 단계 기본값, 영어 Level 1, One, 1단 등)
        h_cue_style = QHBoxLayout()
        h_cue_style.addWidget(QLabel("  🥋 구령 스타일:"))
        self.combo_cue_style = QComboBox()
        self.combo_cue_style.addItem("📢 한국어 표준 단계 ('1단계!', '2단계!' - 시작 단어 제외)", "stage")
        self.combo_cue_style.addItem("🥋 한국어 초간결 단 ('1단!', '2단!', '3단!') - 5m 단거리 추천", "dan")
        self.combo_cue_style.addItem("🔢 한국어 초미니멀 숫자 ('1!', '2!', '3!') - 0.25초 순간 구령", "num")
        self.combo_cue_style.addItem("🇺🇸 영어 레벨 ('Level 1!', 'Level 2!' - 미국 본토 발음)", "en_level")
        self.combo_cue_style.addItem("🇺🇸 영어 숫자 ('One!', 'Two!', 'Three!' - 본토 발음)", "en_num")

        btn_preview_cue = QPushButton("🎧 구령 미리듣기")
        btn_preview_cue.clicked.connect(self.preview_cue_sound)

        h_cue_style.addWidget(self.combo_cue_style, stretch=1)
        h_cue_style.addWidget(btn_preview_cue)
        opt_layout.addLayout(h_cue_style)

        self.cb_intro_guide.toggled.connect(self.combo_intro_style.setEnabled)
        self.cb_intro_guide.toggled.connect(self.update_countdown_banner)

        lbl_voice_info = QLabel("💡 5m 단거리는 '1단!', '2단!' 또는 '1!', '2!'로 설정하시면 빠른 배속(+35%)으로 신호음 간격에 완벽히 들어맞습니다.")
        lbl_voice_info.setStyleSheet("color: #0369a1; font-size: 11px; padding-left: 20px; font-weight: 500;")
        opt_layout.addWidget(lbl_voice_info)

        h_track = QHBoxLayout()
        h_track.addWidget(QLabel("🎛️ 타임라인 트랙 배치:"))
        self.combo_track_layout = QComboBox()
        self.combo_track_layout.addItem("단일 훈련 트랙 (트랙 2에 신호음+멘트 한 줄 순차 배치 - 시각적 혼동 방지 [추천])", "single")
        self.combo_track_layout.addItem("트랙 분리 (트랙 2: 신호음 / 트랙 3: 멘트 - 개별 볼륨 조정)", "split")
        h_track.addWidget(self.combo_track_layout, stretch=1)
        opt_layout.addLayout(h_track)

        self.cb_ducking = QCheckBox("🎵 BGM 오토 덕킹(Auto-Ducking) 활성화")
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

        # 초기 계산 미리보기 업데이트
        self.update_interval_preview()
        self.update_countdown_banner()

    def update_interval_preview(self):
        """거리/연령 선택 변경 시 1단계 인터벌(초)과 회전수를 실시간 계산하여 안내"""
        try:
            dist_val = float(self.dist_btn_group.checkedId())
            age_id = self.age_btn_group.checkedId()
            preset_map = {1: "beginner", 2: "intermediate", 3: "advanced", 4: "pro"}
            preset_key = preset_map.get(age_id, "intermediate")

            schedule = ShuttleRunEngine.calculate_stage_schedule(
                distance=dist_val,
                preset_key=preset_key,
                target_stages=1,
                stage_duration_sec=60.0
            )
            if schedule and hasattr(self, 'lbl_interval_preview'):
                s1 = schedule[0]
                spd = s1["speed_kmh"]
                iv = s1["interval_sec"]
                cnt = s1["shuttles"]
                tot_m = int(cnt * dist_val)
                self.lbl_interval_preview.setText(
                    f"⚡ [물리학적 계산 결과] 선택한 {int(dist_val)}m 거리 1단계 ({spd} km/h):\n"
                    f"   ➔ {iv:.2f}초 간격 비프음 | 1분간 총 {cnt}회 왕복 (총 주행 거리 {tot_m}m)"
                )
            # 5m 초단거리 선택 시 구령 스타일을 '1단!', '2단!'으로 자동 추천 세팅
            if dist_val <= 5.0 and hasattr(self, 'combo_cue_style'):
                idx = self.combo_cue_style.findData("dan")
                if idx >= 0:
                    self.combo_cue_style.setCurrentIndex(idx)
        except Exception:
            pass

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

    def update_countdown_banner(self):
        if not hasattr(self, 'seq_banner'):
            return
        intro_on = self.cb_intro_guide.isChecked() if hasattr(self, 'cb_intro_guide') else True
        cd_on = self.cb_countdown.isChecked() if hasattr(self, 'cb_countdown') else True
        self.combo_countdown_style.setEnabled(cd_on)
        if hasattr(self, 'combo_intro_style'):
            self.combo_intro_style.setEnabled(intro_on)

        intro_part = "[준비 안내: 신호음 소리에 맞춰 출발!] ➔ " if intro_on else ""

        if not cd_on:
            self.seq_banner.setText(f"🎯 1단계 출발 순서: {intro_part}[1단계!] ➔ [첫 출발 신호음(삑!)]")
            return

        style = self.combo_countdown_style.currentData()
        style_desc_map = {
            "en_321": "🇺🇸 Three, Two, One (본토 영어 발음)",
            "beep": "🔔 전자 비프음 3회 (띡-띡-띡)",
            "ko_ready": "🇰🇷 준비되었나요? 준비! 셋, 둘, 하나",
            "en_ready": "🇺🇸 Are you ready? Ready! Three, Two, One (본토 발음)",
            "ko_321": "🇰🇷 셋, 둘, 하나",
        }
        cd_desc = style_desc_map.get(style, "🇺🇸 Three, Two, One")
        self.seq_banner.setText(
            f"🎯 1단계 출발 순서: {intro_part}[{cd_desc}] ➔ (1초 딜레이) ➔ [1단계!] ➔ [첫 출발 신호음(삑!)]"
        )

    def _quick_tts_export(self, text: str, voice: str, out_path: str, rate: str = "+0%"):
        try:
            import edge_tts
            import asyncio
            os.makedirs(os.path.dirname(out_path), exist_ok=True)

            async def _run():
                comm = edge_tts.Communicate(text, voice, rate=rate)
                buf = io.BytesIO()
                async for chunk in comm.stream():
                    if chunk['type'] == 'audio':
                        buf.write(chunk['data'])
                buf.seek(0)
                raw_seg = AudioSegment.from_file(buf, format="mp3")
                trimmed_seg = trim_audio_silence(raw_seg)
                trimmed_seg.export(out_path, format="wav")

            asyncio.run(_run())
        except Exception as e:
            print(f"[Preview] TTS fail: {e}")

    def preview_countdown_sound(self):
        style = self.combo_countdown_style.currentData()
        speaker = self.voice_combo.currentText()
        is_female = "여성" in speaker or "선히" in speaker

        if style == "beep":
            file_path = os.path.join("effects", "countdown_beeps.wav")
            if not os.path.exists(file_path):
                ensure_default_effects()
        elif style == "en_ready":
            en_voice = "en-US-JennyNeural" if is_female else "en-US-GuyNeural"
            file_path = os.path.join("projects", "temp_tts", f"preview_cd_en_ready_{'female' if is_female else 'male'}.wav")
            if not os.path.exists(file_path):
                self._quick_tts_export("Are you ready? Ready! Three, Two, One.", en_voice, file_path, rate="+10%")
        elif style == "ko_ready":
            voice_id = "ko-KR-SunHiNeural" if is_female else "ko-KR-InJoonNeural"
            file_path = os.path.join("projects", "temp_tts", f"preview_cd_ko_ready_{voice_id}.wav")
            if not os.path.exists(file_path):
                self._quick_tts_export("준비되었나요? 준비! 셋, 둘, 하나.", voice_id, file_path, rate="+10%")
        elif style == "ko_321":
            voice_id = "ko-KR-SunHiNeural" if is_female else "ko-KR-InJoonNeural"
            file_path = os.path.join("projects", "temp_tts", f"preview_cd_ko_321_{voice_id}.wav")
            if not os.path.exists(file_path):
                self._quick_tts_export("셋, 둘, 하나.", voice_id, file_path, rate="+10%")
        else:  # en_321
            en_voice = "en-US-JennyNeural" if is_female else "en-US-GuyNeural"
            file_path = os.path.join("projects", "temp_tts", f"preview_cd_en_321_{'female' if is_female else 'male'}.wav")
            if not os.path.exists(file_path):
                self._quick_tts_export("Three, Two, One.", en_voice, file_path, rate="+10%")

        if os.path.exists(file_path):
            try:
                import pygame
                pygame.mixer.init()
                sound = pygame.mixer.Sound(file_path)
                sound.play()
            except Exception as e:
                QMessageBox.warning(self, "미리듣기 실패", f"카운트다운 재생 실패: {e}")

    def preview_cue_sound(self):
        style = self.combo_cue_style.currentData()
        speaker = self.voice_combo.currentText()
        is_female = "여성" in speaker or "선히" in speaker
        en_voice = "en-US-JennyNeural" if is_female else "en-US-GuyNeural"
        ko_voice = "ko-KR-SunHiNeural" if is_female else "ko-KR-InJoonNeural"

        if style == "en_level":
            file_path = os.path.join("projects", "temp_tts", f"preview_cue_level_{'female' if is_female else 'male'}.wav")
            if not os.path.exists(file_path):
                self._quick_tts_export("Level 1!", en_voice, file_path, rate="+20%")
        elif style == "en_num":
            file_path = os.path.join("projects", "temp_tts", f"preview_cue_ennum_{'female' if is_female else 'male'}.wav")
            if not os.path.exists(file_path):
                self._quick_tts_export("One!", en_voice, file_path, rate="+25%")
        elif style == "dan":
            file_path = os.path.join("projects", "temp_tts", f"preview_cue_dan_{ko_voice}.wav")
            if not os.path.exists(file_path):
                self._quick_tts_export("1단!", ko_voice, file_path, rate="+35%")
        elif style == "num":
            file_path = os.path.join("projects", "temp_tts", f"preview_cue_num_{ko_voice}.wav")
            if not os.path.exists(file_path):
                self._quick_tts_export("1!", ko_voice, file_path, rate="+35%")
        else:  # stage
            file_path = os.path.join("projects", "temp_tts", f"preview_cue_stage_{ko_voice}.wav")
            if not os.path.exists(file_path):
                self._quick_tts_export("1단계!", ko_voice, file_path, rate="+20%")

        if os.path.exists(file_path):
            try:
                import pygame
                pygame.mixer.init()
                sound = pygame.mixer.Sound(file_path)
                sound.play()
            except Exception as e:
                QMessageBox.warning(self, "미리듣기 실패", f"구령 재생 실패: {e}")

    def set_vol_preset(self, bgm: int, sig: int, voice: int, duck_mode_idx: int, duck_idx: int):
        self.slider_bgm_vol.setValue(bgm)
        self.slider_sig_vol.setValue(sig)
        self.slider_voice_vol.setValue(voice)
        if hasattr(self, 'combo_duck_mode'):
            self.combo_duck_mode.setCurrentIndex(duck_mode_idx)
        if hasattr(self, 'combo_duck_level'):
            self.combo_duck_level.setCurrentIndex(duck_idx)

    def start_generation(self):
        dist_val = self.dist_btn_group.checkedId()
        age_id = self.age_btn_group.checkedId()
        preset_map = {1: "beginner", 2: "intermediate", 3: "advanced", 4: "pro"}
        preset_key = preset_map.get(age_id, "intermediate")

        duck_db_val = self.combo_duck_level.currentData()
        if duck_db_val is None:
            duck_db_val = -4.0

        duck_mode_val = self.combo_duck_mode.currentData() if hasattr(self, 'combo_duck_mode') else "voice_only"
        intro_enabled_val = self.cb_intro_guide.isChecked() if hasattr(self, 'cb_intro_guide') else True
        intro_text_val = self.combo_intro_style.currentData() if hasattr(self, 'combo_intro_style') else ""
        cue_style_val = self.combo_cue_style.currentData() if hasattr(self, 'combo_cue_style') else "auto"

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
            "countdown_style": self.combo_countdown_style.currentData(),
            "track_layout": self.combo_track_layout.currentData(),
            "bgm_vol_pct": self.slider_bgm_vol.value(),
            "sig_vol_pct": self.slider_sig_vol.value(),
            "voice_vol_pct": self.slider_voice_vol.value(),
            "duck_db": duck_db_val,
            "duck_mode": duck_mode_val,
            "intro_enabled": intro_enabled_val,
            "intro_text": intro_text_val,
            "cue_style": cue_style_val
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
            self.generated_result["track_layout"] = self.combo_track_layout.currentData()
            self.status_lbl.setText("✅ 셔틀런 음원 생성 완료!")
            
            # 사용자에게 로드 및 저장 옵션 제공
            layout_desc = "단일 훈련 트랙 (트랙 2에 신호음+구령 순차 정렬)" if self.combo_track_layout.currentData() == "single" else "트랙 분리 (트랙 2: 신호음, 트랙 3: 구령)"
            reply = QMessageBox.question(
                self,
                "셔틀런 음원 생성 완료",
                "🎉 실내 셔틀런 음원이 성공적으로 생성되었습니다!\n\n"
                f"- 총 거리: {result_data['distance']}m\n"
                f"- 총 단계: {result_data['target_stages']}단계 (소요 시간: 약 {int(result_data['total_duration_sec']//60)}분 {int(result_data['total_duration_sec']%60)}초)\n"
                f"- 트랙 배치: {layout_desc}\n\n"
                "지금 바로 음악 편집기 타임라인에 로드하시겠습니까?\n"
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
