"""
BFS Crawler State Manager
Quản lý hàng đợi URL (global_url_queue) và kế hoạch trang (current_page_plan)
để Agent có thể kiểm thử website một cách có hệ thống.
"""
from urllib.parse import urlparse


MAX_QUEUE_SIZE = 20  # Giới hạn tối đa số URL trong queue

# Keywords to identify destructive or forbidden actions
DESTRUCTIVE_KEYWORDS = [
    "đăng xuất", "logout", "log out", "sign out", "signout",
    "đổi mật khẩu", "thay đổi mật khẩu", "change password", "update password", "reset password"
]

import re

def normalize_selector(selector: str) -> str:
    """
    Chuẩn hóa selector thành một định dạng canonical duy nhất.
    Đặc biệt trích xuất text từ các Playwright pseudo-classes:
    - a:has-text("Submit") -> text='submit'
    - button:has-text('submit ') -> text='submit'
    - text="SUBMIT" -> text='submit'
    """
    if not selector or not isinstance(selector, str):
        return ""
    
    # 1. Trích xuất text content từ các pattern phổ biến của Playwright
    text_patterns = [
        r"text=['\"](.+?)['\"]",             # text="content"
        r":has-text\(['\"](.+?)['\"]\)",     # :has-text("content")
        r"text=(.+)$"                        # text=content (unquoted)
    ]
    
    for pattern in text_patterns:
        match = re.search(pattern, selector, re.IGNORECASE)
        if match:
            content = match.group(1).strip().lower()
            if content:
                # Trả về format chuẩn text='content'
                return f"text='{content}'"

    # 2. Nếu không tìm thấy text pattern, chuẩn hóa CSS selector thuần
    # Loại bỏ tag name nếu có :has-text đi kèm (ví dụ a:has-text -> :has-text)
    selector = re.sub(r'^[a-zA-Z0-9]+:has-text', ':has-text', selector)
    
    # Chuẩn hóa dấu nháy và khoảng trắng
    selector = selector.replace('"', "'").strip().lower()
    selector = re.sub(r'\s+', ' ', selector)
    
    # Loại bỏ các class động thường gặp có thể gây nhiễu loop detection
    selector = re.sub(r'\.(active|hover|focus|show|open|expanded|loading|is-active)\b', '', selector)
    
    return selector


def is_destructive_element(element_text: str, href: str = "") -> bool:
    """Kiểm tra xem một phần tử có phải là nút Logout/Đăng xuất không để tránh vòng lặp."""
    text_lower = str(element_text or "").lower().strip()
    href_lower = str(href or "").lower().strip()
    
    # Kiểm tra trong text
    if any(keyword in text_lower for keyword in DESTRUCTIVE_KEYWORDS):
        return True
        
    # Kiểm tra trong href
    if any(keyword in href_lower for keyword in DESTRUCTIVE_KEYWORDS):
        return True
        
    return False


def get_domain(url: str) -> str:
    """Lấy domain chính từ URL (ví dụ: example.com)"""
    if not url: return ""
    
    # Nếu không có scheme, urlparse sẽ không lấy được netloc
    if "://" not in url:
        # Giả định đây là domain hoặc path
        domain = url.split("/")[0]
    else:
        parsed = urlparse(url)
        domain = parsed.netloc
        
    return domain.split(":")[0].strip().replace("www.", "")


def normalize_url(url: str) -> str:
    """Chuẩn hóa URL để tránh trùng lặp (bỏ trailing slash, fragment)."""
    try:
        parsed = urlparse(url)
        # Bỏ fragment (#section), giữ path
        path = parsed.path.rstrip("/") or "/"
        return f"{parsed.scheme}://{parsed.netloc}{path}"
    except:
        return url


# ============================================
# URL Queue Management
# ============================================

def add_url(queue: list, url: str, base_domain: str) -> bool:
    """
    Thêm URL mới vào queue nếu:
    - Cùng domain với base
    - Chưa tồn tại trong queue
    - Queue chưa đầy
    Returns True nếu thêm thành công.
    """
    if not url or url == "about:blank":
        return False
    
    # Kiểm tra domain
    url_domain = get_domain(url)
    if url_domain != get_domain(base_domain):
        return False
    
    # Chuẩn hóa
    normalized = normalize_url(url)
    
    # Kiểm tra trùng
    existing_urls = [normalize_url(item["url"]) for item in queue]
    if normalized in existing_urls:
        return False
    
    # Kiểm tra giới hạn
    if len(queue) >= MAX_QUEUE_SIZE:
        return False
    
    queue.append({
        "url": url,
        "status": "pending",  # pending | testing | tested
        "title": ""
    })
    print(f"🔗 New URL discovered: {url} (Queue: {len(queue)}/{MAX_QUEUE_SIZE})")
    return True


def get_next_pending(queue: list) -> dict | None:
    """Lấy URL pending tiếp theo trong queue."""
    for item in queue:
        if item["status"] == "pending":
            return item
    return None


