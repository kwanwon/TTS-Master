import os
import re
import json
import zipfile
import xml.etree.ElementTree as ET
import traceback
from openai import OpenAI


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

    # Candidate .env locations (CWD, project root, ~/.aimaster_tts/.env)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(os.getcwd(), ".env"),
        os.path.join(base_dir, ".env"),
        os.path.join(os.path.expanduser("~"), ".aimaster_tts", ".env"),
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
                        if k in config and v and not config[k]:
                            config[k] = v
                        elif k in ("GEMINI_MODEL", "GEMINI_BASE_URL") and v:
                            config[k] = v
                        elif k == "GEMINI_API_KEY" and v:
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
    user_dir = os.path.join(os.path.expanduser("~"), ".aimaster_tts")
    os.makedirs(user_dir, exist_ok=True)
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

    def _call_llm(self, system_prompt: str, user_message: str, max_tokens: int = 1500, temperature: float = 0.6) -> str:
        if not self._ensure_client():
            raise RuntimeError("Gemini API 키가 설정되지 않았습니다. (.env 파일을 확인해 주세요)")

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
                response = self.client.chat.completions.create(
                    model=m,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                content = response.choices[0].message.content
                if content:
                    return content.strip()
            except Exception as e:
                last_err = e
                continue

        raise RuntimeError(f"AI 호출 오류: {str(last_err)}")

    def generate_circuit_routine(
        self,
        user_prompt: str,
        lang_mode: str = "mix_kids",
        mode_type: str = "cycle",
        document_text: str = ""
    ) -> dict:
        """
        Generates a complete circuit interval routine (theme_title, intro_text, formatted_moves)
        from a simple one-line user request or an uploaded training plan file.
        """
        lang_instruction = {
            "kr": (
                "한국어 전용 모드입니다. 영어 없이 힘차고 명확한 한국어 사범 구령으로만 작성하세요.\n"
                "예시: '팔굽혀펴기 2회 후 빠른 발차기 5회, 버피 2회! 신속하게 다음 동작으로 연결! 쉼 없이 반복!'"
            ),
            "mix_kids": (
                "한국어 동작 설명 + 본토 실전 영어 액션콜(1:1 직결) 모드입니다.\n"
                "반드시 '한국어 동작 요약! - 영어 1:1 구령!' 형식으로 작성하세요.\n"
                "절대로 영어를 'Three times!'처럼 횟수만 뭉개지 말고, 반드시 횟수+동작명(예: Two pushups! Five fast kicks! Two burpees! Three squat jumps! Front roll breakfall!)으로 1:1 정확히 매칭하세요.\n"
                "예시: '팔굽혀펴기 2회 후 빠른 발차기 5회와 버피 2회! - Two pushups! Five fast kicks! Two burpees!'"
            ),
            "dual_step": (
                "한국어 전술 동작 요약 + 본토 대련 테크닉 영어 구령 모드입니다.\n"
                "반드시 '한국어 동작 요약! - 영어 연결 구령!' 형식으로 작성하세요.\n"
                "예시: '팔굽혀펴기 2회 후 빠른 발차기 5연타, 버피 2회 연결! - Two pushups, five fast kicks, two burpees, non-stop!'"
            ),
            "en_advanced": (
                "100% 미국 본토 실전 도장 코치 영어(Full English) 모드입니다. 한글 없이 영어로만 구령을 작성하세요.\n"
                "예시: 'Two pushups into five fast kicks and two burpees! Quick recovery, keep repeating non-stop!'"
            ),
        }.get(lang_mode, "")

        combo_count_guide = (
            "사용자가 단일 집중 반복을 원하거나 1가지 복합 루틴만 지정했더라도, "
            "1번 콤보에는 사용자가 요청한 동작을 100% 정확히 그대로 배치하고, "
            "2~4번 콤보에는 해당 동작들을 응용하거나 순서를 변형한 실전 콤보를 추가로 구성해 총 4개의 콤보를 작성하세요. "
            "(단, 사용자가 명확히 1번, 2번, 3번 등 세트별 동작을 각각 지정했다면 그 순서대로 작성하세요.)"
        )

        system_prompt = f"""당신은 태권도 및 무도 체육관의 수석 사범이자 실전 서킷 인터벌 훈련 설계 전문가입니다.
사범님이 간단히 입력한 운동 메모나 수련계획표 문서를 바탕으로, 즉시 방송 가능한 [서킷 인터벌 훈련 대본]을 JSON 형식으로 생성하세요.

[필수 준수 현장 코칭 규칙 - 매우 중요!]
1. '도장'이라는 단어는 제목, 사전 설명(intro_text), 구령 어디에도 절대 사용하지 마세요.
2. '기립'이라는 딱딱한 한자어는 절대 쓰지 마세요. 대신 '신속히 일어나서', '빠르게 일어나', '신속하게 다음 동작 연결'로 표현하세요.
3. 반말("스텝 밟아", "마시자" 등)은 절대 금지하며, 정중하고 절도 있는 사범님의 지도 존댓말("~하세요", "~해 주세요")을 사용하세요.
4. 낙법 용어 한/영 정립:
   - 앞으로 구르는 회전낙법 = '전방 회전낙법' (영어: Front roll breakfall)
   - 뒤로 구르는 회전낙법 = '후방 회전낙법' (영어: Back roll breakfall)
   - 옆으로 구르는 낙법 = '측방 회전낙법' (영어: Side roll breakfall)
   - 쪼그려 점프 = '스쿼트 점프' (영어: Squat jumps)
   - 팔굽혀펴기 = '팔굽혀펴기' 또는 '푸시업' (영어: Pushups)
   - 빠른 발차기 = '빠른 발차기' (영어: Fast kicks)
   - 버피 = '버피' (영어: Burpees)
5. 사전 안내 방송(intro_text) 작성 규칙:
   - 단순 단어 나열식 설명은 절대 금지합니다!
   - 실제 사범님이 수련생들 앞에서 오늘 할 운동의 구성과 훈련 목적(왜 이 동작들을 연결하는지)을 귀에 쏙 들어오게 설명하듯 작성하세요.
   - 반드시 다음 흐름을 따르세요:
     "지금부터 실전 서킷 인터벌 훈련을 시작합니다! 이번 훈련은 [사용자가 입력한 핵심 동작들]을 연결하여 [훈련 효과: 예-상하체 근지구력과 폭발적인 순발력 / 실전 대련 감각과 신체 협응력 등]을 기르는 시간입니다. 지시하는 동작에 맞춰 신속하게 다음 동작으로 연결하며 전력으로 반복하세요! 모두 준비해 주세요!"
   - 사전 안내 방송에 '한국어', '원어민', '영어' 같은 언어 설명 단어는 절대 넣지 마세요.
6. 구령 언어 모드 지침 ({lang_mode}):
   {lang_instruction}
7. 콤보 구성 지침:
   {combo_count_guide}
8. 특수기호(&, · 등)는 읽을 때 어색하므로 제목과 구령에 절대 쓰지 말고 '와/과', '그리고', 쉼표(,)로 자연스럽게 연결하세요.

[반드시 아래 JSON 포맷으로만 응답하세요 (마크다운 코드블록 없이 순수 JSON 권장)]
{{
  "theme_title": "훈련 테마 제목 (예: 팔굽혀펴기와 빠른발차기 버피 복합 서킷)",
  "intro_text": "지금부터 실전 서킷 인터벌 훈련을 시작합니다! 이번 훈련은 ...",
  "combos": [
    {{
      "speech": "1번 콤보 실제 음성 구령 텍스트 (1번 콤보: 접두사 제외)",
      "tip": "사범님 참고용 상세 지도 팁 (➔ 화살표로 동작 연결 순서 명시)"
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

        user_msg = f"[사범님 지시사항]\n{user_prompt.strip() if user_prompt else '수련계획표 문서 기반 서킷 루틴 구성'}\n"
        if document_text:
            user_msg += f"\n[첨부된 수련계획표/문서 내용]\n{document_text[:4000]}\n"

        raw_resp = self._call_llm(system_prompt, user_msg, max_tokens=1500, temperature=0.5)

        # Clean JSON block if wrapped in ```json ... ```
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw_resp.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip())
        start_idx = cleaned.find("{")
        end_idx = cleaned.rfind("}")
        if start_idx != -1 and end_idx != -1:
            cleaned = cleaned[start_idx:end_idx + 1]

        data = json.loads(cleaned)
        theme_title = data.get("theme_title", "실전 맞춤형 서킷 인터벌 콤보").strip()
        intro_text = data.get("intro_text", "").strip()
        combos = data.get("combos", [])

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
            "combos": combos,
        }

    def generate_draft(self, user_text: str, difficulty_level: str = "3단계", document_text: str = "") -> str:
        """
        Generates a general class TTS script with [딜레이 N초] tags for the main TTS tab.
        """
        try:
            level_match = re.search(r"(\d+)", str(difficulty_level))
            level = int(level_match.group(1)) if level_match else 3
        except Exception:
            level = 3

        system_prompt = """당신은 무도 체육관(태권도·합기도 등)에서 수련생을 지도하는 수석 사범이자 TTS 음성 방송 대본 전문가입니다.
사범님이 입력한 간단한 지시사항이나 첨부된 수련계획표 문서를 바탕으로, 즉시 스피커로 틀어 수업을 진행할 수 있는 [TTS 전용 훈련 대본]을 작성하세요.

[필수 작성 규칙]
1. 인사말이나 부연 설명 없이 오직 실제 스피커로 읽힐 대본과 [딜레이 N초] 태그만 출력하세요.
2. 반말을 절대 쓰지 말고, 정중하고 절도 있는 사범님의 지도 존댓말("~하세요", "~해 주세요")로 통일하세요.
3. '도장'이나 '기립' 같은 어색한 단어는 쓰지 마세요 ('기립' 대신 '신속히 일어나서' 사용).
4. 문장이 너무 빠르지 않도록 호흡 구간마다 쉼표(,)를 자연스럽게 넣어주세요.
5. 동작과 동작 사이, 또는 수련생들이 실제로 운동을 수행하는 시간에는 반드시 [딜레이 3초], [딜레이 5초], [딜레이 10초] 형태로 대기 태그를 삽입하세요.
6. 영어 구령이 필요한 경우 본토 도장에서 실제로 쓰는 짧고 명확한 구령(예: Two pushups!, Five fast kicks!, Catch your breath!, Take a break!)을 자연스럽게 섞어주세요.

[출력 예시]
자, 지금부터 체력 강화 및 발차기 집중 훈련을 시작합니다! 모두 간격을 벌려 준비해 주세요. [딜레이 3초]
첫 번째 동작은 팔굽혀펴기 2회 후 빠른 발차기 5회입니다! 구령에 맞춰 힘차게 시작합니다, 준비! [딜레이 2초]
Two pushups! Five fast kicks! Go! [딜레이 5초]
갈려~! 호흡을 가다듬고 다리를 가볍게 털어주세요. Catch your breath! [딜레이 5초]"""

        user_message = f"[요청 수준]: {level}단계\n[사범님 지시사항]:\n{user_text}\n"
        if document_text:
            user_message += f"\n[첨부된 수련계획표 문서 내용]:\n{document_text[:4000]}\n"

        try:
            return self._call_llm(system_prompt, user_message, max_tokens=1500, temperature=0.6)
        except Exception as e:
            print(traceback.format_exc())
            return f"오류: {str(e)}"
