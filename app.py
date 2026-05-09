import streamlit as st
import asyncio
import base64
import os
import threading
import time
from dotenv import load_dotenv
from multi_agent.graph import create_graph
from agents.llm_factory import LLMFactory
from tools.browser_manager import BrowserManager
from deep_translator import GoogleTranslator
from streamlit.runtime.scriptrunner import get_script_run_ctx, add_script_run_ctx

# --- TU DONG CAI DAT TRINH DUYET CHO CLOUD ---
if not os.path.exists("/tmp/playwright_installed"):
    print("Installing Playwright browsers...")
    os.system("python -m playwright install chromium")
    with open("/tmp/playwright_installed", "w") as f:
        f.write("done")

@st.cache_data
def translate_text(text, target_lang='vi'):
    if not text: return ""
    try:
        return GoogleTranslator(source='auto', target=target_lang).translate(text)
    except:
        return text

# --- CẤU HÌNH TRANG ---
st.set_page_config(
    page_title="3DArt AI Agent", 
    layout="wide", 
    page_icon="assets/ai_agent_logo.png",
    initial_sidebar_state="expanded"
)

# --- CSS CAO CẤP (GLASSMORPHISM & MODERN UI) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    .main {
        background: radial-gradient(circle at top right, #1a1c2c, #0a0c10);
    }

    /* ẨN CÁC THÀNH PHẦN STREAMLIT */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display:none;}
    [data-testid="stHeader"] {display:none;}
    .reportview-container .main .footer {display: none;}
    
    /* Tối ưu hóa không gian App */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 0rem;
    }

    /* Glassmorphism Card */
    .glass-card {
        background: rgba(22, 27, 34, 0.7);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 12px 15px;
        margin-bottom: 12px;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
    }

    /* Browser Mockup */
    .browser-frame {
        background: #2d2d2d;
        border-radius: 12px 12px 5px 5px;
        border: 1px solid #444;
        overflow: hidden;
    }
    .browser-header {
        background: #1e1e1e;
        padding: 8px 12px;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .dot { width: 12px; height: 12px; border-radius: 50%; }
    .red { background: #ff5f56; }
    .yellow { background: #ffbd2e; }
    .green { background: #27c93f; }
    .address-bar {
        background: #333;
        color: #aaa;
        padding: 4px 15px;
        border-radius: 20px;
        font-size: 11px;
        flex-grow: 1;
        margin-left: 10px;
        border: 1px solid #444;
        font-family: monospace;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    /* Action Log Labels */
    .action-badge {
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 10px;
        font-weight: 600;
        text-transform: uppercase;
        margin-right: 5px;
    }
    .badge-vision { background: #ffbd2e; color: black; }
    .badge-manager { background: #27c93f; color: white; }
    .badge-action { background: #00d4ff; color: black; }

    /* Pulsing Status */
    .status-pulse {
        display: inline-block;
        width: 10px; height: 10px;
        background: #27c93f;
        border-radius: 50%;
        margin-right: 8px;
        box-shadow: 0 0 0 rgba(39, 201, 63, 0.4);
        animation: pulse 2s infinite;
    }
    @keyframes pulse {
        0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(39, 201, 63, 0.7); }
        70% { transform: scale(1); box-shadow: 0 0 0 10px rgba(39, 201, 63, 0); }
        100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(39, 201, 63, 0); }
    }

    .finding-item {
        border-left: 4px solid #ff5f56;
        background: rgba(255, 95, 86, 0.1);
        padding: 10px;
        border-radius: 0 8px 8px 0;
        margin-bottom: 8px;
        font-size: 12px;
        color: #eee;
    }

    /* Step Item in Plan */
    .step-item {
        display: flex;
        align-items: flex-start;
        gap: 8px;
        margin-bottom: 6px;
        font-size: 12px;
        padding: 4px 8px;
        border-radius: 6px;
        background: rgba(255, 255, 255, 0.03);
    }

    /* Log Item */
    .log-item {
        margin-bottom: 10px;
        padding: 8px;
        border-radius: 8px;
        background: rgba(0, 0, 0, 0.2);
        border: 1px solid rgba(255, 255, 255, 0.05);
    }
    .log-content {
        font-size: 12px;
        color: #ccc;
        line-height: 1.4;
    }

    /* Compact Sidebar */
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        gap: 0.5rem;
    }
    [data-testid="stSidebar"] {
        padding-top: 1rem;
    }
    </style>
""", unsafe_allow_html=True)

# --- KHỞI TẠO STATE ---
if "agent_state" not in st.session_state:
    st.session_state.agent_state = {
        "model_name": "", 
        "goal": "", 
        "url": "", 
        "screenshot": None,
        "history": [], 
        "last_thought": "Sẵn sàng khởi động...",
        "findings": [], 
        "is_complete": False, 
        "base_url": None,
        "dom_elements": None,
        "current_page_plan": [],
        "messages": []
    }
if "running" not in st.session_state:
    st.session_state.running = False

def auto_clear_state():
    if not st.session_state.running and st.session_state.agent_state.get("is_complete"):
        st.session_state.agent_state = {
            "model_name": "", 
            "goal": "", 
            "url": "", 
            "screenshot": None,
            "history": [], 
            "last_thought": "Tự động làm mới...",
            "findings": [], 
            "is_complete": False, 
            "base_url": None,
            "dom_elements": None,
            "current_page_plan": [],
            "messages": [],
            "task_plan": []
        }

# --- SIDEBAR (CẤU HÌNH TỐI GIẢN) ---
llm_factory = LLMFactory()
available_models = llm_factory.get_available_models()

# --- AI SUGGESTION FOR PLACEHOLDER ---
def get_ai_suggestion(model_name):
    """Lấy một câu gợi ý ngẫu nhiên từ AI để hiển thị ở Placeholder"""
    from agents.llm_factory import LLMFactory
    factory = LLMFactory()
    
    prompt = """
    Bạn là một trợ lý AI Testing chuyên nghiệp. 
    Hãy tạo ra MỘT câu gợi ý ngắn gọn (dưới 30 từ) để người dùng nhập vào ô yêu cầu.
    Câu gợi ý nên đa dạng: có thể là test bảo mật, test UI, hoặc thực hiện một tác vụ cụ thể trên web.
    Ví dụ: 'Kiểm tra lỗi hiển thị trên trang chủ 3dart.vn', 'Đăng nhập vào hệ thống quản trị và kiểm tra danh sách bài viết'.
    Hãy trả về DUY NHẤT câu gợi ý đó, không thêm gì khác. Ngôn ngữ: Tiếng Việt.
    """
    
    try:
        if factory.provider == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI
            from langchain_core.messages import HumanMessage
            clean_model = model_name.replace("models/", "").replace("google/", "")
            llm = ChatGoogleGenerativeAI(model=clean_model)
            response = llm.invoke([HumanMessage(content=prompt)])
            return response.content.strip().replace('"', '')
        elif factory.provider == "openrouter":
            import requests
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {factory.openrouter_key}"},
                json={
                    "model": model_name,
                    "messages": [{"role": "user", "content": prompt}]
                }
            )
            return response.json()['choices'][0]['message']['content'].strip().replace('"', '')
        return "Nhập yêu cầu của bạn tại đây... (Ví dụ: Test bảo mật trang abc.com)"
    except:
        return "Nhập yêu cầu của bạn tại đây... (Ví dụ: Test bảo mật trang abc.com)"

if "placeholder_suggestion" not in st.session_state:
    st.session_state.placeholder_suggestion = get_ai_suggestion(available_models[0])

with st.sidebar:
    st.image("assets/ai_agent_logo.png", width=120)
    st.markdown("""
        <div style="margin-top: -15px; margin-bottom: -10px;">
            <h3 style="margin: 0; background: linear-gradient(90deg, #3e44fe, #00d4ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 700; font-size: 20px;">3DArt AI Agent</h3>
        </div>
    """, unsafe_allow_html=True)
    
    selected_model = st.selectbox("🤖 Model AI", available_models, index=0, key="selected_model", on_change=auto_clear_state)

    st.markdown("---")
    st.markdown("#### 📝 Nhập yêu cầu của bạn:")
    user_prompt = st.text_area(
        "Agent sẽ tự phân tích URL, tài khoản và nhiệm vụ.",
        placeholder=st.session_state.placeholder_suggestion,
        height=200,
        key="user_prompt"
    )
    
    st.caption("💡 Mẹo: Bạn có thể nhập ngôn ngữ tự nhiên, Agent sẽ tự hiểu URL và thông tin đăng nhập.")
    
    # Luôn bật chế độ dịch sang tiếng Việt mặc định
    auto_translate = True
    
    st.markdown("---")
    col_s1, col_s2, col_s3 = st.columns(3)
    start_btn = col_s1.button("🚀 CHẠY", type="primary", use_container_width=True, disabled=st.session_state.running)
    stop_btn = col_s2.button("🛑 DỪNG", type="secondary", use_container_width=True, disabled=not st.session_state.running)
    clear_btn = col_s3.button("🧹 XOÁ", type="secondary", use_container_width=True, disabled=st.session_state.running)

# --- AI INTENT ANALYZER ---
def analyze_user_prompt(prompt, model_name):
    """Sử dụng LLMFactory để bóc tách thông tin từ prompt của người dùng"""
    import json
    from agents.llm_factory import LLMFactory
    
    factory = LLMFactory()
    
    system_instruction = """
    Phân tích yêu cầu người dùng và trả về JSON chính xác.
    Quy tắc:
    - url: Tìm URL trang web (nếu có).
    - goal: Mục tiêu ngắn gọn bằng tiếng Anh.
    - login_user: Tài khoản (nếu có).
    - login_pass: Mật khẩu (nếu có).
    - is_web_test: true nếu là yêu cầu audit/test web toàn diện, false nếu là nhiệm vụ cụ thể (linear task).
    - test_ui: true/false.
    - test_security: true/false.
    
    JSON Format:
    {
        "url": "...",
        "goal": "...",
        "login_user": "...",
        "login_pass": "...",
        "is_web_test": true,
        "test_ui": true,
        "test_security": true
    }
    """
    
    # Sử dụng phương thức generate_content của factory (async wrapper)
    # Vì hàm này không async, ta dùng logic sync hoặc gọi trực tiếp nếu factory hỗ trợ
    # Ở đây tôi sẽ dùng logic đơn giản để gọi LLM
    
    try:
        # Gọi qua factory (generate_content là async, nhưng ở đây ta cần kết quả ngay)
        # Tạm thời dùng logic invoke trực tiếp để tránh xung đột async trong Streamlit thread
        if factory.provider == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI
            from langchain_core.messages import HumanMessage
            # Xử lý tên model nếu có prefix
            clean_model = model_name.replace("models/", "").replace("google/", "")
            llm = ChatGoogleGenerativeAI(model=clean_model)
            response = llm.invoke([HumanMessage(content=f"{system_instruction}\n\nUser Prompt: {prompt}")])
            content = response.content
        elif factory.provider == "openrouter":
            import requests
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {factory.openrouter_key}"},
                json={
                    "model": model_name,
                    "messages": [{"role": "user", "content": f"{system_instruction}\n\nUser Prompt: {prompt}"}]
                }
            )
            content = response.json()['choices'][0]['message']['content']
        else:
            # Fallback cho các provider khác
            content = "{}"

        # Làm sạch chuỗi JSON nếu AI trả về kèm markdown
        clean_content = content.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_content)
    except Exception as e:
        print(f"Error in analyze_user_prompt: {e}")
        return {
            "url": None, "goal": prompt, "login_user": None, "login_pass": None,
            "is_web_test": False, "test_ui": True, "test_security": False
        }

if clear_btn:
    from tools.report_tool import cleanup_reports
    cleanup_reports()
    st.session_state.agent_state = {
        "model_name": "", 
        "goal": "", 
        "url": "", 
        "screenshot": None,
        "history": [], 
        "last_thought": "Đã làm mới...",
        "findings": [], 
        "is_complete": False, 
        "base_url": None,
        "dom_elements": None,
        "current_page_plan": [],
        "messages": []
    }
    st.rerun()

# --- LOGIC CHẠY AGENT ---
async def run_agent_async(url, goal, model, login_user=None, login_pass=None):
    from tools.report_tool import cleanup_reports
    cleanup_reports()
    app = create_graph()
    
    initial_state = {
        "goal": goal, 
        "url": url, 
        "screenshot": None, 
        "next_action": None,
        "history": [], 
        "last_thought": "Đang khởi động trình duyệt...",
        "findings": [], 
        "is_complete": False, 
        "model_name": model,
        "base_url": None, 
        "dom_elements": None,
        "current_page_plan": [], 
        "login_user": login_user, 
        "login_pass": login_pass,
        "messages": [],
        "task_plan": []
    }
    st.session_state.agent_state = initial_state
    
    try:
        async for event in app.astream(initial_state):
            if not st.session_state.running: break
            
            for node_name, state in event.items():
                # Gắn nhãn node vào lịch sử mới trước khi gộp
                if "history" in state and state["history"]:
                    new_h = state["history"]
                    for i in range(len(new_h)):
                        if isinstance(new_h[i], str) and not new_h[i].startswith("["):
                            new_h[i] = f"[{node_name.upper()}] {new_h[i]}"
                    
                    # Gộp vào history hiện tại thay vì ghi đè hoàn toàn
                    current_h = st.session_state.agent_state.get("history", [])
                    for item in new_h:
                        if item not in current_h:
                            current_h.append(item)
                    state["history"] = current_h
                
                try:
                    st.session_state.agent_state.update(state)
                except Exception:
                    pass # Ignore state updates if session is dead
                    
                await asyncio.sleep(0.1) 
                
                if st.session_state.agent_state.get("is_complete"): break
    except Exception as e:
        print(f"⚠️ Error in agent thread: {e}")
    finally:
        st.session_state.running = False
        
        # Tự động đóng trình duyệt để giải phóng bộ nhớ
        try:
            await BrowserManager.close()
        except Exception as close_err:
            print(f"⚠️ Lỗi khi đóng trình duyệt: {close_err}")
            BrowserManager.force_reset()
        print("💡 Task finished. Browser closed to free memory.")
        
        # Tự động tạo báo cáo Excel
        try:
            from tools.report_tool import generate_excel_report
            agent_state = st.session_state.agent_state
            findings = agent_state.get("findings", [])
            base_url = agent_state.get("base_url", "unknown")
            safe_domain = base_url.replace("https://", "").replace("http://", "").split("/")[0] if base_url else "unknown"
            
            excel_path = generate_excel_report(findings, title=f"TEST {safe_domain}")
            if excel_path:
                print(f"📊 Báo cáo đã được tạo tại: {excel_path}")
                agent_state["last_report_path"] = excel_path
        except Exception as report_err:
            print(f"⚠️ Lỗi khi tạo báo cáo tự động: {report_err}")

if start_btn:
    if not user_prompt:
        st.error("⚠️ Vui lòng nhập yêu cầu của bạn.")
    else:
        # ĐẢM BẢO đóng trình duyệt cũ trước khi khởi tạo mới (tránh zombie + nhân đôi UI)
        BrowserManager.force_reset()
        
        st.session_state.running = True
        with st.status("🧠 Đang phân tích yêu cầu bằng AI...", expanded=True) as status:
            analysis = analyze_user_prompt(user_prompt, selected_model)
            st.write(f"🌐 URL: `{analysis.get('url')}`")
            st.write(f"🎯 Mục tiêu: {analysis.get('goal')}")
            if analysis.get('login_user'):
                st.write(f"🔑 Tìm thấy thông tin đăng nhập cho `{analysis.get('login_user')}`")
            status.update(label="✅ Phân tích hoàn tất! Đang khởi động Agent...", state="complete", expanded=False)

        target_url = analysis.get("url")
        if target_url and not target_url.startswith("http"): 
            target_url = "https://" + target_url
        
        test_goal = analysis.get("goal")
        user_val = analysis.get("login_user")
        pass_val = analysis.get("login_pass")
        is_web_test = analysis.get("is_web_test", True)
        test_ui_checked = analysis.get("test_ui", True)
        test_sec_checked = analysis.get("test_security", True)
        
        # Xoá trạng thái cũ để UI làm mới ngay lập tức
        st.session_state.agent_state = {
            "model_name": selected_model, 
            "goal": test_goal, 
            "url": target_url, 
            "screenshot": None,
            "history": [], 
            "last_thought": "Đang kết nối trình duyệt...",
            "findings": [], 
            "is_complete": False, 
            "base_url": None,
            "dom_elements": None,
            "current_page_plan": [], 
            "login_user": user_val, 
            "login_pass": pass_val,
            "messages": [],
            "task_plan": []
        }
        
        selected_mode = "test_web" if is_web_test else "custom"
        
        # Define worker function
        def run_in_thread(url, goal, model, u_val, p_val):
            asyncio.run(run_agent_async(url, goal, model, u_val, p_val))
        
        # Create thread and attach context
        thread = threading.Thread(target=run_in_thread, args=(
            target_url, test_goal, selected_model, user_val, pass_val
        ))
        ctx = get_script_run_ctx()
        add_script_run_ctx(thread, ctx)
        thread.start()

if stop_btn:
    st.session_state.running = False
    if "agent_state" in st.session_state:
        st.session_state.agent_state["is_complete"] = True
    
    # Đóng trình duyệt test trong một thread riêng để tránh block Streamlit
    def _close_browser_sync():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(BrowserManager.close())
            loop.close()
        except Exception as e:
            print(f"⚠️ Lỗi khi đóng trình duyệt: {e}")
            BrowserManager.force_reset()
    
    close_thread = threading.Thread(target=_close_browser_sync, daemon=True)
    close_thread.start()
    close_thread.join(timeout=5)  # Chờ tối đa 5 giây
    
    st.rerun()

# --- GIAO DIỆN CHÍNH (SỬ DỤNG PLACEHOLDER ĐỂ TRÁNH NHÂN ĐÔI) ---
main_placeholder = st.empty()

with main_placeholder.container():
    c1, c2 = st.columns([2, 1])

    with c1:
        # Header Status
        status_text = "Đang hoạt động" if st.session_state.running else "Đang chờ"
        st.markdown(f"""
            <div style="display: flex; align-items: center; margin-bottom: 10px;">
                <div class="status-pulse" style="background: {'#27c93f' if st.session_state.running else '#ff5f56'}"></div>
                <h2 style="margin: 0; font-size: 20px;">{status_text}</h2>
            </div>
        """, unsafe_allow_html=True)

        # Browser Mockup View
        st.markdown(f"""
            <div class="browser-frame">
                <div class="browser-header">
                    <div class="dot red"></div><div class="dot yellow"></div><div class="dot green"></div>
                    <div class="address-bar">{st.session_state.agent_state['url'] or 'about:blank'}</div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        screenshot_placeholder = st.empty()
        if st.session_state.agent_state["screenshot"]:
            image_bytes = base64.b64decode(st.session_state.agent_state["screenshot"])
            screenshot_placeholder.image(image_bytes, width="stretch")
        else:
            screenshot_placeholder.info("Chưa có hình ảnh. Nhấn 'CHẠY' để kích hoạt Agent.")

    with c2:
        # 1. Master Plan View
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown("<h4 style='margin:0 0 10px 0;'>📋 Kế hoạch thực hiện</h4>", unsafe_allow_html=True)
        t_plan = st.session_state.agent_state.get("task_plan", [])
        if t_plan:
            for step in t_plan:
                status = step.get("status", "todo")
                if status == "done":
                    status_icon = "✅"
                    color = "#00ff88"
                elif status == "doing":
                    status_icon = "⏳"
                    color = "#00d4ff"
                elif status == "failed":
                    status_icon = "❌"
                    color = "#ff5f56"
                else:
                    status_icon = "⚪"
                    color = "#888"
                
                # Translate step description to Vietnamese
                task_vn = translate_text(step.get('step', ''))
                st.markdown(f"""
                    <div class="step-item">
                        <span>{status_icon}</span>
                        <span style="color:{color};">{task_vn}</span>
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown("<p style='font-size:12px; color:#888;'>Đang lập kế hoạch...</p>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # 2. Brain View (Status)
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown("<h4 style='margin:0 0 5px 0;'>🧠 Trạng thái Agent</h4>", unsafe_allow_html=True)
        
        current_thought = st.session_state.agent_state["last_thought"]
        
        if current_thought:
            translated = translate_text(current_thought)
            st.markdown(f"<div style='font-size:13px; color:#00d4ff; border-left:2px solid #3e44fe; padding-left:8px; margin-bottom:4px; font-weight:600;'>{translated}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div style='font-size:13px; color:#00d4ff; border-left:2px solid #3e44fe; padding-left:8px;'>Đang chờ phản hồi...</div>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # 3. DOM Plan View
        plan = st.session_state.agent_state.get("current_page_plan", [])
        if plan:
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            st.markdown(f"<h4 style='margin:0 0 5px 0;'>🔍 Các phần tử trên trang</h4>", unsafe_allow_html=True)
            tested_elements = sum(1 for p in plan if p.get("status") in ["clicked", "skipped"])
            total_elements = len(plan)
            st.progress(tested_elements / total_elements if total_elements > 0 else 0)
            st.markdown(f"<p style='font-size:11px; margin:2px 0;'>📋 <b>Thành phần giao diện:</b> {total_elements} phần tử đã gán ID SOM</p>", unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        # 4. Findings View
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown("<h4 style='margin:0 0 5px 0;'>⚠️ Phát hiện lỗi</h4>", unsafe_allow_html=True)
        if st.session_state.agent_state["findings"]:
            for f in st.session_state.agent_state["findings"]:
                f_text = f["text"] if isinstance(f, dict) else f
                f_vn = translate_text(f_text)
                st.markdown(f'<div class="finding-item">{f_vn}</div>', unsafe_allow_html=True)
        else:
            st.markdown("<p style='font-size:12px; color:#888;'>Chưa phát hiện lỗi nào.</p>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # 5. Timeline/History View
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown("<h4 style='margin:0 0 10px 0;'>📜 Nhật ký hành động</h4>", unsafe_allow_html=True)
        with st.container(height=350):
            history_data = st.session_state.agent_state.get("history", [])
            if not history_data:
                st.markdown("<p style='font-size:12px; color:#888;'>Chưa có hành động nào.</p>", unsafe_allow_html=True)
            else:
                for h in reversed(history_data):
                    if not isinstance(h, str): continue
                    
                    # Identify node
                    # Identify node by content/icon
                    if any(kw in h for kw in ["quét trang", "mở trang", "mục có thể"]): 
                        label = '<span class="action-badge badge-vision">Mắt Thần</span>'
                    elif any(kw in h for kw in ["✅", "❌", "Đã bấm", "Đã nhập", "Đã cuộn", "Đã chờ"]): 
                        label = '<span class="action-badge badge-action">Hành Động</span>'
                    else: 
                        label = '<span class="action-badge badge-manager">Suy Nghĩ</span>'
                    
                    clean_h = h.split("] ", 1)[-1] if "] " in h else h
                    # Translate log to Vietnamese
                    h_vn = translate_text(clean_h)
                    
                    st.markdown(f"""
                        <div class="log-item">
                            {label}
                            <div class="log-content">{h_vn}</div>
                        </div>
                    """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        
        # 6. Debug View (Last Prompt)
        last_prompt = st.session_state.agent_state.get("last_prompt", "")
        if last_prompt:
            with st.expander(f"🛠️ Dữ liệu gửi lên AI (Debug - {len(last_prompt)} ký tự)"):
                st.code(last_prompt, language="text")

    # ===== BÁO CÁO VÀ TẢI XUỐNG (Cũng nằm trong main_placeholder) =====
    agent_state = st.session_state.agent_state
    if agent_state.get("is_complete") and not st.session_state.running:
        st.markdown("---")
        st.markdown("## 📄 Báo cáo kiểm tra")
        
        # Generate report
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        base_url = agent_state.get("base_url", "N/A")
        queue = agent_state.get("global_url_queue", [])
        findings = agent_state.get("findings", [])
        history = agent_state.get("history", [])
        did_ui = agent_state.get("test_ui", True)
        did_sec = agent_state.get("test_security", True)
        
        # Collect timeouts, errors, closed tabs
        timeouts = [h for h in history if isinstance(h, str) and "⏱️ TIMEOUT" in h]
        errors = [h for h in history if isinstance(h, str) and "❌" in h]
        closed_tabs = [h for h in history if isinstance(h, str) and "🗑️" in h]
        
        tested_urls = "\n".join([f"  - ✅ {q['url']}" for q in queue if q['status'] == 'tested'])
        
        scope_text = []
        if did_ui: scope_text.append("Kiểm tra UI/UX (Duyệt BFS)")
        if did_sec: scope_text.append("Kiểm tra Bảo mật (XSS, SQLi, Path Traversal)")
        
        report = f"""# 📋 BÁO CÁO KIỂM TRA WEBSITE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 Thời gian: {now}
🌐 URL mục tiêu: {base_url}
🔍 Phạm vi kiểm tra: {', '.join(scope_text)}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## 📊 Tổng quan
- Tổng số trang đã quét: {len(queue)}
- Phát hiện lỗi: {len(findings)}
- Timeout: {len(timeouts)}
- Lỗi tương tác: {len(errors)}
- Tab mới đã đóng: {len(closed_tabs)}

## 🌐 Danh sách URL đã kiểm tra
{tested_urls}

## 🚨 Phát hiện lỗi ({len(findings)})
"""
        if findings:
            for i, f in enumerate(findings, 1):
                if isinstance(f, dict):
                    report += f"\n### {i}. {f['text']}"
                    report += f"\n- **URL**: {f['url']}"
                    report += f"\n- **Thời gian**: {f.get('timestamp', 'N/A')}"
                else:
                    report += f"\n{i}. {f}"
        else:
            report += "\n✅ Không phát hiện lỗi bảo mật hoặc UI nghiêm trọng."
        
        if timeouts:
            report += f"\n\n## ⏱️ Timeout ({len(timeouts)})"
            for t in timeouts:
                clean_t = t.split("] ", 1)[-1] if "] " in t else t
                report += f"\n- {clean_t}"
        
        if closed_tabs:
            report += f"\n\n## 🗑️ Tab mới đã đóng ({len(closed_tabs)})"
            for ct in closed_tabs:
                clean_ct = ct.split("] ", 1)[-1] if "] " in ct else ct
                report += f"\n- {clean_ct}"
                
        # Extract detailed action steps
        action_steps = [h for h in history if isinstance(h, str) and not h.startswith("🤖 AI") and "Screenshot:" not in h]
        if action_steps:
            report += f"\n\n## 👣 Chi tiết các bước thao tác\n"
            for step in action_steps:
                # Remove prefixes like [ACTION], [MANAGER], [VISION] or [Step X]
                clean_step = step
                if "] " in clean_step:
                    clean_step = clean_step.split("] ", 1)[-1]
                
                # Further cleanup of any remaining technical bits
                clean_step = clean_step.replace("--- Result: ", "").replace("---", "").strip()
                
                # Translate to Vietnamese for the report
                step_vn = translate_text(clean_step)
                if step_vn: report += f"- {step_vn}\n"

        report += f"\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n✍️ Báo cáo tự động bởi 3DArt AI Agent\n⏰ {now}\n"
        
        with st.expander("👁️ Xem nhanh báo cáo", expanded=False):
            st.markdown(report)
            if findings:
                st.markdown("---")
                st.markdown("### 📸 Ảnh minh chứng phát hiện lỗi")
                for f in findings:
                    if isinstance(f, dict) and f.get('screenshot') and os.path.exists(f['screenshot']):
                        st.image(f['screenshot'], caption=f"⚠️ {f['text']} (tại {f['url']})")
        
        # Download buttons
        safe_base_url = base_url.replace('https://', '').replace('/', '_') if base_url else "agent"
        report_filename = f"report_{safe_base_url}_{datetime.now().strftime('%Y%m%d_%H%M')}"
        col_dl1, col_dl2 = st.columns(2)
        
        col_dl1.download_button(label="⬇️ Tải báo cáo (.txt)", data=report, file_name=f"{report_filename}.txt", mime="text/plain", use_container_width=True)
        
        from tools.report_tool import generate_excel_report
        safe_domain = base_url.replace("https://", "").replace("http://", "").split("/")[0] if base_url else "unknown"
        excel_path = generate_excel_report(findings, title=f"TEST {safe_domain}")
        if excel_path and os.path.exists(excel_path):
            with open(excel_path, "rb") as file:
                col_dl2.download_button(label="📊 Tải báo cáo (.xlsx)", data=file, file_name=os.path.basename(excel_path), mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", use_container_width=True)
        
        if st.button("🗑️ Xóa toàn bộ ảnh minh chứng và tệp tạm thời", use_container_width=True):
            from tools.report_tool import cleanup_reports
            cleanup_reports()
            st.success("Đã xóa toàn bộ dữ liệu tạm thời.")
            st.rerun()

# Tự động làm mới
if st.session_state.running:
    time.sleep(2.0) # Tăng lên 2s để ổn định hơn
    st.rerun()
