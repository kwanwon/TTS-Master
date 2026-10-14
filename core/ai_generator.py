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
                "한국어 전용 모드입니다. 영어 없이 힘차고 명확한 한국어 사범 구령으로만 작성하세요.\n"
                "예시: '팔굽혀펴기 2회 후 빠른 발차기 5회, 버피 2회! 신속하게 다음 동작으로 연결! 쉼 없이 반복!'"
            ),
            "mix_kids": (
                "한국어 동작 설명 + 쉽고 신나는 현장 생활 영어 구령(1:1 매칭) 모드입니다.\n"
                "반드시 '한국어 동작 설명! - 쉬운 현장 영어 구령!' 형식으로 작성하세요.\n"
                "예시: '팔굽혀펴기 2회 후 빠른 발차기 5회와 버피 2회! - Two pushups! Five fast kicks! Two burpees! Let's go!'"
            ),
            "dual_step": (
                "한국어 동작 요약 + 자연스러운 대화형 코칭 영어 연결 모드입니다.\n"
                "반드시 '한국어 동작 요약! - 대화형 코칭 영어!' 형식으로 작성하세요.\n"
                "예시: '팔굽혀펴기 2회 후 빠른 발차기 5연타, 버피 2회 연결! - Down for two pushups, up fast for five quick kicks, then two burpees! Keep moving!'"
            ),
            "en_advanced": (
                "100% 원어민 코치의 자연스러운 대화형 실전 영어(Full English) 모드입니다. 한글 없이 영어로만 작성하세요.\n"
                "예시: 'Give me two pushups, jump up fast for five quick kicks, and finish with two burpees! Keep moving, let's go!'"
            ),
        }.get(lang_mode, "")

        return f"{common_vocab_guide}\n\n[선택된 구령 언어 모드 ({lang_mode})]:\n{mode_specific}"

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

        system_prompt = f"""당신은 무도·체력 체육관의 수석 사범이자 현장 코칭 대본 전문가입니다.
사범님이 입력한 운동 요구사항이나 계획표 내용을 바탕으로, 사범님이 바로 확인하고 입맛대로 수정할 수 있는 [즉석 서킷 인터벌 대본 템플릿]을 JSON으로 생성하세요.

[필수 준수 현장 코칭 규칙]
1. '도장'이라는 단어는 제목, 사전 설명(intro_text), 구령 어디에도 절대 사용하지 마세요.
2. '기립'이라는 한자어는 절대 쓰지 마세요. 대신 '신속히 일어나서', '빠르게 일어나', '신속하게 다음 동작 연결'로 표현하세요.
3. 반말은 절대 금지하며, 정중하고 절도 있는 사범님의 지도 존댓말("~하세요", "~해 주세요")을 사용하세요.
4. 사전 설명 방송(intro_text):
   - 단순 단어 나열 금지! 실제 사범님이 수련생들에게 오늘 할 운동 구성과 훈련 목적을 자연스럽게 설명하듯 작성하세요.
   - 흐름: "지금부터 실전 서킷 인터벌 훈련을 시작합니다! 이번 훈련은 [핵심 동작들]을 연결하여 [훈련 효과]를 기르는 시간입니다. 지시하는 동작에 맞춰 신속하게 다음 동작으로 연결하며 전력으로 반복하세요! 모두 준비해 주세요!"
   - 사전 설명에 '한국어', '원어민', '영어' 같은 언어 메타 단어는 절대 넣지 마세요.
5. {english_guide}
6. [핵심 지침: 기능성 체력·민첩·순발 운동과 무도 기술(발차기)의 지능적 융합]
   - 서킷 인터벌 훈련은 단순 발차기 반복이 아닌 '기능성 체력·민첩·순발 운동 + 실전 발차기 기술'의 고강도 복합 콤보 훈련입니다.
   - (A) 특정 체력 종목이 명시된 경우:
     사범님이 "버피 3회, 나래차기, 앞구르기 1회"처럼 구체적인 피트니스 종목과 횟수를 지정하면 해당 종목과 횟수를 100% 그대로 반영하세요.
   - (B) 훈련 목적이나 포괄적 카테고리가 입력된 경우:
     사범님이 "민첩성을 키우기 위한 훈련", "순발력 운동과 빠른 발차기 3회...", "하체 파워와 점프 뒤차기", "전신 체력 서킷"처럼 훈련 목적이나 추상적 카테고리를 요구한 경우, 절대로 발차기만 나열하지 마세요!
     실내에서 장비 없이 즉시 수행 가능한 최적의 체력·민첩·순발 운동 종목들을 AI가 각 콤보마다 1~2종목씩 지능적으로 엄선하여 발차기와 환상적인 서킷 콤보로 결합하세요.
     * 대표 실내 체력/민첩/순발 운동 풀(Pool):
       - 순발·민첩/플라이오메트릭: 버피테스트(Burpee), 점핑잭(Jumping Jack), 스쿼트 점프(Squat Jump), 사이드 스텝(Side Step), 제자리 빠른 피치(High Knees/Fast Feet), 앞구르기(Forward Roll), 하이점프 등
       - 코어/전신 체력: 마운틴 클라이머(Mountain Climber), 팔굽혀펴기(Pushup), 플랭크 잭(Plank Jack), 베어 크롤 등
     * 콤보 구성 설계 원칙:
       - 1번~4번 콤보마다 체력 운동 종목이 서로 겹치지 않고 다채롭게 순환(Cycle)되도록 배분하세요.
       - 예시:
         * 1번 콤보: 버피 2회 후 신속히 일어나서 빠른 발차기 3회 연결! - Two burpees, jump up fast for three quick kicks!
         * 2번 콤보: 스쿼트 점프 3회 후 착지 즉시 나래차기 연결! - Three squat jumps, double kick right away!
         * 3번 콤보: 마운틴 클라이머 6회 후 빠르게 일어나 들어찍기 양발! - Six mountain climbers, get up for axe kicks both sides!
         * 4번 콤보: 점핑잭 5회 후 앉아 뒤돌아차기 1회 전력 타격! - Five jumping jacks, spin and kick with power!
   - (C) 지도 팁(tip) 작성 요령:
     체력 운동에서 발차기 타격으로 이어지는 신속한 전환 자세와 코칭 포인트를 화살표(➔)로 명확히 가이드하세요.
     (예: "버피 2회 ➔ 신속히 일어나 타격 자세 ➔ 빠른 발차기 3회 ➔ 연속 나래차기 ➔ 전신 스피드 유지")
7. 총 4개의 세트별 콤보를 완성도 높게 구성하세요.
8. 특수기호(&, · 등)는 읽을 때 어색하므로 제목과 구령에 절대 쓰지 마세요.

- [JSON 문법 주의]: 모든 문자열 값(value) 내부에는 절대로 큰따옴표(")를 중복 사용하지 마세요! 강조나 영어 구령을 적을 때도 큰따옴표 대신 작은따옴표(')를 쓰거나 따옴표 없이 자연스럽게 작성하세요.

[반드시 아래 JSON 포맷으로만 응답하세요]
{{
  "theme_title": "훈련 테마 제목 (예: 민첩성 강화 버피와 빠른 발차기 서킷)",
  "intro_text": "지금부터 실전 서킷 인터벌 훈련을 시작합니다! 이번 훈련은 버피와 빠른 발차기 등 체력과 순발력을 연결하여 전신 민첩성을 기르는 시간입니다. 지시하는 동작에 맞춰 신속하게 다음 동작으로 연결하며 전력으로 반복하세요! 모두 준비해 주세요!",
  "combos": [
    {{
      "speech": "1번 콤보 실제 음성 구령 텍스트 (체력운동 + 발차기 조합)",
      "tip": "사범님 참고용 상세 지도 팁 (➔ 화살표로 체력운동부터 발차기까지 동작 연결 순서 명시)"
    }},
    {{
      "speech": "2번 콤보 실제 음성 구령 텍스트",
      "tip": "사범님 참고용 상세 지도 팁"
    }},
    {{
      "speech": "3번 콤보 실제 음성 구령 텍스트",
      "tip": "사범님 참고용 상세 지도 팁"
    }},
    {{
      "speech": "4번 콤보 실제 음성 구령 텍스트",
      "tip": "사범님 참고용 상세 지도 팁"
    }}
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
        return self._parse_circuit_json_response(raw_resp)

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

        system_prompt = f"""당신은 무도·체력 체육관의 수석 사범이자 한/영 코칭 대본 전문가입니다.
