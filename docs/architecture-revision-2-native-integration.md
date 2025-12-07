# Architecture Revision 2: Full Native Open WebUI Integration

**Date**: 2025-12-03
**Status**: Major Architecture Enhancement
**Previous**: Architecture Refinement (Using Open WebUI API)
**Current**: Hybrid Pipe + Filter + Action Architecture

## Key Insight: Use Open WebUI's Native Plugin System

Your observation is **profound and correct**: We should leverage Open WebUI's complete plugin ecosystem, not just Pipelines!

## The Three Plugin Types We Can Use

### 1. **Pipe Function** (Main Orchestrator)
**Purpose**: Central Council controller that manages the overall workflow

**What it handles**:
- Overall workflow orchestration
- State management across the Council process
- Final synthesis and output formatting
- Calling other models via Open WebUI API

### 2. **Filter Functions** (Processing Steps) ⭐ NEW
**Purpose**: Modular, user-configurable processing steps

**What they handle**:
- **Inlet Filters**: Pre-processing before each step
  - Add evaluation instructions to models
  - Add anonymization instructions
  - Add synthesis instructions
- **Outlet Filters**: Post-processing after responses
  - Extract scores from evaluation responses
  - Format outputs

**Key Advantage**: Users can **edit filter prompts in the UI** without touching code!

### 3. **Action Functions** (User Interactions) ⭐ NEW
**Purpose**: Interactive buttons for user control

**What they handle**:
- "Show Individual Responses" button
- "Re-evaluate with Different Criteria" button
- "Show Reasoning" button
- "Change Lead Model" button

## Revised Architecture: Hybrid Approach

```
┌─────────────────────────────────────────────────────────────┐
│                  COUNCIL OF LLMs SYSTEM                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌────────────────────────────────────────────────────┐     │
│  │  PIPE: Council Orchestrator                        │     │
│  │  (Main workflow controller)                        │     │
│  └────────────────────────────────────────────────────┘     │
│                          │                                    │
│                          ▼                                    │
│  ┌────────────────────────────────────────────────────┐     │
│  │  FILTER: Query Preparation (Inlet)                 │     │
│  │  - User-editable prompt for initial query          │     │
│  │  - Configurable in UI                              │     │
│  └────────────────────────────────────────────────────┘     │
│                          │                                    │
│                          ▼                                    │
│  ┌────────────────────────────────────────────────────┐     │
│  │  PIPE: Query Distribution                          │     │
│  │  - Calls N models via Open WebUI API               │     │
│  │  - Collects responses                               │     │
│  └────────────────────────────────────────────────────┘     │
│                          │                                    │
│                          ▼                                    │
│  ┌────────────────────────────────────────────────────┐     │
│  │  PIPE: Anonymization                               │     │
│  │  - Strips model identifiers                        │     │
│  │  - Assigns random tokens                           │     │
│  └────────────────────────────────────────────────────┘     │
│                          │                                    │
│                          ▼                                    │
│  ┌────────────────────────────────────────────────────┐     │
│  │  FILTER: Evaluation Instructions (Inlet)           │     │
│  │  - User-editable evaluation rubric prompt          │     │
│  │  - Configurable criteria emphasis                  │     │
│  │  - Editable in UI without code changes!            │     │
│  └────────────────────────────────────────────────────┘     │
│                          │                                    │
│                          ▼                                    │
│  ┌────────────────────────────────────────────────────┐     │
│  │  PIPE: Evaluation Distribution                     │     │
│  │  - Sends anonymous responses to all models          │     │
│  │  - Collects evaluation responses                    │     │
│  └────────────────────────────────────────────────────┘     │
│                          │                                    │
│                          ▼                                    │
│  ┌────────────────────────────────────────────────────┐     │
│  │  FILTER: Score Extraction (Outlet)                 │     │
│  │  - Parses scores from evaluation text              │     │
│  │  - User-editable parsing logic                     │     │
│  └────────────────────────────────────────────────────┘     │
│                          │                                    │
│                          ▼                                    │
│  ┌────────────────────────────────────────────────────┐     │
│  │  PIPE: Score Aggregation                           │     │
│  │  - Calculates weighted scores                      │     │
│  │  - Ranks responses                                 │     │
│  └────────────────────────────────────────────────────┘     │
│                          │                                    │
│                          ▼                                    │
│  ┌────────────────────────────────────────────────────┐     │
│  │  FILTER: Synthesis Instructions (Inlet)            │     │
│  │  - User-editable synthesis prompt                  │     │
│  │  - Configurable output format                      │     │
│  │  - Editable in UI!                                 │     │
│  └────────────────────────────────────────────────────┘     │
│                          │                                    │
│                          ▼                                    │
│  ┌────────────────────────────────────────────────────┐     │
│  │  PIPE: Lead Model Synthesis                        │     │
│  │  - Calls lead model with top responses             │     │
│  │  - Generates final answer                          │     │
│  └────────────────────────────────────────────────────┘     │
│                          │                                    │
│                          ▼                                    │
│  ┌────────────────────────────────────────────────────┐     │
│  │  FILTER: Output Formatting (Outlet)                │     │
│  │  - Formats final response                          │     │
│  │  - Optionally adds score summary                   │     │
│  └────────────────────────────────────────────────────┘     │
│                          │                                    │
│                          ▼                                    │
│  ┌────────────────────────────────────────────────────┐     │
│  │  ACTIONS: User Interactions                        │     │
│  │  [Show Responses] [Re-evaluate] [Change Settings]  │     │
│  └────────────────────────────────────────────────────┘     │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Component Breakdown

### Main Pipe: `council_orchestrator.py`

```python
"""
Council Orchestrator Pipe
Main workflow controller for Council of LLMs
"""

