"""
Sparring and Kicking Training Engine (겨루기 & 발차기 트레이닝 오디오 엔진)
Supports flexible dojo training modes:
1. RELAY: 1:1, 1:2, 1:3 turn-based pad kicking (미트 순환 발차기)
2. REACTION: Rhythm step + random whistle/cue for counter kicks (받아차기 / 반사신경)
3. COMBO: Step + 1-hit, 2-hit, 3-hit continuous kicks (스텝 + 1연타/2연타)
4. ROUNDS: Sparring rounds with warning beeps and rest cues (정규 겨루기 라운드)

All routines support multiple BGM crossfading and auto-ducking.
"""

import os
import random
import uuid
import math
from typing import List, Dict, Any, Tuple
from pydub import AudioSegment
from core.shuttle_run_engine import ShuttleRunEngine


class SparringTrainingEngine:
    # Training presets
    TRAINING_MODES = {
        "relay": {
            "name": "다자간 릴레이 순환 발차기 (1:1 / 1:2 / 1:3)",
            "desc": "미트를 중심으로 1명 또는 2~3명이 교대로 지정 시간 동안 전력 타격"
        },
        "reaction": {
            "name": "스텝 & 실전 기술 반응 훈련",
            "desc": "신나는 스텝 중 불규칙 랜덤 신호음/구령에 즉시 반응 발차기"
        },
        "combo": {
            "name": "스텝 + 콤비네이션 연타 인터벌 (1연타 / 2연타 / 3연타)",
            "desc": "정해진 주기마다 '1연타!', '2연타!' 구령에 맞춰 콤보 폭발"
        },
        "rounds": {
            "name": "정규 스파링 라운드 타이머 시뮬레이터",
            "desc": "경기 라운드(예: 1분 30초) + 휴식(30초) + 라운드 종료 10초 전 경고"
        }
    }

    @classmethod
    def generate_training_schedule(
        cls,
        mode: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calculates time events and cues based on user parameters.
        Returns:
        {
            "total_duration_sec": float,
            "events": [
                {
                    "time": float,
                    "type": "beep" | "whistle" | "voice" | "bell" | "countdown",
                    "text": str,
                    "sound_file": str,
                    "track": int
                }, ...
            ],
            "duck_segments": [(start_ms, end_ms), ...]
        }
        """
        events = []
        duck_segments = []

        countdown_enabled = params.get("countdown_enabled", True)
        cd_style = params.get("countdown_style", "en_321")

        # 1. 시작 전 훈련 안내 및 카운트다운 (셔틀런처럼 완성도 높은 시퀀스)
        intro_enabled = params.get("intro_enabled", True)
        curr_time = 1.0

        if intro_enabled:
            intro_text = params.get("intro_text", "").strip()
            if not intro_text:
                if mode == "relay":
                    cue_raw = params.get("cue_text", "백스텝 후 받아차기 교차 상단")
                    # 여러 기술일 경우 앞부분 요약
                    cue_first = cue_raw.split(",")[0].strip()
                    intro_text = f"지금부터 실전 스파링 발차기 훈련을 시작합니다. 이번 훈련 기술은 '{cue_first}' 입니다. 지시하는 기술을 듣고 신호음에 맞춰 정확히 타격하세요. 모두 준비해 주세요!"
                elif mode == "reaction":
                    intro_text = "지금부터 실전 스파링 반응 훈련을 시작합니다. 스텝을 뛰며 기술 지시를 듣고 신호음에 맞춰 빠르고 정확하게 타격하세요. 모두 준비해 주세요!"
                elif mode == "combo":
                    intro_text = "지금부터 스텝 콤비네이션 연타 훈련을 시작합니다. 스텝을 유지하다가 신호음과 구령에 맞춰 전력 연타하세요. 준비해 주세요!"
                elif mode == "rounds":
                    intro_text = "지금부터 정규 스파링 라운드 훈련을 시작합니다. 양 선수 준비해 주세요!"
                else:
                    intro_text = "지금부터 스파링 훈련을 시작합니다. 준비해 주세요!"

            intro_dur = max(2.5, round(len(intro_text) * 0.16, 2))
            events.append({
                "time": curr_time,
                "type": "voice",
                "text": f"[사전 안내] {intro_text}",
                "duration": intro_dur,
                "track": 2,
                "vol": 2.0
            })
            duck_segments.append((int(curr_time * 1000), int((curr_time + intro_dur) * 1000)))
            curr_time += intro_dur + 0.4

        # 카운트다운 (Three, Two, One / 3-2-1)
        if countdown_enabled:
            cd_text = "[카운트다운] Three, Two, One"
            if cd_style == "ko_321":
                cd_text = "[카운트다운] 셋, 둘, 하나"
            elif cd_style == "ko_ready":
                cd_text = "[카운트다운] 준비되었나요? 준비! 셋, 둘, 하나"
            elif cd_style == "en_ready":
                cd_text = "[카운트다운] Are you ready? Ready! Three, Two, One"
            elif cd_style == "beep":
                cd_text = "[카운트다운] 전자 비프음 3회 (띡-띡-띡)"

            cd_dur = 3.5 if "ready" in cd_style else 2.5
            events.append({
                "time": curr_time,
                "type": "countdown",
                "text": cd_text,
                "cd_style": cd_style,
                "sound_file": os.path.join("effects", "countdown_beeps.wav") if cd_style == "beep" else os.path.join("effects", "countdown.wav"),
                "duration": cd_dur,
                "track": 2,
                "vol": 2.0
            })
            duck_segments.append((int(curr_time * 1000), int((curr_time + cd_dur) * 1000)))
            curr_time += cd_dur + 1.0  # 1.0초 긴장 딜레이

        # ── Mode 1: 다자간 릴레이 순환 발차기 (1:1, 1:2, 1:3) ──
        if mode == "relay":
            fighters_count = params.get("fighters_count", 2)  # 2 for 1:1, 3 for 1:2, 4 for 1:3
            strike_sec = params.get("strike_sec", 15.0)       # 타격 시간 (초)
            change_sec = params.get("change_sec", 3.0)        # 교대 시간 (초)
            cycles = params.get("cycles", 3)                  # 전체 순환 세트 수
            cue_text_custom = params.get("cue_text", "백스텝 후 받아차기 교차 상단")  # 기술명

            cues_list = [c.strip() for c in cue_text_custom.split(",") if c.strip()]
            if not cues_list:
                cues_list = ["백스텝 후 받아차기 교차 상단"]

            cue_idx = 0
            for c in range(1, cycles + 1):
                for f in range(1, fighters_count + 1):
                    fighter_name = f"{f}번 타자" if fighters_count > 2 else ("A선수" if f == 1 else "B선수")
                    current_cue = cues_list[cue_idx % len(cues_list)]
                    cue_idx += 1
                    
                    # 1. 설명/기술 명칭 먼저 충분히 송출 (절대로 '출발' 단어 넣지 않음!)
                    call_text = f"{fighter_name}! {current_cue}!"
                    call_dur = max(1.5, round(len(call_text) * 0.18, 2))
                    events.append({
                        "time": curr_time,
                        "type": "voice",
                        "text": f"[{c}세트-{fighter_name}] {call_text}",
                        "duration": call_dur,
                        "track": 2,
                        "vol": 2.5
                    })
                    duck_segments.append((int(curr_time * 1000), int((curr_time + call_dur) * 1000)))
                    curr_time += call_dur + 0.25

                    # 2. 설명 직후 타격 시작 신호음 (삑~익!)
                    events.append({
                        "time": curr_time,
                        "type": "beep",
                        "text": f"[{fighter_name} 타격 신호음] 삑~익!",
                        "sound_file": os.path.join("effects", "beep.wav"),
                        "duration": 0.25,
                        "track": 1,
                        "vol": 3.0
                    })
                    duck_segments.append((int(curr_time * 1000), int((curr_time + 0.4) * 1000)))
                    curr_time += 0.3

                    # 3. 타격 시간 진행 및 마지막 3초 카운트다운/경고 비프
                    if strike_sec >= 8:
                        warn_time = curr_time + strike_sec - 3.0
                        for b in range(3):
                            b_t = warn_time + b * 1.0
                            events.append({
                                "time": b_t,
                                "type": "beep",
                                "text": f"[마무리 알림 {3-b}]",
                                "sound_file": os.path.join("effects", "beep.wav"),
                                "duration": 0.25,
                                "track": 1,
                                "vol": 1.0
                            })
                            duck_segments.append((int(b_t * 1000), int((b_t + 0.3) * 1000)))

                    curr_time += strike_sec

                    # 4. 선수 교대 안내: 신호음(벨)이 아니라 "또렷한 음성"으로 교대 방송!
                    is_last_fighter = (c == cycles and f == fighters_count)
                    if not is_last_fighter:
                        if fighters_count == 2:
                            next_fighter = "B선수" if f == 1 else "A선수"
                        else:
                            next_f_idx = (f % fighters_count) + 1
                            next_fighter = f"{next_f_idx}번 타자"

                        change_msg = f"선수 교대! {next_fighter} 준비!"
                        chg_dur = 1.8
                        events.append({
                            "time": curr_time,
                            "type": "voice",
                            "text": f"[선수 교대] {change_msg}",
                            "duration": chg_dur,
                            "track": 2,
                            "vol": 2.5
                        })
                        duck_segments.append((int(curr_time * 1000), int((curr_time + chg_dur) * 1000)))
                        curr_time += chg_dur + change_sec

            # 5. 모든 세트 종료 시 정중한 훈련 종료 멘트
            events.append({
                "time": curr_time + 0.5,
                "type": "voice",
                "text": "[훈련 종료] 훈련 종료! 수고하셨습니다! 호흡 가다듬고 정렬하세요.",
                "duration": 3.5,
                "track": 2,
                "vol": 2.5
            })
            duck_segments.append((int((curr_time + 0.5) * 1000), int((curr_time + 4.2) * 1000)))
            total_duration_sec = curr_time + 5.0

        # ── Mode 2: 스텝 & 실전 기술 반응 훈련 ──
        elif mode == "reaction":
            total_training_sec = params.get("duration_sec", 120.0)  # 예: 2분 훈련
            min_interval = float(params.get("min_interval", 1.0))   # 최소 랜덤 긴장 대기 시간 (초)
            max_interval = float(params.get("max_interval", 3.0))   # 최대 랜덤 긴장 대기 시간 (초)
            if min_interval > max_interval:
                min_interval, max_interval = max_interval, min_interval

            recovery_time = float(params.get("recovery_sec", 0.8))  # 타격 후 스텝 복귀/준비 대기 시간 (기본 0.8초)
            reaction_cues = params.get("cues", ["1연타!", "2연타!", "받아차기!", "카운터!"])  # 기술 목록
            trigger_sound = params.get("signal_sound", "whistle")   # whistle / beep / drum / voice_start / voice_go / voice_bang / random_mix

            if not intro_enabled and not countdown_enabled:
                events.append({
                    "time": curr_time,
                    "type": "voice",
                    "text": "[반응 훈련 시작] 스텝을 뛰며 기술 지시에 집중합니다!",
                    "duration": 2.8,
                    "track": 2,
                    "vol": 2.0
                })
                duck_segments.append((int(curr_time * 1000), int((curr_time + 3.0) * 1000)))
                curr_time += 3.8

            limit_time = curr_time + total_training_sec
            cue_count = 1

            while curr_time < limit_time - 3.5:
                chosen_cue = random.choice(reaction_cues) if reaction_cues else "1연타!"
                
                # 1. 기술 지시/이름 먼저 송출 (글자 수 기반 간결하고 자연스러운 발성 시간 계산)
                char_count = len(chosen_cue.replace(" ", "").replace("!", ""))
                cue_dur = max(0.7, round(char_count * 0.2, 2))
                events.append({
                    "time": curr_time,
                    "type": "voice",
                    "text": f"[{cue_count}회] {chosen_cue}",
                    "duration": cue_dur,
                    "track": 2,
                    "vol": 2.5
                })
                duck_segments.append((int(curr_time * 1000), int((curr_time + cue_dur) * 1000)))
                curr_time += cue_dur

                # 2. 진짜 랜덤 긴장 대기 시간 (완전 무작위 적용)
                rand_gap = round(random.uniform(min_interval, max_interval), 2)
                curr_time += rand_gap
                if curr_time >= limit_time:
                    break

                # 3. 타격/발차기 트리거 신호 발동 (신호음 or 음성 구령)
                current_trigger = trigger_sound
                if current_trigger == "random_mix":
                    current_trigger = random.choice(["whistle", "beep", "drum", "voice_start", "voice_go"])

                if current_trigger == "whistle":
                    events.append({
                        "time": curr_time,
                        "type": "signal",
                        "text": f"[트리거 ({rand_gap}초 대기 후)] 경기용 휘슬!",
                        "sound_file": os.path.join("effects", "whistle.wav"),
                        "duration": 0.35,
                        "track": 1,
                        "vol": 3.0
                    })
                    duck_segments.append((int(curr_time * 1000), int((curr_time + 0.6) * 1000)))
                    curr_time += 0.4
                elif current_trigger == "beep":
                    events.append({
                        "time": curr_time,
                        "type": "signal",
                        "text": f"[트리거 ({rand_gap}초 대기 후)] 전자 비프음 (삑~익)!",
                        "sound_file": os.path.join("effects", "beep.wav"),
                        "duration": 0.25,
                        "track": 1,
                        "vol": 3.0
                    })
                    duck_segments.append((int(curr_time * 1000), int((curr_time + 0.5) * 1000)))
                    curr_time += 0.3
                elif current_trigger == "drum":
                    events.append({
                        "time": curr_time,
                        "type": "signal",
                        "text": f"[트리거 ({rand_gap}초 대기 후)] 대북 타격음 (쿵)!",
                        "sound_file": os.path.join("effects", "drum.wav"),
                        "duration": 0.45,
                        "track": 1,
                        "vol": 3.0
                    })
                    duck_segments.append((int(curr_time * 1000), int((curr_time + 0.7) * 1000)))
                    curr_time += 0.5
                elif current_trigger == "voice_start":
                    events.append({
                        "time": curr_time,
                        "type": "voice",
                        "text": f"[트리거 ({rand_gap}초 대기 후)] 탕!",
                        "duration": 0.8,
                        "track": 2,
                        "vol": 3.0
                    })
                    duck_segments.append((int(curr_time * 1000), int((curr_time + 0.9) * 1000)))
                    curr_time += 0.9
                elif current_trigger == "voice_go":
                    events.append({
                        "time": curr_time,
                        "type": "voice",
                        "text": f"[트리거 ({rand_gap}초 대기 후)] GO!",
                        "duration": 0.7,
                        "track": 2,
                        "vol": 3.0
                    })
                    duck_segments.append((int(curr_time * 1000), int((curr_time + 0.8) * 1000)))
                    curr_time += 0.8
                elif current_trigger == "voice_bang":
                    events.append({
                        "time": curr_time,
                        "type": "voice",
                        "text": f"[트리거 ({rand_gap}초 대기 후)] 탕!",
                        "duration": 0.6,
                        "track": 2,
                        "vol": 3.0
                    })
                    duck_segments.append((int(curr_time * 1000), int((curr_time + 0.7) * 1000)))
                    curr_time += 0.7

                # 4. 타격 후 착지 및 스텝 복귀 시간
                curr_time += recovery_time
                cue_count += 1

            # 훈련 종료
            events.append({
                "time": curr_time + 0.5,
                "type": "bell",
                "text": "[종료 벨] 훈련 종료!",
                "sound_file": os.path.join("effects", "stage_bell.wav"),
                "duration": 1.2,
                "track": 2,
                "vol": 1.5
            })
            events.append({
                "time": curr_time + 1.8,
                "type": "voice",
                "text": "[훈련 종료] 훈련 종료! 수고하셨습니다! 호흡 가다듬고 정렬하세요.",
                "duration": 3.5,
                "track": 2,
                "vol": 2.5
            })
            duck_segments.append((int((curr_time + 1.8) * 1000), int((curr_time + 5.5) * 1000)))
            total_duration_sec = curr_time + 6.0

        # ── Mode 3: 스텝 + 콤비네이션 연타 인터벌 ──
        elif mode == "combo":
            step_sec = params.get("step_sec", 8.0)         # 스텝 지속 시간 (예: 8초)
            combo_sec = params.get("combo_sec", 4.0)       # 연타 지속 시간 (예: 4초)
            sets_count = params.get("sets_count", 6)       # 세트 수 (예: 6세트)
            combo_types = params.get("combo_types", ["1연타", "2연타", "3연타"])  # 순환 콤보

            for s in range(1, sets_count + 1):
                combo_name = combo_types[(s - 1) % len(combo_types)]
                # 스텝 구간 시작 안내
                events.append({
                    "time": curr_time,
                    "type": "voice",
                    "text": f"[{s}세트] 스텝 유지! 호흡 조절!",
                    "duration": 2.0,
                    "track": 2,
                    "vol": 1.5
                })
                duck_segments.append((int(curr_time * 1000), int((curr_time + 2.0) * 1000)))
                curr_time += step_sec

                # 연타 돌입 신호 및 구령
                events.append({
                    "time": curr_time,
                    "type": "whistle",
                    "text": "[휘슬] 연타 돌입!",
                    "sound_file": os.path.join("effects", "whistle.wav"),
                    "duration": 0.35,
                    "track": 1,
                    "vol": 2.5
                })
                events.append({
                    "time": curr_time + 0.2,
                    "type": "voice",
                    "text": f"[{combo_name}] {combo_name} 전력 타격!",
                    "duration": 1.8,
                    "track": 2,
                    "vol": 2.5
                })
                duck_segments.append((int(curr_time * 1000), int((curr_time + combo_sec) * 1000)))
                curr_time += combo_sec

            # 마무리 멘트
            events.append({
                "time": curr_time,
                "type": "bell",
                "text": "[훈련 완료]",
                "sound_file": os.path.join("effects", "stage_bell.wav"),
                "duration": 1.2,
                "track": 2,
                "vol": 1.5
            })
            events.append({
                "time": curr_time + 1.5,
                "type": "voice",
                "text": "[훈련 종료] 훈련 종료! 수고하셨습니다! 호흡 가다듬고 정렬하세요.",
                "duration": 3.5,
                "track": 2,
                "vol": 2.5
            })
            duck_segments.append((int((curr_time + 1.5) * 1000), int((curr_time + 5.2) * 1000)))
            total_duration_sec = curr_time + 6.0

        # ── Mode 4: 정규 스파링 라운드 시뮬레이터 ──
        elif mode == "rounds":
            round_sec = params.get("round_sec", 90.0)      # 1분 30초 (90초)
            rest_sec = params.get("rest_sec", 30.0)        # 휴식 30초
            total_rounds = params.get("total_rounds", 3)   # 3라운드

            for r in range(1, total_rounds + 1):
                # 라운드 시작 멘트 & 휘슬
                events.append({
                    "time": curr_time,
                    "type": "whistle",
                    "text": f"[{r}라운드 시작] 경기 시작 휘슬!",
                    "sound_file": os.path.join("effects", "whistle.wav"),
                    "duration": 0.35,
                    "track": 1,
                    "vol": 2.5
                })
                events.append({
                    "time": curr_time + 0.3,
                    "type": "voice",
                    "text": f"제 {r}라운드, 시작!",
                    "duration": 1.8,
                    "track": 2,
                    "vol": 2.0
                })
                duck_segments.append((int(curr_time * 1000), int((curr_time + 2.5) * 1000)))

                # 라운드 종료 10초 전 경고음
                warn_time = curr_time + round_sec - 10.0
                if round_sec >= 20:
                    events.append({
                        "time": warn_time,
                        "type": "voice",
                        "text": "[종료 10초 전] 마지막 10초! 공격!",
                        "duration": 2.0,
                        "track": 2,
                        "vol": 2.0
                    })
                    events.append({
                        "time": warn_time,
                        "type": "beep",
                        "text": "[10초 경고 비프]",
                        "sound_file": os.path.join("effects", "beep.wav"),
                        "duration": 0.25,
                        "track": 1,
                        "vol": 1.5
                    })
                    duck_segments.append((int(warn_time * 1000), int((warn_time + 2.5) * 1000)))

                curr_time += round_sec

                # 라운드 종료 공(Gong/Bell)
                events.append({
                    "time": curr_time,
                    "type": "bell",
                    "text": f"[{r}라운드 종료] 갈려! 타임!",
                    "sound_file": os.path.join("effects", "stage_bell.wav"),
                    "duration": 1.2,
                    "track": 2,
                    "vol": 2.0
                })

                if r < total_rounds:
                    # 휴식 멘트
                    events.append({
                        "time": curr_time + 1.2,
                        "type": "voice",
                        "text": f"휴식 {int(rest_sec)}초입니다. 물 마시고 숨 고르세요.",
                        "duration": 3.0,
                        "track": 2,
                        "vol": 1.5
                    })
                    duck_segments.append((int(curr_time * 1000), int((curr_time + 4.5) * 1000)))
                    curr_time += rest_sec
                else:
                    # 최종 경기 종료
                    events.append({
                        "time": curr_time + 1.5,
                        "type": "voice",
                        "text": "[훈련 종료] 경기 종료! 수고하셨습니다! 양 선수 마주보고 차렷, 경례!",
                        "duration": 3.5,
                        "track": 2,
                        "vol": 2.0
                    })
                    curr_time += 4.0

            total_duration_sec = curr_time + 3.0
        else:
            total_duration_sec = 60.0

        return {
            "total_duration_sec": total_duration_sec,
            "events": events,
            "duck_segments": duck_segments
        }
