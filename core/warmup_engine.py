"""
Warmup, Stretching, Mobility & Dojo Conditioning Engine (준비운동·스트레칭·도장 체력단련 엔진)
Author: Gemini & Antigravity
Provides authentic martial arts dojo routines:
1. Standard Full Routine (정규 정통 풀코스 관절체조)
2. Quick Express Routine (약식 쾌속 코스)
3. Warmup & Agility Routine (워밍업 & 순발력: 점핑잭, 버피, 쪼그려점프, 무릎 당겨 점프)
4. Stamina & Conditioning Routine (근지구력: 손바닥/주먹/손가락 팔굽혀펴기, 레그레이즈, 플러터킥, 브릿지)
5. Flexibility & Kicking Routine (하체 유연성 & 고관절 모빌리티)
6. Yoga & Pilates Core Routine (요가/필라테스 척추·코어 밸런스: 코브라, 비둘기, 전사, 삼각, 플랭크, 척추비틀기)
7. Kids English Martial Arts Routine (유치부·초등 저학년 신나는 한영 믹스 몸풀기)
8. Custom Routine (사용자 맞춤형 저장/불러오기)

Key Features:
- 4-Tier Language Modes:
  1) 'kr': 🇰🇷 정통 한국어 도장 사범 구령
  2) 'mix_kids': 🧒 [유치부 / 7세 미만] 한-영 단어 믹스 (인체 부위, 동작, 방향 키워드 결합)
  3) 'dual_step': 🏫 [초등부 / 기초] 한국어 먼저 ➔ 쉬운 영어 짧은 문장 순차 진행
  4) 'en_advanced' / 'en': 🇺🇸 [중·고등부 / 상급] 원어민 영어 구령
- Plain, intuitive Korean movement titles and step-by-step physical guidance tips
- Cadence 4-count reps ("하나, 둘, 셋, 하나! 하나, 둘, 셋, 둘!") for Jumping Jacks, Burpees, Squat Jumps (1.5s per rep)
- Dedicated single-rep pacing for heavy strength movements (Pushups, Kicks)
- Precise Bridge Hold timing (Rep 1: 3s hold -> Relax, Rep 2: 3s hold -> Relax, Rep 3: 10s hold -> Relax)
- Audio duration-based cascade realignment (완벽한 음성 겹침/뒤엉킴 원천 차단)
"""

import os
import copy
from typing import List, Dict, Any, Tuple
from pydub import AudioSegment


