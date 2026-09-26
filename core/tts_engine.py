import os
import threading
os.environ["COQUI_TOS_AGREED"] = "1"
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
import tempfile
import traceback
import re
from pydub import AudioSegment

class CoquiEngine:
    def __init__(self):
        self.tts = None
        self.device = "cpu"
        self.reference_wav = os.path.join("voice_samples", "instructor.wav")
        self.last_error = ""
        
    def set_voice(self, voice_name):
        if "남자" in voice_name:
            self.reference_wav = os.path.join("voice_samples", "male.wav")
        elif "여자" in voice_name:
            self.reference_wav = os.path.join("voice_samples", "female.wav")
        elif re.search(r"user(\d+)\.wav", voice_name):
            num = re.search(r"user(\d+)\.wav", voice_name).group(1)
            self.reference_wav = os.path.join("voice_samples", "Coqui", f"user{num}.wav")
        else:
            self.reference_wav = os.path.join("voice_samples", "instructor.wav")
        
    def load_model(self):
        if self.tts is None:
            try:
                import torch
                
                # Fix for transformers >= 4.41.0 compatibility with Coqui TTS
                import transformers
                if not hasattr(transformers, "BeamSearchScorer"):
                    transformers.BeamSearchScorer = object
                    
                from TTS.api import TTS
                
                if torch.cuda.is_available():
                    self.device = "cuda"
                else:
                    self.device = "cpu"
                    
                print(f"Loading Coqui XTTS v2 on {self.device}...")
                self.tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(self.device)
                print("Coqui Model loaded successfully!")
                return True
            except Exception as e:
                self.last_error = f"Coqui TTS 모델 로드 실패: {e}"
                print("Coqui TTS 로드 중 오류 발생:", e)
                return False
        return True

    def _split_text(self, text, max_len=150):
        # 1. $영어$ 태그를 기준으로 먼저 분할
        raw_chunks = re.split(r'(\$[^\$]+\$)', text)
        final_chunks = []
        
        for raw in raw_chunks:
            if not raw.strip():
                continue
                
            is_en = raw.startswith('$') and raw.endswith('$')
            if is_en:
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
                        if is_en:
                            final_chunks.append(f"[EN]{chunk_str}[/EN]")
                        else:
                            final_chunks.append(chunk_str)
                    s = s[split_idx:].strip()
                if s:
                    if is_en:
                        final_chunks.append(f"[EN]{s}[/EN]")
                    else:
                        final_chunks.append(s)
                        
        return final_chunks

    def generate_audio(self, text, language="ko", speed=1.0):
        if not text.strip():
            return None
            
        if self.tts:
            try:
                ref_voice = self.reference_wav if os.path.exists(self.reference_wav) else None
                if not ref_voice:
                    self.last_error = f"참조 음성 파일({self.reference_wav})이 없습니다. 음성을 먼저 등록해 주세요."
                    print(f"경고: {self.reference_wav} 파일이 없습니다.")
                    return None

                chunks = self._split_text(text)
                combined_audio = AudioSegment.empty()
                silence = AudioSegment.silent(duration=250)
                
                for i, chunk in enumerate(chunks):
                    if not chunk.strip(): continue
                    
                    # 딜레이 태그 확인
                    delay_match = re.match(r'^\[딜레이\s*(\d+(?:\.\d+)?)\s*초\]$', chunk)
                    if delay_match:
                        delay_sec = float(delay_match.group(1))
                        print(f"[Coqui] 수동 딜레이 적용: {delay_sec}초")
                        combined_audio += AudioSegment.silent(duration=int(delay_sec * 1000))
                        continue
                        
                    chunk_lang_code = language
                    if chunk.startswith("[EN]") and chunk.endswith("[/EN]"):
                        chunk = chunk[4:-5].strip()
                        chunk_lang_code = "en"
                        print(f"[Coqui] 🇺🇸 영문 모드 전환 발동!")
                        
                    print(f"[Coqui] 청크 {i+1}/{len(chunks)} 처리 중 ({chunk_lang_code}): {chunk[:30]}...")
                    
                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
                    temp_path = temp_file.name
                    temp_file.close()
                    
                    # TTS 모델이 끝음을 잘라먹는 현상 방지
                    tts_text = chunk
                    if not re.search(r'[.?!,;\"\']$', tts_text):
                        tts_text += "."
                        
                    self.tts.tts_to_file(
                        text=tts_text,
                        speaker_wav=ref_voice,
                        language=chunk_lang_code,
                        file_path=temp_path
                    )
                    
                    segment = AudioSegment.from_file(temp_path)
                    
                    # 팝 노이즈 및 끊김 방지를 위해 미세한 페이드아웃 적용
                    if len(segment) > 50:
                        segment = segment.fade_out(30)
                        
                    combined_audio += segment + silence
                    os.remove(temp_path)
                
                if speed != 1.0:
                    combined_audio = combined_audio.speedup(playback_speed=speed)
                
                from pydub.effects import normalize, compress_dynamic_range
                
                # [자동 마스터링] 오디오 톤 및 볼륨 균일화
                print("[Coqui-TTS] 오디오 마스터링(컴프레션 및 노멀라이즈) 적용 중...")
                combined_audio = compress_dynamic_range(combined_audio)
                combined_audio = normalize(combined_audio)
                    
                print(f"[Coqui] 전체 생성 완료 (속도: {speed}x)")
                return combined_audio
            except Exception as e:
                print("오디오 생성 중 오류 발생:", e)
                return None
        return AudioSegment.silent(duration=1000)




