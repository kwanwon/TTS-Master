"""
Warmup, Stretching, and Mobility Audio Engine (준비운동·스트레칭·요가 오디오 엔진)
Author: Gemini & Antigravity
Supports customizable martial arts dojo & fitness routines:
1. Standard Full Routine (정규 정통 풀코스 관절체조)
2. Quick Express Routine (약식 쾌속 코스)
3. Warmup & Agility Routine (약식 + 워밍업/스텝 집중)
4. Flexibility & Kicking Routine (약식 + 다리찢기/유연성 집중)
5. Yoga & Pilates Core Routine (요가/필라테스 척추·코어 밸런스)
6. Custom Routine (사용자 맞춤형 자유 편집)

Features:
- Korean & Easy Kids English dual-language instruction
- Traditional forward & back bend details (Hands touch -> Elbows touch -> Look up back bend)
- Detailed coaching explanation vs. Fast cue-only mode toggle
- Multiple start & end announcements
- Auto-ducking BGM mixing & BPM tempo control
"""

import os
import copy
from typing import List, Dict, Any, Tuple
from pydub import AudioSegment


# 1. 동작 기본 마스터 데이터베이스 (Master Movement Definitions)
MASTER_MOVEMENTS: List[Dict[str, Any]] = [
    {
        "id": "wrist_ankle",
        "name_kr": "손목·발목 털고 돌리기",
        "name_en": "Wrist & Ankle Circles",
        "instruction_kr": "양손 깍지 끼고, 왼발부터 손목 발목 부드럽게 돌려주기! 발 바꿔서 반대로!",
        "instruction_en": "Shake your hands and feet! Roll them round and round!",
        "short_cue_kr": "손목 발목 돌리기, 시작!",
        "short_cue_en": "Roll wrists and ankles, go!",
        "count_type": "8count_x2",
        "default_duration_sec": 16.0,
        "category": "joint"
    },
    {
        "id": "knee_bends",
        "name_kr": "무릎 굽혀펴기",
        "name_en": "Knee Bends & Stretch",
        "instruction_kr": "양손 무릎 위에 올리고, 가볍게 굽혔다 펴기! 준비~ 시작!",
        "instruction_en": "Hands on your knees! Bend and stretch!",
        "short_cue_kr": "무릎 굽혀펴기, 시작!",
        "short_cue_en": "Knee bends, ready go!",
        "count_type": "8count_x2",
        "default_duration_sec": 16.0,
        "category": "joint"
    },
    {
        "id": "knee_circles",
        "name_kr": "무릎 돌려주기 (안팎 회전)",
        "name_en": "Knee Circles",
        "instruction_kr": "무릎 안에서 밖으로 돌려주기! 이어서 밖에서 안으로!",
        "instruction_en": "Roll your knees inside out! Now outside in!",
        "short_cue_kr": "무릎 돌리기, 시작!",
        "short_cue_en": "Roll your knees, go!",
        "count_type": "8count_x2",
        "default_duration_sec": 16.0,
        "category": "joint"
    },
    {
        "id": "knee_press_short",
        "name_kr": "무릎 눌러주기 (짧게 누르기)",
        "name_en": "Short Stance Knee Press",
        "instruction_kr": "다리 어깨너비로 벌리고, 왼쪽부터 짧게 눌러주기! 반대쪽!",
        "instruction_en": "Push your knees softly! Switch sides!",
        "short_cue_kr": "짧게 눌러주기, 시작!",
        "short_cue_en": "Short knee stretch, go!",
        "count_type": "8count_x2",
        "default_duration_sec": 16.0,
        "category": "stretch"
    },
    {
        "id": "deep_lunge_side",
        "name_kr": "길게 앉아 무릎 누르기",
        "name_en": "Deep Side Lunge Stretch",
        "instruction_kr": "다리 넓게 벌리고 깊숙이 앉아서 무릎 지긋이 눌러주기! 발끝 하늘로, 반대쪽!",
        "instruction_en": "Sit down low! Stretch your leg, toe to the sky! Switch sides!",
        "short_cue_kr": "길게 눌러주기, 시작!",
        "short_cue_en": "Deep lunge stretch, go!",
        "count_type": "8count_x2",
        "default_duration_sec": 18.0,
        "category": "stretch"
    },
    {
        "id": "hip_torso_twist",
        "name_kr": "골반-허리 틀기 (어깨 넣기)",
        "name_en": "Shoulder Drop & Torso Twist",
        "instruction_kr": "양손 허벅지 짚고, 오른쪽 어깨 깊숙이 밀어 넣으며 시선 뒤쪽! 반대쪽 어깨!",
        "instruction_en": "Drop your shoulder down, look behind you! Switch shoulders!",
        "short_cue_kr": "어깨 집어넣기, 시작!",
        "short_cue_en": "Shoulder twist, go!",
        "count_type": "8count_x2",
        "default_duration_sec": 16.0,
        "category": "stretch"
    },
    {
        "id": "waist_circles",
        "name_kr": "허리 돌려주기",
        "name_en": "Waist & Hip Circles",
        "instruction_kr": "양손 허리에 얹고, 왼쪽부터 허리 크게 돌려주기! 반대로 돌리기!",
        "instruction_en": "Hands on your hips! Big circles with your belly! Reverse!",
        "short_cue_kr": "허리 돌리기, 시작!",
        "short_cue_en": "Circle your hips, go!",
        "count_type": "8count_x2",
        "default_duration_sec": 16.0,
        "category": "joint"
    },
    {
        "id": "torso_twist",
        "name_kr": "몸통 틀어주기 (상체 비틀기)",
        "name_en": "Upper Body Torso Twists",
        "instruction_kr": "양팔 팔꿈치 접고 가슴 높이, 좌우로 몸통 털며 비틀기! 시선도 함께!",
        "instruction_en": "Twist your body left and right! Swing your arms!",
        "short_cue_kr": "몸통 틀기, 시작!",
        "short_cue_en": "Twist body, go!",
        "count_type": "8count_x2",
        "default_duration_sec": 16.0,
        "category": "joint"
    },
    {
        "id": "forward_back_bend",
        "name_kr": "등배운동 (손바닥·팔꿈치·뒤로)",
        "name_en": "Hands, Elbows & Back Bends",
        "instruction_kr": "등배운동! 앞으로 숙여 손바닥 바닥 터치, 팔꿈치 바닥 터치, 양손 허리 받치고 뒤로 젖히기! 준비~ 시작!",
        "instruction_en": "Touch hands, touch elbows, look up at the ceiling! Ready, go!",
        "short_cue_kr": "등배운동, 시작!",
        "short_cue_en": "Forward and back bends, go!",
        "count_type": "forward_back_8count",
        "default_duration_sec": 18.0,
        "category": "stretch"
    },
    {
        "id": "full_torso_circle",
        "name_kr": "몸통 크게 돌려주기",
        "name_en": "Full Torso Windmill Circles",
        "instruction_kr": "양팔 머리 위로 들고, 몸통 크게 원을 그리며 돌려주기! 반대로 돌리기!",
        "instruction_en": "Arms up high! Make a giant circle like a giant tree! Reverse!",
        "short_cue_kr": "몸통 크게 돌리기, 시작!",
        "short_cue_en": "Giant circles, go!",
        "count_type": "8count_x2",
        "default_duration_sec": 16.0,
        "category": "joint"
    },
    {
        "id": "windmill_toe_touch",
        "name_kr": "발목 교대 터치 (풍차 운동)",
        "name_en": "Alternating Toe Touches",
        "instruction_kr": "다리 넓게 벌리고 양팔 벌려, 오른손 왼발목 왼손 오른발목 번갈아 터치!",
        "instruction_en": "Arms wide open! Touch your left toe, touch your right toe!",
        "short_cue_kr": "발목 교대 터치, 시작!",
        "short_cue_en": "Touch your toes, go!",
        "count_type": "8count_x2",
        "default_duration_sec": 16.0,
        "category": "stretch"
    },
    {
        "id": "shoulder_arm_circles",
        "name_kr": "어깨 짧게/크게 돌리기",
        "name_en": "Shoulder & Big Arm Circles",
        "instruction_kr": "양손 어깨 얹고 짧게 돌리기, 이어서 양팔 펴서 앞으로 뒤로 크게 돌리기!",
        "instruction_en": "Small circles with shoulders, big flying circles with arms!",
        "short_cue_kr": "어깨 돌리기, 시작!",
        "short_cue_en": "Arm circles, go!",
        "count_type": "8count_x2",
        "default_duration_sec": 16.0,
        "category": "joint"
    },
    {
        "id": "neck_stretches",
        "name_kr": "목 운동 (전후좌우 및 돌리기)",
        "name_en": "Neck Stretch & Circles",
        "instruction_kr": "양손 허리, 목 앞으로 숙이고 뒤로 젖히기, 좌우 숙이고, 천천히 돌려주기!",
        "instruction_en": "Look down, look up, look side to side, and roll softly!",
        "short_cue_kr": "목 운동, 시작!",
        "short_cue_en": "Neck stretch, go!",
        "count_type": "8count_x2",
        "default_duration_sec": 16.0,
        "category": "joint"
    },
    {
        "id": "jumping_jacks",
        "name_kr": "팔 벌려 뛰기 (점핑잭 10회)",
        "name_en": "Jumping Jacks (10 reps)",
        "instruction_kr": "체온 올리기! 팔 벌려 뛰기 10회 준비, 시작!",
        "instruction_en": "Jumping jacks! Ten times! Ready, go!",
        "short_cue_kr": "팔 벌려 뛰기 10회, 시작!",
        "short_cue_en": "Jumping jacks, ready go!",
        "count_type": "reps_10",
        "default_duration_sec": 14.0,
        "category": "cardio"
    },
    {
        "id": "breathing_reset",
        "name_kr": "숨고르기 및 정렬",
        "name_en": "Deep Breathing & Reset",
        "instruction_kr": "호흡 가다듬기, 숨 깊게 들이마시고... 천천히 내쉬고... 바로! 차렷!",
        "instruction_en": "Big breath in through your nose... and blow out! Attention!",
        "short_cue_kr": "숨고르기, 심호흡!",
        "short_cue_en": "Deep breaths in and out!",
        "count_type": "breathing",
        "default_duration_sec": 12.0,
        "category": "cardio"
    },
    # 추가 전문 동작 (선수부 / 하체 모빌리티)
    {
        "id": "hip_dynamic_rotation",
        "name_kr": "고관절 다이나믹 회전 (안팎 차올리기)",
        "name_en": "Dynamic Hip Opener Kicks",
        "instruction_kr": "무릎 직각으로 들어 올려 안에서 밖으로 크게 차올리기! 반대 다리 교대!",
        "instruction_en": "Knee up high, open your hip wide! Switch legs!",
        "short_cue_kr": "고관절 회전, 시작!",
        "short_cue_en": "Hip circles kick, go!",
        "count_type": "8count_x2",
        "default_duration_sec": 16.0,
        "category": "mobility"
    },
    {
        "id": "lunge_hip_flexor",
        "name_kr": "장요근 런지 바운스 스트레칭",
        "name_en": "Lunge Hip Stretch",
        "instruction_kr": "앞굽이 길게 딛고 골반을 바닥으로 지긋이 눌러주기! 반대쪽 교대!",
        "instruction_en": "Big step forward! Push your hips down low! Switch legs!",
        "short_cue_kr": "런지 스트레칭, 시작!",
        "short_cue_en": "Lunge stretch, go!",
        "count_type": "8count_x2",
        "default_duration_sec": 18.0,
        "category": "mobility"
    },
    {
        "id": "hamstring_high_kick",
        "name_kr": "햄스트링 프론트 스윙 킥",
        "name_en": "High Kick Leg Swings",
        "instruction_kr": "무릎 펴고 앞차기 높이 가볍게 차올리기! 왼발 오른발 교대!",
        "instruction_en": "Straight leg kick up high to your hand! Switch legs!",
        "short_cue_kr": "앞차기 스윙, 시작!",
        "short_cue_en": "High kick swings, go!",
        "count_type": "8count_x2",
        "default_duration_sec": 16.0,
        "category": "mobility"
    },
    # 추가 전문 동작 (매트 유연성 / 다리 찢기)
    {
        "id": "butterfly_pose",
        "name_kr": "나비 자세 (골반 열기)",
        "name_en": "Butterfly Stretch",
        "instruction_kr": "바닥에 앉아 발바닥 맞대고, 무릎을 바닥으로 지긋이 눌러줍니다.",
        "instruction_en": "Sit down, feet together like a butterfly! Push knees down gently!",
        "short_cue_kr": "나비 자세, 시작!",
        "short_cue_en": "Butterfly stretch, go!",
        "count_type": "hold_15s",
        "default_duration_sec": 20.0,
        "category": "flexibility"
    },
    {
        "id": "straddle_splits",
        "name_kr": "다리 벌려 좌우 숙이기",
        "name_en": "V-Sit Straddle Stretch",
        "instruction_kr": "다리 V자로 넓게 벌리고 왼쪽으로 숙이기, 이어서 오른쪽, 중앙으로 숙이기!",
        "instruction_en": "Legs open wide in a big V! Reach left, reach right, reach forward!",
        "short_cue_kr": "다리 벌려 숙이기, 시작!",
        "short_cue_en": "Straddle stretch, go!",
        "count_type": "8count_x4",
        "default_duration_sec": 25.0,
        "category": "flexibility"
    },
    # 추가 전문 동작 (요가 & 필라테스)
    {
        "id": "cat_cow_flow",
        "name_kr": "캣카우 (고양이·소 척추 이완)",
        "name_en": "Cat & Cow Stretch",
        "instruction_kr": "테이블 자세에서 숨 들이마시며 가슴 열고, 내쉬며 등 둥글게 말아올리기!",
        "instruction_en": "Hands and knees on floor! Look up like a cow, round back like a cat!",
        "short_cue_kr": "캣카우, 시작!",
        "short_cue_en": "Cat and cow, go!",
        "count_type": "breathing_cycle",
        "default_duration_sec": 22.0,
        "category": "yoga"
    },
    {
        "id": "downward_dog",
        "name_kr": "다운독 (견상 자세)",
        "name_en": "Downward Dog Stretch",
        "instruction_kr": "엉덩이를 천장으로 밀어 올리고, 뒤꿈치 바닥 누르며 종아리와 어깨 늘리기!",
        "instruction_en": "Push your hips up high like a triangle tent! Push heels down!",
        "short_cue_kr": "다운독 자세, 유지!",
        "short_cue_en": "Downward dog, hold!",
        "count_type": "hold_15s",
        "default_duration_sec": 20.0,
        "category": "yoga"
    },
    {
        "id": "child_pose",
        "name_kr": "아기 자세 (전신 이완 휴식)",
        "name_en": "Child's Rest Pose",
        "instruction_kr": "엉덩이 뒤꿈치에 얹고 이마 바닥, 온몸에 힘을 빼고 편안하게 호흡합니다.",
        "instruction_en": "Sit on your heels, forehead to the floor. Rest and breathe softly.",
        "short_cue_kr": "아기 자세 휴식!",
        "short_cue_en": "Rest in child pose.",
        "count_type": "hold_15s",
        "default_duration_sec": 18.0,
        "category": "yoga"
    }
]


