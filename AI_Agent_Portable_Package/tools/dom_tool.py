from tools.browser_manager import BrowserManager
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def get_interactive_elements():
    """
    Radar nâng cao: Tìm tất cả phần tử có khả năng tương tác (Clickable/Input).
    Trả về cả nhãn (label) và CSS selector phù hợp cho từng loại phần tử.
    """
    page = await BrowserManager.get_page()
    if not page:
        return []

    script = r"""
    async () => {
        const startTime = performance.now();
        
        document.documentElement.style.scrollBehavior = 'auto';

        // Step 0: Cleanup old attributes and markers to ensure uniqueness
        document.querySelectorAll('[data-som-id]').forEach(el => el.removeAttribute('data-som-id'));
        const oldContainer = document.getElementById('som-marker-container');
        if (oldContainer) oldContainer.remove();

        const baseSelectors = 'button, a[href], input, select, textarea, [role="button"], [role="link"], [role="menuitem"], [role="tab"], [role="switch"], [role="checkbox"], [role="radio"], [tabindex]:not([tabindex="-1"]), [contenteditable="true"], .ivu-input, .ivu-switch, .ivu-checkbox-input, .ivu-radio-input, .ivu-btn, .ivu-btn-primary, .ivu-upload, .ivu-upload-drag, .ivu-upload-select, .ant-btn, .ant-upload, .btn-confirm, button[type="button"], button[type="submit"]';

        const rawElements = document.querySelectorAll(baseSelectors);
        const interactiveElements = new Set(rawElements);

        // Step 2: Computed Styles & Interaction Signals
        document.querySelectorAll('div, span, li, i, svg, td, tr, p, label').forEach(el => {
            const style = window.getComputedStyle(el);
            const isClickable = style.cursor === 'pointer' || el.hasAttribute('onclick');
            const hasEvents = style.pointerEvents !== 'none';
            const className = (el.className && typeof el.className === 'string') ? el.className.toLowerCase() : "";
            const isUploadClass = className.includes('upload') || className.includes('dropzone');
            
            // Text-based detection for custom upload zones (like iView/AntD)
            const text = (el.innerText || "").toLowerCase();
            const hasUploadText = text.includes('kéo hình ảnh') || text.includes('chọn file') || text.includes('tải ảnh');
            
            if ((isClickable || isUploadClass || hasUploadText) && hasEvents) {
                interactiveElements.add(el);
            }
        });

        const countBefore = interactiveElements.size;

        // Step 3: Visibility & Preliminary Filtering
        const validElements = [];
        interactiveElements.forEach(el => {
            const style = window.getComputedStyle(el);
            
            // Check if element or any parent is display: none or visibility: hidden
            let curr = el;
            let isHidden = false;
            while (curr && curr !== document.body) {
                const s = window.getComputedStyle(curr);
                if (s.display === 'none' || s.visibility === 'hidden' || parseFloat(s.opacity) === 0) {
                    isHidden = true;
                    break;
                }
                curr = curr.parentElement;
            }
            if (isHidden) return;

            const rect = el.getBoundingClientRect();
            const isInViewport = rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.right > 0 && rect.top < window.innerHeight && rect.left < window.innerWidth;
            
            if (isInViewport) {
                validElements.push(el);
            }
        });

        // Step 4: Intelligent Deduplication (Child vs Parent)
        // If a parent and child are both in the list, keep the most "specific" one (usually the child)
        // Unless the parent is a formal interactive element (Button, A)
        const finalSet = validElements.filter(el => {
            const tagName = el.tagName.toUpperCase();
            const isPriority = ['BUTTON', 'INPUT', 'SELECT', 'TEXTAREA', 'A'].includes(tagName) || 
                               el.classList.contains('ivu-btn') || 
                               el.classList.contains('ivu-switch');

            // If this element contains another interactive element, and it's NOT a priority tag, skip it
            if (!isPriority) {
                const hasPriorityChild = validElements.some(other => other !== el && el.contains(other));
                if (hasPriorityChild) return false;
            }
            return true;
        });

        const results = finalSet.map((el, index) => {
            const somId = index + 1;
            el.setAttribute('data-som-id', somId);

            let label = (el.innerText || "").trim();
            if (['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName)) {
                label = el.placeholder || el.getAttribute('aria-label') || "";
                // Try to find label for ID
                if (!label && el.id) {
                    const l = document.querySelector(`label[for="${el.id}"]`);
                    if (l) label = l.innerText;
                }
            }

            let roleTag = el.tagName;
            if (el.tagName === 'BUTTON' || el.classList.contains('ivu-btn')) roleTag = 'BUTTON';
            else if (el.tagName === 'A') roleTag = 'LINK';
            else if (['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName)) roleTag = 'INPUT';
            else roleTag = 'CUSTOM';

            const rect = el.getBoundingClientRect();
            return {
                tagName: roleTag,
                actualTag: el.tagName.toLowerCase(),
                text: (label || "").substring(0, 100).replace(/\n/g, ' ') || 'Unnamed',
                bestSelector: `[data-som-id="${somId}"]`,
                id: el.id || "",
                som_id: somId,
                rect: {
                    x: rect.left + window.scrollX,
                    y: rect.top + window.scrollY,
                    width: rect.width,
                    height: rect.height
                }
            };
        });

        return {
            elements: results,
            countBefore: countBefore,
            countAfter: results.length,
            duration: performance.now() - startTime
        };
    }
    """
    try:
        raw_result = await page.evaluate(script)
        data = raw_result.get("elements", [])
        count_before = raw_result.get("countBefore", 0)
        count_after = raw_result.get("countAfter", 0)
        duration = raw_result.get("duration", 0)

        # Print summary
        btns = len([e for e in data if e["tagName"] == "BUTTON"])
        links = len([e for e in data if e["tagName"] == "LINK"])
        inputs = len([e for e in data if e["tagName"] == "INPUT"])
        custom = len([e for e in data if e["tagName"] == "CUSTOM"])

        logger.info(
            f"🔍 DOM SCAN: Found {count_before} raw -> {count_after} filtered elements ({duration:.2f}ms)"
        )
        logger.info(
            f"📊 Summary: Detected {count_after} interactive elements (Buttons: {btns}, Links: {links}, Inputs: {inputs}, Custom: {custom})"
        )

        return data
    except Exception as e:
        logger.error(f"❌ Radar Error: {str(e)}")
        return []


