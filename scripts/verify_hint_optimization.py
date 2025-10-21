#!/usr/bin/env python3
"""
Manual verification script for next_field_hint optimization.

This script helps verify the optimization by:
1. Checking that backend code has the optimization
2. Checking that frontend code has the optimization
3. Providing instructions for manual testing

Run this script to verify the implementation is complete.
"""

import sys
import os
from pathlib import Path

def check_file_contains(filepath: Path, patterns: list[str]) -> bool:
    """Check if file contains all patterns."""
    if not filepath.exists():
        print(f"❌ File not found: {filepath}")
        return False
    
    content = filepath.read_text(encoding='utf-8')
    missing = []
    for pattern in patterns:
        if pattern not in content:
            missing.append(pattern)
    
    if missing:
        print(f"❌ {filepath.name} missing patterns:")
        for p in missing:
            print(f"   - {p}")
        return False
    
    return True


def main():
    print("=" * 70)
    print("Next Field Hint Optimization - Verification")
    print("=" * 70)
    print()
    
    # Get project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    backend_service = project_root / "backend" / "services" / "form_filling_service.py"
    frontend_connection = project_root / "frontend" / "src" / "webFormConnection.ts"
    backend_routes = project_root / "backend" / "routes" / "websocket_routes.py"
    
    print("📋 Checking Backend Implementation...")
    print("-" * 70)
    
    backend_patterns = [
        'request_next_field_hint',
        'request_id',
        'asyncio.Future()',
        'await asyncio.wait_for(future, timeout=2.0)',
        'handle_next_field_hint_response',
    ]
    
    backend_ok = check_file_contains(backend_service, backend_patterns)
    if backend_ok:
        print(f"✅ {backend_service.name} - All patterns found")
    
    print()
    print("📋 Checking Frontend Implementation...")
    print("-" * 70)
    
    frontend_patterns = [
        'requestNextFieldHint',
        'computeNextFieldHintString()',
        'next_field_hint_response',
        'type: "next_field_hint_response"',
    ]
    
    frontend_ok = check_file_contains(frontend_connection, frontend_patterns)
    if frontend_ok:
        print(f"✅ {frontend_connection.name} - All patterns found")
    
    print()
    print("📋 Checking WebSocket Routes...")
    print("-" * 70)
    
    routes_patterns = [
        'next_field_hint_response',
        'service.handle_next_field_hint_response',
    ]
    
    routes_ok = check_file_contains(backend_routes, routes_patterns)
    if routes_ok:
        print(f"✅ {backend_routes.name} - All patterns found")
    
    print()
    print("=" * 70)
    
    if backend_ok and frontend_ok and routes_ok:
        print("✅ ALL CHECKS PASSED - Implementation is complete!")
        print()
        print("🧪 Manual Testing Instructions:")
        print("-" * 70)
        print("1. Start backend: scripts/start_backend.sh")
        print("2. Start frontend: cd frontend && npm run dev")
        print("3. Open: demos/adult_intake_demo.html")
        print("4. Open browser DevTools (F12) → Console tab")
        print("5. Fill one field manually (e.g., firstName)")
        print("6. Connect to voice session")
        print("7. Watch console for these messages:")
        print()
        print("   Expected Backend Log:")
        print("   - 'form_update_sent_with_hint_request'")
        print("   - 'next_field_hint_received' (after frontend responds)")
        print()
        print("   Expected Frontend Log:")
        print("   - '[WebFormConnection] 🔍 handleFormUpdated details:'")
        print("   - '  requestNextFieldHint: true'")
        print("   - '[WebFormConnection] 💡 Sending next_field_hint_response:'")
        print()
        print("8. Say something to fill a field")
        print("9. Verify tool response includes hint about next field")
        print()
        print("💡 Key Verification Points:")
        print("   - Only ONE 'form_updated' message per field update")
        print("   - 'next_field_hint_response' sent immediately after")
        print("   - Tool response includes next field hint in message")
        print("   - No separate 'get_next_field_hint' requests during filling")
        print()
        print("📊 Token Efficiency Check:")
        print("   - Count model turns during session")
        print("   - Should be ~1 per field update (not 2)")
        print("   - Initial message includes first hint")
        print("   - Each tool response includes next hint")
        return 0
    else:
        print("❌ CHECKS FAILED - Please review implementation")
        return 1


if __name__ == "__main__":
    sys.exit(main())