# 1. 동작 기본 마스터 데이터베이스 (Master Movement Definitions)
MASTER_MOVEMENTS: List[Dict[str, Any]] = [
    # ── 기본 관절 및 동적 체조 (Joints & Dynamic Warm-up) ──
    {
        "id": "wrist_ankle",
        "name_kr": "손목·발목 털고 돌리기",
        "name_mix": "손목·발목 롤링 (핸드 앤 앵클)",
        "name_dual": "손목·발목 털기 (Wrists & Ankles)",
        "name_en": "Wrist & Ankle Circles",
        "instruction_kr": "양손 깍지 끼고, 왼발부터 손목 발목 부드럽게 돌려주기! 발 바꿔서 반대로!",
        "instruction_mix": "보스 핸즈(Hands) 깍지 끼고, 레프트 풋(Left foot)부터 부드럽게 롤링(Rolling)! 스위치 체인지!",
        "instruction_dual": "손목 발목 부드럽게 돌려주기! - Shake hands and roll your ankles gently!",
        "instruction_en": "Shake your hands and feet! Roll them round and round! Switch sides!",
        "short_cue_kr": "손목 발목 돌리기, 시작!",
        "short_cue_mix": "핸드 앤 앵클 롤링, 고(Go)!",
        "short_cue_dual": "손목 발목 돌리기! - Roll wrists and ankles!",
        "short_cue_en": "Roll wrists and ankles, go!",
        "tip": "양손 깍지를 끼고 발목을 바닥에 가볍게 대어 원을 그리며 관절의 긴장을 풀어줍니다.",
        "count_type": "8count_x2",
        "default_duration_sec": 16.0,
        "category": "joint"
    },
    {
        "id": "knee_bends",
        "name_kr": "무릎 굽혀펴기",
        "name_mix": "무릎 굽혀펴기 (니 벤드 앤 스트레치)",
        "name_dual": "무릎 굽혀펴기 (Knee Bends)",
        "name_en": "Knee Bends & Stretch",
        "instruction_kr": "양손 무릎 위에 올리고, 가볍게 굽혔다 펴기! 준비~ 시작!",
        "instruction_mix": "핸즈(Hands)를 니(Knee) 무릎에 얹고 벤드 앤 스트레치(Bend and Stretch)! 레디, 고!",
        "instruction_dual": "무릎 가볍게 굽혔다 펴기! - Hands on knees, bend and stretch!",
        "instruction_en": "Hands on your knees! Bend down and stretch up straight!",
        "short_cue_kr": "무릎 굽혀펴기, 시작!",
        "short_cue_mix": "니 벤드, 고!",
        "short_cue_dual": "무릎 굽혀펴기! - Knee bends, ready go!",
        "short_cue_en": "Knee bends, ready go!",
        "tip": "양손으로 무릎을 감싸 쥐고 앉았다 일어나며 무릎 관절을 따뜻하게 덥혀줍니다.",
        "count_type": "8count_x2",
        "default_duration_sec": 16.0,
        "category": "joint"
    },
    {
        "id": "knee_circles",
        "name_kr": "무릎 돌려주기 (안팎 회전)",
        "name_mix": "무릎 서클 돌리기 (니 서클)",
        "name_dual": "무릎 안팎 돌리기 (Knee Circles)",
        "name_en": "Knee Circles",
        "instruction_kr": "무릎 안에서 밖으로 돌려주기! 이어서 밖에서 안으로!",
        "instruction_mix": "니(Knee) 무릎을 인사이드 아웃(Inside out)으로 롤링! 이어서 반대로!",
        "instruction_dual": "무릎 안에서 밖으로 돌려주기! - Roll your knees inside out and reverse!",
        "instruction_en": "Roll your knees inside out! Now outside in!",
        "short_cue_kr": "무릎 돌리기, 시작!",
        "short_cue_mix": "니 서클, 고!",
        "short_cue_dual": "무릎 돌리기! - Roll your knees, go!",
        "short_cue_en": "Roll your knees, go!",
        "tip": "무릎을 모아 안쪽에서 바깥쪽으로 부드럽게 원을 그리고, 방향을 바꿔 바깥에서 안으로 돌립니다.",
        "count_type": "8count_x2",
        "default_duration_sec": 16.0,
        "category": "joint"
    },
    {
        "id": "knee_press_short",
        "name_kr": "무릎 눌러주기 (짧게 누르기)",
        "name_mix": "숏 런지 무릎 프레스 (짧게 누르기)",
        "name_dual": "짧게 무릎 누르기 (Short Knee Press)",
        "name_en": "Short Stance Knee Press",
        "instruction_kr": "다리 어깨너비로 벌리고, 왼쪽부터 짧게 눌러주기! 반대쪽!",
        "instruction_mix": "레그(Leg) 어깨너비 벌리고, 레프트(Left)부터 소프트하게 푸시(Push)! 스위치!",
        "instruction_dual": "왼쪽부터 무릎 지긋이 누르기! - Push your knee gently, switch sides!",
        "instruction_en": "Push your knees softly! Switch sides!",
        "short_cue_kr": "짧게 눌러주기, 시작!",
        "short_cue_mix": "숏 프레스, 고!",
        "short_cue_dual": "짧게 누르기! - Short knee stretch, go!",
        "short_cue_en": "Short knee stretch, go!",
        "tip": "다리를 좁게 벌린 상태에서 한쪽 무릎을 살짝 굽혀 허벅지와 무릎 뒷근육을 가볍게 늘립니다.",
        "count_type": "8count_x2",
        "default_duration_sec": 16.0,
        "category": "stretch"
    },
    {
        "id": "deep_lunge_side",
        "name_kr": "길게 앉아 무릎 누르기",
        "name_mix": "딥 런지 스트레치 (길게 누르기)",
        "name_dual": "길게 앉아 다리 늘리기 (Deep Lunge Stretch)",
        "name_en": "Deep Side Lunge Stretch",
        "instruction_kr": "다리 넓게 벌리고 깊숙이 앉아서 무릎 지긋이 눌러주기! 발끝 하늘로, 반대쪽!",
        "instruction_mix": "레그 와이드(Wide) 벌리고 딥(Deep)하게 다운! 토(Toe) 발끝 스카이 하늘로! 스위치!",
        "instruction_dual": "깊게 앉아 발끝 세우고 늘리기! - Sit down low, toe up to the sky!",
        "instruction_en": "Sit down low! Stretch your leg, toe to the sky! Switch sides!",
        "short_cue_kr": "길게 눌러주기, 시작!",
        "short_cue_mix": "딥 런지, 고!",
        "short_cue_dual": "길게 누르기! - Deep lunge stretch, go!",
        "short_cue_en": "Deep lunge stretch, go!",
        "tip": "한쪽 다리를 옆으로 깊게 뻗고 발끝을 세워 허벅지 안쪽(내전근)과 햄스트링을 깊숙이 스트레칭합니다.",
        "count_type": "8count_x2",
        "default_duration_sec": 18.0,
        "category": "stretch"
    },
    {
        "id": "hip_torso_twist",
        "name_kr": "골반-허리 틀기 (어깨 넣기)",
        "name_mix": "숄더 드롭 & 트위스트 (어깨 넣기)",
        "name_dual": "어깨 깊숙이 넣기 (Shoulder Drop Twist)",
        "name_en": "Shoulder Drop & Torso Twist",
        "instruction_kr": "양손 허벅지 짚고, 오른쪽 어깨 깊숙이 밀어 넣으며 시선 뒤쪽! 반대쪽 어깨!",
        "instruction_mix": "핸즈 허벅지 짚고, 라이트 숄더(Shoulder) 안으로 딥 푸시! 룩 백(Look back)! 스위치!",
        "instruction_dual": "어깨를 안으로 밀어 넣으며 시선 뒤쪽! - Drop shoulder down, look behind you!",
        "instruction_en": "Drop your shoulder down, look behind you! Switch shoulders!",
        "short_cue_kr": "어깨 집어넣기, 시작!",
        "short_cue_mix": "숄더 트위스트, 고!",
        "short_cue_dual": "어깨 넣기! - Shoulder twist, go!",
        "short_cue_en": "Shoulder twist, go!",
        "tip": "기마자세에서 한쪽 어깨를 안쪽 바닥 방향으로 지긋이 눌러 척추와 고관절을 함께 비틀어줍니다.",
        "count_type": "8count_x2",
        "default_duration_sec": 16.0,
        "category": "stretch"
    },
    {
        "id": "waist_circles",
        "name_kr": "허리 돌려주기",
        "name_mix": "웨이스트 서클 (핸드 온 힙)",
        "name_dual": "허리 크게 돌리기 (Waist Circles)",
        "name_en": "Waist & Hip Circles",
        "instruction_kr": "양손 허리에 얹고, 왼쪽부터 허리 크게 돌려주기! 반대로 돌리기!",
        "instruction_mix": "핸즈 온 힙(Hands on hips)! 빅 서클(Big circle) 크게 돌리기! 리버스(Reverse) 반대로!",
        "instruction_dual": "허리 손 얹고 크게 원 그리기! - Hands on your hips, big circles!",
        "instruction_en": "Hands on your hips! Big circles with your hips! Reverse direction!",
        "short_cue_kr": "허리 돌리기, 시작!",
        "short_cue_mix": "웨이스트 서클, 고!",
        "short_cue_dual": "허리 돌리기! - Circle your hips, go!",
        "short_cue_en": "Circle your hips, go!",
        "tip": "양손으로 허리를 받치고 골반 전체로 큰 원을 그리며 허리와 고관절의 긴장을 풉니다.",
        "count_type": "8count_x2",
        "default_duration_sec": 16.0,
        "category": "joint"
    },
    {
        "id": "torso_twist",
        "name_kr": "몸통 틀어주기 (상체 비틀기)",
        "name_mix": "바디 트위스트 (몸통 비틀기)",
        "name_dual": "상체 좌우 비틀기 (Torso Twists)",
        "name_en": "Upper Body Torso Twists",
        "instruction_kr": "양팔 팔꿈치 접고 가슴 높이, 좌우로 몸통 털며 비틀기! 시선도 함께!",
        "instruction_mix": "암즈(Arms) 가슴 높이 들고, 레프트 라이트(Left Right) 트위스트! 시선도 함께 턴!",
        "instruction_dual": "양팔 들고 좌우로 몸통 틀기! - Twist your body left and right!",
        "instruction_en": "Twist your body left and right! Swing your arms smoothly!",
        "short_cue_kr": "몸통 틀기, 시작!",
        "short_cue_mix": "바디 트위스트, 고!",
        "short_cue_dual": "몸통 틀기! - Twist body, go!",
        "short_cue_en": "Twist body, go!",
        "tip": "팔꿈치를 접어 가슴 앞에 두고 좌우로 가볍게 회전하며 척추 회전 근육을 깨웁니다.",
        "count_type": "8count_x2",
        "default_duration_sec": 16.0,
        "category": "joint"
    },
    {
        "id": "forward_back_bend",
        "name_kr": "등배운동 (손바닥·팔꿈치·뒤로)",
        "name_mix": "핸드 앤 엘보우 등배운동",
        "name_dual": "손바닥 팔꿈치 닿기 (Forward & Back Bends)",
        "name_en": "Hands, Elbows & Back Bends",
        "instruction_kr": "등배운동! 앞으로 숙여 손바닥 바닥 터치, 팔꿈치 바닥 터치, 양손 허리 받치고 뒤로 젖히기! 준비~ 시작!",
        "instruction_mix": "앞으로 벤드! 핸드(Hands) 터치, 엘보우(Elbows) 터치, 룩 업(Look up) 뒤로 젖히기! 레디, 고!",
        "instruction_dual": "손바닥 터치, 팔꿈치 터치, 뒤로 젖히기! - Touch hands, touch elbows, bend back!",
        "instruction_en": "Touch hands to the floor, touch elbows down, then bend backwards! Ready, go!",
        "short_cue_kr": "등배운동, 시작!",
        "short_cue_mix": "등배운동, 고!",
        "short_cue_dual": "등배운동! - Forward and back bends, go!",
        "short_cue_en": "Forward and back bends, go!",
        "tip": "무릎을 편 채 상체를 숙여 손바닥과 팔꿈치를 바닥에 대고, 손으로 허리를 받치며 뒤로 시원하게 젖힙니다.",
        "count_type": "forward_back_8count",
        "default_duration_sec": 18.0,
        "category": "stretch"
    },
    {
        "id": "full_torso_circle",
        "name_kr": "몸통 크게 돌려주기",
        "name_mix": "빅 윈드밀 서클 (풍차 몸통돌리기)",
        "name_dual": "상체 크게 돌리기 (Full Torso Circles)",
        "name_en": "Full Torso Windmill Circles",
        "instruction_kr": "양팔 머리 위로 들고, 몸통 크게 원을 그리며 돌려주기! 반대로 돌리기!",
        "instruction_mix": "보스 암즈(Arms) 업 하이! 큰 원 그리며 빅 서클(Big circle)! 체인지 반대로!",
        "instruction_dual": "양팔 들고 몸통 크게 원 그리기! - Arms up high, make a giant circle!",
        "instruction_en": "Arms up high! Make a giant circle with your whole body! Reverse!",
        "short_cue_kr": "몸통 크게 돌리기, 시작!",
        "short_cue_mix": "빅 서클, 고!",
        "short_cue_dual": "크게 돌리기! - Giant circles, go!",
        "short_cue_en": "Giant circles, go!",
        "tip": "양팔을 위로 뻗어 상체 전체로 원을 그리듯 돌려 옆구리, 등, 복부를 전방위로 늘려줍니다.",
        "count_type": "8count_x2",
        "default_duration_sec": 16.0,
        "category": "joint"
    },
    {
        "id": "windmill_toe_touch",
        "name_kr": "발목 교대 터치 (풍차 운동)",
        "name_mix": "토 터치 풍차 (얼터네이팅 토 터치)",
        "name_dual": "양발 번갈아 터치하기 (Alternating Toe Touches)",
        "name_en": "Alternating Toe Touches",
        "instruction_kr": "다리 넓게 벌리고 양팔 벌려, 오른손 왼발목 왼손 오른발목 번갈아 터치!",
        "instruction_mix": "암즈 와이드(Wide) 펼치고, 라이트 핸드 레프트 토(Left toe) 터치! 레프트 핸드 라이트 토 터치!",
        "instruction_dual": "양팔 벌려 반대쪽 발목 교대 터치! - Reach across and touch your opposite toe!",
        "instruction_en": "Arms wide open! Reach across to touch left toe, then right toe!",
        "short_cue_kr": "발목 교대 터치, 시작!",
        "short_cue_mix": "토 터치, 고!",
        "short_cue_dual": "발목 터치! - Touch your toes, go!",
        "short_cue_en": "Touch your toes, go!",
        "tip": "상체를 숙인 상태에서 반대쪽 발목을 교대로 터치하며 햄스트링과 흉추 회전을 동시에 유도합니다.",
        "count_type": "8count_x2",
        "default_duration_sec": 16.0,
        "category": "stretch"
    },
    {
        "id": "shoulder_arm_circles",
        "name_kr": "어깨 짧게/크게 돌리기",
        "name_mix": "숄더 앤 암 서클 (어깨 팔 돌리기)",
        "name_dual": "어깨와 팔 돌리기 (Shoulder & Arm Circles)",
        "name_en": "Shoulder & Big Arm Circles",
        "instruction_kr": "양손 어깨 얹고 짧게 돌리기, 이어서 양팔 펴서 앞으로 뒤로 크게 돌리기!",
        "instruction_mix": "핸즈 온 숄더(Shoulders) 스몰 서클! 이어서 암즈 펴고 빅 플라잉 서클(Big flying circles)!",
        "instruction_dual": "손 어깨 얹고 돌린 후 팔 크게 돌리기! - Roll shoulders small, then circle arms big!",
        "instruction_en": "Small circles with shoulders, then big flying circles with arms!",
        "short_cue_kr": "어깨 돌리기, 시작!",
        "short_cue_mix": "암 서클, 고!",
        "short_cue_dual": "어깨 돌리기! - Arm circles, go!",
        "short_cue_en": "Arm circles, go!",
        "tip": "손을 어깨에 올리고 짧게 돌려 견갑골을 푼 뒤, 양팔을 크게 휘둘러 어깨 관절 전체를 부드럽게 합니다.",
        "count_type": "8count_x2",
        "default_duration_sec": 16.0,
        "category": "joint"
    },
    {
        "id": "neck_stretches",
        "name_kr": "목 운동 (전후좌우 및 돌리기)",
        "name_mix": "넥 엑서사이즈 (목 전후좌우 돌리기)",
        "name_dual": "목 전후좌우 스트레칭 (Neck Stretches)",
        "name_en": "Neck Stretch & Circles",
        "instruction_kr": "양손 허리, 목 앞으로 숙이고 뒤로 젖히기, 좌우 숙이고, 천천히 돌려주기!",
        "instruction_mix": "핸즈 허리에 대고, 넥(Neck) 다운, 업! 레프트, 라이트! 천천히 넥 로테이션(Neck rotation)!",
        "instruction_dual": "목 숙이고 젖히고 천천히 돌리기! - Look down, look up, roll neck gently!",
        "instruction_en": "Hands on hips! Look down, look up, look side to side, and roll softly!",
        "short_cue_kr": "목 운동, 시작!",
        "short_cue_mix": "넥 로테이션, 고!",
        "short_cue_dual": "목 운동! - Neck stretch, go!",
        "short_cue_en": "Neck stretch, go!",
        "tip": "목을 앞뒤, 좌우로 지긋이 늘려준 다음, 무리한 힘을 주지 않고 천천히 원을 그리며 돌려줍니다.",
        "count_type": "8count_x2",
        "default_duration_sec": 16.0,
        "category": "joint"
    },

    # ── 순발력 & 유산소 체온상승 (Cadence 4-count: 1회당 1.5초) ──
    {
        "id": "jumping_jacks_cadence",
        "name_kr": "팔 벌려 뛰기 (점핑잭 10회, 4박자 리듬)",
        "name_mix": "점핑잭 (팔 벌려 뛰기 10회)",
        "name_dual": "팔 벌려 뛰기 10회 (Jumping Jacks)",
        "name_en": "Jumping Jacks (10 Cadence Reps)",
        "instruction_kr": "체온 올리기! 팔 벌려 뛰기 10회! 하나, 둘, 셋에 구령 붙입니다. 준비, 시작!",
        "instruction_mix": "점핑잭(Jumping Jacks) 텐 타임즈(10 times)! 원, 투, 쓰리에 카운트! 레디, 고!",
        "instruction_dual": "팔 벌려 뛰기 10회! - Jumping jacks ten times, ready go!",
        "instruction_en": "Jumping jacks ten times! One, two, three, count! Ready, go!",
        "short_cue_kr": "팔 벌려 뛰기 10회, 시작!",
        "short_cue_mix": "점핑잭, 레디 고!",
        "short_cue_dual": "팔 벌려 뛰기! - Jumping jacks, go!",
        "short_cue_en": "Jumping jacks, ready go!",
        "tip": "점프하며 발을 벌리고 머리 위로 박수를 치는 4박자 경쾌한 전신 유산소 운동입니다.",
        "count_type": "cadence_10reps",
        "default_duration_sec": 17.0,
        "category": "cardio"
    },
    {
        "id": "burpee_cadence",
        "name_kr": "전신 버피 테스트 (엎드려 뻗쳐 점프 10회)",
        "name_mix": "버피 점프 (엎드려 뻗쳐 점프 10회)",
        "name_dual": "버피 점프 10회 (Burpee Jumps)",
        "name_en": "Burpee Jumps (10 Cadence Reps)",
        "instruction_kr": "전신 순발력 버피 10회! 엎드려, 뻗쳐, 모아, 점프! 준비, 시작!",
        "instruction_mix": "전신 버피(Burpees) 텐 타임즈! 다운(Down), 백(Back), 인(In), 점프(Jump)! 레디, 고!",
        "instruction_dual": "버피 점프 10회! - Down, back, in, and jump high!",
        "instruction_en": "Burpee jumps ten times! Down, back, in, jump! Ready, go!",
        "short_cue_kr": "버피 10회, 시작!",
        "short_cue_mix": "버피 점프, 고!",
        "short_cue_dual": "버피 10회! - Burpees, ready go!",
        "short_cue_en": "Burpees, ready go!",
        "tip": "손을 바닥에 대고 다리를 뒤로 뻗었다가 다시 모아 높이 점프하는 고강도 전신 순발력 운동입니다.",
        "count_type": "cadence_10reps",
        "default_duration_sec": 20.0,
        "category": "cardio"
    },
    {
        "id": "squat_jump_cadence",
        "name_kr": "쪼그려 점프뛰기 (스쿼트 점프 10회)",
        "name_mix": "스쿼트 점프 (쪼그려 점프 10회)",
        "name_dual": "스쿼트 점프 10회 (Squat Jumps)",
        "name_en": "Squat Jumps (10 Cadence Reps)",
        "instruction_kr": "하체 폭발력! 깊게 쪼그려 앉았다가 높이 점프 10회! 준비, 시작!",
        "instruction_mix": "스쿼트(Squat) 딥하게 앉고, 점프 하이(Jump high) 텐 타임즈! 레디, 고!",
        "instruction_dual": "깊게 앉았다 높이 점프! - Squat down and jump up high!",
        "instruction_en": "Squat down deep and jump high ten times! Ready, go!",
        "short_cue_kr": "쪼그려 점프 10회, 시작!",
        "short_cue_mix": "스쿼트 점프, 고!",
        "short_cue_dual": "쪼그려 점프! - Squat jumps, go!",
        "short_cue_en": "Squat jumps, ready go!",
        "tip": "엉덩이를 뒤로 빼며 깊게 앉았다가 허벅지와 둔근의 탄력으로 공중으로 높이 뛰어오릅니다.",
        "count_type": "cadence_10reps",
        "default_duration_sec": 18.0,
        "category": "cardio"
    },
    {
        "id": "high_knee_tuck_jump",
        "name_kr": "무릎 당겨 높이 점프 (점프하며 무릎 가슴 터치 10회)",
        "name_mix": "하이니 턱점프 (무릎 가슴 터치 점프 10회)",
        "name_dual": "무릎 당겨 점프 10회 (High Knee Tuck Jumps)",
        "name_en": "High Knee Tuck Jumps (10 reps)",
        "instruction_kr": "제자리에서 힘차게 뛰어올라 공중에서 양 무릎을 가슴까지 높이 끌어당기기 10회! 준비, 시작!",
        "instruction_mix": "점프 업(Jump up)! 양 무릎 니(Knees)를 체스트(Chest) 가슴까지 터치! 텐 타임즈! 레디, 고!",
        "instruction_dual": "무릎 가슴까지 높이 당겨 점프! - Jump high and pull knees to chest!",
        "instruction_en": "Explosive jump up! Tuck both knees high to your chest! Ready, go!",
        "short_cue_kr": "무릎 당겨 점프 10회, 시작!",
        "short_cue_mix": "턱점프, 레디 고!",
        "short_cue_dual": "무릎 당겨 점프! - Tuck jumps, go!",
        "short_cue_en": "Tuck jumps, ready go!",
        "tip": "제자리에서 높이 뛰어올라 공중에서 무릎을 가슴으로 당겨 손바닥을 터치하고 부드럽게 착지합니다.",
        "count_type": "cadence_10reps",
        "default_duration_sec": 18.0,
        "category": "cardio"
    },

    # ── 도장 근지구력 & 체력단련 (Dojo Conditioning & Strength) ──
    {
        "id": "pushup_palms",
        "name_kr": "손바닥 팔굽혀펴기 (기본 10회)",
        "name_mix": "손바닥 푸시업 (팜 푸시업 10회)",
        "name_dual": "손바닥 팔굽혀펴기 10회 (Palm Push-ups)",
        "name_en": "Standard Palm Push-ups (10 reps)",
        "instruction_kr": "손바닥 대고 팔굽혀펴기 10회! 가슴 바닥까지 깊게 내려갔다 올라옵니다. 준비, 시작!",
        "instruction_mix": "팜(Palm) 손바닥 대고 푸시업(Push-ups) 텐 타임즈! 체스트 다운 앤 업! 레디, 고!",
        "instruction_dual": "가슴 바닥까지 닿게 팔굽혀펴기! - Standard push-ups, chest down and up!",
        "instruction_en": "Palm push-ups ten times! Chest all the way to the floor! Ready, go!",
        "short_cue_kr": "손바닥 팔굽혀펴기 10회, 시작!",
        "short_cue_mix": "손바닥 푸시업, 고!",
        "short_cue_dual": "팔굽혀펴기 10회! - Push-ups, go!",
        "short_cue_en": "Palm push-ups, go!",
        "tip": "손을 어깨너비로 짚고 머리부터 발끝까지 일직선을 유지하며 가슴이 바닥에 닿을 때까지 내립니다.",
        "count_type": "single_rep_10",
        "default_duration_sec": 22.0,
        "category": "strength"
    },
    {
        "id": "pushup_knuckles",
        "name_kr": "주먹 쥐고 팔굽혀펴기 (정권 단련 10회)",
        "name_mix": "주먹 푸시업 (너클 푸시업 10회)",
        "name_dual": "정권 주먹 팔굽혀펴기 (Knuckle Push-ups)",
        "name_en": "Knuckle Push-ups (10 reps)",
        "instruction_kr": "주먹 쥐고 정권 팔굽혀펴기 10회! 손목 흔들리지 않게 고정하고 단련합니다. 준비, 시작!",
        "instruction_mix": "피스트(Fist) 주먹 꽉 쥐고 너클 푸시업! 스트롱 손목! 텐 타임즈, 레디 고!",
        "instruction_dual": "주먹 쥐고 손목 단련 팔굽혀펴기! - Knuckle push-ups, keep wrists strong!",
        "instruction_en": "Knuckle push-ups ten times! Lock wrists tight and push! Ready, go!",
        "short_cue_kr": "주먹 팔굽혀펴기 10회, 시작!",
        "short_cue_mix": "주먹 푸시업, 고!",
        "short_cue_dual": "주먹 팔굽혀펴기! - Knuckle push-ups, go!",
        "short_cue_en": "Knuckle push-ups, go!",
        "tip": "검지와 중지 정권 부위로 바닥을 짚어 손목을 꺾지 않고 꼿꼿이 세워 타격 부위를 단련합니다.",
        "count_type": "single_rep_10",
        "default_duration_sec": 22.0,
        "category": "strength"
    },
    {
        "id": "pushup_fingertips",
        "name_kr": "손가락 살려 팔굽혀펴기 (지력 단련 10회)",
        "name_mix": "손가락 푸시업 (핑거팁 푸시업 10회)",
        "name_dual": "손가락 세워 팔굽혀펴기 (Fingertip Push-ups)",
        "name_en": "Fingertip Push-ups (10 reps)",
        "instruction_kr": "다섯 손가락 살려 세우고 지력 팔굽혀펴기 10회! 집중해서 내려갑니다. 준비, 시작!",
        "instruction_mix": "핑거팁(Fingertips) 다섯 손가락 세우고 푸시업! 파워 인 핑거스! 레디, 고!",
        "instruction_dual": "손가락 세우고 지력 팔굽혀펴기! - Fingertip push-ups, strong fingers!",
        "instruction_en": "Fingertip push-ups ten times! Power in your fingers! Ready, go!",
        "short_cue_kr": "손가락 팔굽혀펴기 10회, 시작!",
        "short_cue_mix": "손가락 푸시업, 고!",
        "short_cue_dual": "손가락 팔굽혀펴기! - Fingertip push-ups, go!",
        "short_cue_en": "Fingertip push-ups, go!",
        "tip": "다섯 손가락 끝으로 바닥을 움켜쥐듯 지탱하여 손가락 관절과 악력, 지력을 기릅니다.",
        "count_type": "single_rep_10",
        "default_duration_sec": 22.0,
        "category": "strength"
    },
    {
        "id": "flutter_kicks",
        "name_kr": "누워서 번갈아 다리 올리기 (플러터킥 20회)",
        "name_mix": "플러터 킥 (누워서 다리 차기 20회)",
        "name_dual": "누워서 다리 교대 차기 20회 (Flutter Kicks)",
        "name_en": "Lying Flutter Kicks (20 reps)",
        "instruction_kr": "누워서 양손 엉덩이 받치고, 무릎 펴서 발끝 번갈아 차올리기 20회! 준비, 시작!",
        "instruction_mix": "누워서 핸즈 힙 받치고, 레그를 업 앤 다운 플러터 킥(Flutter kicks)! 트웬티(20) 타임즈! 레디, 고!",
        "instruction_dual": "누워서 발끝 번갈아 차올리기! - Kick feet up and down twenty times!",
        "instruction_en": "Lie down, hands under hips, kick feet up and down twenty times! Ready, go!",
        "short_cue_kr": "다리 번갈아 차기 20회, 시작!",
        "short_cue_mix": "플러터 킥, 고!",
        "short_cue_dual": "플러터 킥 20회! - Flutter kicks, go!",
        "short_cue_en": "Flutter kicks, go!",
        "tip": "바닥에 누워 손을 엉덩이 밑에 대고 허리를 바닥에 밀착한 채 양발을 물장구치듯 교대로 차올립니다.",
        "count_type": "alternate_20reps",
        "default_duration_sec": 20.0,
        "category": "strength"
    },
    {
        "id": "lying_heel_kicks",
        "name_kr": "누워서 뒤꿈치 밀어차기 (레그 드래그 10회)",
        "name_mix": "힐 푸시 킥 (뒤꿈치 밀어차기 10회)",
        "name_dual": "누워서 뒤꿈치 밀어차기 10회 (Heel Push Kicks)",
        "name_en": "Lying Heel Push Kicks (10 reps)",
        "instruction_kr": "누워서 무릎 당겼다가 뒤꿈치로 강하게 밀어차고 버티기 10회! 준비, 시작!",
        "instruction_mix": "누워서 니 당기고, 힐(Heel) 뒤꿈치로 스트롱 푸시 킥! 텐 타임즈! 레디, 고!",
        "instruction_dual": "무릎 당겨 뒤꿈치로 힘차게 밀어차기! - Push heels out strong ten times!",
        "instruction_en": "Lie down, knees in, push heels out strong ten times! Ready, go!",
        "short_cue_kr": "뒤꿈치 밀어차기 10회, 시작!",
        "short_cue_mix": "뒤꿈치 밀어차기, 고!",
        "short_cue_dual": "뒤꿈치 밀어차기! - Heel push kicks, go!",
        "short_cue_en": "Heel push kicks, go!",
        "tip": "누워서 무릎을 가슴으로 당겼다가 발뒤꿈치로 허공을 강하게 밀어내어 하복근과 대퇴부를 단련합니다.",
        "count_type": "single_rep_10",
        "default_duration_sec": 22.0,
        "category": "strength"
    },
    {
        "id": "prone_hip_circles",
        "name_kr": "엎드려 골반 밖에서 안으로 돌리기 (10회)",
        "name_mix": "엎드려 힙 서클 (골반 돌리기 10회)",
        "name_dual": "엎드려 골반 회전 (Prone Hip Circles)",
        "name_en": "Prone Hip Circles (Outside In, 10 reps)",
        "instruction_kr": "엎드린 자세에서 무릎 들어 골반 바깥에서 안쪽으로 크게 돌려주기! 좌우 교대!",
        "instruction_mix": "네 발 기는 자세에서 니(Knee) 들고 힙을 아웃사이드 인으로 서클! 스위치 레그!",
        "instruction_dual": "엎드려 무릎으로 큰 원 그리기! - Circle your hip outside to inside!",
        "instruction_en": "Hands and knees, circle your hip outside to inside! Switch legs!",
        "short_cue_kr": "골반 밖에서 안으로 돌리기, 시작!",
        "short_cue_mix": "힙 서클, 고!",
        "short_cue_dual": "골반 돌리기! - Hip circles, go!",
        "short_cue_en": "Hip circles outside in, go!",
        "tip": "양손과 무릎을 바닥에 대고 한쪽 무릎을 들어 바깥에서 안쪽으로 크게 원을 그려 고관절을 가동합니다.",
        "count_type": "8count_x2",
        "default_duration_sec": 18.0,
        "category": "strength"
    },
    {
        "id": "prone_hip_push",
        "name_kr": "엎드려 골반 안에서 밖으로 밀어주기 (10회)",
        "name_mix": "엎드려 힙 익스텐션 (다리 뒤로 뻗기 10회)",
        "name_dual": "엎드려 다리 뒤로 뻗기 (Hip Extension Push)",
        "name_en": "Prone Hip Extension Push (10 reps)",
        "instruction_kr": "엎드린 자세에서 무릎 안쪽에서 바깥으로 힘차게 밀어 펴주기! 좌우 교대!",
        "instruction_mix": "네 발 기는 자세에서 레그를 백으로 스트레이트 푸시! 스위치 레그!",
        "instruction_dual": "엎드려 다리 뒤로 힘차게 밀어펴기! - Push leg back straight, switch legs!",
        "instruction_en": "Hands and knees, push your leg inside to outside! Switch legs!",
        "short_cue_kr": "골반 안에서 밖으로 밀기, 시작!",
        "short_cue_mix": "힙 익스텐션, 고!",
        "short_cue_dual": "다리 밀어펴기! - Hip push, go!",
        "short_cue_en": "Hip push inside out, go!",
        "tip": "네 발 기기 자세에서 다리를 뒤쪽 대각선으로 힘차게 뻗어 둔근과 햄스트링을 강화합니다.",
        "count_type": "8count_x2",
        "default_duration_sec": 18.0,
        "category": "strength"
    },
    {
        "id": "bridge_hold_3310",
        "name_kr": "브릿지 골반 들기 (하나 3초, 둘 3초, 셋 10초)",
        "name_mix": "글루트 브릿지 (골반 들기 3초-3초-10초)",
        "name_dual": "브릿지 골반 들기 (Glute Bridge Holds)",
        "name_en": "Glute Bridge Holds (3s-3s-10s Pattern)",
        "instruction_kr": "누워서 무릎 세우고 브릿지 골반 들기! 하나에 3초 버티고, 둘에 3초, 셋에는 10초간 힘차게 듭니다. 준비, 시작!",
        "instruction_mix": "누워서 니 세우고 힙 업(Hip up) 브릿지! 원에 3초 홀드, 투에 3초, 쓰리에 10초 롱 홀드! 레디, 고!",
        "instruction_dual": "골반 높이 들어올려 버티기! - Lift hips high, hold strong!",
        "instruction_en": "Lie down, lift hips up high! One hold 3s, Two hold 3s, Three hold 10s! Ready, go!",
        "short_cue_kr": "브릿지 골반 들기, 시작!",
        "short_cue_mix": "브릿지 홀드, 고!",
        "short_cue_dual": "골반 들기! - Glute bridge, go!",
        "short_cue_en": "Glute bridge holds, go!",
        "tip": "누워서 무릎을 세우고 엉덩이를 높이 들어 올려 둔근과 척추기립근을 1회차 3초, 2회차 3초, 3회차 10초간 버팁니다.",
        "count_type": "bridge_pattern",
        "default_duration_sec": 28.0,
        "category": "strength"
    },

    # ── 하체 유연성 & 발차기 모빌리티 (Flexibility & Kicking) ──
    {
        "id": "hip_dynamic_rotation",
        "name_kr": "고관절 다이나믹 회전 (안팎 차올리기)",
        "name_mix": "힙 로테이션 킥 (안팎 차올리기)",
        "name_dual": "고관절 안팎 돌려차기 (Dynamic Hip Opener)",
        "name_en": "Dynamic Hip Opener Kicks",
        "instruction_kr": "무릎 직각으로 들어 올려 안에서 밖으로 크게 차올리기! 반대 다리 교대!",
        "instruction_mix": "니(Knee) 직각으로 들고 안에서 밖으로 오픈 킥! 스위치 레그!",
        "instruction_dual": "무릎 높이 들어 안에서 밖으로 회전! - Knee up high, open hip wide!",
        "instruction_en": "Knee up high, open your hip wide! Switch legs!",
        "short_cue_kr": "고관절 회전, 시작!",
        "short_cue_mix": "힙 로테이션, 고!",
        "short_cue_dual": "고관절 회전! - Hip rotation kick, go!",
        "short_cue_en": "Hip circles kick, go!",
        "tip": "무릎을 가슴 높이로 들어 바깥쪽으로 큰 원을 그리며 차올려 발차기 고관절 가동 범위를 넓힙니다.",
        "count_type": "8count_x2",
        "default_duration_sec": 16.0,
        "category": "mobility"
    },
    {
        "id": "lunge_hip_flexor",
        "name_kr": "장요근 런지 바운스 스트레칭",
        "name_mix": "런지 바운스 (골반 바닥 누르기)",
        "name_dual": "앞굽이 런지 스트레칭 (Lunge Hip Stretch)",
        "name_en": "Lunge Hip Stretch",
        "instruction_kr": "앞굽이 길게 딛고 골반을 바닥으로 지긋이 눌러주기! 반대쪽 교대!",
        "instruction_mix": "빅 스텝(Big step) 앞으로 딛고 힙을 바닥으로 다운 푸시! 스위치!",
        "instruction_dual": "앞굽이 길게 딛고 골반 누르기! - Big step forward, push hips down low!",
        "instruction_en": "Big step forward! Push your hips down low! Switch legs!",
        "short_cue_kr": "런지 스트레칭, 시작!",
        "short_cue_mix": "런지 스트레치, 고!",
        "short_cue_dual": "런지 스트레칭! - Lunge stretch, go!",
        "short_cue_en": "Lunge stretch, go!",
        "tip": "앞다리를 넓게 딛고 뒷다리를 길게 펴서 골반 앞쪽 장요근이 시원하게 늘어나도록 눌러줍니다.",
        "count_type": "8count_x2",
        "default_duration_sec": 18.0,
        "category": "mobility"
    },
    {
        "id": "hamstring_high_kick",
        "name_kr": "햄스트링 프론트 스윙 킥 (앞차기 올리기)",
        "name_mix": "프론트 스윙 킥 (앞차기 투 더 페이스)",
        "name_dual": "앞차기 높이 차올리기 (High Kick Leg Swings)",
        "name_en": "High Kick Leg Swings",
        "instruction_kr": "무릎 펴고 앞차기 높이 가볍게 차올리기! 왼발 오른발 교대!",
        "instruction_mix": "무릎 스트레이트(Straight) 펴고 프론트 킥 투 더 페이스(Front kick to the face)! 레프트 라이트 교대!",
        "instruction_dual": "무릎 펴고 앞차기 높이 차올리기! - Straight leg kick up high to face!",
        "instruction_en": "Straight leg kick up high to your hand! Switch legs!",
        "short_cue_kr": "앞차기 스윙, 시작!",
        "short_cue_mix": "프론트 킥, 고!",
        "short_cue_dual": "앞차기 스윙! - High kick swings, go!",
        "short_cue_en": "High kick swings, go!",
        "tip": "무릎을 곧게 편 상태에서 발끝을 얼굴 높이까지 경쾌하게 차올려 햄스트링 탄력을 높입니다.",
        "count_type": "8count_x2",
        "default_duration_sec": 16.0,
        "category": "mobility"
    },
    {
        "id": "butterfly_pose",
        "name_kr": "나비 자세 (골반 열고 무릎 누르기)",
        "name_mix": "버터플라이 포즈 (나비 자세 무릎 누르기)",
        "name_dual": "나비 자세 (Butterfly Stretch)",
        "name_en": "Butterfly Stretch",
        "instruction_kr": "바닥에 앉아 발바닥 맞대고, 무릎을 바닥으로 지긋이 눌러줍니다.",
        "instruction_mix": "싯 다운(Sit down), 피트(Feet) 맞대고 버터플라이처럼 니(Knees)를 바닥으로 젠틀하게 푸시!",
        "instruction_dual": "발바닥 맞대고 무릎 바닥 누르기! - Sit down, feet together, push knees down!",
        "instruction_en": "Sit down, feet together like a butterfly! Push knees down gently!",
        "short_cue_kr": "나비 자세, 시작!",
        "short_cue_mix": "버터플라이, 고!",
        "short_cue_dual": "나비 자세! - Butterfly stretch, go!",
        "short_cue_en": "Butterfly stretch, go!",
        "tip": "발바닥을 서로 마주 대고 앉아 양손으로 발끝을 잡고 무릎을 바닥으로 가볍게 흔들며 눌러줍니다.",
        "count_type": "hold_15s",
        "default_duration_sec": 20.0,
        "category": "flexibility"
    },
    {
        "id": "straddle_splits",
        "name_kr": "다리 벌려 좌우 숙이기 (다리 찢기 스트레칭)",
        "name_mix": "V-싯 스플릿 (다리 벌려 좌우 숙이기)",
        "name_dual": "다리 벌려 좌우 숙이기 (Straddle Splits)",
        "name_en": "V-Sit Straddle Stretch",
        "instruction_kr": "다리 V자로 넓게 벌리고 왼쪽으로 숙이기, 이어서 오른쪽, 중앙으로 숙이기!",
        "instruction_mix": "레그 V자 와이드 오픈! 레프트 숙이고, 라이트 숙이고, 센터로 딥하게 다운!",
        "instruction_dual": "다리 벌려 왼쪽, 오른쪽, 중앙 숙이기! - Reach left, reach right, reach center!",
        "instruction_en": "Legs open wide in a big V! Reach left, reach right, reach forward!",
        "short_cue_kr": "다리 벌려 숙이기, 시작!",
        "short_cue_mix": "스플릿 스트레치, 고!",
        "short_cue_dual": "다리 벌려 숙이기! - Straddle stretch, go!",
        "short_cue_en": "Straddle stretch, go!",
        "tip": "다리를 가능한 넓게 벌리고 앉아 상체를 왼쪽, 오른쪽, 가운데로 번갈아 숙여 유연성을 극대화합니다.",
        "count_type": "8count_x4",
        "default_duration_sec": 25.0,
        "category": "flexibility"
    },

    # ── 요가 & 필라테스 전문 8종 동작 (Yoga & Pilates Authentic Sequence) ──
    {
        "id": "cobra_pose",
        "name_kr": "코브라 자세 (엎드려 상체 세우기)",
        "name_mix": "코브라 포즈 (엎드려 상체 세우기)",
        "name_dual": "코브라 척추 이완 (Cobra Pose)",
        "name_en": "Cobra Stretch (Bhujangasana)",
        "instruction_kr": "배를 대고 엎드려 양손 가슴 옆을 짚고, 팔을 펴며 상체를 천천히 들어 올립니다. 가슴을 펴고 시선은 하늘, 숨을 길게 내쉽니다.",
        "instruction_mix": "바닥에 엎드려 핸드(Hands) 가슴 옆 짚고 푸시! 코브라처럼 체스트(Chest) 들고 룩 업(Look up)! 브레스(Breathe) 천천히!",
        "instruction_dual": "엎드려 상체 들어올리고 가슴 펴기! - Push your chest up like a cobra, look up to the sky!",
        "instruction_en": "Lie flat on your stomach, place hands by your chest, push up gently and look to the sky! Breathe deeply.",
        "short_cue_kr": "코브라 자세, 유지!",
        "short_cue_mix": "코브라 포즈, 홀드!",
        "short_cue_dual": "코브라 자세! - Cobra stretch, hold!",
        "short_cue_en": "Cobra stretch, hold!",
        "tip": "엎드린 상태에서 손바닥으로 바닥을 밀어 가슴을 열고 시선을 위로 향해 허리와 복부를 이완합니다.",
        "count_type": "hold_15s",
        "default_duration_sec": 20.0,
        "category": "yoga"
    },
    {
        "id": "pigeon_pose_lr",
        "name_kr": "비둘기 자세 (한 다리 접고 골반 누르기, 좌우 교대)",
        "name_mix": "피죤 포즈 (한 다리 접고 골반 누르기)",
        "name_dual": "비둘기 골반 스트레칭 (Pigeon Pose)",
        "name_en": "Pigeon Pose Hip Stretch",
        "instruction_kr": "앞쪽 다리는 ㄱ자로 접고 뒷다리는 뒤로 길게 뻗어, 골반을 바닥으로 지긋이 누릅니다. 왼쪽 먼저 유지하고 반대쪽 진행합니다.",
        "instruction_mix": "앞다리 벤드(Bend) 접고, 백 레그(Back leg)는 스트레이트! 힙(Hip)을 바닥으로 다운(Down)! 스위치 레그 체인지!",
        "instruction_dual": "앞다리 접고 뒷다리 뻗어 골반 누르기! - Fold front leg, stretch back leg, push hips down!",
        "instruction_en": "Fold front leg at 90 degrees, stretch back leg straight, sink hips down low! Switch sides!",
        "short_cue_kr": "비둘기 자세, 시작!",
        "short_cue_mix": "피죤 포즈, 고!",
        "short_cue_dual": "비둘기 자세! - Pigeon pose, hold!",
        "short_cue_en": "Pigeon pose, hold!",
        "tip": "한쪽 다리를 가슴 앞에 접어두고 반대 다리를 뒤로 뻗어 엉덩이 깊은 근육(이상근)과 골반을 풀어줍니다.",
        "count_type": "8count_x2",
        "default_duration_sec": 24.0,
        "category": "yoga"
    },
    {
        "id": "warrior_pose_lr",
        "name_kr": "전사 자세 (앞굽이 팔 벌려 중심잡기, 좌우 교대)",
        "name_mix": "워리어 포즈 (전사 자세 밸런스)",
        "name_dual": "전사 자세 하체 버티기 (Warrior Pose)",
        "name_en": "Warrior II Pose",
        "instruction_kr": "앞다리는 90도로 굽히고 뒷다리는 쭉 편 상태에서, 양팔을 앞뒤로 수평으로 뻗어 하체 힘을 기르고 버팁니다. 좌우 교대!",
        "instruction_mix": "앞무릎 90도 벤드, 양팔 와이드(Wide) 펼치기! 스트롱 워리어(Strong Warrior)! 밸런스 홀드! 스위치!",
        "instruction_dual": "앞무릎 굽히고 양팔 벌려 버티기! - Front knee bent 90 degrees, stretch arms wide!",
        "instruction_en": "Front knee bent at 90 degrees, stretch both arms wide, keep core strong! Switch sides!",
        "short_cue_kr": "전사 자세, 유지!",
        "short_cue_mix": "워리어 포즈, 홀드!",
        "short_cue_dual": "전사 자세! - Warrior pose, hold!",
        "short_cue_en": "Warrior pose, hold!",
        "tip": "앞다리를 깊게 굽히고 양팔을 어깨높이로 펼쳐 시선은 앞쪽 손끝을 보며 하체 지구력과 집중력을 키웁니다.",
        "count_type": "8count_x2",
        "default_duration_sec": 22.0,
        "category": "yoga"
    },
    {
        "id": "triangle_pose_lr",
        "name_kr": "삼각 자세 (다리 벌려 옆구리 늘리기, 좌우 교대)",
        "name_mix": "트라이앵글 포즈 (삼각 자세 옆구리 늘리기)",
        "name_dual": "삼각 자세 옆구리 스트레칭 (Triangle Pose)",
        "name_en": "Triangle Pose (Trikonasana)",
        "instruction_kr": "다리를 넓게 벌리고, 한 손으로 발목을 잡으며 반대 손은 하늘 높이 뻗어 옆구리와 다리 뒷근육을 늘려줍니다. 좌우 교대!",
        "instruction_mix": "레그 와이드(Wide) 벌리고, 원 핸드 발목 터치, 반대 핸드는 스카이(Sky) 하늘 위로 업! 사이드 스트레치! 스위치!",
        "instruction_dual": "발목 잡고 반대 손 하늘 높이 뻗기! - Touch ankle and reach other hand high to sky!",
        "instruction_en": "Legs wide, touch your ankle with one hand, reach the other hand high to the sky! Switch sides!",
        "short_cue_kr": "삼각 자세, 시작!",
        "short_cue_mix": "트라이앵글, 고!",
        "short_cue_dual": "삼각 자세! - Triangle pose, hold!",
        "short_cue_en": "Triangle pose, hold!",
        "tip": "양다리를 펴고 상체를 옆으로 기울여 손끝을 하늘로 뻗음으로써 햄스트링과 늑간근을 시원하게 늘립니다.",
        "count_type": "8count_x2",
        "default_duration_sec": 22.0,
        "category": "yoga"
    },
    {
        "id": "plank_hold_30s",
        "name_kr": "플랭크 코어 버티기 (팔꿈치 대고 엎드려 버티기 30초)",
        "name_mix": "플랭크 코어 홀드 (30초 정적 버티기)",
        "name_dual": "플랭크 코어 30초 버티기 (Plank Hold 30s)",
        "name_en": "Plank Core Hold (30 Seconds)",
        "instruction_kr": "팔꿈치와 발끝으로 몸을 일직선으로 띄워, 복근과 엉덩이에 힘을 꽉 주고 30초간 흔들림 없이 버팁니다.",
        "instruction_mix": "엘보우(Elbow) 바닥 대고 바디 스트레이트(Straight)! 락처럼 단단하게 코어(Core) 힘주고 30초 홀드!",
        "instruction_dual": "팔꿈치 대고 몸 일직선 버티기! - Keep body straight like a board, hold tight for 30s!",
        "instruction_en": "Rest on forearms, keep your body in a straight line, squeeze core tight for 30 seconds!",
        "short_cue_kr": "플랭크 버티기, 시작!",
        "short_cue_mix": "플랭크 홀드, 고!",
        "short_cue_dual": "플랭크 버티기! - Plank hold, go!",
        "short_cue_en": "Plank hold, go!",
        "tip": "팔꿈치를 어깨 아래에 두고 복부와 둔근에 힘을 주어 등이 굽거나 허리가 처지지 않도록 버팁니다.",
        "count_type": "hold_15s",
        "default_duration_sec": 22.0,
        "category": "yoga"
    },
    {
        "id": "spine_twist_lr",
        "name_kr": "누워서 척추 비틀기 (무릎 넘겨 허리 풀기, 좌우 교대)",
        "name_mix": "스파인 트위스트 (누워서 무릎 넘기기)",
        "name_dual": "누워서 허리 비틀기 (Lying Spine Twist)",
        "name_en": "Lying Supine Spinal Twist",
        "instruction_kr": "등을 대고 누워 한쪽 무릎을 반대쪽 바닥으로 넘기고, 고개는 반대쪽을 바라보며 척추를 시원하게 풀어줍니다. 좌우 교대!",
        "instruction_mix": "백(Back) 대고 누워서 니(Knee)를 옆으로 트위스트! 헤드(Head)는 반대쪽 룩! 릴랙스(Relax)! 스위치!",
        "instruction_dual": "누워서 무릎 넘기고 고개는 반대쪽! - Drop knee across, look the other way!",
        "instruction_en": "Lie on your back, cross one knee over to the floor, look the opposite way and relax! Switch sides!",
        "short_cue_kr": "척추 비틀기, 시작!",
        "short_cue_mix": "스파인 트위스트, 고!",
        "short_cue_dual": "척추 비틀기! - Spinal twist, go!",
        "short_cue_en": "Spinal twist, go!",
        "tip": "누워서 무릎을 반대쪽 바닥으로 넘기고 양 어깨는 바닥에 붙여 척추 주변의 굳은 근육을 이완합니다.",
        "count_type": "8count_x2",
        "default_duration_sec": 22.0,
        "category": "yoga"
    },
    {
        "id": "figure4_glute_stretch",
        "name_kr": "누워서 4자 다리 당기기 (엉덩이 시원하게 풀기, 좌우 교대)",
        "name_mix": "피겨 포 스트레치 (누워서 4자 다리 당기기)",
        "name_dual": "누워서 4자 다리 당기기 (Figure-4 Stretch)",
        "name_en": "Figure-4 Glute & Piriformis Stretch",
        "instruction_kr": "누워서 한쪽 다리를 반대쪽 무릎 위에 숫자 4 모양으로 얹고, 양손으로 허벅지를 가슴 쪽으로 지긋이 당겨 엉덩이 근육을 풀어줍니다. 좌우 교대!",
        "instruction_mix": "누워서 레그(Leg)를 넘버 포(Number 4) 모양으로 크로스! 보스 핸즈로 체스트 가슴 쪽으로 풀(Pull) 당기기! 스위치!",
        "instruction_dual": "누워서 4자 모양 다리 가슴으로 당기기! - Cross ankle over knee and pull thigh to chest!",
        "instruction_en": "Cross your ankle over opposite knee like number 4, pull your thigh towards your chest! Switch sides!",
        "short_cue_kr": "4자 다리 당기기, 시작!",
        "short_cue_mix": "피겨 포, 고!",
        "short_cue_dual": "4자 다리 당기기! - Figure-4 stretch, go!",
        "short_cue_en": "Figure-4 stretch, go!",
        "tip": "한쪽 발목을 반대 무릎에 걸쳐 숫자 4 모양을 만들고 허벅지를 가슴으로 당겨 엉덩이 뒤쪽을 깊게 풉니다.",
        "count_type": "8count_x2",
        "default_duration_sec": 22.0,
        "category": "yoga"
    },
    {
        "id": "butterfly_forward_fold",
        "name_kr": "나비 자세 앞으로 숙이기 (발바닥 맞대고 깊게 숙이기)",
        "name_mix": "버터플라이 포워드 폴드 (앞으로 깊게 숙이기)",
        "name_dual": "나비 자세 앞으로 깊게 숙이기 (Butterfly Forward Fold)",
        "name_en": "Butterfly Pose Forward Fold",
        "instruction_kr": "발바닥을 서로 맞대고 발뒤꿈치를 몸쪽으로 당긴 뒤, 숨을 내쉬며 이마가 발끝에 닿도록 상체를 바닥으로 깊숙이 숙여줍니다.",
        "instruction_mix": "피트(Feet) 맞대고 버터플라이! 엑스헤일(Exhale) 숨 내쉬며 포워드(Forward) 앞으로 딥 다운 터치!",
        "instruction_dual": "나비 자세에서 상체 앞으로 깊게 숙이기! - Feet together, bend forward deep to floor!",
        "instruction_en": "Feet together, pull heels in close, exhale and fold your upper body down towards the floor!",
        "short_cue_kr": "나비 자세 숙이기, 유지!",
        "short_cue_mix": "포워드 폴드, 홀드!",
        "short_cue_dual": "앞으로 깊게 숙이기! - Fold forward, hold!",
        "short_cue_en": "Fold forward, hold!",
        "tip": "나비 자세에서 등을 둥글게 말지 않고 가슴을 펴며 상체를 천천히 숙여 고관절과 내전근을 깊게 이완합니다.",
        "count_type": "hold_15s",
        "default_duration_sec": 20.0,
        "category": "yoga"
    },
    {
        "id": "cat_cow_flow",
        "name_kr": "캣카우 (고양이·소 척추 이완)",
        "name_mix": "캣 앤 카우 포즈 (고양이 소 척추 이완)",
        "name_dual": "캣카우 척추 이완 (Cat & Cow Stretch)",
        "name_en": "Cat & Cow Stretch",
        "instruction_kr": "테이블 자세에서 숨 들이마시며 가슴 열고, 내쉬며 등 둥글게 말아올리기!",
        "instruction_mix": "네 발 기는 자세에서 인헤일(Inhale) 카우처럼 룩 업! 엑스헤일(Exhale) 캣처럼 등 둥글게 롤 업!",
        "instruction_dual": "숨 들이마시며 가슴 열고 내쉬며 등 말기! - Inhale look up like cow, exhale round like cat!",
        "instruction_en": "Hands and knees on floor! Inhale look up like a cow, exhale round back like a cat!",
        "short_cue_kr": "캣카우, 시작!",
        "short_cue_mix": "캣 앤 카우, 고!",
        "short_cue_dual": "캣카우! - Cat and cow, go!",
        "short_cue_en": "Cat and cow, go!",
        "tip": "기어가는 자세에서 숨을 들이쉬며 허리를 낮추고, 내쉬며 등을 둥글게 말아 척추 전체의 탄력을 회복합니다.",
        "count_type": "breathing_cycle",
        "default_duration_sec": 22.0,
        "category": "yoga"
    },
    {
        "id": "downward_dog",
        "name_kr": "다운독 (견상 자세, 엉덩이 하늘로)",
        "name_mix": "다운독 포즈 (트라이앵글 텐트 자세)",
        "name_dual": "다운독 견상 자세 (Downward Dog)",
        "name_en": "Downward Dog Stretch",
        "instruction_kr": "엉덩이를 천장으로 밀어 올리고, 뒤꿈치 바닥 누르며 종아리와 어깨 늘리기!",
        "instruction_mix": "힙(Hip)을 스카이 천장으로 업! 텐트처럼 삼각형 만들고 뒤꿈치 힐(Heel) 바닥으로 푸시!",
        "instruction_dual": "엉덩이 높이 들고 뒤꿈치 누르기! - Push hips high like a tent, push heels down!",
        "instruction_en": "Push your hips up high like a triangle tent! Push heels down firmly!",
        "short_cue_kr": "다운독 자세, 유지!",
        "short_cue_mix": "다운독, 홀드!",
        "short_cue_dual": "다운독 자세! - Downward dog, hold!",
        "short_cue_en": "Downward dog, hold!",
        "tip": "손바닥과 발바닥으로 바닥을 밀며 엉덩이를 정점으로 삼각형을 만들어 종아리, 햄스트링, 어깨를 늘립니다.",
        "count_type": "hold_15s",
        "default_duration_sec": 20.0,
        "category": "yoga"
    },
    {
        "id": "child_pose",
        "name_kr": "아기 자세 (전신 이완 편안한 휴식)",
        "name_mix": "차일드 포즈 (아기 자세 릴랙스 휴식)",
        "name_dual": "아기 자세 편안한 휴식 (Child's Pose)",
        "name_en": "Child's Rest Pose",
        "instruction_kr": "엉덩이 뒤꿈치에 얹고 이마 바닥, 온몸에 힘을 빼고 편안하게 호흡합니다.",
        "instruction_mix": "힙(Hip) 뒤꿈치에 얹고 포어헤드(Forehead) 이마 바닥! 온몸에 힘 빼고 릴랙스 브레스(Breathe)!",
        "instruction_dual": "무릎 꿇고 엎드려 편안하게 휴식! - Sit on heels, rest forehead down, relax!",
        "instruction_en": "Sit back on your heels, forehead to the floor. Rest and breathe softly.",
        "short_cue_kr": "아기 자세 휴식!",
        "short_cue_mix": "차일드 포즈, 릴랙스!",
        "short_cue_dual": "아기 자세! - Rest in child pose.",
        "short_cue_en": "Rest in child pose.",
        "tip": "무릎을 꿇고 엉덩이를 발뒤꿈치에 댄 채 이마를 바닥에 대고 온몸의 긴장을 풀며 숨을 고릅니다.",
        "count_type": "hold_15s",
        "default_duration_sec": 18.0,
        "category": "yoga"
    },
    {
        "id": "breathing_reset",
        "name_kr": "숨고르기 및 정렬 (심호흡 마무리)",
        "name_mix": "딥 브리딩 (심호흡 숨고르기 차렷)",
        "name_dual": "심호흡 및 바른 자세 정렬 (Deep Breathing Reset)",
        "name_en": "Deep Breathing & Reset",
        "instruction_kr": "호흡 가다듬기, 숨 깊게 들이마시고... 천천히 내쉬고... 바로! 차렷!",
        "instruction_mix": "딥 브레스 인(Deep breath in) 코로 들이마시고... 마우스 입으로 후 내쉬고... 바로! 어텐션(Attention)!",
        "instruction_dual": "숨 깊게 들이마시고 내쉬기! - Big breath in, blow out, attention!",
        "instruction_en": "Big breath in through your nose... and blow out! Attention!",
        "short_cue_kr": "숨고르기, 심호흡!",
        "short_cue_mix": "딥 브리딩!",
        "short_cue_dual": "숨고르기! - Deep breaths in and out!",
        "short_cue_en": "Deep breaths in and out!",
        "tip": "가슴과 배로 숨을 가득 들이마신 후 입으로 길게 내쉬며 심박수를 안정시키고 정자세로 정렬합니다.",
        "count_type": "breathing",
        "default_duration_sec": 12.0,
        "category": "cardio"
    }
]


