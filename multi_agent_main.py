import logging
import asyncio

# 1. BỘ LỌC LOG SIÊU SẠCH
class CleanAgentFilter(logging.Filter):
    def filter(self, record):
        # Đổi tên mọi thứ liên quan đến Agent thành [UItester1]
        if 'Agent' in record.name or 'browser_use' in record.name:
            record.name = "UItester1"
        
        # Tắt các log kỹ thuật không cần thiết để đỡ rối mắt
        noise = ['httpx', 'BrowserSession', 'Selector', 'Navigation', 'element_tree', 'telemetry', 'cdp_use']
        if any(x in record.msg for x in noise) or any(x in record.name for x in noise):
            return False 
            
        # Làm sạch nội dung: Xóa các mã hex loằng ngoằng như 8d0f, aefc
        import re
        if isinstance(record.msg, str):
            record.msg = re.sub(r'[🅰🅑🅣]\s[a-f0-9]{4}', '', record.msg)
            record.msg = re.sub(r'⇢\s[a-f0-9]{4}', '', record.msg)
        
        return True

# Thiết lập logging: Ép buộc dùng cấu hình này cho mọi thư viện
handler = logging.StreamHandler()
handler.addFilter(CleanAgentFilter())
logging.basicConfig(
    level=logging.INFO, 
    format='%(levelname)-8s [%(name)s] %(message)s',
    handlers=[handler],
    force=True 
)

# 2. IMPORT SAU KHI ĐÃ CẤU HÌNH LOG
from dotenv import load_dotenv
from multi_agent import build_graph, AgentState

load_dotenv()

async def run_team(task: str):
    print("\n" + "🚀 " + "=" * 57)
    print("🤖 HỆ THỐNG AI AGENT ĐANG KHỞI CHẠY...")
    print("=" * 60 + "\n")

    graph = build_graph()
    target_url = "https://www.3dart.vn/"
    
    initial_state: AgentState = {
        "target_url": target_url,
        "pending_urls": [target_url],
        "tested_urls": [],
        "results_map": {},
        "security_memories": {},
        "active_agents_count": 0,
        "final_report": None,
        "history": [],
        "iteration": 0,
    }

    await graph.ainvoke(initial_state)
    print("\n" + "🏁 " + "=" * 57)
    print("TẤT CẢ CÔNG VIỆC ĐÃ HOÀN TẤT.")
    print("=" * 60)

if __name__ == "__main__":
    TASK = "Vào trang https://www.3dart.vn/ test xem có button nào lỗi không"
    asyncio.run(run_team(TASK))
