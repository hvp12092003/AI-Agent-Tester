import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

print("Listing models with new SDK:")
models = list(client.models.list())
if models:
    m = models[0]
    print(f"Name: {m.name}")
    # Print as dict to see all fields
    try:
        print(f"Fields: {m.model_dump()}")
    except:
        print(f"Dir: {dir(m)}")
else:
    print("No models found")
