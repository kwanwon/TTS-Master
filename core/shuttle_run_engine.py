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
        start_delay_sec: float = 5.0
    ) -> List[Dict[str, Any]]:
        """
        Calculates exact beep timestamps and voice cues for each stage.
        Returns a list of dicts:
        [
            {
                "stage": 1,
                "speed_kmh": 8.0,
                "interval_sec": 4.74,
                "shuttles": 13,
                "beeps": [5.0, 9.74, 14.48, ...],
                "stage_start_sec": 5.0,
                "stage_end_sec": 65.0,
                "voice_time_sec": 5.0
            },
            ...
        ]
        """
        preset = cls.PRESETS.get(preset_key, cls.PRESETS["elementary_low"])
        start_speed = preset["start_speed"]
        speed_inc = preset["speed_inc"]
        turn_time = preset["turn_time"]

        schedule = []
        current_time = float(start_delay_sec)

        for s in range(1, target_stages + 1):
            speed_kmh = start_speed + (s - 1) * speed_inc
            # Convert km/h to m/s
            speed_ms = speed_kmh / 3.6
            
            # Physics/Biomechanics formula: T = D / V + T_turn
            raw_interval = (distance / speed_ms) + turn_time
            # Round to 2 decimals for clean intervals (e.g., 4.74, 4.50, 4.29)
            interval_sec = round(raw_interval, 2)
            
            # Number of shuttles in this stage (approx 60s per stage)
            num_shuttles = max(1, int(round(stage_duration_sec / interval_sec)))
            actual_stage_duration = num_shuttles * interval_sec

            stage_start = current_time
            beeps = []
            for b in range(num_shuttles):
                beep_time = round(stage_start + b * interval_sec, 2)
                beeps.append(beep_time)

            schedule.append({
                "stage": s,
                "speed_kmh": round(speed_kmh, 1),
                "interval_sec": interval_sec,
                "shuttles": num_shuttles,
                "beeps": beeps,
                "stage_start_sec": stage_start,
                "stage_end_sec": stage_start + actual_stage_duration,
                "voice_time_sec": stage_start
            })

            current_time = round(stage_start + actual_stage_duration, 2)

        return schedule

    @classmethod
    def apply_auto_ducking(
        cls,
        bgm_audio: AudioSegment,
        duck_segments: List[tuple],
        duck_db: float = -8.0,
        fade_ms: int = 150
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
