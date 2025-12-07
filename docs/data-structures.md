# Council of LLMs - Data Structures Reference

**File**: `council-pipeline/schemas.py`
**Purpose**: Core data structures for the entire Council system

## Overview

The Council system uses Pydantic models for type-safe, validated data structures that are shared across:
- **Orchestrator Pipe**: Main workflow controller
- **Filter Functions**: Evaluation and synthesis prompts
- **Action Functions**: Interactive UI components

All data structures are designed for easy serialization and passing through Open WebUI's metadata system.

## Core Components

### 1. Enums & Constants

#### CouncilMode
```python
class CouncilMode(str, Enum):
    INITIAL_QUERY = "initial_query"   # User's original query
    EVALUATION = "evaluation"          # Evaluating anonymous responses
    SYNTHESIS = "synthesis"            # Synthesizing final answer
    COMPLETE = "complete"              # Final output ready
```

**Usage**: Signals which phase of processing is active. Filters check this to determine behavior.

#### EvaluationCriterion
```python
class EvaluationCriterion(str, Enum):
    ACCURACY = "accuracy"
    CLARITY = "clarity"
    COMPLETENESS = "completeness"
    RELEVANCE = "relevance"
```

**Usage**: Standard evaluation criteria. Extensible for future custom criteria.

---

## 2. Model Response Structures

### ModelParameters
```python
class ModelParameters(BaseModel):
    temperature: float = 0.7        # 0.0-2.0
    top_p: float = 1.0             # 0.0-1.0
    max_tokens: int = 2048         # >= 1
    frequency_penalty: float = 0.0  # -2.0 to 2.0
    presence_penalty: float = 0.0   # -2.0 to 2.0
    stop: Optional[List[str]] = None
```

**Purpose**: Per-model query parameters
**Used by**: Orchestrator when querying models via Open WebUI API

**Example**:
```python
params = ModelParameters(
    temperature=0.5,  # Less random for analytical model
    top_p=0.9,
    max_tokens=2048
)
```

### ModelResponse
```python
class ModelResponse(BaseModel):
    model_id: str                   # e.g., "gpt-4"
    anonymous_id: str               # Auto-generated: "response_a3f2b1c4"
    content: str                    # Response text
    success: bool                   # Query succeeded?
    error: Optional[str]            # Error message if failed
    tokens_used: Optional[int]      # Total tokens
    latency_ms: Optional[float]     # Response time
    timestamp: datetime             # When received
    parameters: Optional[ModelParameters]  # Params used
```

**Purpose**: Complete response from a single model
**Used by**: Orchestrator (storage), Filters (processing), Actions (display)

**Key Feature**: `anonymous_id` is auto-generated for blind evaluation

**Example**:
```python
response = ModelResponse(
    model_id="gpt-4",
    content="Quantum entanglement is...",
    tokens_used=256,
    latency_ms=1234.5
)
# anonymous_id automatically assigned: "response_5ea49052"
```

### AnonymousResponseMapping
```python
class AnonymousResponseMapping(BaseModel):
    model_to_anonymous: Dict[str, str]
    anonymous_to_model: Dict[str, str]

    def add_mapping(model_id: str, anonymous_id: str)
    def get_model_id(anonymous_id: str) -> Optional[str]
    def get_anonymous_id(model_id: str) -> Optional[str]
    def reveal(anonymous_id: str) -> Optional[str]
```

**Purpose**: Bidirectional mapping for anonymization
**Used by**: Orchestrator (tracking), Actions (reveal original models)

**Example**:
```python
mapping = AnonymousResponseMapping()
mapping.add_mapping("gpt-4", "response_abc123")
mapping.add_mapping("claude-3-opus", "response_xyz789")

# Reveal which model produced a response
original = mapping.reveal("response_abc123")  # Returns "gpt-4"
```

---

## 3. Evaluation Structures

### EvaluationScores
```python
class EvaluationScores(BaseModel):
    accuracy: float       # 0.0-10.0
    clarity: float        # 0.0-10.0
    completeness: float   # 0.0-10.0
    relevance: float      # 0.0-10.0

    def weighted_total(weights: Dict[str, float]) -> float
    def average() -> float
```

**Purpose**: Scores for a single response on all criteria
**Used by**: Evaluation filter (parsing), Aggregation (calculation)

**Methods**:
- `weighted_total(weights)`: Calculate weighted score using custom weights
- `average()`: Simple average across all criteria