class Pipeline:
    class Valves(BaseModel):
        # Model Selection
        MODELS_TO_QUERY: str = Field(
            default="gpt-4,claude-3-opus,gemini-pro",
            description="Comma-separated model IDs"
        )

        # Lead Model Selection
        LEAD_SYNTHESIZER: str = Field(
            default="auto",
            description="Lead model ID or 'auto' for highest-scoring"
        )

        # Per-Model Parameters Override (NEW!)
        MODEL_PARAMS_JSON: str = Field(
            default="{}",
            description="JSON dict of model-specific parameters: {\"gpt-4\": {\"temperature\": 0.7}, \"claude-3-opus\": {\"temperature\": 0.5}}"
        )

        # Default Model Parameters (NEW!)
        DEFAULT_TEMPERATURE: float = Field(
            default=0.7,
            description="Default temperature for all models"
        )

        DEFAULT_TOP_P: float = Field(
            default=1.0,
            description="Default top_p for all models"
        )

        DEFAULT_MAX_TOKENS: int = Field(
            default=2048,
            description="Default max tokens for all models"
        )

        # Evaluation Configuration
        EVALUATION_WEIGHT_ACCURACY: float = 0.3
        EVALUATION_WEIGHT_CLARITY: float = 0.25
        EVALUATION_WEIGHT_COMPLETENESS: float = 0.25
        EVALUATION_WEIGHT_RELEVANCE: float = 0.2

        # System Configuration
        MIN_MODELS_REQUIRED: int = 3
        TIMEOUT_SECONDS: int = 30
        DEBUG_MODE: bool = False

    async def pipe(
        self,
        user_message: str,
        model_id: str,
        messages: List[dict],
        body: dict,
        __user__: dict = None,
        __request__: Request = None,
    ):
        """
        Main orchestration logic
        Coordinates with filters and actions
        """
        # 1. Parse model list
        models = self._parse_models()

        # 2. Get model-specific parameters
        model_params = self._get_model_params()

        # 3. Query all models (with individual params!)
        responses = await self._query_all_models(
            models, messages, __request__, __user__, model_params
        )

        # 4. Anonymize responses
        anonymous_responses = self._anonymize_responses(responses)

        # 5. Distribute for evaluation
        evaluations = await self._evaluate_responses(
            anonymous_responses, models, __request__, __user__
        )

        # 6. Aggregate scores
        scores = self._aggregate_scores(evaluations)

        # 7. Synthesize final answer
        final_response = await self._synthesize(
            scores, anonymous_responses, messages, __request__, __user__
        )

        return final_response

    def _get_model_params(self) -> Dict[str, Dict]:
        """
        Get per-model parameters, falling back to defaults
        """
        # Parse custom params JSON
        try:
            custom_params = json.loads(self.valves.MODEL_PARAMS_JSON)
        except:
            custom_params = {}

        # Build params dict for each model
        model_params = {}
        for model_id in self._parse_models():
            model_params[model_id] = {
                "temperature": custom_params.get(model_id, {}).get(
                    "temperature", self.valves.DEFAULT_TEMPERATURE
                ),
                "top_p": custom_params.get(model_id, {}).get(
                    "top_p", self.valves.DEFAULT_TOP_P
                ),
                "max_tokens": custom_params.get(model_id, {}).get(
                    "max_tokens", self.valves.DEFAULT_MAX_TOKENS
                ),
            }

        return model_params

    async def _query_all_models(
        self,
        models: List[str],
        messages: List[dict],
        request: Request,
        user: dict,
        model_params: Dict[str, Dict]
    ):
        """
        Query multiple models with individual parameters
        """
        base_url = f"{request.url.scheme}://{request.url.netloc}"
        auth_token = self._extract_token(request)

        async def query_model(model_id: str):
            params = model_params.get(model_id, {})

            async with aiohttp.ClientSession() as session:
                response = await session.post(
                    f"{base_url}/api/chat/completions",
                    headers={
                        "Authorization": f"Bearer {auth_token}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model_id,
                        "messages": messages,
                        "stream": False,
                        # Per-model parameters!
                        "temperature": params.get("temperature"),
                        "top_p": params.get("top_p"),
                        "max_tokens": params.get("max_tokens"),
                    }
                )

                # Handle response...

        tasks = [query_model(m) for m in models]
        return await asyncio.gather(*tasks)
