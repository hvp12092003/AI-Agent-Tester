import os
from openai import OpenAI
from dotenv import load_dotenv
from google import genai
from google.genai import types
import requests

load_dotenv()


# ==========================================
# CẤU HÌNH NHÚNG (DÀNH CHO BẢN EXE)
# Hãy điền Key của bạn vào đây nếu muốn đóng gói vào EXE
EMBEDDED_OPENROUTER_KEY = "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" 
# ==========================================

class LLMFactory:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "openrouter").lower()
        self.google_key = os.getenv("GOOGLE_API_KEY")
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY") or EMBEDDED_OPENROUTER_KEY

        if self.provider == "google":
            if not self.google_key:
                raise ValueError("GOOGLE_API_KEY is not set in .env")
            self.google_client = genai.Client(api_key=self.google_key)
        elif self.provider == "openrouter":
            # Nếu không có key trong env thì dùng key nhúng
            actual_key = self.openrouter_key
            if not actual_key:
                raise ValueError("OPENROUTER_API_KEY is not set (env or embedded)")
            
            self.client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=actual_key,
            )
        elif self.provider == "ollama":
            self.ollama_base_url = os.getenv(
                "OLLAMA_BASE_URL", "http://localhost:11434/v1"
            )
            self.client = OpenAI(
                base_url=self.ollama_base_url,
                api_key="ollama",
            )
        elif self.provider == "groq":
            self.groq_key = os.getenv("GROQ_API_KEY")
            if not self.groq_key:
                raise ValueError("GROQ_API_KEY is not set in .env")
            self.client = OpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=self.groq_key,
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
                    if "generateContent" in m.supported_actions:
                        if "gemini" in m.name or "gemma" in m.name:
                            models.append(m.name.replace("models/", ""))
                return sorted(list(set(models)))
            except Exception as e:
                print(f"Error fetching Google models: {e}")
                # Fallback sang các model phổ biến năm 2026
                return ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro"]

        elif self.provider == "openrouter":
            try:
                response = requests.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {self.openrouter_key}"}
                )
                if response.status_code == 200:
                    # Filter for models that support vision (optional, but good for this agent)
                    models = [m["id"] for m in response.json().get("data", [])]
                    # Put popular/free models at the top
                    priority_models = ["google/gemini-2.0-flash-001", "google/gemini-2.5-flash", "deepseek/deepseek-chat"]
                    other_models = [m for m in models if m not in priority_models]
                    return priority_models + sorted(other_models)
                return ["google/gemini-2.0-flash-001"] # Fallback
            except Exception as e:
                print(f"Error fetching OpenRouter models: {e}")
                return ["google/gemini-2.0-flash-001"]
        elif self.provider == "ollama":
            try:
                # Cố gắng lấy danh sách model từ Ollama API
                response = requests.get(
                    self.ollama_base_url.replace("/v1", "/api/tags")
                )
                if response.status_code == 200:
                    models = [m["name"] for m in response.json().get("models", [])]
                    return sorted(models)
                return ["qwen2.5:7b"]  # Fallback
            except Exception as e:
                print(f"Error fetching Ollama models: {e}")
                return ["qwen2.5:7b"]
        elif self.provider == "groq":
            try:
                models = self.client.models.list()
                # Hiển thị toàn bộ model để người dùng tự chọn
                return [m.id for m in models.data]
            except Exception as e:
                print(f"Error fetching Groq models: {e}")
                return ["llama-3.2-11b-vision-preview"]  # Fallback
        return []

    async def generate_content(
        self, model_name, prompt, image_data=None, mime_type="image/jpeg", tools=None, history=None
    ):
        """Gửi yêu cầu generate content đến provider tương ứng."""
        if self.provider == "google":
            try:
                # Prepare conversation history for Google
                contents = []
                if history:
                    for msg in history:
                        role = "user" if msg["role"] in ["user", "system"] else "model"
                        parts = [{"text": msg["content"]}]
                        
                        # Assistant tool calls
                        if "tool_calls" in msg and msg["role"] == "assistant":
                            for tc in msg["tool_calls"]:
                                parts.append({
                                    "function_call": {
                                        "name": tc["name"],
                                        "args": tc["arguments"]
                                    }
                                })
                        
                        # Tool execution results (from the system/user side)
                        if msg["role"] == "tool":
                            role = "user" 
                            parts = [{
                                "function_response": {
                                    "name": msg["name"],
                                    "response": {"result": msg["content"]}
                                }
                            }]
                            
                        contents.append({"role": role, "parts": parts})

                # Current observation
                current_parts = [{"text": prompt}]
                if image_data:
                    current_parts.append(types.Part.from_bytes(data=image_data, mime_type=mime_type))
                
                contents.append({"role": "user", "parts": current_parts})
                
                config_kwargs = {
                    "temperature": 0.1,
                }
                
                if tools:
                    # Chuyển đổi tool schema sang định dạng Google SDK
                    google_tools = [{"function_declarations": tools}]
                    config_kwargs["tools"] = google_tools
                else:
                    # Chỉ dùng JSON mode nếu không có tools
                    config_kwargs["response_mime_type"] = "application/json"

                response = self.google_client.models.generate_content(
                    model=model_name, 
                    contents=contents,
                    config=types.GenerateContentConfig(**config_kwargs)
                )
                
                # Trả về tool_calls nếu có, nếu không trả về text
                if response.candidates[0].content.parts[0].function_call:
                    tool_calls = []
                    import uuid
                    for part in response.candidates[0].content.parts:
                        if part.function_call:
                            tool_calls.append({
                                "id": str(uuid.uuid4())[:8],
                                "name": part.function_call.name,
                                "arguments": part.function_call.args
                            })
                    import json
                    return json.dumps({
                        "thought": response.candidates[0].content.parts[0].text if len(response.candidates[0].content.parts) > 1 else "Executing tools...",
                        "tool_calls": tool_calls
                    })
                
                return response.text
            except Exception as e:
                print(f"Error generating content with Google: {e}")
                return f"[[API_ERROR]]: {str(e)}"

        elif self.provider == "openrouter":
            import base64
            import json
            import uuid

            messages = []
            
            # Add history if provided
            if history:
                for msg in history:
                    msg_obj = {"role": msg["role"], "content": msg["content"]}
                    
                    # Handle assistant tool calls in history
                    if msg["role"] == "assistant" and "tool_calls" in msg:
                        msg_obj["tool_calls"] = []
                        for tc in msg["tool_calls"]:
                            msg_obj["tool_calls"].append({
                                "id": tc.get("id", str(uuid.uuid4())[:8]),
                                "type": "function",
                                "function": {
                                    "name": tc["name"],
                                    "arguments": json.dumps(tc["arguments"])
                                }
                            })
                    
                    # Handle tool results in history
                    if msg["role"] == "tool":
                        msg_obj["tool_call_id"] = msg.get("tool_call_id", "no_id")
                        msg_obj["name"] = msg["name"]
                        
                    messages.append(msg_obj)

            # Add current observation
            content = [{"type": "text", "text": prompt}]
            if image_data:
                base64_image = base64.b64encode(image_data).decode("utf-8")
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{base64_image}"},
                })
            messages.append({"role": "user", "content": content})

            kwargs = {
                "model": model_name,
                "messages": messages,
                "max_tokens": 2048,
                "temperature": 0.1,
            }

            if tools:
                # OpenRouter/OpenAI format for tools
                kwargs["tools"] = [{"type": "function", "function": t} for t in tools]
                kwargs["tool_choice"] = "auto"
            else:
                # Force JSON mode for text-only reasoning
                kwargs["response_format"] = {"type": "json_object"}

            try:
                response = self.client.chat.completions.create(**kwargs)
                message = response.choices[0].message
                
                if message.tool_calls:
                    tool_calls = []
                    for tc in message.tool_calls:
                        tool_calls.append({
                            "id": tc.id or str(uuid.uuid4())[:8],
                            "name": tc.function.name,
                            "arguments": json.loads(tc.function.arguments)
                        })
                    return json.dumps({
                        "thought": message.content or "Executing tools...",
                        "tool_calls": tool_calls
                    })
                
                return message.content
            except Exception as e:
                print(f"Error generating content with OpenRouter: {e}")
                return f"[[API_ERROR]]: {str(e)}"

        # Fallback cho các provider khác chưa hỗ trợ tool calling mượt mà
        if self.provider == "ollama":
            import base64
            url = self.ollama_base_url.replace("/v1", "/api/chat")
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": "You are a JSON-only API. Output ONLY the JSON object."},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "options": {"temperature": 0.1},
            }
            if image_data:
                payload["messages"][0]["images"] = [base64.b64encode(image_data).decode("utf-8")]
            try:
                response = requests.post(url, json=payload)
                return response.json().get("message", {}).get("content", "") if response.status_code == 200 else f"[[API_ERROR]]: {response.text}"
            except Exception as e: return f"[[API_ERROR]]: {str(e)}"

        elif self.provider == "groq":
            import base64
            import json
            import uuid
            
            messages = []
            # Add history
            if history:
                for msg in history:
                    messages.append({"role": msg["role"], "content": msg["content"]})
            
            # Add current observation
            content = [{"type": "text", "text": prompt}]
            if image_data:
                base64_image = base64.b64encode(image_data).decode("utf-8")
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{base64_image}"},
                })
            messages.append({"role": "user", "content": content})
            
            kwargs = {
                "model": model_name,
                "messages": messages,
                "temperature": 0.1,
            }
            
            if tools:
                kwargs["tools"] = [{"type": "function", "function": t} for t in tools]
                kwargs["tool_choice"] = "auto"
            else:
                kwargs["response_format"] = {"type": "json_object"}
                
            try:
                response = self.client.chat.completions.create(**kwargs)
                message = response.choices[0].message
                
                if message.tool_calls:
                    tool_calls = []
                    for tc in message.tool_calls:
                        tool_calls.append({
                            "id": tc.id or str(uuid.uuid4())[:8],
                            "name": tc.function.name,
                            "arguments": json.loads(tc.function.arguments)
                        })
                    return json.dumps({
                        "thought": message.content or "Executing tools...",
                        "tool_calls": tool_calls
                    })
                return message.content
            except Exception as e:
                return f"[[API_ERROR]]: {str(e)}"

        return ""
