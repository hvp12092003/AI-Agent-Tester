import os
import json
import re
import base64
from dotenv import load_dotenv
from agents.llm_factory import LLMFactory
from tools.vision_tool import capture_screenshot
from tools.action_tool import perform_action

load_dotenv()
llm_factory = LLMFactory()

class VisionManager:
    def __init__(self, model_name=None):
        self.model_name = model_name or os.getenv("DEFAULT_MODEL", "google/gemini-2.0-flash-001")
        self.history = []

    async def think_and_act(self, user_goal: str, url: str = None):
        print(f"🔍 Đang thực hiện mục tiêu: {user_goal}")
        
        # 1. Quan sát (Vision Tool)
        base64_image = await capture_screenshot(url)
        
        # 2. Suy nghĩ (AI)
        prompt = f"""
        Bạn là một trợ lý tự động hóa web. Mục tiêu của người dùng là: '{user_goal}'
        Đây là ảnh chụp màn hình hiện tại. 
        Hãy phân tích và cho biết bước tiếp theo cần làm là gì.
        
        Trả về kết quả theo định dạng JSON (chỉ trả về JSON, không kèm giải thích khác):
        {{
            "suy_nghi": "mô tả những gì bạn thấy và dự định làm",
            "hanh_dong": "click" hoặc "type" hoặc "scroll" hoặc "hoan_thanh",
            "selector": "playwright selector (ví dụ: button#login)",
            "text": "văn bản cần nhập nếu hành động là type",
            "ly_do": "tại sao làm vậy"
        }}
        """
        
        # Chuyển base64 sang bytes
        image_data = base64.b64decode(base64_image)
        
        content = await llm_factory.generate_content(
            model_name=self.model_name,
            prompt=prompt,
            image_data=image_data
        )
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            result = json.loads(match.group())
            print(f"🤖 AI Suy nghĩ: {result.get('suy_nghi')}")
            
            # 3. Thực thi (Action Tool)
            if result['hanh_dong'] != "hoan_thanh":
                action_result = await perform_action(
                    action_type=result['hanh_dong'],
                    selector=result.get('selector'),
                    text=result.get('text')
                )
                print(f"✅ {action_result}")
                return False # Chưa xong
            else:
                print("🎉 Đã hoàn thành mục tiêu!")
                return True # Xong
        else:
            print(f"❌ AI không trả lời đúng định dạng JSON. Phản hồi: {content}")
            return True
