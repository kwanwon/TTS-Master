import os
import time
import tempfile
import traceback
import re
import numpy as np
from pydub import AudioSegment


class Qwen3Engine:
    TARGET_SAMPLING_RATE = 24000

    def __init__(self, model_size="0.6B"):
        self.model_size = model_size
        self.model = None
        self.device = "cpu"
        self.dtype = None
        self.active_model_type = None  # "Base" or "CustomVoice"

        self.reference_wav = os.path.join("voice_samples", "instructor.wav")
        self.speaker_name = None  # CustomVoice 전용 (예: "Sohee")
        self.last_error = ""
        
        # API 모드 설정
        self.use_api = False
        self.api_key = None

    def _determine_device(self):
        import torch
        # Mac MPS에서 Qwen3-TTS 실행 시 하드 크래시 발생 → CPU 강제
        if torch.cuda.is_available():
            self.device = "cuda"
            self.dtype = torch.float16
        else:
            self.device = "cpu"
            self.dtype = torch.float32

    def set_voice(self, voice_name):
        self.speaker_name = None

        if "남자" in voice_name:
            self.reference_wav = os.path.join("voice_samples", "male.wav")
        elif "여자" in voice_name:
            self.reference_wav = os.path.join("voice_samples", "female.wav")
        elif re.search(r"user(\d+)\.wav", voice_name):
            num = re.search(r"user(\d+)\.wav", voice_name).group(1)
            self.reference_wav = os.path.join("voice_samples", "Qwen3", f"user{num}.wav")
        elif "소희" in voice_name:
            self.reference_wav = "builtin_sohee"
            self.speaker_name = "Sohee"
        elif "라이언" in voice_name:
            self.reference_wav = "builtin_ryan"
            self.speaker_name = "Ryan"
        elif "에이든" in voice_name:
            self.reference_wav = "builtin_aiden"
            self.speaker_name = "Aiden"
        elif "오노_안나" in voice_name:
            self.reference_wav = "builtin_anna"
            self.speaker_name = "Ono_Anna"
        elif "비비안" in voice_name:
            self.reference_wav = "builtin_vivian"
            self.speaker_name = "Vivian"
        elif "세레나" in voice_name:
            self.reference_wav = "builtin_serena"
            self.speaker_name = "Serena"
        elif "Uncle" in voice_name:
            self.reference_wav = "builtin_uncle_fu"
            self.speaker_name = "Uncle_Fu"
        elif "딜런" in voice_name:
            self.reference_wav = "builtin_dylan"
            self.speaker_name = "Dylan"
        elif "에릭" in voice_name:
            self.reference_wav = "builtin_eric"
            self.speaker_name = "Eric"
        else:
            self.reference_wav = os.path.join("voice_samples", "instructor.wav")

    def load_model(self):
        try:
            import torch
            from qwen_tts import Qwen3TTSModel
            self._determine_device()

            required_type = "CustomVoice" if self.speaker_name else "Base"

            if self.model is not None and self.active_model_type == required_type:
                return True

            model_id = f"Qwen/Qwen3-TTS-12Hz-{self.model_size}-{required_type}"
            print(f"Loading {model_id} on {self.device} with {self.dtype}...")

            if self.model is not None:
                del self.model
                if self.device == "mps":
                    torch.mps.empty_cache()
                elif self.device == "cuda":
                    torch.cuda.empty_cache()

            self.model = Qwen3TTSModel.from_pretrained(
                model_id,
                device_map=self.device,
                dtype=self.dtype,
            )
            self.active_model_type = required_type
            print(f"[{model_id}] loaded successfully!")
            return True
        except Exception as e:
            self.last_error = f"Qwen3-TTS 모델 로드 오류: {e}"
            print("Qwen3-TTS 모델 로드 중 오류 발생:", e)
            traceback.print_exc()
            return False

    # ── 텍스트 전처리: 한국어/영어 이외 문자 원천 차단 ─────────────────
    def _sanitize_text(self, text: str) -> str:
        """
        중국어(CJK), 일본어(히라가나·가타카나), 아랍어, 키릴 문자 등
        허용되지 않는 유니코드를 공백으로 치환합니다.
        허용: 한글, 영문, 숫자, 기본 문장부호, 공백, $ (영어태그용)
        """
        cleaned = re.sub(
            r"[^\uAC00-\uD7A3\u1100-\u11FF\u3130-\u318F"  # 한글 전체
            r"A-Za-z0-9"                                    # 영문/숫자
            r" \t\n\r"                                      # 공백류
            r"!?.,;:'\"\-\[\]\(\)"                         # 기본 문장부호
            r"\$"                                           # $영어$ 태그용
            r"]",
            " ", text
        )
        cleaned = re.sub(r" {2,}", " ", cleaned).strip()
        if cleaned != text:
            print(f"[Qwen3-TTS] ⚠️ 비허용 문자(중국어·일본어 등) 제거됨 → 한국어/영어만 허용")
        return cleaned

    def _split_text(self, text, max_len=150):
        # 1. $영어$ 태그를 기준으로 먼저 분할
        raw_chunks = re.split(r'(\$[^$]+\$)', text)
        final_chunks = []

        for raw in raw_chunks:
            if not raw.strip():
                continue

            is_en_tag = raw.startswith('$') and raw.endswith('$')
            if is_en_tag:
                raw = raw.strip('$').strip()

            # 2. 내부 문장 분할 (딜레이 태그 포함)
            sub_chunks = re.split(r'(\[딜레이\s*\d+(?:\.\d+)?\s*초\]|[.?!]+(?:\s+)|\n+)', raw)
            sentences = []
            current = ""

            for chunk in sub_chunks:
                if re.match(r'^\[딜레이\s*\d+(?:\.\d+)?\s*초\]$', chunk):
                    if current.strip():
                        sentences.append(current.strip())
                        current = ""
                    sentences.append(chunk.strip())
                else:
                    current += chunk
                    if re.search(r'[.?!]+(?:\s+)|\n+', chunk):
                        if current.strip():
                            sentences.append(current.strip())
                        current = ""

            if current.strip():
                sentences.append(current.strip())

            for s in sentences:
                if re.match(r'^\[딜레이\s*\d+(?:\.\d+)?\s*초\]$', s):
                    final_chunks.append(s)
                    continue

                while len(s) > max_len:
                    split_idx = s.rfind(' ', 0, max_len)
                    if split_idx == -1:
                        split_idx = max_len
                    chunk_str = s[:split_idx].strip()
                    if chunk_str:
                        if is_en_tag:
                            final_chunks.append(f"[EN]{chunk_str}[/EN]")
                        else:
                            final_chunks.append(chunk_str)
                    s = s[split_idx:].strip()
                if s:
                    if is_en_tag:
                        final_chunks.append(f"[EN]{s}[/EN]")
                    else:
                        final_chunks.append(s)

        return final_chunks

    def generate_audio(self, text, language="ko", speed=1.0):
        if not text.strip():
            return None

        # ① 비허용 문자 제거 (중국어·일본어 등 원천 차단)
        text = self._sanitize_text(text)
        if not text.strip():
            print("[Qwen3-TTS] 텍스트가 허용 문자 제거 후 비어있어 생성 불가.")
            return None

        # API 모드가 활성화되어 있다면 API를 호출합니다.
        if getattr(self, 'use_api', False):
            return self._generate_audio_api(text, speed)

        required_type = "CustomVoice" if self.speaker_name else "Base"
        if self.model is None or self.active_model_type != required_type:
            success = self.load_model()
            if not success:
                return None

        try:
            # ② 언어는 Korean/English 만 허용 (일본어·중국어 코드 무시)
            safe_lang_map = {"ko": "Korean", "en": "English"}
            lang_name = safe_lang_map.get(language, "Korean")

            # ③ 말투 고정 + 한국어/영어 전용 강제 지시문
            STYLE_PROMPT = (
                "You are a Korean sports instructor giving exercise commands. "
                "ALWAYS output ONLY Korean or English speech. "
                "NEVER output Chinese, Japanese, or any other language. "
                "Speak in a consistent, clear, energetic, and motivating tone. "
                "Maintain the same speaking style for every sentence."
            )

            chunks = self._split_text(text)
            combined_audio = AudioSegment.empty()
            silence = AudioSegment.silent(duration=250)  # 청크 간 0.25초 간격

            import soundfile as sf
            import io
            from pydub.effects import normalize

            for i, chunk in enumerate(chunks):
                if not chunk.strip():
                    continue

                # 딜레이 태그 처리
                delay_match = re.match(r'^\[딜레이\s*(\d+(?:\.\d+)?)\s*초\]$', chunk)
                if delay_match:
                    delay_sec = float(delay_match.group(1))
                    print(f"[Qwen3-TTS] 수동 딜레이: {delay_sec}초")
                    combined_audio += AudioSegment.silent(duration=int(delay_sec * 1000))
                    continue

                chunk_lang_name = lang_name
                if chunk.startswith("[EN]") and chunk.endswith("[/EN]"):
                    chunk = chunk[4:-5].strip()
                    chunk_lang_name = "English"
                    print(f"[Qwen3-TTS] 🇺🇸 영문 모드 전환!")

                # ④ 청크도 개별적으로 한번 더 sanitize
                chunk = self._sanitize_text(chunk)
                if not chunk.strip():
                    continue

                print(f"[Qwen3-TTS] 청크 {i+1}/{len(chunks)} ({chunk_lang_name}): {chunk[:30]}...")

                # 끝음 잘림 방지
                tts_text = chunk
                if not re.search(r'[.?!,;"\'$]$', tts_text):
                    tts_text += "."

                if self.active_model_type == "CustomVoice":
                    wavs, sr = self.model.generate_custom_voice(
                        text=tts_text,
                        language=chunk_lang_name,
                        speaker=self.speaker_name,
                        system_prompt=STYLE_PROMPT
                    )
                else:
                    if not os.path.exists(self.reference_wav):
                        self.last_error = f"참조 음성 파일({self.reference_wav})이 없습니다. 1번 탭에서 목소리를 먼저 등록하거나 내장 목소리(소희, 라이언 등) 또는 Edge-TTS를 선택해 주세요."
                        print(f"경고: 참조 오디오 파일({self.reference_wav})이 없습니다.")
                        return None
                    wavs, sr = self.model.generate_voice_clone(
                        text=tts_text,
                        language=chunk_lang_name,
                        ref_audio=self.reference_wav,
                        x_vector_only_mode=True,
                        system_prompt=STYLE_PROMPT
                    )

                byte_io = io.BytesIO()
                sf.write(byte_io, wavs[0], sr, format='WAV')
                byte_io.seek(0)

                segment = AudioSegment.from_file(byte_io, format="wav")

                # 팝 노이즈 방지 미세 페이드아웃
                if len(segment) > 50:
                    segment = segment.fade_out(30)

                combined_audio += segment + silence

            if speed != 1.0:
                combined_audio = combined_audio.speedup(playback_speed=speed)

            print("[Qwen3-TTS] 오디오 노멀라이즈 적용 중...")
            try:
                combined_audio = normalize(combined_audio)
            except Exception as e:
                print(f"[Qwen3-TTS] 노멀라이즈 스킵 (오류: {e})")

            print(f"[Qwen3-TTS] 전체 생성 완료 (속도: {speed}x)")
            return combined_audio

        except BaseException as e:
            print("오디오 생성 중 오류 발생:", e)
            traceback.print_exc()
            return None
        finally:
            # MPS 캐시 정리 (CPU에서는 불필요하므로 안전하게 스킵)
            if self.device == "mps":
                try:
                    import torch
                    torch.mps.empty_cache()
                except Exception:
                    pass

    def _generate_audio_api(self, text, speed=1.0):
        if not self.api_key:
            print("[Qwen3-TTS API] API 키가 설정되지 않았습니다.")
            return None
        import dashscope
        from dashscope.audio.tts_v2 import SpeechSynthesizer
        dashscope.api_key = self.api_key

        print("[Qwen3-TTS API] DashScope API 요청 중...")
        
        # API 전용 콤보박스 선택값에서 화자 추출
        voice_id = "longxiaochun"  # 기본: 아나운서 여성
        api_sel = getattr(self, "api_voice_selection", "")
        if "커스텀 보이스" in api_sel and hasattr(self, "custom_api_voice_id") and self.custom_api_voice_id:
            voice_id = self.custom_api_voice_id
        elif "아나운서 (남성)" in api_sel:
            voice_id = "longanyang"
        elif "어린이 (여성)" in api_sel:
            voice_id = "longxiaoxia"
        elif "어린이 (남성)" in api_sel:
            voice_id = "longxiaocheng"
        elif "아나운서 (여성)" in api_sel:
            voice_id = "longxiaochun"
        else:
            # 기본 Fallback
            if self.reference_wav and "남자" in self.reference_wav:
                voice_id = "longanyang"

        # 속도 변환 (DashScope API는 0.5 ~ 2.0 지원)
        speech_rate = float(speed)
        if speech_rate < 0.5: speech_rate = 0.5
        if speech_rate > 2.0: speech_rate = 2.0

        try:
            # 여러 청크로 분리하여 각 청크마다 API 호출 (딜레이 처리 위함)
            chunks = self._split_text(text)
            combined_audio = AudioSegment.empty()
            silence = AudioSegment.silent(duration=250)
            import io

            for i, chunk in enumerate(chunks):
                if not chunk.strip():
                    continue

                delay_match = re.match(r'^\[딜레이\s*(\d+(?:\.\d+)?)\s*초\]$', chunk)
                if delay_match:
                    delay_sec = float(delay_match.group(1))
                    combined_audio += AudioSegment.silent(duration=int(delay_sec * 1000))
                    continue

                # 언어 태그 무시 (API 모델은 다국어 자동 처리)
                if chunk.startswith("[EN]") and chunk.endswith("[/EN]"):
                    chunk = chunk[4:-5].strip()

                chunk = self._sanitize_text(chunk)
                if not chunk.strip():
                    continue

                print(f"[Qwen3-TTS API] 청크 {i+1}/{len(chunks)} API 호출 중: {chunk[:30]}...")
                synthesizer = SpeechSynthesizer(model="cosyvoice-v1", voice=voice_id, speech_rate=speech_rate)
                audio_bytes = synthesizer.call(chunk)
                
                if audio_bytes is not None:
                    segment = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
                    combined_audio += segment + silence
                else:
                    print(f"[Qwen3-TTS API] 청크 {i+1} API 호출 실패.")

            from pydub.effects import normalize
            try:
                combined_audio = normalize(combined_audio)
            except Exception:
                pass
            print(f"[Qwen3-TTS API] 전체 생성 완료 (API 모드)")
            return combined_audio
            
        except Exception as e:
            print("[Qwen3-TTS API] API 호출 중 오류 발생:", e)
            traceback.print_exc()
            return None
