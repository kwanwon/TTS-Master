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


# ── 도장 고강도 기능성 서킷 인터벌 4대 테마 프리셋 ──
CIRCUIT_INTERVAL_THEMES = {
    "power_agility": {
        "name_kr": "⚡ [순발력 & 파워 점프 인터벌] 턱점프·앞차기·스쿼트점프·버피",
        "name_mix": "⚡ 순발력 & 파워 점프 인터벌 (하이니 점프 & 프론트 킥)",
        "name_dual": "⚡ 순발력 & 파워 인터벌 (Power & Agility)",
        "name_en": "⚡ Explosive Power & Jump Interval",
        "desc": "무릎 당겨 점프, 폭발적 앞차기 연속 타격, 쪼그려 점프, 전신 버피를 순환하여 폭발적 순발력 극대화",
        "exercises": [
            {
                "kr": "무릎 당겨 높이 점프! 무릎을 가슴까지 터치!",
                "mix": "하이니 점프(High knee jump)! 무릎 가슴 터치 렛츠 고!",
                "dual": "무릎 당겨 높이 점프! - Jump high and tuck knees to chest!",
                "en": "High knee tuck jumps, pull knees to chest!",
                "tip": "제자리에서 높이 뛰어올라 공중에서 양 무릎을 가슴 높이까지 끌어당깁니다."
            },
            {
                "kr": "폭발적 앞차기 연속 타격! 좌우 빠르게 차올리기!",
                "mix": "프론트 킥 투 더 페이스(Front kick)! 빠르게 레프트 라이트 킥!",
                "dual": "폭발적 앞차기 연속 타격! - Explosive front kicks left and right!",
                "en": "Explosive front kicks, power and speed!",
                "tip": "가드 올리고 좌우 번갈아 얼굴 높이로 전력 앞차기를 연속 타격합니다."
            },
            {
                "kr": "쪼그려 점프뛰기! 깊게 앉았다가 높이 점프!",
                "mix": "스쿼트 점프(Squat jump)! 딥 다운 앤 점프 하이!",
                "dual": "쪼그려 점프뛰기! - Squat down deep and jump high!",
                "en": "Squat jumps, push from your heels and jump!",
                "tip": "엉덩이를 뒤로 빼며 깊게 앉았다가 허벅지와 둔근 탄력으로 높이 뛰어오릅니다."
            },
            {
                "kr": "전신 버피 테스트! 엎드려, 뻗쳐, 모아, 점프!",
                "mix": "버피 점프(Burpee jump)! 다운, 백, 인, 점프 하이!",
                "dual": "전신 버피 점프! - Burpees, down, back, and jump!",
                "en": "Full burpee jumps, maximum power and speed!",
                "tip": "손 짚고 엎드려 뻗쳤다 다시 모아 공중으로 높이 점프합니다."
            }
        ]
    },
    "footwork_speed": {
        "name_kr": "🏃‍♂️ [민첩성 & 스텝 셔틀 인터벌] 사이드스텝·스위치·지그재그·발구르기",
        "name_mix": "🏃‍♂️ 민첩성 & 스피드 스텝 인터벌 (사이드 스텝 & 패스트 피트)",
        "name_dual": "🏃‍♂️ 민첩성 & 스피드 스텝 (Footwork & Agility)",
        "name_en": "🏃‍♂️ Fast Footwork & Agility Interval",
        "desc": "사이드 스텝 바닥 터치, 앞발/뒷발 빠른 스위치, 지그재그 회피 스텝, 초고속 발구르기",
        "exercises": [
            {
                "kr": "사이드 스텝 좌우 콘 터치! 빠르게 바닥 터치!",
                "mix": "사이드 스텝 터치(Side step touch)! 좌우 빠르게 핸드 터치!",
                "dual": "사이드 스텝 좌우 터치! - Side step shuffle and touch the floor!",
                "en": "Side step shuffles, touch the ground quick!",
                "tip": "자세를 낮추고 좌우로 민첩하게 2스텝 이동하여 바닥을 터치합니다."
            },
            {
                "kr": "앞발 뒷발 빠른 스위치! 자세 바꾸며 전격 발바꿔!",
                "mix": "스위치 스텝(Switch step)! 레그 체인지 빠르게 스위치!",
                "dual": "앞발 뒷발 빠른 발바꿔! - Fast switch footwork, change stance!",
                "en": "Fast stance switch, keep light on your feet!",
                "tip": "대련 자세에서 양발을 동시에 띄워 앞뒤 발을 초고속으로 전환합니다."
            },
            {
                "kr": "지그재그 회피 스텝 앤 고! 각도 꺾으며 전진!",
                "mix": "지그재그 스텝(Zigzag step)! 앵글 꺾고 전진 무브!",
                "dual": "지그재그 회피 스텝! - Zigzag footwork, change angles quickly!",
                "en": "Zigzag evasion footwork, move sharp and crisp!",
                "tip": "상대의 공격선을 벗어나 대각선으로 좌우 방향을 꺾으며 민첩하게 이동합니다."
            },
            {
                "kr": "제자리 초고속 발구르기 후 턴! 빠르게 발 구르기!",
                "mix": "패스트 피트(Fast feet)! 제자리 빠르게 구르고 턴!",
                "dual": "초고속 발구르기! - Fast feet on the spot, quick turn!",
                "en": "Fast feet sprint on the spot, turn and react!",
                "tip": "발끝으로 지면을 초고속으로 두드리며 순발력과 발목 탄력을 극대화합니다."
            }
        ]
    },
    "bodyweight_core": {
        "name_kr": "💪 [도장 전신 근력 & 코어 인터벌] 마운틴클라이머·푸시업·플랭크·V업",
        "name_mix": "💪 도장 근력 & 코어 인터벌 (푸시업 & 마운틴 클라이머)",
        "name_dual": "💪 전신 근력 & 코어 인터벌 (Bodyweight Strength & Core)",
        "name_en": "💪 Dojo Strength & Core HIIT",
        "desc": "마운틴 클라이머 전력 질주, 손바닥 푸시업, 플랭크 버티기, V업 복근 운동",
        "exercises": [
            {
                "kr": "마운틴 클라이머! 엎드려 무릎 가슴으로 전력 달리기!",
                "mix": "마운틴 클라이머(Mountain climber)! 무릎 체스트로 런(Run)!",
                "dual": "엎드려 무릎 달리기! - Mountain climbers, drive knees fast!",
                "en": "Mountain climbers, sprint knees to chest!",
                "tip": "엎드려 뻗쳐 자세에서 무릎을 번갈아 가슴 쪽으로 빠르게 차올립니다."
            },
            {
                "kr": "손바닥 팔굽혀펴기! 가슴 바닥까지 깊게 전력 수행!",
                "mix": "푸시업(Push-ups)! 체스트 바닥까지 다운 앤 업!",
                "dual": "손바닥 팔굽혀펴기! - Push-ups, chest to the floor!",
                "en": "Standard push-ups, keep straight and powerful!",
                "tip": "몸을 일직선으로 유지하며 가슴이 바닥에 닿을 때까지 힘차게 밀어냅니다."
            },
            {
                "kr": "코어 플랭크 버티기! 복근 엉덩이 힘 꽉 주고 버티기!",
                "mix": "플랭크 코어 홀드(Plank hold)! 락처럼 단단하게 홀드!",
                "dual": "플랭크 코어 버티기! - Plank hold, squeeze core tight!",
                "en": "Plank hold, keep your core locked and breathing!",
                "tip": "팔꿈치를 바닥에 대고 몸을 널빤지처럼 일직선으로 만들어 흔들림 없이 버팁니다."
            },
            {
                "kr": "누워서 V업 복근 치기! 손끝 발끝 모아올리기!",
                "mix": "V업 싯업(V-up sit-ups)! 손끝 발끝 터치 앤 다운!",
                "dual": "누워서 V업 복근 치기! - V-ups, touch toes with hands!",
                "en": "V-ups, fold your body and touch toes!",
                "tip": "누운 상태에서 상체와 다리를 동시에 V자로 들어 올려 손끝으로 발끝을 터치합니다."
            }
        ]
    },
    "combat_reaction": {
        "name_kr": "🥋 [대련 실전 & 반사신경 인터벌] 신호음 반응 나래차기·카운터·연타",
        "name_mix": "🥋 대련 실전 & 반사신경 인터벌 (스텝 & 카운터 킥)",
        "name_dual": "🥋 대련 실전 & 반사신경 (Combat Reaction & Kicks)",
        "name_en": "🥋 Sparring Reaction & Combo Interval",
        "desc": "스텝 뛰다 신호음에 즉시 반응 나래차기, 앞발 컷트 후 상단, 백스텝 카운터 뒤차기, 전진 3연타",
        "exercises": [
            {
                "kr": "스텝 유지 중 신호음에 즉시 반응 나래차기! 번개 타격!",
                "mix": "스텝 뛰다 삑 신호에 나래차기(Double kick)! 라이트닝 타격!",
                "dual": "신호음에 반응 나래차기! - Step and double kick on whistle!",
                "en": "Step and react with double fast kicks on signal!",
                "tip": "경쾌하게 스텝을 뛰다 휘슬 소리가 나면 0.1초 만에 공중 연타 나래차기를 꽂아 넣습니다."
            },
            {
                "kr": "앞발 컷트 견제 후 뒷발 돌려차기 상단! 연속 콤보!",
                "mix": "앞발 컷트(Cut) 후 백 레그 하이 킥(High kick)! 콤보!",
                "dual": "앞발 컷트 후 상단 돌려차기! - Front foot cut then high round kick!",
                "en": "Front foot cut check, then powerful high roundhouse kick!",
                "tip": "앞발로 상대 진입을 저지하고 즉시 뒷발을 끌어올려 머리 높이로 돌려찹니다."
            },
            {
                "kr": "백스텝 회피 후 전격 카운터 뒤차기! 강력한 반격!",
                "mix": "백스텝(Back step) 회피 후 카운터 백킥(Back kick)! 스트롱 반격!",
                "dual": "백스텝 후 카운터 뒤차기! - Back step and counter back kick!",
                "en": "Back step dodge and explosive counter back kick!",
                "tip": "상대의 공격 타이밍에 맞춰 뒤로 한 걸음 빠진 뒤 몸을 회전하며 뒤꿈치로 명치를 꽂습니다."
            },
            {
                "kr": "전진 원투 몸통 3연타 폭풍 타격! 밀고 들어가기!",
                "mix": "원투쓰리 콤보 3연타! 전진하며 스트롱 바디 킥!",
                "dual": "전진 3연타 폭풍 타격! - Push forward with three continuous kicks!",
                "en": "Continuous three-strike combo, push forward aggressively!",
                "tip": "스텝을 밀고 들어가며 원투쓰리 3연타를 쉼 없이 몰아붙여 타격합니다."
            }
        ]
    }
}


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
        },
        "circuit": {
            "name": "🔥 도장 기능성 서킷 인터벌 (HIIT & Tabata)",
            "desc": "순발력, 민첩성, 근력, 반사신경, 대련 스텝/발차기 4대 기능 결합 고강도 인터벌"
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

        # ── Mode 5: 도장 고강도 기능성 서킷 인터벌 (HIIT & Tabata) ──
        elif mode == "circuit":
            work_sec = float(params.get("work_sec", 20.0))    # 운동 시간 (기본 20초)
            rest_sec = float(params.get("rest_sec", 10.0))    # 휴식 시간 (기본 10초)
            total_sets = int(params.get("sets_count", 8))     # 총 세트 수 (기본 8세트)
            theme_key = params.get("theme_key", "power_agility")
            lang = params.get("language_mode", "kr")          # kr / mix_kids / dual_step / en_advanced

            theme_data = CIRCUIT_INTERVAL_THEMES.get(theme_key, CIRCUIT_INTERVAL_THEMES["power_agility"])
            exercises = params.get("custom_exercises", [])
            if not exercises:
                exercises = theme_data["exercises"]

            lang_key = "mix" if lang == "mix_kids" else ("dual" if lang == "dual_step" else ("en" if lang in ("en", "en_advanced") else "kr"))
            theme_title = theme_data.get(f"name_{lang_key}", theme_data["name_kr"])

            # 사전 안내 (모드 5 전용 맞춤)
            if intro_enabled:
                if lang == "mix_kids":
                    intro_text = f"지금부터 도장 하이 파워 인터벌(HIIT) 스타트! 이번 테마는 {theme_title}입니다. 운동 타임에 전력으로 무브하고, 레스트(Rest) 타임에 호흡 릴랙스! 준비해 주세요!"
                elif lang == "dual_step":
                    intro_text = f"지금부터 고강도 서킷 인터벌 훈련을 시작합니다. - High intensity interval training! 테마는 '{theme_title}'입니다. 운동 시간에 전력으로 집중하고, 휴식 시간에 호흡을 가다듬으세요. 모두 준비!"
                elif lang in ("en", "en_advanced"):
                    intro_text = f"Attention team! Today's circuit interval training theme is {theme_title}. Give your 100 percent during work intervals, and breathe deep during rest! Line up and get ready!"
                else:
                    intro_text = f"지금부터 도장 고강도 기능성 서킷 인터벌 훈련을 시작합니다! 이번 테마는 '{theme_title}'입니다. 운동 시간 동안 전력으로 수행하고, 휴식 시간 동안 호흡을 가다듬으세요. 모두 준비해 주세요!"

                intro_dur = max(3.5, round(len(intro_text) * 0.22, 2))
                events.append({
                    "time": curr_time,
                    "type": "voice",
                    "text": f"[인터벌 사전 안내] {intro_text}",
                    "duration": intro_dur,
                    "track": 2,
                    "vol": 2.5
                })
                duck_segments.append((int(curr_time * 1000), int((curr_time + intro_dur + 0.5) * 1000)))
                curr_time += intro_dur + 1.2

            # 카운트다운 (Ready, Three, Two, One)
            if countdown_enabled:
                cd_text = "[카운트다운] Three, Two, One"
                cd_dur = 4.3
                events.append({
                    "time": curr_time,
                    "type": "countdown",
                    "text": cd_text,
                    "cd_style": cd_style,
                    "sound_file": os.path.join("effects", "countdown.wav"),
                    "duration": cd_dur,
                    "track": 2,
                    "vol": 2.0
                })
                duck_segments.append((int(curr_time * 1000), int((curr_time + cd_dur) * 1000)))
                curr_time += cd_dur + 1.0

            # 세트 반복 루프
            for s in range(1, total_sets + 1):
                ex_idx = (s - 1) % len(exercises)
                cur_ex = exercises[ex_idx]
                if isinstance(cur_ex, dict):
                    ex_name = cur_ex.get(lang_key, cur_ex.get("kr", "전력 수행!"))
                else:
                    ex_name = str(cur_ex)

                # 1. 동작 호명 및 준비
                call_text = f"[{s}세트] {ex_name}!"
                call_dur = max(1.5, round(len(call_text) * 0.20, 2))
                events.append({
                    "time": curr_time,
                    "type": "voice",
                    "text": call_text,
                    "duration": call_dur,
                    "track": 2,
                    "vol": 2.5
                })
                duck_segments.append((int(curr_time * 1000), int((curr_time + call_dur) * 1000)))
                curr_time += call_dur + 0.3

                # 2. 운동 시작 휘슬 (삐익~!)
                events.append({
                    "time": curr_time,
                    "type": "whistle",
                    "text": f"[{s}세트 시작 휘슬] 삐익~!",
                    "sound_file": os.path.join("effects", "whistle.wav"),
                    "duration": 0.35,
                    "track": 1,
                    "vol": 3.0
                })
                duck_segments.append((int(curr_time * 1000), int((curr_time + 0.6) * 1000)))
                curr_time += 0.4

                # 3. 운동 진행 및 종료 3초 전 카운트다운 비프
                if work_sec >= 7:
                    warn_time = curr_time + work_sec - 3.0
                    for b in range(3):
                        b_t = warn_time + b * 1.0
                        events.append({
                            "time": b_t,
                            "type": "beep",
                            "text": f"[마무리 알림 {3-b}]",
                            "sound_file": os.path.join("effects", "beep.wav"),
                            "duration": 0.25,
                            "track": 1,
                            "vol": 1.5
                        })
                        duck_segments.append((int(b_t * 1000), int((b_t + 0.3) * 1000)))

                curr_time += work_sec

                # 4. 세트 종료 신호 (벨 / 호각)
                is_final_set = (s == total_sets)
                if not is_final_set:
                    # 휴식 전환 벨
                    events.append({
                        "time": curr_time,
                        "type": "bell",
                        "text": f"[{s}세트 종료] 갈려! 휴식!",
                        "sound_file": os.path.join("effects", "stage_bell.wav"),
                        "duration": 0.8,
                        "track": 1,
                        "vol": 2.2
                    })

                    # 휴식 안내 멘트
                    if lang == "mix_kids":
                        rest_ment = "릴랙스 휴식! 딥 브레스 쉬고 다음 동작 웨이트!"
                    elif lang == "dual_step":
                        rest_ment = "휴식! 호흡 가다듬으세요. - Rest, catch your breath!"
                    elif lang in ("en", "en_advanced"):
                        rest_ment = "Rest and breathe! Next exercise coming up!"
                    else:
                        rest_ment = "휴식! 호흡 가다듬고 다음 동작 준비하세요."

                    r_dur = max(1.8, round(len(rest_ment) * 0.20, 2))
                    events.append({
                        "time": curr_time + 0.5,
                        "type": "voice",
                        "text": f"[휴식] {rest_ment}",
                        "duration": r_dur,
                        "track": 2,
                        "vol": 2.2
                    })
                    duck_segments.append((int((curr_time + 0.5) * 1000), int((curr_time + 0.5 + r_dur) * 1000)))
                    curr_time += rest_sec
                else:
                    # 마지막 세트 완료
                    events.append({
                        "time": curr_time,
                        "type": "bell",
                        "text": "[최종 세트 종료] 훈련 완료!",
                        "sound_file": os.path.join("effects", "stage_bell.wav"),
                        "duration": 1.2,
                        "track": 1,
                        "vol": 2.5
                    })
                    curr_time += 1.0

            # 5. 인터벌 훈련 완료 멘트
            if lang == "mix_kids":
                final_outro = "고강도 인터벌 훈련 종료! 굿 잡! 모두 수고했습니다! 워터(Water) 물 한잔 마시고 호흡을 릴랙스 가다듬으세요!"
            elif lang == "dual_step":
                final_outro = "인터벌 훈련 종료! 모두 수고하셨습니다! - Great workout everyone! Drink some water and relax!"
            elif lang in ("en", "en_advanced"):
                final_outro = "Interval training complete! Outstanding effort team! Drink water, catch your breath, and wait for next instruction!"
            else:
                final_outro = "고강도 인터벌 훈련 종료! 모두 수고하셨습니다! 물 한잔 마시고 호흡을 가다듬으며 다음 지시를 위해 잠시 대기하세요."

            outro_dur = max(3.5, round(len(final_outro) * 0.22, 2))
            events.append({
                "time": curr_time + 0.5,
                "type": "voice",
                "text": f"[훈련 종료] {final_outro}",
                "duration": outro_dur,
                "track": 2,
                "vol": 2.5
            })
            duck_segments.append((int((curr_time + 0.5) * 1000), int((curr_time + 0.5 + outro_dur + 0.5) * 1000)))
            total_duration_sec = curr_time + 0.5 + outro_dur + 2.0
        else:
            total_duration_sec = 60.0

        return {
            "total_duration_sec": total_duration_sec,
            "events": events,
            "duck_segments": duck_segments
        }