**Example**:
```python
scores = EvaluationScores(
    accuracy=8.5,
    clarity=9.0,
    completeness=7.5,
    relevance=8.0
)

# Simple average
avg = scores.average()  # 8.25

# Weighted (30% accuracy, 25% others)
weights = {"accuracy": 0.3, "clarity": 0.25, "completeness": 0.25, "relevance": 0.2}
weighted = scores.weighted_total(weights)  # 8.28
```

### Evaluation
```python
class Evaluation(BaseModel):
    evaluator_model_id: str         # Who evaluated
    target_anonymous_id: str        # What was evaluated
    scores: EvaluationScores        # The scores
    reasoning: Optional[str]        # Why these scores
    raw_response: Optional[str]     # Raw text (debugging)
    timestamp: datetime             # When evaluated
```

**Purpose**: Single evaluation of one response by one model
**Used by**: Orchestrator (collection), Aggregation (combining)

**Example**:
```python
evaluation = Evaluation(
    evaluator_model_id="claude-3-opus",
    target_anonymous_id="response_abc123",
    scores=EvaluationScores(
        accuracy=8.5,
        clarity=9.0,
        completeness=7.5,
        relevance=8.0
    ),
    reasoning="Strong technical explanation with clear examples"
)
```

### AggregatedScores
```python
class AggregatedScores(BaseModel):
    anonymous_id: str
    individual_scores: List[EvaluationScores]
    average_scores: Optional[EvaluationScores]
    weighted_total: Optional[float]
    rank: Optional[int]               # 1 = best
    evaluator_count: int

    def calculate_average() -> EvaluationScores
    def calculate_weighted_total(weights: Dict[str, float]) -> float
```

**Purpose**: Aggregated scores for a response from ALL evaluators
**Used by**: Orchestrator (ranking), Synthesis (input), Actions (display)

**Example**:
```python
# Collect scores from multiple evaluators
agg = AggregatedScores(
    anonymous_id="response_abc123",
    individual_scores=[scores1, scores2, scores3]
)

# Calculate average across evaluators
avg = agg.calculate_average()

# Calculate weighted total
weights = {"accuracy": 0.3, "clarity": 0.25, "completeness": 0.25, "relevance": 0.2}
total = agg.calculate_weighted_total(weights)

# Assign rank
agg.rank = 1  # Best response
```

---

## 4. Synthesis Structures

### SynthesisInput
```python
class SynthesisInput(BaseModel):
    original_question: str
    top_responses: List[ModelResponse]
    scores: Dict[str, AggregatedScores]
    lead_model_id: str
    criteria_weights: Dict[str, float]
```

**Purpose**: Input data for synthesis phase
**Used by**: Synthesis filter (prompt construction), Orchestrator (preparation)

**Example**:
```python
synthesis = SynthesisInput(
    original_question="What is quantum entanglement?",
    top_responses=[response1, response2],  # Top 2 responses
    scores={"response_abc123": agg_scores1, ...},
    lead_model_id="gpt-4",
    criteria_weights={"accuracy": 0.3, ...}
)
```

---

## 5. Metadata Structures

### CouncilMetadata
```python
class CouncilMetadata(BaseModel):
    # State
    mode: CouncilMode
    session_id: str  # Unique per invocation

    # Query phase
    models_queried: List[str]

    # Response phase
    responses: List[ModelResponse]
    anonymous_mapping: Optional[AnonymousResponseMapping]

    # Evaluation phase
    evaluations: List[Evaluation]
    aggregated_scores: Dict[str, AggregatedScores]

    # Synthesis phase
    synthesis_input: Optional[SynthesisInput]
    lead_model_id: Optional[str]

    # Configuration
    criteria_weights: Dict[str, float]

    # Timing
    started_at: datetime
    completed_at: Optional[datetime]
    debug_mode: bool
```

**Purpose**: Complete Council session state passed through metadata
**Used by**: ALL components (orchestrator, filters, actions)

**Where it lives**: `body["metadata"]["council_data"]`

**Example**:
```python
# Create new session
metadata = create_council_metadata()
metadata.mode = CouncilMode.EVALUATION
metadata.models_queried = ["gpt-4", "claude-3-opus"]

# Inject into request body
body = inject_council_metadata(body, metadata)

# Extract in filter/action
metadata = extract_council_metadata(body)
if metadata and metadata.mode == CouncilMode.EVALUATION:
    # Add evaluation instructions
    ...
```

---

## Helper Functions

### create_council_metadata()
```python
def create_council_metadata() -> CouncilMetadata
```
Creates a new CouncilMetadata with defaults.

