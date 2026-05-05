from tools.browser_manager import BrowserManager
import asyncio
import re
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def inject_visual_effects(page):
    """Inject helper functions to show visual effects. Effects are short-lived to avoid polluting screenshots."""
    await page.evaluate("""
        // Function to create or update virtual cursor
        window.updateVirtualCursor = (x, y) => {
            let cursor = document.getElementById('ai-virtual-cursor');
            if (!cursor) {
                cursor = document.createElement('div');
                cursor.id = 'ai-virtual-cursor';
                cursor.style.position = 'fixed';
                cursor.style.width = '20px';
                cursor.style.height = '20px';
                cursor.style.borderRadius = '50%';
                cursor.style.backgroundColor = 'rgba(255, 0, 0, 0.7)';
                cursor.style.border = '2px solid white';
                cursor.style.pointerEvents = 'none';
                cursor.style.zIndex = '1000000';
                cursor.style.transition = 'all 0.3s ease-out';
                cursor.style.boxShadow = '0 0 10px red';
                document.body.appendChild(cursor);
            }
            cursor.style.left = (x - 10) + 'px';
            cursor.style.top = (y - 10) + 'px';
        };

        window.showClickEffect = (x, y) => {
            window.updateVirtualCursor(x, y);
            const div = document.createElement('div');
            div.className = 'ai-effect-overlay';
            div.style.position = 'fixed';
            div.style.left = (x - 30) + 'px';
            div.style.top = (y - 30) + 'px';
            div.style.width = '60px';
            div.style.height = '60px';
            div.style.borderRadius = '50%';
            div.style.border = '4px solid red';
            div.style.backgroundColor = 'rgba(255, 0, 0, 0.15)';
            div.style.pointerEvents = 'none';
            div.style.zIndex = '999999';
            document.body.appendChild(div);
            setTimeout(() => div.remove(), 800);
        };

        window.showScrollEffect = (direction) => {
            const div = document.createElement('div');
            div.className = 'ai-effect-overlay';
            div.innerHTML = direction === 'down' ? '⬇️' : '⬆️';
            div.style.position = 'fixed';
            div.style.right = '20px';
            div.style.bottom = '20px';
            div.style.padding = '10px';
            div.style.background = 'rgba(0,0,0,0.5)';
            div.style.color = 'white';
            div.style.borderRadius = '8px';
            div.style.fontSize = '24px';
            div.style.zIndex = '1000001';
            div.style.pointerEvents = 'none';
            document.body.appendChild(div);
            setTimeout(() => div.remove(), 600);
        };

        // Cleanup function: remove all visual effects before screenshot
        window.cleanupEffects = () => {
            document.querySelectorAll('.ai-effect-overlay, #ai-virtual-cursor').forEach(el => el.remove());
        };
    """)


def xpath_escape(text):
    """
    Escape text for use in XPath expressions.
    Handles mixed single and double quotes.
    """
    if '"' not in text:
        return f'"{text}"'
    if "'" not in text:
        return f"'{text}'"
    # Mixed quotes: use concat()
    parts = text.split('"')
    return "concat(" + ",'\"',".join(f'"{p}"' for p in parts) + ")"