# 2. 시작 및 종료 멘트 모음 (수준별 4단계 지원)
START_CUES = {
    "kr": [
        "전체 차렷, 준비운동 시작하겠습니다! 다 같이 큰 소리로 구령 붙입니다.",
        "오늘 수련도 부상 없이 다치지 않게 온몸을 부드럽게 풀어줍니다. 힘차게 준비운동 시작!",
        "자, 모두 제자리 정렬! 가벼운 마음으로 몸풀기부터 힘차게 시작해 봅시다!",
        "오늘 훈련을 위해 관절과 근육을 깨워주겠습니다. 준비운동 시작하겠습니다!"
    ],
    "mix_kids": [
        "전체 어텐션(Attention)! 보우 경례(Bow)! 신나게 몸풀기 스타트(Start)! 빅 보이스(Big voice)로 함께 카운트!",
        "헬로 관원들! 핸드와 레그를 쉐이크(Shake) 털고, 힘차게 웜업(Warm-up) 시작! 레디, 셋, 고!",
        "모두 제자리 라인업(Line up)! 다치지 않게 몸을 릴랙스(Relax) 풀어주겠습니다. 렛츠 고(Let's go)!"
    ],
    "dual_step": [
        "전체 차렷, 준비운동 시작하겠습니다! - Attention, let's start warming up our bodies!",
        "부상 없이 다치지 않게 몸을 풀어줍니다! - Stretch well to stay safe and strong! Ready, go!",
        "큰 소리로 구령 붙이며 시작합니다! - Loud voices and follow the rhythm, let's go!"
    ],
    "en": [
        "Attention! Bow! Let's warm up our bodies together! Big voices, follow me! Ready, go!",
        "Hello team! Time to stretch and get strong! Ready, set, go!",
        "Let's get ready for training! Keep your core tight and follow the rhythm! Let's go!"
    ],
    "en_advanced": [
        "Attention! Bow! Let's warm up our bodies together! Big voices, follow me! Ready, go!",
        "Hello team! Time to stretch and get strong! Ready, set, go!",
        "Let's get ready for training! Keep your core tight and follow the rhythm! Let's go!"
    ]
}

