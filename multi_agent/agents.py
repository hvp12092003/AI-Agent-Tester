import asyncio
import logging
from .state import AgentState
from browser_use import Agent, ChatOpenAI
from tools.controller import controller

# =========================================================
# 🕵️‍♂️ [MANAGER] - NODE ĐIỀU PHỐI
# =========================================================
async def supervisor_node(state: AgentState):
    if not state.get("pending_urls"):
        return {"final_report": "Tất cả các URL đã được kiểm tra."}
    
    url_to_test = state["pending_urls"].pop(0)
    print("\n" + "█" * 80)
    print(f"🕵️‍♂️ [MANAGER] >>> GIAO VIỆC CHO UItester1 <<<")
    print(f"📍 URL: {url_to_test}")
    print("█" * 80 + "\n")
    
    return {"current_url": url_to_test}

# =========================================================
# 🖥️ [UItester1] - NODE KIỂM THỬ GIAO DIỆN
# =========================================================
async def ui_tester_node(state: AgentState):
    url = state.get("current_url")
    if not url:
        return {}

    llm = ChatOpenAI(model="gpt-4o")

    try:
        # Hướng dẫn cực kỳ nghiêm khắc
        task_instruction = (
            f"NHIỆM VỤ QUAN TRỌNG:\n"
            f"1. Truy cập {url}\n"
            f"2. NGAY LẬP TỨC sử dụng tool 'get_all_links' để lấy link. "
            f"CẤM dùng tool 'search' hay 'extract'.\n"
            f"3. Sau khi có link, hãy kết thúc nhiệm vụ và in danh sách ra."
        )
        
        agent = Agent(
            task=task_instruction,
            llm=llm,
            page_extraction_llm=llm, 
            controller=controller,
            # Giảm số lượng hành động mỗi bước để nó không làm loạn
            max_actions_per_step=1,
            # Ép dùng hệ thống prompt nghiêm ngặt
            override_system_message=(
                "Bạn là một chuyên gia Automation Test. "
                "Bạn chỉ được phép sử dụng các công cụ được cung cấp bởi Controller. "
                "Đặc biệt, bạn BẮT BUỘC phải dùng 'get_all_links' để tìm liên kết nội bộ. "
                "TUYỆT ĐỐI KHÔNG sử dụng công cụ tìm kiếm bên ngoài (search) hoặc trích xuất mặc định (extract)."
            )
        )
        await agent.run(max_steps=3)

        return {"final_report": "Done"}
    except Exception as e:
        print(f"❌ Lỗi Agent: {e}")
        return {"final_report": f"Error: {e}"}
