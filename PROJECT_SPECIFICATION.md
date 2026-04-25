# Project Specification: Multi-Agent Automated Web Testing System

## 1. Overview
This project is a robust, stateful multi-agent system designed for automated web testing. It uses **LangGraph** to coordinate between a **Researcher Agent** (which performs the actual browser testing) and a **QA Agent** (which validates the results and decides whether to pass, fail, or retry).

## 2. Core Architecture
The system follows a **Researcher-QA Loop** pattern:
- **Researcher Node:** Uses the `browser-use` library to control a Chromium browser. It performs tasks like navigating to URLs, clicking buttons, and checking for UI errors.
- **QA Node:** Analyzes the output from the Researcher. It issues a `PASS` if the task is complete or a `FAIL` with a reason if it's not.
- **Retry Logic:** If QA issues a `FAIL`, the system automatically routes back to the Researcher for up to 3 attempts, maintaining a shared state.

## 3. Technology Stack
- **Language:** Python 3.14 (Environment: macOS)
- **Orchestration:** LangGraph (StateGraph)
- **Agent Framework:** browser-use (v0.11.13)
- **LLM Integration:** LangChain / LangChain-Ollama
- **Model:** Qwen 2.5 (Running locally via Ollama)
- **Browser:** Playwright (Chromium)

## 4. Key Technical Implementation Details

### A. The "BrowserUseLLM" Wrapper (Composition Pattern)
To ensure compatibility between local models (Ollama) and the `browser-use` library, we implemented a wrapper class.
- **Purpose:** `browser-use` strictly requires an LLM object with a `.provider` attribute to determine which parser to use.
- **The Hack:** We wrap `ChatOllama` in a custom class and set `self.provider = "openai"`. This tricks `browser-use` into using its most stable OpenAI-based JSON/Tool-calling parser, which works perfectly with Qwen 2.5's high compliance.
- **Delegation:** Uses `__getattr__` to pass all other calls (like `ainvoke`, `invoke`) directly to the underlying `ChatOllama` instance.

### B. State Management (`AgentState`)
Defined in `multi_agent/state.py`, the state tracks:
- `task`: The original testing objective.
- `agent_outcome`: The raw output from the Researcher.
- `qa_verdict`: The pass/fail status.
- `history`: A log of actions across loops.
- `iteration`: A counter to prevent infinite loops.

### C. Graph Orchestration
Defined in `multi_agent/graph.py`:
- Uses `StateGraph(AgentState)`.
- Defines conditional edges based on the `qa_verdict`.
- Entry point: `researcher_node`.

## 5. File Structure
- `multi_agent_main.py`: Entry point.
- `multi_agent/state.py`: TypedDict state definition.
- `multi_agent/agents.py`: Node logic and LLM initialization.
- `multi_agent/graph.py`: Workflow definition.
- `tools/`: Custom Python tools for Excel/Word reporting (integrated via `Controller`).

## 6. Current Technical Status
- **LLM Migration:** Successfully migrated from Cloud APIs (Gemini/Groq) to **Local Ollama (Qwen 2.5)** to resolve 429 Quota errors and improve JSON schema compliance.
- **Pydantic Compatibility:** Bypassed strict Pydantic V2 validation issues in Python 3.14 by avoiding class inheritance for LLM wrappers and using composition instead.

---
*Generated for AI Analysis and Debugging purposes.*
