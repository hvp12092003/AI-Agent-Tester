import os
from openai import OpenAI
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

class LLMFactory:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "google").lower()
        self.google_key = os.getenv("GOOGLE_API_KEY")
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY")
        
        if self.provider == "google":
            if not self.google_key:
                raise ValueError("GOOGLE_API_KEY is not set in .env")
            self.google_client = genai.Client(api_key=self.google_key)
        elif self.provider == "openrouter":
            if not self.openrouter_key:
                raise ValueError("OPENROUTER_API_KEY is not set in .env")
            self.client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=self.openrouter_key,
            )
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def get_available_models(self):
        """Lấy danh sách các model khả dụng dựa trên provider."""
        if self.provider == "google":
            models = []
            try:
                # Sử dụng SDK genai mới
                for m in self.google_client.models.list():
                    # Chỉ lấy các model hỗ trợ generateContent và thuộc gemini/gemma
                    if 'generateContent' in m.supported_actions:
                        if "gemini" in m.name or "gemma" in m.name:
                            models.append(m.name.replace("models/", ""))
                return sorted(list(set(models)))
            except Exception as e:
                print(f"Error fetching Google models: {e}")
                # Fallback sang các model phổ biến năm 2026
                return ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro"]
        
        elif self.provider == "openrouter":
            return [
                "google/gemini-2.0-flash-001",
                "google/gemini-2.5-flash",
                "anthropic/claude-3.7-sonnet",
                "openai/gpt-4o",
                "meta-llama/llama-3.3-70b-instruct",
                "deepseek/deepseek-chat",
                "google/gemma-4-31b-it:free"
            ]
        return []

    async def generate_content(self, model_name, prompt, image_data=None, mime_type="image/jpeg"):
        """Gửi yêu cầu generate content đến provider tương ứng."""
        if self.provider == "google":
            try:
                if image_data:
                    # Sử dụng Part.from_bytes cho ảnh trong SDK mới
                    contents = [
                        prompt,
                        types.Part.from_bytes(data=image_data, mime_type=mime_type)
                    ]
                    response = self.google_client.models.generate_content(
                        model=model_name,
                        contents=contents
                    )
                else:
                    response = self.google_client.models.generate_content(
                        model=model_name,
                        contents=prompt
                    )
                return response.text
            except Exception as e:
                print(f"Error generating content with Google: {e}")
                return f"[[API_ERROR]]: {str(e)}"

        elif self.provider == "openrouter":
            import base64
            messages = []
            
            content = [{"type": "text", "text": prompt}]
            
            if image_data:
                base64_image = base64.b64encode(image_data).decode('utf-8')
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{base64_image}"
                    }
                })
            
            messages.append({"role": "user", "content": content})
            
            # Giới hạn max_tokens để tránh lỗi 402 (Payment Required)
            response = self.client.chat.completions.create(
                model=model_name,
                messages=messages,
                max_tokens=2048
            )
            return response.choices[0].message.content

        return ""
