import os
import re
import json
import zipfile
import urllib.request
import urllib.parse
import ssl
import tempfile
import xml.etree.ElementTree as ET
import traceback
from typing import Optional, Dict, List, Any
from openai import OpenAI


def _get_user_config_dir() -> str:
    user_dir = os.path.join(os.path.expanduser("~"), ".aimaster_tts")
    os.makedirs(user_dir, exist_ok=True)
    return user_dir


def load_gemini_env() -> dict:
    """
    Loads Gemini API configuration from environment variables or .env files
    without hardcoding sensitive keys in source code.
    """
    config = {
        "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY", ""),
        "GEMINI_MODEL": os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite"),
        "GEMINI_BASE_URL": os.environ.get(
            "GEMINI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/openai/"
        ),
    }

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(_get_user_config_dir(), ".env"),
        os.path.join(os.getcwd(), ".env"),
        os.path.join(base_dir, ".env"),
        "/Users/gm2hapkido/Desktop/TTS컨트롤/.env",
    ]

    for env_path in candidates:
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k == "GEMINI_API_KEY" and v and not config["GEMINI_API_KEY"]:
                            config["GEMINI_API_KEY"] = v
                        elif k in ("GEMINI_MODEL", "GEMINI_BASE_URL") and v:
                            config[k] = v
                if config["GEMINI_API_KEY"]:
                    break
            except Exception:
                continue

    if not config["GEMINI_MODEL"]:
        config["GEMINI_MODEL"] = "gemini-3.1-flash-lite"
    if not config["GEMINI_BASE_URL"]:
        config["GEMINI_BASE_URL"] = "https://generativelanguage.googleapis.com/v1beta/openai/"

    return config


def save_gemini_api_key(api_key: str, model: str = "gemini-3.1-flash-lite"):
    """Saves the Gemini API key safely to ~/.aimaster_tts/.env and local .env."""
    api_key = (api_key or "").strip()
    if not api_key:
        return
    env_content = (
        f"GEMINI_API_KEY={api_key}\n"
        f"GEMINI_MODEL={model}\n"
        f"GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/\n"
    )
    user_dir = _get_user_config_dir()
    try:
        with open(os.path.join(user_dir, ".env"), "w", encoding="utf-8") as f:
            f.write(env_content)
    except Exception:
        pass

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    local_env = os.path.join(base_dir, ".env")
    try:
        if os.access(base_dir, os.W_OK):
            with open(local_env, "w", encoding="utf-8") as f:
                f.write(env_content)
    except Exception:
        pass


def load_common_settings() -> dict:
    """
    Loads shared program-wide settings (API key status, Google Drive link,
    reference file path, common dojo/training notes).
    """
    default_data = {
        "gdrive_url": "",
        "plan_file_path": "",
        "common_info": "",
        "dashscope_api_key": "",
    }
    settings_path = os.path.join(_get_user_config_dir(), "common_ai_settings.json")
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    default_data.update(loaded)
        except Exception:
            pass
    return default_data


def save_common_settings(data: dict):
    """Saves shared program-wide settings to ~/.aimaster_tts/common_ai_settings.json."""
    settings_path = os.path.join(_get_user_config_dir(), "common_ai_settings.json")
    try:
        current = load_common_settings()
        current.update(data or {})
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def extract_requested_circuit_combo_count(text: str) -> Optional[int]:
    """
    Extracts explicitly requested combo count from user prompt.
    E.g.:
      - "1번부터 3번 콤보까지" -> 3
      - "1부터 3번까지" -> 3
      - "1~3번 콤보", "1-3번", "1번 ~ 3번" -> 3
      - "1번 콤보, 2번 콤보, 3번 콤보" -> 3
      - "3개 콤보", "3콤보", "3개 세트", "3세트", "총 3개 콤보" -> 3
      - "콤보 1부터 3까지" -> 3
    Returns integer between 1 and 10, or None if not explicitly specified.
    """
    if not text:
        return None
    cleaned = text.strip()

    # 1. "1번부터 3번 콤보까지", "1부터 3번까지", "1~3번", "1 - 3번 콤보", "1번 ~ 3번 콤보", "1번부터 3번까지" 등
    m = re.search(r"(?:1\s*(?:번)?\s*(?:콤보|세트)?\s*(?:부터|~|-)\s*(\d+)\s*(?:번)?\s*(?:콤보|세트)?)", cleaned)
    if m:
        val = int(m.group(1))
        if 1 <= val <= 10:
            return val

    # 2. "콤보 1부터 3까지", "세트 1~3"
    m = re.search(r"(?:콤보|세트)\s*1\s*(?:부터|~|-)\s*(\d+)", cleaned)
    if m:
        val = int(m.group(1))
        if 1 <= val <= 10:
            return val

    # 3. 나열형: "1번, 2번, 3번", "1번 콤보, 2번 콤보, 3번 콤보"
    numbered_matches = re.findall(r"(\d+)\s*번\s*(?:콤보|세트)?", cleaned)
    if len(numbered_matches) >= 2:
        nums = [int(n) for n in numbered_matches]
        if nums == list(range(1, max(nums) + 1)) and 1 <= max(nums) <= 10:
            return max(nums)

    # 4. "3개 콤보", "3콤보", "3개 세트", "3세트", "총 3개 콤보"
    m = re.search(r"(\d+)\s*(?:개\s*콤보|콤보|개\s*세트|세트)", cleaned)
    if m:
        val = int(m.group(1))
        if 1 <= val <= 10:
            return val

    return None


def count_combos_in_edited_text(text: str) -> int:
    """
    Counts the number of combos present in user's edited moves text.
    """
    if not text:
        return 4
    matches = re.findall(r"(?:^|\n)\s*(?:\[?\d+\s*세트\]?|\d+\s*번\s*(?:콤보|세트)?|콤보\s*\d+)", text)
    count = len(matches)
    if 1 <= count <= 10:
        return count
    return 4


def extract_text_from_file(file_path: str) -> str:
    """
    Extracts plain text from .txt, .md, .csv, .json, or .docx files
    using standard libraries so it works reliably inside frozen app bundles.
    """
    if not file_path or not os.path.exists(file_path):
        return ""

    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == ".docx":
            with zipfile.ZipFile(file_path) as zf:
                xml_content = zf.read("word/document.xml")
            tree = ET.fromstring(xml_content)
            paragraphs = []
            for p in tree.iter():
                if p.tag.endswith("}p"):
                    texts = [t.text for t in p.iter() if t.tag.endswith("}t") and t.text]
                    if texts:
                        paragraphs.append("".join(texts))
            return "\n".join(paragraphs).strip()
        else:
            for enc in ("utf-8", "utf-8-sig", "cp949", "euc-kr"):
                try:
                    with open(file_path, "r", encoding=enc) as f:
                        return f.read().strip()
                except UnicodeDecodeError:
                    continue
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read().strip()
    except Exception as e:
        return f"[파일 읽기 오류: {str(e)}]"


