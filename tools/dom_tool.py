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

        const originalScrollY = window.scrollY;
        window.scrollTo(0, document.body.scrollHeight);
        await new Promise(r => setTimeout(r, 100)); 
        window.scrollTo(0, 0);
        await new Promise(r => setTimeout(r, 50));
        window.scrollTo(0, originalScrollY);

        const baseSelectors = 'button, a[href], input:not([type="hidden"]), select, textarea, [role="button"], [role="link"], [role="menuitem"], [role="tab"], [role="switch"], [role="checkbox"], [role="radio"], [tabindex]:not([tabindex="-1"]), [contenteditable="true"], .ivu-input, .ivu-switch, .ivu-checkbox-input, .ivu-radio-input, .ivu-btn, .ivu-btn-primary, .btn-confirm, button[type="button"], button[type="submit"]';

        const rawElements = document.querySelectorAll(baseSelectors);
        const interactiveElements = new Set(rawElements);

        // Step 2: Computed Styles & Interaction Signals
        document.querySelectorAll('div, span, li, i, svg, td, tr, p, label').forEach(el => {
            const style = window.getComputedStyle(el);
            const isClickable = style.cursor === 'pointer' || el.hasAttribute('onclick') || style.userSelect === 'none';
            const hasEvents = style.pointerEvents !== 'none';
            if (isClickable && hasEvents) {
                interactiveElements.add(el);
            }
        });

        const countBefore = interactiveElements.size;

        // Step 3: Visibility & Preliminary Filtering
        const validElements = [];
        const scrollX = window.scrollX;
        const scrollY = window.scrollY;

        interactiveElements.forEach(el => {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            
            const hasSize = rect.width > 2 && rect.height > 2; // Increased threshold slightly
            const isVisible = style.visibility !== 'hidden' && style.display !== 'none' && parseFloat(style.opacity || '1') > 0.1;
            
            // If it's a priority element, we are more lenient with size
            const isPriority = ['BUTTON', 'INPUT', 'A', 'SELECT', 'TEXTAREA'].includes(el.tagName) || el.classList.contains('ivu-btn') || el.classList.contains('ivu-switch');

            if (isVisible && (hasSize || isPriority)) {
                validElements.push(el);
            }
        });

        // Step 4: Intelligent Deduplication
        const finalSet = validElements.filter(el => {
            const tagName = el.tagName.toUpperCase();
            const isPriorityTag = ['BUTTON', 'A', 'INPUT', 'SELECT', 'TEXTAREA'].includes(tagName) || 
                                 el.classList.contains('ivu-btn') || 
                                 el.classList.contains('btn-confirm') ||
                                 el.classList.contains('ivu-switch');

            let parent = el.parentElement;
            while (parent) {
                if (validElements.includes(parent)) {
                    const parentTag = parent.tagName.toUpperCase();
                    const isParentPriority = ['BUTTON', 'A', 'INPUT', 'SELECT', 'TEXTAREA'].includes(parentTag) || 
                                           parent.getAttribute('role') === 'button' ||
                                           parent.classList.contains('ivu-btn');
                    
                    // Rule: If I am priority and parent is NOT priority (just a generic div/span), I MUST stay.
                    if (isPriorityTag && !isParentPriority) {
                        parent = parent.parentElement;
                        continue;
                    }
                    
                    // Rule: If both are priority, the parent usually wins (e.g. inner span of a button)
                    // BUT if the parent is a generic container that happens to be marked, the child wins.
                    return false;
                }
                parent = parent.parentElement;
            }
            return true;
        });

        // Secondary Pass: Remove generic parents if they contain a priority child that was kept
        const finalResults = finalSet.filter(parent => {
            const parentTag = parent.tagName.toUpperCase();
            const isParentPriority = ['BUTTON', 'A', 'INPUT', 'SELECT', 'TEXTAREA'].includes(parentTag) || 
                                   parent.getAttribute('role') === 'button' ||
                                   parent.classList.contains('ivu-btn');
            
            if (!isParentPriority) {
                const hasPriorityChild = finalSet.some(child => child !== parent && parent.contains(child));
                if (hasPriorityChild) return false;
            }
            return true;
        });

        const results = finalResults.map(el => {
            let originalEl = el;
            
            // Pivot to the actual interactive component if we caught an inner element
            if (!['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName)) {
                const parentInteractive = el.closest('button, a[href], [role="button"], [role="link"], .ivu-btn, .ivu-switch');
                if (parentInteractive) originalEl = parentInteractive;
            }

            let label = (originalEl.innerText || "").trim();
            
            // Label resolution for inputs
            if (['INPUT', 'TEXTAREA', 'SELECT'].includes(originalEl.tagName) || originalEl.classList.contains('ivu-switch')) {
                let relatedLabel = "";
                if (originalEl.id) {
                    const l = document.querySelector(`label[for="${originalEl.id}"]`);
                    if (l) relatedLabel = l.innerText;
                }
                if (!relatedLabel) {
                    const l = originalEl.closest('label');
                    if (l) relatedLabel = l.innerText;
                }
                if (!relatedLabel) {
                    const formItem = originalEl.closest('.ivu-form-item, .form-group, .field');
                    if (formItem) {
                        const l = formItem.querySelector('label, .ivu-form-item-label');
                        if (l) relatedLabel = l.innerText;
                    }
                }
                if (relatedLabel) label = relatedLabel.trim() + (label ? " (" + label + ")" : "");
                if (!label && originalEl.placeholder) label = originalEl.placeholder;
            }

            if (!label && originalEl.getAttribute('aria-label')) label = originalEl.getAttribute('aria-label');
            if (!label && originalEl.title) label = originalEl.title;
            
            let roleTag = originalEl.tagName;
            if (originalEl.tagName === 'BUTTON' || originalEl.getAttribute('type') === 'submit' || originalEl.getAttribute('role') === 'button' || originalEl.classList.contains('ivu-btn')) {
                roleTag = 'BUTTON';
            } else if (originalEl.tagName === 'A') {
                roleTag = 'LINK';
            } else if (['INPUT', 'TEXTAREA', 'SELECT'].includes(originalEl.tagName) || originalEl.classList.contains('ivu-switch')) {
                roleTag = 'INPUT';
            } else {
                roleTag = 'CUSTOM';
            }
            
            let bestSelector = originalEl.id ? "#" + originalEl.id : "";
            if (!bestSelector && label) {
                const cleanLabel = label.split('\n')[0].replace(/"/g, '\\"').substring(0, 30).trim();
                if (cleanLabel) bestSelector = `text="${cleanLabel}"`;
            }

            let rect = originalEl.getBoundingClientRect();
            // Handle zero-size elements by checking children or parent
            if (rect.width === 0 || rect.height === 0) {
                const childWithRect = originalEl.querySelector('*');
                if (childWithRect) rect = childWithRect.getBoundingClientRect();
                if (rect.width === 0) {
                    const parent = originalEl.parentElement;
                    if (parent) rect = parent.getBoundingClientRect();
                }
            }

            const finalX = rect.left + scrollX;
            const finalY = rect.top + scrollY;

            return {
                tagName: roleTag,
                text: (label || "").substring(0, 50).replace(/\n/g, ' ') || 'Unnamed',
                bestSelector: bestSelector || "N/A",
                rect: {
                    x: finalX, 
                    y: finalY, 
                    width: rect.width, 
                    height: rect.height,
                    centerX: finalX + rect.width / 2, 
                    centerY: finalY + rect.height / 2
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
    """Định dạng danh sách phần tử thành chuỗi tóm tắt cho AI prompt."""
    if not data or not isinstance(data, list):
        return "No interactive elements detected."

    formatted_res = []
    for el in data:
        if not isinstance(el, dict):
            continue
        tag = el.get("tagName", "unknown")
        text = el.get("text", "Unnamed")
        sel = el.get("bestSelector", "N/A")
        id_val = el.get("id", "")
        href = el.get("href", "")

        info = f"- [{tag}] '{text}' (Selector: {sel}"
        if id_val:
            info += f", ID: {id_val}"
        if href:
            info += f", Href: {href}"
        info += ")"
        formatted_res.append(info)

    return f"📍 Radar phát hiện {len(formatted_res)} phần tử:\n" + "\n".join(
        formatted_res
    )


async def inject_som_markers(page, plan):
    """
    Inject visual numbered markers (Set-of-Mark) onto the page based on the current plan.
    Each element in the plan gets a 'som_id'.
    """
    if not plan:
        return plan

    # Assign IDs to unclicked/relevant items
    som_id_counter = 1
    markers_to_inject = []

    for item in plan:
        if not isinstance(item, dict):
            continue
        # Only mark unclicked items or items that were just refreshed
        if item.get("status") == "unclicked":
            item["som_id"] = som_id_counter

            rect = item.get("rect")
            if rect:
                markers_to_inject.append(
                    {
                        "id": som_id_counter,
                        "x": rect["x"],
                        "y": rect["y"],
                        "width": rect["width"],
                        "height": rect["height"],
                    }
                )
                som_id_counter += 1

    if not markers_to_inject:
        return plan

    injection_script = """
    (markers) => {
        const container = document.createElement('div');
        container.id = 'som-marker-container';
        container.style.position = 'absolute';
        container.style.top = '0';
        container.style.left = '0';
        container.style.width = Math.max(document.body.scrollWidth, document.documentElement.scrollWidth) + 'px';
        container.style.height = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight) + 'px';
        container.style.pointerEvents = 'none';
        container.style.zIndex = '999999';
        document.body.appendChild(container);

        // OPTIMIZATION: Use requestAnimationFrame for non-blocking render
        requestAnimationFrame(() => {
            markers.forEach(m => {
                const badge = document.createElement('div');
                badge.className = 'som-badge';
                badge.innerText = m.id;
                badge.style.position = 'absolute';
                badge.style.left = m.x + 'px';
                badge.style.top = m.y + 'px';
                badge.style.background = 'rgba(255, 0, 0, 0.8)';
                badge.style.color = 'white';
                badge.style.padding = '2px 5px';
                badge.style.borderRadius = '4px';
                badge.style.fontSize = '12px';
                badge.style.fontWeight = 'bold';
                badge.style.border = '1px solid white';
                badge.style.boxShadow = '0 2px 4px rgba(0,0,0,0.3)';
                badge.style.pointerEvents = 'none';
                badge.style.zIndex = '999999';
            
            // Draw a border around the element too
            const box = document.createElement('div');
            box.style.position = 'absolute';
            box.style.left = m.x + 'px';
            box.style.top = m.y + 'px';
            box.style.width = m.width + 'px';
            box.style.height = m.height + 'px';
            box.style.border = '2px solid rgba(255, 0, 0, 0.5)';
            box.style.pointerEvents = 'none';
            box.style.zIndex = '999998';
            
            container.appendChild(box);
            container.appendChild(badge);
        });
    });
}
"""
    try:
        await page.evaluate(injection_script, markers_to_inject)
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
