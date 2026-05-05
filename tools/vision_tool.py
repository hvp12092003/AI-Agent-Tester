import base64
import io
from PIL import Image, ImageDraw
from tools.browser_manager import BrowserManager

# Screenshot quality settings (optimize for token cost)
SCREENSHOT_MAX_WIDTH = 1024  # Resize to max 1024px wide (saves ~60% tokens)
SCREENSHOT_JPEG_QUALITY = 70  # JPEG compression (saves ~40% file size)

async def capture_screenshot(url: str = None, cursor_pos: dict = None):
    """
    Capture screenshot, compress and resize before sending to AI.
    Optionally draw a red dot at cursor_pos: {"x": float, "y": float}
    Returns base64 string (JPEG format for smaller size).
    """
    page = await BrowserManager.get_page()
    if url:
        await page.goto(url, wait_until="networkidle")
    else:
        # Wait for page to stabilize after actions
        await page.wait_for_timeout(1000)
    
    # Remove all visual effect overlays before capturing clean screenshot
    try:
        await page.evaluate("if(window.cleanupEffects) window.cleanupEffects()")
    except:
        pass
    
    # Capture raw screenshot (clean, no overlays)
    screenshot_bytes = await page.screenshot(full_page=False)
    
    # Compress and resize using Pillow
    img = Image.open(io.BytesIO(screenshot_bytes))
    
    # Draw cursor if provided
    if cursor_pos:
        draw = ImageDraw.Draw(img)
        x, y = cursor_pos.get('x', 0), cursor_pos.get('y', 0)
        
        # Draw red dot with white outline and glow
        radius = 8
        draw.ellipse([x - radius - 2, y - radius - 2, x + radius + 2, y + radius + 2], fill="white") # Outline
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill="red") # Main dot
    
    # Resize if wider than max width (maintain aspect ratio)
    if img.width > SCREENSHOT_MAX_WIDTH:
        # If we resized, we need to adjust cursor_pos if we drew it later, 
        # but here we draw on original then resize. 
        # Actually, let's resize FIRST then draw to ensure coordinates match the final image scale if needed.
        # But wait, AI uses coordinates from original SOM scan.
        # The SOM scan is done on the current viewport. 
        # If we resize the image, the coordinates in the image will change.
        # So we should resize FIRST, then scale the cursor_pos, then draw.
        
        ratio = SCREENSHOT_MAX_WIDTH / img.width
        new_size = (SCREENSHOT_MAX_WIDTH, int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)
        
        if cursor_pos:
            # We need to re-draw or scale. Let's just resize first.
            pass # See below
    
    # Correct order: Resize first, then draw at scaled coordinates
    img = Image.open(io.BytesIO(screenshot_bytes))
    orig_width = img.width
    
    if img.width > SCREENSHOT_MAX_WIDTH:
        ratio = SCREENSHOT_MAX_WIDTH / img.width
        new_size = (SCREENSHOT_MAX_WIDTH, int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)
        scale = ratio
    else:
        scale = 1.0
        
    if cursor_pos:
        draw = ImageDraw.Draw(img)
        x = cursor_pos.get('x', 0) * scale
        y = cursor_pos.get('y', 0) * scale
        radius = 6
        draw.ellipse([x - radius - 2, y - radius - 2, x + radius + 2, y + radius + 2], fill="white")
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill="red")

    # Convert to JPEG for smaller file size
    buffer = io.BytesIO()
    img.convert("RGB").save(buffer, format="JPEG", quality=SCREENSHOT_JPEG_QUALITY, optimize=True)
    compressed_bytes = buffer.getvalue()
    
    # Log size savings
    original_size = len(screenshot_bytes) / 1024
    compressed_size = len(compressed_bytes) / 1024
    print(f"📸 Screenshot: {original_size:.0f}KB → {compressed_size:.0f}KB ({img.width}x{img.height}) [Saved {(1 - compressed_size/original_size)*100:.0f}%]")
    
    base64_image = base64.b64encode(compressed_bytes).decode('utf-8')
    return base64_image
