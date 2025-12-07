# Council of LLMs - JSON Exports for Open WebUI

**Created**: 2025-12-04
**Status**: Ready for Import

## Overview

This directory contains JSON export files ready for importing into Open WebUI. Each file is self-contained with inlined schemas (no external dependencies).

## Available Exports

### Complete Suite (Recommended)

**File**: `council_llms_complete.json`

Contains all 5 Council components in a single import:
1. **Council of LLMs Orchestrator** (v0.2.0) - Pipe
2. **Council Evaluation Filter** (v0.1.0) - Inlet Filter
3. **Council Synthesis Filter** (v0.1.0) - Inlet Filter
4. **Council Score Extraction Filter** (v0.1.0) - Outlet Filter
5. **Council Show Details Action** (v0.1.0) - Action

**Import Method**: One-click import of the entire Council system.

### Individual Component Exports

If you prefer to import components individually:

| File | Component | Type | Version |
|------|-----------|------|---------|
| `council_orchestrator.json` | Council of LLMs Orchestrator | Pipe | 0.2.0 |
| `council_evaluation_filter.json` | Council Evaluation Filter | Inlet Filter | 0.1.0 |
| `council_synthesis_filter.json` | Council Synthesis Filter | Inlet Filter | 0.1.0 |
| `council_score_extraction_filter.json` | Council Score Extraction Filter | Outlet Filter | 0.1.0 |
| `council_show_details_action.json` | Council Show Details Action | Action | 0.1.0 |

**Import Method**: Import each JSON file separately.

## How to Import

### Method 1: Complete Suite (Easiest)

1. **Open WebUI Admin Panel**
   - Navigate to: `Admin Panel > Functions`

2. **Import Function**
   - Click the "Import Function" button
   - Select `council_llms_complete.json`
   - Click "Import"

3. **Verify**
   - All 5 components should appear in your Functions list
   - Check that each shows the correct version number

### Method 2: Individual Components

1. **Open WebUI Admin Panel**
   - Navigate to: `Admin Panel > Functions`

2. **Import Each Component**
   - Click "Import Function"
   - Select one JSON file (e.g., `council_orchestrator.json`)
   - Click "Import"
   - Repeat for each component

3. **Verify**
   - Ensure all 5 components are imported
   - Check dependencies are working

## JSON Structure

Each JSON export follows the Open WebUI standard format:

```json
[
  {
    "id": "council_orchestrator",
    "user_id": "council-llms",
    "name": "Council of LLMs Orchestrator",
    "type": "pipe",
    "content": "... (full Python code) ...",
    "meta": {
      "description": "Core orchestrator pipe for multi-LLM consultation with anonymous peer review",
      "manifest": {
        "title": "Council of LLMs Orchestrator",
        "author": "chmodxheart",
        "author_url": "https://github.com/chmodxheart",
        "funding_url": "https://github.com/chmodxheart",
        "version": "0.2.0",
        "license": "MIT"
      },
      "type": "pipe"
    },
    "is_active": true,
    "is_global": false,
    "updated_at": 1764722084,
    "created_at": 1764722062
  }
]
```

## Bundled Python Files

The script also creates bundled Python files with inlined schemas:

- `bundled_council_orchestrator.py`
- `bundled_council_evaluation_filter.py`
- `bundled_council_synthesis_filter.py`
- `bundled_council_score_extraction_filter.py`
- `bundled_council_show_details_action.py`

These are the actual code embedded in the JSON exports. You can review them to see the self-contained versions.

## Key Differences from Original Files

### Original Files
- Import `schemas.py` as external module
- Require all files in same directory
- Suitable for development

### Bundled Files (JSON Exports)
- Have schemas inlined directly
- Fully self-contained
- No external dependencies
- Ready for Open WebUI import

## Configuration After Import

After importing, configure the Orchestrator via Admin Panel:

1. **Models to Query**
   - Edit `MODELS_TO_QUERY` Valve
   - Format: `model1,model2,model3`
   - Example: `gpt-5.1,anthropic/claude-sonnet-4.5,groq.moonshotai/kimi-k2-instruct`

2. **Per-Model Parameters** (Optional)
   - Edit `MODEL_PARAMS_JSON` Valve
   - Format: JSON object with model-specific settings
   - Example:
     ```json
     {
       "gpt-4": {"temperature": 0.7, "max_tokens": 2048},
       "claude-3-opus": {"temperature": 0.5, "max_tokens": 4096}
     }
     ```

3. **Evaluation Weights**
   - Adjust `EVALUATION_WEIGHT_*` Valves
   - Must sum to 1.0
   - Default: Accuracy 30%, Clarity 25%, Completeness 25%, Relevance 20%

4. **User-Editable Prompts**
   - **Evaluation Rubric**: Edit in `Council Evaluation Filter` Valves
   - **Synthesis Instructions**: Edit in `Council Synthesis Filter` Valves
   - Both support template placeholders

## Regenerating Exports

If you modify the source code and need to regenerate:

```bash
cd council-pipeline
python create_bundled_exports.py
```

This will:
1. Read `schemas.py` and all component files
2. Inline schemas into each component
3. Generate bundled Python files
4. Create individual JSON exports
5. Create complete JSON export

## Troubleshooting

### Import Fails
- **Error**: "Invalid JSON format"
  - **Solution**: Ensure JSON file is not corrupted; regenerate if needed

### Components Don't Appear
- **Error**: Functions list empty after import
  - **Solution**: Refresh the page; check browser console for errors

### Dependencies Missing
- **Error**: "ModuleNotFoundError: No module named 'schemas'"
  - **Solution**: Use JSON exports (not original .py files); they have inlined schemas

### Metadata Not Showing
- **Error**: Author/version not displayed
  - **Solution**: Verify JSON `meta.manifest` fields are present; reimport if needed

## Version History

### v0.2.0 (Orchestrator) - 2025-12-04
- Open WebUI headers added
- JSON export format implemented
- Self-contained bundled versions

### v0.1.0 (Filters & Actions) - 2025-12-04
- Initial release
- User-editable Valves templates
- Hybrid Pipe + Filter + Action architecture

## License

MIT License - See individual component headers for details

## Support

- **Issues**: https://github.com/chmodxheart/open-web-council/issues
- **Documentation**: See `docs/` directory
- **Funding**: https://github.com/chmodxheart

---

**Ready to import!** Use `council_llms_complete.json` for easiest setup.
