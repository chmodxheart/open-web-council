# Architecture Refinement: Leveraging Open WebUI's Internal API

**Date**: 2025-12-03
**Status**: Critical Architecture Update

## Key Discovery

You're absolutely correct! We can leverage Open WebUI's existing infrastructure instead of implementing direct API calls to external providers. This significantly simplifies our implementation and provides better integration.

## What Open WebUI Provides

### 1. Unified Chat Completions API

**Endpoint**: `POST /api/chat/completions` (Open WebUI internal)

**Capabilities**:
- OpenAI-compatible interface
- Works with ALL configured models in Open WebUI:
  - Ollama models
  - OpenAI models
  - Anthropic models (if configured)
  - Google models (if configured)
  - Any model configured via Pipelines or Functions

**Key Advantage**: Single API interface for all models, regardless of provider!

### 2. Model Discovery API

**Endpoint**: `GET /api/models`

**Returns**: All models configured in Open WebUI
- Ollama models
- OpenAI models
- Pipeline models
- Function models

### 3. Available Context in Pipelines

From `reserved-args.mdx`, pipelines receive:

```python
def pipe(
    self,
    user_message: str,
    model_id: str,
    messages: List[dict],
    body: dict,
    __user__: dict = None,          # User information
    __metadata__: dict = None,      # Chat metadata
    __model__: dict = None,         # Model information
    __messages__: List[dict] = None,# Full message history
    __request__: Request = None,    # FastAPI request object
):
```

**Critical**: `__request__` gives us access to the FastAPI Request object!

## Revised Architecture for Council Pipeline

### OLD Approach (Phase 1.1 Design)
```python
# Direct API calls to each provider
async def query_openai(api_key, model, messages):
    async with aiohttp.ClientSession() as session:
        response = await session.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "messages": messages}
        )
        return await response.json()

async def query_anthropic(api_key, model, messages):
    # Different API format for Anthropic
    ...

async def query_google(api_key, model, messages):
    # Different API format for Google
    ...
```

**Problems**:
- Need to handle each provider's unique API format
- Need to manage multiple API keys
- Need to implement authentication for each provider
- Need to handle rate limiting separately per provider
- Bypasses Open WebUI's existing model management

### NEW Approach (Using Open WebUI Internal API) ⭐

```python
async def query_model_via_openwebui(
    request: Request,
    model_id: str,
    messages: List[dict],
    user_token: str
):
    """
    Query ANY model configured in Open WebUI via its unified API
    """
    # Get Open WebUI base URL from request
    base_url = f"{request.url.scheme}://{request.url.netloc}"

    async with aiohttp.ClientSession() as session:
        response = await session.post(
            f"{base_url}/api/chat/completions",
            headers={
                "Authorization": f"Bearer {user_token}",
                "Content-Type": "application/json"
            },
            json={
                "model": model_id,  # Any model: gpt-4, claude-3-opus, llama3:70b, etc.
                "messages": messages,
                "stream": False
            }
        )
        return await response.json()
```

**Advantages**:
- ✅ Single unified API for ALL models
- ✅ No need to manage individual provider API keys (Open WebUI handles it)
- ✅ No need to implement provider-specific authentication
- ✅ Leverage Open WebUI's existing rate limiting and error handling
- ✅ Automatically supports any new models added to Open WebUI
- ✅ User's existing API keys/configurations are used
- ✅ Respects user's model permissions and access controls

## Updated Council Pipeline Architecture

### Query Distribution Module (Revised)

