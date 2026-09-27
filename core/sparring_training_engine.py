"""
Sparring and Kicking Training Engine (스파링 발차기 트레이닝 오디오 엔진)
Supports flexible dojo training modes:
1. RELAY: 1:1, 1:2, 1:3 turn-based pad kicking (미트 순환 발차기)
2. REACTION: Rhythm step + random whistle/cue for counter kicks (받아차기 / 반사신경)
3. COMBO: Step + continuous strike combo (스텝 + 콤비네이션 연타)
4. ROUNDS: Sparring rounds with warning beeps and rest cues (정규 스파링 라운드)

All routines support multiple BGM crossfading and auto-ducking.
"""

import os
import random
import uuid
import math
from typing import List, Dict, Any, Tuple
from pydub import AudioSegment
from core.shuttle_run_engine import ShuttleRunEngine


class BalancedCuePicker:
    """
    균등 분배 및 연속 중복 방지 큐 피커
    - 모든 기술이 편중 없이 균등하게 출현 (골고루)
    - 순차적이지 않고 예측 불가능한 덱 셔플 방식
    - 동일 기술이 연속으로 나오는 횟수를 최대 2회 이하로 엄격히 제한 (3회 이상 연속 절대 방지)
    """
    def __init__(self, cues: List[str], max_consecutive: int = 2):
        self.cues = [c.strip() for c in cues if c.strip()]
        self.max_consecutive = max(1, max_consecutive)
        self.history: List[str] = []
        self.bag: List[str] = []

    def next_cue(self) -> str:
        if not self.cues:
            return "1연타!"
        if len(self.cues) == 1:
            return self.cues[0]

        if not self.bag:
            self.bag = self.cues.copy()
            random.shuffle(self.bag)
            # 덱(백) 경계 검사: 직전 기술과 새 백의 첫 기술이 동일할 경우
            if self.history and self.bag[0] == self.history[-1]:
                must_swap = (len(self.history) >= self.max_consecutive and 
                             all(h == self.bag[0] for h in self.history[-self.max_consecutive:]))
                if must_swap or random.random() < 0.75:
                    for i in range(1, len(self.bag)):
                        if self.bag[i] != self.history[-1]:
                            self.bag[0], self.bag[i] = self.bag[i], self.bag[0]
                            break

        candidate = self.bag.pop(0)

        # 동일 기술 연속 출현 제한 하드 가드 (최대 2회 이하 유지)
        if len(self.history) >= self.max_consecutive and all(h == candidate for h in self.history[-self.max_consecutive:]):
            other_options = [c for c in self.cues if c != candidate]
            if other_options:
                candidate = random.choice(other_options)

        self.history.append(candidate)
        return candidate


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
            "name": "스텝 + 콤비네이션 연타 인터벌 (스텝 지시 ➔ 삐익 ➔ 갈려/중지)",
            "desc": "스텝 유지 후 신호음에 전력 연타 폭발, 종료 신호(갈려/중지/그만/비프)에 스텝 복귀"
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
                    stop_name_map = {
                        "voice_kalyeo": "갈려",
                        "voice_stop": "중지",
                        "voice_end": "그만",
                        "beep": "종료 비프음",
                        "whistle": "종료 휘슬"
                    }
                    stop_label = stop_name_map.get(params.get("stop_signal", "voice_kalyeo"), "갈려")
                    raw_kicks = params.get("kick_types", [])
                    kick_list = [k.strip() for k in raw_kicks if k and k.strip()] if isinstance(raw_kicks, list) else [k.strip() for k in str(raw_kicks).split(",") if k.strip()]
                    
                    if kick_list:
                        kick_desc = ", ".join(kick_list[:3])
                        if len(kick_list) > 3:
                            kick_desc += f" 외 {len(kick_list)-3}개"
                        intro_text = (
                            f"지금부터 스텝 콤비네이션 연타 스파링 훈련을 시작합니다. "
                            f"이번 집중 훈련 공격 기술은 '{kick_desc}' 입니다. "
                            f"지시하는 스텝을 유지하다가 신호음이 울리면 전력으로 연타하고, "
                            f"'{stop_label}' 신호에 맞춰 스텝으로 복귀하세요. 준비해 주세요!"
                        )
                    else:
                        intro_text = (
                            f"지금부터 스텝 콤비네이션 연타 스파링 훈련을 시작합니다. "
                            f"지시하는 스텝을 유지하다가 신호음이 울리면 전력으로 연타하고, "
                            f"'{stop_label}' 신호에 맞춰 스텝으로 복귀하세요. 준비해 주세요!"
                        )
                elif mode == "rounds":
                    intro_text = "지금부터 정규 스파링 라운드 훈련을 시작합니다. 양 선수 준비해 주세요!"
                else:
                    intro_text = "지금부터 스파링 훈련을 시작합니다. 준비해 주세요!"

            intro_dur = max(3.0, round(len(intro_text) * 0.22, 2))
            events.append({
                "time": curr_time,
                "type": "voice",
                "text": f"[사전 안내] {intro_text}",
                "duration": intro_dur,
                "track": 2,
                "vol": 2.2
            })
            duck_segments.append((int(curr_time * 1000), int((curr_time + intro_dur + 0.5) * 1000)))
            curr_time += intro_dur + 0.8

            # ⭐ [사용자 요청] 설명 후 받기자 미트 착용 및 위치 선정 대기 시간 (n초) + "모두 준비가 되었나요?" 확인
            prep_wait_sec = float(params.get("prep_wait_sec", 0.0))
            if prep_wait_sec > 0:
                curr_time += prep_wait_sec
                ready_prompt = "모두 준비가 되었나요?"
                ready_dur = 1.8
                events.append({
                    "time": curr_time,
                    "type": "voice",
                    "text": f"[준비 확인] {ready_prompt}",
                    "duration": ready_dur,
                    "track": 2,
                    "vol": 2.5
                })
                duck_segments.append((int(curr_time * 1000), int((curr_time + ready_dur + 0.5) * 1000)))
                # 사용자 요청: "모두 준비가 되었나요? 딜레이 2초 후에 시작"
                curr_time += ready_dur + 2.0

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

            # 3-2-1 각 숫자 사이에 1.5초 딜레이 배치: 총 소요시간 약 4.3초 (ready 포함 시 약 6.5초)
            cd_dur = 6.5 if "ready" in cd_style else 4.3
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
            curr_time += cd_dur + 1.5  # 1(One) 발성 후 1.5초 긴장 딜레이 (사용자 요청: 3-1.5s, 2-1.5s, 1-1.5s)

        # ── Mode 1: 다자간 릴레이 순환 발차기 (1:1, 1:2, 1:3) ──
        if mode == "relay":
            fighters_count = params.get("fighters_count", 2)  # 2 for 1:1, 3 for 1:2, 4 for 1:3
            strike_sec = params.get("strike_sec", 15.0)       # 타격 시간 (초)
            change_sec = params.get("change_sec", 3.0)        # 교대 시간 (초)
            cycles = params.get("cycles", 3)                  # 전체 순환 세트 수
            cue_text_custom = params.get("cue_text", "백스텝 후 받아차기 교차 상단")  # 기술명

            # 줄바꿈(\n) 또는 쉼표(,) 모두 지원
            cues_list = [c.strip() for line in str(cue_text_custom).splitlines() for c in line.split(",") if c.strip()]
            if not cues_list:
                cues_list = ["백스텝 후 받아차기 교차 상단"]

            ordinal_names = ["첫번째 선수", "두번째 선수", "세번째 선수", "네번째 선수"]

            for c in range(1, cycles + 1):
                for f in range(1, fighters_count + 1):
                    # 사용자 요청: 1:2와 1:3은 첫번째 선수, 두번째 선수, 세번째 선수 호칭 적용
                    if fighters_count == 2:
                        fighter_name = "A선수" if f == 1 else "B선수"
                    else:
                        fighter_name = ordinal_names[f - 1] if f <= len(ordinal_names) else f"{f}번째 선수"

                    # 사용자 요청: 선수별로 따로 기술 지시어 매칭
                    if len(cues_list) >= fighters_count:
                        current_cue = cues_list[f - 1]
                    elif len(cues_list) > 1:
                        current_cue = cues_list[(f - 1) % len(cues_list)]
                    else:
                        current_cue = cues_list[0]
                    
                    # 1. 설명/기술 명칭 먼저 충분히 송출 (절대로 '출발' 단어 넣지 않음!)
                    call_text = f"{fighter_name}! {current_cue}!"
                    call_dur = max(2.0, round(len(call_text) * 0.22, 2))
                    events.append({
                        "time": curr_time,
                        "type": "voice",
                        "text": f"[{c}세트-{fighter_name}] {call_text}",
                        "duration": call_dur,
                        "track": 2,
                        "vol": 2.5
                    })
                    duck_segments.append((int(curr_time * 1000), int((curr_time + call_dur) * 1000)))
                    curr_time += call_dur + 1.0  # 사용자 요청: 음성 안내 완료 후 1.0초 여유 딜레이 후 신호음 배치

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
                            next_fighter = ordinal_names[next_f_idx - 1] if next_f_idx <= len(ordinal_names) else f"{next_f_idx}번째 선수"

                        change_msg = f"선수 교대! {next_fighter} 준비!"
                        chg_dur = max(1.8, round(len(change_msg) * 0.22, 2))
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

            # 5. 모든 세트 종료 시 휴식 및 대기 안내 멘트 (사용자 요청: 정렬 대신 물 한잔 및 다음 지시 대기/휴식 개념 적용)
            default_outro = "훈련 종료! 모두 수고하셨습니다! 물 한잔 마시고 호흡을 가다듬으며 다음 지시를 위해 잠시 대기하세요."
            outro_text = params.get("outro_text", default_outro).strip() or default_outro
            outro_dur = max(3.5, round(len(outro_text) * 0.22, 2))
            events.append({
                "time": curr_time + 0.5,
                "type": "voice",
                "text": f"[훈련 종료] {outro_text}",
                "duration": outro_dur,
                "track": 2,
                "vol": 2.5
            })
            duck_segments.append((int((curr_time + 0.5) * 1000), int((curr_time + 0.5 + outro_dur + 0.5) * 1000)))
            total_duration_sec = curr_time + 0.5 + outro_dur + 2.0  # 마지막 음성 완전히 끝난 뒤 최소 2.0초 여유 딜레이 보장

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

            # 골고루 균등 분배 및 연속 중복 최대 2회 이하 큐 피커
            cue_picker = BalancedCuePicker(reaction_cues, max_consecutive=2)

            while curr_time < limit_time - 3.5:
                chosen_cue = cue_picker.next_cue()
                
                # 1. 기술 지시/이름 먼저 송출 (글자 수 기반 간결하고 자연스러운 발성 시간 계산)
                char_count = len(chosen_cue.replace(" ", "").replace("!", ""))
                cue_dur = max(0.9, round(char_count * 0.22, 2))
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
                    current_trigger = random.choice(["whistle", "beep", "drum", "voice_start", "voice_letsgo", "voice_readygo", "voice_bang"])

                if current_trigger == "whistle":
                    events.append({
                        "time": curr_time,
                        "type": "signal",
                        "text": f"[트리거 ({rand_gap}초 대기 후)] 경기용 휘슬!",
                        "sound_file": os.path.join("effects", "whistle.wav"),
                        "duration": 0.38,
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
                        "text": f"[트리거 ({rand_gap}초 대기 후)] 시작!",
                        "duration": 0.8,
                        "track": 2,
                        "vol": 3.0
                    })
                    duck_segments.append((int(curr_time * 1000), int((curr_time + 0.9) * 1000)))
                    curr_time += 0.9
                elif current_trigger in ("voice_letsgo", "voice_go"):
                    events.append({
                        "time": curr_time,
                        "type": "voice",
                        "text": f"[트리거 ({rand_gap}초 대기 후)] Let's Go!",
                        "duration": 0.65,
                        "track": 2,
                        "vol": 3.0
                    })
                    duck_segments.append((int(curr_time * 1000), int((curr_time + 0.8) * 1000)))
                    curr_time += 0.75
                elif current_trigger == "voice_readygo":
                    events.append({
                        "time": curr_time,
                        "type": "voice",
                        "text": f"[트리거 ({rand_gap}초 대기 후)] Ready, Go!",
                        "duration": 0.95,
                        "track": 2,
                        "vol": 3.0
                    })
                    duck_segments.append((int(curr_time * 1000), int((curr_time + 1.1) * 1000)))
                    curr_time += 1.05
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
            default_outro = "훈련 종료! 모두 수고하셨습니다! 물 한잔 마시고 호흡을 가다듬으며 다음 지시를 위해 잠시 대기하세요."
            outro_text = params.get("outro_text", default_outro).strip() or default_outro
            outro_dur = max(3.5, round(len(outro_text) * 0.22, 2))
            events.append({
                "time": curr_time + 1.8,
                "type": "voice",
                "text": f"[훈련 종료] {outro_text}",
                "duration": outro_dur,
                "track": 2,
                "vol": 2.5
            })
            duck_segments.append((int((curr_time + 1.8) * 1000), int((curr_time + 1.8 + outro_dur + 0.5) * 1000)))
            total_duration_sec = curr_time + 1.8 + outro_dur + 2.0  # 종료 후 2초 이상의 넉넉한 딜레이 보장

        # ── Mode 3: 스텝 + 콤비네이션 연타 인터벌 ──
        elif mode == "combo":
            step_sec = float(params.get("step_sec", 8.0))         # 스텝 지속 시간 (예: 8초)
            combo_sec = float(params.get("combo_sec", 4.0))       # 전력 연타 지속 시간 (예: 4초)
            sets_count = int(params.get("sets_count", 6))         # 총 세트 수 (예: 6세트)

            # 스텝 목록 (태권도 실전 6가지 기본 스텝 순서)
            raw_steps = params.get("step_types", [
                "제자리 스텝", "앞뒤 스텝", "업다운 스텝", "앞발 스텝", "뒷발 스텝", "앞발 스텝 발바꿔"
            ])
            step_types = [s.strip() for s in raw_steps if s and s.strip()]
            if not step_types:
                step_types = ["제자리 스텝", "앞뒤 스텝", "업다운 스텝", "앞발 스텝", "뒷발 스텝", "앞발 스텝 발바꿔"]

            start_signal = params.get("start_signal", "whistle")   # whistle / beep / drum
            stop_signal = params.get("stop_signal", "voice_kalyeo") # voice_kalyeo / voice_stop / voice_end / beep / whistle
            kick_announce_mode = params.get("kick_announce_mode", "intro_only")  # intro_only / each_set
            raw_kicks = params.get("kick_types", [])
            kick_types = [k.strip() for k in raw_kicks if k and k.strip()] if isinstance(raw_kicks, list) else [k.strip() for k in str(raw_kicks).split(",") if k.strip()]

            start_sound_file = os.path.join("effects", "whistle.wav")
            start_sound_label = "경기용 휘슬 (삐익-!)"
            if start_signal == "beep":
                start_sound_file = os.path.join("effects", "beep.wav")
                start_sound_label = "전자 비프음 (삑~익!)"
            elif start_signal == "drum":
                start_sound_file = os.path.join("effects", "drum.wav")
                start_sound_label = "대북 타격음 (쿵!)"

            for s in range(1, sets_count + 1):
                step_name = step_types[(s - 1) % len(step_types)]

                # 1. 스텝 지시 음성 (intro_only 시 스텝명만 또렷하게 지시, each_set 시 기술명 함께 호명)
                if kick_announce_mode == "each_set" and kick_types:
                    kick_name = kick_types[(s - 1) % len(kick_types)]
                    cue_text = f"[{s}세트] {step_name}! {kick_name}!"
                else:
                    cue_text = f"[{s}세트] {step_name}!"

                cue_dur = max(1.0, round(len(cue_text) * 0.22, 2))
                events.append({
                    "time": curr_time,
                    "type": "voice",
                    "text": cue_text,
                    "duration": cue_dur,
                    "track": 2,
                    "vol": 2.5
                })
                duck_segments.append((int(curr_time * 1000), int((curr_time + cue_dur) * 1000)))

                # 스텝 유지 시간 동안 뛰기
                curr_time += step_sec

                # 2. 타격 시작 신호음 (삐익-!)
                events.append({
                    "time": curr_time,
                    "type": "signal",
                    "text": f"[{s}세트 연타 시작] {start_sound_label}",
                    "sound_file": start_sound_file,
                    "duration": 0.35,
                    "track": 1,
                    "vol": 3.0
                })
                duck_segments.append((int(curr_time * 1000), int((curr_time + 0.6) * 1000)))

                # 3. 전력 연타 시간 진행 (더 이상 매번 연타 종류를 길게 말하지 않고 전력 타격 집중)
                curr_time += combo_sec

                # 4. 연타 종료 신호 (갈려 / 중지 / 그만 / 비프음 / 휘슬 중 선택)
                if stop_signal == "voice_kalyeo":
                    events.append({
                        "time": curr_time,
                        "type": "voice",
                        "text": "[연타 종료] 갈려!",
                        "duration": 0.7,
                        "track": 2,
                        "vol": 2.8
                    })
                    duck_segments.append((int(curr_time * 1000), int((curr_time + 0.8) * 1000)))
                    curr_time += 0.8
                elif stop_signal == "voice_stop":
                    events.append({
                        "time": curr_time,
                        "type": "voice",
                        "text": "[연타 종료] 중지!",
                        "duration": 0.7,
                        "track": 2,
                        "vol": 2.8
                    })
                    duck_segments.append((int(curr_time * 1000), int((curr_time + 0.8) * 1000)))
                    curr_time += 0.8
                elif stop_signal == "voice_end":
                    events.append({
                        "time": curr_time,
                        "type": "voice",
                        "text": "[연타 종료] 그만!",
                        "duration": 0.7,
                        "track": 2,
                        "vol": 2.8
                    })
                    duck_segments.append((int(curr_time * 1000), int((curr_time + 0.8) * 1000)))
                    curr_time += 0.8
                elif stop_signal == "beep":
                    events.append({
                        "time": curr_time,
                        "type": "signal",
                        "text": "[연타 종료] 비프음",
                        "sound_file": os.path.join("effects", "beep.wav"),
                        "duration": 0.25,
                        "track": 1,
                        "vol": 3.0
                    })
                    duck_segments.append((int(curr_time * 1000), int((curr_time + 0.5) * 1000)))
                    curr_time += 0.5
                elif stop_signal == "whistle":
                    events.append({
                        "time": curr_time,
                        "type": "signal",
                        "text": "[연타 종료] 심판 호각",
                        "sound_file": os.path.join("effects", "whistle.wav"),
                        "duration": 0.35,
                        "track": 1,
                        "vol": 3.0
                    })
                    duck_segments.append((int(curr_time * 1000), int((curr_time + 0.5) * 1000)))
                    curr_time += 0.5
                else:  # 기본값 갈려
                    events.append({
                        "time": curr_time,
                        "type": "voice",
                        "text": "[연타 종료] 갈려!",
                        "duration": 0.7,
                        "track": 2,
                        "vol": 2.8
                    })
                    duck_segments.append((int(curr_time * 1000), int((curr_time + 0.8) * 1000)))
                    curr_time += 0.8

                # 세트 간 자연스러운 호흡 텀 (1.0초)
                curr_time += 1.0

            # 5. 모든 세트 종료 시 정중한 훈련 종료 멘트
            events.append({
                "time": curr_time + 0.3,
                "type": "bell",
                "text": "[훈련 완료]",
                "sound_file": os.path.join("effects", "stage_bell.wav"),
                "duration": 1.2,
                "track": 2,
                "vol": 1.5
            })
            default_outro = "훈련 종료! 모두 수고하셨습니다! 물 한잔 마시고 호흡을 가다듬으며 다음 지시를 위해 잠시 대기하세요."
            outro_text = params.get("outro_text", default_outro).strip() or default_outro
            outro_dur = max(3.5, round(len(outro_text) * 0.22, 2))
            events.append({
                "time": curr_time + 1.5,
                "type": "voice",
                "text": f"[훈련 종료] {outro_text}",
                "duration": outro_dur,
                "track": 2,
                "vol": 2.5
            })
            duck_segments.append((int((curr_time + 1.5) * 1000), int((curr_time + 1.5 + outro_dur + 0.5) * 1000)))
            total_duration_sec = curr_time + 1.5 + outro_dur + 2.0  # 종료 후 2초 이상의 넉넉한 딜레이 보장

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