async def _resolve_input_element(page, element, original_selector=""):
    """
    Nếu element tìm được không phải input/textarea/select (ví dụ: div wrapper),
    thử tìm input/textarea con bên trong.
    Hỗ trợ cả Locator, ElementHandle và JSHandle.
    """
    try:
        # [FIX] as_element() trong Playwright Python KHÔNG phải là coroutine. KHÔNG được await.
        if hasattr(element, "as_element"):
            el_handle = element.as_element()
            if el_handle:
                element = el_handle

        # [ROBUST] Kiểm tra nếu là Locator thì convert sang ElementHandle để dùng evaluate
        if hasattr(element, "element_handle"):
            el_handle = await element.element_handle()
            if el_handle:
                element = el_handle

        tag = await element.evaluate("el => el.tagName")
        if tag.upper() in ["INPUT", "TEXTAREA", "SELECT"] or await element.evaluate(
            "el => el.isContentEditable"
        ):
            return element

        # Thử tìm input/textarea con bên trong (xử lý wrapper của iView, Ant Design, Bootstrap)
        # Sử dụng evaluate để tìm thay vì query_selector để tương thích tốt hơn với handles
        child_input = await element.evaluate_handle("""el => {
            // 1. Tìm input/textarea/select trực tiếp
            let found = el.querySelector("input, textarea, select, [contenteditable='true']");
            if (found) return found;
            
            // 2. Tìm theo class framework phổ biến
            return el.querySelector(".ivu-input, .ant-input, .el-input__inner, .form-control, .input");
        }""")

        if child_input:
            is_null = await child_input.evaluate("el => el === null")
            if not is_null:
                child_el = child_input.as_element()
                if child_el:
                    child_tag = await child_el.evaluate("el => el.tagName")
                    print(
                        f"🔍 Resolved wrapper → found <{child_tag}> inside '{original_selector}'"
                    )
                    return child_el

    except Exception as e:
        logger.warning(f"⚠️ _resolve_input_element error: {e}")
    return element


async def _pick_best_locator(loc_all, clean_text=None):
    """Helper to pick the first visible locator from a set, or fallback to the first hidden one."""
    count = await loc_all.count()
    if count == 0:
        return None

    # 1. Try to find a visible one that is NOT a breadcrumb
    for i in range(count):
        cand = loc_all.nth(i)
        if await cand.is_visible():
            is_breadcrumb = await cand.evaluate(
                "el => !!el.closest('.breadcrumb, .ivu-breadcrumb, .breadcrumb-item')"
            )
            if not is_breadcrumb:
                return cand

    # 2. Try any visible one
    visible_loc = loc_all.filter(visible=True)
    if await visible_loc.count() > 0:
        return visible_loc.first

    # 3. Fallback to the very first one (even if hidden)
    return loc_all.first