사범님이 대본 편집창에서 [한국어 동작이나 횟수]를 직접 수정했습니다.
사범님이 수정한 각 콤보의 **한국어 동작 내용과 횟수, 구성을 100% 그대로 최우선 기준으로 삼아서**,
그에 딱 맞는 **쉽고 자연스러운 현장 생활/운동 영어 구령**과 **사범 지도 팁**, 그리고 전체 동작을 아우르는 **사전 설명 방송(intro_text)**과 **테마 제목(theme_title)**을 다시 맞춰주세요!

[핵심 규칙 - 절대 준수!]
1. 사범님이 수정한 각 세트의 한국어 동작과 횟수를 임의로 다른 운동으로 바꾸지 마세요! 사범님이 적은 한국어 동작을 그대로 살리면서 자연스럽게 다듬고, 뒷부분의 영어 구령(`- 영어 구령!`)과 아래 줄의 `➔ [지도 팁]`을 그 한국어 동작에 1:1로 정확히 일치시켜 다시 작성하세요.
2. [절대 콤보 삭제 금지 - 총 4개 콤보 필수 유지!]:
   사범님이 제공한 콤보가 4개 미만이거나 1개만 있더라도, 절대로 콤보 개수를 1개로 줄이지 말고, 반드시 총 4개의 콤보(1번 콤보, 2번 콤보, 3번 콤보, 4번 콤보)를 모두 포함하여 combos 배열에 4개 아이템을 반환하세요! (사범님이 수정한 콤보는 그대로 살리고, 나머지 번호는 기존 루틴을 유지하거나 연관된 기능성/발차기 운동으로 알차게 채우세요).
