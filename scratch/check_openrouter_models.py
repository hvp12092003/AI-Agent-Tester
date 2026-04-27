import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("OPENROUTER_API_KEY")
response = requests.get(
    url="https://openrouter.ai/api/v1/models",
    headers={
        "Authorization": f"Bearer {api_key}",
    }
)

if response.status_code == 200:
    data = response.json()
    models = [m['id'] for m in data['data']]
    
    target_models = [
        "google/gemini-2.0-flash-001",
        "google/gemini-2.0-pro-exp-02-05:free",
        "anthropic/claude-3.5-sonnet",
        "openai/gpt-4o",
        "meta-llama/llama-3.3-70b-instruct",
        "deepseek/deepseek-chat"
    ]
    
    print("Checking specific models:")
    for m in target_models:
        status = "AVAILABLE" if m in models else "NOT FOUND"
        print(f" - {m}: {status}")
    
    # Search for any google models
    google_models = [m for m in models if 'google' in m or 'gemini' in m]
    print("\nGoogle/Gemini models:")
    for m in google_models:
        print(f" - {m}")
else:
    print(f"Error: {response.status_code}")
    print(response.text)