def mark_url_status(queue: list, url: str, status: str):
    """Đánh dấu trạng thái của URL trong queue."""
    normalized = normalize_url(url)
    for item in queue:
        if normalize_url(item["url"]) == normalized:
            item["status"] = status
            return


def get_queue_summary(queue: list) -> str:
    """Tạo bản tóm tắt queue cho AI prompt."""
    if not queue:
        return "No URLs in queue."
    
    pending = sum(1 for q in queue if q["status"] == "pending")
    testing = sum(1 for q in queue if q["status"] == "testing")
    tested = sum(1 for q in queue if q["status"] == "tested")
    
    lines = [f"📊 URL Queue: {tested} tested, {testing} testing, {pending} pending (Total: {len(queue)}/{MAX_QUEUE_SIZE})"]
    for q in queue:
        icon = {"pending": "⏳", "testing": "🔄", "tested": "✅"}.get(q["status"], "❓")
        lines.append(f"  {icon} {q['url']}")
    
    return "\n".join(lines)


def get_base_identifier(item: dict) -> str:
    """Tạo ID duy nhất dựa trên nội dung, thẻ và ngữ cảnh để tránh lọc nhầm."""
    text = str(item.get("text", "")).strip().lower()
    href = str(item.get("href", "")).strip().lower()
    tag = str(item.get("tag", "")).strip().upper()
    context = str(item.get("context", "")).strip().lower()
    
    # Rút gọn href: bỏ domain, giữ path + query
    base_href = href
    if href and "://" in href:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(href)
            base_href = parsed.path
            if parsed.query:
                base_href += "?" + parsed.query
        except:
            pass
    
    # Chuẩn hóa javascript:void(0)
    if "javascript:void(0)" in href or "void(0)" in href:
        base_href = "js:void"
    
    return f"{tag}|{text}|{base_href}|{context}".lower()


def create_page_plan(dom_elements: list, current_url: str = "", blacklist=None):
    """
    Tạo danh sách các bước cần thực hiện trên 1 trang từ raw data.
    """
    if blacklist is None:
        blacklist = []
        
    plan = []
    if not isinstance(dom_elements, list):
        return plan
    
    for el in dom_elements:
        try:
            tag = el.get("tagName", "unknown").upper()
            text = el.get("text", "Unnamed")
            css_selector = el.get("bestSelector", "")
            href = el.get("href", "")
            rect = el.get("rect")
            
            # Final selector
            if css_selector and css_selector != "text=":
                selector = css_selector
            else:
                selector = f'text="{text}"'
            
            # Bỏ qua các phần tử thuần text (Headings, Breadcrumbs, etc.)
            if tag in ["HEADING", "SPAN", "DIV", "P"]:
                is_btn_sel = any(kw in css_selector.lower() for kw in ["button", "btn", "role", "onclick"])
                if not href and not is_btn_sel:
                    continue
            
            # [HARD FILTER] Bỏ qua các phần tử hình nền, ảnh trang trí
            decorative_keywords = ["bg-", "background", "image", "img", "icon", "svg", "logo"]
            if any(kw in text.lower() for kw in decorative_keywords) or ".jpg" in text.lower() or ".png" in text.lower():
                continue

            # Bỏ qua các phần tử quá ngắn hoặc mang tính phá hủy (Logout)
            if len(text) < 2 or text in ["Unnamed", "Image"] or is_destructive_element(text, href):
                continue

            # [CONTEXT DETECTION] Phân biệt Điều hướng vs Hành động
            context = "Hành động chính"
            # Nhận diện Breadcrumb mạnh tay hơn
            is_breadcrumb = "breadcrumb" in css_selector.lower() or "breadcrumb" in href.lower() or (tag == "A" and href == "/")
            is_sidebar = el.get("is_sidebar", False)
            
            if is_breadcrumb:
                context = "Liên kết điều hướng (Breadcrumb/Trang chủ)"
            elif is_sidebar:
                context = "Menu điều hướng (Sidebar)"
            elif tag == "A" and href and not any(kw in href.lower() for kw in ["add", "edit", "submit", "save", "delete", "create", "post", "put"]):
                # Nếu là link A mà không có từ khóa hành động -> Thường là Navigation
                context = "Liên kết điều hướng"
            elif tag == "BUTTON" or "btn" in css_selector.lower() or "ivu-btn" in css_selector.lower() or "submit" in css_selector.lower():
                context = "Nút chức năng"
            
            # Tạo item tạm thời để tính base_id
            temp_item = {"text": text, "href": href, "context": context}
            base_id = get_base_identifier(temp_item)

            # Bỏ qua trùng lặp
            existing_ids = [p.get("base_id") for p in plan]
            if base_id in existing_ids or base_id in blacklist:
                continue

            plan.append({
                "selector": selector,
                "text": text,
                "tag": tag,
                "href": href,
                "url": current_url, # Inject current URL
                "base_id": base_id,
                "context": context,
                "status": "unclicked",
                "rect": rect,
                "is_sidebar": el.get("is_sidebar", False)
            })
        except Exception:
            continue
    
    print(f"📋 Page plan created: {len(plan)} interactive elements")
    return plan


