import asyncio
import os
from dotenv import load_dotenv
from agents.llm_factory import LLMFactory
from multi_agent.graph import create_graph
from tools.browser_manager import BrowserManager

load_dotenv()
llm_factory = LLMFactory()

def get_available_models():
    """Lấy danh sách các model có thể sử dụng từ provider hiện tại."""
    return llm_factory.get_available_models()

async def run_agent(goal: str, url: str, model_name: str):
    app = create_graph()
    
    initial_state = {
        "goal": goal,
        "url": url,
        "screenshot": None,
        "next_action": None,
        "history": [],
        "is_complete": False,
        "model_name": model_name
    }
    
    print(f"🚀 Bắt đầu chạy Multi-Agent Graph với model: {model_name}...")
    async for event in app.astream(initial_state):
        for node_name, state in event.items():
            print(f"--- Kết thúc Node: {node_name} ---")
            
    await BrowserManager.close()
    print("🏁 Toàn bộ quy trình đã kết thúc.")

if __name__ == "__main__":
    # Yêu cầu người dùng nhập thông tin từ bàn phím
    print("--- 🛠️ KHỞI TẠO AGENT TESTER ---")
    
    # 1. Chọn Model
    available_models = get_available_models()
    print("\n🤖 DANH SÁCH MODEL KHẢ DỤNG:")
    for i, m in enumerate(available_models, 1):
        print(f"  {i}. {m}")
    
    try:
        choice = int(input(f"\n👉 Chọn số thứ tự model (1-{len(available_models)}): "))
        selected_model = available_models[choice - 1]
    except:
        selected_model = "gemini-1.5-flash"
        print(f"⚠️ Lựa chọn không hợp lệ, sử dụng mặc định: {selected_model}")

    # 2. Nhập URL và Goal
    url = input("\n👉 Nhập URL trang web muốn test: ")
    goal = input("👉 Nhập mục tiêu bạn muốn Agent thực hiện: ")
    
    if not url.startswith("http"):
        url = "https://" + url
        
    asyncio.run(run_agent(goal, url, selected_model))
