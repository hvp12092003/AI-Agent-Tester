import logging

logger = logging.getLogger(__name__)

async def inject_visual_effects(page):
    """Inject helper functions to show visual effects. Effects are short-lived to avoid polluting screenshots."""
    try:
        await page.evaluate("""
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

            window.cleanupEffects = () => {
                document.querySelectorAll('.ai-effect-overlay, #ai-virtual-cursor').forEach(el => el.remove());
            };
        """)
    except Exception as e:
        logger.warning(f"Failed to inject visual effects: {e}")

def xpath_escape(text):
    """Escape text for use in XPath expressions."""
    if '"' not in text:
        return f'"{text}"'
    if "'" not in text:
        return f"'{text}'"
    parts = text.split('"')
    return "concat(" + ",'\"',".join(f'"{p}"' for p in parts) + ")"
