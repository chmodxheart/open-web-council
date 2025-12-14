#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automatic Open WebUI Function Updater

This script automates the process of updating Council of LLMs functions:
1. Authenticates with Open WebUI API
2. Lists and finds existing Council functions
3. Deletes old versions
4. Imports new versions from JSON files
5. Enables them automatically
6. Verifies successful deployment

Usage:
    python update_functions.py
"""

import requests
import json
import os
import sys
import subprocess
from pathlib import Path
from typing import List, Dict, Optional

# Fix Windows console encoding for Unicode characters
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# Configuration
def get_credential(env_var: str, command_var: str, default: str = "") -> str:
    """
    Get credential from environment variable or command.

    Priority:
    1. Direct environment variable (e.g., OPENWEBUI_URL)
    2. Command from environment variable (e.g., OPENWEBUI_URL_COMMAND)
    3. Default value

    Examples:
        export OPENWEBUI_URL="https://owu.mysite.com"
        export OPENWEBUI_URL_COMMAND='op item get "OpenWebUI API Key" --fields label=url --reveal'
    """
    # Try direct env var first
    value = os.getenv(env_var)
    if value:
        return value

    # Try command from env var
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
        except subprocess.CalledProcessError as e:
            print(f"[WARNING] Failed to execute {command_var}: {e}")
            print(f"[WARNING] Falling back to default")

    return default

OPEN_WEBUI_URL = get_credential("OPENWEBUI_URL", "OPENWEBUI_URL_COMMAND", "https://owu.mysite.com")
API_KEY = get_credential("OPENWEBUI_API_KEY", "OPENWEBUI_API_KEY_COMMAND", "")

# Function name patterns to match
COUNCIL_FUNCTION_PATTERNS = [
    "Council of LLMs Orchestrator",
    "LLM Writer's Room",
    "Council Evaluation Filter",
    "Council Synthesis Filter",
    "Council Score Extraction Filter",
    "Council Show Details Action",
    "LLM Roundtable",
    "LLM En Banc"
]

# JSON files to import (in order)
JSON_FILES = [
    "council_orchestrator.json",
    "writers_room_orchestrator.json",
    "council_evaluation_filter.json",
    "council_synthesis_filter.json",
    "council_score_extraction_filter.json",
    "council_show_details_action.json",
    "llm_roundtable.json",
    "llm_en_banc.json"
]

class OpenWebUIUpdater:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    def test_connection(self) -> bool:
        """Test connection to Open WebUI API"""
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/functions/",
                headers=self.headers,
                timeout=10
            )
            if response.status_code == 200:
                print(f"✓ Connected to Open WebUI at {self.base_url}")
                return True
            else:
                print(f"✗ Failed to connect: HTTP {response.status_code}")
                print(f"  Response: {response.text}")
                return False
        except Exception as e:
            print(f"✗ Connection error: {e}")
            return False

    def list_functions(self) -> List[Dict]:
        """List all functions"""
        try:
            response = requests.get(
                f"{self.base_url}/api/v1/functions/",
                headers=self.headers,
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                # Response might be a list or a dict with a data field
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and "data" in data:
                    return data["data"]
                else:
                    return []
            else:
                print(f"✗ Failed to list functions: HTTP {response.status_code}")
                print(f"  Response: {response.text}")
                return []
        except Exception as e:
            print(f"✗ Error listing functions: {e}")
            return []

    def find_council_functions(self, functions: List[Dict]) -> List[Dict]:
        """Find all Council-related functions"""
        council_funcs = []
        for func in functions:
            name = func.get("name", "")
            for pattern in COUNCIL_FUNCTION_PATTERNS:
                if pattern.lower() in name.lower():
                    council_funcs.append(func)
                    break
        return council_funcs

    def delete_function(self, function_id: str, function_name: str) -> bool:
        """Delete a function by ID"""
        try:
            # Try POST with /delete endpoint first
            response = requests.post(
                f"{self.base_url}/api/v1/functions/id/{function_id}/delete",
                headers=self.headers,
                timeout=10
            )
            if response.status_code in [200, 204]:
                print(f"  ✓ Deleted: {function_name}")
                return True

            # If that didn't work, try DELETE
            response = requests.delete(
                f"{self.base_url}/api/v1/functions/id/{function_id}",
                headers=self.headers,
                timeout=10
            )
            if response.status_code in [200, 204]:
                print(f"  ✓ Deleted: {function_name}")
                return True
            else:
                # Deletion not available - manual deletion required
                print(f"  ⚠ Could not delete {function_name} - please delete manually via UI")
                return False
        except Exception as e:
            print(f"  ✗ Error deleting {function_name}: {e}")
            return False

    def import_function(self, json_file_path: Path) -> Optional[Dict]:
        """Import a function from JSON file"""
        try:
            with open(json_file_path, 'r', encoding='utf-8') as f:
                function_data = json.load(f)

            # JSON files are arrays with one element, extract it
            if isinstance(function_data, list) and len(function_data) > 0:
                function_data = function_data[0]

            name = function_data.get("name", json_file_path.stem)
            function_id = function_data.get("id", "")

            # Try to create
            response = requests.post(
                f"{self.base_url}/api/v1/functions/create",
                headers=self.headers,
                json=function_data,
                timeout=30
            )

            if response.status_code in [200, 201]:
                print(f"  ✓ Imported: {name}")
                return response.json()
            elif response.status_code == 400 and "already registered" in response.text:
                # Function exists, try to update it instead
                print(f"  ⚠ {name} already exists, updating...")
                response = requests.post(
                    f"{self.base_url}/api/v1/functions/id/{function_id}/update",
                    headers=self.headers,
                    json=function_data,
                    timeout=30
                )
                if response.status_code in [200, 201]:
                    print(f"  ✓ Updated: {name}")
                    return response.json()
                else:
                    print(f"  ✗ Failed to update {name}: HTTP {response.status_code}")
                    return None
            else:
                print(f"  ✗ Failed to import {json_file_path.name}: HTTP {response.status_code}")
                print(f"    Response: {response.text[:500]}")
                return None
        except Exception as e:
            print(f"  ✗ Error importing {json_file_path.name}: {e}")
            return None

    def toggle_function(self, function_id: str, function_name: str, enable: bool = True) -> bool:
        """Enable or disable a function"""
        try:
            response = requests.post(
                f"{self.base_url}/api/v1/functions/id/{function_id}/toggle",
                headers=self.headers,
                json={"active": enable},
                timeout=10
            )

            if response.status_code == 200:
                status = "enabled" if enable else "disabled"
                print(f"  ✓ {status.capitalize()}: {function_name}")
                return True
            else:
                print(f"  ✗ Failed to toggle {function_name}: HTTP {response.status_code}")
                return False
        except Exception as e:
            print(f"  ✗ Error toggling {function_name}: {e}")
            return False

    def update_all(self, script_dir: Path) -> bool:
        """Main update workflow"""
        print("\n" + "=" * 60)
        print("Council of LLMs Function Updater")
        print("=" * 60 + "\n")

        # Step 1: Test connection
        print("Step 1: Testing connection...")
        if not self.test_connection():
            return False
        print()

        # Step 2: List existing functions
        print("Step 2: Finding existing Council functions...")
        all_functions = self.list_functions()
        council_functions = self.find_council_functions(all_functions)

        if council_functions:
            print(f"Found {len(council_functions)} existing Council function(s):")
            for func in council_functions:
                print(f"  - {func.get('name', 'Unknown')} (ID: {func.get('id', 'Unknown')})")
        else:
            print("No existing Council functions found (first-time install)")
        print()

        # Step 3: Delete old versions
        if council_functions:
            print("Step 3: Deleting old versions...")
            for func in council_functions:
                self.delete_function(func.get("id"), func.get("name", "Unknown"))
            print()
        else:
            print("Step 3: No old versions to delete")
            print()

        # Step 4: Import new versions
        print("Step 4: Importing new versions...")
        imported_functions = []
        for json_file in JSON_FILES:
            json_path = script_dir / json_file
            if json_path.exists():
                result = self.import_function(json_path)
                if result:
                    imported_functions.append(result)
            else:
                print(f"  ⚠ Warning: {json_file} not found, skipping")

        if not imported_functions:
            print("\n✗ No functions were imported successfully!")
            return False
        print()

        # Step 5: Enable all imported functions
        print("Step 5: Enabling imported functions...")
        # Get fresh function list to find the newly imported ones
        all_functions = self.list_functions()
        council_functions = self.find_council_functions(all_functions)

        for func in council_functions:
            # Check if function is already active
            is_active = func.get("is_active", False)
            if not is_active:
                self.toggle_function(func.get("id"), func.get("name", "Unknown"), enable=True)
            else:
                print(f"  ✓ Already enabled: {func.get('name', 'Unknown')}")
        print()

        # Step 6: Verification
        print("Step 6: Verifying deployment...")
        all_functions = self.list_functions()
        council_functions = self.find_council_functions(all_functions)

        active_count = sum(1 for f in council_functions if f.get("is_active", False))
        print(f"Found {len(council_functions)} Council function(s), {active_count} enabled")
        print()

        # Summary
        print("=" * 60)
        print("✓ Update Complete!")
        print("=" * 60)
        print(f"\nImported: {len(imported_functions)} function(s)")
        print(f"Active:   {active_count} function(s)")
        print("\nYou can now test the Council in Open WebUI!")
        print("No need to refresh - functions are immediately available.")
        print()

        return True


def main():
    # Get script directory
    script_dir = Path(__file__).parent

    # Create updater
    updater = OpenWebUIUpdater(OPEN_WEBUI_URL, API_KEY)

    # Run update
    success = updater.update_all(script_dir)

    # Exit code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
