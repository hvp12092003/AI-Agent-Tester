import os
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")

if not api_key:
    print("❌ Lỗi: Không tìm thấy GOOGLE_API_KEY trong file .env")
else:
    try:
        llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash")
        response = llm.invoke("Hello, are you working?")
        print(f"✅ API Key hợp lệ! Phản hồi từ Gemini: {response.content}")
    except Exception as e:
        print(f"❌ Lỗi API Key: {e}")