END_CUES = {
    "kr": [
        "수고하셨습니다! 가볍게 물 한 잔 마시고 본 수련 대기하세요.",
        "준비운동 끝! 호흡 가다듬고 바른 자세로 제자리에 앉아서 대기합니다.",
        "몸풀기 완료! 매트 정리하고 다음 훈련 위치로 이동합니다.",
        "수고했습니다! 심호흡 세 번 하고 본 운동에 집중해 주세요."
    ],
    "mix_kids": [
        "굿 잡(Good job)! 원더풀! 워터(Water) 물 한 잔 마시고 시트 다운(Sit down) 예쁘게 대기하세요!",
        "베리 굿(Very good)! 온몸이 따뜻해졌습니다! 딥 브레스(Deep breath) 쉬고 다음 지시를 웨이트(Wait)!",
        "엑설런트(Excellent)! 하이파이브! 바른 자세로 싯 다운(Sit down) 대기합니다!"
    ],
    "dual_step": [
        "수고하셨습니다! 물 한 잔 마시고 대기하세요. - Awesome job! Drink some water and wait for master!",
        "준비운동 완료! 바른 자세로 앉아 대기합니다. - Great work! Sit down nicely and take a deep breath!",
        "모두 훌륭했습니다! 다음 훈련 준비! - Excellent effort everyone! Get ready for next training!"
    ],
    "en": [
        "Awesome job! Drink some water and wait for the Master!",
        "Great work everyone! Sit down nicely and take a deep breath!",
        "All done! Excellent effort! Ready for next training!"
    ],
    "en_advanced": [
        "Awesome job! Drink some water and wait for the Master!",
        "Great work everyone! Sit down nicely and take a deep breath!",
        "All done! Excellent effort! Ready for next training!"
    ]
}


