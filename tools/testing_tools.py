"""
Testing Tools — Report Issue, Finish Task, Wait.

All tools auto-register via @register_tool decorator.
"""
import asyncio
import logging
from tools.tool_registry import register_tool

logger = logging.getLogger(__name__)


# ============================================================
# TOOL: report_issue
# ============================================================
@register_tool(
    name="report_issue",
    description="Report a security vulnerability, UI bug, or functional issue discovered.",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "A short, descriptive title of the issue."},
            "description": {"type": "string", "description": "Detailed description and steps to reproduce."},
            "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"], "description": "The severity level."}
        },
        "required": ["title", "description", "severity"]
    }
)
async def report_issue(title: str, description: str, severity: str, **ctx) -> str:
    """Report a bug or security issue."""
    logger.info(f"🚨 ISSUE: [{severity.upper()}] {title}")
    return f"✅ Recorded issue [{severity}]: {title}"


# ============================================================
# TOOL: finish_task
# ============================================================
@register_tool(
    name="finish_task",
    description="Finish the task when the goal is achieved or exploration is complete.",
    parameters={
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "Summary of results and testing done."}
        },
        "required": ["summary"]
    }
)
async def finish_task(summary: str, **ctx) -> str:
    """Mark the task as complete."""
    logger.info(f"🏁 TASK COMPLETE: {summary}")
    return f"TASK_COMPLETE: {summary}"


# ============================================================
# TOOL: wait
# ============================================================
@register_tool(
    name="wait",
    description="Wait for a specified duration (seconds) for the page to load or animations to finish.",
    parameters={
        "type": "object",
        "properties": {
            "seconds": {"type": "number", "description": "Seconds to wait (1-10)."}
        },
        "required": ["seconds"]
    }
)
async def wait(seconds: float, **ctx) -> str:
    """Wait for a specified number of seconds."""
    seconds = min(max(seconds, 0.5), 10)  # Clamp 0.5–10s
    await asyncio.sleep(seconds)
    return f"✅ Waited for {seconds} seconds."
