import asyncio
import os
import argparse
from dotenv import load_dotenv
from agents.llm_factory import LLMFactory
from multi_agent.graph import create_graph
from tools.browser_manager import BrowserManager

load_dotenv()
llm_factory = LLMFactory()

def get_available_models():
    """Fetch available models from current provider."""
    return llm_factory.get_available_models()

async def run_agent(state: dict):
    app = create_graph()
    
    print(f"🚀 Starting Multi-Agent Graph with model: {state['model_name']}...")
    async for event in app.astream(state):
        for node_name, state in event.items():
            print(f"--- Node Finished: {node_name} ---")
            
    # Browser remains open for potential next tasks
    print("🏁 Execution complete. Browser remains open.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Security Agent Tester")
    parser.add_argument("--url", help="Target website URL")
    parser.add_argument("--goal", help="Custom goal for the agent")
    parser.add_argument("--model", help="Model name (e.g., google/gemini-2.0-flash-001)")
    parser.add_argument("--security", action="store_true", help="Enable security testing")
    parser.add_argument("--ui", action="store_true", help="Enable UI testing")
    parser.add_argument("--login-user", help="Login username")
    parser.add_argument("--login-pass", help="Login password")
    
    args = parser.parse_args()
    
    print("--- 🛠️ INITIALIZING AGENT TESTER ---")
    
    # 1. Select Model
    available_models = get_available_models()
    selected_model = args.model
    if not selected_model:
        # Default fallback or interactive if no model provided and no args
        if not args.url:
            print("\n🤖 AVAILABLE MODELS:")
            for i, m in enumerate(available_models, 1):
                print(f"  {i}. {m}")
            try:
                choice = int(input(f"\n👉 Select model number (1-{len(available_models)}): "))
                selected_model = available_models[choice - 1]
            except:
                selected_model = "google/gemini-2.0-flash-001"
        else:
            selected_model = "google/gemini-2.0-flash-001"

    # 2. Setup URL and Goal
    url = args.url
    if not url:
        url = input("\n👉 Enter target website URL: ")
    
    if not url.startswith("http"):
        url = "https://" + url
        
    goal = args.goal or "Thực hiện kiểm thử toàn diện UI và bảo mật. Khám phá các luồng chính trước, sau đó tập trung vào security testing (XSS, SQLi)."
    
    initial_state = {
        "model_name": selected_model,
        "goal": goal,
        "mode": "test_web",
        "url": url,
        "base_url": url,
        "screenshot": None,
        "dom_elements": None,
        "next_action": None,
        "history": [],
        "last_thought": None,
        "findings": [],
        "is_complete": False,
        "global_url_queue": [],
        "clicked_selectors_blacklist": [],
        "testing_url": url,
        "phase": "planning",
        "security_steps": 0,
        "test_ui": args.ui or True,
        "test_security": args.security or True,
        "login_user": args.login_user,
        "login_pass": args.login_pass,
        "logged_in": False,
        "master_plan": [],
        "login_steps": 0,
        "login_attempts": 0,
        "path_steps": [],
        "current_step_index": 0,
        "security_memory": []
    }
    
    asyncio.run(run_agent(initial_state))