def get_next_unclicked(plan: list) -> dict | None:
    """Lấy phần tử unclicked tiếp theo trong page plan."""
    for item in plan:
        if item["status"] == "unclicked":
            return item
    return None


def mark_element_status(plan: list, selector: str, status: str):
    """
    Đánh dấu trạng thái phần tử trong page plan.
    Sử dụng canonical normalization để đảm bảo khớp đúng ngay cả khi AI dùng selector khác format.
    """
    if not selector or not plan:
        return
        
    norm_target = normalize_selector(selector)
    
    # 1. First pass: Canonical matches
    for item in plan:
        if not isinstance(item, dict): continue
        
        # Thử khớp với selector gốc, text gốc, hoặc canonical selector
        if (normalize_selector(item.get("selector")) == norm_target or 
            normalize_selector(item.get("text")) == norm_target or
            item.get("selector") == selector or
            item.get("text") == selector):
            
            item["status"] = status
            return
            
    # 2. Second pass: Fuzzy match for text (nếu canonical không khớp)
    for item in plan:
        if not isinstance(item, dict): continue
        item_text = str(item.get("text", "")).lower()
        if item_text and item_text in norm_target.lower() and len(item_text) > 3:
            item["status"] = status
            return


def get_plan_summary(plan: list) -> str:
    """Tạo bản tóm tắt page plan cho AI prompt."""
    if not plan:
        return "No elements in current page plan."
    
    unclicked = sum(1 for p in plan if p["status"] == "unclicked")
    clicked = sum(1 for p in plan if p["status"] == "clicked")
    skipped = sum(1 for p in plan if p["status"] == "skipped")
    
    lines = [f"📋 Page Plan: {clicked} clicked, {skipped} skipped, {unclicked} remaining"]
    for p in plan:
        icon = {"unclicked": "⬜", "clicked": "✅", "skipped": "⏭️"}.get(p["status"], "❓")
        context_info = f" ({p.get('context', 'Action')})" if p.get('context') else ""
        som_id_str = f" [ID: {p.get('som_id')}]" if p.get('som_id') else ""
        lines.append(f"  {icon}{som_id_str} [{p['tag']}] '{p['text']}'{context_info} → {p['selector']}")
    
    return "\n".join(lines)


def is_page_complete(plan: list) -> bool:
    """Kiểm tra xem tất cả phần tử đã được click/skip chưa."""
    if not plan:
        return True
    return all(p["status"] in ["clicked", "skipped"] for p in plan)


def detect_plan_refresh(current_plan: list, dom_elements: list) -> list:
    """
    So sánh DOM mới quét được với page plan hiện tại.
    - LUÔN cập nhật tọa độ rect cho các phần tử cũ nếu chúng vẫn tồn tại.
    - Nếu phát hiện nội dung thay đổi đáng kể (>30%), rebuild page plan.
    """
    if not current_plan or not dom_elements:
        return current_plan
    
    # 1. Tạo plan mới để so sánh
    new_plan = create_page_plan(dom_elements)
    if not new_plan:
        return current_plan
    
    # Tạo map từ new_plan để tra cứu nhanh (key = base_id)
    new_map = {p["base_id"]: p for p in new_plan}
    
    # 2. Cập nhật tọa độ cho các phần tử trong plan hiện tại
    for item in current_plan:
        if item["base_id"] in new_map:
            # Cập nhật rect mới nhất để SOM marker vẽ đúng vị trí
            item["rect"] = new_map[item["base_id"]]["rect"]

    # 3. Tính tỷ lệ thay đổi để quyết định có refresh cấu trúc không
    old_ids = {p["base_id"] for p in current_plan}
    new_ids = {p["base_id"] for p in new_plan}
    
    added = new_ids - old_ids
    removed = old_ids - new_ids
    
    total_elements = len(old_ids | new_ids)
    if total_elements == 0: return current_plan
    
    change_ratio = (len(added) + len(removed)) / total_elements
    CHANGE_THRESHOLD = 0.30
    
    if change_ratio >= CHANGE_THRESHOLD:
        print(f"🔄 DOM CHANGE DETECTED! {len(added)} new, {len(removed)} removed "
              f"({change_ratio:.0%} changed) → Refreshing page plan.")
        
        # Giữ status từ plan cũ
        old_status_map = {p["base_id"]: p["status"] for p in current_plan}
        for item in new_plan:
            if item["base_id"] in old_status_map:
                item["status"] = old_status_map[item["base_id"]]
        
        return new_plan
    
    return current_plan
