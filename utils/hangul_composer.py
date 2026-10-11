"""
Hangul Jamo Auto-Composer (완전한 한글 자모 실시간 자동 분해·재조합 오토마타)
Solves macOS PyQt IME disassembled jamo issues and remote typing jamo bugs.
Fully supports:
  - Decompose completed syllables + newly typed jamo -> seamless recombine (e.g. '호'+'ㅏ'+'ㄴ' -> '환')
  - Compatibility jamo (호환 자모 U+3131~U+318E: 'ㅌㅔㅅㅡㅌㅡ' -> '테스트')
  - Single-space separated remote jamo typing (e.g. 'ㅌ ㅔ ㅅ ㅡ' -> '테스')
  - Unicode NFD jamo (U+1100~U+11FF)
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

# 이중모음 및 겹받침 단일 자모 분해 맵
SPLIT_JUNG = {
    'ㅘ': ['ㅗ', 'ㅏ'], 'ㅙ': ['ㅗ', 'ㅐ'], 'ㅚ': ['ㅗ', 'ㅣ'],
    'ㅝ': ['ㅜ', 'ㅓ'], 'ㅞ': ['ㅜ', 'ㅔ'], 'ㅟ': ['ㅜ', 'ㅣ'],
    'ㅢ': ['ㅡ', 'ㅣ']
}

SPLIT_JONG = {
    'ㄳ': ['ㄱ', 'ㅅ'], 'ㄵ': ['ㄴ', 'ㅈ'], 'ㄶ': ['ㄴ', 'ㅎ'],
    'ㄺ': ['ㄹ', 'ㄱ'], 'ㄻ': ['ㄹ', 'ㅁ'], 'ㄼ': ['ㄹ', 'ㅂ'],
    'ㄽ': ['ㄹ', 'ㅅ'], 'ㄾ': ['ㄹ', 'ㅌ'], 'ㄿ': ['ㄹ', 'ㅍ'],
    'ㅀ': ['ㄹ', 'ㅎ'], 'ㅄ': ['ㅂ', 'ㅅ']
}


def full_decompose(text: str) -> list:
    """완성형 음절 및 NFD 자모를 기본 단일 자모 스트림으로 완전 평탄화 분해"""
    chars = []
    for ch in text:
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:
            code -= 0xAC00
            jong_idx = code % 28
            code //= 28
            jung_idx = code % 21
            cho_idx = code // 21
            chars.append(CHOSUNG[cho_idx])
            jung = JUNGSUNG[jung_idx]
            chars.extend(SPLIT_JUNG.get(jung, [jung]))
            if jong_idx > 0:
                jong = JONGSUNG[jong_idx]
                chars.extend(SPLIT_JONG.get(jong, [jong]))
        elif 0x1100 <= code <= 0x11FF:
            # Unicode NFD jamo normalize
            nfc = unicodedata.normalize('NFC', ch)
            chars.extend(full_decompose(nfc))
        else:
            chars.append(ch)
    return chars


def compose_automata(jamo_list: list) -> str:
    """단일 자모 스트림을 2벌식 오토마타 규칙에 따라 온전한 완성형 음절로 재조합"""
    # 1. 자모 사이에 끼어있는 원격 IME 단일 공백 흡수 (예: 'ㅌ ㅔ' -> 'ㅌㅔ')
    clean_jamos = []
    k = 0
    m = len(jamo_list)
    while k < m:
        c = jamo_list[k]
        if c == ' ' and clean_jamos and k + 1 < m:
            prev = clean_jamos[-1]
            nxt = jamo_list[k + 1]
            if (prev in CHO_MAP and nxt in JUNG_MAP) or (prev in JUNG_MAP and nxt in CHO_MAP) or (prev in JUNG_MAP and nxt in JUNG_MAP):
                k += 1
                continue
        clean_jamos.append(c)
        k += 1

    # 2. 음절 조합 오토마타
    result = []
    i = 0
    n = len(clean_jamos)
    while i < n:
        c = clean_jamos[i]
        # 초성 + 중성 감지
        if c in CHO_MAP and i + 1 < n and clean_jamos[i + 1] in JUNG_MAP:
            cho_idx = CHO_MAP[c]
            jung_char = clean_jamos[i + 1]
            i += 2

            # 이중 모음 확인 (예: ㅗ + ㅏ -> ㅘ)
            if i < n and (jung_char, clean_jamos[i]) in DOUBLE_JUNGSUNG:
                jung_char = DOUBLE_JUNGSUNG[(jung_char, clean_jamos[i])]
                i += 1
            jung_idx = JUNG_MAP[jung_char]

            # 종성 확인
            jong_idx = 0
            if i < n and clean_jamos[i] in JONG_MAP and JONG_MAP[clean_jamos[i]] != 0:
                # 다음다음 글자가 모음이면 이 자음은 다음 음절의 초성으로 넘김!
                if i + 1 < n and clean_jamos[i + 1] in JUNG_MAP:
                    pass
                else:
                    first_jong = clean_jamos[i]
                    # 겹받침 가능 여부 확인
                    if i + 1 < n and (first_jong, clean_jamos[i + 1]) in DOUBLE_JONGSUNG:
                        if not (i + 2 < n and clean_jamos[i + 2] in JUNG_MAP):
                            double_jong = DOUBLE_JONGSUNG[(first_jong, clean_jamos[i + 1])]
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


def compose_hangul_jamo(text: str) -> str:
    """
    분리된 한글 자모(호환 자모/NFD) 및 반조합 음절을 온전한 완성형 음절(NFC)로 결합합니다.
    예:
      - 'ㅌㅔㅅㅡㅌㅡ' -> '테스트'
      - 'ㅌ ㅔ ㅅ ㅡ' -> '테스'
      - '호' + 'ㅏ' + 'ㄴ' -> '환'
      - '겨' + 'ㅇ' -> '경'
    """
    if not text:
        return text

    # 자모가 전혀 없으면 초고속 패스스루
    has_jamo = any('\u3131' <= ch <= '\u318e' or '\u1100' <= ch <= '\u11ff' for ch in text)
    if not has_jamo:
        return text

    # 완전 분해 후 2벌식 오토마타 재조합
    decomposed = full_decompose(text)
    return compose_automata(decomposed)
