from openai import OpenAI
import traceback

class AIGenerator:
    def __init__(self, api_key=""):
        self.client = OpenAI(api_key=api_key) if api_key else None
        
    def set_api_key(self, api_key):
        self.client = OpenAI(api_key=api_key)
        
    def generate_draft(self, user_text, difficulty_level, document_text=""):
        if not self.client:
            return "오류: API 키가 입력되지 않았습니다. 좌측 상단에 OpenAI API 키를 입력해 주세요."
            
        # 난이도 분석
        # "1단계 (유치원: 쉬운 한글 위주)" -> 1
        level = int(difficulty_level.split("단계")[0].strip())
        
        system_prompt = """
        당신은 체육관(태권도 등)에서 아이들을 지도하는 마스터이자, 영어 교육을 접목시키는 전문가입니다.
        사용자가 입력한 체육관 훈련 대본(또는 제공된 수련계획표 문서)을 바탕으로 TTS(음성 합성) 전용 스크립트 초안을 작성해주세요.
        
        [난이도별 영어 혼합 규칙]
        - 1단계 (유치원): 100% 한글. 매우 쉽고 친근한 어투. (예: "발차기 준비! 앞차기 얍!")
        - 2단계 (초등 저학년): 주요 단어만 영어로 혼용. (예: "스탠드 업(Stand up)! 앞차기 프론트 킥(Front kick)!")
        - 3단계 (초등 중학년): 한글과 영어를 자연스럽게 섞어서. (예: "손을 허리에 대고 넥 서클(Neck circle) 준비, 하나, 둘..")
        - 4단계 (초등 고학년 이상): 대부분 영어로 지시하되 필수적인 설명만 한글. (예: "Ready for front kick. 하나, 둘, 셋!")
        
        [출력 규칙]
        - 각 지시문(동작) 사이에는 사용자가 나중에 시간을 조정할 수 있도록 기본적으로 **[딜레이: 0초]** 태그를 삽입해 주세요.
        - 만약 제공된 수련계획표에 '50분 수업', '명상 5분' 등의 긴 시간이 있다면 그것만 [딜레이: 5분] 처럼 표현하세요.
        - 예시 출력 형식:
          발차기 준비! [딜레이: 0초]
          앞차기, Front kick 하나! [딜레이: 0초]
          둘! [딜레이: 0초]
          이제 명상을 시작합니다. 눈을 감으세요. [딜레이: 3분]
          명상 끝! [딜레이: 0초]
        
        사용자가 입력한 내용(및 첨부된 수련계획표)을 위 규칙에 맞게 변환하여 반환해 주세요. (인사말이나 다른 말은 빼고 대본만 출력하세요)
        """
        
        user_message = f"난이도: {level}단계\n입력 대본/지시사항:\n{user_text}\n"
        if document_text:
            user_message += f"\n[참고할 수련계획표 문서 내용]\n{document_text}\n(이 문서 내용을 바탕으로 훈련 스크립트를 작성해 주세요.)"
            
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.7,
                max_tokens=1000
            )
            return response.choices[0].message.content
        except Exception as e:
            error_msg = str(e)
            print(traceback.format_exc())
            return f"API 호출 중 오류가 발생했습니다:\n{error_msg}"
            
    def generate_master_draft(self, document_text, difficulty_level, total_time_minutes):
        if not self.client:
            return "오류: API 키가 입력되지 않았습니다."
            
        level = int(difficulty_level.split("단계")[0].strip())
        
        system_prompt = f"""
        당신은 체육관(태권도 등)에서 아이들을 지도하는 마스터이자, 영어 교육을 접목시키는 전문가입니다.
        사용자가 제공한 수련계획표 문서를 분석하여, 정확히 총 {total_time_minutes}분 동안 진행될 훈련의 TTS 오디오 스크립트를 작성해주세요.
        
        [난이도별 영어 혼합 규칙]
        - 1단계 (유치원): 100% 한글. 매우 쉽고 친근한 어투. 
        - 2단계 (초등 저학년): 주요 단어만 영어로 혼용. (예: "스탠드 업(Stand up)!")
        - 3단계 (초등 중학년): 한글과 영어를 자연스럽게 섞어서.
        - 4단계 (초등 고학년 이상): 대부분 영어로 지시하되 필수적인 설명만 한글.
        
        [출력 규칙 (매우 중요)]
        - 전체 훈련 시간이 {total_time_minutes}분이 될 수 있도록 딜레이를 분배하되, 구체적인 동작 사이의 간격은 사용자가 직접 수정할 수 있도록 기본적으로 **[딜레이: 0초]**를 넣어주세요.
        - 몸풀기, 본 운동, 마무리 운동 등 스케줄표에 명시된 활동이 끝날 때마다 실제 운동하는 시간을 딜레이 태그로 반드시 넣으세요.
        - 딜레이 태그 형식: [딜레이: 10분], [딜레이: 0초]
        - 인사말 없이 오직 대본과 딜레이 태그만 출력하세요.
        """
        
        user_message = f"난이도: {level}단계\n총 훈련 시간: {total_time_minutes}분\n[수련계획표 문서]\n{document_text}\n\n위 문서를 기반으로 {total_time_minutes}분짜리 스크립트를 작성해 주세요."
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.7,
                max_tokens=2000
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"API 호출 중 오류가 발생했습니다:\n{str(e)}"
