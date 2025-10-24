"""
Script to refactor form_filling_service.py to use CallbackHandler.
Replaces nested callback functions (lines 129-540) with CallbackHandler delegation.
"""

import sys
from pathlib import Path

# Get the file path
file_path = Path(__file__).parent.parent / "backend" / "services" / "form_filling_service.py"

# Read the file
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Lines to keep before callbacks (0-128, which is lines[0:128])
before_callbacks = lines[:128]

# Lines to keep after callbacks (540+, which is lines[540:])
after_callbacks = lines[540:]

# New callback initialization code
new_code = '''
        if accept_connection:
            await self._websocket.accept()
        
        # Initialize callback handler
        self._callback_handler = CallbackHandler(
            websocket=websocket,
            session_id=session_id,
            request_coordinator=self._request_coordinator,
            send_transcript=send_transcript,
        )
        
        # Inject tool handler methods into callback handler
        self._callback_handler.set_tool_handlers(
            handle_update_fields=self.handle_update_fields_tool_call,
            handle_switch_section=self.handle_switch_section,
            handle_get_field_value=self.handle_get_field_value,
            handle_complete_section=self.handle_complete_section,
            request_form_state_from_client=self.request_form_state_from_client,
        )
        
        # Use web form tool declarations (stateless)
        tool_declarations = deepcopy(self._settings.TOOL_DECLARATIONS)

        if self._live_ai is not None:
            # Register callbacks with Gemini Live AI
            # System instruction is passed from caller and included in the initial
            # Gemini connection config.
            try:
                self._live_ai.set_callbacks(
                    on_form_update=self._callback_handler.on_form_update,
                    on_transcript=self._callback_handler.on_transcript,
                    on_audio=self._callback_handler.on_audio,
                    on_tool_call=self._callback_handler.on_tool_call,
                    system_instruction=system_instruction,
                    tool_declarations=tool_declarations,
                    enable_transcripts=bool(send_transcript),
                )
            except TypeError:
                # Adapter does not accept on_audio (older implementations); fall
                # back to previous behavior.
                try:
                    self._live_ai.set_callbacks(
                        on_form_update=self._callback_handler.on_form_update,
                        on_transcript=self._callback_handler.on_transcript,
                        on_tool_call=self._callback_handler.on_tool_call,
                        system_instruction=system_instruction,
                        tool_declarations=tool_declarations,
                    )
                except TypeError:
                    # If this also fails, give up silently — the adapter
                    # truly doesn't implement callback registration.
                    pass

'''

# Combine
new_lines = before_callbacks + [new_code] + after_callbacks

# Write back
with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"✅ Refactored {file_path}")
print(f"   Removed lines 129-540 (412 lines of nested callbacks)")
print(f"   Inserted callback handler initialization (58 lines)")
print(f"   Net reduction: ~354 lines")
