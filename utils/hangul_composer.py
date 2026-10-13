"""
Hangul Jamo Auto-Composer (완전한 한글 자모 실시간 자동 분해·재조합 오토마타 & 전역 입력 보호기)
Solves macOS PyQt6 IME disassembled jamo issues ('ㅅㅡㅍㅏㄹㅣㅇ' -> '스파링') across all widgets.
Fully supports:
  - Step-by-step real-time syllable + jamo re-composition ('스' + 'ㅍ' -> '슾' + 'ㅏ' -> '스파')
  - Compatibility jamo (호환 자모 U+3131~U+318E)
  - Unicode NFD conjoining jamo (U+1100~U+11FF) without recursion
  - Preserves word spaces after completed syllables ('스파 ㅎ' -> '스파 ㅎ', never '스팧')
  - Uses QTextCursor minimal-diff replacement so macOS native IME preedit state is never broken
"""

import re
import unicodedata

CHOSUNG = ['ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ']
JUNGSUNG = ['ㅏ', 'ㅐ', 'ㅑ', 'ㅒ', 'ㅓ', 'ㅔ', 'ㅕ', 'ㅖ', 'ㅗ', 'ㅘ', 'ㅙ', 'ㅚ', 'ㅛ', 'ㅜ', 'ㅝ', 'ㅞ', 'ㅟ', 'ㅠ', 'ㅡ', 'ㅢ', 'ㅣ']
JONGSUNG = ['', 'ㄱ', 'ㄲ', 'ㄳ', 'ㄴ', 'ㄵ', 'ㄶ', 'ㄷ', 'ㄹ', 'ㄺ', 'ㄻ', 'ㄼ', 'ㄽ', 'ㄾ', 'ㄿ', 'ㅀ', 'ㅁ', 'ㅂ', 'ㅄ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ']

DOUBLE_JUNGSUNG = {
    ('ㅗ', 'ㅏ'): 'ㅘ', ('ㅗ', 'ㅐ'): 'ㅙ', ('ㅗ', 'ㅣ'): 'ㅚ',
    ('ㅜ', 'ㅓ'): 'ㅝ', ('ㅜ', 'ㅔ'): 'ㅞ', ('ㅜ', 'ㅣ'): 'ㅟ',
    ('ㅡ', 'ㅣ'): 'ㅢ'
}

DOUBLE_JONGSUNG = {
    ('ㄱ', 'ㅅ'): 'ㄳ', ('ㄴ', 'ㅈ'): 'ㄵ', ('ㄴ', 'ㅎ'): 'ㄶ',
    ('ㄹ', 'ㄱ'): 'ㄹㄱ', # handled via DOUBLE_JONGSUNG_MAP below
}

DOUBLE_JONGSUNG_MAP = {
    ('ㄱ', 'ㅅ'): 'ㄳ', ('ㄴ', 'ㅈ'): 'ㄵ', ('ㄴ', 'ㅎ'): 'ㄶ',
    ('ㄹ', 'ㄱ'): 'ㄺ', ('ㄹ', 'ㅁ'): 'ㄻ', ('ㄹ', 'ㅂ'): 'ㄼ',
    ('ㄹ', 'ㅅ'): 'ㄽ', ('ㄹ', 'ㅌ'): 'ㄾ', ('ㄹ', 'ㅍ'): 'ㄿ',
    ('ㄹ', 'ㅎ'): 'ㅀ', ('ㅂ', 'ㅅ'): 'ㅄ'
}

CHO_MAP = {c: i for i, c in enumerate(CHOSUNG)}
JUNG_MAP = {c: i for i, c in enumerate(JUNGSUNG)}
JONG_MAP = {c: i for i, c in enumerate(JONGSUNG)}

SPLIT_JUNG = {
    'ㅘ': ['ㅗ', 'ㅏ'], 'ㅙ': ['ㅗ', 'ㅐ'], 'ㅚ': ['ㅗ', 'ㅣ'],
    'ㅝ': ['ㅜ', 'ㅓ'], 'ㅞ': ['ㅜ', 'ㅔ'], 'ㅟ': ['ㅜ', 'ㅣ'],
    'ㅢ': ['ㅡ', 'ㅣ']
}

SPLIT_JONG = {
    'ㄳ': ['ㄱ', 'ㅅ'], 'ㄵ': ['ㄴ', 'ㅈ'], 'ㄶ': ['ㄴ', 'ㅎ'],
    'ㄹㄱ': ['ㄹ', 'ㄱ'], 'ㄺ': ['ㄹ', 'ㄱ'], 'ㄻ': ['ㄹ', 'ㅁ'], 'ㄼ': ['ㄹ', 'ㅂ'],
    'ㄽ': ['ㄹ', 'ㅅ'], 'ㄾ': ['ㄹ', 'ㅌ'], 'ㄿ': ['ㄹ', 'ㅍ'],
    'ㅀ': ['ㄹ', 'ㅎ'], 'ㅄ': ['ㅂ', 'ㅅ']
}