# 2. 시작 및 종료 멘트 모음 (Start & End Cues)
START_CUES = {
    "kr": [
        "전체 차렷, 준비운동 시작하겠습니다! 다 같이 큰 소리로 구령 붙입니다.",
        "오늘 수련도 부상 없이 다치지 않게 온몸을 부드럽게 풀어줍니다. 힘차게 준비운동 시작!",
        "자, 모두 제자리 정렬! 가벼운 마음으로 몸풀기부터 힘차게 시작해 봅시다!",
        "오늘 훈련을 위해 관절과 근육을 깨워주겠습니다. 준비운동 시작하겠습니다!"
    ],
    "en": [
        "Attention! Line up everyone! Let's warm up our bodies! Are you ready?",
        "Hello team! Time to stretch and get strong! Ready, set, go!",
        "Let's get ready for training! Big voices, follow me! Let's go!"
    ]
}

END_CUES = {
    "kr": [
        "수고하셨습니다! 가볍게 물 한 잔 마시고 본 수련 대기하세요.",
        "준비운동 끝! 호흡 가다듬고 바른 자세로 제자리에 앉아서 대기합니다.",
        "몸풀기 완료! 매트 정리하고 다음 훈련 위치로 이동합니다.",
        "수고했습니다! 심호흡 세 번 하고 본 운동에 집중해 주세요."
    ],
    "en": [
        "Awesome job! Drink some water and wait for the Master!",
        "Great work everyone! Sit down nicely and take a deep breath!",
        "All done! Excellent effort! Ready for next training!"
    ]
}


