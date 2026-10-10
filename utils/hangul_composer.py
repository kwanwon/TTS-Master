"""
Hangul Jamo Auto-Composer (한글 자모 실시간 자동 조합기)
Solves macOS PyQt IME disassembled jamo issues (e.g. 'ㅌㅔㅅㅡㅌㅡ' -> '테스트').
Combines compatibility jamo (호환 자모) and unicode NFD jamo into complete modern Korean syllables (NFC).
"""

import unicodedata

CHOSUNG = ['ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ']
JUNGSUNG = ['ㅏ', 'ㅐ', 'ㅑ', 'ㅒ', 'ㅓ', 'ㅔ', 'ㅕ', 'ㅖ', 'ㅗ', 'ㅘ', 'ㅙ', 'ㅚ', 'ㅛ', 'ㅜ', 'ㅝ', 'ㅞ', 'ㅟ', 'ㅠ', 'ㅡ', 'ㅢ', 'ㅣ']
JONGSUNG = ['', 'ㄱ', 'ㄲ', 'ㄳ', 'ㄴ', 'ㄵ', 'ㄶ', 'ㄷ', 'ㄹ', 'ㄺ', 'ㄻ', 'ㄼ', 'ㄽ', 'ㄾ', 'ㄿ', 'ㅀ', 'ㅁ', 'ㅂ', 'ㅄ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ']

# 이중 모음 결합 맵
DOUBLE_JUNGSUNG = {
    ('ㅗ', 'ㅏ'): 'ㅘ', ('ㅗ', 'ㅐ'): 'ㅙ', ('ㅗ', 'ㅣ'): 'ㅚ',
    ('ㅜ', 'ㅓ'): 'ㅝ', ('ㅜ', 'ㅔ'): 'ㅞ', ('ㅜ', 'ㅣ'): 'ㅟ',
    ('ㅡ', 'ㅣ'): 'ㅢ'
}

# 겹받침 종성 결합 맵
DOUBLE_JONGSUNG = {
    ('ㄱ', 'ㅅ'): 'ㄳ', ('ㄴ', 'ㅈ'): 'ㄵ', ('ㄴ', 'ㅎ'): 'ㄶ',
    ('ㄹ', 'ㄱ'): 'ㄺ', ('ㄹ', 'ㅁ'): 'ㄻ', ('ㄹ', 'ㅂ'): 'ㄼ',
    ('ㄹ', 'ㅅ'): 'ㄽ', ('ㄹ', 'ㅌ'): 'ㄾ', ('ㄹ', 'ㅍ'): 'ㄿ',
    ('ㄹ', 'ㅎ'): 'ㅀ', ('ㅂ', 'ㅅ'): 'ㅄ'
}

CHO_MAP = {c: i for i, c in enumerate(CHOSUNG)}
JUNG_MAP = {c: i for i, c in enumerate(JUNGSUNG)}
JONG_MAP = {c: i for i, c in enumerate(JONGSUNG)}


def compose_hangul_jamo(text: str) -> str:
    """
    분리된 한글 자모(호환 자모/NFD)를 온전한 한글 완성형 음절(NFC)로 결합합니다.
    예: 'ㅌㅔㅅㅡㅌㅡ ㅇㅣㅂㄴㅣㄷㅏ.' -> '테스트 입니다.'
    """
    if not text:
        return text

    # 1. 1차 유니코드 NFC 정규화
    normalized = unicodedata.normalize('NFC', text)

    # 자모가 전혀 없으면 바로 반환 (고속 패스스루)
    has_jamo = any('\u3131' <= ch <= '\u318e' or '\u1100' <= ch <= '\u11ff' for ch in normalized)
    if not has_jamo:
        return normalized

    # 2. 2벌식 조립 오토마타
    result = []
    i = 0
    n = len(normalized)

    while i < n:
        c = normalized[i]
        # 초성 + 중성 조합 감지
        if c in CHO_MAP and i + 1 < n and normalized[i + 1] in JUNG_MAP:
            cho_idx = CHO_MAP[c]
            jung_char = normalized[i + 1]
            i += 2

            # 이중 모음 확인 (예: ㅗ + ㅏ -> ㅘ)
            if i < n and (jung_char, normalized[i]) in DOUBLE_JUNGSUNG:
                jung_char = DOUBLE_JUNGSUNG[(jung_char, normalized[i])]
                i += 1
            jung_idx = JUNG_MAP[jung_char]

            # 종성 확인
            jong_idx = 0
            if i < n and normalized[i] in JONG_MAP and JONG_MAP[normalized[i]] != 0:
                # 다음다음 글자가 모음이면 이 자음은 다음 음절의 초성으로 넘김!
                if i + 1 < n and normalized[i + 1] in JUNG_MAP:
                    pass
                else:
                    first_jong = normalized[i]
                    # 겹받침 가능 여부 확인
                    if i + 1 < n and (first_jong, normalized[i + 1]) in DOUBLE_JONGSUNG:
                        if not (i + 2 < n and normalized[i + 2] in JUNG_MAP):
                            double_jong = DOUBLE_JONGSUNG[(first_jong, normalized[i + 1])]
                            jong_idx = JONG_MAP[double_jong]
                            i += 2
                        else:
                            jong_idx = JONG_MAP[first_jong]
                            i += 1
                    else:
                        jong_idx = JONG_MAP[first_jong]
                        i += 1

            syllable = chr(0xAC00 + (cho_idx * 21 + jung_idx) * 28 + jong_idx)
            result.append(syllable)
        else:
            result.append(c)
            i += 1

    return ''.join(result)
