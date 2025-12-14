# Async Event Loop Fix - LLM En Banc

## Issue
LLM En Banc was throwing error:
```
asyncio.run() cannot be called from a running event loop
```

## Root Cause
The `pipe()` method was defined as a regular function (`def pipe()`) instead of async (`async def pipe()`), and it was using `asyncio.run()` to execute async operations.

In Open WebUI's pipeline environment, the event loop is already running, so calling `asyncio.run()` from within that event loop causes a conflict.

## Solution
Changed the `pipe()` method from synchronous to asynchronous:

**Before:**
```python
def pipe(self, body, __user__=None, __event_emitter__=None):
    # ...
    if __event_emitter__:
        asyncio.run(__event_emitter__({...}))  # ❌ Error!

    results = asyncio.run(evaluate_all())  # ❌ Error!
```

**After:**
```python
async def pipe(self, body, __user__=None, __event_emitter__=None):
    # ...
    if __event_emitter__:
        await __event_emitter__({...})  # ✅ Correct

    results = await asyncio.gather(*tasks)  # ✅ Correct
```

## Changes Made

### File: `llm_en_banc.py`
1. Changed `def pipe()` to `async def pipe()` (line 218)
2. Replaced `asyncio.run(__event_emitter__(...))` with `await __event_emitter__(...)` (line 259)
3. Replaced nested async function and `asyncio.run(evaluate_all())` with direct `await asyncio.gather(*tasks)` (lines 265-269)
4. Replaced final `asyncio.run(__event_emitter__(...))` with `await __event_emitter__(...)` (line 327)
5. Updated version from 0.1.0 to 0.1.1

### Verification
Other components already using async correctly:
- ✅ `council_orchestrator.py` - Already `async def pipe()`
- ✅ `llm_roundtable.py` - Already `async def pipe()`
- ✅ `writers_room_orchestrator.py` - Already `async def pipe()` (inherited from Council)

## Files Updated
- `llm_en_banc.py` - Source file
- `bundled_llm_en_banc.py` - Bundled version (regenerated)
- `llm_en_banc.json` - JSON export (regenerated)
- `council_llms_complete.json` - Complete suite (regenerated)

## Testing
The fix allows En Banc to properly execute within Open WebUI's async pipeline environment without event loop conflicts.

**Status:** ✅ Fixed and verified
**Version:** 0.1.1
**Date:** 2025-12-09