def format_elements(data: list) -> str:
    """Format the list of elements into a summary string for the AI prompt."""
    if not data or not isinstance(data, list):
        return "No interactive elements detected."

    formatted_res = []
    for el in data:
        if not isinstance(el, dict):
            continue
        tag = el.get("tagName", "unknown")
        actual_tag = el.get("actualTag", "")
        text = el.get("text", "Unnamed")
        sel = el.get("bestSelector", "N/A")
        id_val = el.get("id", "")
        som_id = el.get("som_id", "N/A")

        tag_display = f"{tag}:{actual_tag}" if actual_tag else tag
        info = f"- [{tag_display}] '{text}' (ID: {som_id}"
        if id_val:
            info += f", DOM_ID: {id_val}"
        info += f", Selector: {sel})"
        formatted_res.append(info)

    return f"📍 Radar detected {len(formatted_res)} elements:\n" + "\n".join(
        formatted_res
    )


async def inject_som_markers(page, plan):
    """
    Inject visual numbered markers (Set-of-Mark) onto the page.
    Uses FIXED positioning relative to the viewport for 100% accuracy in screenshots.
    """
    if not plan:
        return plan

    injection_script = """
    () => {
        const container = document.createElement('div');
        container.id = 'som-marker-container';
        // Use FIXED to match viewport-based screenshotting
        container.style.position = 'fixed';
        container.style.top = '0';
        container.style.left = '0';
        container.style.width = '100vw';
        container.style.height = '100vh';
        container.style.pointerEvents = 'none';
        container.style.zIndex = '2147483647'; // Max possible z-index
        document.documentElement.appendChild(container);

        const elements = document.querySelectorAll('[data-som-id]');
        elements.forEach(el => {
            const somId = el.getAttribute('data-som-id');
            const rect = el.getBoundingClientRect();
            
            // Skip if not in viewport or zero size
            if (rect.width < 1 || rect.height < 1) return;
            if (rect.bottom < 0 || rect.right < 0 || rect.top > window.innerHeight || rect.left > window.innerWidth) return;

            const padding = 1;
            const badgeWidth = 18;
            
            const badge = document.createElement('div');
            badge.innerText = somId;
            badge.style.position = 'absolute';
            
            // Viewport-relative placement
            if (rect.left > (badgeWidth + 2)) {
                badge.style.left = (rect.left - badgeWidth - 2) + 'px';
                badge.style.top = rect.top + 'px';
            } else {
                badge.style.left = rect.left + 'px';
                badge.style.top = Math.max(0, rect.top - 12) + 'px';
            }
            
            badge.style.background = 'rgba(255, 0, 0, 0.85)';
            badge.style.color = 'white';
            badge.style.padding = '0px 2px';
            badge.style.borderRadius = '3px';
            badge.style.fontSize = '10px';
            badge.style.fontFamily = 'Arial, sans-serif';
            badge.style.fontWeight = 'bold';
            badge.style.border = '1px solid white';
            badge.style.pointerEvents = 'none';
            badge.style.zIndex = '2147483647';
            badge.style.minWidth = '14px';
            badge.style.textAlign = 'center';
        
            const box = document.createElement('div');
            box.style.position = 'absolute';
            box.style.left = (rect.left - padding) + 'px';
            box.style.top = (rect.top - padding) + 'px';
            box.style.width = (rect.width + (padding * 2)) + 'px';
            box.style.height = (rect.height + (padding * 2)) + 'px';
            box.style.border = '1.5px solid rgba(255, 0, 0, 0.5)';
            box.style.borderRadius = '2px';
            box.style.pointerEvents = 'none';
            box.style.zIndex = '2147483646';
            
            container.appendChild(box);
            container.appendChild(badge);
        });
    }
    """
    try:
        await page.evaluate(injection_script)
    except Exception as e:
        logger.error(f"❌ Error injecting SOM markers: {e}")

    return plan


async def cleanup_som_markers(page):
    """
    Remove SOM markers from the page.
    """
    try:
        await page.evaluate("""() => {
            const container = document.getElementById('som-marker-container');
            if (container) container.remove();
        }""")
    except Exception as e:
        logger.warning(f"⚠️ Error cleaning up SOM markers: {e}")
