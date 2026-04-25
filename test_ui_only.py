import asyncio
import logging
from browser_use import Agent, ChatOpenAI
from tools.controller import controller
import tools.testUI


# FILTER NÂNG CẤP: Quét mọi logger có tên liên quan đến Agent
class AgentNameFilter(logging.Filter):
    def __init__(self, name):
        super().__init__()
        self.agent_name = name

    def filter(self, record):
        # Nếu tên logger có chứa 'Agent', đổi thành tên Agent của mình
        if "Agent" in record.name:
            record.name = record.name.replace("Agent", self.agent_name)
        # Nếu tên logger có chứa 'tools', gắn tên Agent vào trước
        if "tools" in record.name:
            record.name = f"{self.agent_name}:tools"
        return True


async def main():
    agent_name = "UItester1"
    url = "https://www.3dart.vn/"

    # KÍCH HOẠT ĐỔI TÊN TRÊN TOÀN HỆ THỐNG LOGGING
    # Ta lấy logger gốc của browser_use để đảm bảo bao phủ hết các module con
    root_logger = logging.getLogger()
    agent_filter = AgentNameFilter(agent_name)
    root_logger.addFilter(agent_filter)

    print("\n" + "=" * 60)
    print(f"🚀 ĐANG CHẠY TEST VỚI TÊN: {agent_name}")
    print("=" * 60 + "\n")

    try:
        agent = Agent(
            task=f"Truy cập {url} và sử dụng tool get_all_links để lấy danh sách URL nội bộ và in ra màn hình.",
            llm=ChatOpenAI(model="gpt-4o"),
            controller=controller,
        )
        await agent.run(max_steps=5)
    finally:
        root_logger.removeFilter(agent_filter)


if __name__ == "__main__":
    # Đảm bảo logging ở mức INFO để thấy được kết quả
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)-8s [%(name)s] %(message)s"
    )
    asyncio.run(main())