# 3. 5대 대표 루틴 프리셋 (Routine Presets)
ROUTINE_PRESETS = {
    "standard_full": {
        "name_kr": "🥋 [도장 정통 풀코스] 전신 관절 체조 (약 7~8분)",
        "name_en": "🥋 Full Master Routine (7-8 min)",
        "description_kr": "머리부터 발끝까지 15가지 동작을 정석대로 꼼꼼하게 푸는 도장 정통 체조",
        "movement_ids": [
            "wrist_ankle", "knee_bends", "knee_circles", "knee_press_short",
            "deep_lunge_side", "hip_torso_twist", "waist_circles", "torso_twist",
            "forward_back_bend", "full_torso_circle", "windmill_toe_touch",
            "shoulder_arm_circles", "neck_stretches", "jumping_jacks", "breathing_reset"
        ],
        "default_tempo_bpm": 85
    },
    "quick_express": {
        "name_kr": "⚡ [약식 쾌속 코스] 핵심 7대 관절 풀기 (약 3~4분)",
        "name_en": "⚡ Quick Express Routine (3-4 min)",
        "description_kr": "시간이 촉박할 때 꼭 필요한 핵심 관절 7가지만 빠르게 순환",
        "movement_ids": [
            "wrist_ankle", "knee_bends", "deep_lunge_side", "forward_back_bend",
            "waist_circles", "neck_stretches", "jumping_jacks", "breathing_reset"
        ],
        "default_tempo_bpm": 90
    },
    "warmup_agility": {
        "name_kr": "🔥 [약식 + 워밍업 집중] 체온 상승 & 스텝 모빌리티 (약 6분)",
        "name_en": "🔥 Warm-up & Agility Routine (6 min)",
        "description_kr": "관절을 가볍게 푼 후 점핑잭과 고관절 다이나믹 스윙으로 심박수 상승",
        "movement_ids": [
            "wrist_ankle", "knee_circles", "deep_lunge_side", "hip_torso_twist",
            "forward_back_bend", "hip_dynamic_rotation", "hamstring_high_kick",
            "jumping_jacks", "breathing_reset"
        ],
        "default_tempo_bpm": 95
    },
    "stretch_flexibility": {
        "name_kr": "🦵 [약식 + 스트레칭 집중] 고관절 가동성 & 다리 찢기 (약 8분)",
        "name_en": "🦵 Kicking & Flexibility Routine (8 min)",
        "description_kr": "하체 유연성과 발차기 각도를 위해 런지, 나비자세, 다리벌려 숙이기 집중",
        "movement_ids": [
            "knee_bends", "deep_lunge_side", "hip_torso_twist", "forward_back_bend",
            "lunge_hip_flexor", "butterfly_pose", "straddle_splits", "breathing_reset"
        ],
        "default_tempo_bpm": 70
    },
    "yoga_pilates": {
        "name_kr": "🧘‍♀️ [요가 & 필라테스] 척추 정렬 & 코어 밸런스 (약 9분)",
        "name_en": "🧘‍♀️ Yoga & Core Balance (9 min)",
        "description_kr": "복식 호흡과 함께 캣카우, 다운독, 아기자세로 몸의 중심을 잡는 코스",
        "movement_ids": [
            "neck_stretches", "shoulder_arm_circles", "waist_circles", "cat_cow_flow",
            "downward_dog", "child_pose", "breathing_reset"
        ],
        "default_tempo_bpm": 60
    }
}


