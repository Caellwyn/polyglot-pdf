"""
VAD Configuration WebSocket Endpoint

Allows real-time VAD configuration updates from the tuning lab UI.
Updates are written to a config file that the live_ai_gemini adapter reads.
"""

from fastapi import WebSocket, WebSocketDisconnect
import json
import structlog
from pathlib import Path

log = structlog.get_logger()

# Path to VAD config file
VAD_CONFIG_PATH = Path(__file__).parent.parent / "vad_config.json"

def get_vad_config():
    """Load current VAD configuration"""
    if VAD_CONFIG_PATH.exists():
        try:
            with open(VAD_CONFIG_PATH, 'r') as f:
                return json.load(f)
        except Exception as e:
            log.error("failed_to_load_vad_config", error=str(e))
    
    # Default configuration
    return {
        "startSensitivity": "UNSPECIFIED",
        "endSensitivity": "UNSPECIFIED",
        "prefixPadding": 120,
        "silenceDuration": 250
    }

def save_vad_config(config):
    """Save VAD configuration to file"""
    try:
        with open(VAD_CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=2)
        log.info("vad_config_saved", config=config)
        return True
    except Exception as e:
        log.error("failed_to_save_vad_config", error=str(e))
        return False

async def vad_config_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for VAD configuration updates.
    
    Receives messages from tuning lab UI and updates VAD config file.
    Backend auto-reloads (--reload flag) pick up the changes.
    """
    await websocket.accept()
    log.info("vad_config_websocket_connected")
    
    try:
        # Send current config on connect
        current_config = get_vad_config()
        await websocket.send_json({
            "type": "current_config",
            "config": current_config
        })
        
        while True:
            # Receive config updates
            message = await websocket.receive_json()
            
            if message.get("type") == "update_vad_config":
                config = message.get("config", {})
                
                log.info("vad_config_update_received", config=config)
                
                # Save configuration
                if save_vad_config(config):
                    await websocket.send_json({
                        "type": "update_success",
                        "message": "VAD configuration updated successfully"
                    })
                else:
                    await websocket.send_json({
                        "type": "update_error",
                        "message": "Failed to save VAD configuration"
                    })
                    
    except WebSocketDisconnect:
        log.info("vad_config_websocket_disconnected")
    except Exception as e:
        log.error("vad_config_websocket_error", error=str(e))
