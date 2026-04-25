import requests
import datetime
import re
from browser_use import Controller
from pydantic import BaseModel, Field


# 1. Bổ sung Field để Agent hiểu cách truyền URL
class SecurityScanParams(BaseModel):
    url: str = Field(
        ...,
        description="Đường dẫn URL của trang web cần quét bảo mật (VD: https://3dart.vn)",
    )


def register_security_tools(controller: Controller):
    @controller.registry.action(
        "Thực hiện quét bảo mật thụ động (Passive Scan) cho website tĩnh",
        param_model=SecurityScanParams,
    )
    async def scan_static_web_security(params: SecurityScanParams) -> str:
        """
        Thực hiện kiểm tra bảo mật cơ bản: Header, rò rỉ phiên bản Server, và lộ file nhạy cảm.
        """
        url = params.url
        if not url.startswith("http"):
            url = "https://" + url

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        report = [f"## 🛡️ BÁO CÁO QUÉT BẢO MẬT TĨNH"]
        report.append(f"- **Mục tiêu:** {url}")
        report.append(f"- **Thời gian:** {timestamp}\n")

        # Fake User-Agent để tránh bị WAF (Cloudflare, AWS) chặn ngay từ vòng gửi xe
        headers_req = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
        }

        try:
            # Tăng timeout lên 1 chút để tránh lỗi với các server phản hồi chậm
            report.append("### 1. Phân tích Security Headers")
            response = requests.get(url, headers=headers_req, timeout=10, verify=True)
            headers = response.headers

            security_headers = {
                "Content-Security-Policy": "CSP (Chính sách bảo mật nội dung)",
                "X-Frame-Options": "X-Frame-Options (Chống Clickjacking)",
                "Strict-Transport-Security": "HSTS (Bảo mật truyền tải)",
                "X-Content-Type-Options": "X-Content-Type-Options (Chống MIME sniffing)",
            }

            for header, description in security_headers.items():
                if header in headers:
                    report.append(f"- 🟢 **PASS**: {header} hiện diện.")
                else:
                    report.append(f"- 🔴 **FAIL**: Thiếu {header} ({description}).")

            report.append("\n### 2. Kiểm tra rò rỉ thông tin Server")
            server_headers = ["Server", "X-Powered-By"]
            leaks_found = False
            for sh in server_headers:
                val = headers.get(sh)
                if val:
                    if re.search(r"\d+\.\d+", val):
                        report.append(
                            f"- ⚠️ **CẢNH BÁO**: Rò rỉ phiên bản chi tiết trong '{sh}': `{val}`"
                        )
                        leaks_found = True
                    else:
                        report.append(
                            f"- ✅ {sh}: `{val}` (Không chứa phiên bản chi tiết)"
                        )
            if not leaks_found and not any(h in headers for h in server_headers):
                report.append("- ✅ Không tìm thấy chữ ký Server nhạy cảm.")

            report.append("\n### 3. Kiểm tra lộ file nhạy cảm (Exposure Check)")
            sensitive_paths = {
                "/.env": "File môi trường (Chứa Secret Key)",
                "/.git/HEAD": "Thư mục mã nguồn Git",
                "/robots.txt": "File chỉ dẫn Robot",
            }

            base_url = url.rstrip("/")
            for path, desc in sensitive_paths.items():
                try:
                    test_url = base_url + path
                    # allow_redirects=False để tránh báo cáo nhầm do redirect về trang chủ
                    res = requests.get(
                        test_url, headers=headers_req, timeout=5, allow_redirects=False
                    )

                    if res.status_code == 200:
                        # File .env/.git thường là text/plain hoặc application/octet-stream, không phải text/html
                        content_type = res.headers.get("Content-Type", "")
                        if (
                            path in ["/.env", "/.git/HEAD"]
                            and "text/html" not in content_type
                        ):
                            report.append(
                                f"- 🚨 **NGUY HIỂM**: Phát hiện lộ file `{path}`! ({desc})"
                            )
                        elif path == "/robots.txt":
                            report.append(
                                f"- ℹ️ Phát hiện file `{path}` (Trạng thái bình thường)."
                            )
                        else:
                            report.append(
                                f"- ✅ Không tìm thấy `{path}` (Có thể là Soft 404)."
                            )
                    else:
                        report.append(
                            f"- ✅ Không tìm thấy `{path}` (Mã lỗi {res.status_code})."
                        )
                except requests.exceptions.RequestException:
                    report.append(f"- ⚪ Không thể kết nối để kiểm tra `{path}`")

        except Exception as e:
            return f"❌ Lỗi khi thực hiện quét bảo mật: {str(e)}"

        return "\n".join(report)
