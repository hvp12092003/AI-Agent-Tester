import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# Lấy key từ .env (giả định đã được uncomment hoặc lấy thủ công nếu cần)
# Ở đây tôi sẽ thử đọc file .env để lấy key bị comment
with open(".env", "r") as f:
    lines = f.readlines()
    google_key = None
    for line in lines:
        if "GOOGLE_API_KEY" in line:
            google_key = line.split("=")[1].strip().replace("#", "").strip()
            break

if google_key:
    print(f"Testing key: {google_key[:10]}...")
    genai.configure(api_key=google_key)
    print("Listing available models:")
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                print(f" - {m.name}")
    except Exception as e:
        print(f"Error listing models: {e}")
else:
    print("No GOOGLE_API_KEY found in .env")