```

### Filter: `council_evaluation_prompt.py`

```python
"""
Council Evaluation Prompt Filter
User-editable evaluation instructions (Inlet)
"""

class Filter:
    class Valves(BaseModel):
        EVALUATION_RUBRIC: str = Field(
            default="""You are participating in a blind peer review of AI responses.

Evaluate the following anonymous response on these criteria (1-10 scale):

1. **Accuracy**: Factual correctness and precision
2. **Clarity**: Clear, understandable explanation
3. **Completeness**: Thoroughly addresses the question
4. **Relevance**: Stays on-topic and useful

ANONYMOUS RESPONSE:
{response_text}

Provide your evaluation in this exact format:
ACCURACY: [score 1-10]
CLARITY: [score 1-10]
COMPLETENESS: [score 1-10]
RELEVANCE: [score 1-10]
REASONING: [brief explanation]""",
            description="Evaluation prompt template (use {response_text} placeholder)"
        )

        PRIORITY: int = 10  # Run before model query

    def inlet(self, body: dict, __user__: dict = None) -> dict:
        """
        Inject evaluation instructions when in evaluation mode
        """
        # Check if this is an evaluation request (set by orchestrator)
        if body.get("metadata", {}).get("council_mode") == "evaluation":
            response_text = body.get("metadata", {}).get("anonymous_response", "")

            # Format the evaluation rubric with the response
            evaluation_prompt = self.valves.EVALUATION_RUBRIC.format(
                response_text=response_text
            )

            # Replace user message with evaluation prompt
            body["messages"][-1]["content"] = evaluation_prompt

        return body
```

**Key Insight**: Users can edit `EVALUATION_RUBRIC` in the UI to change how models evaluate responses, without touching code!

### Filter: `council_synthesis_prompt.py`

```python
"""
Council Synthesis Prompt Filter
User-editable synthesis instructions (Inlet)
"""

class Filter:
    class Valves(BaseModel):
        SYNTHESIS_PROMPT: str = Field(
            default="""You are synthesizing the best insights from multiple AI responses.

ORIGINAL QUESTION:
{original_question}

TOP-RATED RESPONSES:
{top_responses}

EVALUATION SCORES:
{score_summary}

Your task:
1. Identify the strongest points from each top response
2. Synthesize them into a coherent, comprehensive answer
3. Ensure accuracy and clarity
4. Acknowledge different perspectives if they exist

Provide a synthesized response that combines the best elements.""",
            description="Synthesis prompt template"
        )

        PRIORITY: int = 10

    def inlet(self, body: dict, __user__: dict = None) -> dict:
        """
        Inject synthesis instructions
        """
        if body.get("metadata", {}).get("council_mode") == "synthesis":
            # Extract synthesis data from metadata
            original_question = body.get("metadata", {}).get("original_question", "")
            top_responses = body.get("metadata", {}).get("top_responses", "")
            score_summary = body.get("metadata", {}).get("score_summary", "")

            # Format synthesis prompt
            synthesis_prompt = self.valves.SYNTHESIS_PROMPT.format(
                original_question=original_question,
                top_responses=top_responses,
                score_summary=score_summary
            )

            body["messages"][-1]["content"] = synthesis_prompt

        return body
```

### Action: `council_show_details.py`

```python
"""
Council Show Details Action
Interactive button to reveal individual responses and scores
"""

class Action:
    class Valves(BaseModel):
        pass

    async def action(
        self,
        body: dict,
        __user__: dict = None,
        __event_emitter__ = None,
    ):
        """
        Show detailed Council information
        """
        # Extract Council metadata from message
        metadata = body.get("metadata", {}).get("council_data", {})

        if not metadata:
            return {
                "content": "⚠️ No Council data available for this message."
            }

        # Build detailed output
        details = "# 🏛️ Council of LLMs - Detailed Results\n\n"

        details += "## Individual Responses\n\n"
        for resp in metadata.get("responses", []):
            details += f"### {resp['anonymous_id']} (Score: {resp['avg_score']})\n"
            details += f"{resp['content']}\n\n"

        details += "## Evaluation Scores\n\n"
        for resp_id, scores in metadata.get("scores", {}).items():
            details += f"### {resp_id}\n"
            details += f"- Accuracy: {scores['accuracy']}\n"
            details += f"- Clarity: {scores['clarity']}\n"
            details += f"- Completeness: {scores['completeness']}\n"
            details += f"- Relevance: {scores['relevance']}\n\n"

        return {"content": details}
