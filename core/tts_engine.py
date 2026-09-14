import os
import threading
os.environ["COQUI_TOS_AGREED"] = "1"
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
import tempfile
import traceback
import re
from pydub import AudioSegment
from core.qwen3_engine import Qwen3Engine

class CoquiEngine:
    def __init__(self):
        self.tts = None
        self.device = "cpu"
        self.reference_wav = os.path.join("voice_samples", "instructor.wav")
        
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
            
        if self.tts:
            try:
                ref_voice = self.reference_wav if os.path.exists(self.reference_wav) else None
                if not ref_voice:
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




class TTSEngine:
    """
    팩토리/프록시 클래스: UI에서 호출할 때 단일 인터페이스 유지
    """
    def __init__(self):
        self.current_engine_name = "Coqui XTTS v2"
        self.engines = {
            "Coqui XTTS v2": CoquiEngine(),
            "Qwen3-TTS (0.6B)": Qwen3Engine("0.6B"),
            "Qwen3-TTS (1.7B)": Qwen3Engine("1.7B")
        }
        self.active_engine = self.engines[self.current_engine_name]
        self._lock = threading.Lock()   # 동시 호출 방지 잠금장치
        self.is_busy = False             # 현재 생성 중인지 상태 플래그
        
    def switch_engine(self, engine_name):
        if engine_name in self.engines:
            self.current_engine_name = engine_name
            self.active_engine = self.engines[engine_name]
            return True
        return False
        
    def set_voice(self, voice_name):
        for engine in self.engines.values():
            engine.set_voice(voice_name)
            
    def load_model(self):
        return self.active_engine.load_model()
        
    def generate_audio(self, text, language="ko", speed=1.0):
        if self.is_busy:
            print("[TTSEngine] 경고: 이미 음성 생성 중입니다. 요청 무시됨.")
            return None
        with self._lock:
            self.is_busy = True
            try:
                return self.active_engine.generate_audio(text, language, speed)
            finally:
                self.is_busy = False
