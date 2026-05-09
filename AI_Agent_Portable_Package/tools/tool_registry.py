"""
Tool Registry — Auto-registration system for Agent tools.

Usage:
    @register_tool(
        name="click_element",
        description="Click vào phần tử web theo SOM ID",
        parameters={...}
    )
    async def click_element(element_id: int, **ctx):
        ...

    # In action_node:
    handler = get_handler("click_element")
    result = await handler(element_id=5, plan=plan, page=page)
"""

# Global registries
_TOOL_DEFINITIONS = []   # List of tool schemas (sent to AI)
_TOOL_HANDLERS = {}       # Dict of tool_name -> async function


def register_tool(name: str, description: str, parameters: dict):
    """Decorator to register a tool with its schema and handler."""
    def decorator(func):
        # Register the schema
        _TOOL_DEFINITIONS.append({
            "name": name,
            "description": description,
            "parameters": parameters,
        })
        # Register the handler
        _TOOL_HANDLERS[name] = func
        return func
    return decorator


def get_all_tool_definitions() -> list:
    """Returns all tool schemas for sending to the AI model."""
    return _TOOL_DEFINITIONS.copy()


def get_handler(tool_name: str):
    """Returns the async handler function for a tool, or None if not found."""
    return _TOOL_HANDLERS.get(tool_name)


def get_all_handlers() -> dict:
    """Returns all registered handlers."""
    return _TOOL_HANDLERS.copy()


def import_all_tools():
    """Import all tool modules to trigger registration.
    Call this once at startup."""
    import tools.web_tools       # noqa: F401
    import tools.navigation_tools  # noqa: F401
    import tools.data_tools      # noqa: F401
    import tools.testing_tools   # noqa: F401