### extract_council_metadata(body)
```python
def extract_council_metadata(body: dict) -> Optional[CouncilMetadata]
```
Extracts CouncilMetadata from `body["metadata"]["council_data"]`.
Returns None if not present.

### inject_council_metadata(body, council_metadata)
```python
def inject_council_metadata(
    body: dict,
    council_metadata: CouncilMetadata
) -> dict
```
Injects CouncilMetadata into `body["metadata"]["council_data"]`.

---

## Usage Patterns

### Pattern 1: Orchestrator Creating Session
```python
# Create new Council session
metadata = create_council_metadata()
metadata.mode = CouncilMode.INITIAL_QUERY
metadata.models_queried = ["gpt-4", "claude-3-opus", "gemini-pro"]

# Query models...
for model_id in metadata.models_queried:
    response = await query_model(model_id, messages)
    metadata.responses.append(response)

# Create anonymous mapping
metadata.anonymous_mapping = AnonymousResponseMapping()
for resp in metadata.responses:
    metadata.anonymous_mapping.add_mapping(resp.model_id, resp.anonymous_id)
```

### Pattern 2: Filter Checking Mode
```python
def inlet(self, body: dict, __user__: dict = None) -> dict:
    # Extract metadata
    metadata = extract_council_metadata(body)

    if metadata and metadata.mode == CouncilMode.EVALUATION:
        # Add evaluation instructions
        evaluation_prompt = self.valves.EVALUATION_RUBRIC.format(
            response_text=body["metadata"]["anonymous_response"]
        )
        body["messages"][-1]["content"] = evaluation_prompt

    return body
```

### Pattern 3: Action Displaying Results
```python
async def action(self, body: dict, __user__: dict = None):
    # Extract metadata
    metadata = extract_council_metadata(body)

    if not metadata:
        return {"content": "No Council data available"}

    # Build detailed output
    details = "# Council Results\n\n"

    for resp in metadata.responses:
        agg_scores = metadata.aggregated_scores.get(resp.anonymous_id)
        details += f"## {resp.anonymous_id}\n"
        details += f"Average Score: {agg_scores.average_scores.average():.2f}\n"
        details += f"Rank: {agg_scores.rank}\n\n"

    return {"content": details}
```

---

## Data Flow Through Council

```
1. User Query
   └─> CouncilMetadata created (mode: INITIAL_QUERY)

2. Query Distribution
   └─> ModelResponse objects created
   └─> AnonymousResponseMapping created
   └─> Metadata updated with responses

3. Evaluation
   └─> mode: EVALUATION
   └─> Evaluation objects created for each model×response
   └─> Metadata updated with evaluations

4. Aggregation
   └─> AggregatedScores calculated
   └─> Responses ranked
   └─> Metadata updated with aggregated_scores

5. Synthesis
   └─> mode: SYNTHESIS
   └─> SynthesisInput created
   └─> Lead model generates final answer
   └─> Metadata updated (mode: COMPLETE)

6. User receives final answer
   └─> Action can reveal details from metadata
```

---

## Type Safety Benefits

All structures use Pydantic for:
- ✅ **Automatic validation** (e.g., scores must be 0-10)
- ✅ **Type checking** (IDE autocomplete)
- ✅ **Easy serialization** (`.model_dump()` for JSON)
- ✅ **Clear documentation** (Field descriptions)
- ✅ **Default values** (sensible defaults)

---

## Testing

Run the validation examples:
```bash
cd council-pipeline
python schemas.py
```

Expected output:
```
=== Council Data Structures - Examples ===

1. Model Responses:
   gpt-4 -> response_5ea49052
   Tokens: 150, Latency: 1234.5ms

2. Anonymous Mapping:
   Reveal response_5ea49052: gpt-4

3. Evaluation:
   Evaluator: claude-3-opus
   Average Score: 8.25

4. Aggregated Scores:
   Average: 8.25
   Weighted Total: 8.28

5. Council Metadata:
   Mode: CouncilMode.EVALUATION
   Session: ade7e2b1de5b4ff18dba8b324c179c5d
   Models: 3

All data structures validated successfully!
```

---

## Next Steps

With data structures defined, we can now:
1. ✅ Implement orchestrator pipe (uses ModelResponse, CouncilMetadata)
2. ✅ Create filters (read/write CouncilMetadata)
3. ✅ Build actions (display data from CouncilMetadata)

All components share these type-safe structures for seamless integration!