# 3. 7대 대표 루틴 프리셋 (Rich Dojo Presets)
ROUTINE_PRESETS = {
    "standard_full": {
        "name_kr": "🥋 [도장 정통 풀코스] 전신 관절 체조 (약 7~8분)",
        "name_en": "🥋 Full Master Routine (7-8 min)",
        "description_kr": "머리부터 발끝까지 13개 관절체조 + 점핑잭 4박자 + 숨고르기 풀코스",
        "movement_ids": [
            "wrist_ankle", "knee_bends", "knee_circles", "knee_press_short",
            "deep_lunge_side", "hip_torso_twist", "waist_circles", "torso_twist",
            "forward_back_bend", "full_torso_circle", "windmill_toe_touch",
            "shoulder_arm_circles", "neck_stretches", "jumping_jacks_cadence", "breathing_reset"
        ],
        "default_tempo_bpm": 85
    },
    "quick_express": {
        "name_kr": "⚡ [약식 쾌속 코스] 핵심 7대 관절 풀기 (약 3~4분)",
        "name_en": "⚡ Quick Express Routine (3-4 min)",
        "description_kr": "시간이 촉박할 때 꼭 필요한 핵심 관절 7가지만 빠르게 순환",
        "movement_ids": [
            "wrist_ankle", "knee_bends", "deep_lunge_side", "forward_back_bend",
            "waist_circles", "neck_stretches", "jumping_jacks_cadence", "breathing_reset"
        ],
        "default_tempo_bpm": 90
    },
    "warmup_cadence": {
        "name_kr": "💥 [워밍업 & 순발력] 점핑잭·버피·무릎당겨점프 (약 5~6분)",
        "name_en": "💥 Cardio & Cadence Jumps (5-6 min)",
        "description_kr": "관절을 푼 후 4박자(1회당 1.5초) 경쾌한 구령으로 버피, 점핑잭, 무릎당겨점프 폭발적 진행",
        "movement_ids": [
            "wrist_ankle", "knee_circles", "forward_back_bend",
            "jumping_jacks_cadence", "squat_jump_cadence", "high_knee_tuck_jump", "burpee_cadence", "breathing_reset"
        ],
        "default_tempo_bpm": 100
    },
    "stamina_strength": {
        "name_kr": "💪 [도장 근지구력 체력단련] 팔굽혀펴기 3종·복근·브릿지 (약 8분)",
        "name_en": "💪 Dojo Strength & Conditioning (8 min)",
        "description_kr": "손바닥/주먹/손가락 푸시업 10회씩 + 플러터킥 + 뒤꿈치차기 + 브릿지(3초-3초-10초)",
        "movement_ids": [
            "wrist_ankle", "forward_back_bend",
            "pushup_palms", "pushup_knuckles", "pushup_fingertips",
            "flutter_kicks", "lying_heel_kicks", "prone_hip_circles", "bridge_hold_3310",
            "breathing_reset"
        ],
        "default_tempo_bpm": 75
    },
    "kick_mobility": {
        "name_kr": "🦵 [고관절 가동성 & 킥 스트레칭] 다이나믹 킥 & 다리찢기 (약 8분)",
        "name_en": "🦵 Kicking Mobility & Splits (8 min)",
        "description_kr": "하체 유연성과 발차기 각도를 위해 런지, 고관절회전, 스윙킥, 나비자세, 다리벌려 숙이기",
        "movement_ids": [
            "knee_bends", "deep_lunge_side", "hip_dynamic_rotation", "hamstring_high_kick",
            "lunge_hip_flexor", "butterfly_pose", "straddle_splits", "breathing_reset"
        ],
        "default_tempo_bpm": 70
    },
    "yoga_core": {
        "name_kr": "🧘‍♀️ [요가 & 필라테스] 척추 정렬 & 코어 8대 전문 시퀀스 (약 9~10분)",
        "name_en": "🧘‍♀️ Yoga & Core Master Sequence (9-10 min)",
        "description_kr": "복식 호흡과 함께 코브라, 비둘기, 전사, 삼각, 플랭크, 척추비틀기, 4자다리, 나비자세 숙이기",
        "movement_ids": [
            "neck_stretches", "cat_cow_flow", "cobra_pose", "downward_dog",
            "pigeon_pose_lr", "warrior_pose_lr", "triangle_pose_lr", "plank_hold_30s",
            "spine_twist_lr", "figure4_glute_stretch", "butterfly_forward_fold", "child_pose", "breathing_reset"
        ],
        "default_tempo_bpm": 60
    },
    "kids_english_fun": {
        "name_kr": "🧒 [유치부·초등 저학년] 신나는 영어 무도 몸풀기 (약 5~6분)",
        "name_en": "🧒 Kids English Martial Arts Fun Warm-up (5-6 min)",
        "description_kr": "핸드, 레그, 니, 넥 등 쉬운 인체 영어와 점핑잭, 앞차기 투 더 페이스가 결합된 놀이형 몸풀기",
        "movement_ids": [
            "wrist_ankle", "knee_bends", "waist_circles", "shoulder_arm_circles",
            "neck_stretches", "jumping_jacks_cadence", "hamstring_high_kick", "child_pose", "breathing_reset"
        ],
        "default_tempo_bpm": 90
    }
}


