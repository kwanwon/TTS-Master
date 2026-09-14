import json
import os

class ProjectManager:
    def __init__(self, save_path=None):
        if save_path is None:
            self.save_path = os.path.join("projects", "last_session.json")
        else:
            self.save_path = save_path
        os.makedirs(os.path.dirname(self.save_path), exist_ok=True)
        
    def save_state(self, api_key, playlist_items):
        """
        API 키와 현재 플레이리스트의 항목들을 JSON으로 저장합니다.
        """
        data = {
            "api_key": api_key,
            "playlist": playlist_items
        }
        with open(self.save_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            
    def load_state(self):
        """
        저장된 JSON 파일에서 상태를 불러옵니다.
        """
        if os.path.exists(self.save_path):
            with open(self.save_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"api_key": "", "playlist": []}
