# Council of LLMs - Pipeline Source

**Developer documentation for the Council of LLMs pipeline source code.**

> **User documentation** (installation, configuration, usage) is in the [main README](../README.md).

**Version**: 0.6.0
**Status**: Fully Functional

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

### Building JSON Exports

If you modify the source files:

```bash
python create_bundled_exports.py
```

This creates bundled versions with inlined schemas and generates JSON exports ready for Open WebUI import.

### Testing Changes

1. Edit `council_orchestrator.py` or other source files
2. Run `python create_bundled_exports.py` to regenerate JSON exports
3. Import the new `council_orchestrator.json` into Open WebUI (Admin Panel > Functions)
4. Test in Open WebUI

### Development Scripts

| Script | Purpose |
|--------|---------|
| `update_functions.py` | Auto-update functions in Open WebUI via API |
| `check_valve_config.py` | Check current valve values in database |
| `reset_models_valve.py` | Reset MODELS_TO_QUERY to default |

**Credential Configuration** for development scripts: See [`.env.example`](../.env.example) in the root directory for flexible credential management (direct env vars, 1Password, AWS Secrets Manager, etc.).

## Additional Documentation

- **User Guide**: [Main README](../README.md)
- **Writer's Room Guide**: [WRITERS_ROOM_README.md](WRITERS_ROOM_README.md) - Creative writing variant
- **Release Notes**: `V0.6.0-RELEASE-NOTES.md`
- **Configuration Presets**: `QUICK-CONFIG-REFERENCE.md`
- **Testing Guide**: `TESTING-CONFIG-ALL-MODELS.md`
- **Import Instructions**: `JSON-EXPORTS-README.md`

---

**For installation, configuration, and usage instructions, see the [main README](../README.md).**
