# Council Evaluation Fix Session - 2026-01-01

## Problem Statement
Council evaluations were failing at 75% rate (4/16 evaluations succeeding). Only Gemini model evaluations were working.

## Root Cause
The `response_format` parameter with strict JSON schema (`type: "json_schema"`) is only supported by certain providers:
- ✅ OpenAI (gpt-*) - supports strict JSON schema
- ✅ Google/Gemini - supports strict JSON schema
- ❌ Anthropic/Claude - does NOT support `response_format` with `json_schema`
- ❌ Groq - does NOT support strict JSON schema

## User's Configuration
**Query Models:**
- gpt-5.2 (direct OpenAI)
- anthropic/claude-opus-4.5 (OpenRouter)
- groq.moonshotai/kimi-k2-instruct (Groq)
- google/gemini-3-pro-preview (OpenRouter)

**Evaluation Models:**
- gpt-5.2 (OpenAI)
- anthropic/claude-sonnet-4.5 (OpenRouter)
- groq.moonshotai/kimi-k2-instruct (Groq)
- google/gemini-3-flash-preview (OpenRouter)

## Solution Implemented

### 1. Added `_supports_strict_json_schema(model_id)` helper
Detects which models support OpenAI's strict JSON schema based on model ID patterns:
```python
# Supports: gpt-*, o1*, o3*, google/*, *gemini*
# Does not support: anthropic/*, claude*, groq.*, mistral*, llama*
```

### 2. Added `_get_json_format_instructions(schema_type)` helper
Generates explicit JSON format instructions to append to prompts for models that don't support `response_format`.

### 3. Added `_parse_evaluation_json_fallback(raw_response, model_id)` helper
Multi-strategy JSON parser that tries:
1. Direct JSON parse
2. Extract from markdown code blocks
3. Find JSON object anywhere in response
4. Aggressive brace matching

### 4. Updated `_query_for_evaluation` and `_query_for_bulk_evaluation`
Both methods now:
- Check `_supports_strict_json_schema(evaluator_model_id)`
- If supported: use `response_format` with strict schema
- If not: add JSON instructions to prompt, use fallback parser

## Files Modified
- `council-pipeline/council_orchestrator.py` - Main modular version
- `council-pipeline/bundled_council_orchestrator.py` - Bundled version for Open WebUI

## Key Insight
**IMPORTANT:** Open WebUI uses the **bundled** versions (`bundled_*.py`). The initial fix only modified `council_orchestrator.py` but not `bundled_council_orchestrator.py`, which is why the problem persisted after the first attempt.

## Code Locations (in bundled version)
- `_supports_strict_json_schema`: ~line 2096
- `_get_json_format_instructions`: after `_supports_strict_json_schema`
- `_parse_evaluation_json_fallback`: after `_get_json_format_instructions`
- `_query_for_evaluation`: ~line 2912 (updated)
- `_query_for_bulk_evaluation`: ~line 2791 (updated)

## Testing
After fix, expect debug output like:
```
[Council] anthropic/claude-opus-4.5: Using prompt-based JSON (no strict schema support)
[Council] groq.moonshotai/kimi-k2-instruct: Using prompt-based JSON (no strict schema support)
```

## Related Issue
The `_query_and_evaluate_overlapped` method uses **peer evaluation** where query models evaluate each other's responses (not the separate EVALUATION_MODELS list). This is by design for the overlapped execution mode.
