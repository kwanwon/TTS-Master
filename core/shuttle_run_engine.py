"""
Shuttle Run Generator Core Logic
Accurately computes interval schedules based on biomechanics/physics formulas:
  T_interval = (Distance / Velocity) + T_turn
Generates mixed tracks, handles auto-ducking for background music, and emits timeline clips.
"""

import os
import math
import uuid
from typing import List, Dict, Any, Optional
from pydub import AudioSegment
from pydub.effects import normalize


class ShuttleRunEngine:
    # 4-tier skill level presets: starting speed (km/h), speed increase per level (km/h), turn deceleration (seconds)
    PRESETS = {
        "beginner": {
            "name": "🌱 초급 (생활체육 · 유치부 · 일반회원)",
            "start_speed": 6.0,
            "speed_inc": 0.5,
            "turn_time": 0.85,
            "desc": "6.0 km/h 시작 (턴 감속 0.85초 보정, 가장 여유롭고 안전함)"
        },
        "intermediate": {
            "name": "🏃 일반선수 (초등학생 표준 · 생활체육 숙련)",
            "start_speed": 7.2,
            "speed_inc": 0.5,
            "turn_time": 0.65,
            "desc": "7.2 km/h 시작 (턴 감속 0.65초 보정, 표준 도장 체력 훈련)"
        },
        "advanced": {
            "name": "🥋 전문선수 (선수부 · 중고등부 · 체대입시반)",
            "start_speed": 8.0,
            "speed_inc": 0.5,
            "turn_time": 0.50,
            "desc": "8.0 km/h 시작 (턴 감속 0.50초 보정, 고강도 시합 대비)"
        },
        "pro": {
            "name": "🏆 프로선수 (공인 규격 페이서 · 엘리트 마스터)",
            "start_speed": 8.5,
            "speed_inc": 0.5,
            "turn_time": 0.45,
            "desc": "8.5 km/h 시작 (턴 감속 0.45초 보정, PAPS 공인 만점 도전)"
        }
    }
    # Backward compatibility aliases
    PRESETS["kinder"] = PRESETS["beginner"]
    PRESETS["elementary_low"] = PRESETS["intermediate"]
    PRESETS["elementary_high_teen"] = PRESETS["pro"]

    DISTANCES = {
        5: {"name": "5m (실내 초소형)", "val": 5.0},
        10: {"name": "10m (실내 표준)", "val": 10.0},
        15: {"name": "15m (중형 도장)", "val": 15.0},
        20: {"name": "20m (야외 공인)", "val": 20.0}
    }

    @classmethod
    def calculate_stage_schedule(
        cls,
        distance: float,
        preset_key: str,
        target_stages: int = 8,
        stage_duration_sec: float = 60.0,
        start_delay_sec: float = 5.0,
        stage_cue_durations: Optional[Dict[int, float]] = None,
        countdown_duration: float = 0.0,
        countdown_delay_sec: float = 1.0,
        signal_duration_sec: float = 0.25,
        cue_post_gap_sec: float = 0.35,
        intro_duration_sec: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Calculates exact beep timestamps and voice cues for each stage.
        Guarantees strict sequential ordering:
          [Intro Guide] -> [Stage 1 Cue] -> [Countdown] -> [Beep 1-Start] -> ... -> [Beep 1-End] ->
          [Stage 2 Cue] -> [Beep 2-Start] -> ... -> [Beep 2-End]
        No overlaps occur between voice cues, countdowns, and beeps.
        """
        preset = cls.PRESETS.get(preset_key, cls.PRESETS["elementary_low"])
        start_speed = preset["start_speed"]
        speed_inc = preset["speed_inc"]
        turn_time = preset["turn_time"]

        schedule = []

        # 1단계 시작 타이밍 계산:
        # [준비 안내] ➔ [카운트다운: 3, 2, 1] ➔ [1.0초 긴장 딜레이] ➔ [1단계 구령] ➔ [첫 출발 신호음]
        intro_time = 1.0 if intro_duration_sec > 0 else None
        t_prep_end = (1.0 + intro_duration_sec) if intro_duration_sec > 0 else 0.5

        if countdown_duration > 0:
            cd_time = round(t_prep_end + 0.4, 2)
            t_cd_end = cd_time + countdown_duration
            cue_time_1 = round(t_cd_end + countdown_delay_sec, 2)
            cue_dur_1 = stage_cue_durations.get(1, 0.0) if stage_cue_durations else 0.0
            if cue_dur_1 > 0:
                stage_1_first_beep = round(cue_time_1 + cue_dur_1 + cue_post_gap_sec, 2)
            else:
                stage_1_first_beep = round(cue_time_1 + 0.25, 2)
        else:
            cd_time = None
            cue_dur_1 = stage_cue_durations.get(1, 0.0) if stage_cue_durations else 0.0
            if cue_dur_1 > 0:
                cue_time_1 = round(t_prep_end + 0.5, 2)
                stage_1_first_beep = round(cue_time_1 + cue_dur_1 + cue_post_gap_sec, 2)
            else:
                cue_time_1 = None
                stage_1_first_beep = round(t_prep_end + float(start_delay_sec), 2)

        last_beep = 0.0

        for s in range(1, target_stages + 1):
            speed_kmh = start_speed + (s - 1) * speed_inc
            speed_ms = speed_kmh / 3.6
            raw_interval = (distance / speed_ms) + turn_time
            interval_sec = round(raw_interval, 2)
            num_shuttles = max(1, int(round(stage_duration_sec / interval_sec)))

            if s == 1:
                stage_start = stage_1_first_beep
                stage_cue_time = cue_time_1
                stage_cue_dur = stage_cue_durations.get(1, 0.0) if stage_cue_durations else 0.0
                # 1단계: B_0(출발), B_1..B_num_shuttles(각 회차 도착 및 턴)
                beeps = []
                for b in range(num_shuttles + 1):
                    beep_time = round(stage_start + b * interval_sec, 2)
                    beeps.append(beep_time)
                stage_start_time = beeps[0]
                stage_end_time = beeps[-1]
                last_beep = beeps[-1]
            else:
                # 2단계 이상:
                # 1단계 마지막 완주 비프(last_beep)와 2단계 첫 도착 비프(last_beep + interval_sec) 사이의
                # 정확한 중간(center)에 "2단계!" 안내 멘트를 배치하여 스샷 3번처럼 가장 자연스러운 대칭 간격을 형성합니다.
                stage_cue_dur = stage_cue_durations.get(s, 0.0) if stage_cue_durations else 0.0
                if stage_cue_dur > 0:
                    center_time = last_beep + (interval_sec / 2.0)
                    calculated_cue_time = round(center_time - (stage_cue_dur / 2.0), 2)
                    # 앞뒤 비프음과 절대 겹치지 않도록 안전 여백 보장
                    min_cue_time = round(last_beep + signal_duration_sec + 0.35, 2)
                    max_cue_time = round((last_beep + interval_sec) - stage_cue_dur - 0.35, 2)
                    if max_cue_time >= min_cue_time:
                        stage_cue_time = max(min_cue_time, min(calculated_cue_time, max_cue_time))
                    else:
                        stage_cue_time = round(last_beep + max(0.2, (interval_sec - stage_cue_dur) / 2.0), 2)
                else:
                    stage_cue_time = None

                # 2단계 이상 비프: 1회차 도착부터 num_shuttles회차 도착 비프까지 순차 배치
                beeps = []
                for b in range(1, num_shuttles + 1):
                    beep_time = round(last_beep + b * interval_sec, 2)
                    beeps.append(beep_time)

                stage_start_time = last_beep
                stage_end_time = beeps[-1]
                last_beep = beeps[-1]

            schedule.append({
                "stage": s,
                "speed_kmh": round(speed_kmh, 1),
                "interval_sec": interval_sec,
                "shuttles": num_shuttles,
                "beeps": beeps,
                "stage_start_sec": stage_start_time,
                "stage_end_sec": stage_end_time,
                "cue_time_sec": stage_cue_time,
                "cue_duration_sec": stage_cue_dur,
                "countdown_time_sec": cd_time if s == 1 else None,
                "countdown_duration_sec": countdown_duration if s == 1 else 0.0,
                "intro_time_sec": intro_time if s == 1 else None,
                "intro_duration_sec": intro_duration_sec if s == 1 else 0.0
            })

        return schedule


    @classmethod
    def apply_auto_ducking(
        cls,
        bgm_audio: AudioSegment,
        duck_segments: List[tuple],
        duck_db: float = -4.0,
        fade_ms: int = 250
    ) -> AudioSegment:
        """
        Ducks background music volume by `duck_db` during periods specified in `duck_segments`
        [(start_ms, end_ms), ...].
        """
        if not duck_segments or len(bgm_audio) == 0:
            return bgm_audio

        # Merge overlapping duck segments
        sorted_segs = sorted(duck_segments, key=lambda x: x[0])
        merged = []
        for start_ms, end_ms in sorted_segs:
            # Add padding of 100ms before and 200ms after
            s = max(0, start_ms - 100)
            e = min(len(bgm_audio), end_ms + 200)
            if not merged:
                merged.append([s, e])
            else:
                prev = merged[-1]
                if s <= prev[1]:
                    prev[1] = max(prev[1], e)
                else:
                    merged.append([s, e])

        ducked_bgm = bgm_audio
        # Apply ducking slice by slice
        result = AudioSegment.empty()
        curr_pos = 0

        for s_ms, e_ms in merged:
            if s_ms > curr_pos:
                result += ducked_bgm[curr_pos:s_ms]

            # Ducked slice with smooth crossfades
            duck_slice = ducked_bgm[s_ms:e_ms] + duck_db
            if len(duck_slice) > fade_ms * 2:
                duck_slice = duck_slice.fade_in(fade_ms).fade_out(fade_ms)
            result += duck_slice
            curr_pos = e_ms

        if curr_pos < len(ducked_bgm):
            result += ducked_bgm[curr_pos:]

        return result

    @classmethod
    def build_seamless_bgm(
        cls,
        bgm_paths: List[str],
        target_duration_ms: int,
        crossfade_ms: int = 2000
    ) -> AudioSegment:
        """
        Loads multiple BGM files and crossfades them sequentially.
        If total length is shorter than target_duration_ms, loops the playlist seamlessly.
        """
        valid_paths = [p for p in bgm_paths if os.path.exists(p)]
        if not valid_paths:
            return AudioSegment.silent(duration=target_duration_ms)

        playlist = []
        for p in valid_paths:
            try:
                seg = AudioSegment.from_file(p)
                if len(seg) > 500:
                    playlist.append(seg)
            except Exception as e:
                print(f"[ShuttleRunEngine] Failed to load BGM {p}: {e}")

        if not playlist:
            return AudioSegment.silent(duration=target_duration_ms)

        # Merge playlist with crossfades
        combined = AudioSegment.empty()
        for idx, track in enumerate(playlist):
            if idx == 0:
                combined = track
            else:
                cf = min(crossfade_ms, len(combined) // 3, len(track) // 3)
                if cf > 200:
                    combined = combined.append(track, crossfade=cf)
                else:
                    combined = combined + track

        # Loop if combined length is less than target duration
        if len(combined) < target_duration_ms:
            loop_count = math.ceil(target_duration_ms / max(len(combined), 1000))
            full_loop = combined
            for _ in range(loop_count):
                cf = min(crossfade_ms, len(full_loop) // 3, len(combined) // 3)
                if cf > 200:
                    full_loop = full_loop.append(combined, crossfade=cf)
                else:
                    full_loop = full_loop + combined
            combined = full_loop[:target_duration_ms]
        else:
            combined = combined[:target_duration_ms]

        # 3 seconds fade out at the very end
        if len(combined) > 3000:
            combined = combined.fade_out(3000)

        return combined