3. '도장'과 '기립' 단어는 절대 쓰지 마세요 ('기립' 대신 '신속히 일어나서', '빠르게 일어나' 사용).
4. [JSON 문법 주의]: 값(value) 내부에는 절대로 큰따옴표(")를 중복 사용하지 마세요! 강조나 영어가 필요할 때는 작은따옴표(')를 쓰거나 따옴표 없이 자연스럽게 작성하세요.
5. {english_guide}

[반드시 아래 JSON 포맷으로만 응답하세요]
{{
  "theme_title": "수정된 운동에 맞춘 테마 제목",
  "intro_text": "지금부터 실전 서킷 인터벌 훈련을 시작합니다! 이번 훈련은 [수정된 핵심 동작들]을 연결하여 ...",
  "combos": [
    {{
      "speech": "1번 콤보 실제 음성 구령 텍스트 (한국어 동작! - 쉬운 현장 영어 구령!)",
      "tip": "수정된 동작에 맞춘 사범님 참고용 상세 지도 팁"
    }},
    {{
      "speech": "2번 콤보 실제 음성 구령 텍스트 (한국어 동작! - 쉬운 현장 영어 구령!)",
      "tip": "수정된 동작에 맞춘 사범님 참고용 상세 지도 팁"
    }},
    {{
      "speech": "3번 콤보 실제 음성 구령 텍스트 (한국어 동작! - 쉬운 현장 영어 구령!)",
      "tip": "수정된 동작에 맞춘 사범님 참고용 상세 지도 팁"
    }},
    {{
      "speech": "4번 콤보 실제 음성 구령 텍스트 (한국어 동작! - 쉬운 현장 영어 구령!)",
      "tip": "수정된 동작에 맞춘 사범님 참고용 상세 지도 팁"
    }}
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
        return self._parse_circuit_json_response(raw_resp)

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
    def _parse_circuit_json_response(cls, raw_resp: str) -> dict:
        data = cls.robust_json_loads(raw_resp)
        theme_title = data.get("theme_title", "실전 맞춤형 서킷 인터벌 콤보").strip()
        intro_text = data.get("intro_text", "").strip()
        combos = data.get("combos", [])

        # 안전장치: 콤보가 4개 미만인 경우 기본 서킷 루틴으로 보충하여 항상 4개 세트 유지
        default_fallbacks = [
            {"speech": "팔굽혀펴기 2회 후 빠른 발차기 5회! - Two pushups, five fast kicks! Go!", "tip": "푸시업 후 신속히 일어나서 빠른발 연결"},
            {"speech": "무릎 올려 제자리 점프 3회 후 앞차기! - High knees three times, front kick!", "tip": "무릎을 가슴까지 높게 당겨 점프 후 앞차기 타격"},
            {"speech": "개구리 점프 3회 후 나래차기와 전방낙법! - Three squat jumps, double kicks and front roll!", "tip": "하체 폭발력 점프 후 연속 발차기와 안전한 낙법"},
            {"speech": "버피 2회 후 뒤차기와 연속 타격! - Two burpees, back kick combo!", "tip": "지치지 않고 전력으로 다음 동작 신속히 연결"}
        ]
        while len(combos) < 4:
            combos.append(default_fallbacks[len(combos)])

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

        if tab_mode == "relay":
            schema_desc = """{
  "intro_text": "시작 전 플레이어와 보조자들에게 송출할 종합 훈련 설명 및 미트 착용 행동요령 (정중한 사범님 존댓말, '도장'/'기립'/'선수' 단어 절대 금지, '플레이어'와 '보조자' 명칭 사용)",
  "cue_text": "플레이어 및 보조자별 기술 구령 (줄바꿈으로 구분, '플레이어: 기술명\\n1번 보조자: 기술명' 형식 또는 순환 기술 목록, 선택된 언어 모드에 맞춰 쉬운 현장 영어 구령 포함)"
}"""
            r_intro = current_fields.get('intro_text') or current_fields.get('relay_intro', '')
            r_cue = current_fields.get('cue_text') or current_fields.get('relay_cues', '')
            current_context = (
                f"[현재 화면의 훈련 종합 설명]:\n{r_intro}\n\n"
                f"[현재 화면의 플레이어/보조자 지시 기술 대본]:\n{r_cue}\n"
            )
            role_desc = "1:1 / 1:2 / 1:3 플레이어 및 보조자 다자간 릴레이 미트 순환 훈련"
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

