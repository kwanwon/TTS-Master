import re
import os
from pydub import AudioSegment

class AudioMixer:
    def __init__(self, effect_dir="effects"):
        self.effect_dir = effect_dir
        try:
            if self.effect_dir and not os.path.exists(self.effect_dir):
                os.makedirs(self.effect_dir, exist_ok=True)
        except Exception as e:
            print(f"[AudioMixer] Warning: could not create effect dir: {e}")
            
    def parse_script(self, text):
        """
        텍스트를 파싱하여 (타입, 내용)의 리스트로 반환합니다.
        타입: 'text', 'delay', 'effect'
        """
        # 정규식: [딜레이: 1.5], [딜레이 1.5초], [효과음: 기합] 등 매칭 (: 기호 생략 허용)
        pattern = r'\[(딜레이|효과음):?\s*([^\]]+)\]'
        
        # 텍스트를 분할
        parts = re.split(pattern, text)
        
        result = []
        i = 0
        while i < len(parts):
            # 일반 텍스트 부분
            text_part = parts[i].strip()
            if text_part:
                # 텍스트를 영어와 비영어(한국어)로 자동 쪼개기 (Auto-Splitter)
                # 영단어(알파벳+공백+문장부호) 뭉치와 그 외 문자를 분리
                lang_pattern = r'([a-zA-Z\s\.,!\?]+)'
                lang_chunks = re.split(lang_pattern, text_part)
                
                for chunk in lang_chunks:
                    chunk = chunk.strip()
                    if chunk:
                        # 영문자가 하나라도 포함되어 있으면 영어 모드로 처리
                        if re.search(r'[a-zA-Z]', chunk):
                            result.append(('text', chunk, 'en'))
                        else:
                            result.append(('text', chunk, 'ko'))
            
            # 매칭된 그룹 처리
            if i + 2 < len(parts):
                tag_type = parts[i+1].strip()
                tag_val = parts[i+2].strip()
                
                if tag_type == "딜레이":
                    # '분 대기', '분', '초' 등 파싱, 0/2 같은 오타 방지를 위해 /를 .으로 변환
                    val_str = tag_val.replace("대기", "").strip()
                    is_minute = "분" in val_str
                    val_str = val_str.replace("분", "").replace("초", "").replace("/", ".").replace(" ", "").strip()
                    try:
                        delay_val = float(val_str)
                        delay_ms = int(delay_val * 60 * 1000) if is_minute else int(delay_val * 1000)
                        result.append(('delay', delay_ms, None))
                    except ValueError:
                        pass # 숫자가 아니면 무시
                elif tag_type == "효과음":
                    result.append(('effect', tag_val, None))
                i += 3
            else:
                i += 1
                
        return result
        
    def create_mixed_audio(self, parsed_items, tts_generator_func, bgm_path=None):
        """
        파싱된 아이템 리스트를 받아서 하나의 오디오로 합성합니다.
        tts_generator_func(text, language) -> AudioSegment
        """
        final_audio = AudioSegment.silent(duration=0)
        
        for item_type, item_val, lang in parsed_items:
            if item_type == 'text':
                # TTS 함수로 텍스트를 음성으로 변환 (AudioSegment 반환)
                audio_segment = tts_generator_func(item_val, lang)
                if audio_segment:
                    final_audio += audio_segment
            elif item_type == 'delay':
                # 무음 추가
                final_audio += AudioSegment.silent(duration=item_val)
            elif item_type == 'effect':
                # 효과음 파일 로드 (예: effects/기합.wav)
                effect_file = os.path.join(self.effect_dir, f"{item_val}.wav")
                if not os.path.exists(effect_file):
                    effect_file = os.path.join(self.effect_dir, f"{item_val}.mp3")
                    
                if os.path.exists(effect_file):
                    effect_audio = AudioSegment.from_file(effect_file)
                    final_audio += effect_audio
                else:
                    print(f"경고: 효과음 파일을 찾을 수 없습니다 -> {effect_file}")
                    
        # BGM이 있다면 최종 오디오와 믹싱
        if bgm_path and os.path.exists(bgm_path):
            bgm = AudioSegment.from_file(bgm_path)
            
            # BGM을 목소리 길이만큼 자르거나 반복
            if len(bgm) < len(final_audio):
                bgm = bgm * (len(final_audio) // len(bgm) + 1)
            bgm = bgm[:len(final_audio)]
            
            # BGM 볼륨 약간 줄임 (-10dB)
            bgm = bgm - 10
            
            # 합성
            final_audio = final_audio.overlay(bgm)
            
        return final_audio

    def export_audio(self, audio_segment, save_path, format="mp3"):
        """
        오디오를 파일로 내보냅니다.
        """
        audio_segment.export(save_path, format=format)