class EdgeTTSEngine:
    """
    Microsoft Edge-TTS 기반 초고음질 온라인 음성 합성 엔진
    별도의 무거운 로컬 가중치 없이 즉시 자연스러운 한국어/다국어 음성 생성
    """
    VOICE_MAP = {
        "선히": "ko-KR-SunHiNeural",
        "인준": "ko-KR-InJoonNeural",
        "현수": "ko-KR-HyunsuMultilingualNeural",
        "jenny": "en-US-JennyNeural",
        "guy": "en-US-GuyNeural",
        "nanami": "ja-JP-NanamiNeural",
        "xiaoxiao": "zh-CN-XiaoxiaoNeural",
    }

    def __init__(self):
        self.current_voice = "ko-KR-SunHiNeural"
        self.last_error = ""

    def set_voice(self, voice_name):
        vn_lower = voice_name.lower()
        for k, v in self.VOICE_MAP.items():
            if k in vn_lower:
                self.current_voice = v
                return
        if "neural" in vn_lower:
            self.current_voice = voice_name
            return
        self.current_voice = "ko-KR-SunHiNeural"

    def load_model(self):
        self.last_error = ""
        return True

    def _split_text(self, text, max_len=150):
        # 1. $영어$ 태그를 최우선으로 확실하게 분리 (예: "안녕하세요$ hi$" -> ["안녕하세요", "$ hi$"])
        raw_chunks = re.split(r'(\$[^$]+\$)', text)
        tagged_chunks = []
        for raw in raw_chunks:
            if not raw.strip():
                continue
            if raw.startswith('$') and raw.endswith('$'):
                en_val = raw.strip('$').strip()
                if en_val:
                    tagged_chunks.append(f"[EN]{en_val}[/EN]")
            else:
                tagged_chunks.append(raw)

        # 2. 태그가 없는 일반 한국어 문장 중 영단어/영문장 스마트 감지
        final_chunks = []
        for chunk in tagged_chunks:
            if chunk.startswith("[EN]") and chunk.endswith("[/EN]"):
                final_chunks.append(chunk)
                continue

            # 영문 어구(알파벳 2자 이상 포함된 영문 구) 자동 분할
            # 예: "안녕하세요 hi my name is Ryan 반갑습니다" -> ["안녕하세요", "[EN]hi my name is Ryan[/EN]", "반갑습니다"]
            tokens = re.split(r'(\[딜레이\s*\d+(?:\.\d+)?\s*초\]|[A-Za-z][A-Za-z0-9\s,\'\"\?!]{1,}[A-Za-z0-9\?!])', chunk)
            for tok in tokens:
                if not tok.strip():
                    continue
                if re.match(r'^\[딜레이\s*\d+(?:\.\d+)?\s*초\]$', tok):
                    final_chunks.append(tok.strip())
                elif re.search(r'[A-Za-z]{2,}', tok) and not re.search(r'[\uAC00-\uD7A3]', tok):
                    # 순수 영문(한글 미포함)인 경우 100% 미국 원어민 모드로 전환!
                    final_chunks.append(f"[EN]{tok.strip()}[/EN]")
                else:
                    # 한국어 문장 부호 단위 분할
                    sub_sents = re.split(r'([.?!]+(?:\s+)|\n+)', tok)
                    cur_ko = ""
                    for s in sub_sents:
                        cur_ko += s
                        if re.search(r'[.?!]+(?:\s+)|\n+', s):
                            if cur_ko.strip():
                                final_chunks.append(cur_ko.strip())
                                cur_ko = ""
                    if cur_ko.strip():
                        final_chunks.append(cur_ko.strip())

        return final_chunks

    def generate_audio(self, text, language="ko", speed=1.0):
        if not text.strip():
            return None
        self.last_error = ""
        try:
            import asyncio
            import io
            import edge_tts
            from pydub.effects import normalize, compress_dynamic_range

            chunks = self._split_text(text)
            combined_audio = AudioSegment.empty()
            silence = AudioSegment.silent(duration=100)  # 자연스러운 호흡 간격 (100ms)

            rate_percent = int((speed - 1.0) * 100)
            rate_str = f"+{rate_percent}%" if rate_percent >= 0 else f"{rate_percent}%"

            async def _synthesize_chunk(chunk_text, voice):
                try:
                    communicate = edge_tts.Communicate(chunk_text, voice, rate=rate_str)
                    mp3_fp = io.BytesIO()
                    async for c in communicate.stream():
                        if c['type'] == 'audio':
                            mp3_fp.write(c['data'])
                    mp3_fp.seek(0)
                    return AudioSegment.from_file(mp3_fp, format="mp3")
                except Exception as inner_e:
                    print(f"[Edge-TTS] 화자 '{voice}' 실패 ({inner_e}) -> 기본 화자(선히)로 안전 재시도")
                    fallback_voice = "ko-KR-SunHiNeural"
                    communicate = edge_tts.Communicate(chunk_text, fallback_voice, rate=rate_str)
                    mp3_fp = io.BytesIO()
                    async for c in communicate.stream():
                        if c['type'] == 'audio':
                            mp3_fp.write(c['data'])
                    mp3_fp.seek(0)
                    return AudioSegment.from_file(mp3_fp, format="mp3")

            for chunk in chunks:
                if not chunk.strip():
                    continue

                delay_match = re.match(r'^\[딜레이\s*(\d+(?:\.\d+)?)\s*초\]$', chunk)
                if delay_match:
                    sec = float(delay_match.group(1))
                    print(f"[Edge-TTS] 수동 딜레이 적용: {sec}초")
                    combined_audio += AudioSegment.silent(duration=int(sec * 1000))
                    continue

                voice = self.current_voice
                if chunk.startswith("[EN]") and chunk.endswith("[/EN]"):
                    chunk = chunk[4:-5].strip()
                    # 콩글리시 원천 차단: 어떤 기본 화자이든 영어는 100% 미국 본토 원어민 화자로 발음!
                    # 기본 화자가 남성이면 미국 남성 원어민(Guy), 여성이면 미국 여성 원어민(Jenny)
                    is_male = any(k in self.current_voice.lower() for k in ["injoon", "hyunsu", "guy", "male"])
                    voice = "en-US-GuyNeural" if is_male else "en-US-JennyNeural"
                    print(f"[Edge-TTS] 🇺🇸 100% 미국 본토 원어민 보이스로 발음: '{chunk}' -> {voice}")

                if not re.search(r'[.?!,;\"\']$', chunk):
                    chunk += "!" if len(chunk) <= 6 else "."

                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop and loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        seg = pool.submit(asyncio.run, _synthesize_chunk(chunk, voice)).result()
                else:
                    seg = asyncio.run(_synthesize_chunk(chunk, voice))

                if len(seg) > 50:
                    seg = seg.fade_out(20)
                combined_audio += seg + silence

            if len(combined_audio) > 0:
                try:
                    combined_audio = compress_dynamic_range(combined_audio)
                    combined_audio = normalize(combined_audio)
                except Exception as ne:
                    print(f"[Edge-TTS] 마스터링 경고: {ne}")

            return combined_audio
        except Exception as e:
            self.last_error = f"Edge-TTS 음성 합성 오류: {e}"
            print("[Edge-TTS] 에러 발생:", e)
            traceback.print_exc()
            return None


