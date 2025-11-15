"""
Half-Cascade Tool Executor - Phase 3B

Executes tool calls from Flash-Lite responses in the half-cascade architecture.
Integrates with existing form filling tools while maintaining stateless backend design.

Supported Tools:
- update_form_fields: Update form field values
- get_form_status: Retrieve current form state
- switch_section: Navigate to different section
- get_field_value: Look up specific field value
- complete_section: Mark section/part complete
"""

from typing import Dict, Any, Optional, Callable
import structlog

_log = structlog.get_logger().bind(module="half_cascade_tool_executor")


class ToolExecutionError(Exception):
    """Raised when tool execution fails."""
    pass


class HalfCascadeToolExecutor:
    """
    Tool executor for half-cascade pipeline.

    Executes tools in response to Flash-Lite tool calls.
    Delegates to injected tool handlers for actual execution.
    """

    def __init__(
        self,
        websocket,
        session_id: Optional[str] = None
    ):
        """
        Initialize tool executor.

        Args:
            websocket: WebSocket connection for sending updates
            session_id: Session ID for logging
        """
        self._websocket = websocket
        self._session_id = session_id

        # Tool handlers (injected)
        self._tool_handlers: Dict[str, Callable] = {}

        _log.info(
            "tool_executor_initialized",
            session_id=session_id
        )

    def register_tool(self, tool_name: str, handler: Callable) -> None:
        """
        Register a tool handler.

        Args:
            tool_name: Name of the tool
            handler: Async function to execute the tool
        """
        self._tool_handlers[tool_name] = handler
        _log.info(
            "tool_registered",
            tool=tool_name,
            session_id=self._session_id
        )

    async def execute(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool call.

        Args:
            tool_name: Name of the tool to execute
            tool_args: Arguments for the tool

        Returns:
            Dict with execution result:
            {
                "success": bool,
                "result": Any,
                "error": Optional[str]
            }

        Raises:
            ToolExecutionError: If tool execution fails critically
        """
        log = _log.bind(
            session_id=self._session_id,
            tool=tool_name
        )

        if tool_name not in self._tool_handlers:
            log.warning("tool_not_registered", available_tools=list(self._tool_handlers.keys()))
            return {
                "success": False,
                "error": f"Tool '{tool_name}' not registered"
            }

        try:
            log.info("executing_tool", args=tool_args)

            # Get handler
            handler = self._tool_handlers[tool_name]

            # Execute tool
            result = await handler(tool_args)

            log.info("tool_executed_successfully", result_type=type(result).__name__)

            return {
                "success": True,
                "result": result
            }

        except Exception as e:
            log.error(
                "tool_execution_failed",
                error=str(e),
                exc_info=True
            )
            return {
                "success": False,
                "error": str(e)
            }


# ============================================================================
# Tool Handler Implementations for Half-Cascade
# ============================================================================

async def create_update_fields_handler(websocket):
    """
    Create handler for update_form_fields tool.

    In half-cascade mode, form updates are sent to frontend which holds state.
    Backend is stateless.

    Args:
        websocket: WebSocket connection to send updates

    Returns:
        Async handler function
    """
    async def handle_update_fields(args: Dict[str, Any]) -> Dict[str, Any]:
        """Handle update_form_fields tool call."""
        field_id = args.get("field_id")
        value = args.get("value")

        if not field_id:
            raise ValueError("field_id is required")

        # Send update to frontend
        await websocket.send_json({
            "type": "form_updated",
            "data": {
                "form_state": {field_id: value},
                "applied_fields": [field_id]
            }
        })

        return {"updated": field_id, "value": value}

    return handle_update_fields


async def create_get_form_status_handler(websocket, request_coordinator):
    """
    Create handler for get_form_status tool.

    Requests current form state from frontend via request/response pattern.

    Args:
        websocket: WebSocket connection
        request_coordinator: Coordinator for async requests

    Returns:
        Async handler function
    """
    async def handle_get_form_status(args: Dict[str, Any]) -> Dict[str, Any]:
        """Handle get_form_status tool call."""
        # Request form state from frontend
        form_state = await request_coordinator.request_form_state()

        return {"form_state": form_state}

    return handle_get_form_status


async def create_get_field_value_handler(websocket, request_coordinator):
    """
    Create handler for get_field_value tool.

    Looks up specific field value from frontend.

    Args:
        websocket: WebSocket connection
        request_coordinator: Coordinator for async requests

    Returns:
        Async handler function
    """
    async def handle_get_field_value(args: Dict[str, Any]) -> Dict[str, Any]:
        """Handle get_field_value tool call."""
        field_id = args.get("field_id")

        if not field_id:
            raise ValueError("field_id is required")

        # Request field value from frontend
        value, found = await request_coordinator.request_field_value(field_id)

        return {
            "field_id": field_id,
            "value": value,
            "found": found
        }

    return handle_get_field_value


async def create_switch_section_handler(websocket, form_filling_service):
    """
    Create handler for switch_section tool.

    Switches to a different form section/part.

    Args:
        websocket: WebSocket connection
        form_filling_service: Form filling service for section switching

    Returns:
        Async handler function
    """
    async def handle_switch_section(args: Dict[str, Any]) -> Dict[str, Any]:
        """Handle switch_section tool call."""
        section_identifier = args.get("section_identifier")

        if not section_identifier:
            raise ValueError("section_identifier is required")

        # Delegate to form filling service
        result = await form_filling_service.handle_switch_section(section_identifier)

        return result

    return handle_switch_section


async def create_complete_section_handler(websocket):
    """
    Create handler for complete_section tool.

    Marks current section as complete.

    Args:
        websocket: WebSocket connection

    Returns:
        Async handler function
    """
    async def handle_complete_section(args: Dict[str, Any]) -> Dict[str, Any]:
        """Handle complete_section tool call."""
        # Notify frontend to mark section complete
        await websocket.send_json({
            "type": "complete_section",
            "data": args
        })

        return {"success": True}

    return handle_complete_section