```python
class Pipeline:
    async def query_all_models(
        self,
        models: List[str],
        messages: List[dict],
        request: Request,
        user_token: str
    ) -> List[Dict]:
        """
        Query multiple models in parallel via Open WebUI's API
        """
        base_url = f"{request.url.scheme}://{request.url.netloc}"

        async def query_single_model(model_id: str):
            try:
                async with aiohttp.ClientSession() as session:
                    response = await session.post(
                        f"{base_url}/api/chat/completions",
                        headers={
                            "Authorization": f"Bearer {user_token}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": model_id,
                            "messages": messages,
                            "stream": False
                        },
                        timeout=aiohttp.ClientTimeout(total=self.valves.TIMEOUT_SECONDS)
                    )

                    if response.status == 200:
                        data = await response.json()
                        return {
                            "model_id": model_id,
                            "success": True,
                            "content": data["choices"][0]["message"]["content"],
                            "tokens": data.get("usage", {}).get("total_tokens", 0),
                            "latency_ms": response.elapsed.total_seconds() * 1000
                        }
                    else:
                        return {
                            "model_id": model_id,
                            "success": False,
                            "error": f"HTTP {response.status}"
                        }
            except Exception as e:
                return {
                    "model_id": model_id,
                    "success": False,
                    "error": str(e)
                }

        # Query all models in parallel
        tasks = [query_single_model(model) for model in models]
        results = await asyncio.gather(*tasks)

        # Filter successful responses
        successful = [r for r in results if r.get("success")]

        if len(successful) < self.valves.MIN_MODELS_REQUIRED:
            raise Exception(f"Only {len(successful)} models responded successfully. Need {self.valves.MIN_MODELS_REQUIRED}.")

        return successful
```

### Getting User Token

From the `__user__` reserved argument, we can extract authentication:

```python
def pipe(
    self,
    user_message: str,
    model_id: str,
    messages: List[dict],
    body: dict,
    __user__: dict = None,
    __request__: Request = None,
):
    # Extract user token from request headers
    auth_header = __request__.headers.get("Authorization", "")
    user_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""

    # Or generate a new token if needed (requires access to Open WebUI's auth system)
    # user_id = __user__["id"]
```

### Getting Available Models

```python
async def get_available_models(self, request: Request, user_token: str) -> List[str]:
    """
    Fetch all models available in Open WebUI
    """
    base_url = f"{request.url.scheme}://{request.url.netloc}"

    async with aiohttp.ClientSession() as session:
        response = await session.get(
            f"{base_url}/api/models",
            headers={"Authorization": f"Bearer {user_token}"}
        )

        if response.status == 200:
            data = await response.json()
            return [model["id"] for model in data.get("data", [])]
        else:
            return []
```

## Updated Valves Configuration

```python
class Valves(BaseModel):
    # Model Selection - now just model IDs, not API keys!
    MODELS_TO_QUERY: str = Field(
        default="gpt-4,claude-3-opus,gemini-pro,llama3:70b",
        description="Comma-separated list of model IDs available in Open WebUI"
    )

    AUTO_DETECT_MODELS: bool = Field(
        default=False,
        description="Automatically use all available models in Open WebUI"
    )

    LEAD_SYNTHESIZER: str = Field(
        default="auto",
        description="Model ID for synthesis ('auto' for highest-scoring)"
    )

    MIN_MODELS_REQUIRED: int = Field(
        default=3,
        description="Minimum models needed for Council"
    )

    # NO MORE API KEYS NEEDED!
    # Open WebUI handles all authentication

    # Evaluation Configuration
    EVALUATION_WEIGHT_ACCURACY: float = 0.3
    EVALUATION_WEIGHT_CLARITY: float = 0.25
    EVALUATION_WEIGHT_COMPLETENESS: float = 0.25
    EVALUATION_WEIGHT_RELEVANCE: float = 0.2

    # Performance Configuration
    TOKEN_BUDGET_MAX: int = 10000
    TIMEOUT_SECONDS: int = 30

    # Output Configuration
    SHOW_INDIVIDUAL_RESPONSES: bool = False
    SHOW_EVALUATION_SCORES: bool = True
    SHOW_REASONING: bool = False

    DEBUG_MODE: bool = False
```

## Benefits of This Approach

### 1. **Radical Simplification**
- ❌ No need to manage OpenAI API keys
- ❌ No need to manage Anthropic API keys
- ❌ No need to manage Google API keys
- ❌ No need to manage Ollama base URLs
- ✅ Use Open WebUI's existing configuration!

