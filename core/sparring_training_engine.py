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
import re
from typing import List, Dict, Any, Tuple
from pydub import AudioSegment
from core.shuttle_run_engine import ShuttleRunEngine


def clean_speech_text(text: str) -> str:
    """
    TTS 음성 합성용 텍스트에서 이모지(도복 🥋, 번개 ⚡ 등) 및 화살표, 특수기호를 완벽하게 제거하여
    '도복', '화살표' 같은 불필요한 단어가 발음되는 것을 원천 차단하고 순수 자연어 구령만 추출
    """
    if not text:
        return ""
    # 유니코드 이모지 (도복 🥋, 번개 ⚡, 달리기 🏃, 근육 💪, 펀치 🥊 등 전 범위)
    t = re.sub(r'[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\u2300-\u23ff]|[\u2b50-\u2b55]|[\u203c-\u2049]', '', text)
    # 화살표 및 불필요한 특수기호
    t = re.sub(r'->|➔|▶|=>|◀|<-|★|※|#|@', ' ', t)
    # 가운뎃점(·), 불릿, 슬래시(/) 등은 자연스러운 쉼(공백)으로 처리
    t = re.sub(r'[·•\/\\]', ' ', t)
    # 한글과 영단어 and가 붙어 발음이 꼬이는 현상 완벽 방어 ("점프and" -> "점프 그리고", "and발차기" -> "그리고 발차기")
    t = re.sub(r'([가-힣])\s*and\s*([가-힣])', r'\1 그리고 \2', t, flags=re.IGNORECASE)
    t = re.sub(r'([가-힣])\s*and\b', r'\1 그리고 ', t, flags=re.IGNORECASE)
    t = re.sub(r'\band\s*([가-힣])', r' 그리고 \1', t, flags=re.IGNORECASE)
    # & 기호 변환: 한글 문맥에서는 자연스럽게 '그리고', 영문 문맥에서는 'and'로 명확히 처리
    t = re.sub(r'([가-힣])\s*&\s*([가-힣])', r'\1 그리고 \2', t)
    t = re.sub(r'([가-힣])\s*&', r'\1 그리고 ', t)
    t = re.sub(r'&\s*([가-힣])', r' 그리고 \1', t)
    t = re.sub(r'([A-Za-z])\s*&\s*([A-Za-z])', r'\1 and \2', t)
    t = re.sub(r'\s*&\s*', ' 그리고 ', t)
    # 한국어 문맥에서 '3회'가 '셋'이나 '셋 회'로 어색하게 읽히는 현상 원천 방지 (한자어 수사 '삼 회' 표준화)
    ko_count_map = {
        '1': '일', '2': '이', '3': '삼', '4': '사', '5': '오',
        '6': '육', '7': '칠', '8': '팔', '9': '구', '10': '십'
    }
    t = re.sub(r'(?<!\d)([1-9]|10)\s*회(?=(?:와|과|씩|로|를|는|만|도|에|의|후|\s|$|[.,!?;:\-\)]))', lambda m: f"{ko_count_map.get(m.group(1), m.group(1))} 회", t)
    # 대괄호 문자 정리
    t = t.replace('[', ' ').replace(']', ' ')
    # 앞뒤 불필요한 기호 및 중복 공백 정제
    t = re.sub(r'^[(\s\-_:]+|[)\s\-_:]+$', '', t)
    return re.sub(r'\s+', ' ', t).strip()


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