def is_raw_jamo(ch: str) -> bool:
    if not ch:
        return False
    code = ord(ch)
    return (0x3131 <= code <= 0x318E) or (0x1100 <= code <= 0x11FF) or (0xFFA0 <= code <= 0xFFDC)


def has_any_jamo(text: str) -> bool:
    if not text:
        return False
    return any(is_raw_jamo(ch) for ch in text)


def _decompose_char(ch: str) -> list:
    """단일 문자(완성형 음절, NFD 자모, 호환 자모)를 기본 호환 자모 리스트로 안전하게 분해 (재귀 없음)"""
    code = ord(ch)
    if 0xAC00 <= code <= 0xD7A3:
        code -= 0xAC00
        jong_idx = code % 28
        code //= 28
        jung_idx = code % 21
        cho_idx = code // 21
        res = [CHOSUNG[cho_idx]]
        jung = JUNGSUNG[jung_idx]
        res.extend(SPLIT_JUNG.get(jung, [jung]))
        if jong_idx > 0:
            jong = JONGSUNG[jong_idx]
            res.extend(SPLIT_JONG.get(jong, [jong]))
        return res
    elif 0x1100 <= code <= 0x1112:
        return [CHOSUNG[code - 0x1100]]
    elif 0x1161 <= code <= 0x1175:
        jung = JUNGSUNG[code - 0x1161]
        return SPLIT_JUNG.get(jung, [jung])
    elif 0x11A8 <= code <= 0x11C2:
        jong = JONGSUNG[code - 0x11A7]
        return SPLIT_JONG.get(jong, [jong])
    elif 0xFFA0 <= code <= 0xFFDC:
        nfkc = unicodedata.normalize('NFKC', ch)
        if nfkc != ch:
            out = []
            for sub in nfkc:
                out.extend(SPLIT_JUNG.get(sub, SPLIT_JONG.get(sub, [sub])))
            return out
        return [ch]
    elif ch in SPLIT_JUNG:
        return SPLIT_JUNG[ch]
    elif ch in SPLIT_JONG:
        return SPLIT_JONG[ch]
    else:
        return [ch]


def compose_automata(jamo_list: list) -> str:
    """단일 자모 스트림을 2벌식 오토마타 규칙에 따라 온전한 완성형 음절로 재조합"""
    result = []
    i = 0
    n = len(jamo_list)
    while i < n:
        c = jamo_list[i]
        if c in CHO_MAP and i + 1 < n and jamo_list[i + 1] in JUNG_MAP:
            cho_idx = CHO_MAP[c]
            jung_char = jamo_list[i + 1]
            i += 2

            # 이중 모음 확인 (예: ㅗ + ㅏ -> ㅘ)
            if i < n and (jung_char, jamo_list[i]) in DOUBLE_JUNGSUNG:
                jung_char = DOUBLE_JUNGSUNG[(jung_char, jamo_list[i])]
                i += 1
            jung_idx = JUNG_MAP[jung_char]

            # 종성 확인
            jong_idx = 0
            if i < n and jamo_list[i] in JONG_MAP and JONG_MAP[jamo_list[i]] != 0:
                # 다음 글자가 모음이면 이 자음은 다음 음절의 초성으로 넘김
                if i + 1 < n and jamo_list[i + 1] in JUNG_MAP:
                    pass
                else:
                    first_jong = jamo_list[i]
                    if i + 1 < n and (first_jong, jamo_list[i + 1]) in DOUBLE_JONGSUNG_MAP:
                        if not (i + 2 < n and jamo_list[i + 2] in JUNG_MAP):
                            double_jong = DOUBLE_JONGSUNG_MAP[(first_jong, jamo_list[i + 1])]
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


# 한글 음절 + 분리 자모가 붙어 있는 연속 덩어리 정규식 (단어 사이 정상 공백은 절대 건드리지 않음)
_HANGUL_CLUSTER_RE = re.compile(r'[\uAC00-\uD7A3\u3131-\u318E\u1100-\u11FF\uFFA0-\uFFDC]+')


def compose_hangul_jamo(text: str) -> str:
    """
    분리된 한글 자모(호환 자모/NFD) 및 반조합 음절을 온전한 완성형 음절(NFC)로 결합합니다.
    정상적인 단어 사이의 공백('스파 ㅎ')은 100% 보존하면서,
    자모가 섞인 연속 한글 덩어리('ㅅㅡㅍㅏㄹㅣㅇ', '스ㅍㅏ' 등)만 정확히 조합합니다.
    """
    if not text or not has_any_jamo(text):
        return text

    # 1. 만약 원격 입력 등으로 순수 낱개 자모들 사이에만 단일 공백이 끼어있는 경우('ㅌ ㅔ ㅅ ㅡ') 먼저 붙임
    #    (완성형 음절 뒤의 공백은 절대 건드리지 않음!)
    chars = list(text)
    cleaned = []
    idx = 0
    total = len(chars)
    while idx < total:
        ch = chars[idx]
        if ch == ' ' and cleaned and idx + 1 < total:
            prev_ch = cleaned[-1]
            next_ch = chars[idx + 1]
            if is_raw_jamo(prev_ch) and is_raw_jamo(next_ch):
                p_list = _decompose_char(prev_ch)
                n_list = _decompose_char(next_ch)
                if p_list and n_list:
                    p0, n0 = p_list[-1], n_list[0]
                    if (p0 in CHO_MAP and n0 in JUNG_MAP) or (p0 in JUNG_MAP and n0 in CHO_MAP) or ((p0, n0) in DOUBLE_JUNGSUNG):
                        idx += 1
                        continue
        cleaned.append(ch)
        idx += 1
    working = ''.join(cleaned)

    # 2. 자모가 포함된 연속 한글 덩어리만 분해 후 2벌식 오토마타로 재조합
    def _replace_cluster(match: re.Match) -> str:
        cluster = match.group(0)
        if not has_any_jamo(cluster):
            return cluster
        decomposed = []
        for c in cluster:
            decomposed.extend(_decompose_char(c))
        return compose_automata(decomposed)

    return _HANGUL_CLUSTER_RE.sub(_replace_cluster, working)


