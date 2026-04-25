import os
import json
from browser_use import Controller
from pydantic import BaseModel, Field


class ButtonTestParams(BaseModel):
    button_name: str = Field(..., description="Tên hoặc nhãn của nút bấm vừa test")
    status: str = Field(..., description="Trạng thái: 'hoạt động' hoặc 'không hoạt động'")
    details: str = Field(..., description="Chi tiết lỗi nếu có hoặc mô tả hành động sau khi bấm")


def register_click_button_tool(controller: Controller):
    @controller.registry.action(
        "Ghi lại kết quả kiểm thử của một nút bấm cụ thể",
        param_model=ButtonTestParams,
    )
    async def record_button_test(params: ButtonTestParams) -> str:
        """
        Dùng để ghi lại lịch sử bấm nút. Giúp Agent không bị quên các nút đã test.
        """
        os.makedirs("logs", exist_ok=True)
        
        log_entry = {
            "button": params.button_name,
            "status": params.status,
            "details": params.details
        }
        
        with open("logs/button_test_history.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            
        print(f"✅ [Click Tool] Đã ghi nhận: {params.button_name} -> {params.status}")
        return f"Đã ghi lại kết quả cho nút '{params.button_name}'."
