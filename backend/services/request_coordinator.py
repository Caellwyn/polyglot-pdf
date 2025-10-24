"""
Request coordinator for async frontend communication.

Handles the async request/response pattern for stateless client-server
communication. Backend sends requests to frontend and awaits responses
via WebSocket with timeout handling.
"""
import asyncio
import uuid
from typing import Any, Dict, List, Optional
from fastapi import WebSocket
import structlog

_log = structlog.get_logger().bind(module="request_coordinator")


class RequestCoordinator:
    """Coordinates async request/response cycles with the frontend."""
    
    def __init__(self, websocket: Optional[WebSocket] = None, session_id: Optional[str] = None):
        """
        Initialize request coordinator.
        
        Args:
            websocket: WebSocket connection to frontend
            session_id: Optional session ID for logging context
        """
        self._websocket = websocket
        self._session_id = session_id
        
        # Pending request tracking
        self._pending_form_state_request: Optional[Dict[str, Any]] = None
        self._pending_next_field_request: Optional[Dict[str, Any]] = None
        self._pending_field_value_request: Optional[Dict[str, Any]] = None
        self._pending_section_switch: Optional[Dict[str, Any]] = None
    
    def set_websocket(self, websocket: WebSocket) -> None:
        """Update WebSocket connection."""
        self._websocket = websocket
    
    # Request methods
    
    async def request_form_state(self, field_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Request current form state from the frontend client.
        
        This implements the async request/response pattern for stateless architecture.
        Backend sends a request to frontend and waits for response.
        
        Args:
            field_ids: Specific field IDs to request, or None/empty for all fields
            
        Returns:
            Dictionary of field_id -> value from the client
        """
        if not self._websocket:
            _log.warning("request_form_state_no_websocket", session_id=self._session_id)
            return {}
        
        # Generate request ID for matching response
        request_id = str(uuid.uuid4())
        
        # Create future to await response
        future = asyncio.Future()
        self._pending_form_state_request = {
            "request_id": request_id,
            "future": future,
        }
        
        # Send request to frontend
        try:
            await self._websocket.send_json({
                "type": "get_form_state",
                "request_id": request_id,
                "field_ids": field_ids or [],
            })
        except Exception as exc:
            _log.error("failed_to_send_form_state_request", session_id=self._session_id, error=str(exc))
            self._pending_form_state_request = None
            return {}
        
        # Wait for response with timeout
        try:
            result = await asyncio.wait_for(future, timeout=5.0)
            return result
        except asyncio.TimeoutError:
            _log.error("form_state_request_timeout", session_id=self._session_id, request_id=request_id)
            self._pending_form_state_request = None
            return {}
        except Exception as exc:
            _log.error("form_state_request_error", session_id=self._session_id, error=str(exc))
            self._pending_form_state_request = None
            return {}
    
    async def request_next_field_hint(self) -> Optional[str]:
        """
        Request next field hint from the frontend client.
        
        This implements the async request/response pattern for getting navigation hints.
        The frontend computes the next unfilled field and formats a hint for Gemini.
        
        Returns:
            Formatted hint string (e.g., "Next field to fill is #3: 'email' (type: text, required)")
            or None if request fails or no unfilled fields remain
        """
        if not self._websocket:
            _log.warning("request_next_field_hint_no_websocket", session_id=self._session_id)
            return None
        
        # Generate request ID for matching response
        request_id = str(uuid.uuid4())
        
        # Create future to await response
        future = asyncio.Future()
        self._pending_next_field_request = {
            "request_id": request_id,
            "future": future,
        }
        
        # Send request to frontend
        try:
            await self._websocket.send_json({
                "type": "get_next_field_hint",
                "request_id": request_id,
            })
        except Exception as exc:
            _log.error("failed_to_send_next_field_request", session_id=self._session_id, error=str(exc))
            self._pending_next_field_request = None
            return None
        
        # Wait for response with timeout
        try:
            result = await asyncio.wait_for(future, timeout=2.0)
            return result
        except asyncio.TimeoutError:
            _log.error("next_field_request_timeout", session_id=self._session_id, request_id=request_id)
            self._pending_next_field_request = None
            return None
        except Exception as exc:
            _log.error("next_field_request_error", session_id=self._session_id, error=str(exc))
            self._pending_next_field_request = None
            return None
    
    async def request_field_value(self, spoken_name: str) -> Dict[str, Any]:
        """
        Request field value from frontend using spoken name.
        
        Frontend will lookup in spokenNameToFieldId map and return value.
        
        Args:
            spoken_name: The spoken name of the field (e.g., 'phone number')
            
        Returns:
            Dictionary with 'value' and 'found' keys
        """
        if not self._websocket:
            _log.warning("get_field_value_no_websocket", session_id=self._session_id)
            return {"found": False, "value": None}
        
        # Generate request ID for matching response
        request_id = str(uuid.uuid4())
        
        # Create future to await response
        future = asyncio.Future()
        self._pending_field_value_request = {
            "request_id": request_id,
            "future": future,
            "spoken_name": spoken_name,  # Store for error messages
        }
        
        # Send request to frontend
        try:
            await self._websocket.send_json({
                "type": "get_field_value",
                "request_id": request_id,
                "spoken_name": spoken_name,
            })
        except Exception as exc:
            _log.error("failed_to_send_get_field_value", 
                      session_id=self._session_id,
                      spoken_name=spoken_name,
                      error=str(exc))
            self._pending_field_value_request = None
            return {"found": False, "value": None}
        
        # Wait for response with timeout
        try:
            result = await asyncio.wait_for(future, timeout=2.0)
            return result
        except asyncio.TimeoutError:
            _log.error("get_field_value_timeout", 
                      session_id=self._session_id,
                      spoken_name=spoken_name,
                      request_id=request_id)
            self._pending_field_value_request = None
            return {"found": False, "value": None}
        except Exception as exc:
            _log.error("get_field_value_error", 
                      session_id=self._session_id,
                      spoken_name=spoken_name,
                      error=str(exc))
            self._pending_field_value_request = None
            return {"found": False, "value": None}
    
    async def request_section_info(self, section_identifier: str) -> Optional[Dict[str, Any]]:
        """
        Request section information from frontend.
        
        Used during section switching to get new section schema and metadata.
        
        Args:
            section_identifier: Section number ('3'), ID, or label
            
        Returns:
            Dictionary with schema, current_values, metadata, initial_field_hint
            or None if request fails
        """
        if not self._websocket:
            _log.warning("request_section_info_no_websocket", session_id=self._session_id)
            return None
        
        # Generate request ID for matching response
        request_id = str(uuid.uuid4())
        
        # Create future to await response
        future = asyncio.Future()
        self._pending_section_switch = {
            "request_id": request_id,
            "future": future,
        }
        
        # Send request to frontend
        try:
            await self._websocket.send_json({
                "type": "prepare_section_switch",
                "request_id": request_id,
                "identifier": section_identifier,
            })
        except Exception as exc:
            _log.error("failed_to_send_section_info_request",
                      session_id=self._session_id,
                      error=str(exc))
            self._pending_section_switch = None
            return None
        
        # Wait for response with timeout
        try:
            result = await asyncio.wait_for(future, timeout=5.0)
            return result
        except asyncio.TimeoutError:
            _log.error("section_info_request_timeout",
                      session_id=self._session_id,
                      request_id=request_id)
            self._pending_section_switch = None
            return None
        except Exception as exc:
            _log.error("section_info_request_error",
                      session_id=self._session_id,
                      error=str(exc))
            self._pending_section_switch = None
            return None
    
    # Response handlers
    
    def handle_form_state_response(self, request_id: str, field_values: Dict[str, Any]) -> None:
        """
        Handle form_state_response message from frontend.
        
        This completes the async request/response cycle by resolving the pending future.
        
        Args:
            request_id: ID matching the original request
            field_values: Dictionary of field_id -> value from client
        """
        if not self._pending_form_state_request:
            _log.warning("unexpected_form_state_response", session_id=self._session_id, request_id=request_id)
            return
        
        if self._pending_form_state_request.get("request_id") != request_id:
            _log.warning("mismatched_form_state_response", 
                        session_id=self._session_id,
                        expected=self._pending_form_state_request.get("request_id"),
                        received=request_id)
            return
        
        # Resolve the future with the field values
        future = self._pending_form_state_request.get("future")
        if future and not future.done():
            future.set_result(field_values)
        
        self._pending_form_state_request = None
    
    def handle_next_field_hint_response(self, request_id: str, hint: Optional[str]) -> None:
        """
        Handle next_field_hint_response message from frontend.
        
        This completes the async request/response cycle by resolving the pending future.
        
        Args:
            request_id: ID matching the original request
            hint: Formatted hint string or None if form is complete
        """
        if not self._pending_next_field_request:
            _log.warning("unexpected_next_field_response", session_id=self._session_id, request_id=request_id)
            return
        
        if self._pending_next_field_request.get("request_id") != request_id:
            _log.warning("mismatched_next_field_response", 
                        session_id=self._session_id,
                        expected=self._pending_next_field_request.get("request_id"),
                        received=request_id)
            return
        
        # Resolve the future with the hint
        future = self._pending_next_field_request.get("future")
        if future and not future.done():
            future.set_result(hint)
        
        self._pending_next_field_request = None
    
    def handle_field_value_response(self, request_id: str, value: Any, found: bool) -> None:
        """
        Handle field_value_response message from frontend.
        
        Completes the async request/response cycle for get_field_value.
        
        Args:
            request_id: ID matching the original request
            value: The field value from client
            found: Whether the field was found
        """
        if not self._pending_field_value_request:
            _log.warning("unexpected_field_value_response", 
                        session_id=self._session_id,
                        request_id=request_id)
            return
        
        if self._pending_field_value_request.get("request_id") != request_id:
            _log.warning("mismatched_field_value_response", 
                        session_id=self._session_id,
                        expected=self._pending_field_value_request.get("request_id"),
                        received=request_id)
            return
        
        # Resolve the future with the response
        future = self._pending_field_value_request.get("future")
        if future and not future.done():
            future.set_result({"value": value, "found": found})
        
        self._pending_field_value_request = None
    
    def handle_section_info_response(self, request_id: str, section_info: Dict[str, Any]) -> None:
        """
        Handle section_info_response message from frontend.
        
        Completes the async request/response cycle for section switching.
        
        Args:
            request_id: ID matching the original request
            section_info: Dictionary with schema, current_values, metadata, initial_field_hint
        """
        if not self._pending_section_switch:
            _log.warning("unexpected_section_info_response", 
                        session_id=self._session_id,
                        request_id=request_id)
            return
        
        if self._pending_section_switch.get("request_id") != request_id:
            _log.warning("mismatched_section_info_response", 
                        session_id=self._session_id,
                        expected=self._pending_section_switch.get("request_id"),
                        received=request_id)
            return
        
        # Resolve the future with the section info
        future = self._pending_section_switch.get("future")
        if future and not future.done():
            future.set_result(section_info)
        
        self._pending_section_switch = None
