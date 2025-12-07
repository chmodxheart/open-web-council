"""
Reset MODELS_TO_QUERY valve to default value

This script resets the MODELS_TO_QUERY valve in the Council orchestrator
back to its code default, overriding any cached database values.
"""

import requests
import os
import subprocess
from typing import Optional

# Configuration
def get_credential(env_var: str, command_var: str, default: str = "") -> str:
    """
    Get credential from environment variable or command.

    Priority:
    1. Direct environment variable (e.g., OPENWEBUI_URL)
    2. Command from environment variable (e.g., OPENWEBUI_URL_COMMAND)
    3. Default value
    """
    value = os.getenv(env_var)
    if value:
        return value

    command = os.getenv(command_var)
    if command:
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            pass

    return default

OPENWEBUI_URL = get_credential("OPENWEBUI_URL", "OPENWEBUI_URL_COMMAND", "https://owu.mysite.com")
API_KEY = get_credential("OPENWEBUI_API_KEY", "OPENWEBUI_API_KEY_COMMAND", "")

# Default model list from code
DEFAULT_MODELS = "gpt-5.1,anthropic/claude-sonnet-4.5,groq.moonshotai/kimi-k2-instruct"

def reset_models_valve(custom_models: Optional[str] = None):
    """
    Reset MODELS_TO_QUERY valve to default (or custom value)

    Args:
        custom_models: Optional custom model list. If None, uses code default.
    """

    models_to_set = custom_models if custom_models else DEFAULT_MODELS

    print(f"Connecting to {OPENWEBUI_URL}...")

    # Get all functions
    response = requests.get(
        f"{OPENWEBUI_URL}/api/v1/functions",
        headers={"Authorization": f"Bearer {API_KEY}"}
    )

    if response.status_code != 200:
        print(f"[ERROR] Failed to fetch functions: {response.status_code}")
        return False

    functions = response.json()

    # Find Council function
    council_func = None
    for func in functions:
        if func.get("id") == "council_orchestrator" or "Council" in func.get("name", ""):
            council_func = func
            break

    if not council_func:
        print("[ERROR] Could not find Council of LLMs function")
        return False

    print(f"[OK] Found function: {council_func['name']}")

    # Get current valves
    func_id = council_func["id"]
    current_valves = council_func.get("valves", {})

    print(f"\n[INFO] Current MODELS_TO_QUERY:")
    print(f"   {current_valves.get('MODELS_TO_QUERY', 'NOT SET')[:100]}...")

    # Update valves
    current_valves["MODELS_TO_QUERY"] = models_to_set

    # Update function
    update_response = requests.post(
        f"{OPENWEBUI_URL}/api/v1/functions/id/{func_id}/valves/update",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        },
        json=current_valves
    )

    if update_response.status_code == 200:
        print(f"\n[SUCCESS] Successfully reset MODELS_TO_QUERY to:")
        print(f"   {models_to_set}")
        return True
    else:
        print(f"\n[ERROR] Failed to update valves: {update_response.status_code}")
        print(f"   {update_response.text}")
        return False


if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("Council MODELS_TO_QUERY Valve Reset")
    print("=" * 60)
    print()

    if len(sys.argv) > 1:
        # Custom model list provided
        custom_models = sys.argv[1]
        print(f"Using custom model list: {custom_models[:100]}...")
        reset_models_valve(custom_models)
    else:
        # Use code default
        print(f"Resetting to code default: {DEFAULT_MODELS}")
        reset_models_valve()

    print()
    print("=" * 60)
    print("Done! You may need to refresh Open WebUI to see changes.")
    print("=" * 60)