def apply_hangul_compose_to_textedit(widget) -> None:
    """
    QTextEdit / QPlainTextEdit에서 macOS IME preedit 세션을 깨뜨리지 않고
    분리된 자모 영역만 QTextCursor로 정밀 치환합니다.
    """
    if getattr(widget, '_in_hangul_compose', False):
        return
    try:
        if widget.isReadOnly():
            return
    except Exception:
        pass

    text = widget.toPlainText()
    if not text or not has_any_jamo(text):
        return

    composed = compose_hangul_jamo(text)
    if composed == text:
        return

    prefix_len = 0
    min_len = min(len(text), len(composed))
    while prefix_len < min_len and text[prefix_len] == composed[prefix_len]:
        prefix_len += 1

    suffix_len = 0
    while (
        suffix_len < (min_len - prefix_len)
        and text[len(text) - 1 - suffix_len] == composed[len(composed) - 1 - suffix_len]
    ):
        suffix_len += 1

    replace_start = prefix_len
    replace_end = len(text) - suffix_len
    replacement = composed[prefix_len : len(composed) - suffix_len]

    widget._in_hangul_compose = True
    try:
        from PyQt6.QtGui import QTextCursor
        edit_cursor = widget.textCursor()
        edit_cursor.beginEditBlock()
        edit_cursor.setPosition(replace_start)
        edit_cursor.setPosition(replace_end, QTextCursor.MoveMode.KeepAnchor)
        edit_cursor.insertText(replacement)
        edit_cursor.endEditBlock()
    except Exception:
        pass
    finally:
        widget._in_hangul_compose = False


def apply_hangul_compose_to_lineedit(widget) -> None:
    """QLineEdit에서 분리된 자모를 실시간으로 조합합니다."""
    if getattr(widget, '_in_hangul_compose', False):
        return
    try:
        if widget.isReadOnly():
            return
    except Exception:
        pass

    text = widget.text()
    if not text or not has_any_jamo(text):
        return

    composed = compose_hangul_jamo(text)
    if composed == text:
        return

    widget._in_hangul_compose = True
    try:
        pos = widget.cursorPosition()
        diff = len(text) - len(composed)
        widget.blockSignals(True)
        widget.setText(composed)
        widget.setCursorPosition(max(0, min(len(composed), pos - diff)))
        widget.blockSignals(False)
    except Exception:
        pass
    finally:
        widget._in_hangul_compose = False


def bind_hangul_composer(widget) -> None:
    """특정 입력 위젯(QTextEdit, QPlainTextEdit, QLineEdit)에 한글 자모 자동 조합기를 바인딩합니다."""
    if widget is None or getattr(widget, '_hangul_composer_bound', False):
        return
    try:
        from PyQt6.QtWidgets import QTextEdit, QPlainTextEdit, QLineEdit
        from PyQt6.QtCore import Qt
        if isinstance(widget, (QTextEdit, QPlainTextEdit)):
            widget.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
            widget.textChanged.connect(lambda w=widget: apply_hangul_compose_to_textedit(w))
            widget._hangul_composer_bound = True
        elif isinstance(widget, QLineEdit):
            widget.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
            widget.textChanged.connect(lambda _txt, w=widget: apply_hangul_compose_to_lineedit(w))
            widget._hangul_composer_bound = True
    except Exception:
        pass


def install_global_hangul_composer(app) -> None:
    """
    QApplication 전체에 포커스 이동 리스너를 장착하여,
    메인 창·서킷 마법사·스파링 마법사·준비운동 마법사·설정창 등 모든 입력칸에서
    한글 자모 분리('ㅅㅡㅍㅏㄹㅣㅇ') 현상을 자동으로 100% 방지합니다.
    """
    if app is None or getattr(app, '_global_hangul_composer_installed', False):
        return

    def _on_focus_changed(_old, new_widget):
        if new_widget is not None:
            bind_hangul_composer(new_widget)

    app.focusChanged.connect(_on_focus_changed)
    app._global_hangul_composer_installed = True
