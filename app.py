import streamlit as st
import asyncio
import base64
import os
import threading
import time
from dotenv import load_dotenv
from multi_agent.graph import create_graph
from agents.llm_factory import LLMFactory
from tools.browser_manager import BrowserManager
from deep_translator import GoogleTranslator
from streamlit.runtime.scriptrunner import get_script_run_ctx, add_script_run_ctx

# --- TU DONG CAI DAT TRINH DUYET CHO CLOUD ---
if not os.path.exists("/tmp/playwright_installed_v3"):
    print("Installing Playwright browsers and system dependencies...")
    # Bước 1: Cài đặt system dependencies cho Chromium (libcups2, libdbus, etc.)
    os.system(
        "playwright install-deps chromium 2>/dev/null || python -m playwright install-deps chromium 2>/dev/null || true"
    )

    # Bước 2: Cài đặt Chromium browser
    res = os.system("playwright install chromium")
    if res != 0:
        res = os.system("python -m playwright install chromium")

    # Chỉ tạo file khóa nếu cài đặt thành công
    if res == 0:
        with open("/tmp/playwright_installed_v3", "w") as f:
            f.write("done")


@st.cache_data
def parse_markdown_table(md_str):
    """
    Parses a markdown table into a list of dictionaries.
    Looks for the first table in the string.
    """
    lines = md_str.strip().split("\n")
    headers = []
    rows = []
    in_table = False

    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            if in_table:
                break  # end of table
            continue

        in_table = True
        cells = [c.strip() for c in line.split("|")[1:-1]]

        if not headers:
            headers = cells
        elif all(c.replace("-", "").replace(":", "").strip() == "" for c in cells):
            continue  # separator
        else:
            # Map values to headers
            row_dict = {}
            for i, h in enumerate(headers):
                if i < len(cells):
                    row_dict[h] = cells[i]
            rows.append(row_dict)
    return rows


@st.cache_data
def translate_text(text, target_lang="vi"):
    if not text:
        return ""
    try:
        return GoogleTranslator(source="auto", target=target_lang).translate(text)
    except:
        return text


# --- HÀM HỖ TRỢ XỬ LÝ BẢNG TEST CASE ---
def normalize_df_columns(df):
    if df is None or df.empty:
        return df
        
    standard_cols = [
        "ID", "Component", "Test Type", "Scenario Type", 
        "Preconditions", "Steps (with exact JSON payload)", 
        "Expected Result (HTTP Status + Response Body + DB State)", "Severity"
    ]
    
    mapping = {}
    for col in df.columns:
        col_lower = col.lower()
        if col_lower in ["id", "mã", "tc_id", "tc id"]:
            mapping[col] = "ID"
        elif col_lower in ["component", "hợp phần", "chức năng"]:
            mapping[col] = "Component"
        elif "test type" in col_lower or "loại test" in col_lower:
            mapping[col] = "Test Type"
        elif "scenario" in col_lower or "kịch bản" in col_lower:
            mapping[col] = "Scenario Type"
        elif "precondition" in col_lower or "điều kiện" in col_lower:
            mapping[col] = "Preconditions"
        elif "step" in col_lower or "bước" in col_lower:
            mapping[col] = "Steps (with exact JSON payload)"
        elif "expected" in col_lower or "kết quả mong đợi" in col_lower or "kết quả" in col_lower:
            mapping[col] = "Expected Result (HTTP Status + Response Body + DB State)"
        elif "severity" in col_lower or "độ nghiêm trọng" in col_lower or "mức độ" in col_lower:
            mapping[col] = "Severity"
            
    df = df.rename(columns=mapping)
    
    for col in standard_cols:
        if col not in df.columns:
            df[col] = ""
            
    extra_cols = [c for c in df.columns if c not in standard_cols]
    df = df[standard_cols + extra_cols]
    return df


def load_json_to_df(json_str):
    import json
    import pandas as pd
    try:
        data = json.loads(json_str)
        if not isinstance(data, list):
            return None
        rows = []
        for item in data:
            steps_list = item.get("steps", [])
            steps_raw = "\n".join(steps_list) if isinstance(steps_list, list) else str(steps_list)
            
            expected_results = item.get("expected_results", {})
            expected_raw = ""
            if isinstance(expected_results, dict):
                expected_raw = expected_results.get("ui_check") or expected_results.get("api_check") or ""
            else:
                expected_raw = str(expected_results)
                
            rows.append({
                "ID": item.get("id", ""),
                "Component": item.get("component", ""),
                "Test Type": item.get("test_type", "") or item.get("type", ""),
                "Scenario Type": item.get("scenario", ""),
                "Preconditions": item.get("preconditions", ""),
                "Steps (with exact JSON payload)": steps_raw,
                "Expected Result (HTTP Status + Response Body + DB State)": expected_raw,
                "Severity": item.get("severity", "")
            })
        return pd.DataFrame(rows)
    except Exception as e:
        print(f"Error loading JSON to DF: {e}")
        return None


def sync_df_to_test_cases(df):
    if df is None or df.empty:
        st.session_state.pop("test_case_json_str", None)
        st.session_state.pop("pre_built_task_plan", None)
        if "agent_state" in st.session_state:
            st.session_state.agent_state["task_plan"] = []
        return
        
    test_cases = []
    pre_built_plan = []
    
    for idx, row in df.iterrows():
        row_dict = row.to_dict()
        
        tc_id = ""
        for k in ["ID", "id", "Id", "Mã"]:
            if k in row_dict and row_dict[k]:
                tc_id = str(row_dict[k]).strip()
                break
                
        component = ""
        for k in ["Component", "component", "Hợp phần", "Chức năng"]:
            if k in row_dict and row_dict[k]:
                component = str(row_dict[k]).strip()
                break
                
        scenario = ""
        for k in ["Scenario Type", "scenario", "Kịch bản", "Tên kịch bản"]:
            if k in row_dict and row_dict[k]:
                scenario = str(row_dict[k]).strip()
                break
                
        preconditions = ""
        for k in ["Preconditions", "preconditions", "Điều kiện", "Điều kiện tiên quyết"]:
            if k in row_dict and row_dict[k]:
                preconditions = str(row_dict[k]).strip()
                break
                
        severity = ""
        for k in ["Severity", "severity", "Mức độ", "Độ nghiêm trọng"]:
            if k in row_dict and row_dict[k]:
                severity = str(row_dict[k]).strip()
                break
                
        steps_raw = ""
        for k in ["Steps (with exact JSON payload)", "steps", "Steps", "Các bước", "Bước"]:
            if k in row_dict and row_dict[k]:
                steps_raw = str(row_dict[k]).strip()
                break
        if not steps_raw:
            for k, v in row_dict.items():
                if "step" in k.lower():
                    steps_raw = str(v).strip()
                    break
                    
        expected_raw = ""
        for k in ["Expected Result (HTTP Status + Response Body + DB State)", "Expected Result (UI & DB/API State)", "expected", "expected_results", "Kết quả mong đợi"]:
            if k in row_dict and row_dict[k]:
                expected_raw = str(row_dict[k]).strip()
                break
        if not expected_raw:
            for k, v in row_dict.items():
                if "expect" in k.lower():
                    expected_raw = str(v).strip()
                    break
                    
        steps_list = [
            s.strip()
            for s in steps_raw.replace("<br>", "\n").replace("\\n", "\n").split("\n")
            if s.strip()
        ]
        
        test_cases.append(
            {
                "id": tc_id,
                "component": component,
                "scenario": scenario,
                "steps": steps_list if steps_list else [steps_raw],
                "expected_results": {
                    "ui_check": expected_raw,
                },
                "preconditions": preconditions,
                "severity": severity
            }
        )
        
        for step in (steps_list if steps_list else [steps_raw]):
            label = f"[{tc_id}] [{scenario}]" if tc_id else f"[{scenario}]"
            pre_built_plan.append({"step": f"{label} {step}", "status": "todo"})
            
    import json as _json_tc
    st.session_state["test_case_json_str"] = _json_tc.dumps(test_cases, ensure_ascii=False, indent=2)
    st.session_state["pre_built_task_plan"] = pre_built_plan
    if "agent_state" in st.session_state:
        st.session_state.agent_state["task_plan"] = pre_built_plan


# --- CẤU HÌNH TRANG ---
st.set_page_config(
    page_title="3DArt AI Agent",
    layout="wide",
    page_icon="assets/ai_agent_logo.png",
    initial_sidebar_state="collapsed",
)

