import os
import base64
import pandas as pd
from datetime import datetime
from PIL import Image
import io
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.drawing.image import Image as OpenpyxlImage
from openpyxl.utils import get_column_letter

def save_finding_screenshot(screenshot_b64, url):
    """
    Saves a base64 screenshot to the reports/screenshots directory.
    Returns the relative path to the saved image.
    """
    if not screenshot_b64:
        return None
        
    try:
        # Create reports directory if not exists
        reports_dir = "reports"
        screenshots_dir = os.path.join(reports_dir, "screenshots")
        os.makedirs(screenshots_dir, exist_ok=True)
        
        # Generate filename based on timestamp and url
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        clean_url = "".join([c if c.isalnum() else "_" for c in url[:30]])
        filename = f"finding_{timestamp}_{clean_url}.png"
        filepath = os.path.join(screenshots_dir, filename)
        
        # Decode and save image
        image_data = base64.b64decode(screenshot_b64)
        image = Image.open(io.BytesIO(image_data))
        image.save(filepath)
        
        return filepath
    except Exception as e:
        print(f"⚠️ Error saving finding screenshot: {e}")
        return None

def generate_excel_report(findings, output_path=None, title="BÁO CÁO KIỂM THỬ"):
    """
    Generates a professional Excel report from the findings list.
    """
    if not findings:
        return None
        
    try:
        if output_path is None:
            reports_dir = "reports"
            os.makedirs(reports_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(reports_dir, f"security_report_{timestamp}.xlsx")
            
        # 1. Chuẩn bị dữ liệu
        processed_findings = []
        for f in findings:
            if not isinstance(f, dict): continue
            processed_findings.append({
                "Thời gian": f.get("timestamp", ""),
                "Địa chỉ URL": f.get("url", ""),
                "Phát hiện / Lỗi": f.get("text", ""),
                "Mô tả chi tiết": f.get("details", "Không có mô tả chi tiết."),
                "Ảnh minh chứng": f.get("screenshot", "") 
            })
            
        df = pd.DataFrame(processed_findings)
        
        # 2. Tạo File Excel
        writer = pd.ExcelWriter(output_path, engine='openpyxl')
        df.to_excel(writer, index=False, sheet_name='Security Findings', startrow=2) 
        
        workbook = writer.book
        worksheet = writer.sheets['Security Findings']
        
        # 3. Định dạng Style
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        title_font = Font(bold=True, size=16, color="000000")
        center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
        left_align = Alignment(horizontal="left", vertical="center", wrap_text=True)
        border = Border(
            left=Side(style='thin'), 
            right=Side(style='thin'), 
            top=Side(style='thin'), 
            bottom=Side(style='thin')
        )

        # 4. Thêm Tiêu đề (Row 1)
        worksheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(df.columns))
        title_cell = worksheet.cell(row=1, column=1)
        title_cell.value = title.upper()
        title_cell.font = title_font
        title_cell.alignment = Alignment(horizontal="center", vertical="center")
        worksheet.row_dimensions[1].height = 35

        # 5. Định dạng Header (Row 3)
        for col_idx, col_name in enumerate(df.columns, 1):
            cell = worksheet.cell(row=3, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_align
            cell.border = border
            
            # Set column widths
            if col_name == "Thời gian": worksheet.column_dimensions[get_column_letter(col_idx)].width = 15
            elif col_name == "Địa chỉ URL": worksheet.column_dimensions[get_column_letter(col_idx)].width = 45
            elif col_name == "Phát hiện / Lỗi": worksheet.column_dimensions[get_column_letter(col_idx)].width = 35
            elif col_name == "Mô tả chi tiết": worksheet.column_dimensions[get_column_letter(col_idx)].width = 55
            elif col_name == "Ảnh minh chứng": worksheet.column_dimensions[get_column_letter(col_idx)].width = 50

        # 6. Chèn dữ liệu và ảnh
        img_col_idx = 5 
        
        for row_idx, finding in enumerate(processed_findings, start=4):
            # Apply border and alignment for all cells in row
            for col_idx in range(1, len(df.columns) + 1):
                cell = worksheet.cell(row=row_idx, column=col_idx)
                cell.border = border
                if col_idx == 4: # Mô tả chi tiết -> Left align
                    cell.alignment = left_align
                else:
                    cell.alignment = center_align
            
            # Xử lý ảnh
            img_path = finding.get("Ảnh minh chứng")
            if img_path and os.path.exists(img_path):
                try:
                    img = OpenpyxlImage(img_path)
                    # Resize ảnh
                    orig_w, orig_h = img.width, img.height
                    new_w = 350 
                    new_h = int((new_w / orig_w) * orig_h)
                    img.width = new_w
                    img.height = new_h
                    
                    # Thêm ảnh vào cell
                    cell_ref = f"{get_column_letter(img_col_idx)}{row_idx}"
                    worksheet.add_image(img, cell_ref)
                    
                    # Xóa text path trong cell ảnh
                    worksheet.cell(row=row_idx, column=img_col_idx).value = ""
                    
                    # Chỉnh chiều cao row cho khớp ảnh
                    worksheet.row_dimensions[row_idx].height = new_h * 0.75 + 15
                except Exception as img_err:
                    print(f"⚠️ Could not embed image {img_path}: {img_err}")
                    worksheet.cell(row=row_idx, column=img_col_idx).value = "[Lỗi tải ảnh]"
            else:
                 worksheet.cell(row=row_idx, column=img_col_idx).value = "[Không có ảnh]"

        writer.close()
        return output_path
    except Exception as e:
        print(f"⚠️ Error generating Excel report: {e}")
        import traceback
        traceback.print_exc()
        return None

def cleanup_reports():
    """
    Deletes all temporary screenshots and Excel reports in the reports directory.
    """
    reports_dir = "reports"
    if not os.path.exists(reports_dir):
        return
        
    try:
        import shutil
        # Xóa toàn bộ nội dung trong thư mục screenshots
        screenshots_dir = os.path.join(reports_dir, "screenshots")
        if os.path.exists(screenshots_dir):
            shutil.rmtree(screenshots_dir)
            os.makedirs(screenshots_dir)
            
        # Xóa các file excel cũ
        for f in os.listdir(reports_dir):
            if f.endswith(".xlsx") or f.endswith(".md") or f.endswith(".txt"):
                os.remove(os.path.join(reports_dir, f))
        print("🧹 Đã dọn dẹp các tệp báo cáo tạm thời.")
    except Exception as e:
        print(f"⚠️ Lỗi khi dọn dẹp báo cáo: {e}")
