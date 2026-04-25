import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=api_key)

try:
    models = client.models.list()
    print("✅ API Key hợp lệ! Đã kết nối thành công.")
except Exception as e:
    print(f"❌ Lỗi API Key: {e}")
