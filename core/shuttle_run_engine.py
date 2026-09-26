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
    # Age category presets: starting speed (km/h), speed increase per level (km/h), turn deceleration (seconds)
    PRESETS = {
        "kinder": {
            "name": "유치부",
            "start_speed": 6.5,
            "speed_inc": 0.5,
            "turn_time": 0.75,
            "desc": "6.5 km/h 시작 (턴 감속 0.75초 고려)"
        },
        "elementary_low": {
            "name": "초등 저학년",
            "start_speed": 8.0,
            "speed_inc": 0.5,
            "turn_time": 0.50,
            "desc": "8.0 km/h 시작 (턴 감속 0.50초 고려)"
        },
        "elementary_high_teen": {
            "name": "초등 고학년 및 청소년",
            "start_speed": 8.5,
            "speed_inc": 0.5,
            "turn_time": 0.50,
            "desc": "8.5 km/h 시작 (턴 감속 0.50초 고려)"
        }
    }

    DISTANCES = {
        5: {"name": "5m (실내 초소형)", "val": 5.0},
        10: {"name": "10m (실내 표준)", "val": 10.0},
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

        # 1단계 시작 타이밍 계산 (안내 방송, 멘트 및 카운트다운 길이 기반)
        intro_time = 1.0 if intro_duration_sec > 0 else None
        intro_offset = (intro_duration_sec + 0.8) if intro_duration_sec > 0 else 0.0

        if stage_cue_durations is not None:
            cue_dur_1 = stage_cue_durations.get(1, 0.0)
            if cue_dur_1 > 0:
                cue_time_1 = round(1.0 + intro_offset, 2)
                t_curr = cue_time_1 + cue_dur_1
                if countdown_duration > 0:
                    cd_time = round(t_curr + 0.25, 2)
                    t_curr = cd_time + countdown_duration
                    stage_1_first_beep = round(t_curr + 0.2, 2)
                else:
                    cd_time = None
                    stage_1_first_beep = round(t_curr + cue_post_gap_sec, 2)
            else:
                cue_time_1 = None
                if countdown_duration > 0:
                    cd_time = round(1.0 + intro_offset, 2)
                    stage_1_first_beep = round(cd_time + countdown_duration + 0.2, 2)
                else:
                    cd_time = None
                    stage_1_first_beep = round(float(start_delay_sec) + intro_offset, 2)
        else:
            cue_time_1 = None
            cd_time = None
            stage_1_first_beep = round(float(start_delay_sec) + intro_offset, 2)

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
            else:
                cue_gap = 0.15 if distance <= 5.0 else 0.25
                post_gap = 0.25 if distance <= 5.0 else cue_post_gap_sec
                stage_cue_dur = stage_cue_durations.get(s, 0.0) if stage_cue_durations else 0.0
                
                if stage_cue_dur > 0:
                    stage_cue_time = round(last_beep + signal_duration_sec + cue_gap, 2)
                    stage_start = round(stage_cue_time + stage_cue_dur + post_gap, 2)
                else:
                    stage_cue_time = None
                    stage_start = round(last_beep + signal_duration_sec + (0.3 if distance <= 5.0 else 0.6), 2)

            # 비프 타임스탬프: B_0(출발), B_1..B_num_shuttles(각 회차 도착 및 턴)
            beeps = []
            for b in range(num_shuttles + 1):
                beep_time = round(stage_start + b * interval_sec, 2)
                beeps.append(beep_time)

            last_beep = beeps[-1]

            schedule.append({
                "stage": s,
                "speed_kmh": round(speed_kmh, 1),
                "interval_sec": interval_sec,
                "shuttles": num_shuttles,
                "beeps": beeps,
                "stage_start_sec": beeps[0],
                "stage_end_sec": beeps[-1],
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
