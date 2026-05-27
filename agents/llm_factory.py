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
        self.groq_key = os.getenv("GROQ_API_KEY")

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
        elif self.provider == "groq":
            if not self.groq_key:
                raise ValueError("GROQ_API_KEY is not set in .env")
            self.client = OpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=self.groq_key,
            )
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    # ------------------------------------------------------------------
    # Dynamic Model Routing — Auto-detect provider from model name
    # ------------------------------------------------------------------
    @staticmethod
    def get_provider_for_model(model_name: str) -> str:
        """Infer which provider/client to use based on the model name string.

        Priority rules (checked in order):
          1. Explicit OpenRouter prefix  "google/...", "anthropic/...", "openai/..."
          2. Google native prefix        "gemini-...", "gemma-..."
          3. Anthropic model names       "claude-..."
          4. OpenAI model names          "gpt-...", "o1", "o3"
          5. Groq model names            "llama-...", "mixtral-..."
          6. Fall back to .env provider
        """
        if not model_name:
            return os.getenv("LLM_PROVIDER", "openrouter").lower()

        m = model_name.lower()

        # Explicit vendor-prefixed OpenRouter IDs
        openrouter_prefixes = (
            "google/", "anthropic/", "openai/", "meta-llama/",
            "mistralai/", "deepseek/", "cohere/", "qwen/", "x-ai/",
        )
        if any(m.startswith(p) for p in openrouter_prefixes):
            return "openrouter"

        # Google native SDK models
        if m.startswith(("gemini-", "gemma-", "models/gemini", "models/gemma")):
            return "google"

        # Anthropic (Claude)
        if m.startswith("claude-"):
            return "openrouter"  # Claude via OpenRouter

        # OpenAI
        if m.startswith(("gpt-", "o1-", "o3-", "o1", "o3")):
            return "openrouter"  # GPT via OpenRouter

        # Groq
        groq_keywords = ("llama-", "mixtral", "llama3", "llama2", "whisper")
        if any(k in m for k in groq_keywords):
            return "groq"

        # Default to configured provider
        return os.getenv("LLM_PROVIDER", "openrouter").lower()

    def _get_openrouter_client(self) -> OpenAI:
        """Lazily return (or create) the OpenRouter client."""
        if hasattr(self, "client") and self.provider == "openrouter":
            return self.client
        key = self.openrouter_key
        if not key:
            raise ValueError("OPENROUTER_API_KEY not set")
        return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key)

    def _get_google_client(self):
        """Lazily return (or create) the Google Generative AI client."""
        if hasattr(self, "google_client"):
            return self.google_client
        if not self.google_key:
            raise ValueError("GOOGLE_API_KEY not set")
        return genai.Client(api_key=self.google_key)

    def _get_groq_client(self) -> OpenAI:
        """Lazily return (or create) the Groq client."""
        if hasattr(self, "client") and self.provider == "groq":
            return self.client
        if not self.groq_key:
            raise ValueError("GROQ_API_KEY not set")
        return OpenAI(base_url="https://api.groq.com/openai/v1", api_key=self.groq_key)


    def get_available_models(self, vision_only: bool = False):
        """Lấy danh sách các model khả dụng dựa trên provider và hỗ trợ xử lý hình ảnh (Vision)."""
        if self.provider == "google":
            models = []
            try:
                # Sử dụng SDK genai mới
                for m in self.google_client.models.list():
                    if "generateContent" in m.supported_actions:
                        if vision_only:
                            if "gemini" in m.name:
                                models.append(m.name.replace("models/", ""))
                        else:
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
                    all_models = response.json().get("data", [])
                    models = []
                    for m in all_models:
                        if vision_only:
                            supported_params = m.get("supported_parameters", [])
                            if isinstance(supported_params, list) and "vision" in supported_params:
                                models.append(m["id"])
                            elif any(x in m["id"].lower() for x in ["vision", "claude-3", "gpt-4o", "gemini"]):
                                models.append(m["id"])
                        else:
                            models.append(m["id"])
                    
                    # Put popular/free models at the top
                    priority_models = ["google/gemini-3.1-flash-lite", "google/gemini-2.0-flash-001", "google/gemini-2.5-flash"]
                    valid_priority = [m for m in priority_models if m in models]
                    other_models = [m for m in models if m not in valid_priority]
                    return valid_priority + sorted(other_models)
                return ["google/gemini-2.0-flash-001"] # Fallback
            except Exception as e:
                print(f"Error fetching OpenRouter models: {e}")
                return ["google/gemini-2.0-flash-001"]
        elif self.provider == "groq":
            try:
                models = self.client.models.list()
                if vision_only:
                    # Lọc ra các model có chữ vision hoặc llava
                    vision_models = [m.id for m in models.data if "vision" in m.id.lower() or "llava" in m.id.lower()]
                    return sorted(vision_models) if vision_models else ["llama-3.2-11b-vision-preview"]
                return sorted([m.id for m in models.data])
            except Exception as e:
                print(f"Error fetching Groq models: {e}")
                return ["llama-3.2-11b-vision-preview"]
        return []


    async def generate_content(
        self, model_name, prompt, image_data=None, mime_type="image/jpeg", tools=None, history=None
    ):
        """Send a generate content request — auto-routes to the correct provider based on model_name.

        Dynamic Model Routing:
          If model_name belongs to a different provider than self.provider (set via .env),
          this method temporarily overrides the provider for this call only.
          This allows brain_model and eval_model to use different providers simultaneously.
        """
        # --- Dynamic provider override ---
        effective_provider = self.get_provider_for_model(model_name)
        if effective_provider != self.provider:
            # Route to the correct backend without changing self.provider
            return await self._generate_with_provider(
                provider=effective_provider,
                model_name=model_name,
                prompt=prompt,
                image_data=image_data,
                mime_type=mime_type,
                tools=tools,
                history=history,
            )

        # --- Default: use self.provider (original dispatch logic below) ---
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
                "max_tokens": 8192,
                "temperature": 0.1,
            }

            if tools:
                # OpenRouter/OpenAI format for tools
                kwargs["tools"] = [{"type": "function", "function": t} for t in tools]
                kwargs["tool_choice"] = "auto"
            
            # Luôn áp dụng JSON mode để đảm bảo phản hồi text là JSON hợp lệ
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

    async def _generate_with_provider(
        self, provider: str, model_name: str, prompt: str,
        image_data=None, mime_type="image/jpeg", tools=None, history=None
    ) -> str:
        """Internal dispatcher: generate content using an explicit provider client.

        Used by generate_content() when the requested model belongs to a
        different provider than self.provider (Dynamic Model Routing).
        """
        import base64 as _b64
        import json
        import uuid as _uuid

        # --- Google ---
        if provider == "google":
            try:
                google_client = self._get_google_client()
                contents = []
                if history:
                    for msg in history:
                        role = "user" if msg["role"] in ["user", "system"] else "model"
                        parts = [{"text": msg.get("content", "")}]
                        if msg["role"] == "tool":
                            role = "user"
                            parts = [{"function_response": {"name": msg["name"], "response": {"result": msg["content"]}}}]
                        contents.append({"role": role, "parts": parts})

                current_parts = [{"text": prompt}]
                if image_data:
                    current_parts.append(types.Part.from_bytes(data=image_data, mime_type=mime_type))
                contents.append({"role": "user", "parts": current_parts})

                config_kwargs = {"temperature": 0.1}
                if tools:
                    config_kwargs["tools"] = [{"function_declarations": tools}]
                else:
                    config_kwargs["response_mime_type"] = "application/json"

                response = google_client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(**config_kwargs)
                )
                parts = response.candidates[0].content.parts
                if parts and parts[0].function_call:
                    tcs = []
                    for part in parts:
                        if part.function_call:
                            tcs.append({
                                "id": str(_uuid.uuid4())[:8],
                                "name": part.function_call.name,
                                "arguments": part.function_call.args,
                            })
                    return json.dumps({"thought": "Executing tools...", "tool_calls": tcs})
                return response.text
            except Exception as e:
                return f"[[API_ERROR]]: {str(e)}"

        # --- OpenRouter (handles anthropic, openai, google/, etc.) ---
        if provider == "openrouter":
            try:
                or_client = self._get_openrouter_client()
                messages = []
                if history:
                    for msg in history:
                        m = {"role": msg["role"], "content": msg.get("content", "")}
                        if msg["role"] == "assistant" and "tool_calls" in msg:
                            m["tool_calls"] = [{
                                "id": tc.get("id", str(_uuid.uuid4())[:8]),
                                "type": "function",
                                "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])}
                            } for tc in msg["tool_calls"]]
                        if msg["role"] == "tool":
                            m["tool_call_id"] = msg.get("tool_call_id", "no_id")
                            m["name"] = msg["name"]
                        messages.append(m)

                content = [{"type": "text", "text": prompt}]
                if image_data:
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{_b64.b64encode(image_data).decode()}"}
                    })
                messages.append({"role": "user", "content": content})

                kwargs = {"model": model_name, "messages": messages, "max_tokens": 4096, "temperature": 0.1}
                if tools:
                    kwargs["tools"] = [{"type": "function", "function": t} for t in tools]
                    kwargs["tool_choice"] = "auto"
                else:
                    kwargs["response_format"] = {"type": "json_object"}

                response = or_client.chat.completions.create(**kwargs)
                message = response.choices[0].message
                if message.tool_calls:
                    tcs = [
                        {
                            "id": tc.id or str(_uuid.uuid4())[:8],
                            "name": tc.function.name,
                            "arguments": json.loads(tc.function.arguments),
                        }
                        for tc in message.tool_calls
                    ]
                    return json.dumps({"thought": message.content or "Executing tools...", "tool_calls": tcs})
                return message.content
            except Exception as e:
                return f"[[API_ERROR]]: {str(e)}"

        # --- Groq ---
        if provider == "groq":
            try:
                groq_client = self._get_groq_client()
                messages = []
                if history:
                    for msg in history:
                        messages.append({"role": msg["role"], "content": msg.get("content", "")})
                content = [{"type": "text", "text": prompt}]
                if image_data:
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{_b64.b64encode(image_data).decode()}"}
                    })
                messages.append({"role": "user", "content": content})
                kwargs = {"model": model_name, "messages": messages, "temperature": 0.1}
                if tools:
                    kwargs["tools"] = [{"type": "function", "function": t} for t in tools]
                    kwargs["tool_choice"] = "auto"
                else:
                    kwargs["response_format"] = {"type": "json_object"}
                response = groq_client.chat.completions.create(**kwargs)
                message = response.choices[0].message
                if message.tool_calls:
                    tcs = [
                        {
                            "id": tc.id or str(_uuid.uuid4())[:8],
                            "name": tc.function.name,
                            "arguments": json.loads(tc.function.arguments),
                        }
                        for tc in message.tool_calls
                    ]
                    return json.dumps({"thought": message.content or "Executing tools...", "tool_calls": tcs})
                return message.content
            except Exception as e:
                return f"[[API_ERROR]]: {str(e)}"

        return f"[[API_ERROR]]: No handler for provider '{provider}'"