### 2. **Automatic Provider Support**
- Works with ANY model configured in Open WebUI
- Automatically supports new providers added to Open WebUI
- No code changes needed to support new providers

### 3. **Security & Access Control**
- Respects Open WebUI's user permissions
- Respects Open WebUI's model access controls
- Uses user's own API quotas/limits
- No additional API key storage needed

### 4. **User Experience**
- Users don't need to configure API keys twice
- Works with their existing Open WebUI setup
- Transparent integration with existing models

### 5. **Maintenance**
- Open WebUI team handles provider API changes
- We don't need to update code for API updates
- Leverage community fixes and improvements

## What We Still Need to Implement

1. **Anonymization Layer** (unchanged)
   - Strip model identifiers from responses
   - Assign random tokens

2. **Evaluation Logic** (simplified)
   - Use same Open WebUI API to send evaluation prompts
   - Parse scores from responses

3. **Synthesis Logic** (simplified)
   - Use same Open WebUI API for final synthesis
   - Format output for user

4. **Scoring Aggregation** (unchanged)
   - Calculate aggregate scores
   - Rank responses

## Hermeneutic Insight

**The Whole** (revised understanding):
- Council is not a standalone multi-LLM orchestrator
- Council is an *Open WebUI-native* peer-review system
- It leverages the platform's existing infrastructure

**The Parts** (revised understanding):
- Query Distribution → Uses Open WebUI's unified model API
- Anonymization → Pure logic layer (unchanged)
- Evaluation → Uses Open WebUI's unified model API
- Synthesis → Uses Open WebUI's unified model API

**The Interplay**:
- Council extends Open WebUI, doesn't replace or bypass it
- Each component trusts Open WebUI's existing capabilities
- The system's meaning emerges from *enhancing* Open WebUI's native multi-model support

## Implementation Impact

### Phase 2.1 Changes

**Before** (original plan):
1. Implement OpenAI API client
2. Implement Anthropic API client
3. Implement Google API client
4. Implement Ollama API client
5. Manage API keys per provider
6. Handle authentication per provider
7. Implement anonymization

**After** (revised plan):
1. Implement single Open WebUI API client ✅ (much simpler!)
2. Extract user token from request
3. Query models via `/api/chat/completions`
4. Implement anonymization

**Lines of Code Reduction**: ~60-70% reduction in query distribution module!

### Configuration Simplification

**User Setup - Before**:
```
1. Configure OpenAI API key in Council pipeline
2. Configure Anthropic API key in Council pipeline
3. Configure Google API key in Council pipeline
4. Configure Ollama base URL in Council pipeline
5. Select models to use
```

**User Setup - After**:
```
1. Select models to use (that's it!)
   (Models already configured in Open WebUI)
```

## Updated Phase 2.1 Tasks

**Revised Objectives**:
1. ✅ Implement Open WebUI API client (single unified client)
2. ✅ Extract user authentication from request context
3. ✅ Query multiple models in parallel via `/api/chat/completions`
4. ✅ Collect responses with metadata
5. ✅ Implement anonymization layer
6. ✅ Handle errors and graceful degradation
7. ✅ Test with multiple model types (OpenAI, Anthropic, Ollama)

**Estimated Complexity**: Reduced from **High** to **Medium**
**Estimated Time**: Reduced from **1-2 weeks** to **3-5 days**

## Next Steps

1. Update `council_pipeline.py` to use `__request__` parameter
2. Implement Open WebUI API client helper functions
3. Remove all provider-specific API key valves
4. Simplify configuration to model selection only
5. Test with multiple models configured in Open WebUI
6. Update documentation to reflect simplified setup

---

**Key Takeaway**: By leveraging Open WebUI's existing infrastructure, we've dramatically simplified the implementation while improving integration, security, and user experience. This is the hermeneutic circle in action - understanding the whole (Open WebUI ecosystem) reveals simpler implementations for the parts (Council modules).