class WarmupEngine:
    """
    준비운동·스트레칭·요가 오디오 시퀀서 엔진
    - 타임라인 이벤트 배치
    - 한국어/영어 카운트 및 사범 멘트 타이밍 계산
    - 배경음악 자동 오토 더킹(Auto-Ducking) 연동
    """

    @classmethod
    def get_movement_dict(cls) -> Dict[str, Dict[str, Any]]:
        return {m["id"]: m for m in MASTER_MOVEMENTS}

    @classmethod
    def build_timeline_events(cls, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        주어진 옵션에 맞춰 정확한 타임라인 이벤트 목록과 오토 더킹 구간을 생성함.
        params:
            - routine_key: 'standard_full', 'quick_express', etc.
            - movements: List[Dict] (커스텀 동작 리스트)
            - coaching_mode: 'detailed' (상세 설명) or 'quick' (명칭만)
            - language: 'kr' or 'en'
            - tempo_bpm: int (60 ~ 110, default 85)
            - start_cue: str
            - end_cue: str
            - signal_type: 'bell' | 'beep' | 'whistle'
            - transition_gap_sec: float (동작 간 여백 초, default 1.5)
        """
        lang = params.get("language", "kr")
        mode = params.get("coaching_mode", "detailed")
        bpm = params.get("tempo_bpm", 85)
        signal_type = params.get("signal_type", "bell")
        trans_gap = params.get("transition_gap_sec", 1.5)

        # 1박자당 소요 시간 (초 단위)
        beat_interval = 60.0 / max(40, min(140, bpm))

        events: List[Dict[str, Any]] = []
        duck_segments: List[Tuple[int, int]] = []

        curr_time = 1.0  # 시작 1초 여백

        # 1. 시작 멘트 (Start Cue)
        start_cue = params.get("start_cue", "").strip()
        if not start_cue:
            start_cue = START_CUES[lang][0]

        start_dur_est = max(3.0, len(start_cue) * (0.13 if lang == "kr" else 0.08))
        events.append({
            "time": round(curr_time, 2),
            "type": "voice",
            "text": start_cue,
            "sound_file": "",
            "track": 3,
            "duration": round(start_dur_est, 2)
        })
        duck_segments.append((int(curr_time * 1000), int((curr_time + start_dur_est + 0.5) * 1000)))
        curr_time += start_dur_est + trans_gap

        # 2. 동작 시퀀스 순회
        movement_list = params.get("movements", [])
        if not movement_list:
            routine_key = params.get("routine_key", "standard_full")
            p_data = ROUTINE_PRESETS.get(routine_key, ROUTINE_PRESETS["standard_full"])
            m_dict = cls.get_movement_dict()
            movement_list = [copy.deepcopy(m_dict[mid]) for mid in p_data["movement_ids"] if mid in m_dict]

        for idx, mov in enumerate(movement_list):
            if not mov.get("enabled", True):
                continue

            # (1) 동작 전환 신호음 (차임벨 / 비프음)
            sig_file = "stage_bell.wav" if signal_type == "bell" else ("whistle.wav" if signal_type == "whistle" else "beep.wav")
            events.append({
                "time": round(curr_time, 2),
                "type": "bell" if signal_type == "bell" else "beep",
                "text": f"[{mov.get('name_kr' if lang == 'kr' else 'name_en')}]",
                "sound_file": sig_file,
                "track": 2,
                "duration": 0.8
            })
            curr_time += 0.8

            # (2) 사범 안내 멘트
            if mode == "detailed":
                coach_text = mov.get(f"instruction_{lang}", mov.get("instruction_kr", ""))
            else:
                coach_text = mov.get(f"short_cue_{lang}", mov.get("short_cue_kr", ""))

            coach_dur = max(2.0, len(coach_text) * (0.12 if lang == "kr" else 0.07))
            events.append({
                "time": round(curr_time, 2),
                "type": "voice",
                "text": coach_text,
                "sound_file": "",
                "track": 3,
                "duration": round(coach_dur, 2)
            })
            duck_segments.append((int(curr_time * 1000), int((curr_time + coach_dur + 0.3) * 1000)))
            curr_time += coach_dur + 0.5

            # (3) 구령 및 카운트다운 생성
            count_type = mov.get("count_type", "8count_x2")
            count_events, count_dur = cls._generate_count_events(
                count_type=count_type,
                lang=lang,
                start_time=curr_time,
                beat_interval=beat_interval
            )
            for ce in count_events:
                events.append(ce)

            if count_events:
                duck_segments.append((int(curr_time * 1000), int((curr_time + count_dur + 0.3) * 1000)))
                curr_time += count_dur + trans_gap
            else:
                curr_time += trans_gap

        # 3. 종료 멘트 (End Cue)
        end_cue = params.get("end_cue", "").strip()
        if not end_cue:
            end_cue = END_CUES[lang][0]

        end_dur_est = max(3.0, len(end_cue) * (0.13 if lang == "kr" else 0.08))
        events.append({
            "time": round(curr_time, 2),
            "type": "voice",
            "text": end_cue,
            "sound_file": "",
            "track": 3,
            "duration": round(end_dur_est, 2)
        })
        duck_segments.append((int(curr_time * 1000), int((curr_time + end_dur_est + 0.5) * 1000)))
        curr_time += end_dur_est + 1.0

        total_duration = round(curr_time, 2)

        return {
            "total_duration_sec": total_duration,
            "events": events,
            "duck_segments": duck_segments,
            "tempo_bpm": bpm,
            "language": lang,
            "coaching_mode": mode
        }

    @classmethod
    def _generate_count_events(
        cls,
        count_type: str,
        lang: str,
        start_time: float,
        beat_interval: float
    ) -> Tuple[List[Dict[str, Any]], float]:
        """
        카운트 타입에 따른 박자별 구령 이벤트 생성
        """
        c_events: List[Dict[str, Any]] = []
        t = start_time

        # 1. 8박자 한국어 / 영어
        kr_counts_set1 = ["하나", "둘", "셋", "넷", "다섯", "여섯", "일곱", "여덟"]
        kr_counts_set2 = ["둘", "둘", "셋", "넷", "다섯", "여섯", "일곱", "여덟"]
        kr_counts_set3 = ["셋", "둘", "셋", "넷", "다섯", "여섯", "일곱", "여덟"]
        kr_counts_set4 = ["넷", "둘", "셋", "넷", "다섯", "여섯", "일곱", "여덟"]

        en_counts_set1 = ["One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight"]
        en_counts_set2 = ["Two", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight"]
        en_counts_set3 = ["Three", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight"]
        en_counts_set4 = ["Four", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight"]

        if count_type == "8count_x2":
            sets = [
                (kr_counts_set1 if lang == "kr" else en_counts_set1),
                (kr_counts_set2 if lang == "kr" else en_counts_set2)
            ]
            for s in sets:
                for word in s:
                    c_events.append({
                        "time": round(t, 2),
                        "type": "count",
                        "text": word,
                        "sound_file": "",
                        "track": 3,
                        "duration": round(beat_interval * 0.85, 2)
                    })
                    t += beat_interval

        elif count_type == "8count_x4":
            sets = [
                (kr_counts_set1 if lang == "kr" else en_counts_set1),
                (kr_counts_set2 if lang == "kr" else en_counts_set2),
                (kr_counts_set3 if lang == "kr" else en_counts_set3),
                (kr_counts_set4 if lang == "kr" else en_counts_set4)
            ]
            for s in sets:
                for word in s:
                    c_events.append({
                        "time": round(t, 2),
                        "type": "count",
                        "text": word,
                        "sound_file": "",
                        "track": 3,
                        "duration": round(beat_interval * 0.85, 2)
                    })
                    t += beat_interval

        elif count_type == "forward_back_8count":
            # [등배운동 정통 도장 구령]: 손바닥(1,2) -> 팔꿈치(3,4) -> 뒤로 젖히기(5,6,7,8)
            words_kr = ["손바닥", "둘", "팔꿈치", "넷", "뒤로", "여섯", "일곱", "여덟"]
            words_en = ["Hands", "Two", "Elbows", "Four", "Look up", "Six", "Seven", "Eight"]
            w_list = words_kr if lang == "kr" else words_en

            # 2회 반복
            for rep in range(2):
                for word in w_list:
                    c_events.append({
                        "time": round(t, 2),
                        "type": "count",
                        "text": word,
                        "sound_file": "",
                        "track": 3,
                        "duration": round(beat_interval * 0.85, 2)
                    })
                    t += beat_interval

        elif count_type == "reps_10":
            # 점핑잭 10회 카운트
            for i in range(1, 11):
                word = str(i)
                c_events.append({
                    "time": round(t, 2),
                    "type": "count",
                    "text": word,
                    "sound_file": "",
                    "track": 3,
                    "duration": round(beat_interval * 0.85, 2)
                })
                t += beat_interval

        elif count_type.startswith("hold_"):
            # 정적 유지 카운트다운 (예: 15초 유지)
            hold_sec = 15.0 if "15s" in count_type else 10.0
            mid_text = "호흡 유지하며 5초 전..." if lang == "kr" else "Keep breathing... 5 seconds left!"
            c_events.append({
                "time": round(t + hold_sec - 5.0, 2),
                "type": "voice",
                "text": mid_text,
                "sound_file": "",
                "track": 3,
                "duration": 2.0
            })
            # 5, 4, 3, 2, 1 카운트
            for c_num in [5, 4, 3, 2, 1]:
                c_events.append({
                    "time": round(t + hold_sec - c_num, 2),
                    "type": "count",
                    "text": str(c_num),
                    "sound_file": "",
                    "track": 3,
                    "duration": 0.8
                })
            # 바로
            c_events.append({
                "time": round(t + hold_sec, 2),
                "type": "voice",
                "text": "바로!" if lang == "kr" else "Relax!",
                "sound_file": "",
                "track": 3,
                "duration": 1.0
            })
            t += hold_sec + 1.0

        elif count_type in ("breathing", "breathing_cycle"):
            # 심호흡 및 호흡 주기
            if lang == "kr":
                steps = [
                    ("숨을 천천히 들이마시고...", 3.0),
                    ("길게 내쉽니다...", 3.5),
                    ("한 번 더 깊게 들이마시고...", 3.0),
                    ("편안하게 내쉽니다.", 3.5)
                ]
            else:
                steps = [
                    ("Breathe in slowly...", 3.0),
                    ("Breathe out gently...", 3.5),
                    ("One more deep breath in...", 3.0),
                    ("And blow it all out.", 3.5)
                ]
            for step_text, dur in steps:
                c_events.append({
                    "time": round(t, 2),
                    "type": "voice",
                    "text": step_text,
                    "sound_file": "",
                    "track": 3,
                    "duration": dur
                })
                t += dur

        total_dur = t - start_time
        return c_events, total_dur
