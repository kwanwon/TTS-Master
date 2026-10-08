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


# ── 도장 고강도 기능성 서킷 인터벌 4대 복합 콤보 테마 (체력 + 발차기 + 낙법/점프 무한 반복 루프) ──
CIRCUIT_INTERVAL_THEMES = {
    "power_agility": {
        "name_kr": "🥋 [대련 실전 & 낙법 협응 콤보] 점프·발차기·회전낙법 무한 루프",
        "name_mix": "🥋 대련 실전 & 낙법 협응 콤보 (점프 & 킥 & 롤링 낙법)",
        "name_dual": "🥋 대련 실전 & 낙법 협응 (Combat Kicks & Rolling Fall Combo)",
        "name_en": "🥋 Dojo Combat & Breakfall Flow Interval",
        "desc": "15~20초 동안 [체력 점프 ➔ 실전 발차기 ➔ 회전낙법/점프턴] 콤보를 전력으로 무한 반복하고 휴식하는 실전 대련 인터벌",
        "exercises": [
            {
                "kr": "쪼그려 점프 3회 후 나래차기, 전방 회전낙법 기립! 쉼 없이 반복!",
                "mix": "스쿼트 점프 3 타임스(Times), 나래 더블 킥, 롤링 낙법 기립! 무한 리핏(Repeat)!",
                "dual": "쪼그려 점프 3회, 나래차기, 회전낙법! - 3 squat jumps, double kick, rolling breakfall, repeat!",
                "en": "3 squat jumps, fast double kicks, rolling breakfall and spring up! Non-stop loop!",
                "tip": "쪼그려 점프 3회 ➔ 양발 나래차기 ➔ 전방 회전낙법 후 즉시 스프링처럼 기립하여 15~20초 동안 처음부터 무한 반복합니다."
            },
            {
                "kr": "전력 버피 1회 후 전진 몸통 2연타, 180도 점프 뒤돌아 착지! 쉼 없이 반복!",
                "mix": "버피 1 타임(Time), 바디 2연타 킥, 180도 점프 턴 착지! 무한 리핏(Repeat)!",
                "dual": "버피 1회, 전진 몸통 2연타, 180도 점프 턴! - 1 burpee, 2 body kicks, 180 jump turn, repeat!",
                "en": "1 burpee, 2 continuous body kicks, 180-degree jump turn! Non-stop continuous loop!",
                "tip": "전력 버피 1회 ➔ 전진 몸통 2연타 ➔ 공중에서 180도 점프 뒤돌아 착지 후 즉시 처음부터 무한 반복합니다."
            },
            {
                "kr": "무릎 당겨 높이 점프 2회 후 앞발 컷트 뒷발 상단, 측방 낙법 기립! 쉼 없이 반복!",
                "mix": "하이니 점프 2 타임스, 앞발 컷트 하이 킥, 사이드 낙법 기립! 무한 리핏!",
                "dual": "무릎당겨 점프 2회, 컷트 후 상단킥, 측방낙법! - 2 high knee jumps, cut & high kick, side fall, repeat!",
                "en": "2 high knee jumps, front cut to high kick, side breakfall! Keep repeating!",
                "tip": "무릎을 가슴까지 높이 2회 점프 ➔ 앞발 컷트 견제 후 뒷발 머리 상단 돌려차기 ➔ 측방 회전낙법 후 기립을 반복합니다."
            },
            {
                "kr": "손바닥 푸시업 2회 후 백스텝 카운터 뒤차기, 좌우 스케이터 점프! 쉼 없이 반복!",
                "mix": "푸시업 2 타임스, 백스텝 카운터 뒤차기, 스케이터 점프! 무한 리핏!",
                "dual": "푸시업 2회, 카운터 뒤차기, 스케이터 점프! - 2 pushups, counter back kick, skater jumps, repeat!",
                "en": "2 pushups, explosive counter back kick, lateral skater jumps! Non-stop loop!",
                "tip": "바닥 푸시업 2회 ➔ 재빨리 기립하여 백스텝 카운터 뒤차기 ➔ 좌우 스케이터 점프 2회 후 처음부터 반복합니다."
            }
        ]
    },
    "agility_power_combo": {
        "name_kr": "⚡ [순발력 & 민첩성 폭발 콤보] 버피·점프턴·나래차기 순환 루프",
        "name_mix": "⚡ 순발력 & 민첩성 폭발 콤보 (버피 & 점프 턴 & 나래 킥)",
        "name_dual": "⚡ 순발력 & 민첩성 콤보 (Agility, Burpee & Fast Kick Flow)",
        "name_en": "⚡ Agility & Explosive Kick Flow",
        "desc": "15~20초 동안 [전신 순발력 ➔ 폭풍 스피드 발차기 ➔ 공중 방향전환]을 결합한 고강도 협응 인터벌",
        "exercises": [
            {
                "kr": "전력 버피 1회 후 공중 나래차기 연타, 무릎 당겨 점프 1회! 쉼 없이 반복!",
                "mix": "버피 1회 후 나래 더블 킥, 하이니 점프 1회! 무한 리핏(Repeat)!",
                "dual": "버피 1회, 나래차기 연타, 무릎당겨 점프! - 1 burpee, double kick, high knee jump, repeat!",
                "en": "1 burpee, rapid double kicks, 1 high knee tuck jump! Non-stop loop!",
                "tip": "버피 1회 ➔ 공중 나래차기 2연타 ➔ 무릎 당겨 가슴 터치 점프 1회 후 쉬지 않고 무한 반복합니다."
            },
            {
                "kr": "쪼그려 점프 3회 후 빠른발 상단 끊어차기 2회, 180도 점프 뒤돌기! 쉼 없이 반복!",
                "mix": "스쿼트 점프 3회, 패스트 하이 킥 2회, 180도 점프 턴! 무한 리핏!",
                "dual": "쪼그려 점프 3회, 상단 끊어차기, 180도 점프 턴! - 3 squat jumps, high snap kicks, 180 jump turn, repeat!",
                "en": "3 squat jumps, rapid high snap kicks, 180-degree jump turn! Non-stop loop!",
                "tip": "깊게 쪼그려 점프 3회 ➔ 앞발 빠른 상단 끊어차기 2회 ➔ 공중 180도 점프 뒤돌아 착지를 반복합니다."
            },
            {
                "kr": "제자리 초고속 발구르기 3초 후 전진 원투 3연타, 전방 회전낙법 기립! 쉼 없이 반복!",
                "mix": "패스트 피트 3초 후 전진 3연타 킥, 롤링 낙법 기립! 무한 리핏!",
                "dual": "초고속 발구르기 후 전진 3연타, 회전낙법! - Fast feet 3s, 3 continuous kicks, rolling breakfall, repeat!",
                "en": "3 seconds fast feet sprint, 3 push kicks, rolling breakfall! Non-stop continuous loop!",
                "tip": "발끝으로 지면을 초고속으로 3초 구르고 ➔ 전진하며 3연타 ➔ 전방 회전낙법으로 굴러 일어나 반복합니다."
            },
            {
                "kr": "마운틴 클라이머 4회 후 기립 앞차기 양발 연속 4회, 점프 대련자세! 쉼 없이 반복!",
                "mix": "마운틴 클라이머 4회, 프론트 킥 4회, 점프 파이팅 스탠스! 무한 리핏!",
                "dual": "마운틴 클라이머 4회, 앞차기 4회, 점프 대련자세! - 4 mountain climbers, 4 front kicks, ready stance, repeat!",
                "en": "4 mountain climbers, 4 alternating front kicks, jump to fighting stance! Non-stop loop!",
                "tip": "엎드려 마운틴 클라이머 4회 ➔ 용수철처럼 일어나 얼굴 앞차기 좌우 4회 ➔ 점프 착지를 반복합니다."
            }
        ]
    },
    "footwork_reaction_combo": {
        "name_kr": "🏃‍♂️ [스파링 풋워크 & 카운터 콤보] 스텝·카운터킥·회전낙법 루프",
        "name_mix": "🏃‍♂️ 스파링 풋워크 & 반사신경 콤보 (스텝 & 카운터 킥 & 롤링 낙법)",
        "name_dual": "🏃‍♂️ 스파링 풋워크 & 카운터 콤보 (Footwork, Counter Kicks & Breakfall)",
        "name_en": "🏃‍♂️ Sparring Footwork & Reaction Flow",
        "desc": "15~20초 동안 [대련 스텝 풋워크 ➔ 상대 격파 발차기 ➔ 낙법 회피 기립]을 무한 반복하는 실전 스파링 서킷",
        "exercises": [
            {
                "kr": "사이드 스텝 좌우 터치 후 백스텝 카운터 뒤차기, 전방 회전낙법 기립! 쉼 없이 반복!",
                "mix": "사이드 스텝 터치, 백스텝 카운터 뒤차기, 롤링 낙법 기립! 무한 리핏!",
                "dual": "사이드 스텝 후 카운터 뒤차기, 회전낙법! - Side step touch, counter back kick, rolling breakfall, repeat!",
                "en": "Side step touch ground, back step counter back kick, rolling breakfall! Non-stop loop!",
                "tip": "사이드 스텝 좌우 터치 ➔ 한 걸음 빠지며 몸통 꽂는 카운터 뒤차기 ➔ 전방 회전낙법 후 기립을 반복합니다."
            },
            {
                "kr": "앞뒤 풋워크 3단 전진 후 앞발 컷트 뒷발 상단 돌려차기, 180도 점프 턴! 쉼 없이 반복!",
                "mix": "앞뒤 스텝 전진, 앞발 컷트 뒷발 하이 킥, 180도 점프 턴! 무한 리핏!",
                "dual": "앞뒤 스텝, 컷트 후 상단 돌려차기, 180도 점프 턴! - In-and-out footwork, cut & high kick, 180 jump turn, repeat!",
                "en": "3 in-and-out steps, front foot cut to high kick, 180-degree jump turn! Non-stop loop!",
                "tip": "앞뒤 리듬 스텝 3회 ➔ 앞발 컷트로 상대 진입 저지 후 뒷발 상단 강타 ➔ 180도 점프 턴을 반복합니다."
            },
            {
                "kr": "양발 스위치 2회 후 전격 전진 몸통 3연타, 측방 낙법 후 스프링 기립! 쉼 없이 반복!",
                "mix": "스위치 스텝 2회, 전진 바디 3연타 킥, 사이드 낙법 기립! 무한 리핏!",
                "dual": "양발 스위치 2회, 전진 몸통 3연타, 측방 낙법! - 2 switch steps, 3 forward body kicks, side fall, repeat!",
                "en": "2 stance switches, 3 pushing body kicks, side breakfall! Non-stop continuous loop!",
                "tip": "대련 자세에서 양발 스위치 2회 ➔ 밀고 들어가며 몸통 3연타 ➔ 측방 회전낙법으로 굴러 일어나 반복합니다."
            },
            {
                "kr": "지그재그 회피 스텝 후 기습 나래차기, 쪼그려 점프 2회 착지! 쉼 없이 반복!",
                "mix": "지그재그 스텝, 나래 더블 킥, 스쿼트 점프 2회! 무한 리핏!",
                "dual": "지그재그 회피 후 나래차기, 쪼그려 점프 2회! - Zigzag evasion, double kick, 2 squat jumps, repeat!",
                "en": "Zigzag evasion footwork, surprise double kick, 2 squat jumps! Non-stop loop!",
                "tip": "공격선을 비켜서는 지그재그 스텝 ➔ 공중 나래차기 연타 ➔ 쪼그려 점프 2회 착지 후 다시 반복합니다."
            }
        ]
    },
    "strength_endurance_combo": {
        "name_kr": "💪 [근지구력 & 심폐 협응 파워 콤보] 푸시업·복근·연타킥 전신 서킷",
        "name_mix": "💪 근지구력 & 심폐 파워 콤보 (푸시업 & V업 복근 & 연속 킥)",
        "name_dual": "💪 근지구력 & 심폐 파워 (Strength, Core & Continuous Kick Combo)",
        "name_en": "💪 Endurance Strength & Striking Circuit",
        "desc": "15~20초 동안 [도장 특화 체력 단련 ➔ 전력 타격 ➔ 심폐 파워]를 한 세트로 묶어 무한 반복하는 서킷",
        "exercises": [
            {
                "kr": "손바닥 푸시업 2회 후 스프링 기립, 전진 몸통 3연타, 무릎 당겨 점프! 쉼 없이 반복!",
                "mix": "푸시업 2회, 스프링 기립, 전진 바디 3연타, 하이니 점프! 무한 리핏!",
                "dual": "푸시업 2회, 전진 몸통 3연타, 무릎당겨 점프! - 2 pushups, 3 body kicks, 1 high knee jump, repeat!",
                "en": "2 standard pushups, spring up, 3 body kicks, 1 high knee tuck jump! Non-stop loop!",
                "tip": "가슴 바닥 푸시업 2회 ➔ 스프링처럼 박차고 일어나 몸통 3연타 ➔ 무릎 당겨 점프 1회 후 반복합니다."
            },
            {
                "kr": "마운틴 클라이머 6회 후 기립, 양발 교차 나래차기, 180도 점프 뒤돌기! 쉼 없이 반복!",
                "mix": "마운틴 클라이머 6회, 나래 더블 킥, 180도 점프 턴! 무한 리핏!",
                "dual": "마운틴 클라이머 6회, 나래차기, 180도 점프 턴! - 6 mountain climbers, double kick, 180 jump turn, repeat!",
                "en": "6 mountain climbers, alternating double kicks, 180 jump turn! Non-stop loop!",
                "tip": "엎드려 무릎 달리기 6회 ➔ 재빨리 일어나 공중 나래차기 ➔ 180도 점프 뒤돌아 착지를 반복합니다."
            },
            {
                "kr": "누워서 V업 복근 2회 후 오뚝이 기립, 좌우 하이킥 2회, 전방 회전낙법! 쉼 없이 반복!",
                "mix": "V업 복근 2회, 오뚝이 기립, 하이 킥 2회, 롤링 낙법! 무한 리핏!",
                "dual": "누워서 V업 복근 2회, 좌우 하이킥 2회, 회전낙법! - 2 V-ups, 2 high kicks, rolling breakfall, repeat!",
                "en": "2 V-ups, stand up quick, 2 alternating high kicks, rolling breakfall! Non-stop loop!",
                "tip": "손끝 발끝 V업 복근 2회 ➔ 반동으로 오뚝이처럼 일어나 좌우 하이킥 2회 ➔ 전방 회전낙법 후 반복합니다."
            },
            {
                "kr": "쪼그려 점프 3회 후 앞발 컷트 카운터 뒤차기, 좌우 스케이터 점프 2회! 쉼 없이 반복!",
                "mix": "스쿼트 점프 3회, 앞발 컷트 카운터 뒤차기, 스케이터 점프 2회! 무한 리핏!",
                "dual": "쪼그려 점프 3회, 컷트 카운터 뒤차기, 스케이터 점프! - 3 squat jumps, cut & counter kick, skaters, repeat!",
                "en": "3 squat jumps, front cut to counter back kick, 2 lateral skater jumps! Non-stop loop!",
                "tip": "깊게 쪼그려 점프 3회 ➔ 앞발 컷트 후 번개 카운터 뒤차기 ➔ 좌우 스케이터 점프 2회 후 반복합니다."
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
    def parse_custom_circuit_text(cls, text: str) -> List[Dict[str, str]]:
        """
        Parses customized combo routine text into structured exercise dictionaries.
        Supports:
          - "1번 콤보: ...", "1. ...", "[1세트] ..."
          - Tip lines containing "지도 팁", "➔ [지도" attached to the previous combo
          - Raw text lines
        """
        if not text or not text.strip():
            return []

        import re
        lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
        exercises = []
        current_item = None

        for line in lines:
            # Check if this line is an instructional tip
            if any(marker in line for marker in ["[지도 팁]", "지도 팁", "➔ [지도", "★", "※"]):
                if current_item:
                    tip_part = line.split(":", 1)[-1].strip() if ":" in line else line
                    current_item["tip"] = tip_part.replace("]", "").strip()
                continue

            # Check if line starts with combo marker like '1번 콤보:', '1.', '[1세트]', '1)'
            m = re.match(r"^(?:\[?\d+세트\]?|\d+번\s*(?:콤보)?|\d+[\.\)])\s*[:\-\.]?\s*(.+)$", line)
            if m:
                combo_text = m.group(1).strip()
                if combo_text:
                    current_item = {
                        "kr": combo_text,
                        "mix": combo_text,
                        "dual": combo_text,
                        "en": combo_text,
                        "tip": ""
                    }
                    exercises.append(current_item)
            else:
                # Normal line without number prefix
                current_item = {
                    "kr": line,
                    "mix": line,
                    "dual": line,
                    "en": line,
                    "tip": ""
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
                "text": f"[{label}] 갈려!",
                "duration": 0.7,
                "track": 2,
                "vol": 2.8
            })
            if duck_segments is not None:
                duck_segments.append((int(curr_time * 1000), int((curr_time + 0.8) * 1000)))
            return 0.8
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
                "text": f"[{label}] 갈려!",
                "duration": 0.7,
                "track": 2,
                "vol": 2.8
            })
            if duck_segments is not None:
                duck_segments.append((int(curr_time * 1000), int((curr_time + 0.8) * 1000)))
            return 0.8

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
        lang = params.get("language_mode", "mix_kids")
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
        theme_title = theme_data.get(f"name_{lang_key}", theme_data.get("name_kr", "기능성 서킷 인터벌"))

        events = []
        duck_segments = []
        curr_time = 1.0

        # 2. 서킷 인터벌 전용 사전 안내 방송 (스파링 멘트가 아닌 서킷 전용 멘트)
        if intro_enabled:
            intro_text = params.get("intro_text", "").strip()
            if not intro_text:
                if circuit_mode_type == "single":
                    ex0_name = exercises[0].get(lang_key, exercises[0].get("kr", ""))
                    clean_ex = str(ex0_name).rstrip(".!? ").strip()
                    import re
                    is_pred = bool(re.search(r'(됩니다|합니다|입니다|습니다|된다|한다|이다)$', clean_ex))
                    appended_ex = clean_ex if is_pred else f"{clean_ex}입니다"
                    if lang == "mix_kids":
                        intro_text = f"지금부터 단일 집중 파워 인터벌 스타트! 오늘의 집중 콤보는 {appended_ex}. 매 세트 전력 무한 리핏! 준비해 주세요!"
                    elif lang == "dual_step":
                        intro_text = f"지금부터 단일 집중 인터벌 훈련을 시작합니다. - Focused interval training! 오늘 집중 동작은 {appended_ex}. 매 세트 전력 반복하세요. 준비!"
                    elif lang in ("en", "en_advanced"):
                        intro_text = f"Attention team! Today's focused interval theme is {theme_title}. Perform the combo loop non-stop during work intervals! Get ready!"
                    else:
                        intro_text = f"지금부터 단일 종목 집중 서킷 인터벌 훈련을 시작합니다! 이번 훈련은 {clean_ex} 단일 콤보를 전 세트 동안 극한으로 반복하여 심폐지구력과 근력을 극대화합니다. 모두 준비해 주세요!"
                else:
                    if lang == "mix_kids":
                        intro_text = f"지금부터 도장 파워 콤보 인터벌 스타트! 이번 테마는 {theme_title}입니다. 점프, 발차기, 롤링 낙법 콤보를 운동 시간 동안 쉼 없이 무한 리핏! 레스트 타임에 릴랙스! 준비해 주세요!"
                    elif lang == "dual_step":
                        intro_text = f"지금부터 도장 실전 복합 인터벌 훈련을 시작합니다. - Functional flow interval training! 테마는 '{theme_title}'입니다. 체력, 발차기, 낙법 콤보를 무한 반복하세요. 모두 준비!"
                    elif lang in ("en", "en_advanced"):
                        intro_text = f"Attention team! Today's functional flow interval theme is {theme_title}. Perform the continuous combo loop non-stop during work intervals, and breathe deep during rest! Get ready!"
                    else:
                        intro_text = f"지금부터 도장 실전 복합 서킷 인터벌 훈련을 시작합니다! 이번 테마는 '{theme_title}'입니다. 각 세트마다 체력, 발차기, 회전낙법이 결합된 연속 콤보를 운동 시간 동안 전력으로 쉬지 않고 무한 반복합니다. 모두 준비해 주세요!"

            intro_dur = max(3.5, round(len(intro_text) * 0.22, 2))
            events.append({
                "time": curr_time,
                "type": "voice",
                "text": f"[인터벌 사전 안내] {intro_text}",
                "duration": intro_dur,
                "track": 2,
                "vol": 2.5
            })
            curr_time += intro_dur + 0.8

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
                if s == 1 and circuit_mode_type == "single":
                    call_text = f"[오늘의 집중 콤보] {ex_name}"
                elif lang == "mix_kids":
                    call_text = f"[{s}세트 콤보] {ex_name}"
                elif lang == "dual_step":
                    call_text = f"[{s}세트] {ex_name}"
                elif lang in ("en", "en_advanced"):
                    call_text = f"[Set {s} Flow] {ex_name}"
                else:
                    call_text = f"[{s}세트 복합 콤보] {ex_name}"

                call_dur = max(1.8, round(len(call_text) * 0.20, 2))
                events.append({
                    "time": curr_time,
                    "type": "voice",
                    "text": call_text,
                    "duration": call_dur,
                    "track": 2,
                    "vol": 2.5
                })
                curr_time += call_dur + 0.5

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
                if lang == "mix_kids":
                    rest_ment = "릴랙스 휴식! 딥 브레스 쉬고 다음 동작 웨이트!"
                elif lang == "dual_step":
                    rest_ment = "휴식! 호흡 가다듬으세요. - Rest, catch your breath!"
                elif lang in ("en", "en_advanced"):
                    rest_ment = "Rest and breathe! Next exercise coming up!"
                else:
                    rest_ment = "휴식! 호흡 가다듬고 다음 세트 준비하세요."

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
            final_outro = "고강도 인터벌 훈련 종료! 굿 잡! 모두 수고했습니다! 워터 물 한잔 마시고 호흡을 릴랙스 가다듬으세요!"
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