async def find_element(page, selector, action_type=None):
    """Helper to find element with fallback logic (main page, text=, iframes)."""

    # 0. Tự động dẹp các bảng thông báo Cookie (YouTube, Google, v.v.)
    cookie_selectors = [
        "button[aria-label='Accept all']",
        "button[aria-label='Chấp nhận tất cả']",
        "button:has-text('Accept all')",
        "button:has-text('I agree')",
        "#L2AGLb",  # ID phổ biến của Google Cookie banner
    ]
    for cs in cookie_selectors:
        try:
            btn = await page.query_selector(cs)
            if btn and await btn.is_visible():
                await btn.click()
                await asyncio.sleep(0.5)
        except:
            pass

    if not selector:
        return None
    element = None
    clean_text = selector.replace("text=", "").strip('"').strip("'")

    # 1. Nếu là hành động TYPE, ưu tiên tìm placeholder hoặc input trước
    if action_type == "type":
        try:
            # Ưu tiên placeholder trên chính input/textarea
            loc = page.locator(
                f"input[placeholder*='{clean_text}'], textarea[placeholder*='{clean_text}']"
            )
            best = await _pick_best_locator(loc)
            if best:
                return best
        except:
            pass
        try:
            # Ưu tiên role textbox
            loc = page.get_by_role("textbox", name=clean_text)
            best = await _pick_best_locator(loc)
            if best:
                return best
        except:
            pass
        try:
            # Fallback placeholder bằng Playwright API
            loc = page.get_by_placeholder(clean_text, exact=False)
            best = await _pick_best_locator(loc)
            if best:
                return best
        except:
            pass

    # 2. Try direct selector
    try:
        # Chuyển đổi :contains sang :has-text (Playwright không hỗ trợ :contains)
        if ":contains(" in selector:
            selector = selector.replace(":contains(", ":has-text(")

        # [ROBUST] Bắt lỗi SyntaxError nếu AI cung cấp XPath sai định dạng
        # Dùng wait_for_selector cho direct selector vì nó trả về ElementHandle thật
        element = await page.wait_for_selector(selector, timeout=2000, state="attached")
        if element:
            return element
    except Exception as e:
        if "SyntaxError" in str(e) or "not a valid XPath" in str(e):
            print(
                f"⚠️ Invalid selector provided by AI: {selector}. Falling back to text search."
            )
        pass

    # 3. Smart Text Matching (Ưu tiên Interactive elements cho Click)
    try:
        if action_type == "click":
            # [CRITICAL] Danh sách các khu vực không phải là Action chính (Breadcrumbs, etc.)
            non_action_selectors = (
                ":not(.breadcrumb):not(.ivu-breadcrumb):not(.header):not(.footer)"
            )

            # 3.1. Ưu tiên các nút có class 'primary' hoặc 'btn' (thường là nút chính)
            primary_selectors = [
                "button.ivu-btn-primary",
                "button.btn-primary",
                "button.ivu-btn",
                "button[type='submit']",
                ".btn-login",
                "button.btn",
            ]
            for ps in primary_selectors:
                try:
                    loc = page.locator(
                        f"{ps}{non_action_selectors}:has-text('{clean_text}')"
                    )
                    best = await _pick_best_locator(loc)
                    if best:
                        return best
                except:
                    pass

            # 3.2. Ưu tiên các role có thể click được
            for role in ["button", "link"]:
                try:
                    loc_all = page.get_by_role(role, name=clean_text, exact=False)
                    best = await _pick_best_locator(loc_all)
                    if best:
                        return best
                except:
                    pass

            # 3.3. Thử tìm các thẻ BUTTON hoặc A chứa text này
            for tag in ["button", "a"]:
                try:
                    loc = page.locator(
                        f"{tag}{non_action_selectors}:has-text('{clean_text}')"
                    )
                    best = await _pick_best_locator(loc)
                    if best:
                        return best
                except:
                    pass

        # Fallback get_by_text
        loc_all = page.get_by_text(clean_text, exact=False)
        return await _pick_best_locator(loc_all)
    except Exception as e:
        logger.warning(f"⚠️ Text matching error: {e}")

    return None

    # 4. Search in iframes
    try:
        for frame in page.frames:
            try:
                element = await frame.wait_for_selector(
                    selector, timeout=1000, state="visible"
                )
                if element:
                    return element

                loc = frame.get_by_text(clean_text, exact=False).first
                if await loc.count() > 0:
                    return loc
            except:
                continue
    except:
        pass

    return None


