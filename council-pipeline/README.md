# Council of LLMs - Pipeline Source

**Developer documentation for the Council of LLMs pipeline source code.**

> **User documentation** (installation, configuration, usage) is in the [main README](../README.md).

**Version**: 0.6.1
**Status**: Production Ready

## Files

### Core Tools

| File | Description |
|------|-------------|
| `council_orchestrator.py` | Full Council pipeline (v0.6.0) |
| `writers_room_orchestrator.py` | Creative writing variant with creative rubrics (v0.1.0) |
| `llm_roundtable.py` | Parallel multi-model query (v0.1.0) |
| `llm_en_banc.py` | Multi-model response evaluation (v0.1.0) |
| `schemas.py` | Shared data structures |

### Ready-to-Import JSON Files

| File | Description |
|------|-------------|
| `council_orchestrator.json` | Council of LLMs (full pipeline) |
| `writers_room_orchestrator.json` | Writer's Room (creative writing focused) |
| `llm_roundtable.json` | LLM Roundtable (parallel query) |
| `llm_en_banc.json` | LLM En Banc (evaluation) |

### Supporting Components (Optional)

These filters were part of the original architecture but are now optional - the orchestrator is self-contained:

| File | Description |
|------|-------------|
| `council_evaluation_filter.py` | Evaluation prompt filter |
| `council_synthesis_filter.py` | Synthesis prompt filter |
| `council_score_extraction_filter.py` | Score extraction filter |
| `council_show_details_action.py` | Interactive details action |

### Build Files

| File | Description |
|------|-------------|
| `create_bundled_exports.py` | Script to generate JSON exports |
| `bundled_*.py` | Self-contained versions with inlined schemas |
| `*.json` | Ready-to-import JSON exports |

## Development Workflow

### Quick Iteration Cycle (Recommended)

The fastest way to develop and test changes:

```bash
# 1. Edit source files
vim writers_room_orchestrator.py

# 2. Regenerate JSON exports
python create_bundled_exports.py

# 3. Deploy to Open WebUI (preserves Valve configs!)
python update_functions.py
```

The `update_functions.py` script is the **recommended way** to deploy changes because it:
- Automatically updates existing functions (no manual deletion needed)
- Preserves your Valve configurations
- Creates new functions if they don't exist
- Handles all JSON files in one command

### Building JSON Exports

After modifying any source `.py` file:

```bash
python create_bundled_exports.py
```

This script:
- Reads schemas from `schemas.py`
- Creates bundled versions with inlined schemas
- Generates JSON exports for Open WebUI import
- Creates both individual function JSONs and `council_llms_complete.json`

### Manual Testing (Alternative)

If you prefer manual import:

1. Edit `council_orchestrator.py` or other source files
2. Run `python create_bundled_exports.py` to regenerate JSON exports
3. Go to Open WebUI Admin Panel → Functions
4. Delete the old function (if updating)
5. Import the new `council_orchestrator.json`
6. Reconfigure Valves (they reset on manual import)
7. Test in Open WebUI

**Note**: Manual import requires reconfiguring Valves. Use `update_functions.py` to preserve settings.

### Development Scripts

| Script | Purpose |
|--------|---------|
| `update_functions.py` | **Deploy/update functions in Open WebUI via API** (preserves Valves) |
| `create_bundled_exports.py` | Generate JSON exports from source files |
| `check_valve_config.py` | View current Valve values for all functions |
| `reset_models_valve.py` | Reset MODELS_TO_QUERY to default value |

**Credential Configuration**: See [`.env.example`](../.env.example) for flexible credential management (direct env vars, 1Password, AWS Secrets Manager, etc.).

## Additional Documentation

- **User Guide**: [Main README](../README.md)
- **Writer's Room Guide**: [WRITERS_ROOM_README.md](WRITERS_ROOM_README.md) - Creative writing variant
- **Release Notes**: `V0.6.0-RELEASE-NOTES.md`
- **Configuration Presets**: `QUICK-CONFIG-REFERENCE.md`
- **Testing Guide**: `TESTING-CONFIG-ALL-MODELS.md`
- **Import Instructions**: `JSON-EXPORTS-README.md`

---

**For installation, configuration, and usage instructions, see the [main README](../README.md).**