# --- CSS CAO CẤP (GLASSMORPHISM & MODERN UI) ---
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    
    :root {
        /* Default / Dark Theme variables — Ultra High Contrast Borders */
        --bg-app: #020204;
        --bg-app-gradient: none;
        --text-main: #ffffff;
        --bg-panel: #0d0f18;
        --border-panel: rgba(140, 155, 255, 0.65);
        --shadow-panel: 0 8px 32px 0 rgba(0, 0, 0, 0.98), 0 0 0 1px rgba(140, 155, 255, 0.4);
        --bg-input: #111320;
        --border-input: rgba(140, 155, 255, 0.6);
        --text-input: #ffffff;
        --text-label: #dde3f0;
        --border-table: rgba(255, 255, 255, 0.3);
        --text-caption: #c8d2e4;
        --placeholder-color: #8a96a8;
        --bg-uploader: rgba(13, 14, 20, 0.5);
        --border-uploader: rgba(140, 155, 255, 0.55);
        --bg-secondary-btn: #111320;
        --text-secondary-btn: #ffffff;
        --border-secondary-btn: rgba(140, 155, 255, 0.7);
        --bg-secondary-btn-hover: #1a1d30;
        --border-secondary-btn-hover: rgba(139, 92, 246, 0.95);
        --bg-card: #0d0f18;
        --border-card: rgba(140, 155, 255, 0.55);
        --text-card-name: #ffffff;
        --text-card-desc: #ccd5e8;
        --bg-category: rgba(255, 255, 255, 0.05);
        --border-category: rgba(255, 255, 255, 0.22);
        --text-category: #ccd5e8;
        --bg-empty-state: rgba(13, 15, 24, 0.95);
        --border-empty-state: rgba(255, 255, 255, 0.25);
        --bg-browser-chrome: #0d0f18;
        --border-browser-chrome: rgba(140, 155, 255, 0.55);
        --bg-browser-url: #060810;
        --border-browser-url: rgba(140, 155, 255, 0.5);
        --text-browser-url: #ccd5e8;
        --bg-browser-viewport-empty: #060810;
        --bg-browser-footer: #0d0f18;
        --border-browser-footer: rgba(140, 155, 255, 0.45);
        --border-panel-header: rgba(255, 255, 255, 0.25);
        --bg-execution-step: rgba(255, 255, 255, 0.05);
        --border-execution-step: rgba(255, 255, 255, 0.18);
        --bg-execution-step-hover: rgba(255, 255, 255, 0.09);
        --text-execution-step-empty: #8a96a8;
        --bg-agent-status: #0d0f18;
        --border-agent-status: rgba(140, 155, 255, 0.6);
        --text-agent-status-label: #ffffff;
        --text-agent-status-thought: #ccd5e8;
        --bg-action-log: #060810;
        --border-action-log: rgba(140, 155, 255, 0.55);
        --text-action-log: #eaf0ff;
        --bg-help-tooltip: #111320;
        --border-help-tooltip: rgba(139, 92, 246, 0.75);
        --text-help-tooltip: #dde3f0;
        --border-section-header: rgba(255, 255, 255, 0.28);
        --text-section-header: #ffffff;
        --bg-popover: #111320;
        --text-popover: #ffffff;
        --theme-icon-color: #60a5fa;

        /* Accordion Theme variables */
        --bg-accordion: #0d0f18;
        --border-accordion: rgba(140, 155, 255, 0.55);
        --bg-accordion-header: #111320;
        --bg-accordion-header-hover: #1a1d30;
        --text-accordion-header: #ffffff;
        --bg-accordion-badge: rgba(255, 255, 255, 0.12);
        --text-accordion-badge: #ccd5e8;
        --border-accordion-category: rgba(255, 255, 255, 0.18);
        --bg-accordion-item-hover: rgba(255, 255, 255, 0.07);
        --text-accordion-item-title: #ffffff;
        --text-accordion-item-desc: #ccd5e8;

        /* Terminal Row Colors */
        --color-terminal-vision: #fbbf24;
        --color-terminal-action: #22d3ee;
        --color-terminal-manager: #a78bfa;
        --color-terminal-default: #dde3f0;
    }

    [data-theme="light"] {
        /* Light Theme variables */
        --bg-app: #ffffff;
        --bg-app-gradient: radial-gradient(circle at top right, rgba(139, 92, 246, 0.06), transparent 50%),
                           radial-gradient(circle at bottom left, rgba(16, 185, 129, 0.03), transparent 50%);
        --text-main: #1f2937;
        --bg-panel: #fcfcfd;
        --border-panel: rgba(0, 0, 0, 0.08);
        --shadow-panel: 0 8px 32px 0 rgba(0, 0, 0, 0.06);
        --bg-input: #f3f4f6;
        --border-input: rgba(0, 0, 0, 0.15);
        --text-input: #111827;
        --text-label: #374151;
        --border-table: rgba(0, 0, 0, 0.1);
        --text-caption: #4b5563;
        --placeholder-color: #6b7280;
        --bg-uploader: #f9fafb;
        --border-uploader: rgba(0, 0, 0, 0.15);
        --bg-secondary-btn: #ffffff;
        --text-secondary-btn: #374151;
        --border-secondary-btn: rgba(0, 0, 0, 0.15);
        --bg-secondary-btn-hover: #f3f4f6;
        --border-secondary-btn-hover: rgba(0, 0, 0, 0.25);
        --bg-card: #f9fafb;
        --border-card: rgba(0, 0, 0, 0.08);
        --text-card-name: #111827;
        --text-card-desc: #6b7280;
        --bg-category: rgba(0, 0, 0, 0.02);
        --border-category: rgba(0, 0, 0, 0.05);
        --text-category: #4b5563;
        --bg-empty-state: rgba(243, 244, 246, 0.6);
        --border-empty-state: rgba(0, 0, 0, 0.06);
        --bg-browser-chrome: #f3f4f6;
        --border-browser-chrome: rgba(0, 0, 0, 0.1);
        --bg-browser-url: #ffffff;
        --border-browser-url: rgba(0, 0, 0, 0.08);
        --text-browser-url: #4b5563;
        --bg-browser-viewport-empty: #f9fafb;
        --bg-browser-footer: #f3f4f6;
        --border-browser-footer: rgba(0, 0, 0, 0.1);
        --border-panel-header: rgba(0, 0, 0, 0.08);
        --bg-execution-step: rgba(0, 0, 0, 0.02);
        --border-execution-step: rgba(0, 0, 0, 0.04);
        --bg-execution-step-hover: rgba(0, 0, 0, 0.04);
        --text-execution-step-empty: #9ca3af;
        --bg-agent-status: #f3f4f6;
        --border-agent-status: rgba(0, 0, 0, 0.08);
        --text-agent-status-label: #111827;
        --text-agent-status-thought: #4b5563;
        --bg-action-log: #f3f4f6;
        --border-action-log: rgba(0, 0, 0, 0.08);
        --text-action-log: #1f2937;
        --bg-help-tooltip: #ffffff;
        --border-help-tooltip: rgba(0, 0, 0, 0.12);
        --text-help-tooltip: #374151;
        --border-section-header: rgba(0, 0, 0, 0.08);
        --text-section-header: #111827;
        --bg-popover: #ffffff;
        --text-popover: #111827;
        --theme-icon-color: #2563eb;

        /* Accordion Theme variables */
        --bg-accordion: #f9fafb;
        --border-accordion: rgba(0, 0, 0, 0.08);
        --bg-accordion-header: #f3f4f6;
        --bg-accordion-header-hover: #e5e7eb;
        --text-accordion-header: #111827;
        --bg-accordion-badge: rgba(0, 0, 0, 0.05);
        --text-accordion-badge: #4b5563;
        --border-accordion-category: rgba(0, 0, 0, 0.05);
        --bg-accordion-item-hover: rgba(0, 0, 0, 0.03);
        --text-accordion-item-title: #111827;
        --text-accordion-item-desc: #4b5563;

        /* Terminal Row Colors */
        --color-terminal-vision: #b45309;
        --color-terminal-action: #0284c7;
        --color-terminal-manager: #6d28d9;
        --color-terminal-default: #4b5563;
    }

    [data-theme="dark"] {
        /* Dark Theme variables — Ultra High Contrast Borders */
        --bg-app: #020204;
        --bg-app-gradient: none;
        --text-main: #ffffff;
        --bg-panel: #0d0f18;
        --border-panel: rgba(140, 155, 255, 0.65);
        --shadow-panel: 0 8px 32px 0 rgba(0, 0, 0, 0.98), 0 0 0 1px rgba(140, 155, 255, 0.4);
        --bg-input: #111320;
        --border-input: rgba(140, 155, 255, 0.6);
        --text-input: #ffffff;
        --text-label: #dde3f0;
        --border-table: rgba(255, 255, 255, 0.3);
        --text-caption: #c8d2e4;
        --placeholder-color: #8a96a8;
        --bg-uploader: rgba(13, 14, 20, 0.5);
        --border-uploader: rgba(140, 155, 255, 0.55);
        --bg-secondary-btn: #111320;
        --text-secondary-btn: #ffffff;
        --border-secondary-btn: rgba(140, 155, 255, 0.7);
        --bg-secondary-btn-hover: #1a1d30;
        --border-secondary-btn-hover: rgba(139, 92, 246, 0.95);
        --bg-card: #0d0f18;
        --border-card: rgba(140, 155, 255, 0.55);
        --text-card-name: #ffffff;
        --text-card-desc: #ccd5e8;
        --bg-category: rgba(255, 255, 255, 0.05);
        --border-category: rgba(255, 255, 255, 0.22);
        --text-category: #ccd5e8;
        --bg-empty-state: rgba(13, 15, 24, 0.95);
        --border-empty-state: rgba(255, 255, 255, 0.25);
        --bg-browser-chrome: #0d0f18;
        --border-browser-chrome: rgba(140, 155, 255, 0.55);
        --bg-browser-url: #060810;
        --border-browser-url: rgba(140, 155, 255, 0.5);
        --text-browser-url: #ccd5e8;
        --bg-browser-viewport-empty: #060810;
        --bg-browser-footer: #0d0f18;
        --border-browser-footer: rgba(140, 155, 255, 0.45);
        --border-panel-header: rgba(255, 255, 255, 0.25);
        --bg-execution-step: rgba(255, 255, 255, 0.05);
        --border-execution-step: rgba(255, 255, 255, 0.18);
        --bg-execution-step-hover: rgba(255, 255, 255, 0.09);
        --text-execution-step-empty: #8a96a8;
        --bg-agent-status: #0d0f18;
        --border-agent-status: rgba(140, 155, 255, 0.6);
        --text-agent-status-label: #ffffff;
        --text-agent-status-thought: #ccd5e8;
        --bg-action-log: #060810;
        --border-action-log: rgba(140, 155, 255, 0.55);
        --text-action-log: #eaf0ff;
        --bg-help-tooltip: #111320;
        --border-help-tooltip: rgba(139, 92, 246, 0.75);
        --text-help-tooltip: #dde3f0;
        --border-section-header: rgba(255, 255, 255, 0.28);
        --text-section-header: #ffffff;
        --bg-popover: #111320;
        --text-popover: #ffffff;
        --theme-icon-color: #60a5fa;

        /* Accordion Theme variables */
        --bg-accordion: #0d0f18;
        --border-accordion: rgba(140, 155, 255, 0.55);
        --bg-accordion-header: #111320;
        --bg-accordion-header-hover: #1a1d30;
        --text-accordion-header: #ffffff;
        --bg-accordion-badge: rgba(255, 255, 255, 0.12);
        --text-accordion-badge: #ccd5e8;
        --border-accordion-category: rgba(255, 255, 255, 0.18);
        --bg-accordion-item-hover: rgba(255, 255, 255, 0.07);
        --text-accordion-item-title: #ffffff;
        --text-accordion-item-desc: #ccd5e8;

        /* Terminal Row Colors */
        --color-terminal-vision: #fbbf24;
        --color-terminal-action: #22d3ee;
        --color-terminal-manager: #a78bfa;
        --color-terminal-default: #dde3f0;
    }
    
    @media (prefers-color-scheme: light) {
        :root {
            /* Light Theme variables fallback */
            --bg-app: #ffffff;
            --bg-app-gradient: radial-gradient(circle at top right, rgba(139, 92, 246, 0.06), transparent 50%),
                               radial-gradient(circle at bottom left, rgba(16, 185, 129, 0.03), transparent 50%);
            --text-main: #1f2937;
            --bg-panel: #fcfcfd;
            --border-panel: rgba(0, 0, 0, 0.08);
            --shadow-panel: 0 8px 32px 0 rgba(0, 0, 0, 0.06);
            --bg-input: #f3f4f6;
            --border-input: rgba(0, 0, 0, 0.15);
            --text-input: #111827;
            --text-label: #374151;
            --border-table: rgba(0, 0, 0, 0.1);
            --text-caption: #4b5563;
            --placeholder-color: #6b7280;
            --bg-uploader: #f9fafb;
            --border-uploader: rgba(0, 0, 0, 0.15);
            --bg-secondary-btn: #ffffff;
            --text-secondary-btn: #374151;
            --border-secondary-btn: rgba(0, 0, 0, 0.15);
            --bg-secondary-btn-hover: #f3f4f6;
            --border-secondary-btn-hover: rgba(0, 0, 0, 0.25);
            --bg-card: #f9fafb;
            --border-card: rgba(0, 0, 0, 0.08);
            --text-card-name: #111827;
            --text-card-desc: #6b7280;
            --bg-category: rgba(0, 0, 0, 0.02);
            --border-category: rgba(0, 0, 0, 0.05);
            --text-category: #4b5563;
            --bg-empty-state: rgba(243, 244, 246, 0.6);
            --border-empty-state: rgba(0, 0, 0, 0.06);
            --bg-browser-chrome: #f3f4f6;
            --border-browser-chrome: rgba(0, 0, 0, 0.1);
            --bg-browser-url: #ffffff;
            --border-browser-url: rgba(0, 0, 0, 0.08);
            --text-browser-url: #4b5563;
            --bg-browser-viewport-empty: #f9fafb;
            --bg-browser-footer: #f3f4f6;
            --border-browser-footer: rgba(0, 0, 0, 0.1);
            --border-panel-header: rgba(0, 0, 0, 0.08);
            --bg-execution-step: rgba(0, 0, 0, 0.02);
            --border-execution-step: rgba(0, 0, 0, 0.04);
            --bg-execution-step-hover: rgba(0, 0, 0, 0.04);
            --text-execution-step-empty: #9ca3af;
            --bg-agent-status: #f3f4f6;
            --border-agent-status: rgba(0, 0, 0, 0.08);
            --text-agent-status-label: #111827;
            --text-agent-status-thought: #4b5563;
            --bg-action-log: #f3f4f6;
            --border-action-log: rgba(0, 0, 0, 0.08);
            --text-action-log: #1f2937;
            --bg-help-tooltip: #ffffff;
            --border-help-tooltip: rgba(0, 0, 0, 0.12);
            --text-help-tooltip: #374151;
            --border-section-header: rgba(0, 0, 0, 0.08);
            --text-section-header: #111827;
            --bg-popover: #ffffff;
            --text-popover: #111827;
            --theme-icon-color: #2563eb;

            /* Accordion Theme variables */
            --bg-accordion: #f9fafb;
            --border-accordion: rgba(0, 0, 0, 0.08);
            --bg-accordion-header: #f3f4f6;
            --bg-accordion-header-hover: #e5e7eb;
            --text-accordion-header: #111827;
            --bg-accordion-badge: rgba(0, 0, 0, 0.05);
            --text-accordion-badge: #4b5563;
            --border-accordion-category: rgba(0, 0, 0, 0.05);
            --bg-accordion-item-hover: rgba(0, 0, 0, 0.03);
            --text-accordion-item-title: #111827;
            --text-accordion-item-desc: #4b5563;

            /* Terminal Row Colors */
            --color-terminal-vision: #b45309;
            --color-terminal-action: #0284c7;
            --color-terminal-manager: #6d28d9;
            --color-terminal-default: #4b5563;
        }
    }
    
    /* Core Layout & Base Override */
    html, body, [class*="css"] {
        font-family: 'Outfit', -apple-system, sans-serif;
    }
    
    .stApp {
        background-color: var(--bg-app) !important;
        background-image: var(--bg-app-gradient) !important;
        color: var(--text-main) !important;
    }
    
    /* Extra overrides for Streamlit internal containers */
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    [data-testid="stBottomBlockContainer"],
    .stApp > div, .stApp > section {
        background-color: var(--bg-app) !important;
    }
    
    /* Force all markdown text to high contrast */
    .stMarkdown p, .stMarkdown li, .stMarkdown span {
        color: var(--text-main) !important;
    }
    
    /* Hide Default Streamlit Elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display:none;}
    [data-testid="stHeader"] {
        background: transparent !important;
    }
    [data-testid="stSidebar"] {
        display: none !important;
    }
    [data-testid="collapsedControl"] {
        display: none !important;
    }
    .block-container {
        padding-top: 0.4rem;
        padding-bottom: 0.4rem;
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
        max-width: 100% !important;
    }
    
    /* Panel Borders and Backgrounds */
    div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
        background: var(--bg-panel) !important;
        backdrop-filter: blur(16px) !important;
        border: 1.5px solid var(--border-panel) !important;
        border-radius: 12px !important;
        padding: 12px !important;
        box-shadow: var(--shadow-panel) !important;
        outline: 1px solid rgba(139, 92, 246, 0.25);
        height: calc(100vh - 1.4rem);
        overflow-y: auto;
        overflow-x: hidden;
    }
    
    /* Custom scrollbar for panel columns */
    div[data-testid="stHorizontalBlock"] > div[data-testid="column"]::-webkit-scrollbar {
        width: 4px;
    }
    div[data-testid="stHorizontalBlock"] > div[data-testid="column"]::-webkit-scrollbar-track {
        background: transparent;
    }
    div[data-testid="stHorizontalBlock"] > div[data-testid="column"]::-webkit-scrollbar-thumb {
        background: rgba(255, 255, 255, 0.1);
        border-radius: 4px;
    }
    div[data-testid="stHorizontalBlock"] > div[data-testid="column"]::-webkit-scrollbar-thumb:hover {
        background: rgba(255, 255, 255, 0.2);
    }

    /* Override styling for nested columns to remove background and border */
    div[data-testid="column"] div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
        background: transparent !important;
        backdrop-filter: none !important;
        border: none !important;
        padding: 0px !important;
        box-shadow: none !important;
        max-height: none !important;
        height: auto !important;
        overflow: visible !important;
    }
    
    
    /* Sidebar Headers */
    .sidebar-header-box {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 8px;
        padding-bottom: 8px;
        border-bottom: 1px solid var(--border-section-header);
    }
    
    .logo-container {
        width: 38px;
        height: 38px;
        border-radius: 10px;
        background: linear-gradient(135deg, #8b5cf6, #10b981);
        display: flex;
        align-items: center;
        justify-content: center;
    }

    /* Logo header flex container */
    .logo-header-container {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 12px;
        padding: 4px 0;
    }
    .logo-img {
        width: 44px !important;
        height: 44px !important;
        object-fit: contain;
        border-radius: 10px;
        box-shadow: 0 4px 12px rgba(88, 86, 214, 0.25);
    }
    .logo-text-wrapper {
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    .logo-title {
        margin: 0 !important;
        font-size: 15px !important;
        font-weight: 700 !important;
        color: var(--text-section-header) !important;
        line-height: 1.2 !important;
    }
    .logo-subtitle {
        margin: 0 !important;
        font-size: 9.5px !important;
        color: var(--text-card-desc) !important;
        line-height: 1.2 !important;
        margin-top: 2px !important;
    }
    
    /* Sections Headers */
    .section-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin: 6px 0 4px 0;
        padding-bottom: 4px;
        border-bottom: 1px solid var(--border-section-header);
    }
    .section-header h4 {
        margin: 0;
        font-size: 0.7rem;
        font-weight: 700;
        letter-spacing: 1px;
        background: linear-gradient(90deg, #a78bfa, #60a5fa);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        text-transform: uppercase;
    }

    /* Compact vertical spacing for Streamlit elements (left column) */
    div[data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"],
    div[data-testid="stVerticalBlock"] > div.element-container {
        margin-bottom: 0 !important;
    }
    /* Reduce gap between stacked widget blocks */
    div[data-testid="stVerticalBlock"] > div[data-testid="element-container"] {
        padding-bottom: 0 !important;
    }
    /* Streamlit default element gap override */
    .stSelectbox, .stTextArea, .stFileUploader, .stButton, .stMarkdown {
        margin-bottom: 0 !important;
        padding-bottom: 0 !important;
    }
    /* Reduce widget label top margin */
    div[data-testid="stWidgetLabel"] {
        margin-bottom: 1px !important;
        margin-top: 3px !important;
    }
    /* Reduce stSelectbox vertical padding */
    div[data-testid="stSelectbox"] {
        padding-bottom: 2px !important;
    }
    /* Reduce horizontal divider (st.markdown("---")) margins */
    hr {
        margin-top: 4px !important;
        margin-bottom: 4px !important;
    }
    /* Compact sidebar header */
    .sidebar-header-box {
        margin-bottom: 6px !important;
        padding-bottom: 6px !important;
    }
    /* Compact selectbox internal padding */
    div[data-baseweb="select"] > div {
        min-height: 42px !important;
        padding-top: 4px !important;
        padding-bottom: 4px !important;
        line-height: 1.4 !important;
        overflow: visible !important;
    }
    /* Ensure the inner single value container centers items and does not clip */
    div[data-baseweb="select"] div[class*="valueContainer"] {
        padding-top: 0px !important;
        padding-bottom: 0px !important;
        display: flex !important;
        align-items: center !important;
        overflow: visible !important;
    }
    /* Fix selected value text clipping */
    div[data-baseweb="select"] [data-testid="stSelectboxLabel"],
    div[data-baseweb="select"] div[class*="singleValue"],
    div[data-baseweb="select"] div[class*="placeholder"],
    div[data-baseweb="select"] span,
    div[data-baseweb="select"] p {
        line-height: 1.4 !important;
        font-size: 14px !important;
        overflow: visible !important;
        white-space: nowrap !important;
        text-overflow: ellipsis !important;
    }
    /* Compact textarea */
    textarea {
        min-height: 90px !important;
        padding: 8px 12px !important;
        line-height: 1.4 !important;
        overflow-y: auto !important;
    }
    /* Compact file uploader */
    div[data-testid="stFileUploader"] {
        padding: 4px !important;
    }
    div[data-testid="stFileUploader"] section {
        min-height: 52px !important;
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 4px !important;
        padding: 8px 12px !important;
    }
    
    /* Custom select & textarea styling overrides */
    div[data-baseweb="select"] > div, textarea, input {
        background-color: var(--bg-input) !important;
        border: 1px solid var(--border-input) !important;
        color: var(--text-input) !important;
        border-radius: 8px !important;
    }
    
    /* Force selectbox values and text to be bright */
    div[data-baseweb="select"] * {
        color: var(--text-input) !important;
    }
    
    /* Dropdown options popover styles */
    [data-baseweb="menu"] *, [data-baseweb="popover"] * {
        color: var(--text-popover) !important;
        background-color: var(--bg-popover) !important;
    }
    
    /* Streamlit labels & widget label paragraphs */
    div[data-testid="stWidgetLabel"] p, label, .stMarkdown p {
        color: var(--text-label) !important;
    }
    
    /* Table responsive layout rules to prevent screen stretching */
    .stMarkdown table {
        display: block !important;
        width: 100% !important;
        overflow-x: auto !important;
        overflow-y: hidden !important;
        border-collapse: collapse !important;
        margin-bottom: 12px !important;
    }
    
    .stMarkdown th, .stMarkdown td {
        min-width: 100px !important;
        max-width: 300px !important;
        word-break: break-word !important;
        white-space: normal !important;
        padding: 8px 12px !important;
        font-size: 11px !important;
        border: 1px solid var(--border-table) !important;
        line-height: 1.4 !important;
    }
    
    /* Captions & helper text next to/below widgets */
    div[data-testid="stCaptionContainer"] p, div[data-testid="stCaptionContainer"], small {
        color: var(--text-caption) !important;
    }
    
    /* Text input placeholder styling */
    textarea::placeholder, input::placeholder, textarea::-webkit-input-placeholder, input::-webkit-input-placeholder {
        color: var(--placeholder-color) !important;
        opacity: 0.85 !important;
    }
    
    /* Custom Green Alert Card */
    .custom-alert-success {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 8px 12px;
        background: rgba(16, 185, 129, 0.08);
        border: 1px solid rgba(16, 185, 129, 0.3);
        border-radius: 8px;
        margin-bottom: 12px;
        color: #10b981;
        font-size: 12px;
        font-weight: 500;
    }
    .custom-alert-success .alert-icon {
        font-weight: bold;
        font-size: 14px;
    }
    
    /* Custom Info Alert Box */
    .custom-alert-info {
        display: flex;
        align-items: flex-start;
        gap: 10px;
        padding: 10px 14px;
        background: rgba(59, 130, 246, 0.06);
        border: 1px solid rgba(59, 130, 246, 0.2);
        border-radius: 8px;
        margin-bottom: 14px;
        font-size: 11.5px;
        line-height: 1.4;
        color: #8b949e;
    }
    .custom-alert-info .alert-icon {
        color: #3b82f6;
        font-size: 14px;
        margin-top: 1px;
    }

    /* Sidebar uploaded file card */
    .sidebar-file-item {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 8px 12px;
        background: var(--bg-card) !important;
        border: 1px solid var(--border-card) !important;
        border-radius: 8px;
        margin-bottom: 8px;
    }
    .sidebar-file-item .file-icon {
        font-size: 16px;
        color: var(--text-caption) !important;
    }
    .sidebar-file-item .file-info {
        flex: 1;
        min-width: 0;
    }
    .sidebar-file-item .file-name {
        font-size: 12px;
        font-weight: 500;
        color: var(--text-main) !important;
        text-overflow: ellipsis;
        overflow: hidden;
        white-space: nowrap;
    }
    .sidebar-file-item .file-size {
        font-size: 10px;
        color: var(--text-caption) !important;
    }
    .sidebar-file-item .check-icon {
        color: #10b981;
        font-weight: bold;
        font-size: 12px;
    }

    /* Streamlit File Uploader overrides to force text color inside */
    div[data-testid="stFileUploader"] {
        border: 1.5px dashed var(--border-uploader) !important;
        background-color: var(--bg-uploader) !important;
        border-radius: 8px !important;
        padding: 4px !important;
        text-align: center;
        transition: border-color 0.2s ease;
    }
    div[data-testid="stFileUploader"]:hover {
        border-color: var(--theme-icon-color) !important;
    }
    div[data-testid="stFileUploader"] section {
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 4px !important;
        padding: 8px 12px !important;
        min-height: 52px !important;
    }
    div[data-testid="stFileUploader"] section > div {
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 4px !important;
        width: 100% !important;
    }
    div[data-testid="stFileUploader"] p, div[data-testid="stFileUploader"] span, div[data-testid="stFileUploader"] small {
        color: var(--text-caption) !important;
        font-size: 11px !important;
        line-height: 1.4 !important;
        text-align: center !important;
    }
    div[data-testid="stFileUploader"] section button {
        background-color: var(--bg-secondary-btn) !important;
        border: 1px solid var(--border-secondary-btn) !important;
        color: var(--text-secondary-btn) !important;
        border-radius: 6px !important;
        padding: 3px 12px !important;
        font-size: 11px !important;
        margin: 0 auto !important;
        display: block !important;
        transition: all 0.2s ease;
    }
    div[data-testid="stFileUploader"] section button:hover {
        background-color: var(--bg-secondary-btn-hover) !important;
        border-color: var(--border-secondary-btn-hover) !important;
    }
    
    /* Buttons Custom Overrides */
    button[kind="primary"] {
        background: linear-gradient(135deg, #6d6ae8, #4f46e5) !important;
        color: white !important;
        border: 1px solid rgba(139, 92, 246, 0.6) !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        transition: all 0.2s ease !important;
        box-shadow: 0 4px 16px rgba(88, 86, 214, 0.45), 0 0 0 1px rgba(139, 92, 246, 0.25) !important;
    }
    button[kind="primary"]:hover {
        background: linear-gradient(135deg, #8b89f0, #6d6ae8) !important;
        box-shadow: 0 0 24px rgba(139, 92, 246, 0.65), 0 0 0 1px rgba(139, 92, 246, 0.5) !important;
        transform: translateY(-1px);
    }
    button[kind="secondary"] {
        background-color: var(--bg-secondary-btn) !important;
        color: var(--text-secondary-btn) !important;
        border: 1px solid var(--border-secondary-btn) !important;
        border-radius: 8px !important;
        font-weight: 500 !important;
        white-space: nowrap !important;
    }
    button[kind="secondary"]:hover {
        background-color: var(--bg-secondary-btn-hover) !important;
        border-color: var(--border-secondary-btn-hover) !important;
    }
    
    /* Glass Cards */
    .glass-card {
        background: var(--bg-card) !important;
        border: 1px solid var(--border-card) !important;
        border-radius: 12px;
        padding: 14px;
        margin-bottom: 14px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
    }
    
    /* Test Plan Categories */
    .category-header {
        padding: 6px 12px;
        background: var(--bg-category);
        border-bottom: 1px solid var(--border-category);
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: var(--text-category);
        border-radius: 4px;
        margin-top: 10px;
        margin-bottom: 4px;
    }
    
    .test-case-row {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 8px 12px;
        border-bottom: 1px solid var(--border-category);
        border-radius: 6px;
        transition: background 0.2s ease;
    }
    .test-case-row:hover {
        background: var(--bg-execution-step);
    }
    
    .test-case-info {
        flex: 1;
        min-width: 0;
    }
    .test-case-name {
        font-size: 13px;
        font-weight: 500;
        color: var(--text-card-name);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .test-case-desc {
        font-size: 11px;
        color: var(--text-card-desc);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    
    /* Custom Accordion Accordance details/summary styling */
    .custom-accordion {
        border: 1.5px solid var(--border-accordion) !important;
        border-radius: 10px;
        background: var(--bg-accordion) !important;
        margin-bottom: 14px;
        overflow: hidden;
        box-shadow: var(--shadow-panel) !important;
    }
    .accordion-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 11px 16px;
        background: var(--bg-accordion-header) !important;
        cursor: pointer;
        user-select: none;
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.8px;
        text-transform: uppercase;
        color: var(--text-accordion-header) !important;
        border-bottom: 1px solid var(--border-accordion-category) !important;
    }
    .accordion-header:hover {
        background: var(--bg-accordion-header-hover) !important;
    }
    .accordion-title {
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .accordion-arrow {
        font-size: 10px;
        color: var(--text-accordion-badge);
        transition: transform 0.2s ease;
    }
    .accordion-badge {
        font-size: 11px;
        color: var(--text-accordion-badge) !important;
        background: var(--bg-accordion-badge) !important;
        padding: 2px 8px;
        border-radius: 12px;
    }
    .accordion-content {
        padding: 8px 0;
    }
    .accordion-category {
        padding: 10px 16px 4px 16px;
        font-size: 10px;
        font-weight: 700;
        color: var(--text-accordion-badge) !important;
        text-transform: uppercase;
        letter-spacing: 1px;
        border-bottom: 1px solid var(--border-accordion-category) !important;
    }
    .accordion-item {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 8px 16px;
        border-bottom: 1px solid var(--border-accordion-category) !important;
        transition: background-color 0.15s ease;
    }
    .accordion-item:hover {
        background-color: var(--bg-accordion-item-hover) !important;
    }
    .accordion-item:last-child {
        border-bottom: none !important;
    }
    .item-icon {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 14px;
        height: 14px;
        border-radius: 50%;
        font-size: 10px;
        font-weight: bold;
    }
    .item-icon.todo {
        border: 1px solid var(--text-accordion-badge) !important;
        color: transparent !important;
    }
    .item-icon.doing {
        border: 1px solid #f59e0b !important;
        background: #f59e0b !important;
        box-shadow: 0 0 8px #f59e0b !important;
    }
    .item-icon.passed {
        border: 1px solid #10b981 !important;
        background: #10b981 !important;
        box-shadow: 0 0 8px #10b981 !important;
    }
    .item-icon.failed {
        border: 1px solid #ef4444 !important;
        background: #ef4444 !important;
        box-shadow: 0 0 8px #ef4444 !important;
    }
    .item-details {
        flex: 1;
        min-width: 0;
    }
    .item-title {
        font-size: 12.5px;
        font-weight: 500;
        color: var(--text-accordion-item-title) !important;
    }
    .item-desc {
        font-size: 10.5px;
        color: var(--text-accordion-item-desc) !important;
        margin-top: 1px;
    }

    /* Right Column Widgets styling */
    .right-panel-card {
        background: var(--bg-card) !important;
        border: 1.5px solid var(--border-card) !important;
        border-radius: 10px !important;
        padding: 10px !important;
        margin-bottom: 8px !important;
        box-shadow: var(--shadow-panel) !important;
        color: var(--text-main) !important;
        position: relative;
        overflow: hidden;
    }
    .right-panel-card::before {
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(139, 92, 246, 0.5), rgba(96, 165, 250, 0.4), transparent);
    }
    .right-panel-header {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 9px;
        font-weight: 700;
        letter-spacing: 1.2px;
        text-transform: uppercase;
        background: linear-gradient(90deg, #a78bfa, #60a5fa);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin-bottom: 6px;
        padding-bottom: 6px;
        border-bottom: 1px solid var(--border-panel-header) !important;
    }
    .right-panel-header svg {
        flex-shrink: 0;
        -webkit-text-fill-color: initial;
        filter: drop-shadow(0 0 4px rgba(139, 92, 246, 0.4));
    }
    .right-panel-header .panel-icon {
        font-size: 14px;
        -webkit-text-fill-color: initial;
    }
    .execution-plan-list {
        display: flex;
        flex-direction: column;
        gap: 10px;
    }
    .execution-plan-item {
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 12px;
        color: var(--text-card-desc) !important;
        line-height: 1.4;
    }
    .execution-plan-item .status-icon {
        font-size: 14px;
        width: 14px;
        display: inline-block;
        text-align: center;
    }
    .execution-plan-item.active {
        color: var(--text-card-name) !important;
        font-weight: 500;
    }
    .agent-status-box {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 10px 12px;
        background: var(--bg-agent-status) !important;
        border: 1px solid var(--border-agent-status) !important;
        border-radius: 8px;
    }
    .agent-status-box .status-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        display: inline-block;
    }
    .agent-status-box .status-dot.idle {
        background-color: #10b981;
        box-shadow: 0 0 8px #10b981;
    }
    .agent-status-box .status-dot.running {
        background-color: #f59e0b;
        box-shadow: 0 0 8px #f59e0b;
    }
    .agent-status-box .status-text {
        font-size: 12px;
        color: var(--text-agent-status-label) !important;
        line-height: 1.4;
    }
    .terminal-container {
        height: 140px;
        min-height: 80px;
        max-height: 600px;
        overflow-y: auto;
        resize: vertical;
        background: var(--bg-action-log) !important;
        border: 1px solid var(--border-action-log) !important;
        border-radius: 8px;
        padding: 6px 10px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 10px;
    }
    .terminal-row {
        margin-bottom: 6px;
        line-height: 1.4;
        word-break: break-all;
    }
    .terminal-row.vision { color: var(--color-terminal-vision) !important; }
    .terminal-row.action { color: var(--color-terminal-action) !important; }
    .terminal-row.manager { color: var(--color-terminal-manager) !important; }
    .terminal-row.default { color: var(--color-terminal-default) !important; }
    .terminal-row.empty {
        color: #6b7280;
        text-align: center;
        margin-top: 70px;
    }
    .error-detection-empty {
        color: #6b7280;
        text-align: center;
        font-size: 11px;
        padding: 10px 0;
    }

    /* Right panel scrollable list */
    .execution-plan-list {
        height: 120px;
        min-height: 60px;
        max-height: 500px;
        overflow-y: auto;
        resize: vertical;
        scrollbar-width: thin;
        scrollbar-color: rgba(139, 92, 246, 0.3) transparent;
    }
    .execution-plan-list::-webkit-scrollbar { width: 3px; }
    .execution-plan-list::-webkit-scrollbar-thumb { background: rgba(139, 92, 246, 0.3); border-radius: 2px; }

    /* Findings scrollable container */
    .findings-container {
        max-height: 400px;
        overflow-y: auto;
        resize: vertical;
        padding-right: 4px;
    }
    .findings-container::-webkit-scrollbar { width: 3px; }
    .findings-container::-webkit-scrollbar-thumb { background: rgba(239, 68, 68, 0.3); border-radius: 2px; }
    
    /* Empty State */
    .empty-state-card {
        background: var(--bg-empty-state);
        border: 1px dashed var(--border-empty-state);
        border-radius: 8px;
        padding: 10px 16px;
        text-align: center;
        margin-bottom: 8px;
    }
    
    /* Browser Mockup Chrome */
    .browser-preview-card {
        background: var(--bg-browser-viewport-empty) !important;
        border: 1.5px solid var(--border-browser-chrome) !important;
        border-radius: 14px;
        overflow: hidden;
        display: flex;
        flex-direction: column;
        margin-top: 14px;
        box-shadow: var(--shadow-panel) !important;
        position: relative;
    }
    .browser-viewport-screenshot {
        width: 100%;
        max-height: 480px;
        overflow-y: auto;
        background-color: var(--bg-browser-viewport-empty);
        display: block;
    }
    .browser-viewport-screenshot img {
        width: 100%;
        height: auto;
        display: block;
    }
    .browser-preview-card::before {
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(139, 92, 246, 0.6), rgba(96, 165, 250, 0.4), transparent);
        z-index: 1;
    }
    .browser-chrome {
        background-color: var(--bg-browser-chrome) !important;
        border-bottom: 1px solid var(--border-browser-chrome) !important;
        padding: 8px 16px;
        display: flex;
        align-items: center;
        gap: 16px;
    }
    .browser-traffic-lights {
        display: flex;
        gap: 6px;
        align-items: center;
    }
    .browser-traffic-lights .light {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        display: inline-block;
    }
    .browser-traffic-lights .red { background-color: #ef4444; }
    .browser-traffic-lights .yellow { background-color: #f59e0b; }
    .browser-traffic-lights .green { background-color: #10b981; }
    
    .browser-nav-buttons {
        display: flex;
        gap: 8px;
        color: #6b7280;
        font-size: 12px;
    }
    .browser-url-bar {
        background-color: var(--bg-browser-url);
        border: 1px solid var(--border-browser-url) !important;
        border-radius: 6px;
        padding: 4px 12px;
        display: flex;
        align-items: center;
        flex: 1;
        min-width: 0;
        font-family: 'JetBrains Mono', monospace;
    }
    .browser-url-text {
        font-size: 11px;
        color: var(--text-browser-url);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    
    .browser-viewport-empty {
        min-height: 200px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        background-color: var(--bg-browser-viewport-empty);
        text-align: center;
        padding: 12px;
    }
    
    .browser-footer {
        background-color: var(--bg-browser-footer);
        border-top: 1px solid var(--border-browser-footer) !important;
        padding: 6px 16px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    
    /* Pulsing & Status Dots */
    .status-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        display: inline-block;
    }
    .status-dot-idle { background-color: #6b7280; }
    .status-dot-running {
        background-color: #f59e0b;
        box-shadow: 0 0 8px #f59e0b;
    }
    .status-dot-success {
        background-color: #10b981;
        box-shadow: 0 0 8px #10b981;
    }
    .status-dot-error {
        background-color: #ef4444;
        box-shadow: 0 0 8px #ef4444;
    }
    
    /* Panel Title Headers */
    .panel-header {
        font-size: 10px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1px;
        background: linear-gradient(90deg, #a78bfa, #60a5fa);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        padding-bottom: 6px;
        border-bottom: 1px solid rgba(139, 92, 246, 0.2) !important;
        margin-bottom: 10px;
    }
    
    /* Execution Step Items */
    .execution-step-row {
        display: flex;
        align-items: flex-start;
        padding: 6px 8px;
        border-radius: 6px;
        background: var(--bg-execution-step) !important;
        margin-bottom: 4px;
        border: 1px solid var(--border-execution-step) !important;
    }
    .execution-step-row:hover {
        background: var(--bg-execution-step-hover) !important;
    }
    .empty-list-placeholder {
        text-align: center;
        color: var(--text-execution-step-empty);
        font-size: 12px;
        padding: 16px 0;
    }
    
    /* Agent Status Widget */
    .agent-status-container {
        padding: 12px;
        border-radius: 8px;
        border: 1px solid var(--border-agent-status) !important;
        background: var(--bg-agent-status) !important;
    }
    .status-box-idle { border-left: 3px solid #6b7280; }
    .status-box-running {
        border-left: 3px solid #f59e0b;
        background: rgba(245, 158, 11, 0.05) !important;
    }
    .status-box-completed {
        border-left: 3px solid #10b981;
        background: rgba(16, 185, 129, 0.05) !important;
    }
    
    .status-label {
        font-size: 12px;
        font-weight: 600;
        color: var(--text-agent-status-label);
    }
    .status-thought {
        font-size: 11px;
        color: var(--text-agent-status-thought);
        margin-top: 6px;
        line-height: 1.4;
    }
    
    /* Finding items in Error Detection */
    .findings-count-badge {
        font-size: 10px;
        background: rgba(239, 68, 68, 0.2);
        color: #ef4444;
        padding: 1px 6px;
        border-radius: 10px;
        font-weight: bold;
    }
    
    .finding-alert-item {
        background: rgba(239, 68, 68, 0.1) !important;
        border: 1px solid rgba(239, 68, 68, 0.3) !important;
        border-left: 4px solid #ef4444 !important;
        padding: 10px;
        border-radius: 6px;
        font-size: 11px;
        margin-bottom: 8px;
    }
    
    /* Action logs scrollable terminal rows */
    .action-log-row {
        padding: 8px;
        border-radius: 4px;
        background: var(--bg-action-log) !important;
        border: 1px solid var(--border-action-log) !important;
        margin-bottom: 6px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
    }
    .action-log-row.border-badge-vision { border-left: 3px solid #f59e0b !important; }
    .action-log-row.border-badge-action { border-left: 3px solid #00d4ff !important; }
    .action-log-row.border-badge-manager { border-left: 3px solid #8b5cf6 !important; }
    
    .log-badge {
        font-size: 9px;
        font-weight: 600;
        padding: 1px 6px;
        border-radius: 3px;
        text-transform: uppercase;
    }
    .badge-vision { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
    .badge-action { background: rgba(0, 212, 255, 0.15); color: #00d4ff; }
    .badge-manager { background: rgba(139, 92, 246, 0.15); color: #8b5cf6; }
    
    .log-row-text {
        margin-top: 4px;
        color: var(--text-action-log);
        line-height: 1.4;
    }
    
    /* Help Icon Tooltip */
    .help-icon {
        position: relative;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 16px;
        height: 16px;
        background: rgba(139, 92, 246, 0.15);
        /* Override inherited -webkit-text-fill-color: transparent from h4 gradient */
        color: #a78bfa !important;
        -webkit-text-fill-color: #a78bfa !important;
        border: 1px solid rgba(139, 92, 246, 0.5);
        border-radius: 50%;
        font-size: 10px;
        font-weight: 700;
        font-family: 'Outfit', sans-serif;
        cursor: help;
        transition: all 0.2s ease;
        flex-shrink: 0;
        line-height: 1;
        vertical-align: middle;
    }
    .help-icon:hover {
        background: rgba(139, 92, 246, 0.3);
        color: #c4b5fd !important;
        -webkit-text-fill-color: #c4b5fd !important;
        border-color: rgba(139, 92, 246, 0.9);
        box-shadow: 0 0 6px rgba(139, 92, 246, 0.4);
    }
    .help-icon .tooltip-box {
        visibility: hidden;
        opacity: 0;
        position: fixed;
        background: var(--bg-help-tooltip, #111320);
        border: 1px solid var(--border-help-tooltip, rgba(139, 92, 246, 0.5));
        border-radius: 8px;
        padding: 10px 12px;
        width: 220px;
        font-size: 11.5px;
        /* Force tooltip text to always be readable */
        color: var(--text-help-tooltip, #c8d0e0) !important;
        -webkit-text-fill-color: var(--text-help-tooltip, #c8d0e0) !important;
        line-height: 1.5;
        box-shadow: 0 8px 24px rgba(0,0,0,0.6), 0 0 0 1px rgba(139, 92, 246, 0.2);
        transition: opacity 0.18s ease, visibility 0.18s ease;
        z-index: 99999;
        pointer-events: none;
        white-space: normal;
        word-wrap: break-word;
    }
    .help-icon:hover .tooltip-box {
        visibility: visible;
        opacity: 1;
    }
    
    /* Spinner animation */
    .spinner-container {
        display: flex;
        justify-content: center;
    }
    .spinner {
        width: 32px;
        height: 32px;
        border: 3px solid rgba(139, 92, 246, 0.2);
        border-top-color: #8b5cf6;
        border-radius: 50%;
        animation: spin 1s infinite linear;
    }
    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
    .animate-pulse {
        animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: .5; }
    }
    iframe[width="0"][height="0"] {
        display: none !important;
    }
    </style>
""",
    unsafe_allow_html=True,
)

# --- TỰ ĐỘNG PHÁT HIỆN THEME (LIGHT/DARK) & KÉO RỘNG SIDEBAR ---
st.components.v1.html(
    """
    <script>
    const parentDoc = window.parent.document;
    const parentHtml = parentDoc.documentElement;
    
    function updateTheme() {
        // Đọc computed style từ root của trang cha
        const rootStyle = window.getComputedStyle(parentHtml);
        
        let bgColor = rootStyle.getPropertyValue('--background-color').trim() || 
                      rootStyle.getPropertyValue('--st-background-color').trim();
                      
        // Nếu không có biến CSS, đọc màu nền của body
        if (!bgColor) {
            const body = parentDoc.body;
            if (body) {
                bgColor = window.getComputedStyle(body).backgroundColor;
            }
        }
        
        let isLight = false;
        if (bgColor) {
            const cleanBg = bgColor.replace(/\\s+/g, '').toLowerCase();
            if (cleanBg === '#ffffff' || cleanBg === '#fff' || cleanBg === 'white' || cleanBg === 'rgb(255,255,255)') {
                isLight = true;
            } else if (cleanBg.startsWith('rgb')) {
                const match = cleanBg.match(/rgb\\((\\d+),(\\d+),(\\d+)\\)/);
                if (match) {
                    const r = parseInt(match[1]);
                    const g = parseInt(match[2]);
                    const b = parseInt(match[3]);
                    const brightness = (r * 299 + g * 587 + b * 114) / 1000;
                    isLight = brightness > 150;
                }
            } else if (cleanBg.startsWith('#')) {
                const hex = cleanBg.slice(1);
                if (hex.length === 3 || hex.length === 6) {
                    const r = parseInt(hex.length === 3 ? hex[0] + hex[0] : hex.slice(0, 2), 16);
                    const g = parseInt(hex.length === 3 ? hex[1] + hex[1] : hex.slice(2, 4), 16);
                    const b = parseInt(hex.length === 3 ? hex[2] + hex[2] : hex.slice(4, 6), 16);
                    const brightness = (r * 299 + g * 587 + b * 114) / 1000;
                    isLight = brightness > 150;
                }
            }
        }
        
        const currentTheme = isLight ? 'light' : 'dark';
        if (parentHtml.getAttribute('data-theme') !== currentTheme) {
            parentHtml.setAttribute('data-theme', currentTheme);
        }
    }
    
    // --- DUAL PANEL RESIZER v2 — Fixed Overlay approach ---
    const MIN_SIDE_PX = 160;
    const MAX_SIDE_PX = 420;
    let resizerInitialized = false;
    let _repositionHandles = null;

    function buildGripHandle() {
        const wrap = parentDoc.createElement('div');
        wrap.className = 'panel-resize-handle';
        wrap.style.cssText = `
            position: fixed;
            top: 0;
            width: 20px;
            height: 100vh;
            z-index: 999999;
            cursor: col-resize;
            display: flex;
            align-items: center;
            justify-content: center;
            pointer-events: auto;
        `;

        // vertical line full height
        const vline = parentDoc.createElement('div');
        vline.className = 'rh-vline';
        vline.style.cssText = `
            position: absolute;
            top: 0; bottom: 0;
            left: 50%;
            transform: translateX(-50%);
            width: 2px;
            background: rgba(255,255,255,0.08);
            transition: background 0.2s;
            pointer-events: none;
        `;
        wrap.appendChild(vline);

        // pill grip button
        const pill = parentDoc.createElement('div');
        pill.className = 'rh-pill';
        pill.style.cssText = `
            position: relative; z-index: 1;
            width: 16px; height: 44px;
            border-radius: 8px;
            background: #12131e;
            border: 1.5px solid rgba(255,255,255,0.22);
            box-shadow: 0 2px 12px rgba(0,0,0,0.7), inset 0 1px 0 rgba(255,255,255,0.06);
            display: flex; flex-direction: column;
            align-items: center; justify-content: center; gap: 4px;
            transition: background 0.15s, border-color 0.15s, box-shadow 0.15s;
        `;
        for (let i = 0; i < 4; i++) {
            const d = parentDoc.createElement('div');
            d.style.cssText = 'width:4px;height:4px;border-radius:50%;background:rgba(255,255,255,0.35);transition:background 0.15s;';
            pill.appendChild(d);
        }
        wrap.appendChild(pill);

        // hover effects
        wrap.addEventListener('mouseenter', () => {
            vline.style.background = 'rgba(139,92,246,0.6)';
            pill.style.background = '#261a42';
            pill.style.borderColor = '#8b5cf6';
            pill.style.boxShadow = '0 0 16px rgba(139,92,246,0.5), 0 2px 12px rgba(0,0,0,0.7)';
            pill.querySelectorAll('div').forEach(d => d.style.background = '#a78bfa');
        });
        wrap.addEventListener('mouseleave', () => {
            if (!wrap._dragging) {
                vline.style.background = 'rgba(255,255,255,0.08)';
                pill.style.background = '#12131e';
                pill.style.borderColor = 'rgba(255,255,255,0.22)';
                pill.style.boxShadow = '0 2px 12px rgba(0,0,0,0.7), inset 0 1px 0 rgba(255,255,255,0.06)';
                pill.querySelectorAll('div').forEach(d => d.style.background = 'rgba(255,255,255,0.35)');
            }
        });

        parentDoc.body.appendChild(wrap);
        return { wrap, pill, vline };
    }

    function setupDualPanelResizer() {
        // find 3-column block
        const allBlocks = Array.from(parentDoc.querySelectorAll('[data-testid="stHorizontalBlock"]'));
        let mainBlock = null;
        for (const b of allBlocks) {
            const dc = Array.from(b.children).filter(c => c.getAttribute('data-testid') === 'column');
            if (dc.length === 3) { mainBlock = b; break; }
        }
        if (!mainBlock) return;

        const cols = Array.from(mainBlock.children).filter(c => c.getAttribute('data-testid') === 'column');
        if (cols.length !== 3) return;

        const [leftCol, centerCol, rightCol] = cols;

        // Only create handles once — on subsequent calls just reposition
        if (resizerInitialized) {
            // repositionHandles is assigned below after first init
            if (typeof _repositionHandles === 'function') _repositionHandles();
            return;
        }
        resizerInitialized = true;

        // Override Streamlit's column flex widths
        const totalW = mainBlock.offsetWidth || window.parent.innerWidth;
        const sideW = Math.max(MIN_SIDE_PX, Math.min(MAX_SIDE_PX, Math.round(totalW * 0.19)));

        const applyFixed = (col, w) => {
            col.style.setProperty('flex', `0 0 ${w}px`, 'important');
            col.style.setProperty('width', `${w}px`, 'important');
            col.style.setProperty('min-width', `${MIN_SIDE_PX}px`, 'important');
            col.style.setProperty('max-width', `${MAX_SIDE_PX}px`, 'important');
        };
        const applyCenter = (col) => {
            col.style.setProperty('flex', '1 1 auto', 'important');
            col.style.setProperty('min-width', '300px', 'important');
            col.style.removeProperty('max-width');
        };

        applyFixed(leftCol, sideW);
        applyCenter(centerCol);
        applyFixed(rightCol, sideW);

        const { wrap: h1, pill: p1, vline: v1 } = buildGripHandle();
        const { wrap: h2, pill: p2, vline: v2 } = buildGripHandle();

        function repositionHandles() {
            const lb = leftCol.getBoundingClientRect();
            const rb = rightCol.getBoundingClientRect();
            if (lb.width > 0) {
                h1.style.left = (lb.right - 10) + 'px';
                h2.style.left = (rb.left - 10) + 'px';
            }
        }
        _repositionHandles = repositionHandles;  // expose to outer scope

        repositionHandles();

        // Reposition on resize
        window.parent.addEventListener('resize', repositionHandles);

        function makeDrag(handle, targetCol, side, pill, vline) {
            handle.addEventListener('mousedown', (e) => {
                e.preventDefault();
                handle._dragging = true;
                const startX = e.clientX;
                const startW = targetCol.offsetWidth;
                parentDoc.body.style.cursor = 'col-resize';
                parentDoc.body.style.userSelect = 'none';
                pill.style.background = '#3a1f5e';
                pill.style.borderColor = '#a78bfa';
                pill.style.boxShadow = '0 0 20px rgba(139,92,246,0.8)';
                vline.style.background = 'rgba(167,139,250,0.8)';

                function onMove(ev) {
                    const dx = ev.clientX - startX;
                    const newW = side === 'left'
                        ? Math.max(MIN_SIDE_PX, Math.min(MAX_SIDE_PX, startW + dx))
                        : Math.max(MIN_SIDE_PX, Math.min(MAX_SIDE_PX, startW - dx));
                    applyFixed(targetCol, newW);
                    repositionHandles();
                }
                function onUp() {
                    handle._dragging = false;
                    parentDoc.body.style.cursor = '';
                    parentDoc.body.style.userSelect = '';
                    pill.style.background = '#12131e';
                    pill.style.borderColor = 'rgba(255,255,255,0.22)';
                    pill.style.boxShadow = '0 2px 12px rgba(0,0,0,0.7)';
                    vline.style.background = 'rgba(255,255,255,0.08)';
                    parentDoc.removeEventListener('mousemove', onMove);
                    parentDoc.removeEventListener('mouseup', onUp);
                }
                parentDoc.addEventListener('mousemove', onMove);
                parentDoc.addEventListener('mouseup', onUp);
            });
        }

        makeDrag(h1, leftCol, 'left', p1, v1);
        makeDrag(h2, rightCol, 'right', p2, v2);
    }

    function setupSidebarResizer() {
        setupDualPanelResizer();
    }
    
    // --- TOOLTIP FIXED POSITIONING ---
    // Since help-icon's tooltip uses position:fixed to escape overflow:hidden containers,
    // we need JS to set the correct top/left coordinates on hover.
    function setupTooltipPositioning() {
        const icons = parentDoc.querySelectorAll('.help-icon');
        icons.forEach(icon => {
            if (icon._tooltipBound) return;
            icon._tooltipBound = true;
            const box = icon.querySelector('.tooltip-box');
            if (!box) return;

            icon.addEventListener('mouseenter', () => {
                const rect = icon.getBoundingClientRect();
                const vpW = window.parent.innerWidth;
                const vpH = window.parent.innerHeight;
                // Position tooltip to the right of the icon
                let left = rect.right + 8;
                let top = rect.top - 4;
                // If tooltip would overflow right edge, show it to the left
                if (left + 220 > vpW - 8) {
                    left = rect.left - 228;
                }
                // If tooltip would overflow bottom, move it up
                if (top + 120 > vpH - 8) {
                    top = vpH - 130;
                }
                box.style.left = left + 'px';
                box.style.top = top + 'px';
            });
        });
    }

    // Re-run periodically to catch dynamically added icons
    setInterval(() => {
        updateTheme();
        setupSidebarResizer();
        setupTooltipPositioning();
    }, 500);
    
    updateTheme();
    setupSidebarResizer();
    setupTooltipPositioning();
    </script>
    """,
    height=0,
    width=0
)


# --- KHỞI TẠO STATE ---
if "agent_state" not in st.session_state:
    st.session_state.agent_state = {
        "model_name": "",
        "goal": "",
        "url": "",
        "screenshot": None,
        "history": [],
        "last_thought": "Sẵn sàng khởi động...",
        "findings": [],
        "is_complete": False,
        "base_url": None,
        "dom_elements": None,
        "current_page_plan": [],
        "messages": [],
    }
if "running" not in st.session_state:
    st.session_state.running = False
if "building_task_plan" not in st.session_state:
    st.session_state.building_task_plan = False


def auto_clear_state():
    if not st.session_state.running and st.session_state.agent_state.get("is_complete"):
        st.session_state.pop("tc_gen_df", None)
        st.session_state.pop("tc_gen_result", None)
        st.session_state.pop("test_case_json_str", None)
        st.session_state.pop("pre_built_task_plan", None)
        st.session_state.agent_state = {
            "model_name": "",
            "goal": "",
            "url": "",
            "screenshot": None,
            "history": [],
            "last_thought": "Tự động làm mới...",
            "findings": [],
            "is_complete": False,
            "base_url": None,
            "dom_elements": None,
            "test_case_data": None,
            "messages": [],
            "task_plan": [],
        }


# --- SIDEBAR (CẤU HÌNH TỐI GIẢN) ---
llm_factory = LLMFactory()
available_models = llm_factory.get_available_models(True)
all_models = llm_factory.get_available_models(False)


# --- AI SUGGESTION FOR PLACEHOLDER ---
def get_ai_suggestion(model_name):
    """Lấy một câu gợi ý ngẫu nhiên từ AI để hiển thị ở Placeholder"""
    from agents.llm_factory import LLMFactory

    factory = LLMFactory()

    prompt = """
    You are a professional AI Testing assistant.
    Generate exactly ONE short suggestion (under 30 words) for the user to input as a testing request.
    The suggestion should vary: it could be a security test, UI test, or specific web task.
    Example: 'Kiểm tra lỗi hiển thị trên trang chủ 3dart.vn', 'Đăng nhập vào hệ thống quản trị và kiểm tra danh sách bài viết'.
    Return ONLY the suggestion, nothing else. CRITICAL: The generated suggestion MUST be in Vietnamese.
    """

    try:
        if factory.provider == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI
            from langchain_core.messages import HumanMessage

            clean_model = model_name.replace("models/", "").replace("google/", "")
            llm = ChatGoogleGenerativeAI(model=clean_model)
            response = llm.invoke([HumanMessage(content=prompt)])
            return response.content.strip().replace('"', "")
        elif factory.provider == "openrouter":
            import requests

            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {factory.openrouter_key}"},
                json={
                    "model": model_name,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            return (
                response.json()["choices"][0]["message"]["content"]
                .strip()
                .replace('"', "")
            )
        return "Nhập yêu cầu của bạn tại đây... (Ví dụ: Test bảo mật trang abc.com)"
    except:
        return "Nhập yêu cầu của bạn tại đây... (Ví dụ: Test bảo mật trang abc.com)"


if "placeholder_suggestion" not in st.session_state:
    st.session_state.placeholder_suggestion = get_ai_suggestion(available_models[0])

col_sidebar, col_center, col_right = st.columns([1.3, 4.0, 1.3], gap="small")

with col_sidebar:
    import base64
    try:
        with open("assets/ai_agent_logo.png", "rb") as f:
            logo_b64 = base64.b64encode(f.read()).decode()
        st.markdown(
            f"""
            <div class="logo-header-container">
                <img src="data:image/png;base64,{logo_b64}" class="logo-img" />
                <div class="logo-text-wrapper">
                    <h2 class="logo-title">AI Agent Tester</h2>
                    <p class="logo-subtitle">Professional Testing Platform</p>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    except Exception:
        col_logo, col_logo_text = st.columns([1, 4])
        with col_logo:
            st.image("assets/ai_agent_logo.png", use_container_width=True)
        with col_logo_text:
            st.markdown(
                """
                <div style="margin-top: 2px;">
                    <h2 style="margin: 0; font-size: 13px; font-weight: 700; color: var(--text-section-header);">AI Agent Tester</h2>
                    <p style="margin: 0; font-size: 9px; color: var(--text-card-desc);">Professional Testing Platform</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # ── Dynamic Model Routing ─────────────────────────────────────────────
    st.markdown(
        '<div class="section-header"><h4 style="display: flex; align-items: center; gap: 8px;"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--theme-icon-color)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0;"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/><path d="m5 3 1 2.5L8.5 6 6 7 5 9.5 4 7 1.5 6 4 5.5 5 3Z"/><path d="m19 17 1 2.5 2.5.5-2.5 1-1 2.5-1-2.5-2.5-1 2.5-1 1-2.5Z"/></svg>Cấu hình Model<span class="help-icon" style="margin-left:6px;">?<span class="tooltip-box">Chọn model AI để điều khiển logic tổng thể (Brain) và model đánh giá kết quả (Evaluation). Brain Model cần mạnh, Evaluation Model có thể dùng model nhẹ hơn để tiết kiệm chi phí.</span></span></h4></div>',
        unsafe_allow_html=True,
    )
    # Brain model defaults to a powerful but cost-effective model
    brain_default_candidates = [
        "google/gemini-2.5-pro",
        "google/gemini-2.5-flash",
        "google/gemini-2.0-flash-001",
        "google/gemini-3.1-flash-lite",
    ]
    brain_default_idx = 0
    for candidate in brain_default_candidates:
        if candidate in available_models:
            brain_default_idx = available_models.index(candidate)
            break
    brain_model = st.selectbox(
        "Brain Model (Điều khiển chính)",
        available_models,
        index=brain_default_idx,
        key="brain_model",
        on_change=auto_clear_state,
    )

    # Eval model defaults to a fast/cheap vision model if available
    eval_default_candidates = [
        "google/gemini-3.1-flash-lite",
        "google/gemini-2.0-flash-001",
        "google/gemini-2.5-flash",
    ]
    eval_default_idx = 0
    for candidate in eval_default_candidates:
        if candidate in available_models:
            eval_default_idx = available_models.index(candidate)
            break
    eval_model = st.selectbox(
        "Evaluation Model (Đánh giá)",
        available_models,
        index=eval_default_idx,
        key="eval_model",
    )
    # Backward compat alias
    selected_model = brain_model

    st.markdown("---")

    # ── Test Case Management ──────────────────────────────────────────────
    st.markdown(
        '<div class="section-header"><h4 style="display: flex; align-items: center; gap: 8px;"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--theme-icon-color)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0;"><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/></svg>Test Cases<span class="help-icon" style="margin-left:6px;">?<span class="tooltip-box">Tải lên file kế hoạch kiểm thử (.xlsx, .csv, .json, .md). Agent sẽ tự động đọc và thực thi từng test case theo thứ tự. Hỗ trợ nhiều file cùng lúc để sinh test case tự động.</span></span></h4><div style="font-size: 14px; font-weight: bold; color: var(--text-label); cursor: pointer;">+</div></div>',
        unsafe_allow_html=True,
    )

    # Render custom dotted upload box wrapper
    st.markdown('<div class="custom-upload-wrapper">', unsafe_allow_html=True)
    uploaded_files = st.file_uploader(
        "Tải lên kế hoạch kiểm thử",
        type=["xlsx", "xls", "csv", "docx", "md", "json"],
        key="universal_upload",
        label_visibility="collapsed",
        accept_multiple_files=True,
    )
    st.markdown('</div>', unsafe_allow_html=True)

    if uploaded_files:
        # Render clean success alert matching screenshot
        st.markdown(
            """
            <div class="custom-alert-success">
                <span class="alert-icon">✓</span>
                <span class="alert-text">Đã tải kế hoạch kiểm thử thành công</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Kiểm tra xem có phải nạp Test Case hay không (Chỉ 1 file và là .md hoặc .json)
        is_import_tc = False
        if len(uploaded_files) == 1:
            file_ext = uploaded_files[0].name.split(".")[-1].lower()
            if file_ext in ["md", "json"]:
                is_import_tc = True

        if is_import_tc:
            uploaded_file = uploaded_files[0]
            file_ext = uploaded_file.name.split(".")[-1].lower()
            current_file_id = f"{uploaded_file.name}_{uploaded_file.size}"

            # Logic nạp Test Case vào DataFrame để chỉnh sửa
            if st.session_state.get("last_uploaded_tc_id") != current_file_id:
                st.session_state.building_task_plan = True
                content = uploaded_file.getvalue().decode("utf-8")
                
                df = None
                if file_ext == "md":
                    rows = parse_markdown_table(content)
                    if rows:
                        import pandas as pd
                        df = pd.DataFrame(rows)
                elif file_ext == "json":
                    df = load_json_to_df(content)
                    
                if df is not None and not df.empty:
                    df = normalize_df_columns(df)
                    st.session_state["tc_gen_df"] = df
                    st.session_state["tc_gen_result"] = content if file_ext == "md" else "JSON_IMPORT"
                    st.session_state["last_uploaded_tc_id"] = current_file_id
                    
                    sync_df_to_test_cases(df)
                    st.session_state.building_task_plan = False
                else:
                    st.session_state.building_task_plan = False
                    st.error("❌ Không thể đọc file kế hoạch kiểm thử. Vui lòng kiểm tra định dạng file.")
        else:
            # Logic mới cho sinh Test Case từ nhiều file
            st.markdown(
                "<small>File đặc tả. Chọn model và nhấn Generate để sinh test case tự động.</small>",
                unsafe_allow_html=True,
            )

            col_gen1, col_gen2 = st.columns([2, 1])
            with col_gen1:
                pro_models = [m for m in all_models if "gemini" in m.lower() and "pro" in m.lower()]
                pro_models.sort(reverse=True)
                
                tc_gen_default_idx = 0
                if pro_models:
                    tc_gen_default_idx = all_models.index(pro_models[0])
                else:
                    fallback_candidates = [
                        "google/gemini-2.5-flash",
                        "google/gemini-2.0-flash-001",
                        "google/gemini-3.1-flash-lite",
                    ]
                    for candidate in fallback_candidates:
                        if candidate in all_models:
                            tc_gen_default_idx = all_models.index(candidate)
                            break
                            
                gen_model_choice = st.selectbox(
                    "Model sinh test case",
                    all_models,
                    index=tc_gen_default_idx,
                    key="tc_gen_model",
                    label_visibility="collapsed",
                )
            with col_gen2:
                generate_btn = st.button(
                    "⚡ Tạo",
                    key="tc_gen_btn",
                    use_container_width=True,
                    type="primary",
                )

            if generate_btn:
                from tools.doc_parser import parse_uploaded_file
                from tools.testcase_generator import generate_test_cases

                with st.spinner("Đang phân tích file..."):
                    try:
                        combined_text = ""
                        for f in uploaded_files:
                            file_ext = f.name.split(".")[-1].lower()
                            if file_ext in ["md", "json"]:
                                file_text = f.getvalue().decode("utf-8")
                            else:
                                file_text = parse_uploaded_file(f)
                            combined_text += f"\n\n--- Content from: {f.name} ---\n{file_text}"
                        
                        st.session_state["tc_gen_parsed_text"] = combined_text
                        st.session_state["tc_gen_error"] = None
                    except Exception as ve:
                        st.session_state["tc_gen_error"] = f"File read error: {str(ve)}"
                        combined_text = None

                if combined_text and not st.session_state.get("tc_gen_error"):
                    with st.spinner("Đang sinh Test Cases..."):
                        try:
                            test_plan = generate_test_cases(
                                combined_text, gen_model_choice
                            )
                            st.session_state["tc_gen_result"] = test_plan
                            st.session_state["tc_gen_error"] = None
                            
                            if test_plan:
                                rows = parse_markdown_table(test_plan)
                                if rows:
                                    import pandas as pd
                                    df = pd.DataFrame(rows)
                                    df = normalize_df_columns(df)
                                    st.session_state["tc_gen_df"] = df
                                    sync_df_to_test_cases(df)
                        except RuntimeError as re_err:
                            st.session_state["tc_gen_error"] = str(re_err)
                            st.session_state["tc_gen_result"] = None
                            st.session_state.pop("tc_gen_df", None)

            if st.session_state.get("tc_gen_error"):
                st.error(f"❌ {st.session_state['tc_gen_error']}")

    else:
        if "last_uploaded_tc_id" in st.session_state:
            st.session_state.pop("last_uploaded_tc_id", None)
            st.session_state.pop("test_case_json_str", None)
            st.session_state.pop("tc_gen_result", None)
            st.session_state.pop("tc_gen_df", None)

    st.markdown("---")
    st.markdown(
        '<div class="section-header"><h4 style="display: flex; align-items: center; gap: 8px;"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--theme-icon-color)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0;"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>Yêu cầu kiểm thử<span class="help-icon" style="margin-left:6px;">?<span class="tooltip-box">Nhập mô tả bằng ngôn ngữ tự nhiên. Ví dụ: "Kiểm tra bảo mật trang abc.com với tài khoản admin/123456". Agent sẽ tự phân tích URL, tài khoản, và mục tiêu.</span></span></h4></div>',
        unsafe_allow_html=True,
    )
    if st.session_state.get("test_case_json_str"):
        st.markdown(
            """
            <div class="custom-alert-info">
                <span class="alert-icon">📄</span>
                <span class="alert-text">Đã tải test cases. Agent sẽ ưu tiên thực thi các kịch bản này.</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    user_prompt = st.text_area(
        "Mô tả yêu cầu kiểm thử...",
        placeholder="Mô tả yêu cầu của bạn... Agent sẽ tự phân tích URL, thông tin đăng nhập và các tác vụ cần thực hiện.",
        height=95,
        key="user_prompt",
        label_visibility="collapsed",
    )

    st.markdown(
        """
        <div style="font-size: 10px; color: var(--placeholder-color); margin-top: 2px; line-height: 1.3;">
            💡 Dùng ngôn ngữ tự nhiên. Agent hiểu URL và thông tin đăng nhập.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Luôn bật chế độ dịch sang tiếng Việt mặc định
    auto_translate = True

    st.markdown("---")
    _is_building = st.session_state.get("building_task_plan", False)
    if _is_building:
        st.info("⏳ Đang tạo kế hoạch thực thi từ file...", icon="🔄")
        
    col_s1, col_s2, col_s3 = st.columns([3, 1, 1])
    start_btn = col_s1.button(
        "⚡ Chạy Test",
        type="primary",
        use_container_width=True,
        disabled=st.session_state.running or _is_building,
    )
    stop_btn = col_s2.button(
        "Dừng",
        type="secondary",
        use_container_width=True,
        disabled=(not st.session_state.running) or _is_building,
    )
    clear_btn = col_s3.button(
        "Xóa",
        type="secondary",
        use_container_width=True,
        disabled=st.session_state.running or _is_building,
    )


# --- AI INTENT ANALYZER ---
def analyze_user_prompt(prompt, model_name):
    """Sử dụng LLMFactory để bóc tách thông tin từ prompt của người dùng"""
    import json
    from agents.llm_factory import LLMFactory

    factory = LLMFactory()

    system_instruction = """
    Analyze the user request and return a precise JSON object.
    Rules:
    - url: Find the website URL (if any).
    - goal: A concise goal description in English.
    - login_user: Username (if any).
    - login_pass: Password (if any).
    - is_web_test: true if it is a comprehensive web audit/test request, false if it is a specific linear task.
    - test_ui: true/false.
    - test_security: true/false.
    - start_from_step: If the user mentions skipping steps or starting from a specific step number, extract the number of steps to SKIP (0-indexed count to skip). Examples:
        - "bỏ qua 20 bước đầu" → 20
        - "skip first 20 steps" → 20
        - "bắt đầu từ bước 21" → 20  (skip 20 to start at 21)
        - "start from step 30" → 29  (skip 29 to start at 30)
        - "thực hiện từ bước thứ 5" → 4
        - If no skip/start instruction found → 0
    - run_last_n_steps: If the user mentions running only a specific number of steps at the end of the scenario/script (e.g. "chạy 5 bước cuối", "run last 5 steps", "5 bước cuối cùng", "test 5 bước cuối của kịch bản này"), extract that number N as integer. Otherwise, return 0.
    
    JSON Format:
    {
        "url": "...",
        "goal": "...",
        "login_user": "...",
        "login_pass": "...",
        "is_web_test": true,
        "test_ui": true,
        "test_security": true,
        "start_from_step": 0,
        "run_last_n_steps": 0
    }
    """

    # Sử dụng phương thức generate_content của factory (async wrapper)
    # Vì hàm này không async, ta dùng logic sync hoặc gọi trực tiếp nếu factory hỗ trợ
    # Ở đây tôi sẽ dùng logic đơn giản để gọi LLM

    try:
        # Gọi qua factory (generate_content là async, nhưng ở đây ta cần kết quả ngay)
        # Tạm thời dùng logic invoke trực tiếp để tránh xung đột async trong Streamlit thread
        if factory.provider == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI
            from langchain_core.messages import HumanMessage

            # Xử lý tên model nếu có prefix
            clean_model = model_name.replace("models/", "").replace("google/", "")
            llm = ChatGoogleGenerativeAI(model=clean_model)
            response = llm.invoke(
                [HumanMessage(content=f"{system_instruction}\n\nUser Prompt: {prompt}")]
            )
            content = response.content
        elif factory.provider == "openrouter":
            import requests

            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {factory.openrouter_key}"},
                json={
                    "model": model_name,
                    "messages": [
                        {
                            "role": "user",
                            "content": f"{system_instruction}\n\nUser Prompt: {prompt}",
                        }
                    ],
                },
            )
            try:
                resp_json = response.json()
                if "choices" in resp_json and len(resp_json["choices"]) > 0:
                    content = resp_json["choices"][0]["message"]["content"]
                else:
                    content = "{}"
            except Exception:
                content = "{}"
        else:
            # Fallback cho các provider khác
            content = "{}"

        if not content:
            content = "{}"

        # Làm sạch chuỗi JSON nếu AI trả về kèm markdown
        import re

        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            clean_content = match.group(0)
        else:
            clean_content = content.replace("```json", "").replace("```", "").strip()

        if not clean_content:
            clean_content = "{}"

        result = json.loads(clean_content)

        # Fallback to regex if URL is not found
        if not result.get("url"):
            import re

            url_match = re.search(
                r"(https?://[^\s]+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}[^\s]*)", prompt
            )
            if url_match:
                result["url"] = url_match.group(1)

        return result
    except Exception as e:
        print(f"Error in analyze_user_prompt: {e}")

        import re

        url_match = re.search(
            r"(https?://[^\s]+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}[^\s]*)", prompt
        )
        fallback_url = url_match.group(1) if url_match else None

        return {
            "url": fallback_url,
            "goal": prompt,
            "login_user": None,
            "login_pass": None,
            "is_web_test": False,
            "test_ui": True,
            "test_security": False,
            "start_from_step": 0,
            "run_last_n_steps": 0,
        }


if clear_btn:
    from tools.report_tool import cleanup_reports

    cleanup_reports()
    # Xoá pre_built_task_plan để tránh kế hoạch cũ bị tái sử dụng
    st.session_state.pop("pre_built_task_plan", None)
    st.session_state.pop("test_case_json_str", None)
    st.session_state.pop("last_uploaded_tc_id", None)
    st.session_state.pop("tc_gen_result", None)
    st.session_state.pop("skip_steps_count", None)  # Reset skip count
    st.session_state.pop("tc_gen_df", None)
    st.session_state.agent_state = {
        "model_name": "",
        "url": "",
        "screenshot": None,
        "history": [],
        "last_thought": "Đã làm mới...",
        "findings": [],
        "is_complete": False,
        "base_url": None,
        "dom_elements": None,
        "test_case_data": None,
        "goal": "",
        "messages": [],
        "findings": [],
        "history": [],
        "task_plan": [],
    }
    st.rerun()


# --- LOGIC CHẠY AGENT ---
async def run_agent_async(
    url,
    goal,
    model,
    login_user=None,
    login_pass=None,
    brain_model=None,
    eval_model=None,
    test_case_data=None,
):
    from tools.report_tool import cleanup_reports
    from tools.data_tools import _do_cleanup_test_assets

    cleanup_reports()
    # Auto-cleanup: remove any generated test files left from a previous crashed session
    _do_cleanup_test_assets()
    app = create_graph()

    initial_state = {
        "url": url,
        "screenshot": None,
        "next_action": None,
        "history": [],
        "last_thought": "Đang khởi động trình duyệt...",
        "findings": [],
        "is_complete": False,
        "model_name": model,
        "base_url": None,
        "dom_elements": None,
        "login_user": login_user,
        "login_pass": login_pass,
        "task_plan": st.session_state.agent_state.get("task_plan", []),
        "_api_error_count": 0,
        "_empty_count": 0,
        "_last_actions": [],
        "step_retry_count": 0,
        # === EVN QA New Fields ===
        "model_config": {
            "brain_model": brain_model or model,
            "eval_model": eval_model or model,
        },
        "test_scope": {},  # Populated by scoping_node
        "test_case_data": test_case_data,
        "goal": test_case_data.get("title", "Execute provided test cases.")
        if isinstance(test_case_data, dict)
        else ("Execute provided test cases." if test_case_data else goal),
        "messages": [],
        "findings": [],
        "history": [],
        "is_bug": False,
        "severity": None,
        "last_action_location": None,
        "current_step_count": 0,
        "max_steps": 50,
        "final_report": None,
    }
    st.session_state.agent_state = initial_state

    try:
        async for event in app.astream(initial_state):
            if not st.session_state.running:
                break

            for node_name, state in event.items():
                # Gắn nhãn node vào lịch sử mới trước khi gộp
                if "history" in state and state["history"]:
                    new_h = state["history"]
                    for i in range(len(new_h)):
                        if isinstance(new_h[i], str) and not new_h[i].startswith("["):
                            new_h[i] = f"[{node_name.upper()}] {new_h[i]}"

                    # Gộp vào history hiện tại thay vì ghi đè hoàn toàn
                    current_h = st.session_state.agent_state.get("history", [])
                    for item in new_h:
                        if item not in current_h:
                            current_h.append(item)
                    state["history"] = current_h

                try:
                    st.session_state.agent_state.update(state)
                except Exception:
                    pass  # Ignore state updates if session is dead

                await asyncio.sleep(0.1)

                if st.session_state.agent_state.get("is_complete"):
                    break
    except Exception as e:
        print(f"⚠️ Error in agent thread: {e}")
    finally:
        st.session_state.running = False

        # Tự động đóng trình duyệt để giải phóng bộ nhớ
        try:
            await BrowserManager.close()
        except Exception as close_err:
            print(f"⚠️ Lỗi khi đóng trình duyệt: {close_err}")
            BrowserManager.force_reset()
        print("💡 Task finished. Browser closed to free memory.")

        # Tự động tạo báo cáo Excel (EVN QA 3-Sheet)
        try:
            from multi_agent.nodes.reporter_node import reporter_node
            
            agent_state = st.session_state.agent_state
            if "final_report" not in agent_state:
                print("📋 [Finally] Báo cáo chưa được tạo. Đang gọi Reporter Node để tạo báo cáo đầy đủ...")
                st.session_state.agent_state["last_thought"] = "Đang tổng hợp báo cáo đầy đủ..."
                
                # Gọi reporter_node để xử lý tổng hợp và tạo file Excel v3
                updated_state = await reporter_node(agent_state)
                st.session_state.agent_state.update(updated_state)
            else:
                print("📊 [Finally] Báo cáo đã được tạo bởi Graph trước đó.")
                
            # Đảm bảo cập nhật đường dẫn báo cáo để UI hiển thị
            if "final_report" in st.session_state.agent_state:
                excel_path = st.session_state.agent_state["final_report"].get("excel_path")
                if excel_path:
                    st.session_state.agent_state["last_report_path"] = excel_path
                    print(f"📊 Báo cáo đã được tạo tại: {excel_path}")
                    
        except Exception as report_err:
            print(f"⚠️ Lỗi khi tạo báo cáo tự động: {report_err}")


if start_btn:
    if not user_prompt:
        st.error("⚠️ Vui lòng nhập yêu cầu kiểm thử trước khi chạy.")
    else:
        # ĐẢM BẢO đóng trình duyệt cũ trước khi khởi tạo mới (tránh zombie + nhân đôi UI)
        BrowserManager.force_reset()

        st.session_state.running = True
        with st.status("🧠 Đang phân tích yêu cầu bằng AI...", expanded=True) as status:
            analysis = analyze_user_prompt(user_prompt, selected_model)
            st.write(f"🌐 URL: `{analysis.get('url')}`")
            st.write(f"🎯 Mục tiêu: {analysis.get('goal')}")
            if analysis.get("login_user"):
                st.write(
                    f"🔑 Đã nhận thông tin đăng nhập cho `{analysis.get('login_user')}`"
                )
            status.update(
                label="✅ Phân tích hoàn tất! Đang khởi động Agent...",
                state="complete",
                expanded=False,
            )

        target_url = analysis.get("url")
        if not target_url:
            st.error(
                "⚠️ Không tìm thấy URL trong yêu cầu. Vui lòng nhập URL của trang cần kiểm thử."
            )
            st.session_state.running = False
            st.stop()

        if target_url and not target_url.startswith("http"):
            target_url = "https://" + target_url

        test_goal = analysis.get("goal")
        user_val = analysis.get("login_user")
        pass_val = analysis.get("login_pass")
        is_web_test = analysis.get("is_web_test", True)
        test_ui_checked = analysis.get("test_ui", True)
        test_sec_checked = analysis.get("test_security", True)

        # ── Xác định số bước cần bỏ qua từ prompt ───────────────────────────
        skip_count = int(analysis.get("start_from_step", 0) or 0)
        run_last_n = int(analysis.get("run_last_n_steps", 0) or 0)

        # Parse test_case_data from sidebar
        import json as _json_parse

        _tc_str = st.session_state.get("test_case_json_str", "").strip()
        parsed_test_case = None
        # ✅ Ưu tiên dùng task_plan đã được tạo sẵn khi nạp file,
        # tránh tạo lại khi Agent chạy
        initial_task_plan = st.session_state.get("pre_built_task_plan", [])
        if _tc_str:
            try:
                parsed_test_case = _json_parse.loads(_tc_str)
                # Chỉ tạo lại task_plan nếu chưa có sẵn từ lúc nạp file
                if isinstance(parsed_test_case, list) and not initial_task_plan:
                    for tc in parsed_test_case:
                        scenario = tc.get("scenario", "")
                        tc_id = tc.get("id", "")
                        for step in tc.get("steps", []):
                            label = f"[{tc_id}] [{scenario}]" if tc_id else f"[{scenario}]"
                            initial_task_plan.append(
                                {"step": f"{label} {step}", "status": "todo"}
                            )
            except Exception:
                parsed_test_case = None  # Fallback to common-sense mode

        # Nếu có yêu cầu chạy N bước cuối của kịch bản, tính toán skip_count dựa trên tổng số bước
        if run_last_n > 0 and initial_task_plan:
            skip_count = max(0, len(initial_task_plan) - run_last_n)

        st.session_state["skip_steps_count"] = skip_count

        # ── Áp dụng skip: đánh dấu N bước đầu là "skipped" ──────────────────
        if skip_count > 0 and initial_task_plan:
            actual_skip = min(skip_count, len(initial_task_plan))
            for i in range(actual_skip):
                initial_task_plan[i]["status"] = "skipped"
            st.toast(f"⏭️ Đã bỏ qua {actual_skip} bước đầu. Bắt đầu từ bước #{actual_skip + 1}", icon="⏭️")

        # Xoá trạng thái cũ để UI làm mới ngay lập tức
        _initial_history = []
        if skip_count > 0 and initial_task_plan:
            _actual_skip = min(skip_count, len(initial_task_plan))
            _initial_history.append(
                f"⏭️ [SKIP] Đã bỏ qua {_actual_skip} bước đầu theo yêu cầu. Agent bắt đầu thực hiện từ bước #{_actual_skip + 1}."
            )

        st.session_state.agent_state = {
            "model_name": selected_model,
            "goal": test_goal,
            "url": target_url,
            "screenshot": None,
            "history": _initial_history,
            "last_thought": "Đang kết nối trình duyệt...",
            "findings": [],
            "is_complete": False,
            "base_url": None,
            "dom_elements": None,
            "current_page_plan": [],
            "login_user": user_val,
            "login_pass": pass_val,
            "messages": [],
            "task_plan": initial_task_plan,
        }

        selected_mode = "test_web" if is_web_test else "custom"

        # Get model config from sidebar
        _brain_model = st.session_state.get("brain_model") or selected_model
        _eval_model = st.session_state.get("eval_model") or selected_model

        # Define worker function
        def run_in_thread(url, goal, model, u_val, p_val, b_model, e_model, tc_data):
            asyncio.run(
                run_agent_async(
                    url,
                    goal,
                    model,
                    u_val,
                    p_val,
                    brain_model=b_model,
                    eval_model=e_model,
                    test_case_data=tc_data,
                )
            )

        # Create thread and attach context
        thread = threading.Thread(
            target=run_in_thread,
            args=(
                target_url,
                test_goal,
                selected_model,
                user_val,
                pass_val,
                _brain_model,
                _eval_model,
                parsed_test_case,
            ),
        )
        ctx = get_script_run_ctx()
        add_script_run_ctx(thread, ctx)
        thread.start()


if stop_btn:
    st.session_state.running = False
    if "agent_state" in st.session_state:
        st.session_state.agent_state["is_complete"] = True

    # Đóng trình duyệt test trong một thread riêng để tránh block Streamlit
    def _close_browser_sync():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(BrowserManager.close())
            loop.close()
        except Exception as e:
            print(f"⚠️ Lỗi khi đóng trình duyệt: {e}")
            BrowserManager.force_reset()

    close_thread = threading.Thread(target=_close_browser_sync, daemon=True)
    close_thread.start()
    close_thread.join(timeout=5)  # Chờ tối đa 5 giây

    st.rerun()

# --- RENDER CENTER & RIGHT PANELS ---
with col_center:
    # 1. Kịch bản và Kế hoạch Test (Dùng DataFrame biên tập st.data_editor và Tab Tiến trình)
    # Khởi tạo tc_gen_df từ tc_gen_result hoặc test_case_json_str nếu df chưa tồn tại
    if "tc_gen_df" not in st.session_state or st.session_state.tc_gen_df is None:
        import pandas as pd
        if st.session_state.get("tc_gen_result") and st.session_state.tc_gen_result not in ["JSON_IMPORT", "MD_IMPORT"]:
            rows = parse_markdown_table(st.session_state.tc_gen_result)
            if rows:
                st.session_state.tc_gen_df = normalize_df_columns(pd.DataFrame(rows))
        elif st.session_state.get("test_case_json_str"):
            df_json = load_json_to_df(st.session_state.test_case_json_str)
            if df_json is not None:
                st.session_state.tc_gen_df = normalize_df_columns(df_json)

    tc_df = st.session_state.get("tc_gen_df")
    if tc_df is not None and not tc_df.empty:
        # Calculate passed/total
        total_cases = 0
        passed_cases = 0
        if st.session_state.get("test_case_json_str"):
            try:
                import json as _json_parse
                tc_list = _json_parse.loads(st.session_state.test_case_json_str)
                if isinstance(tc_list, list) and tc_list:
                    total_cases = len(tc_list)
                    t_plan = st.session_state.agent_state.get("task_plan", [])
                    for tc in tc_list:
                        tc_id = tc.get("id", "")
                        scenario = tc.get("scenario", "")
                        matching_steps = []
                        if t_plan:
                            for step_item in t_plan:
                                step_text = step_item.get("step", "")
                                if tc_id and f"[{tc_id}]" in step_text:
                                    matching_steps.append(step_item)
                                elif not tc_id and scenario in step_text:
                                    matching_steps.append(step_item)
                        if matching_steps:
                            statuses = [s.get("status", "todo") for s in matching_steps]
                            if all(s == "done" for s in statuses):
                                passed_cases += 1
            except Exception:
                pass

        # Build Accordion HTML
        accordion_html = f"""
        <details class="custom-accordion" open>
            <summary class="accordion-header">
                <div class="accordion-title">
                    <span class="accordion-arrow">▼</span> Test Plan Generated
                </div>
                <div class="accordion-badge">{passed_cases}/{total_cases} passed</div>
            </summary>
            <div class="accordion-content">
        """
        
        try:
            import json as _json_parse
            tc_list = _json_parse.loads(st.session_state.test_case_json_str)
            if isinstance(tc_list, list) and tc_list:
                grouped_tcs = {}
                for tc in tc_list:
                    comp = tc.get("component") or "General"
                    if comp not in grouped_tcs:
                        grouped_tcs[comp] = []
                    grouped_tcs[comp].append(tc)
                
                for comp, cases in grouped_tcs.items():
                    accordion_html += f'<div class="accordion-category">{comp.upper()}</div>'
                    for case in cases:
                        tc_id = case.get("id", "")
                        scenario = case.get("scenario", "")
                        steps = case.get("steps", [])
                        
                        t_plan = st.session_state.agent_state.get("task_plan", [])
                        matching_steps = []
                        if t_plan:
                            for step_item in t_plan:
                                step_text = step_item.get("step", "")
                                if tc_id and f"[{tc_id}]" in step_text:
                                    matching_steps.append(step_item)
                                elif not tc_id and scenario in step_text:
                                    matching_steps.append(step_item)
                        
                        case_status = "todo"
                        if matching_steps:
                            statuses = [s.get("status", "todo") for s in matching_steps]
                            if any(s == "failed" for s in statuses):
                                case_status = "failed"
                            elif any(s == "doing" for s in statuses):
                                case_status = "doing"
                            elif all(s == "done" for s in statuses):
                                case_status = "passed"
                            elif all(s == "skipped" for s in statuses):
                                case_status = "skipped"
                            elif any(s == "done" for s in statuses):
                                case_status = "doing"
                        
                        icon_html = '<span class="item-icon todo">○</span>'
                        if case_status == "passed":
                            icon_html = '<span class="item-icon passed" style="color: #ffffff; line-height: 14px;">✓</span>'
                        elif case_status == "failed":
                            icon_html = '<span class="item-icon failed" style="color: #ffffff; line-height: 14px;">✗</span>'
                        elif case_status == "doing":
                            icon_html = '<span class="item-icon doing" style="color: #ffffff; line-height: 14px;">⟳</span>'
                            
                        desc = ', '.join(steps[:2]) + ('...' if len(steps) > 2 else '')
                        accordion_html += f"""
                        <div class="accordion-item">
                            {icon_html}
                            <div class="item-details">
                                <div class="item-title">{tc_id + " - " if tc_id else ""}{scenario}</div>
                                <div class="item-desc">{desc}</div>
                            </div>
                        </div>
                        """
        except Exception as e:
            accordion_html += f'<div style="padding:16px; color:red;">Error loading test cases: {str(e)}</div>'
            
        accordion_html += "</div></details>"
        st.markdown("\n".join([line.strip() for line in accordion_html.split("\n")]), unsafe_allow_html=True)
        
        # Keep the st.data_editor hidden under an expander for editing functionality
        with st.expander("📝 Chỉnh sửa Test Cases / Data Editor", expanded=False):
            edited_df = st.data_editor(
                st.session_state.tc_gen_df,
                use_container_width=True,
                num_rows="dynamic",
                key="tc_editor_key",
                column_config={
                    "ID": st.column_config.TextColumn("ID", width="small", help="Test Case ID"),
                    "Component": st.column_config.TextColumn("Component", width="medium"),
                    "Test Type": st.column_config.TextColumn("Test Type", width="medium"),
                    "Scenario Type": st.column_config.TextColumn("Scenario Type", width="medium"),
                    "Preconditions": st.column_config.TextColumn("Preconditions", width="medium"),
                    "Steps (with exact JSON payload)": st.column_config.TextColumn("Steps (with exact JSON payload)", width="large"),
                    "Expected Result (HTTP Status + Response Body + DB State)": st.column_config.TextColumn("Expected Result (HTTP Status + Response Body + DB State)", width="large"),
                    "Severity": st.column_config.SelectboxColumn("Severity", options=["Critical", "High", "Medium", "Low"], width="small")
                }
            )
            
            if not edited_df.equals(st.session_state.tc_gen_df):
                st.session_state.tc_gen_df = edited_df
                sync_df_to_test_cases(edited_df)
                st.toast("⚡ Synchronized Test Case changes!", icon="🔄")
            
            col_tc1, col_tc2 = st.columns(2)
            markdown_table = edited_df.to_markdown(index=False)
            col_tc1.download_button(
                label="⬇️ Tải Markdown",
                data=markdown_table,
                file_name="Test_Plan.md",
                mime="text/markdown",
                key="tc_gen_download_btn",
                use_container_width=True,
            )
            if col_tc2.button("🗑️ Xóa Test Plan", key="tc_gen_clear_btn", use_container_width=True):
                st.session_state.pop("tc_gen_result", None)
                st.session_state.pop("tc_gen_parsed_text", None)
                st.session_state.pop("tc_gen_error", None)
                st.session_state.pop("test_case_json_str", None)
                st.session_state.pop("pre_built_task_plan", None)
                st.session_state.pop("tc_gen_df", None)
                st.rerun()
    else:
        st.markdown(f"""
        <div class="empty-state-card">
            <div style="font-size: 32px; margin-bottom: 8px; opacity: 0.3;">📋</div>
            <div style="font-size: 13px; font-weight: 500; color: var(--text-card-name);">Chưa có kế hoạch kiểm thử</div>
            <div style="font-size: 11px; color: var(--text-card-desc); margin-top: 4px;">Tải file kế hoạch hoặc nhập yêu cầu tùy chỉnh ở cột bên trái.</div>
        </div>
        """, unsafe_allow_html=True)

    # 3. Browser Preview Mockup
    url_val = st.session_state.agent_state["url"] or "about:blank"
    lock_icon = "🔒" if url_val.startswith("https") else "🌐"
    
    agent_status = "idle"
    if st.session_state.running:
        agent_status = "running"
    elif st.session_state.agent_state.get("is_complete"):
        if st.session_state.agent_state.get("findings"):
            agent_status = "error"
        else:
            agent_status = "success"
            
    status_dot_class = "status-dot-idle"
    status_text_en = "Sẵn sàng"
    if agent_status == "running":
        status_dot_class = "status-dot-running animate-pulse"
        status_text_en = "Đang chạy kiểm thử..."
    elif agent_status == "success":
        status_dot_class = "status-dot-success"
        status_text_en = "Hoàn tất kiểm thử"
    elif agent_status == "error":
        status_dot_class = "status-dot-error"
        status_text_en = "Phát hiện lỗi/bảo mật"
        
    current_time = time.strftime("%H:%M:%S")

    # Construct the viewport HTML content
    if st.session_state.agent_state["screenshot"]:
        screenshot_b64 = st.session_state.agent_state["screenshot"]
        viewport_html = f"""<div class="browser-viewport-screenshot">
<img src="data:image/png;base64,{screenshot_b64}" />
</div>"""
    else:
        if st.session_state.running:
            viewport_html = """<div class="browser-viewport-empty">
<div class="spinner-container">
<div class="spinner"></div>
</div>
<div style="font-size: 13px; color: var(--text-card-name); font-weight: 500; margin-top: 16px;">Agent đang thực thi kiểm thử...</div>
<div style="font-size: 11px; color: var(--text-card-desc); margin-top: 4px;">Đang phân tích cấu trúc trang và các phần tử DOM</div>
</div>"""
        else:
            viewport_html = """<div class="browser-viewport-empty">
<div style="font-size: 32px; opacity: 0.2; margin-bottom: 12px;">🌐</div>
<div style="font-size: 13px; color: var(--text-card-name); font-weight: 500;">Nhấn "⚡ Chạy Test" để kích hoạt Agent</div>
<div style="font-size: 11px; color: var(--text-card-desc); margin-top: 4px;">Xem trước trình duyệt sẽ hiển thị tại đây</div>
</div>"""

    preview_html = f"""<div class="browser-preview-card">
<div class="browser-chrome">
<div class="browser-traffic-lights">
<span class="light red"></span>
<span class="light yellow"></span>
<span class="light green"></span>
</div>
<div class="browser-nav-buttons">
<span class="nav-btn">◀</span>
<span class="nav-btn">▶</span>
<span class="nav-btn">↻</span>
</div>
<div class="browser-url-bar">
<span style="margin-right: 4px; font-size: 11px;">{lock_icon}</span>
<span class="browser-url-text">{url_val}</span>
</div>
</div>
{viewport_html}
<div class="browser-footer">
<div style="display: flex; align-items: center; gap: 8px;">
<span class="status-dot {status_dot_class}"></span>
<span style="font-size: 11px; color: #9ca3af;">{status_text_en}</span>
</div>
<span style="font-size: 11px; font-family: monospace; color: #9ca3af;">{current_time}</span>
</div>
</div>"""
    st.markdown(preview_html, unsafe_allow_html=True)

    # 4. Report View (bottom of Column 2)
    agent_state = st.session_state.agent_state
    if agent_state.get("is_complete") and not st.session_state.running:
        st.markdown("---")
        st.markdown("## 📄 Báo cáo kiểm tra")
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        base_url = agent_state.get("base_url", "N/A")
        queue = agent_state.get("global_url_queue", [])
        findings = agent_state.get("findings", [])
        history = agent_state.get("history", [])
        did_ui = agent_state.get("test_ui", True)
        did_sec = agent_state.get("test_security", True)

        timeouts = [h for h in history if isinstance(h, str) and "⏱️ TIMEOUT" in h]
        errors = [h for h in history if isinstance(h, str) and "❌" in h]
        closed_tabs = [h for h in history if isinstance(h, str) and "🗑️" in h]

        tested_urls = "\n".join([f"  - ✅ {q['url']}" for q in queue if q["status"] == "tested"])
        scope_text = []
        if did_ui:
            scope_text.append("Kiểm tra UI/UX (Duyệt BFS)")
        if did_sec:
            scope_text.append("Kiểm tra Bảo mật (XSS, SQLi, Path Traversal)")

        report = f"""# 📋 BÁO CÁO KIỂM TRA WEBSITE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 Thời gian: {now}
🌐 URL mục tiêu: {base_url}
🔍 Phạm vi kiểm tra: {", ".join(scope_text)}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## 📊 Tổng quan
- Tổng số trang đã quét: {len(queue)}
- Phát hiện lỗi: {len(findings)}
- Timeout: {len(timeouts)}
- Lỗi tương tác: {len(errors)}
- Tab mới đã đóng: {len(closed_tabs)}

## 🌐 Danh sách URL đã kiểm tra
{tested_urls}

## 🚨 Phát hiện lỗi ({len(findings)})
"""
        if findings:
            for i, f in enumerate(findings, 1):
                if isinstance(f, dict):
                    report += f"\n### {i}. {f['text']}"
                    report += f"\n- **URL**: {f['url']}"
                    report += f"\n- **Thời gian**: {f.get('timestamp', 'N/A')}"
                else:
                    report += f"\n{i}. {f}"
        else:
            report += "\n✅ Không phát hiện lỗi bảo mật hoặc UI nghiêm trọng."

        if timeouts:
            report += f"\n\n## ⏱️ Timeout ({len(timeouts)})"
            for t in timeouts:
                clean_t = t.split("] ", 1)[-1] if "] " in t else t
                report += f"\n- {clean_t}"

        if closed_tabs:
            report += f"\n\n## 🗑️ Tab mới đã đóng ({len(closed_tabs)})"
            for ct in closed_tabs:
                clean_ct = ct.split("] ", 1)[-1] if "] " in ct else ct
                report += f"\n- {clean_ct}"

        action_steps = [h for h in history if isinstance(h, str) and not h.startswith("🤖 AI") and "Screenshot:" not in h]
        if action_steps:
            report += f"\n\n## 👣 Chi tiết các bước thao tác\n"
            for step in action_steps:
                clean_step = step.split("] ", 1)[-1] if "] " in step else step
                clean_step = clean_step.replace("--- Result: ", "").replace("---", "").strip()
                step_vn = translate_text(clean_step)
                if step_vn:
                    report += f"- {step_vn}\n"

        report += f"\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n✍️ Báo cáo tự động bởi 3DArt AI Agent\n⏰ {now}\n"

        with st.expander("👁️ Xem nhanh báo cáo kết quả", expanded=False):
            st.markdown(report)
            if findings:
                st.markdown("---")
                st.markdown("### 📸 Ảnh minh chứng phát hiện lỗi")
                for f in findings:
                    if isinstance(f, dict) and f.get("screenshot") and os.path.exists(f["screenshot"]):
                        st.image(f["screenshot"], caption=f"⚠️ {f['text']} (tại {f['url']})")

        # Download buttons
        safe_base_url = (
            base_url.replace("https://", "").replace("/", "_") if base_url else "agent"
        )
        report_filename = (
            f"report_{safe_base_url}_{datetime.now().strftime('%Y%m%d_%H%M')}"
        )
        col_dl1, col_dl2 = st.columns(2)

        col_dl1.download_button(
            label="⬇️ Tải báo cáo (.txt)",
            data=report,
            file_name=f"{report_filename}.txt",
            mime="text/plain",
            width="stretch",
        )

        # Ưu tiên dùng báo cáo v3 đã được tạo ở khối finally (hoặc graph)
        excel_path = st.session_state.agent_state.get("last_report_path")
        
        # Nếu chưa có, mới tạo fallback bằng hàm cũ
        if not excel_path or not os.path.exists(excel_path):
            from tools.report_tool import generate_excel_report
            safe_domain = (
                base_url.replace("https://", "").replace("http://", "").split("/")[0]
                if base_url
                else "unknown"
            )
            excel_path = generate_excel_report(findings, title=f"TEST {safe_domain}")
        if excel_path and os.path.exists(excel_path):
            with open(excel_path, "rb") as file:
                col_dl2.download_button(
                    label="📊 Tải báo cáo (.xlsx)",
                    data=file,
                    file_name=os.path.basename(excel_path),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary",
                    width="stretch",
                )

        if st.button(
            "🗑️ Xóa ảnh minh chứng & tệp tạm thời", width="stretch"
        ):
            from tools.report_tool import cleanup_reports

            cleanup_reports()
            st.success("Đã xóa toàn bộ dữ liệu tạm thời.")
            st.rerun()

# --- RENDER RIGHT COLUMN ---
with col_right:
    # 1. Execution Plan Panel
    st.markdown('<div class="right-panel-card">', unsafe_allow_html=True)
    st.markdown(
        '<div class="right-panel-header"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--theme-icon-color)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0;"><line x1="8" x2="21" y1="6" y2="6"/><line x1="8" x2="21" y1="12" y2="12"/><line x1="8" x2="21" y1="18" y2="18"/><line x1="3" x2="3.01" y1="6" y2="6"/><line x1="3" x2="3.01" y1="12" y2="12"/><line x1="3" x2="3.01" y1="18" y2="18"/></svg>Kế hoạch thực thi</div>',
        unsafe_allow_html=True,
    )
    # Compute unique scenarios
    scenarios = []
    if st.session_state.get("test_case_json_str"):
        try:
            import json as _json_parse
            tc_list = _json_parse.loads(st.session_state.test_case_json_str)
            if isinstance(tc_list, list):
                for tc in tc_list:
                    scenario = tc.get("scenario")
                    if scenario and scenario not in scenarios:
                        scenarios.append(scenario)
        except Exception:
            pass
    if not scenarios:
        # Fallback to parsing from task_plan
        t_plan = st.session_state.agent_state.get("task_plan", [])
        for item in t_plan:
            step_text = item.get("step", "")
            if step_text.startswith("["):
                parts = step_text.split("]", 2)
                if len(parts) > 1:
                    bracket_content = parts[0][1:].strip()
                    if bracket_content not in scenarios:
                        scenarios.append(bracket_content)

    execution_plan_html = '<div class="execution-plan-list">'
    if scenarios:
        t_plan = st.session_state.agent_state.get("task_plan", [])
        for sc in scenarios:
            matching_steps = []
            for step_item in t_plan:
                step_text = step_item.get("step", "")
                if sc in step_text:
                    matching_steps.append(step_item)
            
            sc_status = "todo"
            if matching_steps:
                statuses = [s.get("status", "todo") for s in matching_steps]
                if any(s == "failed" for s in statuses):
                    sc_status = "failed"
                elif any(s == "doing" for s in statuses):
                    sc_status = "doing"
                elif all(s == "done" for s in statuses):
                    sc_status = "passed"
                elif all(s == "skipped" for s in statuses):
                    sc_status = "skipped"
                elif any(s == "done" for s in statuses):
                    sc_status = "doing"
                    
            status_icon = "○"
            status_class = ""
            if sc_status == "passed":
                status_icon = "🟢"
            elif sc_status == "failed":
                status_icon = "🔴"
            elif sc_status == "doing":
                status_icon = "🟡"
                status_class = "active"
            elif sc_status == "skipped":
                status_icon = "⚪"
                
            execution_plan_html += f"""
            <div class="execution-plan-item {status_class}">
                <span class="status-icon">{status_icon}</span>
                <span>{sc}</span>
            </div>
            """
    else:
        execution_plan_html += '<div style="font-size: 11px; color: #6b7280; text-align: center; padding: 10px 0;">Chưa có test case nào trong hàng đợi</div>'
    execution_plan_html += '</div>'
    st.markdown("\n".join([line.strip() for line in execution_plan_html.split("\n")]), unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # 2. Agent Status Panel
    st.markdown('<div class="right-panel-card">', unsafe_allow_html=True)
    st.markdown(
        '<div class="right-panel-header"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--theme-icon-color)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0;"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>Trạng thái Agent</div>',
        unsafe_allow_html=True,
    )
    dot_class = "idle"
    if st.session_state.running:
        dot_class = "running"
    last_thought = st.session_state.agent_state.get("last_thought", "Sẵn sàng để bắt đầu...")
    if not last_thought or last_thought.strip() == "":
        last_thought = "Sẵn sàng để bắt đầu..."
        
    if last_thought == "Ready to start.." or last_thought == "Sẵn sàng khởi động...":
        last_thought = "Sẵn sàng để bắt đầu..."
        
    st.markdown(f"""
    <div class="agent-status-box">
        <span class="status-dot {dot_class}"></span>
        <span class="status-text">{last_thought}</span>
    </div>
    """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # 3. Error Detection Panel
    st.markdown('<div class="right-panel-card">', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="right-panel-header">
            <span class="panel-icon" style="color: #ef4444;">⚠️</span> Phát hiện lỗi
        </div>
        """,
        unsafe_allow_html=True,
    )
    findings = st.session_state.agent_state.get("findings", [])
    if findings:
        findings_html = '<div class="findings-container">'
        for i, f in enumerate(findings, 1):
            f_text = f.get("text", str(f)) if isinstance(f, dict) else str(f)
            findings_html += f"""
            <div class="finding-alert-item">
                <strong>Lỗi #{i}</strong><br/>
                {f_text}
            </div>
            """
        findings_html += '</div>'
        st.markdown(findings_html, unsafe_allow_html=True)
    else:
        st.markdown('<div class="error-detection-empty">Chưa phát hiện lỗi nào</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # 4. Action Logs Panel
    st.markdown('<div class="right-panel-card">', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="right-panel-header">
            <span class="panel-icon" style="color: #3b82f6;">&gt;_</span> Nhật ký hành động
        </div>
        """,
        unsafe_allow_html=True,
    )
    history = st.session_state.agent_state.get("history", [])
    terminal_html = '<div class="terminal-container">'
    if history:
        for h in history:
            line = str(h)
            line_class = "default"
            if "[VISION]" in line:
                line_class = "vision"
            elif "[ACTION]" in line:
                line_class = "action"
            elif "[MANAGER]" in line:
                line_class = "manager"
                
            terminal_html += f'<div class="terminal-row {line_class}">{line}</div>'
    else:
        terminal_html += '<div class="terminal-row empty">Chưa có hành động nào được ghi lại</div>'
    terminal_html += '</div>'
    st.markdown(terminal_html, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# Tự động làm mới
if st.session_state.running:
    time.sleep(2.0)  # Tăng lên 2s để ổn định hơn
    st.rerun()