async def perform_action(
    action_type: str,
    selector: str = None,
    text: str = None,
    x: int = None,
    y: int = None,
    form_data: list = None,
    is_viewport_coords: bool = False,
):
    """Execute action with extended visual effects."""
    page = await BrowserManager.get_page()
    if not page:
        return "❌ Error: Browser page not available."

    await inject_visual_effects(page)

    try:
        if action_type == "fill_form":
            if not form_data or not isinstance(form_data, list):
                return "❌ Error: 'form_data' must be a list of fields for fill_form action."

            results = []
            errors = []
            for field in form_data:
                if not isinstance(field, dict):
                    continue
                f_sel = field.get("selector")
                f_val = str(field.get("value", ""))
                f_type = str(field.get("type", "text")).lower()
                f_x = field.get("x")
                f_y = field.get("y")

                element = None
                try:
                    # 1. SOM ID Support: Resolve from coordinates if provided
                    if f_x is not None and f_y is not None:
                        try:
                            js_handle = await page.evaluate_handle(
                                "(coords) => document.elementFromPoint(coords.x, coords.y)",
                                {"x": f_x, "y": f_y}
                            )
                            element = js_handle.as_element()
                            if element:
                                print(f"🎯 Resolved field via coordinates ({f_x}, {f_y})")
                        except Exception as e:
                            print(f"⚠️ Error resolving field from coords: {e}")

                    # 2. Selector-based lookup if no element found yet
                    if not element and f_sel:
                        element = await find_element(page, f_sel, action_type="type")
                        if not element:
                            # Fallback: Nếu không tìm thấy bằng selector, thử tìm bằng text (label hoặc placeholder)
                            print(
                                f"🕵️ Field '{f_sel}' not found by selector, trying text fallback..."
                            )

                            # Làm sạch text để tìm label (bỏ selector syntax)
                            clean_text = (
                                f_sel.replace("text=", "")
                                .replace('"', "")
                                .replace("'", "")
                                .strip()
                            )
                            if (
                                "input[" in clean_text
                            ):  # Nếu là CSS selector thì lấy phần name bên trong
                                match = re.search(r"name=['\"]([^'\"]+)['\"]", clean_text)
                                if match:
                                    clean_text = match.group(1)

                            try:
                                # Tìm theo label text (Playwright native)
                                cand = page.get_by_label(clean_text, exact=False).first
                                if await cand.count() > 0:
                                    element = cand
                                
                                if not element or await element.count() == 0:
                                    # Tìm theo placeholder (Playwright native)
                                    cand = page.get_by_placeholder(
                                        clean_text, exact=False
                                    ).first
                                    if await cand.count() > 0:
                                        element = cand

                                if not element or await element.count() == 0:
                                    # Tìm theo XPath (label -> input)
                                    escaped_text = xpath_escape(clean_text)
                                    xpath_variants = [
                                        f"xpath=//label[contains(text(), {escaped_text})]/following::input[1]",
                                        f"xpath=//label[contains(text(), {escaped_text})]/parent::div//input",
                                        f"xpath=//*[contains(text(), {escaped_text})]/following::input[1]",
                                        f"xpath=//*[contains(text(), {escaped_text})]/parent::div//input",
                                    ]
                                    for xv in xpath_variants:
                                        try:
                                            cand = page.locator(xv).first
                                            if await cand.count() > 0:
                                                element = cand
                                                break
                                        except:
                                            continue

                                if not element or (hasattr(element, "count") and await element.count() == 0):
                                    # Fallback cuối cùng: Tìm phần tử có text tương tự rồi tìm input gần nó nhất qua JS
                                    try:
                                        loc_text = page.get_by_text(
                                            clean_text, exact=False
                                        ).first
                                        if await loc_text.count() > 0:
                                            print(
                                                f"🔍 Found label text '{clean_text}', searching for nearby input..."
                                            )
                                            element = await loc_text.evaluate_handle("""el => {
                                                const parent = el.closest('div, form, section') || el.parentElement;
                                                return parent.querySelector('input, textarea, select');
                                            }""")
                                    except:
                                        pass
                            except Exception as fe:
                                logger.warning(f"⚠️ Text fallback search failed: {fe}")

                    # 3. Final verification of found element
                    found = False
                    if element:
                        try:
                            if hasattr(element, "count") and await element.count() > 0:
                                found = True
                            elif not hasattr(element, "count"):
                                found = True  # JSHandle
                        except:
                            pass

                    if not found:
                        errors.append(f"Field '{f_sel or f_x}' not found")
                        continue

                    print(f"🎯 Found field: '{f_sel or f_x}'")

                    # Resolve wrapper
                    element = await _resolve_input_element(page, element, f_sel)

                    # [FAIL FAST] Check if hidden
                    if (
                        hasattr(element, "is_visible")
                        and not await element.is_visible()
                    ):
                        errors.append(
                            f"Field '{f_sel}' is HIDDEN. Open its parent menu/tab first."
                        )
                        continue

                    try:
                        await element.scroll_into_view_if_needed(timeout=3000)
                    except Exception:
                        errors.append(
                            f"Field '{f_sel}' is HIDDEN. Open its parent menu/tab first."
                        )
                        continue

                    # Ensure element is stable and clickable
                    try:
                        await element.wait_for_element_state("stable", timeout=1000)
                    except:
                        pass

                    if f_type == "text":
                        # Click to focus, wait a bit, then fill
                        await element.click(delay=100, timeout=3000)
                        await asyncio.sleep(0.3)
                        await element.fill("", timeout=3000)
                        await element.type(f_val, delay=40)
                        results.append(f"Filled '{f_sel}'")

                    elif f_type == "select":
                        await element.select_option(f_val, timeout=3000)
                        results.append(f"Selected {f_val} in '{f_sel}'")

                    elif f_type in ["checkbox", "radio"]:
                        is_checked = await element.is_checked()
                        should_check = f_val.lower() in ["true", "1", "yes", "on"]
                        if should_check and not is_checked:
                            await element.check(timeout=3000)
                            results.append(f"Checked '{f_sel}'")
                        elif not should_check and is_checked:
                            await element.uncheck(timeout=3000)
                            results.append(f"Unchecked '{f_sel}'")
                    else:
                        results.append(f"Warning: Unknown type {f_type} for '{f_sel}'")

                except Exception as e:
                    error_msg = str(e).split("\n")[0]
                    errors.append(f"Error in '{f_sel}': {error_msg}")

            # Submit logic
            click_result = ""
            
            # [PROTECTION] If no fields were successfully filled, DO NOT attempt to click the submit button
            if not results and errors:
                return (
                    f"❌ Error: Could not find any of the requested fields ({len(form_data)} fields). Not submitting. Errors: "
                    + "; ".join(errors)
                )

            # Perform click-based submission
            if x is not None and y is not None:
                try:
                    # Document-relative to Viewport-relative conversion
                    scroll_y = await page.evaluate("window.scrollY")
                    scroll_x = await page.evaluate("window.scrollX")
                    
                    # If outside viewport, scroll there first
                    viewport_height = await page.evaluate("window.innerHeight")
                    if not is_viewport_coords and (y < scroll_y or y > (scroll_y + viewport_height)):
                        await page.evaluate(f"window.scrollTo({{top: {y - 200}, behavior: 'instant'}})")
                        await asyncio.sleep(0.3)
                        scroll_y = await page.evaluate("window.scrollY")
                    
                    viewport_x = x if is_viewport_coords else x - scroll_x
                    viewport_y = y if is_viewport_coords else y - scroll_y

                    print(f"🎯 Clicking submit at Viewport (vx: {viewport_x}, vy: {viewport_y})")
                    
                    # Human-like click sequence
                    await page.mouse.move(viewport_x, viewport_y)
                    await asyncio.sleep(0.15) # hover delay
                    await page.mouse.down()
                    await asyncio.sleep(0.08) # hold delay
                    await page.mouse.up()
                    
                    await asyncio.sleep(2.0)
                    click_result = f" and clicked submit at Viewport ({viewport_x}, {viewport_y})"
                except Exception as e:
                    click_result = f" (Error clicking submit at coords: {str(e)})"
            elif selector and selector.lower() not in ["form", "none", "null"]:
                try:
                    await asyncio.sleep(0.5)
                    submit_btn = await find_element(
                        page, selector, action_type="click"
                    )

                    if submit_btn:
                        print(f"🎯 Found submit button: {selector}")
                        try:
                            # Try physical click first via bounding box
                            box = await submit_btn.bounding_box()
                            if box:
                                bx = box["x"] + box["width"] / 2
                                by = box["y"] + box["height"] / 2
                                await page.mouse.move(bx, by)
                                await asyncio.sleep(0.15)
                                await page.mouse.down()
                                await asyncio.sleep(0.08)
                                await page.mouse.up()
                            else:
                                await submit_btn.click(delay=150, force=True, timeout=3000)
                        except:
                            # JS Fallback with focus
                            try:
                                await submit_btn.evaluate("el => { el.focus(); el.click(); }")
                            except:
                                pass

                        await asyncio.sleep(2.0)
                        click_result = f" and clicked submit '{selector}'"
                    else:
                        click_result = f" (Warning: submit button '{selector}' not found)"
                except Exception as e:
                    click_result = f" (Error clicking submit: {str(e)})"

            # [REPORTING] Trả về kết quả chi tiết hơn để AI không bị nhầm lẫn
            if not results:
                status_emoji = "❌"
                summary_text = "No fields were filled"
            elif errors:
                status_emoji = "⚠️"
                summary_text = (
                    f"Partially filled ({len(results)}/{len(form_data)} fields)"
                )
            else:
                status_emoji = "✅"
                summary_text = f"Successfully filled {len(results)} fields"

            summary = f"{status_emoji} Form result: {summary_text}"
            if results:
                summary += f" ({', '.join(results)})"
            if errors:
                summary += " | ❌ Errors: " + "; ".join(errors)

            return summary + click_result

        if action_type == "click":
            target_x, target_y = x, y,
            found_element = None
            
            if target_x is None or target_y is None:
                if selector:
                    found_element = await find_element(page, selector, action_type="click")
                    if not found_element:
                        return (
                            f"❌ Not found: {selector}. Try a DIFFERENT selector or action."
                        )

                    # [FAIL FAST] Check if hidden
                    if (
                        hasattr(found_element, "is_visible")
                        and not await found_element.is_visible()
                    ):
                        return f"❌ Error: Element '{selector}' is HIDDEN. Look for a parent menu, accordion, or dropdown to click and expand first."

                    try:
                        await found_element.scroll_into_view_if_needed(timeout=3000)
                    except Exception:
                        return f"❌ Error: Element '{selector}' is HIDDEN. Look for a parent menu, accordion, or dropdown to click and expand first."
                    box = await found_element.bounding_box()
                    if box:
                        target_x = box["x"] + box["width"] / 2
                        target_y = box["y"] + box["height"] / 2

            if target_x is not None:
                # Document-relative to Viewport-relative conversion
                scroll_x = await page.evaluate("window.scrollX")
                scroll_y = await page.evaluate("window.scrollY")
                
                # If target is far outside current viewport, scroll there
                viewport_height = await page.evaluate("window.innerHeight")
                if not is_viewport_coords and (target_y < scroll_y or target_y > (scroll_y + viewport_height)):
                    await page.evaluate(f"window.scrollTo({{top: {target_y - 200}, behavior: 'instant'}})")
                    # 🚨 Settle Time
                    await asyncio.sleep(0.3)
                    scroll_x = await page.evaluate("window.scrollX")
                    scroll_y = await page.evaluate("window.scrollY")

                if not is_viewport_coords:
                    target_x -= scroll_x
                    target_y -= scroll_y

                print(f"🎯 Clicking at Viewport (vx: {target_x}, vy: {target_y}) [is_viewport={is_viewport_coords}]")

                # === OBSTRUCTION CHECK ===
                if found_element:
                    try:
                        hit_test_ok = await found_element.evaluate(
                            """(targetEl, coords) => {
                            const [tx, ty] = coords;
                            const topEl = document.elementFromPoint(tx, ty);
                            if (!topEl) return { ok: false, blockerTag: 'UNKNOWN', blockerClass: '', blockerText: '' };
                            
                            const isOk = targetEl.contains(topEl) || topEl.contains(targetEl) || targetEl === topEl;
                            return {
                                ok: isOk,
                                blockerTag: topEl.tagName,
                                blockerClass: topEl.className && typeof topEl.className === 'string' ? topEl.className.substring(0, 80) : '',
                                blockerText: (topEl.innerText || '').substring(0, 60)
                            };
                        }""",
                            [target_x, target_y],
                        )

                        if not hit_test_ok.get("ok", True):
                            blocker_tag = hit_test_ok.get("blockerTag", "?")
                            blocker_text = hit_test_ok.get("blockerText", "")
                            blocker_class = hit_test_ok.get("blockerClass", "")

                            # Harmless elements
                            harmless_blockers = [
                                "SPAN",
                                "I",
                                "svg",
                                "IMG",
                                "STRONG",
                                "EM",
                                "B",
                                "LABEL",
                            ]
                            harmless_classes = [
                                "icon",
                                "material",
                                "fa-",
                                "glyphicon",
                                "text",
                                "label",
                                "title",
                            ]

                            is_harmless = (
                                blocker_tag in harmless_blockers
                                or any(
                                    cls in str(blocker_class).lower()
                                    for cls in harmless_classes
                                )
                                or len(str(blocker_text).strip()) < 3
                            )

                            if is_harmless:
                                print(
                                    f"⚠️ Element '{selector}' covered by harmless element <{blocker_tag}>. Proceeding."
                                )
                            else:
                                print(
                                    f"🚫 BLOCKED! Element '{selector}' is covered by <{blocker_tag} class='{blocker_class}'> '{blocker_text}'"
                                )
                                return (
                                    f"❌ BLOCKED: '{selector}' bị che bởi một lớp overlay/popup "
                                    f"(<{blocker_tag} class='{blocker_class}'> '{blocker_text}')."
                                )
                    except Exception as e:
                        print(f"⚠️ Obstruction check failed ({e}), proceeding.")

                await page.evaluate(f"window.showClickEffect({target_x}, {target_y})")

            try:
                # Human-like click sequence
                await page.mouse.move(target_x, target_y)
                await asyncio.sleep(0.15) # hover delay
                await page.mouse.down()
                await asyncio.sleep(0.08) # hold delay
                await page.mouse.up()
            except Exception as e:
                print(f"⚠️ Physical click failed, trying fallbacks: {e}")
                if found_element:
                    try:
                        # Playwright click as backup
                        await found_element.click(force=True, timeout=2000)
                    except:
                        # Final JS fallback with focus
                        await found_element.evaluate("el => { el.focus(); el.click(); }")

            await asyncio.sleep(0.5)
            return f"✅ Click success: {selector if selector else f'at ({target_x}, {target_y})'}"

        elif action_type == "type":
            target_element = None
            if x is not None and y is not None:
                # Resolve element from coordinates
                try:
                    # Document-relative to Viewport-relative conversion
                    scroll_y = await page.evaluate("window.scrollY")
                    scroll_x = await page.evaluate("window.scrollX")
                    
                    # If outside viewport, scroll there first
                    viewport_height = await page.evaluate("window.innerHeight")
                    if not is_viewport_coords and (y < scroll_y or y > (scroll_y + viewport_height)):
                        await page.evaluate(f"window.scrollTo({{top: {y - 200}, behavior: 'instant'}})")
                        # 🚨 Settle Time
                        await asyncio.sleep(0.3)
                        scroll_y = await page.evaluate("window.scrollY")

                    vx = x if is_viewport_coords else x - scroll_x
                    vy = y if is_viewport_coords else y - scroll_y

                    js_handle = await page.evaluate_handle(
                        "(coords) => document.elementFromPoint(coords.x, coords.y)",
                        {"x": vx, "y": vy}
                    )
                    target_element = js_handle.as_element()
                    if not target_element:
                        # Fallback: Just click and type if no specific element returned
                        await page.mouse.click(vx, vy)
                        await asyncio.sleep(0.2)
                        await page.keyboard.type(text, delay=50)
                        return f"✅ Text typed at Viewport ({vx}, {vy}) [is_viewport={is_viewport_coords}]: {text}"
                except Exception as e:
                    print(f"⚠️ Error resolving element from coords for typing: {e}")

            if not target_element and selector:
                target_element = await find_element(page, selector, action_type="type")
                if not target_element:
                    await page.mouse.wheel(0, 400)
                    await asyncio.sleep(0.5)
                    target_element = await find_element(page, selector, action_type="type")

            if not target_element:
                return (
                    f"❌ Not found: {selector if selector else f'at ({x}, {y})'}. Try a DIFFERENT selector or scroll."
                )

            try:
                # Resolve real input if it's a wrapper
                target_element = await _resolve_input_element(page, target_element, selector or "coordinates")

                # [FAIL FAST] Check if hidden (only if it has is_visible)
                if hasattr(target_element, "is_visible") and not await target_element.is_visible():
                     # If we have coordinates, maybe it's "hidden" but clickable (0 dimensions inner tag)
                     if x is None:
                        return f"❌ Error: Element is HIDDEN. Look for a parent menu, accordion, or dropdown first."

                try:
                    await target_element.scroll_into_view_if_needed(timeout=3000)
                except:
                    pass

                await target_element.click(timeout=3000)
                await asyncio.sleep(0.2)
                await target_element.fill("", timeout=3000)
                await target_element.type(text, delay=50)
                return f"✅ Text typed: {text}"
            except Exception as e:
                # Final fallback for SOM: just click and type
                if x is not None and y is not None:
                    await page.mouse.click(x, y)
                    await asyncio.sleep(0.1)
                    # Keyboard clear
                    await page.keyboard.press("Control+A")
                    await page.keyboard.press("Backspace")
                    await asyncio.sleep(0.1)
                    await page.keyboard.type(text, delay=50)
                    return f"✅ Text typed at ({x}, {y}) via fallback after clearing: {text}"
                return f"❌ Error typing: {str(e)}"

        elif action_type == "scroll":
            direction = text if text in ["up", "down"] else "down"
            direction_val = 600 if direction == "down" else -600
            await page.mouse.wheel(0, direction_val)
            await asyncio.sleep(0.8)

            scroll_info = await page.evaluate("""() => {
                const scrollTop = window.scrollY || document.documentElement.scrollTop;
                const scrollHeight = document.documentElement.scrollHeight;
                const clientHeight = document.documentElement.clientHeight;
                const scrollPercent = Math.round((scrollTop + clientHeight) / scrollHeight * 100);
                const atBottom = (scrollTop + clientHeight) >= (scrollHeight - 50);
                return { scrollTop: Math.round(scrollTop), scrollHeight, clientHeight, scrollPercent, atBottom };
            }""")
            pos_pct = scroll_info.get("scrollPercent", "?")
            at_bottom = scroll_info.get("atBottom", False)
            return f"✅ Scrolled {direction}. 📍 Position: {pos_pct}% {'— REACHED BOTTOM' if at_bottom else ''}"

        elif action_type == "back":
            await page.go_back()
            return "✅ Navigated back"

        elif action_type == "goto":
            if text:
                target_url = text.strip()
                if target_url.startswith("/"):
                    current_origin = await page.evaluate("window.location.origin")
                    target_url = f"{current_origin}{target_url}"
                elif (
                    not target_url.startswith("http")
                    and "." in target_url
                    and " " not in target_url
                ):
                    target_url = f"https://{target_url}"
                elif " " in target_url or (
                    "." not in target_url and not target_url.startswith("http")
                ):
                    search_url = f"https://www.google.com/search?q={target_url.replace(' ', '+')}"
                    await page.goto(search_url, wait_until="load", timeout=5000)
                    return f"✅ Navigated to Google Search: {text}"

                try:
                    await page.goto(target_url, wait_until="load", timeout=5000)
                    return f"✅ Navigated to {target_url}"
                except Exception as e:
                    search_url = (
                        f"https://www.google.com/search?q={text.replace(' ', '+')}"
                    )
                    try:
                        await page.goto(search_url, wait_until="load", timeout=5000)
                        return f"✅ URL failed, searched Google instead: {text}"
                    except:
                        return f"❌ Failed to navigate to {target_url}."
            return "❌ Error: 'text' field required for goto."

        elif action_type == "hover":
            if x is not None and y is not None:
                await page.mouse.move(x, y)
                await asyncio.sleep(0.5)
                return f"✅ Hovered at ({x}, {y})"
            elif selector:
                element = await find_element(page, selector, action_type="click")
                if element:
                    await element.hover()
                    return f"✅ Hovered on {selector}"
                return f"❌ Not found: {selector}"
            return "❌ Error: 'selector' or coordinates required for hover."

        elif action_type == "refresh":
            await page.reload(wait_until="networkidle")
            return "✅ Page refreshed"

        elif action_type == "wait":
            await asyncio.sleep(2)
            return "✅ Wait complete"

    except Exception as e:
        error_msg = str(e).split("\n")[0]
        logger.error(f"❌ Error in perform_action: {e}")
        return f"❌ Error: {error_msg}. Try something else."
    return "⚠️ Invalid action"
