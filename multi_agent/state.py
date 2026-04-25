"""
state.py - Định nghĩa "Bộ nhớ dùng chung" cho luồng tuyến tính
"""

import operator
from typing import TypedDict, Optional, Any, Annotated, List, Dict

def merge_dicts(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    if not left: left = {}
    if not right: right = {}
    merged = left.copy()
    merged.update(right)
    return merged

def merge_unique_lists(left: List[str], right: List[str]) -> List[str]:
    if not left: left = []
    if not right: right = []
    return list(dict.fromkeys(left + right))

class AgentState(TypedDict):
    target_url: str
    current_url: Optional[str] # URL đang được xử lý trong lượt này
    pending_urls: Annotated[List[str], merge_unique_lists]
    tested_urls: Annotated[List[str], merge_unique_lists]
    
    results_map: Annotated[Dict[str, Any], merge_dicts]
    security_memories: Annotated[Dict[str, List[str]], merge_dicts]

    final_report: Optional[str]
    history: Annotated[List[str], operator.add]
    
    iteration: int
    discovery_done: Optional[bool]
    next_agent: Optional[str]