def fetch_text_from_url(url: str) -> str:
    """
    Fetches text content from a Google Docs link, Google Sheets link,
    Google Drive shared file link, or general web URL.
    """
    url = (url or "").strip()
    if not url:
        return ""

    download_url = url
    is_binary_doc = False

    # 1. Google Docs: https://docs.google.com/document/d/{ID}/...
    doc_match = re.search(r"docs\.google\.com/document/d/([a-zA-Z0-9_-]+)", url)
    if doc_match:
        doc_id = doc_match.group(1)
        download_url = f"https://docs.google.com/document/d/{doc_id}/export?format=txt"

    # 2. Google Sheets: https://docs.google.com/spreadsheets/d/{ID}/...
    sheet_match = re.search(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if sheet_match:
        sheet_id = sheet_match.group(1)
        download_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"

    # 3. Google Drive file: https://drive.google.com/file/d/{ID}/... or ?id={ID}
    drive_match = re.search(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)", url)
    if not drive_match:
        drive_match = re.search(r"drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)", url)
    if drive_match:
        file_id = drive_match.group(1)
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        is_binary_doc = True

    try:
        ctx = ssl.create_default_context()
        try:
            import certifi
            ctx.load_verify_locations(certifi.where())
        except Exception:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(
            download_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }
        )
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            raw_bytes = resp.read()
            content_type = resp.headers.get("Content-Type", "").lower()

        # Check if downloaded bytes are a ZIP (.docx)
        if raw_bytes[:4] == b"PK\x03\x04":
            with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
                tmp.write(raw_bytes)
                tmp_path = tmp.name
            try:
                return extract_text_from_file(tmp_path)
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

        # Decode text
        decoded = ""
        for enc in ("utf-8", "utf-8-sig", "cp949", "euc-kr"):
            try:
                decoded = raw_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if not decoded:
            decoded = raw_bytes.decode("utf-8", errors="ignore")

        # If HTML page, strip tags cleanly
        if "<html" in decoded.lower() or "<!doctype html" in decoded.lower() or "text/html" in content_type:
            decoded = re.sub(r"<script[\s\S]*?</script>", " ", decoded, flags=re.IGNORECASE)
            decoded = re.sub(r"<style[\s\S]*?</style>", " ", decoded, flags=re.IGNORECASE)
            decoded = re.sub(r"<[^>]+>", "\n", decoded)
            decoded = re.sub(r"\n\s*\n+", "\n", decoded)

        return decoded.strip()
    except Exception as e:
        return f"[링크 불러오기 오류: {str(e)} (구글 드라이브/문서의 공유 설정이 '링크가 있는 모든 사용자에게 공개'인지 확인해 주세요)]"