# ── 도장 고강도 기능성 서킷 인터벌 5대 복합 콤보 테마 (체력 + 발차기 + 낙법/점프 무한 반복 루프) ──
CIRCUIT_INTERVAL_THEMES = {
    "power_agility": {
        "name_kr": "[실전 대련과 낙법 협응] 점프·발차기·전방낙법 루프",
        "name_mix": "[실전 대련과 낙법 협응] 파워 점프와 나래차기 루프",
        "name_dual": "[실전 대련과 낙법 협응] 파워 점프와 나래차기 루프",
        "name_en": "Combat & Forward Breakfall Flow Interval",
        "desc": "점프와 발차기, 전방낙법을 쉼 없이 연결하여 실전 순발력과 신체 협응력을 기르는 훈련",
        "exercises": [
            {
                "kr": "스쿼트 점프 3회 후 나래차기 연타, 전방낙법 후 신속히 일어나기! 쉼 없이 반복!",
                "mix": "스쿼트 점프 3회 후 나래차기와 전방낙법! - Three squat jumps! Double kicks! Front roll breakfall!",
                "dual": "스쿼트 점프 3회 후 나래차기와 전방낙법! - Three squat jumps, double kicks, front roll breakfall!",
                "en": "Three squat jumps, double kicks, front roll breakfall! Non-stop loop!",
                "tip": "스쿼트 점프 3회 ➔ 양발 나래차기 연타 ➔ 전방 회전낙법 후 신속하게 다음 동작 연결"
            },
            {
                "kr": "전력 버피 1회 후 몸통 2연타, 180도 점프 턴! 쉼 없이 반복!",
                "mix": "전력 버피 1회 후 몸통 2연타! - One burpee! Two body kicks! Jump turn!",
                "dual": "전력 버피 1회 후 몸통 2연타와 180도 점프 턴! - One burpee, two body kicks, jump turn!",
                "en": "One burpee, two body kicks, 180-degree jump turn! Non-stop loop!",
                "tip": "전력 버피 1회 ➔ 전진 몸통 2연타 ➔ 공중 180도 점프 뒤돌아 착지 후 신속히 다음 반복"
            },
            {
                "kr": "무릎 점프 2회 후 앞발 컷트, 상단 하이킥! 쉼 없이 반복!",
                "mix": "무릎 점프 2회 후 앞발 컷트, 하이킥! - Two knee tuck jumps! Cut kick! High kick!",
                "dual": "무릎 높이 점프 2회 후 앞발 컷트와 상단 하이킥! - Two knee tuck jumps, front cut, high kick!",
                "en": "Two knee tuck jumps, front cut to high kick! Keep repeating!",
                "tip": "무릎 높이 점프 2회 ➔ 앞발 컷트 견제 ➔ 뒷발 머리 상단 돌려차기 후 신속히 복귀"
            },
            {
                "kr": "바닥 푸시업 2회 후 백스텝, 카운터 뒤차기! 쉼 없이 반복!",
                "mix": "바닥 푸시업 2회 후 백스텝, 카운터 뒤차기! - Two pushups! Step back! Back kick!",
                "dual": "바닥 푸시업 2회 후 신속히 백스텝 카운터 뒤차기! - Two pushups, step back, counter back kick!",
                "en": "Two pushups, explosive step back, counter back kick! Non-stop loop!",
                "tip": "바닥 푸시업 2회 ➔ 신속히 일어나 백스텝 ➔ 카운터 뒤차기 무한 반복"
            },
            {
                "kr": "제자리 턱점프 2회 후 뛰어 돌개차기! 쉼 없이 반복!",
                "mix": "제자리 턱점프 2회 후 뛰어 돌개차기! - Two tuck jumps! Tornado kick! Go!",
                "dual": "턱점프 2회 후 공중 360도 돌개차기! - Two tuck jumps, jumping tornado kick!",
                "en": "Two tuck jumps, jumping tornado 360 kick! Non-stop loop!",
                "tip": "무릎 턱점프 2회 ➔ 공중 회전 돌개차기 ➔ 착지 후 신속히 대련자세 복귀"
            },
            {
                "kr": "사이드 스텝 좌우 터치 후 빠른 상단차기! 쉼 없이 반복!",
                "mix": "사이드 스텝 좌우 터치 후 빠른 상단차기! - Two side touches! Fast high kick! Switch!",
                "dual": "사이드 스텝 좌우 터치 후 신속한 상단차기! - Two side touches, rapid high kick!",
                "en": "Two side touches, rapid lead high kick! Keep moving!",
                "tip": "좌우 사이드 스텝 바닥 터치 ➔ 앞발 기습 상단차기 후 신속히 다음 반복"
            }
        ]
    },
    "agility_power_combo": {
        "name_kr": "[순발력 그리고 민첩성 폭발 콤보] 버피·점프턴·나래차기 루프",
        "name_mix": "[순발력 그리고 민첩성 폭발] 버피 그리고 나래차기 루프",
        "name_dual": "[순발력 그리고 민첩성 폭발] 버피 그리고 나래차기 루프",
        "name_en": "Agility & Explosive Kick Flow",
        "desc": "15~20초 동안 [전신 순발력 ➔ 폭풍 스피드 발차기 ➔ 공중 방향전환]을 결합한 고강도 협응 인터벌",
        "exercises": [
            {
                "kr": "전력 버피 1회 후 공중 나래차기 연타! 쉼 없이 반복!",
                "mix": "전력 버피 1회 후 공중 나래차기 연타! - One time! Rapid double kicks! Go!",
                "dual": "용수철 버피 1회 후 폭풍 나래차기 연타! - One time, rapid double kicks!",
                "en": "One time burpee, rapid double kicks! Non-stop loop!",
                "tip": "전력 버피 1회 ➔ 공중 나래차기 2연타 ➔ 즉시 다음 반복"
            },
            {
                "kr": "쪼그려 점프 3회 후 앞발 빠른 상단차기! 쉼 없이 반복!",
                "mix": "쪼그려 점프 3회 후 빠른 상단차기! - Three times! Fast snap kick! Turn!",
                "dual": "스쿼트 점프 3회 후 앞발 빠른 상단차기! - Three times, rapid snap kick!",
                "en": "Three times squat jumps, rapid high snap kicks! Non-stop loop!",
                "tip": "깊게 쪼그려 점프 3회 ➔ 앞발 빠른 상단차기 2회 무한 반복"
            },
            {
                "kr": "초고속 발구르기 3초 후 전진 몸통 3연타! 쉼 없이 반복!",
                "mix": "초고속 발구르기 후 전진 몸통 3연타! - Three times! Fast feet! Body kicks!",
                "dual": "초고속 지면 발구르기 후 전진 몸통 3연타! - Three times sprint, triple body kicks!",
                "en": "Three seconds fast feet sprint, three body kicks! Non-stop loop!",
                "tip": "제자리 초고속 발구르기 3초 ➔ 전진하며 몸통 3연타 무한 반복"
            },
            {
                "kr": "마운틴 클라이머 4회 후 연속 앞차기 4회! 쉼 없이 반복!",
                "mix": "마운틴 클라이머 4회 후 연속 앞차기! - Four times! Four front kicks!",
                "dual": "마운틴 클라이머 4회 후 폭풍 연속 앞차기! - Four times, alternating front kicks!",
                "en": "Four times mountain climbers, four alternating front kicks! Non-stop loop!",
                "tip": "엎드려 마운틴 클라이머 4회 ➔ 신속히 일어나서 연속 앞차기 4회 무한 반복"
            },
            {
                "kr": "앞뒤 셔플 스텝 3회 후 돌개차기! 쉼 없이 반복!",
                "mix": "앞뒤 셔플 스텝 3회 후 돌개차기! - Three times! Tornado kick! Move!",
                "dual": "앞뒤 쾌속 셔플 3회 후 공중 돌개차기! - Three times, explosive tornado kick!",
                "en": "Three times in-and-out shuffles, tornado kick! Keep pushing!",
                "tip": "앞뒤 셔플 스텝 3회 ➔ 공중 360도 돌개차기 무한 반복"
            },
            {
                "kr": "무릎 점프 2회 후 좌우 나래차기, 백스텝! 쉼 없이 반복!",
                "mix": "무릎 점프 2회 후 좌우 나래차기! - Two times! Double kicks! Step back!",
                "dual": "무릎 점프 2회 후 좌우 나래차기와 백스텝 회피! - Two times, double kicks, step back!",
                "en": "Two times knee tuck jumps, double kicks, step back! Non-stop loop!",
                "tip": "무릎 가슴 점프 2회 ➔ 좌우 연속 나래차기 ➔ 백스텝 복귀 무한 반복"
            }
        ]
    },
    "footwork_reaction_combo": {
        "name_kr": "[스파링 풋워크 그리고 카운터 공방] 스텝·컷트·뒤차기 루프",
        "name_mix": "[스파링 풋워크 그리고 카운터] 스텝 그리고 컷트 루프",
        "name_dual": "[스파링 풋워크 그리고 카운터] 스텝 그리고 컷트 루프",
        "name_en": "Sparring Footwork & Reaction Flow",
        "desc": "15~20초 동안 [대련 스텝 풋워크 ➔ 상대 격파 발차기 ➔ 신속한 회피 동작]을 무한 반복하는 실전 스파링 서킷",
        "exercises": [
            {
                "kr": "사이드 스텝 좌우 터치 후 카운터 뒤차기! 쉼 없이 반복!",
                "mix": "사이드 스텝 터치 후 카운터 뒤차기! - Side touch! Counter back kick!",
                "dual": "사이드 스텝 좌우 터치 후 백스텝 카운터 뒤차기! - Side touch, counter back kick!",
                "en": "Two times step touch, counter back kick! Non-stop loop!",
                "tip": "사이드 스텝 좌우 바닥 터치 ➔ 한 걸음 빠지며 카운터 뒤차기 무한 반복"
            },
            {
                "kr": "앞뒤 스텝 3단 전진 후 앞발 컷트, 상단 돌려차기! 쉼 없이 반복!",
                "mix": "앞뒤 스텝 후 앞발 컷트, 상단 돌려차기! - In and out! Cut kick! High kick!",
                "dual": "앞뒤 리듬 스텝 후 앞발 컷트와 상단 돌려차기! - In and out steps, lead cut, high kick!",
                "en": "Three times in-and-out steps, lead cut to high kick! Non-stop loop!",
                "tip": "앞뒤 리듬 스텝 3회 ➔ 앞발 컷트 저지 ➔ 뒷발 상단 돌려차기 무한 반복"
            },
            {
                "kr": "양발 스위치 2회 후 전진 몸통 3연타! 쉼 없이 반복!",
                "mix": "양발 스위치 2회 후 전진 몸통 3연타! - Two switches! Three body kicks!",
                "dual": "스탠스 스위치 2회 후 전진 몸통 3연타! - Two switches, triple body kicks!",
                "en": "Two times stance switches, three body kicks! Non-stop loop!",
                "tip": "대련 자세 양발 스위치 2회 ➔ 밀고 들어가며 몸통 3연타 무한 반복"
            },
            {
                "kr": "지그재그 회피 스텝 후 기습 나래차기! 쉼 없이 반복!",
                "mix": "지그재그 회피 스텝 후 기습 나래차기! - Zigzag steps! Double kicks!",
                "dual": "지그재그 사각 회피 후 기습 나래차기! - Zigzag evasion, rapid double kicks!",
                "en": "Zigzag evasion footwork, surprise double kicks! Non-stop loop!",
                "tip": "공격선 비켜서는 지그재그 스텝 ➔ 공중 나래차기 연타 무한 반복"
            },
            {
                "kr": "위빙으로 주먹 회피 후 카운터 돌려차기! 쉼 없이 반복!",
                "mix": "위빙 회피 후 카운터 돌려차기! - Weave down! Counter roundhouse kick!",
                "dual": "아래로 위빙 회피 후 카운터 돌려차기! - Duck and weave, counter roundhouse kick!",
                "en": "Weave under punch, counter roundhouse kick! Non-stop loop!",
                "tip": "상대 주먹 아래로 위빙 회피 ➔ 즉시 몸통 카운터 돌려차기 무한 반복"
            },
            {
                "kr": "앞손 페이크 동작 후 전광석화 뒤후리기! 쉼 없이 반복!",
                "mix": "앞손 페이크 후 전광석화 뒤후리기! - Fake punch! Spinning hook kick!",
                "dual": "상단 유인 페이크 후 전광석화 뒤후리기! - Lead fake, spinning hook kick!",
                "en": "Lead fake punch, spinning hook kick! Finish strong!",
                "tip": "앞손 페이크로 상대 가드 분산 ➔ 머리 상단 뒤후리기 무한 반복"
            }
        ]
    },
    "strength_endurance_combo": {
        "name_kr": "[근지구력 그리고 전신 파워 서킷] 푸시업·복근·연타킥 서킷",
        "name_mix": "[근지구력 그리고 전신 파워] 푸시업·복근·연타킥 서킷",
        "name_dual": "[근지구력 그리고 전신 파워] 푸시업·복근·연타킥 서킷",
        "name_en": "Endurance Strength & Striking Circuit",
        "desc": "15~20초 동안 [체력 단련 ➔ 전력 타격 ➔ 심폐 파워]를 한 세트로 묶어 무한 반복하는 서킷",
        "exercises": [
            {
                "kr": "손바닥 푸시업 2회 후 빠르게 일어나 몸통 3연타! 쉼 없이 반복!",
                "mix": "손바닥 푸시업 2회 후 몸통 3연타! - Two pushups! Pop up! Three body kicks!",
                "dual": "바닥 푸시업 2회 후 빠르게 일어나 몸통 3연타! - Two pushups, spring up, three body kicks!",
                "en": "Two sets pushups, spring up, three body kicks! Non-stop loop!",
                "tip": "가슴 바닥 푸시업 2회 ➔ 신속히 일어나 전진 몸통 3연타 무한 반복"
            },
            {
                "kr": "마운틴 클라이머 6회 후 교차 나래차기! 쉼 없이 반복!",
                "mix": "마운틴 클라이머 6회 후 교차 나래차기! - Six climbers! Double kicks!",
                "dual": "마운틴 클라이머 6회 후 공중 나래차기! - Six climbers, jumping double kicks!",
                "en": "Six times mountain climbers, alternating double kicks! Non-stop loop!",
                "tip": "엎드려 마운틴 클라이머 6회 ➔ 재빨리 일어나 공중 나래차기 무한 반복"
            },
            {
                "kr": "V업 복근 2회 후 빠르게 일어나 좌우 하이킥! 쉼 없이 반복!",
                "mix": "V업 복근 2회 후 빠르게 일어나 하이킥! - Two V-ups! Pop up! High kick!",
                "dual": "V업 복근 2회 후 신속히 일어나 좌우 하이킥! - Two V-ups, spring up, double high kicks!",
                "en": "Two sets V-ups, stand up quick, two high kicks! Non-stop loop!",
                "tip": "손끝 발끝 V업 복근 2회 ➔ 반동으로 빠르게 일어나 좌우 하이킥 무한 반복"
            },
            {
                "kr": "스쿼트 점프 3회 후 앞발 컷트, 카운터 뒤차기! 쉼 없이 반복!",
                "mix": "스쿼트 점프 3회 후 컷트, 뒤차기! - Three squat jumps! Cut kick! Back kick!",
                "dual": "스쿼트 점프 3회 후 앞발 컷트 카운터 뒤차기! - Three squat jumps, front cut, back kick!",
                "en": "Three times squat jumps, front cut, counter back kick! Non-stop loop!",
                "tip": "깊게 스쿼트 점프 3회 ➔ 앞발 컷트 ➔ 번개 카운터 뒤차기 무한 반복"
            },
            {
                "kr": "플랭크 잭 4회 후 빠르게 일어나 연속 돌려차기! 쉼 없이 반복!",
                "mix": "플랭크 잭 4회 후 연속 돌려차기! - Four plank jacks! Pop up! Continuous kicks!",
                "dual": "플랭크 잭 4회 후 신속히 일어나 연속 돌려차기! - Four plank jacks, spring up, rapid kicks!",
                "en": "Four times plank jacks, spring up, rapid roundhouse kicks! Keep going!",
                "tip": "플랭크 다리 벌렸다 모으기 4회 ➔ 신속히 일어나 연속 돌려차기 무한 반복"
            },
            {
                "kr": "팔벌려뛰기 4회 후 전방낙법, 신속히 일어나 몸통 2연타! 쉼 없이 반복!",
                "mix": "팔벌려뛰기 4회 후 전방낙법, 몸통 2연타! - Four jumping jacks! Front roll breakfall! Two body kicks!",
                "dual": "점핑 잭 4회 후 전방 회전낙법과 몸통 2연타! - Four jumping jacks, front roll breakfall, two body kicks!",
                "en": "Four times jumping jacks, front roll breakfall, two body kicks! Push it!",
                "tip": "팔벌려뛰기 4회 ➔ 전방 회전낙법 후 신속히 일어나 몸통 2연타 무한 반복"
            }
        ]
    },
    "taekwondo_sparring_tactics": {
        "name_kr": "[겨루기 실전 전술 콤보] 나래차기·뒤후리기·돌개차기 루프",
        "name_mix": "[겨루기 실전 전술] 나래차기·뒤후리기·돌개차기 루프",
        "name_dual": "[겨루기 실전 전술] 나래차기·뒤후리기·돌개차기 루프",
        "name_en": "TKD Sparring Tactics & Knockout Combo",
        "desc": "15~20초 동안 [앞발 컷트 견제 ➔ 기습 회전타격 ➔ 카운터 맞받아치기] 실전 겨루기 승리 콤보를 무한 반복하는 전술 인터벌",
        "exercises": [
            {
                "kr": "앞발 컷트 견제 후 전진 나래차기 연타! 쉼 없이 반복!",
                "mix": "앞발 컷트 견제 후 전진 나래차기! - Cut kick! Forward double kicks! Step back!",
                "dual": "앞발 컷트 차단 후 전진 나래차기 연타! - Lead cut stop, forward double kicks!",
                "en": "Lead cut kick to stop, forward rapid double kicks! Non-stop loop!",
                "tip": "앞발 컷트로 상대 돌진 저지 ➔ 뒷발 따라붙으며 나래차기 ➔ 백스텝 복귀"
            },
            {
                "kr": "맞받아치기 몸통차기 후 공중 돌개차기! 쉼 없이 반복!",
                "mix": "맞받아 몸통차기 후 공중 돌개차기! - Counter body kick! Tornado kick! Move!",
                "dual": "상대 공격 맞받아 몸통차기 후 공중 돌개차기! - Counter body kick, aerial tornado kick!",
                "en": "Counter body kick, explosive tornado 360 kick! Non-stop loop!",
                "tip": "상대 진입 순간 카운터 몸통차기 ➔ 탄력 이어받아 공중 360도 돌개차기"
            },
            {
                "kr": "상단 페이크 후 복부 몸통 2연타, 회전 뒤후리기! 쉼 없이 반복!",
                "mix": "상단 페이크 후 복부 2연타, 뒤후리기! - High fake! Two body kicks! Hook kick!",
                "dual": "상단 유인 페이크 후 복부 2연타와 뒤후리기! - High fake, double body kicks, spinning hook kick!",
                "en": "High fake, two body kicks, spinning hook kick! Keep pushing!",
                "tip": "얼굴 페이크로 시선 유인 ➔ 열린 몸통에 2연타 ➔ 머리 회전 뒤후리기"
            },
            {
                "kr": "클린치 밀어내기 후 기습 카운터 뒤차기! 쉼 없이 반복!",
                "mix": "클린치 밀어내기 후 기습 뒤차기! - Push away! Lightning back kick! Turn around!",
                "dual": "접전 밀어내기 후 번개 뒤차기 카운터! - Push away, lightning back kick, jump turn!",
                "en": "Push away from clinch, lightning back kick! Finish strong!",
                "tip": "붙었을 때 어깨로 밀어내며 공간 확보 ➔ 번개 카운터 뒤차기 꽂기"
            },
            {
                "kr": "앞발 상단 도끼찍기 후 반대발 뒤후리기! 쉼 없이 반복!",
                "mix": "앞발 도끼찍기 후 반대발 뒤후리기! - Lead axe kick! Spinning hook kick!",
                "dual": "앞발 상단 도끼찍기 후 연계 뒤후리기! - Lead axe kick, follow-up spinning hook kick!",
                "en": "Lead axe kick, follow-up spinning hook kick! Keep balance!",
                "tip": "앞발을 높이 올려 상단 도끼찍기 ➔ 착지 탄력으로 반대발 머리 뒤후리기"
            },
            {
                "kr": "리듬 바운스 스텝 후 앞발 기습 상단차기! 쉼 없이 반복!",
                "mix": "바운스 스텝 후 앞발 기습 상단차기! - Bounce! Surprise lead high kick! Cut!",
                "dual": "리듬 바운스 스텝 후 기습 앞발 상단차기! - Rhythm bounce, surprise lead high kick!",
                "en": "Rhythm bounce steps, surprise lead head kick! Non-stop loop!",
                "tip": "가볍게 뛰며 상대 타이밍 뺏기 ➔ 예비동작 없이 앞발로 얼굴 상단차기"
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
    def get_random_circuit_routine(cls, theme_key: str = "power_agility", lang: str = "mix_kids", count: int = 4) -> List[Dict[str, str]]:
        """
        지정된 테마의 풍부한 동작 풀(Pool)에서 중복 없이 count개의 신선한 콤보를 무작위로 추출하여 반환
        """
        theme_data = CIRCUIT_INTERVAL_THEMES.get(theme_key, CIRCUIT_INTERVAL_THEMES.get("power_agility", {}))
        pool = list(theme_data.get("exercises", []))
        if not pool:
            return []
        if len(pool) <= count:
            selected = pool.copy()
            random.shuffle(selected)
            return selected
        return random.sample(pool, count)

    @classmethod
    def parse_custom_circuit_text(cls, text: str) -> List[Dict[str, str]]:
        """
        Parses customized combo routine text into structured exercise dictionaries.
        Supports:
          - "1번 콤보: ...", "1번: ...", "1. ...", "[1세트] ...", "1) ...", "1 - ...", "콤보 1: ..."
          - Tip lines containing "지도 팁", "➔ [지도", "-> [지도", "지도 요령", "요령", "주의사항", "설명"
          - Arrow bullet lines (->, ➔, ▶, =>) attached to the previous combo
          - Raw text lines
        """
        if not text or not text.strip():
            return []

        import re
        lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
        exercises = []
        current_item = None

        tip_markers = [
            "[지도 팁]", "지도 팁", "➔ [지도", "-> [지도", "[지도팁]", "지도팁",
            "[팁]", "팁:", "[요령]", "요령:", "지도 요령:", "지도요령:",
            "★", "※", "[주의사항]", "주의사항:", "[설명]", "설명:"
        ]

        for line in lines:
            is_tip_marker = any(m in line for m in tip_markers)
            is_arrow_bullet = (current_item is not None) and bool(re.match(r"^(?:->|➔|▶|=>|[*•-])\s*", line))

            if is_tip_marker or is_arrow_bullet:
                if current_item:
                    tip_text = line
                    for m in tip_markers:
                        if m in tip_text:
                            tip_text = tip_text.split(m, 1)[-1]
                            break
                    # Strip leading arrow/colons/brackets
                    tip_text = re.sub(r"^(?:->|➔|▶|=>|[:\-\]\s•*])+", "", tip_text).strip()
                    tip_text = tip_text.replace("]", "").strip()
                    # Clean arrows inside tip for natural voice speech
                    speech_tip = re.sub(r"\s*(?:->|➔|▶|=>)\s*", ", ", tip_text).strip()
                    current_item["tip"] = tip_text
                    current_item["speech_tip"] = speech_tip
                continue

            # Check if line starts with combo marker like '1번 콤보:', '1.', '[1세트]', '1)', '1 -', '콤보 1:'
            m = re.match(r"^(?:\[?\d+세트\]?|\d+번\s*(?:콤보)?|\d+[\.\)\-]|콤보\s*\d+)\s*[:\-\.]?\s*(.+)$", line)
            if m:
                combo_text = m.group(1).strip()
            else:
                combo_text = line.strip()

            if combo_text:
                current_item = {
                    "kr": combo_text,
                    "mix": combo_text,
                    "dual": combo_text,
                    "en": combo_text,
                    "tip": "",
                    "speech_tip": ""
                }
                exercises.append(current_item)

        return exercises

    @classmethod
    def _add_stop_signal_event(
        cls,
        events: List[Dict[str, Any]],
        duck_segments: List[Tuple[int, int]],
        curr_time: float,
        stop_signal: str,
        label: str = "종료"
    ) -> float:
        """
        Appends the selected stop signal event (referee voice or sound effect)
        and returns the elapsed time offset for the next sequence.
        Note: Sound effects (whistle, beep, bell) do NOT duck music to keep background music natural and smooth.
        """
        stop_sig = str(stop_signal or "voice_kalyeo").strip()
        if stop_sig == "voice_kalyeo":
            events.append({
                "time": curr_time,
                "type": "voice",
                "text": f"[{label}] 갈려~!",
                "duration": 1.2,
                "track": 2,
                "vol": 2.8
            })
            if duck_segments is not None:
                duck_segments.append((int(curr_time * 1000), int((curr_time + 1.3) * 1000)))
            return 1.3
        elif stop_sig == "voice_stop":
            events.append({
                "time": curr_time,
                "type": "voice",
                "text": f"[{label}] 중지!",
                "duration": 0.7,
                "track": 2,
                "vol": 2.8
            })
            if duck_segments is not None:
                duck_segments.append((int(curr_time * 1000), int((curr_time + 0.8) * 1000)))
            return 0.8
        elif stop_sig == "voice_end":
            events.append({
                "time": curr_time,
                "type": "voice",
                "text": f"[{label}] 그만!",
                "duration": 0.7,
                "track": 2,
                "vol": 2.8
            })
            if duck_segments is not None:
                duck_segments.append((int(curr_time * 1000), int((curr_time + 0.8) * 1000)))
            return 0.8
        elif stop_sig == "whistle":
            events.append({
                "time": curr_time,
                "type": "signal",
                "text": f"[{label}] 심판 호각",
                "sound_file": os.path.join("effects", "whistle.wav"),
                "duration": 0.35,
                "track": 1,
                "vol": 3.0
            })
            return 0.5
        elif stop_sig == "beep":
            events.append({
                "time": curr_time,
                "type": "signal",
                "text": f"[{label}] 비프음",
                "sound_file": os.path.join("effects", "beep.wav"),
                "duration": 0.25,
                "track": 1,
                "vol": 3.0
            })
            return 0.5
        elif stop_sig == "bell":
            events.append({
                "time": curr_time,
                "type": "bell",
                "text": f"[{label}] 경기장 벨소리",
                "sound_file": os.path.join("effects", "stage_bell.wav"),
                "duration": 0.8,
                "track": 1,
                "vol": 2.5
            })
            return 0.8
        else: # 기본값 갈려
            events.append({
                "time": curr_time,
                "type": "voice",
                "text": f"[{label}] 갈려~!",
                "duration": 1.2,
                "track": 2,
                "vol": 2.8
            })
            if duck_segments is not None:
                duck_segments.append((int(curr_time * 1000), int((curr_time + 1.3) * 1000)))
            return 1.3

    @classmethod
    def _generate_circuit_schedule(cls, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates functional circuit interval schedule (HIIT / Tabata / Combat intervals).
        Sequence:
          [1세트]: [설명] ➔ [카운트다운: 준비 3, 2, 1] ➔ [1세트 시작 휘슬(삐익)] ➔ [운동] ➔ [휴식]
          [2세트 이후]:
            - single 모드: 설명 없이 바로 [준비 3, 2, 1] ➔ [시작 휘슬(삐익)] ➔ [운동] ➔ [휴식]
            - cycle 모드: 해당 세트 콤보 호명 ➔ [준비 3, 2, 1] ➔ [시작 휘슬(삐익)] ➔ [운동] ➔ [휴식]
        """
        work_sec = float(params.get("work_sec", 20.0))    # 운동 시간
        rest_sec = float(params.get("rest_sec", 10.0))    # 휴식 시간
        total_sets = int(params.get("sets_count", 8))     # 총 세트 수
        theme_key = params.get("theme_key", "power_agility")
        lang = params.get("language_mode", "kr")
        circuit_mode_type = params.get("circuit_mode_type", "cycle") # "cycle" or "single"
        custom_routine_text = params.get("custom_routine_text", "").strip()
        intro_enabled = params.get("intro_enabled", True)
        countdown_enabled = params.get("countdown_enabled", True)
        cd_style = params.get("countdown_style", "en_321")

        # 1. 훈련 동작 결정 (커스텀 텍스트 우선 반영)
        theme_data = CIRCUIT_INTERVAL_THEMES.get(theme_key, CIRCUIT_INTERVAL_THEMES.get("power_agility", {}))
        exercises = []
        if custom_routine_text:
            parsed = cls.parse_custom_circuit_text(custom_routine_text)
            if parsed:
                exercises = parsed
        if not exercises:
            exercises = list(theme_data.get("exercises", []))

        # 단일 종목 집중 반복 모드일 경우: 첫 번째 콤보 1개로 고정
        if circuit_mode_type == "single" and exercises:
            exercises = [exercises[0]]

        lang_key = "mix" if lang == "mix_kids" else ("dual" if lang == "dual_step" else ("en" if lang in ("en", "en_advanced") else "kr"))
        user_theme_title = params.get("theme_title", "").strip()
        if user_theme_title:
            theme_title = clean_speech_text(user_theme_title)
        else:
            raw_title = theme_data.get(f"name_{lang_key}", theme_data.get("name_kr", "기능성 서킷 인터벌"))
            theme_title = clean_speech_text(raw_title)

        events = []
        duck_segments = []
        curr_time = 1.0

        # 2. 서킷 인터벌 전용 사전 안내 방송 (실제 도장 수업에 최적화된 명확하고 힘찬 지도자 구령 - 메타 언어 설명 완전 배제)
        if intro_enabled:
            intro_text = params.get("intro_text", "").strip()
            if not intro_text:
                if lang in ("en", "en_advanced"):
                    intro_text = "Circuit interval training starts now! Connect your jumps, kicks, and techniques with maximum intensity. Push your limits every set! Get ready!"
                else:
                    if "낙법" in theme_title:
                        intro_text = "지금부터 실전 서킷 인터벌 훈련을 시작합니다! 이번 훈련은 점프와 발차기, 그리고 낙법 콤보를 연결하여 실전 감각과 신체 협응력을 기르는 시간입니다. 지시하는 동작에 맞춰 신속하게 다음 동작으로 연결하며 전력으로 반복하세요! 모두 준비해 주세요!"
                    elif "순발력" in theme_title:
                        intro_text = "지금부터 실전 서킷 인터벌 훈련을 시작합니다! 이번 훈련은 폭발적인 버피와 점프, 연속 발차기를 통해 순발력과 민첩성을 극대화하는 시간입니다. 지시하는 구령에 맞춰 끝까지 빠른 템포로 집중하세요! 모두 준비해 주세요!"
                    elif "풋워크" in theme_title or "카운터" in theme_title:
                        intro_text = "지금부터 실전 서킷 인터벌 훈련을 시작합니다! 이번 훈련은 빠른 스텝 풋워크와 번개 같은 카운터 발차기 공방을 익히는 시간입니다. 상대의 빈틈을 노려 빠르고 정확하게 타격하세요! 모두 준비해 주세요!"
                    elif "근지구력" in theme_title or "파워" in theme_title:
                        intro_text = "지금부터 실전 서킷 인터벌 훈련을 시작합니다! 이번 훈련은 푸시업과 복근, 그리고 연타 발차기를 묶어 전신 파워와 근지구력을 기르는 시간입니다. 지친 순간에도 바른 자세를 유지하며 한계에 도전하세요! 모두 준비해 주세요!"
                    elif "전술" in theme_title or "겨루기" in theme_title:
                        intro_text = "지금부터 실전 서킷 인터벌 훈련을 시작합니다! 이번 훈련은 앞발 견제와 기습 회전차기 등 실전 겨루기 득점 콤보를 무한 반복하는 시간입니다. 실전 시합의 긴장감을 유지하며 전력으로 꽂아 넣으세요! 모두 준비해 주세요!"
                    else:
                        clean_theme = theme_title if theme_title else "기능성 서킷 인터벌"
                        intro_text = f"지금부터 기능성 서킷 인터벌 훈련을 시작합니다! 이번 테마는 {clean_theme}입니다. 지시하는 동작에 맞춰 신속하게 다음 동작을 연결하며 전력으로 반복하세요! 모두 준비해 주세요!"
            else:
                # 커스텀 텍스트에서도 언어 관련 메타 설명(한국어, 원어민, 바이링구얼 등) 완전 정제
                intro_text = re.sub(r'바이링구얼\s*', '', intro_text)
                intro_text = re.sub(r'한국어\s*설명과\s*영어\s*지시어에\s*맞춰', '지시하는 동작과 구령에 맞춰', intro_text)
                intro_text = re.sub(r'한국어\s*전술\s*설명과\s*원어민\s*구령에\s*맞춰', '지시하는 기술과 구령에 맞춰', intro_text)
                intro_text = re.sub(r'원어민\s*구령에\s*맞춰', '구령에 맞춰', intro_text)
                intro_text = re.sub(r'한국어\s*설명과\s*', '', intro_text)
                intro_text = re.sub(r'\s+', ' ', intro_text).strip()
                intro_text = clean_speech_text(intro_text)

            intro_dur = max(2.8, round(len(intro_text) * 0.18, 2))
            events.append({
                "time": curr_time,
                "type": "voice",
                "text": f"[인터벌 사전 안내] {intro_text}",
                "duration": intro_dur,
                "track": 2,
                "vol": 2.5
            })
            curr_time += intro_dur + 0.6

        cd_sound_file = os.path.join("effects", "countdown_beeps.wav") if cd_style == "beep" else os.path.join("effects", "countdown.wav")
        cd_dur = 6.5 if "ready" in cd_style else 4.3

        # 3. 세트 반복 루프
        for s in range(1, total_sets + 1):
            ex_idx = (s - 1) % len(exercises)
            cur_ex = exercises[ex_idx]
            if isinstance(cur_ex, dict):
                ex_name = cur_ex.get(lang_key, cur_ex.get("kr", "전력 수행!"))
            else:
                ex_name = str(cur_ex)

            # (A) 설명: 1세트는 필수, 2세트 이후는 cycle 모드일 때만 호명
            should_explain = (s == 1) or (circuit_mode_type == "cycle")
            if should_explain:
                # 이모지 및 불필요한 특수기호 완벽 제거
                clean_name = clean_speech_text(str(ex_name).rstrip(".!? ").strip())

                # 지도 팁(tip)은 지도자가 화면에서 참고하는 가이드이므로 음성에서는 배제하여 운동 템포 극대화
                if s == 1 and circuit_mode_type == "single":
                    call_text = f"[오늘의 집중 콤보] {clean_name}!"
                elif lang == "mix_kids":
                    call_text = f"[{s}세트] {clean_name}!"
                elif lang == "dual_step":
                    call_text = f"[{s}세트] {clean_name}!"
                elif lang in ("en", "en_advanced"):
                    call_text = f"[Set {s}] {clean_name}!"
                else:
                    call_text = f"[{s}세트] {clean_name}!"

                call_dur = max(1.5, round(len(call_text) * 0.16, 2))
                events.append({
                    "time": curr_time,
                    "type": "voice",
                    "text": call_text,
                    "duration": call_dur,
                    "track": 2,
                    "vol": 2.5
                })
                curr_time += call_dur + 0.4

            # (B) 카운트다운 (준비 3, 2, 1): 설명 바로 뒤에 배치
            if countdown_enabled:
                cd_label = f"[{s}세트 카운트다운] 준비 3, 2, 1"
                events.append({
                    "time": curr_time,
                    "type": "countdown",
                    "text": cd_label,
                    "cd_style": cd_style,
                    "sound_file": cd_sound_file,
                    "duration": cd_dur,
                    "track": 2,
                    "vol": 2.2
                })
                curr_time += cd_dur + 0.3

            # (C) 세트 시작 휘슬 (삐익~!)
            events.append({
                "time": curr_time,
                "type": "whistle",
                "text": f"[{s}세트 시작 휘슬] 삐익~!",
                "sound_file": os.path.join("effects", "whistle.wav"),
                "duration": 0.35,
                "track": 1,
                "vol": 3.0
            })
            curr_time += 0.4

            # (D) 운동 구간 (work_sec) & 종료 3초 전 알림 비프 3회
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

            curr_time += work_sec

            # (E) 세트 종료 및 휴식 구간
            is_final_set = (s == total_sets)
            stop_sig = params.get("stop_signal", "voice_kalyeo")
            delta = cls._add_stop_signal_event(
                events=events,
                duck_segments=duck_segments,
                curr_time=curr_time,
                stop_signal=stop_sig,
                label=f"{s}세트 종료" if not is_final_set else "최종 세트 종료"
            )

            if not is_final_set:
                rest_style = params.get("rest_style", "auto_mix")
                if rest_style == "none":
                    rest_ment = ""
                elif lang in ("mix_kids", "dual_step"):
                    # Catch your breath! 와 Take a break! 본토 실전 멘트 세트별 유연 순환 (물 마시기 배제, 지도자 정중 구령)
                    if rest_style == "catch_breath":
                        catch_list = [
                            "휴식! 호흡을 가다듬고 다음 세트를 준비하세요. - Catch your breath! Deep breath!",
                            "휴식! 숨을 깊게 들이쉬고 내쉬세요. - Breathe in, breathe out! Catch your breath!",
                            "휴식! 숨을 고르고 다음 동작에 집중해 주세요. - Catch your breath! Focus on the next set!",
                            "휴식! 호흡을 정돈하며 다리를 가볍게 털어주세요. - Catch your breath! Shake your legs!"
                        ]
                        rest_ment = catch_list[(s - 1) % len(catch_list)]
                    elif rest_style == "take_break":
                        break_list = [
                            "휴식! 잠시 숨 고르고 다리를 가볍게 털어주세요. - Take a break! Shake your legs!",
                            "휴식! 잠시 긴장을 풀고 다음 콤보를 준비하세요. - Take a break! Stay focused, get ready!",
                            "휴식! 잠시 휴식하며 호흡을 가다듬으세요. - Take a break! Great pace, keep it up!",
                            "휴식! 제자리에서 호흡을 정돈하고 다음을 준비하세요. - Take a break! Shake it off!"
                        ]
                        rest_ment = break_list[(s - 1) % len(break_list)]
                    elif rest_style == "kr_only":
                        kr_list = [
                            "휴식! 호흡을 가다듬고 다음 세트를 준비하세요.",
                            "휴식! 심호흡하며 다리를 가볍게 털어주세요.",
                            "휴식! 깊게 숨을 들이쉬고 다음 동작을 준비하세요.",
                            "휴식! 호흡을 정돈하고 다음 구령에 집중해 주세요."
                        ]
                        rest_ment = kr_list[(s - 1) % len(kr_list)]
                    else:  # auto_mix (기본값: Catch your breath!와 Take a break! 번갈아 순환)
                        mix_cues = [
                            "휴식! 호흡을 가다듬고 다음 세트를 준비하세요. - Catch your breath! Deep breath!",
                            "휴식! 잠시 숨 고르고 다리를 가볍게 털어주세요. - Take a break! Shake your legs!",
                            "휴식! 숨을 깊게 들이쉬고 내쉬세요. - Breathe in, breathe out! Catch your breath!",
                            "휴식! 잠시 긴장을 풀고 다음 콤보를 준비하세요. - Take a break! Stay focused, get ready!",
                            "휴식! 제자리에서 호흡을 가다듬고 다음 동작을 준비하세요. - Catch your breath! Deep breath!",
                            "휴식! 잠시 휴식하며 템포를 유지하세요. - Take a break! Shake your legs!"
                        ]
                        rest_ment = mix_cues[(s - 1) % len(mix_cues)]
                elif lang in ("en", "en_advanced"):
                    if rest_style == "catch_breath":
                        en_catch = [
                            "Catch your breath! Deep breath, get ready!",
                            "Breathe in, breathe out! Catch your breath!",
                            "Catch your breath! Stay loose and recover!",
                            "Catch your breath! Focus on the next set!"
                        ]
                        rest_ment = en_catch[(s - 1) % len(en_catch)]
                    elif rest_style == "take_break":
                        en_break = [
                            "Take a break! Shake out the legs and reset!",
                            "Take a break! Great tempo, stay focused!",
                            "Take a break! Shake it off, keep pushing!",
                            "Take a break! Great pace, keep it up!"
                        ]
                        rest_ment = en_break[(s - 1) % len(en_break)]
                    else:  # auto_mix
                        en_mix = [
                            "Catch your breath! Deep breath, recover for the next set!",
                            "Take a break! Shake out the legs and reset!",
                            "Breathe in, breathe out! Catch your breath!",
                            "Take a break! Keep your tempo, stay focused!",
                            "Catch your breath! Stay loose and recover!",
                            "Take a break! Great pace, keep pushing!"
                        ]
                        rest_ment = en_mix[(s - 1) % len(en_mix)]
                else:  # kr
                    kr_cues = [
                        "휴식! 호흡을 가다듬고 다음 세트를 준비하세요.",
                        "휴식! 심호흡하며 다리를 가볍게 털어주세요.",
                        "휴식! 깊게 숨을 들이쉬고 다음 동작을 준비하세요.",
                        "휴식! 호흡을 정돈하고 다음 구령에 집중해 주세요."
                    ]
                    rest_ment = kr_cues[(s - 1) % len(kr_cues)]

                if rest_ment:
                    r_dur = max(1.8, round(len(rest_ment) * 0.20, 2))
                    events.append({
                        "time": curr_time + delta + 0.3,
                        "type": "voice",
                        "text": f"[휴식] {rest_ment}",
                        "duration": r_dur,
                        "track": 2,
                        "vol": 2.2
                    })
                curr_time += rest_sec
            else:
                curr_time += delta + 0.5

        # 4. 전체 훈련 완료 멘트
        if lang == "mix_kids":
            final_outro = "서킷 인터벌 훈련 완료! 모두 끝까지 훌륭하게 해냈습니다! - Outstanding effort! Great job everyone!"
        elif lang == "dual_step":
            final_outro = "실전 인터벌 훈련 완료! 모두 정말 훌륭했습니다! - Awesome job everyone! Great workout today!"
        elif lang in ("en", "en_advanced"):
            final_outro = "Interval training complete! Outstanding effort team! Hydrate up, catch your breath, and wait for the next instruction!"
        else:
            final_outro = "고강도 기능성 서킷 인터벌 훈련 종료! 모두 수고하셨습니다. 물 한 잔 마시며 호흡을 정돈하고 다음 지시를 기다려 주세요."

        outro_dur = max(3.5, round(len(final_outro) * 0.22, 2))
        events.append({
            "time": curr_time + 0.5,
            "type": "voice",
            "text": f"[훈련 종료] {final_outro}",
            "duration": outro_dur,
            "track": 2,
            "vol": 2.5
        })
        curr_time += 0.5 + outro_dur + 1.5

        # 5. 오토덕킹 구간 (비프음/신호음은 0dB 유지, 오직 음성에만 덕킹)
        for ev in events:
            ev_type = ev.get("type", "")
            is_voice = (ev_type == "voice")
            if ev_type == "countdown" and ev.get("cd_style") != "beep":
                is_voice = True

            if is_voice:
                st_ms = int(ev["time"] * 1000)
                dur_ms = int(ev.get("duration", 0.5) * 1000)
                duck_segments.append((st_ms, st_ms + dur_ms + 200))

        return {
            "total_duration_sec": round(curr_time, 2),
            "events": events,
            "duck_segments": duck_segments
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
            "events": [...],
            "duck_segments": [(start_ms, end_ms), ...]
        }
        """
        # circuit 모드는 전용 인터벌 스케줄러로 즉시 분기 (스파링 멘트/공통 카운트다운 침범 방지)
        if mode == "circuit":
            return cls._generate_circuit_schedule(params)

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
                    f_cnt = params.get("fighters_count", 2)
                    match_label = "1대1" if f_cnt == 2 else ("2대1" if f_cnt == 3 else f"{f_cnt-1}대1")
                    cue_raw = params.get("cue_text", "미트 발차기")
                    cues_list_tmp = [c.strip() for line in str(cue_raw).splitlines() for c in line.split(",") if c.strip()]
                    if cues_list_tmp:
                        cue_summary = cues_list_tmp[0]
                        if len(cues_list_tmp) > 1:
                            cue_summary += f" 외 {len(cues_list_tmp)-1}개"
                        intro_text = f"지금부터 {match_label} 릴레이 미트 발차기 훈련을 시작합니다. 지시하는 세트별 기술을 듣고 신호음에 맞춰 정확히 타격하세요. 모두 준비해 주세요!"
                    else:
                        intro_text = f"지금부터 {match_label} 릴레이 미트 발차기 훈련을 시작합니다. 지시하는 기술을 듣고 신호음에 맞춰 정확히 타격하세요. 모두 준비해 주세요!"
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
                        clean_kdesc = kick_desc.rstrip(".!? ").strip()
                        import re
                        if re.search(r'(됩니다|합니다|입니다|습니다|시오|세요|된다|한다|이다|있습니다|없습니다)$', clean_kdesc):
                            intro_text = (
                                f"지금부터 스텝 콤비네이션 연타 스파링 훈련을 시작합니다. "
                                f"이번 집중 훈련 공격 기술은 {clean_kdesc}. "
                                f"지시하는 스텝을 유지하다가 신호음이 울리면 전력으로 연타하고, "
                                f"'{stop_label}' 신호에 맞춰 스텝으로 복귀하세요. 준비해 주세요!"
                            )
                        else:
                            intro_text = (
                                f"지금부터 스텝 콤비네이션 연타 스파링 훈련을 시작합니다. "
                                f"이번 집중 훈련 공격 기술은 {clean_kdesc}입니다. "
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
                    round_type = params.get("round_type", "real")
                    if round_type == "shadow":
                        intro_text = "지금부터 섀도우 스파링 훈련을 시작합니다. 가상의 상대를 상상하며 실전처럼 스텝을 뛰고 공방 기술을 구사하세요. 준비해 주세요!"
                    elif round_type == "promise":
                        promise_note = params.get("promise_detail", "").strip()
                        if promise_note:
                            clean_note = promise_note.rstrip(".!? ").strip()
                            import re
                            if re.search(r'(됩니다|합니다|입니다|습니다|시오|세요|된다|한다|이다|있습니다|없습니다)$', clean_note):
                                intro_text = f"지금부터 약속 스파링 훈련을 시작합니다. 이번 약속 기술은 {clean_note}. 상호 원칙을 지키며 침착하게 공방을 이어가세요. 양 선수 준비해 주세요!"
                            else:
                                intro_text = f"지금부터 약속 스파링 훈련을 시작합니다. 이번 약속 기술은 {clean_note}입니다. 상호 원칙을 지키며 침착하게 공방을 이어가세요. 양 선수 준비해 주세요!"
                        else:
                            intro_text = "지금부터 약속 스파링 훈련을 시작합니다. 약속된 기술과 공방 원칙을 준수하며 침착하게 공방을 이어가세요. 양 선수 준비해 주세요!"
                    elif round_type == "attack_defense":
                        atk_def_mode = params.get("atk_def_mode", "alternate")
                        if atk_def_mode == "a_attack_only":
                            intro_text = "지금부터 A선수 공격, B선수 방어 공수 특화 스파링 훈련을 시작합니다."
                        elif atk_def_mode == "b_attack_only":
                            intro_text = "지금부터 B선수 공격, A선수 방어 공수 특화 스파링 훈련을 시작합니다."
                        else:
                            intro_text = "지금부터 A선수와 B선수 공수 교대 스파링 훈련을 시작합니다."
                    else:
                        intro_text = "지금부터 정규 실전 스파링 라운드 훈련을 시작합니다. 양 선수 마주보고 차렷, 경례! 준비해 주세요!"
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

            # ⭐ [사용자 요청] 공수 스파링(attack_defense) 시퀀스: 설명 ➔ 주의사항 ➔ 모두 준비 되었나요?
            if mode == "rounds" and params.get("round_type") == "attack_defense":
                caution_text = params.get("caution_text", "").strip()
                if not caution_text:
                    caution_text = "스파링 시 안전에 유의하세요. 방어 선수는 가드를 바짝 올리고 무리한 반격을 삼가며, 공격 선수는 과도한 흥분을 자제하고 정확한 타격에 집중하세요. 상호 부상에 절대 주의합니다!"
                
                caut_dur = max(3.0, round(len(caution_text) * 0.22, 2))
                events.append({
                    "time": curr_time,
                    "type": "voice",
                    "text": f"[주의사항] {caution_text}",
                    "duration": caut_dur,
                    "track": 2,
                    "vol": 2.5
                })
                duck_segments.append((int(curr_time * 1000), int((curr_time + caut_dur + 0.5) * 1000)))
                curr_time += caut_dur + 0.8

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
                curr_time += ready_dur + 1.5

            # ⭐ [사용자 요청] 설명 후 받기자 미트 착용 및 위치 선정 대기 시간 (n초) + "모두 준비가 되었나요?" 확인 (릴레이 등)
            prep_wait_sec = float(params.get("prep_wait_sec", 0.0))
            if prep_wait_sec > 0 and mode != "rounds":
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
                curr_time += ready_dur + 2.0

        # 카운트다운 (Three, Two, One / 3-2-1)
        # ⭐ [사용자 요청] 정규 스파링 라운드(rounds)는 카운트다운 제외, 릴레이(relay)는 1세트 종목 설명 뒤에 배치
        if countdown_enabled and mode not in ("relay", "rounds"):
            cd_text = "[카운트다운] Three, Two, One"
            if cd_style == "ko_321":
                cd_text = "[카운트다운] 셋, 둘, 하나"
            elif cd_style == "ko_ready":
                cd_text = "[카운트다운] 준비되었나요? 준비! 셋, 둘, 하나"
            elif cd_style == "en_ready":
                cd_text = "[카운트다운] Are you ready? Ready! Three, Two, One"
            elif cd_style == "beep":
                cd_text = "[카운트다운] 전자 비프음 3회 (띡-띡-띡)"

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
            curr_time += cd_dur + 1.5

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

            fighter_names = ["A선수", "B선수", "C선수", "D선수"]

            for c in range(1, cycles + 1):
                # 세트별 훈련 종목 결정: 동일 세트 내에서는 A, B, C 모든 선수가 같은 발차기 훈련!
                # 등록된 기술이 여러 개일 경우 세트가 바뀔 때마다 순차적으로 다음 기술로 전환
                current_cue = cues_list[(c - 1) % len(cues_list)]

                # 1. 세트 시작 안내 (예: "1세트! 앞차기!", "2세트! 돌려차기!")
                set_msg = f"{c}세트! {current_cue}!"
                set_dur = max(2.0, round(len(set_msg) * 0.22, 2))
                events.append({
                    "time": curr_time,
                    "type": "voice",
                    "text": f"[{c}세트 안내] {set_msg}",
                    "duration": set_dur,
                    "track": 2,
                    "vol": 2.5
                })
                duck_segments.append((int(curr_time * 1000), int((curr_time + set_dur) * 1000)))
                curr_time += set_dur + 0.8  # 세트 안내 후 0.8초 호흡 정렬

                for f in range(1, fighters_count + 1):
                    fighter_name = fighter_names[f - 1] if f <= len(fighter_names) else f"{f}번째 선수"

                    # 2. 선수 준비 멘트 (예: "A선수 준비!", "B선수 준비!")
                    call_text = f"{fighter_name} 준비!"
                    call_dur = max(1.5, round(len(call_text) * 0.22, 2))
                    events.append({
                        "time": curr_time,
                        "type": "voice",
                        "text": f"[{c}세트-{fighter_name}] {call_text}",
                        "duration": call_dur,
                        "track": 2,
                        "vol": 2.5
                    })
                    duck_segments.append((int(curr_time * 1000), int((curr_time + call_dur) * 1000)))
                    curr_time += call_dur + 0.4

                    # ⭐ [사용자 승인] 1세트 첫 번째 선수(c == 1, f == 1) 준비 멘트 직후에 카운트다운 배치!
                    # 순서: [사전 안내] ➔ [1세트 설명: 앞차기! A선수 준비!] ➔ [카운트다운: 셋, 둘, 하나] ➔ [삑~익!]
                    if c == 1 and f == 1 and countdown_enabled:
                        cd_text = "[카운트다운] Three, Two, One"
                        if cd_style == "ko_321":
                            cd_text = "[카운트다운] 셋, 둘, 하나"
                        elif cd_style == "ko_ready":
                            cd_text = "[카운트다운] 준비되었나요? 준비! 셋, 둘, 하나"
                        elif cd_style == "en_ready":
                            cd_text = "[카운트다운] Are you ready? Ready! Three, Two, One"
                        elif cd_style == "beep":
                            cd_text = "[카운트다운] 전자 비프음 3회 (띡-띡-띡)"

                        cd_dur = 6.5 if "ready" in cd_style else 4.3
                        events.append({
                            "time": curr_time,
                            "type": "countdown",
                            "text": cd_text,
                            "cd_style": cd_style,
                            "sound_file": os.path.join("effects", "countdown_beeps.wav") if cd_style == "beep" else os.path.join("effects", "countdown.wav"),
                            "duration": cd_dur,
                            "track": 2,
                            "vol": 2.2
                        })
                        duck_segments.append((int(curr_time * 1000), int((curr_time + cd_dur) * 1000)))
                        curr_time += cd_dur + 0.6
                    else:
                        curr_time += 0.5  # 카운트다운 없는 경우(교대 선수 또는 2세트 이후) 0.5초 호흡 긴장 딜레이

                    # 3. 타격 시작 신호음 (삑~익!)
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

                    # 4. 타격 시간 진행 및 종료 3초 전 마무리 비프음 (3-2-1)
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

                    # 5. 타격 종료 신호 (갈려 / 중지 / 그만 등)
                    stop_sig = params.get("stop_signal", "voice_kalyeo")
                    delta = cls._add_stop_signal_event(
                        events=events,
                        duck_segments=duck_segments,
                        curr_time=curr_time,
                        stop_signal=stop_sig,
                        label="타격 종료"
                    )
                    curr_time += delta + 0.4  # 종료 신호 후 0.4초 호흡 대기

                    # 6. 선수 교대 안내
                    is_last_fighter_in_set = (f == fighters_count)
                    is_last_overall = (c == cycles and is_last_fighter_in_set)

                    if not is_last_overall:
                        if not is_last_fighter_in_set:
                            # 세트 내 다음 선수로 교대
                            change_msg = "선수 교대!"
                            chg_dur = 1.3
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
                        else:
                            # 세트의 마지막 선수 완료 후 다음 세트로 넘어가는 휴식/교대 대기
                            curr_time += change_sec

            # 7. 모든 세트 종료 시 정중하고 자연스러운 마무리 멘트
            user_outro = params.get("outro_text", "").strip()
            if user_outro and "물 한잔" not in user_outro:
                outro_text = user_outro
            else:
                outro_text = "릴레이 발차기 훈련 종료! 모두 수고하셨습니다. 장비 정리 후 제자리 앉아서 대기하세요."
            outro_dur = max(2.5, round(len(outro_text) * 0.22, 2))
            events.append({
                "time": curr_time + 0.5,
                "type": "voice",
                "text": f"[훈련 종료] {outro_text}",
                "duration": outro_dur,
                "track": 2,
                "vol": 2.5
            })
            duck_segments.append((int((curr_time + 0.5) * 1000), int((curr_time + 0.5 + outro_dur + 0.5) * 1000)))
            total_duration_sec = curr_time + 0.5 + outro_dur + 5.5

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

            # 훈련 종료 신호 (갈려 / 중지 / 그만 / 차임벨 / 휘슬 / 비프)
            stop_sig = params.get("stop_signal", "voice_kalyeo")
            delta = cls._add_stop_signal_event(
                events=events,
                duck_segments=duck_segments,
                curr_time=curr_time + 0.3,
                stop_signal=stop_sig,
                label="훈련 종료"
            )
            curr_time += 0.3 + delta + 0.5

            user_outro = params.get("outro_text", "").strip()
            if user_outro and "물 한잔" not in user_outro:
                outro_text = user_outro
            else:
                outro_text = "반응 훈련 종료! 모두 수고하셨습니다. 가볍게 몸을 풀고 제자리 앉아서 대기하세요."
            outro_dur = max(2.5, round(len(outro_text) * 0.22, 2))
            events.append({
                "time": curr_time,
                "type": "voice",
                "text": f"[훈련 종료] {outro_text}",
                "duration": outro_dur,
                "track": 2,
                "vol": 2.5
            })
            duck_segments.append((int(curr_time * 1000), int((curr_time + outro_dur + 0.5) * 1000)))
            total_duration_sec = curr_time + outro_dur + 5.5  # 종료 후 5초 페이드아웃 넉넉한 딜레이 보장

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

                # 1. 스텝 지시 음성 (each_set: 매 세트 기술명 함께 호명, first_set_only: 1세트만 기술 호명, intro_only: 스텝만 호명)
                kick_name = kick_types[(s - 1) % len(kick_types)] if kick_types else ""
                clean_kick = str(kick_name).rstrip(".!? ").strip()

                if kick_announce_mode == "first_set_only" and clean_kick:
                    if s == 1:
                        cue_text = f"[1세트] {step_name}! 집중 기술: {clean_kick}!"
                    else:
                        cue_text = f"[{s}세트] {step_name}!"
                elif kick_announce_mode == "intro_only":
                    cue_text = f"[{s}세트] {step_name}!"
                else:  # each_set 기본값 (매 세트 스텝 + 기술 함께 호명)
                    if clean_kick:
                        cue_text = f"[{s}세트] {step_name}! {clean_kick}!"
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
                delta = cls._add_stop_signal_event(
                    events=events,
                    duck_segments=duck_segments,
                    curr_time=curr_time,
                    stop_signal=stop_signal,
                    label="연타 종료"
                )
                curr_time += delta

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
            user_outro = params.get("outro_text", "").strip()
            if user_outro and "물 한잔" not in user_outro:
                outro_text = user_outro
            else:
                outro_text = "스텝 연타 훈련 완료! 모두 수고하셨습니다. 가볍게 전신 스트레칭하며 다음 지시를 기다리세요."
            outro_dur = max(2.5, round(len(outro_text) * 0.22, 2))
            events.append({
                "time": curr_time + 1.5,
                "type": "voice",
                "text": f"[훈련 종료] {outro_text}",
                "duration": outro_dur,
                "track": 2,
                "vol": 2.5
            })
            duck_segments.append((int((curr_time + 1.5) * 1000), int((curr_time + 1.5 + outro_dur + 0.5) * 1000)))
            total_duration_sec = curr_time + 1.5 + outro_dur + 5.5  # 종료 후 5초 페이드아웃 넉넉한 딜레이 보장

        # ── Mode 4: 정규 스파링 라운드 시뮬레이터 (실전 / 섀도우 / 약속 / A공격·B방어) ──
        elif mode == "rounds":
            round_sec = params.get("round_sec", 90.0)      # 1분 30초 (90초)
            rest_sec = params.get("rest_sec", 30.0)        # 휴식 30초
            total_rounds = params.get("total_rounds", 3)   # 3라운드
            round_type = params.get("round_type", "real")  # real / shadow / promise / attack_defense
            atk_def_mode = params.get("atk_def_mode", "alternate")
            promise_detail = params.get("promise_detail", "").strip()

            for r in range(1, total_rounds + 1):
                # ⭐ [사용자 요청]
                # 설명은 훈련 시작 전 [사전 안내]에서 한 번만 하고, 라운드마다 설명 중복 완전 제거!
                # 모든 라운드는 간결하게 구령("제 n라운드! 준비!") ➔ 신호음(삐익!) 순서로만 경기 시작
                round_call = f"제 {r}라운드! 준비!"

                # 1. 먼저 "제 n라운드 ... 준비!" 음성 송출
                round_call_dur = max(1.5, round(len(round_call) * 0.22, 2))
                events.append({
                    "time": curr_time,
                    "type": "voice",
                    "text": round_call,
                    "duration": round_call_dur,
                    "track": 2,
                    "vol": 2.5
                })
                duck_segments.append((int(curr_time * 1000), int((curr_time + round_call_dur + 0.4) * 1000)))
                curr_time += round_call_dur + 0.4  # "준비!" 발성 후 0.4초 긴장 딜레이

                # 2. 그 다음 시작 신호음 (호각/휘슬 - 삐익~!) 으로 경기 시작!
                events.append({
                    "time": curr_time,
                    "type": "whistle",
                    "text": f"[{r}라운드 시작 신호음] 경기 시작 휘슬!",
                    "sound_file": os.path.join("effects", "whistle.wav"),
                    "duration": 0.35,
                    "track": 1,
                    "vol": 3.0
                })
                duck_segments.append((int(curr_time * 1000), int((curr_time + 0.5) * 1000)))
                curr_time += 0.4  # 신호음 직후부터 실경기 시간 시작

                # 라운드 종료 10초 전 경고음
                warn_time = curr_time + round_sec - 10.0
                if round_sec >= 20:
                    if round_type == "shadow":
                        warn_text = "[종료 10초 전] 마지막 10초! 전력 스퍼트!"
                    elif round_type == "attack_defense":
                        warn_text = "[종료 10초 전] 마지막 10초! 공격 몰아붙이세요!"
                    elif round_type == "promise":
                        warn_text = "[종료 10초 전] 마지막 10초! 침착하게 마무리!"
                    else:
                        warn_text = "[종료 10초 전] 마지막 10초! 공격!"

                    events.append({
                        "time": warn_time,
                        "type": "voice",
                        "text": warn_text,
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

                # 라운드 종료 신호 (일반 라운드는 stop_signal, 최종 라운드는 final_stop_signal)
                if r == total_rounds:
                    stop_sig = params.get("final_stop_signal") or "voice_end"
                    stop_lbl = "최종 라운드 종료"
                else:
                    stop_sig = params.get("stop_signal", "voice_kalyeo")
                    stop_lbl = f"{r}라운드 종료"

                delta = cls._add_stop_signal_event(
                    events=events,
                    duck_segments=duck_segments,
                    curr_time=curr_time,
                    stop_signal=stop_sig,
                    label=stop_lbl
                )
                curr_time += delta + 0.4

                if r < total_rounds:
                    # 휴식 멘트
                    if round_type == "attack_defense" and atk_def_mode == "alternate":
                        next_atk = "B선수" if (r % 2 == 1) else "A선수"
                        next_def = "A선수" if (r % 2 == 1) else "B선수"
                        rest_msg = f"휴식 {int(rest_sec)}초입니다. 다음 라운드는 {next_atk} 공격, {next_def} 방어 차례입니다! 호흡 정돈하세요."
                    elif round_type == "shadow":
                        rest_msg = f"휴식 {int(rest_sec)}초입니다. 호흡을 가다듬고 다리 가볍게 털어주세요."
                    elif round_type == "promise":
                        rest_msg = f"휴식 {int(rest_sec)}초입니다. 호흡 정돈하고 다음 약속 공방 준비하세요."
                    else:
                        rest_msg = f"휴식 {int(rest_sec)}초입니다. 호흡 가다듬고 가볍게 스트레칭하며 다음 라운드를 준비하세요."

                    rest_dur = max(2.5, round(len(rest_msg) * 0.22, 2))
                    events.append({
                        "time": curr_time,
                        "type": "voice",
                        "text": rest_msg,
                        "duration": rest_dur,
                        "track": 2,
                        "vol": 2.0
                    })
                    duck_segments.append((int(curr_time * 1000), int((curr_time + rest_dur + 0.5) * 1000)))
                    curr_time += rest_sec
                else:
                    # 최종 경기 종료 멘트 (물 한잔 반복 문제 해결!)
                    user_outro = params.get("outro_text", "").strip()
                    if user_outro and "물 한잔" not in user_outro:
                        final_msg = f"[훈련 종료] 경기 종료! {user_outro}"
                    else:
                        if round_type == "shadow":
                            final_msg = "[훈련 종료] 섀도우 스파링 종료! 모두 수고하셨습니다. 가볍게 몸을 풀고 전신 스트레칭을 실시하세요."
                        elif round_type == "promise":
                            final_msg = "[훈련 종료] 약속 스파링 종료! 양 선수 마주보고 차렷, 경례! 수고하셨습니다. 장비 정리 후 제자리 앉아서 대기하세요."
                        elif round_type == "attack_defense":
                            final_msg = "[훈련 종료] 공수 스파링 종료! 양 선수 마주보고 차렷, 경례! 수고하셨습니다. 다리 가볍게 털고 심호흡하며 스트레칭하세요."
                        else:
                            final_msg = "[훈련 종료] 경기 종료! 양 선수 마주보고 차렷, 경례! 모두 수고하셨습니다. 제자리에 바르게 앉아 호흡을 정돈하고 대기하세요."

                    final_dur = max(3.0, round(len(final_msg) * 0.22, 2))
                    events.append({
                        "time": curr_time + 0.5,
                        "type": "voice",
                        "text": final_msg,
                        "duration": final_dur,
                        "track": 2,
                        "vol": 2.5
                    })
                    duck_segments.append((int((curr_time + 0.5) * 1000), int((curr_time + final_dur + 0.5) * 1000)))
                    curr_time += final_dur + 1.0

            total_duration_sec = curr_time + 5.5  # 종료 멘트 후 5.5초 여유 (마지막 5초 동안 0까지 천천히 페이드아웃)

        # ── Mode 5: 도장 고강도 기능성 서킷 인터벌 (HIIT & Tabata) ──
        elif mode == "circuit":
            return cls._generate_circuit_schedule(params)
        else:
            total_duration_sec = 60.0

        return {
            "total_duration_sec": total_duration_sec,
            "events": events,
            "duck_segments": duck_segments
        }
