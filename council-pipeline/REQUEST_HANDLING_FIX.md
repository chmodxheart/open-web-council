# Request Handling Fix - En Banc & Roundtable

## Issue
Both LLM En Banc and LLM Roundtable were failing with connection errors:
```
HTTPConnectionPool(host='localhost', port=3000): Max retries exceeded
Failed to establish a new connection: [Errno 111] Connection refused
```

## Root Cause
En Banc and Roundtable were written with incorrect request/auth handling patterns that differed from the working Council code:

### Problems Identified:

1. **Wrong Request Extraction**
   - ❌ Using: `request = __user__.get("request")`
   - ✅ Should use: `__request__` parameter directly

2. **Wrong HTTP Library (En Banc only)**
   - ❌ Using: Synchronous `requests.post()`
   - ✅ Should use: Async `aiohttp.ClientSession()`

3. **Missing Helper Method (En Banc only)**
   - ❌ Missing: `_extract_token()` method
   - ✅ Should match: Council's token extraction pattern

## Solution Applied

### LLM En Banc (v0.1.2)

1. **Added `__request__` parameter to `pipe()` method**
   ```python
   async def pipe(self, body, __user__=None, __event_emitter__=None, __request__=None):
   ```

2. **Changed `evaluate_response()` to use `__request__` and async aiohttp**
   ```python
   async def evaluate_response(self, model_id, evaluation_prompt, request, __event_emitter__=None):
       # Get base URL and auth token (same pattern as Council)
       base_url = f"{request.url.scheme}://{request.url.netloc}" if request else "http://localhost:3000"
       auth_token = self._extract_token(request)

       # Use aiohttp for async requests
       async with aiohttp.ClientSession() as session:
           async with session.post(...) as response:
   ```

3. **Added `_extract_token()` helper method** (copied from Council)
   ```python
   def _extract_token(self, request: Any) -> str:
       """Extract authentication token from request (same pattern as Council)"""
       if not request:
           return ""
       try:
           auth_header = request.headers.get("Authorization", "")
           if auth_header.startswith("Bearer "):
               return auth_header.replace("Bearer ", "")
       except:
           pass
       return ""
   ```

4. **Updated task creation to pass `__request__`**
   ```python
   tasks = [
       self.evaluate_response(model, eval_prompt, __request__, __event_emitter__)
       for model in models
   ]
   ```

5. **Added aiohttp import**
   ```python
   import aiohttp
   ```

### LLM Roundtable (v0.1.1)

1. **Added `__request__` parameter to `pipe()` method**
   ```python
   async def pipe(self, body, __user__=None, __event_emitter__=None, __request__=None):
   ```

2. **Fixed request extraction**
   ```python
   # OLD (wrong):
   request = __user__.get("request") if __user__ else None

   # NEW (correct):
   request = __request__
   ```

Note: Roundtable already had:
- ✅ Async aiohttp usage
- ✅ `_extract_token()` method
- ✅ Proper auth header handling

## Why This Happened

The En Banc and Roundtable were written as standalone tools before being integrated with the Council system, and they used different (incorrect) patterns for:
- Request object access
- Token extraction
- HTTP client (sync vs async)

The Council orchestrator had the correct patterns all along, but they weren't copied to these components.

## Files Updated

### Source Files:
- `llm_en_banc.py` (v0.1.0 → v0.1.2)
- `llm_roundtable.py` (v0.1.0 → v0.1.1)

### Regenerated:
- `bundled_llm_en_banc.py`
- `bundled_llm_roundtable.py`
- `llm_en_banc.json`
- `llm_roundtable.json`
- `council_llms_complete.json`

## Testing

Both En Banc and Roundtable should now:
- ✅ Correctly extract the request object from `__request__` parameter
- ✅ Properly authenticate using Bearer token from request headers
- ✅ Use the correct base URL from the request
- ✅ Make async HTTP calls using aiohttp
- ✅ Work in the same environment as the Council orchestrator

## Pattern to Follow

For any future pipes/filters/actions that need to make API calls:

```python
async def pipe(self, body, __user__=None, __event_emitter__=None, __request__=None):
    # Extract base URL and token from __request__ (NOT from __user__)
    base_url = f"{__request__.url.scheme}://{__request__.url.netloc}" if __request__ else "http://localhost:3000"
    auth_token = self._extract_token(__request__)

    # Use aiohttp for async HTTP calls
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{base_url}/api/chat/completions",
            headers={
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=aiohttp.ClientTimeout(total=timeout_seconds)
        ) as response:
            # ...

def _extract_token(self, request: Any) -> str:
    """Extract authentication token from request"""
    if not request:
        return ""
    try:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header.replace("Bearer ", "")
    except:
        pass
    return ""
```

**Status:** ✅ Fixed
**Date:** 2025-12-09