class AIGenerator:
    def __init__(self, api_key: str = ""):
        self.env_config = load_gemini_env()
        effective_key = api_key.strip() if api_key else self.env_config.get("GEMINI_API_KEY", "")
        self.model = self.env_config.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
        self.base_url = self.env_config.get(
            "GEMINI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        self.client = (
            OpenAI(api_key=effective_key, base_url=self.base_url)
            if effective_key else None
        )

    def _ensure_client(self) -> bool:
        if self.client:
            return True
        self.env_config = load_gemini_env()
        key = self.env_config.get("GEMINI_API_KEY", "")
        if key:
            self.client = OpenAI(api_key=key, base_url=self.base_url)
            return True
        return False

    def set_api_key(self, api_key: str):
        api_key = (api_key or "").strip()
        if api_key:
            save_gemini_api_key(api_key, self.model)
            self.client = OpenAI(api_key=api_key, base_url=self.base_url)

    def test_connection(self) -> tuple:
        """Tests if the configured Gemini API key and model respond properly."""
        try:
            res = self._call_llm("Say OK", "OK", max_tokens=10, temperature=0.1)
            return True, f"연결 성공! (모델: {self.model}, 응답: {res[:20]})"
        except Exception as e:
            return False, f"연결 실패: {str(e)}"

    def _call_llm(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 1600,
        temperature: float = 0.55,
        response_format: Optional[dict] = None
    ) -> str:
        if not self._ensure_client():
            raise RuntimeError("Gemini API 키가 설정되지 않았습니다. 상단 [⚙️ AI·수련자료 통합 설정]에서 API 키를 입력해 주세요.")

        models_to_try = [
            self.model,
            "gemini-3.1-flash-lite",
            "gemini-3.1-flash-lite-preview",
            "gemini-2.5-flash-lite",
        ]
        seen = []
        unique_models = [m for m in models_to_try if not (m in seen or seen.append(m))]

        last_err = None
        for m in unique_models:
            try:
                kwargs = {
                    "model": m,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if response_format:
                    kwargs["response_format"] = response_format

                response = self.client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content
                if content:
                    return content.strip()
            except Exception as e:
                # 만약 response_format을 지원하지 않는 에러라면 없이 재시도
                if response_format:
                    try:
                        kwargs.pop("response_format", None)
                        response = self.client.chat.completions.create(**kwargs)
                        content = response.choices[0].message.content
                        if content:
                            return content.strip()
                    except Exception as e2:
                        last_err = e2
                        continue
                last_err = e
                continue

        raise RuntimeError(f"AI 호출 오류: {str(last_err)}")

    @staticmethod
    def _get_easy_conversational_english_guide(lang_mode: str) -> str:
        """
        Returns instructions for natural, easy, everyday conversational coaching English
        used in real gym/dojo workouts (avoiding textbook/stiff vocabulary).
        """
        common_vocab_guide = """[생생하고 쉬운 현장 생활/운동 영어 지침 - 매우 중요!]
- 딱딱한 교과서식 영어나 어려운 단어(Execute, Perform, Subsequent, Maintain, Recuperate 등)는 절대 쓰지 마세요!
- 실제 체육관 현장에서 원어민 코치가 아이들·수련생들과 호흡하며 일상적으로 자주 쓰는 **쉽고 직관적인 생활형·대화형 코칭 영어**를 사용하세요.
- 동작과 횟수를 수련생이 귀로 듣자마자 바로 몸이 반응할 수 있게 짧고 리듬감 있게 말하세요:
  • 팔굽혀펴기 2회 ➔ "Two pushups! Down and up!" 또는 "Two pushups, get right back up!"
  • 빠른 발차기 5회 ➔ "Five fast kicks! Kick, kick, kick!" 또는 "Five quick kicks, let's go!"
  • 버피 2회 ➔ "Two burpees! Jump up high!"
  • 스쿼트 점프 3회(쪼그려 점프) ➔ "Three squat jumps! Jump high!"
  • 무릎 점프 2회 ➔ "Two high knee jumps! Knees up!"
  • 나래차기 ➔ "Double kicks! Fast feet!"
  • 전방 회전낙법 후 신속히 일어나기 ➔ "Front roll breakfall, stand up quick!" 또는 "Roll forward and get right up!"
  • 후방 회전낙법 후 일어나기 ➔ "Back roll breakfall, stand up fast!"
  • 앞발 컷트 후 상단 발차기 ➔ "Front foot cut, then high kick! Nice!"
  • 백스텝 후 뒤차기 ➔ "Step back and back kick! Let's go!"
  • 자연스러운 연결/격려 추임새: "Let's go!", "Keep moving!", "Nice and fast!", "Don't stop!", "You got this!\""""

        mode_specific = {
            "kr": (
                "한국어 전용 모드입니다. 영어 없이 힘차고 명확한 한국어 사범 동작 지시로만 작성하세요.\n"
                "예시: '팔굽혀펴기 2회 후 빠른 발차기 5회, 버피 2회! 신속하게 다음 동작으로 연결!'"
            ),
            "mix_kids": (
                "한국어 동작 설명 + 쉽고 명확한 현장 생활 영어 동작 구령(1:1 매칭) 모드입니다.\n"
                "반드시 '한국어 동작 설명! - 쉬운 현장 영어 동작 구령!' 형식으로 작성하세요.\n"
                "예시: '팔굽혀펴기 2회 후 빠른 발차기 5회와 버피 2회! - Two pushups! Five fast kicks! Two burpees!'"
            ),
            "dual_step": (
                "한국어 동작 요약 + 자연스러운 코칭 영어 연결 모드입니다.\n"
                "반드시 '한국어 동작 요약! - 대화형 코칭 영어!' 형식으로 작성하세요.\n"
                "예시: '팔굽혀펴기 2회 후 빠른 발차기 5연타, 버피 2회 연결! - Down for two pushups, up fast for five quick kicks, then two burpees!'"
            ),
            "en_advanced": (
                "100% 원어민 코치의 자연스러운 실전 영어(Full English) 모드입니다. 한글 없이 영어로만 작성하세요.\n"
                "예시: 'Give me two pushups, jump up fast for five quick kicks, and finish with two burpees!'"
            ),
        }.get(lang_mode, "")

        return (
            f"{common_vocab_guide}\n\n[선택된 구령 언어 모드 ({lang_mode})]:\n{mode_specific}\n\n"
            "[🚨 조기 출발(오발) 방지 - 시작/독려 구령 절대 금지!]:\n"
            "수련생들은 사전 음성 지시를 듣고 난 후, 시스템의 [카운트다운: 준비 3, 2, 1]과 [시작 휘슬(삐익~)] 신호음에 맞춰 정확히 움직여야 합니다.\n"
            "따라서 음성 구령(speech) 어디에도 'Let's go', 'Keep moving', 'Move', 'Go go go', 'Go', 'Don't stop', 'Start', '출발', '시작', '가자' 등 행동 개시나 출발을 재촉하는 단어를 일절 포함하지 마세요!\n"
            "오직 수행할 동작과 기술(예: 'Two burpees, jump up fast for three quick kicks!')만을 명확히 지시하세요."
        )

    def generate_circuit_routine(
        self,
        user_prompt: str,
        lang_mode: str = "mix_kids",
        mode_type: str = "cycle",
        document_text: str = ""
    ) -> dict:
        """
        Generates an instant customizable circuit template (theme_title, intro_text, formatted_moves)
        from user requirements, uploaded file, Google Drive link, or shared common settings.
        """
        common_cfg = load_common_settings()
        common_info = common_cfg.get("common_info", "").strip()
        english_guide = self._get_easy_conversational_english_guide(lang_mode)

        req_count = extract_requested_circuit_combo_count(user_prompt)
        target_count = req_count if req_count is not None else 4

        combo_examples = []
        for c_i in range(1, target_count + 1):
            combo_examples.append(f"""    {{
      "speech": "{c_i}번 콤보 실제 음성 구령 텍스트 (체력운동 + 발차기 조합)",
      "tip": "사범님 참고용 상세 지도 팁 (➔ 화살표로 체력요소별 코칭 포인트와 연결 순서 명시)"
    }}""")
        combo_examples_str = ",\n".join(combo_examples)

        system_prompt = f"""당신은 무도·체력 체육관의 수석 사범이자 현장 코칭 대본 전문가입니다.
사범님이 입력한 운동 요구사항이나 계획표 내용을 바탕으로, 사범님이 바로 확인하고 입맛대로 수정할 수 있는 [즉석 서킷 인터벌 대본 템플릿]을 JSON으로 생성하세요.

[필수 준수 현장 코칭 규칙]
1. '도장'이라는 단어는 제목, 사전 설명(intro_text), 구령 어디에도 절대 사용하지 마세요.
2. '기립'이라는 한자어는 절대 쓰지 마세요. 대신 '신속히 일어나서', '빠르게 일어나', '신속하게 다음 동작 연결'로 표현하세요.
3. 반말은 절대 금지하며, 정중하고 절도 있는 사범님의 지도 존댓말("~하세요", "~해 주세요")을 사용하세요.
4. 사전 설명 방송(intro_text) - [첫 문장 고정 절대 금지 및 맞춤형 도입부 생성]:
   - **첫 문장 획일화 절대 금지**: 모든 훈련에서 기계적으로 "지금부터 실전 서킷 인터벌 훈련을 시작합니다!"라고 시작하지 마세요!
   - 사범님이 요청한 훈련 종목이나 핵심 운동(예: 플랭크, 코어, 인터벌, 버피, 스피드 피치, 낙법, 실전 겨루기 등)에 맞춰 **첫 문장부터 다채롭고 생동감 넘치게 맞춤형으로 작성**하세요:
     * 플랭크/복근/코어/버티기 중심 요구 시 ➔ "지금부터 단단한 코어와 신체 밸런스를 잡는 코어 집중 훈련을 시작합니다!", "단단한 중심과 흔들림 없는 균형감각을 기르는 코어 강화 트레이닝 시간입니다!"
     * 스피드/인터벌/고속 발놀림 요구 시 ➔ "지금부터 한계 스피드를 돌파하는 고강도 인터벌 트레이닝을 시작합니다!", "초고속 스텝과 번개 같은 연타 스피드를 극대화하는 시간입니다!"
     * 순발력/파워/점프 요구 시 ➔ "지금부터 순간적인 하체 폭발력과 타격 파워를 폭발시키는 순발력 훈련을 시작합니다!"
     * 민첩성/버피/방향전환/낙법 요구 시 ➔ "지금부터 신속한 자세 전환과 위기 대처 신체 협응력을 기르는 실전 연계 훈련을 시작합니다!"
     * 실전 겨루기/전술/스파링 요구 시 ➔ "지금부터 실전 대련 감각과 겨루기 득점 콤보를 완성하는 시간입니다!"
     * 복합 체력/서킷 요구 시 ➔ "지금부터 전신 근력과 심폐지구력을 동시에 끌어올리는 복합 서킷 트레이닝을 시작합니다!"
   - 이어지는 본문에서도 감지된 핵심 동작들(플랭크, 버피, 발차기 등)과 그에 따른 훈련 효과를 자연스럽고 당당한 사범님 존댓말로 설명하며, "지시하는 구령에 맞춰 끝까지 빠른 템포로 집중하세요! 모두 준비해 주세요!"처럼 마무리하세요.
   - 사전 설명에 '한국어', '원어민', '영어' 같은 언어 메타 단어는 절대 넣지 마세요.
5. {english_guide}
6. [스포츠 과학 표준 기반 체력 요소 분류 및 지능적 융합 원칙]
   - 서킷 인터벌 훈련은 '기능성 체력 운동 + 실전 발차기 기술'의 결합이며, 아래 스포츠 과학 표준 3대 체력 요소를 엄격히 구분하여 적용하세요:
     ① **순발력 (Explosive Power - 순간적인 최대 폭발력)**:
        * 본질: 짧은 순간에 최대 힘을 폭발시키는 플라이오메트릭 운동
        * 표준 종목: 스쿼트 점프(Squat Jump), 무릎 당겨 점프/터크 점프(Tuck Jump), 점핑 런지(Jumping Lunge), 폭발적 팔굽혀펴기/박수 푸시업(Explosive Pushup), 제자리 멀리뛰기 등
        * 발차기 연계: 공중 폭발력을 요하는 점프 뒤차기, 점프 앞차기, 뛰어 찍기 등 고파워 타격
     ② **민첩성 (Agility - 전신 자세 전환 및 방향 전환 협응력)**:
        * 본질: 바닥과 기립 사이의 레벨 체인지(Level Change) 및 신속한 방향·각도 전환, 회전 후 중심 복원
        * 표준 종목: 버피테스트(Burpee - 바닥에 엎드렸다 순식간에 일어나는 레벨 체인지), 앞구르기/회전 낙법(Forward Roll), 사이드 스텝/셔틀 스텝(Side Step), 플랭크 투 스쿼트, 4방향 코너 터치 등
        * 발차기 연계: 무게중심과 각도를 빠르게 전환하는 앉아 뒤돌아차기, 나래차기(좌우 연속 교차), 턴 차기
     ③ **스피드 (Speed / Quickness - 초고속 발놀림 및 동작 빈도)**:
        * 본질: 최단 시간에 사지와 발놀림을 최고 빈도(High Frequency)로 움직이는 능력
        * 표준 종목: 마운틴 클라이머(Mountain Climber - 빠른 다리 교차), 앞으로 숙여 제자리 빠른 발구르기(Foot Fire/Flutter Steps), 제자리 고속 피치/하이니(High Knees), 점핑잭(Jumping Jack) 등
        * 발차기 연계: 빠른 발차기 3~5연타, 초고속 연속 타격

   - [스마트 양방향 인지 및 테마/설명(intro_text) 자동 배치 규칙]:
     * **방향 1 (요청 목적 ➔ 종목 지능적 배치)**:
       - 사범님이 "순발력 훈련" 요구 시: 스쿼트 점프, 터크 점프 등 [순발력 표준 종목] 위주로 배치.
       - 사범님이 "민첩성 훈련" 요구 시: 버피테스트, 앞구르기, 사이드 스텝 등 [민첩성 표준 종목] 위주로 배치.
       - 사범님이 "스피드 훈련" 요구 시: 마운틴 클라이머, 앞으로 숙여 발구르기, 빠른 피치 등 [스피드 표준 종목] 위주로 배치.
       - 사범님이 "서킷/복합 훈련" 요구 시: 1번 순발력(스쿼트점프) ➔ 2번 민첩성(버피) ➔ 3번 스피드(마운틴클라이머/발구르기) ➔ 4번 복합 파워로 체계적 순환 배치.
     * **방향 2 (입력 종목 ➔ 훈련 목적 역추적 및 테마/설명 자동 최적화)**:
       - 사범님이 구체적으로 "버피", "앞구르기", "사이드스텝"을 입력창에 넣으면 ➔ AI가 '전신 레벨 전환을 통한 민첩성(Agility) 훈련'임을 스스로 파악하여 테마 제목과 사전 설명(intro_text)에 "전신 민첩성과 신속한 자세 전환 능력 강화"를 명시하세요.
       - 사범님이 "스쿼트 점프", "터크 점프" 등을 넣으면 ➔ '순간적인 폭발력과 순발력(Power) 훈련'임을 스스로 파악하여 "순간적인 하체 폭발력과 순발력 강화"를 명시하세요.
       - 사범님이 "마운틴 클라이머", "앞으로 숙여 발구르기", "빠른 피치", "빠른 발차기" 등을 넣으면 ➔ '초고속 발놀림과 스피드(Speed) 훈련'임을 파악하여 "초고속 스텝과 연타 스피드 극대화"를 명시하세요.
       - 사범님이 "플랭크", "코어" 등을 넣으면 ➔ '단단한 중심과 신체 균형을 잡는 코어 안정성 훈련'임을 파악하여 "단단한 코어와 밸런스 극대화"를 명시하세요.
       - 여러 종목이 섞여 있으면 ➔ "순발력과 민첩성, 스피드를 완성하는 실전 복합 서킷"으로 스마트하게 설명하세요.
     * **지도 팁(tip)**:
       - 해당 체력 요소의 핵심 코칭 포인트(예: 순발력=착지 반동과 점프 폭발력, 민첩성=엎드렸다 신속히 일어나기/중심 제어, 스피드=발놀림의 최고 속도 유지, 코어=복부 긴장 유지와 척추 정렬)를 화살표(➔)로 명시하세요.
7. [사범님 주문 콤보 개수 엄격 준수 - 정확히 총 {target_count}개 콤보]:
   - 사범님의 요청({user_prompt})에 명시된 콤보 개수에 따라 **반드시 정확히 총 {target_count}개의 세트별 콤보(1번 콤보부터 {target_count}번 콤보까지)**를 완성도 높게 구성하세요.
   - 절대로 임의로 콤보를 추가하거나 4개로 강제하지 마세요. combos 배열 길이는 반드시 정확히 {target_count}개여야 합니다.
   - 모든 콤보의 speech와 tip은 절대로 빈칸 없이 100% 충실히 작성하세요.
8. 특수기호(&, · 등)는 읽을 때 어색하므로 제목과 구령에 절대 쓰지 마세요.
9. [조기 출발 방지 - 시작/독려 구령 절대 금지]: speech 내부에는 절대로 'Let's go', 'Keep moving', 'Move', 'Go go go', 'Go', 'Don't stop', '출발', '시작', '가자' 등 행동 개시나 출발을 재촉하는 단어를 일절 넣지 마세요! 수련생들은 설명 후 이어지는 [카운트다운과 시작 휘슬 신호음]에 맞춰 움직여야 하므로, 오직 수행할 동작과 기술만을 객관적으로 명시하세요.

- [JSON 문법 주의]: 모든 문자열 값(value) 내부에는 절대로 큰따옴표(")를 중복 사용하지 마세요! 강조나 영어 구령을 적을 때도 큰따옴표 대신 작은따옴표(')를 쓰거나 따옴표 없이 자연스럽게 작성하세요.

[반드시 아래 JSON 포맷으로만 응답하세요]
{{
  "theme_title": "입력 종목의 체력 요소에 맞춘 테마 제목 (예: 하체 폭발력과 순발력 강화 서킷, 단단한 코어와 밸런스 강화 루틴 등)",
  "intro_text": "훈련 종목의 특성에 맞춘 생동감 넘치는 사전 설명 방송 (예: 지금부터 강력한 코어와 신체 밸런스를 다지는 집중 훈련을 시작합니다! 이번 훈련은...)",
  "combos": [
{combo_examples_str}
  ]
}}"""

        user_msg = f"[사범님 운동 요구사항]\n{user_prompt.strip() if user_prompt else '제공된 수련계획표 기반 서킷 구성'}\n"
        if document_text:
            user_msg += f"\n[참고 수련계획표/링크 문서 내용]\n{document_text[:4000]}\n"
        elif common_info:
            user_msg += f"\n[공통 설정 수련계획표/기본 정보]\n{common_info[:3000]}\n"

        raw_resp = self._call_llm(
            system_prompt,
            user_msg,
            max_tokens=1600,
            temperature=0.45,
            response_format={"type": "json_object"}
        )
        return self._parse_circuit_json_response(raw_resp, expected_count=target_count)

    def refine_edited_circuit_routine(
        self,
        edited_moves_text: str,
        current_intro_text: str = "",
        user_prompt: str = "",
        lang_mode: str = "mix_kids",
        current_theme_title: str = "",
        mode_type: str = "cycle"
    ) -> dict:
        """
        Takes the template text that the user edited in Korean (in txt_circuit_moves),
        preserves the user's exact Korean exercise choices and counts, and regenerates
        matching easy conversational coaching English cues, intro_text, and coaching tips!
        """
        english_guide = self._get_easy_conversational_english_guide(lang_mode)

        # 사범님이 편집창에 작성한 실제 콤보 개수를 우선 감지, 또는 사용자 프롬프트에서 감지
        detected_count = count_combos_in_edited_text(edited_moves_text)
        req_count = extract_requested_circuit_combo_count(user_prompt)
        target_count = req_count if req_count is not None else detected_count

        combo_examples = []
        for c_i in range(1, target_count + 1):
            combo_examples.append(f"""    {{
      "speech": "{c_i}번 콤보 실제 음성 구령 텍스트 (한국어 동작! - 쉬운 현장 영어 구령!)",
      "tip": "수정된 동작에 맞춘 사범님 참고용 상세 지도 팁"
    }}""")
        combo_examples_str = ",\n".join(combo_examples)

        system_prompt = f"""당신은 무도·체력 체육관의 수석 사범이자 한/영 코칭 대본 전문가입니다.
사범님이 대본 편집창에서 [한국어 동작이나 횟수]를 직접 수정했습니다.
사범님이 수정한 각 콤보의 **한국어 동작 내용과 횟수, 구성을 100% 그대로 최우선 기준으로 삼아서**,
그에 딱 맞는 **쉽고 자연스러운 현장 생활/운동 영어 구령**과 **사범 지도 팁**, 그리고 전체 동작을 아우르는 **사전 설명 방송(intro_text)**과 **테마 제목(theme_title)**을 다시 맞춰주세요!

[핵심 규칙 - 절대 준수!]
1. 사범님이 수정한 각 세트의 한국어 동작과 횟수를 임의로 다른 운동으로 바꾸지 마세요! 사범님이 적은 한국어 동작을 그대로 살리면서 자연스럽게 다듬고, 뒷부분의 영어 구령(`- 영어 구령!`)과 아래 줄의 `➔ [지도 팁]`을 그 한국어 동작에 1:1로 정확히 일치시켜 다시 작성하세요.
2. [콤보 개수 엄격 유지 - 총 {target_count}개 콤보]:
   - 사범님이 편집창에 작성한 콤보 개수(총 {target_count}개)를 100% 동일하게 유지하세요!
   - 절대로 임의로 콤보 개수를 4개로 강제하거나 늘리지 말고, 정확히 {target_count}개의 콤보(1번 콤보부터 {target_count}번 콤보까지)만 combos 배열에 반환하세요.
3. '도장'과 '기립' 단어는 절대 쓰지 마세요 ('기립' 대신 '신속히 일어나서', '빠르게 일어나' 사용).
4. [JSON 문법 주의]: 값(value) 내부에는 절대로 큰따옴표(")를 중복 사용하지 마세요! 강조나 영어가 필요할 때는 작은따옴표(')를 쓰거나 따옴표 없이 자연스럽게 작성하세요.
5. {english_guide}
6. [스포츠 과학 체력 요소 역추적 및 사전 설명(intro_text) 첫 문장 맞춤형 다양화]:
   사범님이 수정한 대본에 포함된 운동 종목을 분석하여 테마 제목과 사전 설명(intro_text)의 **첫 문장부터 맞춤형으로 다채롭게** 작성하세요 (매번 '지금부터 실전 서킷 인터벌 훈련을 시작합니다'로 획일화 절대 금지!):
   - 플랭크/코어/복근/버티기 종목 포함 시 ➔ "지금부터 강력한 코어 안정성과 밸런스를 다지는 집중 훈련을 시작합니다!"
   - 버피/앞구르기/사이드스텝 포함 시 ➔ "지금부터 전신 민첩성과 신속한 자세 전환을 기르는 실전 연계 훈련을 시작합니다!"
   - 스쿼트점프/터크점프/점핑런지 포함 시 ➔ "지금부터 순간적인 하체 폭발력과 타격 파워를 기르는 순발력 훈련을 시작합니다!"
   - 마운틴클라이머/제자리 발구르기/빠른 피치 포함 시 ➔ "지금부터 한계 스피드를 돌파하는 초고속 인터벌 트레이닝을 시작합니다!"
   - 혼합 시 ➔ "지금부터 다양한 체력 요소와 실전 발차기를 결합한 맞춤형 트레이닝을 시작합니다!"
7. [조기 출발 방지]: speech 내부에는 절대로 'Let's go', 'Keep moving', 'Move', 'Go', 'Don't stop', '출발', '시작', '가자' 등 행동 개시 단어를 일절 넣지 마세요! 신호음 전에 선수들이 미리 움직이는 오발을 막아야 합니다.

[반드시 아래 JSON 포맷으로만 응답하세요]
{{
  "theme_title": "수정된 운동의 체력 요소에 맞춘 테마 제목 (예: 하체 폭발력과 전신 민첩성 복합 서킷, 단단한 코어와 밸런스 루틴 등)",
  "intro_text": "수정된 운동 종목의 특성에 맞춘 생동감 넘치는 사전 설명 방송 (예: 지금부터 강력한 코어와 신체 밸런스를 위한 플랭크 집중 훈련을 시작합니다! 이번 훈련은...)",
  "combos": [
{combo_examples_str}
  ]
}}"""

        user_msg = (
            f"[사범님이 직접 수정한 대본 템플릿 내용]\n{edited_moves_text.strip()}\n\n"
            f"[추가 요구사항 메모]: {user_prompt.strip() if user_prompt else '없음 (위 수정된 대본의 한글 동작 기준으로 영어와 설명 자동 맞춤)'}\n"
        )
        raw_resp = self._call_llm(
            system_prompt,
            user_msg,
            max_tokens=1600,
            temperature=0.4,
            response_format={"type": "json_object"}
        )
        return self._parse_circuit_json_response(raw_resp, expected_count=target_count)

    @staticmethod
    def robust_json_loads(raw_resp: str) -> dict:
        """
        Robust JSON parser that repairs malformed LLM responses
        (unescaped inner quotes, trailing commas, missing commas, control characters, etc.)
        and falls back to regex-based key-value extraction if strict parsing fails.
        """
        if not raw_resp:
            return {}

        cleaned = re.sub(r"^```(?:json)?\s*", "", raw_resp.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip())
        s_idx = cleaned.find("{")
        e_idx = cleaned.rfind("}")
        if s_idx != -1 and e_idx != -1 and e_idx > s_idx:
            cleaned = cleaned[s_idx:e_idx + 1]

        # 1차 시도: 표준 json.loads (strict=False)
        try:
            return json.loads(cleaned, strict=False)
        except Exception:
            pass

        # 2차 시도: 일반적인 문법 결함 보정
        try:
            fixed = cleaned
            # 후행 쉼표 제거 (, } 또는 , ])
            fixed = re.sub(r",\s*([\}\]])", r"\1", fixed)
            # 줄바꿈 직후 쉼표 누락 보정: "value"\n"key": -> "value",\n"key":
            fixed = re.sub(r'("\s*)\n(\s*"[a-zA-Z0-9_]+"\s*:)', r'\1,\n\2', fixed)
            # 객체 사이 쉼표 누락: }\n{ -> },\n{
            fixed = re.sub(r'(\}\s*)\n(\s*\{)', r'\1,\n\2', fixed)
            return json.loads(fixed, strict=False)
        except Exception:
            pass

        # 3차 시도: 정규식 기반 키-값 추출 (Unescaped inner quotes 등 치명적 문법 파손 완벽 대응)
        extracted = {}

        # 3-1. theme_title
        m_theme = re.search(r'"theme_title"\s*:\s*"([^"\n\r]*)', cleaned)
        if m_theme:
            extracted["theme_title"] = m_theme.group(1).strip()

        # 3-2. intro_text / relay_intro
        m_intro = re.search(r'"(?:intro_text|relay_intro)"\s*:\s*"([\s\S]*?)(?=",\s*"\w+"|\s*"\w+"\s*:|\s*\}\s*$)', cleaned)
        if m_intro:
            extracted["intro_text"] = m_intro.group(1).replace('\\"', '"').strip()
            extracted["relay_intro"] = extracted["intro_text"]

        # 3-3. cues / reac_cues / cue_text / relay_cues
        m_cues = re.search(r'"(?:cues|reac_cues|cue_text|relay_cues)"\s*:\s*"([\s\S]*?)(?=",\s*"\w+"|\s*"\w+"\s*:|\s*\}\s*$)', cleaned)
        if m_cues:
            val = m_cues.group(1).replace('\\"', '"').strip()
            extracted["cues"] = val
            extracted["cue_text"] = val
            extracted["relay_cues"] = val
            extracted["reac_cues"] = val

        # 3-4. step_types / combo_steps
        m_steps = re.search(r'"(?:step_types|combo_steps)"\s*:\s*"([\s\S]*?)(?=",\s*"\w+"|\s*"\w+"\s*:|\s*\}\s*$)', cleaned)
        if m_steps:
            val = m_steps.group(1).replace('\\"', '"').strip()
            extracted["step_types"] = val
            extracted["combo_steps"] = val

        # 3-5. kick_types / combo_kicks
        m_kicks = re.search(r'"(?:kick_types|combo_kicks)"\s*:\s*"([\s\S]*?)(?=",\s*"\w+"|\s*"\w+"\s*:|\s*\}\s*$)', cleaned)
        if m_kicks:
            val = m_kicks.group(1).replace('\\"', '"').strip()
            extracted["kick_types"] = val
            extracted["combo_kicks"] = val

        # 3-6. promise_detail & caution_text
        m_prom = re.search(r'"promise_detail"\s*:\s*"([\s\S]*?)(?=",\s*"\w+"|\s*"\w+"\s*:|\s*\}\s*$)', cleaned)
        if m_prom:
            extracted["promise_detail"] = m_prom.group(1).replace('\\"', '"').strip()
        m_caut = re.search(r'"caution_text"\s*:\s*"([\s\S]*?)(?=",\s*"\w+"|\s*"\w+"\s*:|\s*\}\s*$)', cleaned)
        if m_caut:
            extracted["caution_text"] = m_caut.group(1).replace('\\"', '"').strip()

        # 3-7. combos 배열 정규식 추출
        combos = []
        blocks = re.findall(r'\{\s*"speech"\s*:\s*"([\s\S]*?)"\s*,\s*"tip"\s*:\s*"([\s\S]*?)"\s*\}', cleaned)
        if blocks:
            for sp, tp in blocks:
                combos.append({"speech": sp.strip(), "tip": tp.strip()})
        else:
            sp_matches = re.findall(r'"speech"\s*:\s*"([\s\S]*?)(?=",\s*"tip"|\s*"tip"\s*:)', cleaned)
            tp_matches = re.findall(r'"tip"\s*:\s*"([\s\S]*?)(?="\s*\}|\s*\}\s*,|\s*\}\s*\])', cleaned)
            for idx in range(max(len(sp_matches), len(tp_matches))):
                sp = sp_matches[idx].replace('\\"', '"').strip() if idx < len(sp_matches) else ""
                tp = tp_matches[idx].replace('\\"', '"').strip() if idx < len(tp_matches) else ""
                if sp:
                    combos.append({"speech": sp, "tip": tp})

        if combos:
            extracted["combos"] = combos

        return extracted

    @classmethod
    def _parse_circuit_json_response(cls, raw_resp: str, expected_count: Optional[int] = None) -> dict:
        data = cls.robust_json_loads(raw_resp)
        theme_title = data.get("theme_title", "실전 맞춤형 서킷 인터벌 콤보").strip()
        intro_text = data.get("intro_text", "").strip()
        combos = data.get("combos", [])

        # 목표 콤보 개수 결정: expected_count가 지정되면 최우선, 아니면 응답 길이 (최소 1, 없으면 4)
        if expected_count is not None and expected_count >= 1:
            target_n = expected_count
        else:
            target_n = len(combos) if len(combos) >= 1 else 4

        # 풍부한 기본 fallback 리스트
        default_fallbacks = [
            {"speech": "팔굽혀펴기 2회 후 빠른 발차기 5회! - Two pushups, five fast kicks! Go!", "tip": "푸시업 후 신속히 일어나서 빠른발 연결"},
            {"speech": "무릎 올려 제자리 점프 3회 후 앞차기! - High knees three times, front kick!", "tip": "무릎을 가슴까지 높게 당겨 점프 후 앞차기 타격"},
            {"speech": "개구리 점프 3회 후 나래차기와 전방낙법! - Three squat jumps, double kicks and front roll!", "tip": "하체 폭발력 점프 후 연속 발차기와 안전한 낙법"},
            {"speech": "버피 2회 후 뒤차기와 연속 타격! - Two burpees, back kick combo!", "tip": "지치지 않고 전력으로 다음 동작 신속히 연결"},
            {"speech": "스쿼트 점프 3회 후 돌려차기 양쪽! - Three squat jumps, roundhouse kick both sides!", "tip": "점프 폭발력 후 신속한 좌우 몸통 타격"},
            {"speech": "마운틴 클라이머 4회 후 빠른 발차기! - Mountain climbers four times, fast kicks!", "tip": "초고속 다리 피치 후 즉시 일어서서 연속 타격"},
            {"speech": "사이드 스텝 후 옆차기! - Side step, side kick!", "tip": "민첩한 스텝 이동 후 정확한 중심 잡고 타격"},
            {"speech": "터크 점프 2회 후 점프 뒤차기! - Tuck jump twice, jump back kick!", "tip": "높은 탄력 점프 후 공중에서 몸통 회전 타격"}
        ]

        if len(combos) > target_n:
            combos = combos[:target_n]
        else:
            while len(combos) < target_n:
                fallback_idx = len(combos) % len(default_fallbacks)
                combos.append(default_fallbacks[fallback_idx])

        lines = []
        for idx, c in enumerate(combos, 1):
            speech = str(c.get("speech", "")).strip()
            speech = re.sub(r"^\d+\s*번\s*콤보\s*:\s*", "", speech).strip()
            tip = str(c.get("tip", "")).strip()
            lines.append(f"{idx}번 콤보: {speech}\n   ➔ [지도 팁]: {tip}\n")

        formatted_moves = "\n".join(lines).strip()
        return {
            "theme_title": theme_title,
            "intro_text": intro_text,
            "formatted_moves": formatted_moves,
            "moves_text": formatted_moves,
            "combos": combos,
        }

    def generate_draft(
        self,
        user_text: str,
        difficulty_level: str = "3단계",
        document_text: str = "",
        existing_draft: str = ""
    ) -> str:
        """
        Generates or refines a general class TTS script with [딜레이 N초] tags
        and natural conversational coaching English for the main TTS tab.
        """
        common_cfg = load_common_settings()
        common_info = common_cfg.get("common_info", "").strip()

        system_prompt = """당신은 무도·체력 체육관에서 수련생을 지도하는 수석 사범이자 TTS 음성 방송 대본 전문가입니다.
사범님이 입력한 요구사항(또는 수정한 한글 대본, 수련계획표 문서/링크)을 바탕으로, 즉시 스피커로 틀어 수업을 진행할 수 있는 [즉석 TTS 수업 대본 템플릿]을 작성하세요.

[필수 작성 규칙]
1. 인사말이나 부연 설명 없이 오직 실제 스피커로 읽힐 대본과 [딜레이 N초] 태그만 출력하세요.
2. 반말을 절대 쓰지 말고, 정중하고 절도 있는 사범님의 지도 존댓말("~하세요", "~해 주세요")로 통일하세요.
3. '도장'이나 '기립' 같은 어색한 단어는 쓰지 마세요 ('기립' 대신 '신속히 일어나서' 사용).
4. 영어 구령은 교과서적인 어려운 영어가 아니라, 실제 운동 현장에서 원어민 코치가 일상적으로 자주 쓰는 **쉽고 자연스러운 생활/운동 대화형 영어**를 사용하세요:
   - 예: "Two pushups! Down and up!", "Five fast kicks! Let's go!", "Catch your breath! Deep breath!", "Take a break! Shake your legs!", "Good job everyone, keep moving!"
5. 문장이 너무 빠르지 않도록 호흡 구간마다 쉼표(,)를 자연스럽게 넣어주세요.
6. 동작과 동작 사이, 또는 수련생들이 실제로 운동을 수행하는 시간에는 반드시 [딜레이 3초], [딜레이 5초], [딜레이 10초] 형태로 대기 태그를 삽입하세요.
7. 만약 사범님이 기존 대본 초안의 한글 내용을 일부 수정해서 다시 생성을 요청한 경우, 수정된 한글 동작과 횟수를 100% 반영하여 영어 구령과 흐름을 자연스럽게 맞춰주세요."""

        user_message = f"[사범님 요구사항 / 지시사항]:\n{user_text.strip() if user_text else '제공된 내용 기반 대본 작성'}\n"
        if existing_draft.strip():
            user_message += f"\n[사범님이 현재 화면에서 작성/수정한 대본 내용 (이 한글 내용을 기준으로 영어 구령과 대본 완성)]:\n{existing_draft.strip()}\n"
        if document_text.strip():
            user_message += f"\n[첨부된 수련계획표/구글드라이브 문서 내용]:\n{document_text[:4000]}\n"
        elif common_info:
            user_message += f"\n[공통 설정 수련계획표/기본 정보]:\n{common_info[:3000]}\n"

        try:
            return self._call_llm(system_prompt, user_message, max_tokens=1600, temperature=0.55)
        except Exception as e:
            print(traceback.format_exc())
            return f"오류: {str(e)}"

    def generate_or_refine_sparring_tab(
        self,
        tab_mode: str,
        user_prompt: str,
        lang_mode: str = "mix_kids",
        document_text: str = "",
        refine_mode: bool = False,
        current_fields: dict = None
    ) -> dict:
        """
        Universal AI instant-template generator & Korean-to-English refiner for ALL 5 tabs
        of SparringDialog:
        - 'circuit': 기능성 서킷 인터벌 (HIIT)
        - 'relay': 1:1 / 1:2 / 1:3 릴레이 미트
        - 'reaction': 스텝 & 실전 반응
        - 'combo': 스텝 + 콤비네이션 연타
        - 'round': 정규 스파링 라운드
        """
        current_fields = current_fields or {}
        if tab_mode == "circuit":
            moves_text = current_fields.get("moves_text") or current_fields.get("formatted_moves") or ""
            intro_text = current_fields.get("intro_text", "")
            theme_title = current_fields.get("theme_title", "")
            mode_type = current_fields.get("mode_type", "cycle")
            if refine_mode:
                return self.refine_edited_circuit_routine(
                    edited_moves_text=moves_text,
                    current_intro_text=intro_text,
                    user_prompt=user_prompt,
                    lang_mode=lang_mode,
                    current_theme_title=theme_title,
                    mode_type=mode_type,
                )
            else:
                return self.generate_circuit_routine(
                    user_prompt=user_prompt,
                    lang_mode=lang_mode,
                    mode_type=mode_type,
                    document_text=document_text,
                )

        common_cfg = load_common_settings()
        common_info = common_cfg.get("common_info", "").strip()
        english_guide = self._get_easy_conversational_english_guide(lang_mode)

        relay_special_rules = ""
        if tab_mode == "relay":
            fighters = current_fields.get("fighters_count", 2)
            match_label = current_fields.get("match_label", "1:1 (플레이어 1명, 1번 보조자 1명)")
            role_desc = f"{match_label} 릴레이 미트 순환 훈련"

            r_intro = current_fields.get('intro_text') or current_fields.get('relay_intro', '')
            r_cue = current_fields.get('cue_text') or current_fields.get('relay_cues', '')
            current_context = (
                f"[현재 릴레이 인원 모드]: {match_label}\n"
                f"[현재 화면의 훈련 종합 설명]:\n{r_intro}\n\n"
                f"[현재 화면의 플레이어/보조자 지시 기술 대본]:\n{r_cue}\n"
            )

            schema_desc = """{
  "intro_text": "시작 전 플레이어와 보조자들에게 송출할 종합 훈련 설명 및 미트 착용 행동요령 (정중한 사범님 존댓말, '도장'/'기립'/'선수' 단어 절대 금지, '플레이어'와 '보조자' 명칭 사용, 훈련 특성에 맞는 도입부)",
  "cue_text": "플레이어 및 보조자별 기술 구령 (줄바꿈으로 구분, '플레이어: 기술명! - 영어 구령!\\n1번 보조자: 기술명! - 영어 구령!')"
}"""
            relay_special_rules = f"""
[릴레이 미트 훈련 대본(cue_text) 구성 엄격 규칙 - 위반 절대 금지!]
1. 현재 인원 구성: {match_label}
   - **1:1 모드**: 오직 '플레이어'와 '1번 보조자'만 나와야 합니다! (2번 보조자, 3번 보조자 절대 생성 금지)
   - **1:2 모드**: '플레이어', '1번 보조자', '2번 보조자'가 순서대로 나와야 합니다.
   - **1:3 모드**: '플레이어', '1번 보조자', '2번 보조자', '3번 보조자'가 순서대로 나와야 합니다.

2. [양쪽(좌우) 연습 세트 구성 vs 단방향 1세트 구성]:
   - **사범님이 '양쪽', '좌우', '양발'을 요구했거나 수정한 대본에 양쪽 훈련 의도가 있는 경우**:
     * 절대로 단순 복사/중복하지 말고, **1회차는 '오른쪽(우측)', 2회차는 '왼쪽(좌측)'**으로 명확히 구분된 2개 세트로 작성하세요!
     * 1:1 양쪽 훈련 작성 예시:
       플레이어: 방족술 전진 허리 감아 던지기 오른쪽! - Forward hip throw right side!
       1번 보조자: 전진 몸통차기 1회 오른쪽! - Forward body kick right side!
       플레이어: 방족술 전진 허리 감아 던지기 왼쪽! - Forward hip throw left side!
       1번 보조자: 전진 몸통차기 1회 왼쪽! - Forward body kick left side!
   - **사범님이 양쪽/좌우를 명시하지 않은 단방향 훈련인 경우**:
     * **동일 동작 중복 복사 전면 금지**: 1:1이면 플레이어 1줄, 1번 보조자 1줄로 **단 1세트만** 작성하세요! 똑같은 동작을 2번 반복해서 4줄로 늘리지 마세요!
     * 1:1 단방향 훈련 작성 예시:
       플레이어: 방족술 전진 허리 감아 던지기 동작 수행! - Forward hip throw, turn and throw!
       1번 보조자: 전진 몸통차기 1회! - Forward body kick, kick hard!

3. [사범님 지시 횟수 100% 엄격 준수 - 임의 횟수 변경 절대 금지!]:
   - 사범님이 '전진 몸통차기 1회', '몸통차기(한번)', '1회', '단타' 등으로 지시했으면 **반드시 1회/한번**으로 작성하세요.
   - 절대로 임의로 '2회!', '3회!' 등으로 횟수를 부풀리거나 바꾸지 마세요. 사범님이 주문한 그대로 작성하세요.

4. [사범님이 수정한 대본 정제(refine) 시 중복 정제 원칙]:
   - 사범님이 수정한 대본에 똑같은 내용이 2번 반복되어 있고 '양쪽' 요구가 있는 경우 ➔ 첫 번째는 '오른쪽', 두 번째는 '왼쪽' 세트로 명확히 나누어 작성하세요.
   - '양쪽' 요구가 없다면 ➔ 중복된 2번째 반복을 완전히 삭제하고 1세트만 깔끔하게 남기세요.
"""
        elif tab_mode == "reaction":
            schema_desc = """{
  "cues": "쉼표(,)로 구분된 4~6개의 실전 반응 타격 기술 구령 (선택된 언어 모드에 맞춰 한국어 동작 및 쉬운 현장 영어 구령 포함. 예: 백스텝 받아차기 상단! - Step back counter kick!, 전진 몸통 2연타! - Double body kicks!)"
}"""
            reac_c = current_fields.get('cues') or current_fields.get('reac_cues', '')
            current_context = f"[현재 화면의 반응 타격 구령 목록]:\n{reac_c}\n"
            role_desc = "스텝 & 실전 반사 반응 발차기 훈련"
        elif tab_mode == "combo":
            schema_desc = """{
  "step_types": "쉼표(,)로 구분된 4~6개의 세트별 스텝 지시 구령 (예: 제자리 스텝, 앞뒤 스텝, 업다운 스텝, 사이드 스텝, 앞발 발바꿔 스텝)",
  "kick_types": "쉼표(,)로 구분된 3~4개의 집중 공격/발차기 콤비네이션 구령 (선택된 언어 모드에 맞춰 쉬운 현장 영어 구령 포함 가능)"
}"""
            c_steps = current_fields.get('step_types') or current_fields.get('combo_steps', '')
            c_kicks = current_fields.get('kick_types') or current_fields.get('combo_kicks', '')
            current_context = (
                f"[현재 화면의 스텝 목록]:\n{c_steps}\n\n"
                f"[현재 화면의 집중 훈련 공격 기술]:\n{c_kicks}\n"
            )
            role_desc = "스텝 유지 후 신호음에 폭발적인 콤비네이션 연타를 치는 인터벌 훈련"
        else:  # "round"
            schema_desc = """{
  "promise_detail": "라운드 중 집중 수행할 약속 스파링/실전 전술 핵심 동작 요약 (한글 및 쉬운 현장 코칭 영어 구령)",
  "caution_text": "스파링 시작 전 사범님이 안내하는 라운드 전술 목표 및 부상 방지 안전 수칙 방송 멘트 (정중한 존댓말)"
}"""
            p_detail = current_fields.get('promise_detail', '')
            c_text = current_fields.get('caution_text', '')
            current_context = (
                f"[현재 화면의 약속/전술 기술 내용]:\n{p_detail}\n\n"
                f"[현재 화면의 사전 설명 및 안전 주의사항]:\n{c_text}\n"
            )
            role_desc = "정규 스파링 라운드 (자유/섀도우/약속/공수분리 대련) 훈련"

        action_instruction = (
            "사범님이 화면의 입력칸에서 한국어 동작이나 내용을 직접 수정했습니다. 수정된 한국어 내용을 100% 최우선 기준으로 삼아, 그에 맞는 쉽고 자연스러운 현장 생활 영어 구령과 사전 설명 멘트를 다시 맞춰주세요!"
            if refine_mode else
            "사범님이 입력한 운동 요구사항(또는 수련계획표)에 딱 맞는 즉석 훈련 템플릿을 생성하세요."
        )

        system_prompt = f"""당신은 무도·체력 체육관의 수석 사범이자 [{role_desc}] 코칭 대본 전문가입니다.
{action_instruction}

[필수 준수 규칙]
1. '도장', '기립', '출발' 같은 어색한 단어는 절대 쓰지 마세요 ('기립' 대신 '신속히 일어나서' 사용).
2. 'A선수', 'B선수', '1번 선수' 등 '선수'라는 호칭은 절대 쓰지 마세요! 릴레이 훈련에서는 반드시 **'플레이어'**와 **'보조자'** ('1번 보조자', '2번 보조자') 명칭만 사용하세요.
3. 반말 금지! 사범님의 절도 있고 정중한 존댓말("~하세요", "~해 주세요")을 사용하세요.
4. 특수기호(&, · 등)는 사용하지 마세요.
5. [JSON 문법 주의]: 값(value) 내부에는 절대로 큰따옴표(")를 중복 사용하지 마세요! 강조나 영어가 필요할 때는 작은따옴표(')를 쓰거나 따옴표 없이 자연스럽게 작성하세요.
6. {english_guide}
{relay_special_rules}

[반드시 아래 JSON 포맷으로만 응답하세요]
{schema_desc}"""

        user_msg = f"[사범님 요구사항]: {user_prompt.strip() if user_prompt else '아래 내용 기반 자동 완성'}\n\n"
        if refine_mode or not user_prompt.strip():
            user_msg += f"{current_context}\n"
        if document_text.strip():
            user_msg += f"\n[참고 수련계획표/링크 문서]:\n{document_text[:3500]}\n"
        elif common_info:
            user_msg += f"\n[공통 설정 수련계획표]:\n{common_info[:2500]}\n"

        raw_resp = self._call_llm(
            system_prompt,
            user_msg,
            max_tokens=1500,
            temperature=0.45,
            response_format={"type": "json_object"}
        )
        data = self.robust_json_loads(raw_resp)
        data["tab_mode"] = tab_mode

        # 모든 탭 키 양방향 호환 보장
        if "intro_text" in data or "relay_intro" in data:
            val = (data.get("intro_text") or data.get("relay_intro") or "").strip()
            data["intro_text"] = val
            data["relay_intro"] = val
        if "cue_text" in data or "relay_cues" in data:
            val = (data.get("cue_text") or data.get("relay_cues") or "").strip()
            data["cue_text"] = val
            data["relay_cues"] = val
        if "cues" in data or "reac_cues" in data:
            val = (data.get("cues") or data.get("reac_cues") or "").strip()
            data["cues"] = val
            data["reac_cues"] = val
        if "step_types" in data or "combo_steps" in data:
            val = (data.get("step_types") or data.get("combo_steps") or "").strip()
            data["step_types"] = val
            data["combo_steps"] = val
        if "kick_types" in data or "combo_kicks" in data:
            val = (data.get("kick_types") or data.get("combo_kicks") or "").strip()
            data["kick_types"] = val
            data["combo_kicks"] = val

        return data

    def generate_or_refine_warmup_routine(
        self,
        user_prompt: str,
        lang_mode: str = "mix_kids",
        document_text: str = "",
        refine_mode: bool = False,
        existing_movements: list = None
    ) -> list:
        """
        Generates or refines a customizable warmup/stretching movement list for WarmupDialog.
        """
        common_cfg = load_common_settings()
        common_info = common_cfg.get("common_info", "").strip()
        english_guide = self._get_easy_conversational_english_guide(lang_mode)

        system_prompt = f"""당신은 무도·체력 체육관의 수석 사범이자 준비운동·스트레칭·체력 코칭 전문가입니다.
사범님의 요구사항(또는 현재 표에서 수정한 한글 동작 목록)을 바탕으로 준비운동·스트레칭 동작 리스트를 JSON 배열로 생성하세요.

[필수 규칙]
1. 각 동작은 사범님이 현장에서 바로 지도할 수 있도록 자연스러운 한국어 설명(desc_kr)과 **쉽고 자연스러운 현장 생활/운동 영어 설명(desc_en)**을 포함해야 합니다.
2. '도장', '기립' 단어는 절대 쓰지 마세요.
3. {english_guide}
4. 사범님이 기존 표의 한글 동작명(name_kr)이나 한글 설명(desc_kr)을 수정한 뒤 다시 생성(refine_mode)을 요청한 경우, 사범님이 수정한 한글 동작 순서와 구성을 그대로 유지하면서 영어 명칭(name_en)과 한/영 코칭 멘트(desc_kr, desc_en)를 완벽하게 맞춰주세요.

[반드시 아래 JSON 배열 포맷으로만 응답하세요]
[
  {{
    "name_kr": "동작 한글 이름 (예: 목 돌리기 / 스쿼트 점프)",
    "name_en": "쉬운 현장 영어 이름 (예: Neck Circles / Squat Jumps)",
    "desc_kr": "사범님의 자연스러운 한글 동작 지도 멘트 (예: 양손 허리 짚고 목을 천천히 크게 돌려주세요)",
    "desc_en": "쉽고 자연스러운 현장 생활 영어 코칭 멘트 (예: Hands on your hips! Roll your neck nice and slow!)",
    "type": "8beat 또는 hold (구령에 맞춰 움직이면 8beat, 정지 스트레칭이면 hold)",
    "sets": 2,
    "hold_sec": 10
  }}
]"""

        user_msg = f"[사범님 준비운동 요구사항]: {user_prompt.strip() if user_prompt else '아래 동작 목록 기반 완성'}\n"
        if existing_movements:
            user_msg += f"\n[현재 표에 입력/수정된 준비운동 동작 목록 (한글 수정사항 최우선 반영)]:\n{json.dumps(existing_movements, ensure_ascii=False, indent=2)}\n"
        if document_text.strip():
            user_msg += f"\n[참고 수련계획표/링크 문서]:\n{document_text[:3000]}\n"
        elif common_info:
            user_msg += f"\n[공통 설정 수련계획표]:\n{common_info[:2000]}\n"

        raw_resp = self._call_llm(system_prompt, user_msg, max_tokens=1800, temperature=0.45)
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw_resp.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip())
        s_idx, e_idx = cleaned.find("["), cleaned.rfind("]")
        if s_idx != -1 and e_idx != -1:
            cleaned = cleaned[s_idx:e_idx + 1]
        items = json.loads(cleaned)
        result = []
        for idx, it in enumerate(items, 1):
            t_val = it.get("type", "8beat")
            if t_val not in ("8beat", "hold"):
                t_val = "8beat"
            result.append({
                "id": f"ai_warmup_{idx}",
                "enabled": True,
                "name_kr": str(it.get("name_kr", f"동작 {idx}")).strip(),
                "name_en": str(it.get("name_en", f"Exercise {idx}")).strip(),
                "desc_kr": str(it.get("desc_kr", "")).strip(),
                "desc_en": str(it.get("desc_en", "")).strip(),
                "type": t_val,
                "sets": int(it.get("sets", 2) or 2),
                "hold_sec": int(it.get("hold_sec", 10) or 10),
            })
        return result

    @staticmethod
    def detect_target_platform(prompt_text: str) -> str:
        """
        사용자가 1번 탭에서 입력한 텍스트를 분석하여 어떤 플랫폼 창을 열어야 할지 자동 판별합니다.
        반환값: 'circuit' | 'relay' | 'reaction' | 'combo' | 'round' | 'warmup' | 'shuttle' | 'general_tts'
        """
        t = (prompt_text or "").strip().lower()
        if not t:
            return "circuit"
        if any(k in t for k in ["셔틀런", "왕복달리기", "오래달리기", "페이서", "shuttle", "beep test"]):
            return "shuttle"
        if any(k in t for k in ["준비운동", "스트레칭", "체조", "요가", "필라테스", "관절", "몸풀기", "워밍업", "warmup", "stretch"]):
            return "warmup"
        if any(k in t for k in ["릴레이", "암미트", "손미트", "1:1", "1:2", "1:3", "방족술", "선수 교대", "미트 순환"]):
            return "relay"
        if any(k in t for k in ["반응", "받아차기", "랜덤 대기", "반사신경"]):
            return "reaction"
        if any(k in t for k in ["스텝", "콤비네이션 연타", "스텝 유지"]):
            return "combo"
        if any(k in t for k in ["라운드", "자유 대련", "약속 스파링", "섀도우 스파링", "공수 분리", "스파링 라운드", "스파링"]):
            return "round"
        if any(k in t for k in ["서킷", "인터벌", "타바타", "버피", "푸시업", "팔굽혀", "점프", "낙법", "콤보", "세트", "회"]):
            return "circuit"
        return "general_tts"

