"""
Create bundled JSON exports for Open WebUI import

This script creates self-contained versions of each Council component
by inlining the schemas.py dependencies directly into each file.
"""

import json
import os
from datetime import datetime

def read_file(filename):
    """Read file content"""
    with open(filename, 'r', encoding='utf-8') as f:
        return f.read()

def extract_schemas_content():
    """Extract the schemas.py content without header comments"""
    content = read_file('schemas.py')
    # Remove the docstring at the top
    lines = content.split('\n')
    # Find where the actual code starts (after the module docstring)
    start_idx = 0
    in_docstring = False
    for i, line in enumerate(lines):
        if line.strip().startswith('"""'):
            if in_docstring:
                start_idx = i + 1
                break
            else:
                in_docstring = True

    # Return everything after the docstring
    return '\n'.join(lines[start_idx:])

def create_bundled_pipe(pipe_file, schemas_content):
    """Create a bundled version of a pipe/filter/action file"""
    content = read_file(pipe_file)

    # Find where imports start
    lines = content.split('\n')

    # Find the header (everything up to first import)
    header_end = 0
    for i, line in enumerate(lines):
        if line.strip().startswith('from typing') or line.strip().startswith('import '):
            header_end = i
            break

    # Extract header
    header = '\n'.join(lines[:header_end])

    # Find where the schema import is
    schema_import_start = -1
    schema_import_end = -1
    in_try_block = False

    for i in range(header_end, len(lines)):
        line = lines[i]

        # Check for try block start
        if line.strip().startswith('try:'):
            in_try_block = True
            if schema_import_start == -1:
                schema_import_start = i
            continue

        # Check for import statements
        if 'from schemas import' in line or ('import sys' in line and in_try_block):
            if schema_import_start == -1:
                schema_import_start = i

        # Check for except block (end of try/except)
        elif line.strip().startswith('except'):
            # Continue until we find the fallback import or end
            continue
        elif 'from schemas import' in line:
            # This is the fallback import in except block
            continue

        # End of import block detection
        elif schema_import_start != -1 and line.strip() and not line.strip().startswith('#'):
            # Check if still in import continuation
            if line.strip().endswith(',') or line.strip().endswith(')'):
                continue
            elif ')' in line:
                schema_import_end = i + 1
                break
            # Check if we're past the entire try/except block
            elif not in_try_block or (in_try_block and not line.strip().startswith('except') and not line.strip().startswith('import') and not line.strip().startswith('from') and not line.strip().startswith('sys.path')):
                schema_import_end = i
                break

    # If we found the import block, replace it
    if schema_import_start != -1:
        before_import = '\n'.join(lines[:schema_import_start])
        after_import = '\n'.join(lines[schema_import_end:])

        # Create bundled version
        bundled = f"{before_import}\n\n# ============================================================================\n"
        bundled += "# INLINED SCHEMAS (from schemas.py)\n"
        bundled += "# ============================================================================\n\n"
        bundled += schemas_content
        bundled += "\n\n# ============================================================================\n"
        bundled += "# MAIN COMPONENT CODE\n"
        bundled += "# ============================================================================\n\n"
        bundled += after_import

        return bundled
    else:
        # No schemas import found, return as-is
        return content

def create_json_export(component_name, component_type, content):
    """Create a JSON export in Open WebUI format"""

    # Extract metadata from header
    lines = content.split('\n')
    title = ""
    author = ""
    author_url = ""
    funding_url = ""
    version = ""
    description = ""

    for line in lines[:20]:  # Check first 20 lines
        if line.startswith('title:'):
            title = line.split('title:', 1)[1].strip()
        elif line.startswith('author:'):
            author = line.split('author:', 1)[1].strip()
        elif line.startswith('author_url:'):
            author_url = line.split('author_url:', 1)[1].strip()
        elif line.startswith('funding_url:'):
            funding_url = line.split('funding_url:', 1)[1].strip()
        elif line.startswith('version:'):
            version = line.split('version:', 1)[1].strip()
        elif line.startswith('description:'):
            description = line.split('description:', 1)[1].strip()

    # Create the JSON structure
    export = {
        "id": component_name,
        "user_id": "council-llms",  # Placeholder
        "name": title,
        "type": component_type,
        "content": content,
        "meta": {
            "description": description,
            "manifest": {
                "title": title,
                "author": author,
                "author_url": author_url,
                "funding_url": funding_url,
                "version": version,
                "license": "MIT"
            },
            "type": component_type
        },
        "is_active": True,
        "is_global": False,
        "updated_at": int(datetime.now().timestamp()),
        "created_at": int(datetime.now().timestamp())
    }

    return export

def main():
    print("Creating bundled Open WebUI exports...")

    # Read schemas content
    print("\n[1/9] Reading schemas.py...")
    schemas_content = extract_schemas_content()

    # Create bundled versions
    components = [
        ("council_orchestrator", "pipe", "council_orchestrator.py"),
        ("writers_room_orchestrator", "pipe", "writers_room_orchestrator.py"),
        ("council_evaluation_filter", "filter", "council_evaluation_filter.py"),
        ("council_synthesis_filter", "filter", "council_synthesis_filter.py"),
        ("council_score_extraction_filter", "filter", "council_score_extraction_filter.py"),
        ("council_show_details_action", "action", "council_show_details_action.py"),
        ("llm_roundtable", "manifold", "llm_roundtable.py"),
        ("llm_en_banc", "manifold", "llm_en_banc.py"),
    ]

    exports = []

    for i, (component_name, component_type, filename) in enumerate(components, start=2):
        print(f"\n[{i}/9] Creating bundled {component_name}...")

        # LLM Roundtable and En Banc don't use schemas, so don't bundle
        if component_name in ["llm_roundtable", "llm_en_banc"]:
            bundled_content = read_file(filename)
        else:
            bundled_content = create_bundled_pipe(filename, schemas_content)

        # Save bundled version
        bundled_filename = f"bundled_{filename}"
        with open(bundled_filename, 'w', encoding='utf-8') as f:
            f.write(bundled_content)
        print(f"  > Saved {bundled_filename}")

        # Create JSON export
        export = create_json_export(component_name, component_type, bundled_content)
        exports.append(export)

    # Save individual JSON files
    print("\n[9/9] Creating JSON exports...")
    for export in exports:
        json_filename = f"{export['id']}.json"
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump([export], f, indent=2)
        print(f"  > Saved {json_filename}")

    # Save combined JSON
    with open("council_llms_complete.json", 'w', encoding='utf-8') as f:
        json.dump(exports, f, indent=2)
    print(f"\n[OK] Saved council_llms_complete.json (all components)")

    print("\n" + "="*60)
    print("BUNDLED EXPORTS CREATED SUCCESSFULLY!")
    print("="*60)
    print("\nFiles created:")
    print("  - bundled_*.py - Self-contained Python files")
    print("  - council_*.json - Individual JSON imports")
    print("  - council_llms_complete.json - Complete suite import")
    print("\nTo import into Open WebUI:")
    print("  1. Go to Admin Panel > Functions")
    print("  2. Click 'Import Function'")
    print("  3. Upload council_llms_complete.json")
    print("  4. OR upload individual JSON files one by one")
    print()

if __name__ == "__main__":
    main()