class TTSEngine:
    """
    팩토리/프록시 클래스: UI에서 호출할 때 단일 인터페이스 유지 (지연 로딩 적용)
    시작 시에는 초경량 Edge-TTS만 즉시 로드하여 0.5초 이내에 쾌속 실행(Fast Launch)을 보장합니다.
    """
    def __init__(self):
        self.current_engine_name = "Edge-TTS (초고음질 온라인)"
        self._current_voice = ""
        self._saved_use_api = False
        self._saved_api_key = None
        self._saved_api_voice_selection = ""
        self._saved_custom_api_voice_id = None

        self._engine_factories = {
            "Edge-TTS (초고음질 온라인)": lambda: EdgeTTSEngine(),
            "Qwen3-TTS (0.6B)": lambda: self._create_qwen3("0.6B"),
            "Qwen3-TTS (1.7B)": lambda: self._create_qwen3("1.7B"),
            "Coqui XTTS v2": lambda: self._create_coqui(),
        }
        self._engine_instances = {}
        # 시작 시에는 기본 Edge-TTS만 즉시 인스턴스화
        self._engine_instances[self.current_engine_name] = EdgeTTSEngine()
        self.active_engine = self._engine_instances[self.current_engine_name]

        self._lock = threading.Lock()   # 동시 호출 방지 잠금장치
        self.is_busy = False             # 현재 생성 중인지 상태 플래그
        self.last_error = ""

    def _create_qwen3(self, model_size):
        from core.qwen3_engine import Qwen3Engine
        engine = Qwen3Engine(model_size)
        if self._current_voice:
            engine.set_voice(self._current_voice)
        if hasattr(engine, 'use_api'):
            engine.use_api = self._saved_use_api
        if hasattr(engine, 'api_key'):
            engine.api_key = self._saved_api_key
        if hasattr(engine, 'api_voice_selection'):
            engine.api_voice_selection = self._saved_api_voice_selection
        if hasattr(engine, 'custom_api_voice_id'):
            engine.custom_api_voice_id = self._saved_custom_api_voice_id
        return engine

    def _create_coqui(self):
        engine = CoquiEngine()
        if self._current_voice:
            engine.set_voice(self._current_voice)
        return engine

    @property
    def engines(self):
        """호환성을 위한 프로퍼티"""
        return self._engine_instances

    def switch_engine(self, engine_name):
        if engine_name in self._engine_factories:
            self.current_engine_name = engine_name
            if engine_name not in self._engine_instances:
                print(f"[TTSEngine] 지연 로딩 초기화: {engine_name}")
                self._engine_instances[engine_name] = self._engine_factories[engine_name]()
            self.active_engine = self._engine_instances[engine_name]
            if self._current_voice:
                self.active_engine.set_voice(self._current_voice)
            return True
        return False
        
    def set_voice(self, voice_name):
        self._current_voice = voice_name
        for engine in self._engine_instances.values():
            engine.set_voice(voice_name)

    @property
    def use_api(self):
        return getattr(self.active_engine, 'use_api', False)

    @use_api.setter
    def use_api(self, val):
        self._saved_use_api = val
        for engine in self._engine_instances.values():
            if hasattr(engine, 'use_api'):
                engine.use_api = val

    @property
    def api_key(self):
        return getattr(self.active_engine, 'api_key', None)

    @api_key.setter
    def api_key(self, val):
        self._saved_api_key = val
        for engine in self._engine_instances.values():
            if hasattr(engine, 'api_key'):
                engine.api_key = val

    @property
    def api_voice_selection(self):
        return getattr(self.active_engine, 'api_voice_selection', "")

    @api_voice_selection.setter
    def api_voice_selection(self, val):
        self._saved_api_voice_selection = val
        for engine in self._engine_instances.values():
            if hasattr(engine, 'api_voice_selection'):
                engine.api_voice_selection = val

    @property
    def custom_api_voice_id(self):
        return getattr(self.active_engine, 'custom_api_voice_id', None)

    @custom_api_voice_id.setter
    def custom_api_voice_id(self, val):
        self._saved_custom_api_voice_id = val
        for engine in self._engine_instances.values():
            if hasattr(engine, 'custom_api_voice_id'):
                engine.custom_api_voice_id = val
            
    def load_model(self):
        res = self.active_engine.load_model()
        if not res:
            self.last_error = getattr(self.active_engine, 'last_error', '모델 로드에 실패했습니다.')
        return res
        
    def generate_audio(self, text, language="ko", speed=1.0):
        if self.is_busy:
            print("[TTSEngine] 경고: 이미 음성 생성 중입니다. 요청 무시됨.")
            self.last_error = "현재 다른 음성을 생성하고 있습니다. 잠시 후 다시 시도해 주세요."
            return None
        with self._lock:
            self.is_busy = True
            try:
                audio = self.active_engine.generate_audio(text, language, speed)
                if not audio:
                    self.last_error = getattr(self.active_engine, 'last_error', '오디오 생성에 실패했습니다.')
                return audio
            finally:
                self.is_busy = False
