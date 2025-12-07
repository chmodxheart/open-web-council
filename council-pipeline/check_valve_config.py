"""
Check current valve configuration stored in Open WebUI database

This script shows what valve values are currently stored in the database,
which may differ from code defaults.
"""

import requests
import os
import subprocess
import json

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


def check_valve_config():
    """Check current valve configuration"""

    print(f"Connecting to {OPENWEBUI_URL}...")

    # Get all functions
    response = requests.get(
        f"{OPENWEBUI_URL}/api/v1/functions",
        headers={"Authorization": f"Bearer {API_KEY}"}
    )

    if response.status_code != 200:
        print(f"[ERROR] Failed to fetch functions: {response.status_code}")
        return

    functions = response.json()

    # Find Council function
    council_func = None
    for func in functions:
        if func.get("id") == "council_orchestrator" or "Council" in func.get("name", ""):
            council_func = func
            break

    if not council_func:
        print("[ERROR] Could not find Council of LLMs function")
        return

    print(f"[OK] Found function: {council_func['name']} (ID: {council_func['id']})")
    print()

    # Get valves
    valves = council_func.get("valves", {})

    # Show MODELS_TO_QUERY
    models_str = valves.get("MODELS_TO_QUERY", "NOT SET")
    models_list = [m.strip() for m in models_str.split(",") if m.strip()]

    print("=" * 70)
    print("MODELS_TO_QUERY Configuration")
    print("=" * 70)
    print()
    print(f"Raw value length: {len(models_str)} characters")
    print(f"Parsed model count: {len(models_list)}")
    print()
    print("Models configured:")
    for i, model in enumerate(models_list, 1):
        print(f"  {i:2d}. {model}")
    print()

    # Show other key valves
    print("=" * 70)
    print("Other Key Valve Settings")
    print("=" * 70)
    print()

    key_valves = [
        "MIN_MODELS_REQUIRED",
        "LEAD_SYNTHESIZER",
        "TOP_N_FOR_SYNTHESIS",
        "MIN_SCORE_FOR_SYNTHESIS",
        "TIMEOUT_SECONDS",
        "EVAL_TIMEOUT_SECONDS",
        "SHOW_EVALUATION_SCORES",
        "SHOW_INDIVIDUAL_RESPONSES",
        "SHOW_REASONING",
        "DEBUG_MODE",
    ]

    for valve_name in key_valves:
        value = valves.get(valve_name, "NOT SET")
        print(f"  {valve_name:30s} = {value}")

    print()


if __name__ == "__main__":
    print("=" * 70)
    print("Council Valve Configuration Check")
    print("=" * 70)
    print()

    check_valve_config()

    print("=" * 70)
    print()
    print("To reset MODELS_TO_QUERY to default, run:")
    print("  python reset_models_valve.py")
    print()
    print("To set custom models, run:")
    print("  python reset_models_valve.py \"model1,model2,model3\"")
    print()