```

## Per-Model Parameter Configuration

### Configuration Approach

**Option 1: JSON in Valves** (Simplest for now)
```python
MODEL_PARAMS_JSON: str = Field(
    default='{"gpt-4": {"temperature": 0.7, "top_p": 0.9}, "claude-3-opus": {"temperature": 0.5}}',
    description="Per-model parameters as JSON"
)
```

**Option 2: Individual Valves per Model** (More UI-friendly, implement later)
```python
GPT4_TEMPERATURE: float = 0.7
GPT4_TOP_P: float = 0.9
GPT4_MAX_TOKENS: int = 2048

CLAUDE_TEMPERATURE: float = 0.5
CLAUDE_TOP_P: float = 1.0
# etc.
```

**Option 3: Dynamic Valves** (Most advanced, future enhancement)
- Dynamically generate valves based on selected models
- Requires custom UI integration

### Parameters to Support

Based on OpenAI API (and compatible endpoints):

```python
{
    "temperature": float,      # 0-2, default 0.7
    "top_p": float,           # 0-1, default 1.0
    "max_tokens": int,        # Model-specific max
    "frequency_penalty": float, # -2 to 2, default 0
    "presence_penalty": float,  # -2 to 2, default 0
    "stop": List[str],         # Stop sequences
}
```

**For Council, prioritize**:
- `temperature`: Control randomness/creativity
- `top_p`: Nucleus sampling
- `max_tokens`: Response length control

## Benefits of This Hybrid Architecture

### 1. **User-Editable Prompts** ⭐ MAJOR
- Evaluation rubric editable in UI
- Synthesis instructions editable in UI
- No code changes needed to refine prompts
- A/B testing different prompt strategies becomes trivial

### 2. **Modular & Composable**
- Each filter can be enabled/disabled independently
- Users can add their own filters to the pipeline
- Filters can be reused across different Council configurations

### 3. **Interactive User Experience**
- Actions provide buttons for exploration
- Users can drill down into details on demand
- Real-time feedback via event emitters

### 4. **Per-Model Fine-Tuning**
- Different temperature for creative vs. analytical models
- Adjust max_tokens for verbose vs. concise models
- Optimize each model for its strengths

### 5. **Flexible & Extensible**
- Easy to add new filters (e.g., "Translation Filter", "Formatting Filter")
- Easy to add new actions (e.g., "Export to PDF", "Save to Knowledge Base")
- Community can contribute filters/actions

## Implementation Phases (Revised)

### Phase 2.1: Core Pipe (Simplified)
- ✅ Main orchestrator pipe
- ✅ Query distribution (with per-model params)
- ✅ Anonymization
- ✅ Basic synthesis

### Phase 2.2: Filter Integration ⭐ NEW
- ✅ Evaluation prompt filter (user-editable!)
- ✅ Synthesis prompt filter (user-editable!)
- ✅ Score extraction filter (outlet)
- ✅ Output formatting filter (outlet)

### Phase 2.3: Action Integration ⭐ NEW
- ✅ "Show Details" action
- ✅ "Re-evaluate" action
- ✅ "Adjust Criteria" action

### Phase 3: Configuration & Testing
- ✅ Per-model parameter support
- ✅ Test with multiple models
- ✅ Refine default prompts
- ✅ Documentation

## Hermeneutic Insight (Deepened)

**Previous Understanding**:
- Council extends Open WebUI via Pipelines API

**Current Understanding**:
- Council **is natively integrated** into Open WebUI's plugin ecosystem
- It uses **all three plugin types** (Pipes, Filters, Actions) in harmony
- Each plugin type serves the whole (Council) while remaining modular

**The Whole**:
- Not just a pipeline, but a complete ecosystem integration
- Leverages Open WebUI's full capabilities organically

**The Parts**:
- Pipe: Orchestration
- Filters: User-configurable processing steps
- Actions: Interactive user controls

**The Interplay**:
- Parts communicate via Open WebUI's native mechanisms (metadata, body)
- Users can customize each part independently
- System remains coherent despite modularity
- This is **true native integration**, not just API usage

## Next Steps

1. ✅ Design filter prompts (evaluation, synthesis)
2. ✅ Implement per-model parameter support in orchestrator
3. ✅ Create evaluation prompt filter
4. ✅ Create synthesis prompt filter
5. ✅ Create "Show Details" action
6. ✅ Test filter editing in UI
7. ✅ Document for users

---

**Key Takeaway**: By leveraging **Pipes + Filters + Actions**, we create a truly native Open WebUI experience where users can customize prompts, configure parameters per-model, and interact with results—all without touching code. This is the ultimate expression of the hermeneutic circle: understanding Open WebUI's full ecosystem (the whole) reveals a dramatically better architecture for Council (the parts).