class WarmupEngine:
    """
    준비운동·스트레칭·도장 체력단련 오디오 시퀀서 엔진
    """

    @classmethod
    def get_movement_dict(cls) -> Dict[str, Dict[str, Any]]:
        return {m["id"]: m for m in MASTER_MOVEMENTS}

    @classmethod
    def get_movement_text(cls, mov: Dict[str, Any], lang: str, mode: str = "detailed") -> Tuple[str, str]:
        """
        언어 모드(kr, mix_kids, dual_step, en_advanced)에 따라 명칭과 사범 멘트를 추출
        """
        # 1. 명칭
        if lang == "mix_kids":
            name = mov.get("name_mix", mov.get("name_kr", ""))
        elif lang == "dual_step":
            name = mov.get("name_dual", mov.get("name_kr", ""))
        elif lang in ("en", "en_advanced"):
            name = mov.get("name_en", mov.get("name_kr", ""))
        else:
            name = mov.get("name_kr", "")

        # 2. 사범 멘트
        if mode == "detailed":
            if lang == "mix_kids":
                cue = mov.get("instruction_mix", mov.get("instruction_kr", ""))
            elif lang == "dual_step":
                cue = mov.get("instruction_dual", mov.get("instruction_kr", ""))
            elif lang in ("en", "en_advanced"):
                cue = mov.get("instruction_en", mov.get("instruction_kr", ""))
            else:
                cue = mov.get("instruction_kr", "")
        else:
            if lang == "mix_kids":
                cue = mov.get("short_cue_mix", mov.get("short_cue_kr", ""))
            elif lang == "dual_step":
                cue = mov.get("short_cue_dual", mov.get("short_cue_kr", ""))
            elif lang in ("en", "en_advanced"):
                cue = mov.get("short_cue_en", mov.get("short_cue_kr", ""))
            else:
                cue = mov.get("short_cue_kr", "")

        return name, cue

    @classmethod
    def build_timeline_events(cls, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        초기 뼈대 이벤트 생성 (예상 시간 배치)
        """
        lang = params.get("language", "kr")
        mode = params.get("coaching_mode", "detailed")
        bpm = params.get("tempo_bpm", 85)
        signal_type = params.get("signal_type", "bell")
        trans_gap = params.get("transition_gap_sec", 1.2)

        # 1박자당 소요 시간 (초 단위)
        beat_interval = 60.0 / max(40, min(140, bpm))

        events: List[Dict[str, Any]] = []
        curr_time = 1.0

        # 1. 시작 멘트
        start_cues_list = START_CUES.get(lang, START_CUES["kr"])
        start_cue = params.get("start_cue", "").strip() or start_cues_list[0]
        start_dur_est = max(3.0, len(start_cue) * (0.13 if lang == "kr" else 0.08))
        events.append({
            "time": round(curr_time, 2),
            "type": "voice",
            "text": start_cue,
            "sound_file": "",
            "track": 3,
            "duration": round(start_dur_est, 2)
        })
        curr_time += start_dur_est + trans_gap

        # 2. 동작 시퀀스
        movement_list = params.get("movements", [])
        if not movement_list:
            routine_key = params.get("routine_key", "standard_full")
            p_data = ROUTINE_PRESETS.get(routine_key, ROUTINE_PRESETS["standard_full"])
            m_dict = cls.get_movement_dict()
            movement_list = [copy.deepcopy(m_dict[mid]) for mid in p_data["movement_ids"] if mid in m_dict]

        for mov in movement_list:
            if not mov.get("enabled", True):
                continue

            mov_name, coach_text = cls.get_movement_text(mov, lang, mode)

            # (1) 신호음
            sig_file = "stage_bell.wav" if signal_type == "bell" else ("whistle.wav" if signal_type == "whistle" else "beep.wav")
            events.append({
                "time": round(curr_time, 2),
                "type": "bell" if signal_type == "bell" else "beep",
                "text": f"[{mov_name}]",
                "sound_file": sig_file,
                "track": 2,
                "duration": 0.8
            })
            curr_time += 0.8

            # (2) 사범 지도/안내 멘트
            coach_dur = max(2.0, len(coach_text) * (0.12 if lang == "kr" else 0.07))
            events.append({
                "time": round(curr_time, 2),
                "type": "voice",
                "text": coach_text,
                "sound_file": "",
                "track": 3,
                "duration": round(coach_dur, 2)
            })
            curr_time += coach_dur + 0.5

            # (3) 구령 생성
            count_type = mov.get("count_type", "8count_x2")
            count_events, count_dur = cls._generate_count_events(
                count_type=count_type,
                lang=lang,
                start_time=curr_time,
                beat_interval=beat_interval
            )
            for ce in count_events:
                events.append(ce)

            curr_time += count_dur + trans_gap

        # 3. 종료 멘트
        end_cues_list = END_CUES.get(lang, END_CUES["kr"])
        end_cue = params.get("end_cue", "").strip() or end_cues_list[0]
        end_dur_est = max(3.0, len(end_cue) * (0.13 if lang == "kr" else 0.08))
        events.append({
            "time": round(curr_time, 2),
            "type": "voice",
            "text": end_cue,
            "sound_file": "",
            "track": 3,
            "duration": round(end_dur_est, 2)
        })
        curr_time += end_dur_est + 1.0

        return {
            "total_duration_sec": round(curr_time, 2),
            "events": events,
            "duck_segments": [],
            "tempo_bpm": bpm,
            "language": lang,
            "coaching_mode": mode
        }

    @classmethod
    def cascade_realign_events(cls, events: List[Dict[str, Any]], trans_gap_sec: float = 0.5) -> Tuple[List[Dict[str, Any]], List[Tuple[int, int]], float]:
        """
        [핵심 음성 겹침 방지 엔진]
        모든 오디오 파일의 실제 물리적 길이(duration)를 기반으로,
        앞선 음성이 100% 끝난 후에 다음 음성이 나오도록 타임스탬프(time)를 처음부터 끝까지 완전 순차 재배치함.
        """
        realigned: List[Dict[str, Any]] = []
        duck_segments: List[Tuple[int, int]] = []
        curr_t = 1.0

        for i, ev in enumerate(events):
            dur = max(0.4, ev.get("duration", 1.0))
            ev_type = ev.get("type", "voice")

            # 이벤트 시작 시간 결정
            ev["time"] = round(curr_t, 2)
            realigned.append(ev)

            # 오토 더킹 구간 등록 (음성 및 구령 시)
            if ev_type in ("voice", "count"):
                start_ms = int(curr_t * 1000)
                end_ms = int((curr_t + dur + 0.3) * 1000)
                duck_segments.append((start_ms, end_ms))

            # 다음 이벤트 시작 시간 계산 (타입별 최적 간격)
            if ev_type == "count":
                # 구령 단어 간격: 오디오 길이 + 0.15초 (숨막히지 않고 타이트하게)
                curr_t += dur + 0.15
            elif ev_type in ("bell", "beep", "whistle"):
                # 신호음 후 멘트/구령: 0.3초 여백
                curr_t += dur + 0.3
            else:
                # 일반 멘트 후: 설정된 여백 (0.5초)
                curr_t += dur + trans_gap_sec

        total_dur = round(curr_t + 1.0, 2)
        return realigned, duck_segments, total_dur

    @classmethod
    def _generate_count_events(
        cls,
        count_type: str,
        lang: str,
        start_time: float,
        beat_interval: float
    ) -> Tuple[List[Dict[str, Any]], float]:
        """
        다양한 도장 맞춤형 카운트 이벤트 생성 (수준별 언어 반영)
        """
        c_events: List[Dict[str, Any]] = []
        t = start_time

        kr_8_set1 = ["하나", "둘", "셋", "넷", "다섯", "여섯", "일곱", "여덟"]
        kr_8_set2 = ["둘", "둘", "셋", "넷", "다섯", "여섯", "일곱", "여덟"]
        kr_8_set3 = ["셋", "둘", "셋", "넷", "다섯", "여섯", "일곱", "여덟"]
        kr_8_set4 = ["넷", "둘", "셋", "넷", "다섯", "여섯", "일곱", "여덟"]

        mix_8_set1 = ["원", "투", "쓰리", "포", "파이브", "식스", "세븐", "에잇"]
        mix_8_set2 = ["투", "투", "쓰리", "포", "파이브", "식스", "세븐", "에잇"]
        mix_8_set3 = ["쓰리", "투", "쓰리", "포", "파이브", "식스", "세븐", "에잇"]
        mix_8_set4 = ["포", "투", "쓰리", "포", "파이브", "식스", "세븐", "에잇"]

        en_8_set1 = ["One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight"]
        en_8_set2 = ["Two", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight"]
        en_8_set3 = ["Three", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight"]
        en_8_set4 = ["Four", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight"]

        def _pick_8sets():
            if lang == "mix_kids":
                return [mix_8_set1, mix_8_set2, mix_8_set3, mix_8_set4]
            elif lang in ("en", "en_advanced", "dual_step"):
                return [en_8_set1, en_8_set2, en_8_set3, en_8_set4]
            return [kr_8_set1, kr_8_set2, kr_8_set3, kr_8_set4]

        # 1. 8박자 x 2회
        if count_type == "8count_x2":
            all_sets = _pick_8sets()
            sets = [all_sets[0], all_sets[1]]
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

        # 2. 8박자 x 4회
        elif count_type == "8count_x4":
            sets = _pick_8sets()
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

        # 3. 등배운동 정통 도장 구령 (손바닥/둘/팔꿈치/넷/뒤로/여섯/일곱/여덟)
        elif count_type == "forward_back_8count":
            if lang == "mix_kids":
                w_list = ["핸드", "투", "엘보우", "포", "룩업", "식스", "세븐", "에잇"]
            elif lang in ("en", "en_advanced", "dual_step"):
                w_list = ["Hands", "Two", "Elbows", "Four", "Look up", "Six", "Seven", "Eight"]
            else:
                w_list = ["손바닥", "둘", "팔꿈치", "넷", "뒤로", "여섯", "일곱", "여덟"]

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

        # 4. 점핑잭 / 버피 / 쪼그려점프 / 무릎당겨점프 4박자 케이던스 ("하나, 둘, 셋, [횟수]!")
        # 1회당 약 1.5초 소요 (빠르고 경쾌함)
        elif count_type in ("cadence_10reps", "reps_10"):
            cadence_int = 0.38  # 0.38초 x 4 = 1.52초 (1회당 1.5초 정확한 박자!)
            kr_reps = ["하나!", "둘!", "셋!", "넷!", "다섯!", "여섯!", "일곱!", "여덟!", "아홉!", "열!"]
            mix_reps = ["원!", "투!", "쓰리!", "포!", "파이브!", "식스!", "세븐!", "에잇!", "나인!", "텐!"]
            en_reps = ["One!", "Two!", "Three!", "Four!", "Five!", "Six!", "Seven!", "Eight!", "Nine!", "Ten!"]

            if lang == "mix_kids":
                base_cues = ["원", "투", "쓰리"]
                rep_list = mix_reps
            elif lang in ("en", "en_advanced", "dual_step"):
                base_cues = ["One", "Two", "Three"]
                rep_list = en_reps
            else:
                base_cues = ["하나", "둘", "셋"]
                rep_list = kr_reps

            for rep_idx in range(10):
                final_cue = rep_list[rep_idx]
                words = [base_cues[0], base_cues[1], base_cues[2], final_cue]
                for w in words:
                    c_events.append({
                        "time": round(t, 2),
                        "type": "count",
                        "text": w,
                        "sound_file": "",
                        "track": 3,
                        "duration": 0.32
                    })
                    t += cadence_int

        # 5. 팔굽혀펴기 / 단일 횟수제 ("하나!... 둘!... 셋!...") 큰 동작 여유 있는 박자 (1회당 약 2.0초)
        elif count_type == "single_rep_10":
            kr_singles = ["하나!", "둘!", "셋!", "넷!", "다섯!", "여섯!", "일곱!", "여덟!", "아홉!", "열!"]
            mix_singles = ["원!", "투!", "쓰리!", "포!", "파이브!", "식스!", "세븐!", "에잇!", "나인!", "텐!"]
            en_singles = ["One!", "Two!", "Three!", "Four!", "Five!", "Six!", "Seven!", "Eight!", "Nine!", "Ten!"]

            if lang == "mix_kids":
                s_list = mix_singles
            elif lang in ("en", "en_advanced", "dual_step"):
                s_list = en_singles
            else:
                s_list = kr_singles

            for rep_w in s_list:
                c_events.append({
                    "time": round(t, 2),
                    "type": "count",
                    "text": rep_w,
                    "sound_file": "",
                    "track": 3,
                    "duration": 0.8
                })
                t += 2.0  # 1회 푸시업 수행 시간 2초

        # 6. 플러터 킥 (번갈아 다리 올리기 20회)
        elif count_type == "alternate_20reps":
            if lang == "mix_kids":
                alt_list = ["레프트", "라이트"] * 10
            elif lang in ("en", "en_advanced", "dual_step"):
                alt_list = ["Left", "Right"] * 10
            else:
                alt_list = ["왼발", "오른발"] * 10

            for alt_w in alt_list:
                c_events.append({
                    "time": round(t, 2),
                    "type": "count",
                    "text": alt_w,
                    "sound_file": "",
                    "track": 3,
                    "duration": 0.4
                })
                t += 0.6

        # 7. 브릿지 골반 들기 (하나 3초, 둘 3초, 셋 10초) 특수 패턴
        elif count_type == "bridge_pattern":
            hold_cue1 = "하나, 들고 버팁니다!" if lang == "kr" else ("원, 힙 업 홀드!" if lang == "mix_kids" else "One, lift and hold!")
            down_cue = "바로!" if lang in ("kr", "mix_kids") else "Down!"
            hold_cue2 = "둘, 높이 듭니다!" if lang == "kr" else ("투, 하이 홀드!" if lang == "mix_kids" else "Two, hold high!")
            hold_cue3 = "셋! 10초간 힘차게 유지!" if lang == "kr" else ("쓰리! 텐 세컨즈 홀드!" if lang == "mix_kids" else "Three! Hold for ten seconds!")
            warn_5s = "5초 전..." if lang == "kr" else ("파이브 세컨즈..." if lang == "mix_kids" else "5 seconds...")
            done_cue = "바로! 수고했습니다." if lang in ("kr", "mix_kids") else "Down! Good job."

            # 1회차: 3초 홀드
            c_events.append({"time": round(t, 2), "type": "count", "text": hold_cue1, "sound_file": "", "track": 3, "duration": 1.5})
            t += 3.0
            c_events.append({"time": round(t, 2), "type": "voice", "text": down_cue, "sound_file": "", "track": 3, "duration": 0.8})
            t += 1.5

            # 2회차: 3초 홀드
            c_events.append({"time": round(t, 2), "type": "count", "text": hold_cue2, "sound_file": "", "track": 3, "duration": 1.5})
            t += 3.0
            c_events.append({"time": round(t, 2), "type": "voice", "text": down_cue, "sound_file": "", "track": 3, "duration": 0.8})
            t += 1.5

            # 3회차: 10초 롱 홀드 카운트다운
            c_events.append({"time": round(t, 2), "type": "count", "text": hold_cue3, "sound_file": "", "track": 3, "duration": 2.0})
            t += 4.5
            c_events.append({"time": round(t, 2), "type": "voice", "text": warn_5s, "sound_file": "", "track": 3, "duration": 1.0})
            t += 1.0
            for cn in ["4", "3", "2", "1"]:
                c_events.append({"time": round(t, 2), "type": "count", "text": cn, "sound_file": "", "track": 3, "duration": 0.6})
                t += 1.0
            c_events.append({"time": round(t, 2), "type": "voice", "text": done_cue, "sound_file": "", "track": 3, "duration": 1.2})
            t += 2.0

        # 8. 정적 유지 홀딩 (15초 / 30초)
        elif count_type.startswith("hold_"):
            hold_sec = 30.0 if "30s" in count_type else (15.0 if "15s" in count_type else 10.0)
            t += hold_sec - 5.0
            pre_cue = "호흡하며 5초 전..." if lang == "kr" else ("브레스 홀드, 5초 전..." if lang == "mix_kids" else "Keep breathing... 5 seconds left!")
            c_events.append({
                "time": round(t, 2),
                "type": "voice",
                "text": pre_cue,
                "sound_file": "",
                "track": 3,
                "duration": 1.5
            })
            t += 1.5
            for c_num in ["4", "3", "2", "1"]:
                c_events.append({
                    "time": round(t, 2),
                    "type": "count",
                    "text": c_num,
                    "sound_file": "",
                    "track": 3,
                    "duration": 0.6
                })
                t += 0.9
            relax_cue = "바로!" if lang in ("kr", "mix_kids") else "Relax!"
            c_events.append({
                "time": round(t, 2),
                "type": "voice",
                "text": relax_cue,
                "sound_file": "",
                "track": 3,
                "duration": 0.8
            })
            t += 1.2

        # 9. 심호흡 및 호흡 주기
        elif count_type in ("breathing", "breathing_cycle"):
            if lang == "kr":
                steps = [
                    ("숨을 천천히 들이마시고...", 3.0),
                    ("길게 내쉽니다...", 3.5),
                    ("한 번 더 깊게 들이마시고...", 3.0),
                    ("편안하게 내쉽니다.", 3.5)
                ]
            elif lang == "mix_kids":
                steps = [
                    ("브레스 인(Breathe in), 숨 들이마시고...", 3.0),
                    ("브레스 아웃(Breathe out), 길게 후 내쉬고...", 3.5),
                    ("원 모어 타임, 깊게 들이마시고...", 3.0),
                    ("편안하게 릴랙스 내쉽니다.", 3.5)
                ]
            else:
                steps = [
                    ("Breathe in slowly through your nose...", 3.0),
                    ("Breathe out gently and relax...", 3.5),
                    ("One more deep breath in...", 3.0),
                    ("And blow it all out smoothly.", 3.5)
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
