"""
title: Council Show Details Action
author: chmodxheart
author_url: https://github.com/chmodxheart
funding_url: https://github.com/chmodxheart
version: 0.1.0
description: Interactive button to reveal Council session details and de-anonymization

Council of LLMs - Show Details Action

This action function creates an interactive button that reveals detailed
information about a Council session when clicked.

Key Features:
- Shows individual model responses with rankings
- Displays evaluation scores breakdown
- Reveals which models produced which responses (de-anonymization)
- Shows evaluation reasoning (optional)
- Formats output in clean Markdown

Users can click this action button beneath any Council response to see
the full details of how the answer was synthesized.
"""

from pydantic import BaseModel, Field
from typing import Optional

# Import Council data structures

# ============================================================================
# INLINED SCHEMAS (from schemas.py)
# ============================================================================


from pydantic import BaseModel, Field, validator
from typing import Dict, List, Optional, Any, Literal, Union
from datetime import datetime
from enum import Enum
import uuid


# ============================================================================
# ENUMS & CONSTANTS
# ============================================================================

class CouncilMode(str, Enum):
    """
    Operating modes for Council components
    Used in metadata to signal which phase of processing is active
    """
    INITIAL_QUERY = "initial_query"      # User's original query
    EVALUATION = "evaluation"             # Evaluating anonymous responses
    SYNTHESIS = "synthesis"               # Synthesizing final answer
    COMPLETE = "complete"                 # Final output ready


class EvaluationCriterion(str, Enum):
    """
    Standard evaluation criteria
    Extensible for custom criteria in future versions
    """
    ACCURACY = "accuracy"
    CLARITY = "clarity"
    COMPLETENESS = "completeness"
    RELEVANCE = "relevance"


# ============================================================================
# MODEL RESPONSE STRUCTURES
# ============================================================================

class ModelParameters(BaseModel):
    """
    Parameters for individual model queries
    Allows per-model customization of behavior
    """
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Sampling temperature (0.0 = deterministic, 2.0 = very random)"
    )

    top_p: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Nucleus sampling threshold"
    )

    max_tokens: int = Field(
        default=2048,
        ge=1,
        description="Maximum tokens to generate"
    )

    frequency_penalty: Optional[float] = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Penalty for token frequency"
    )

    presence_penalty: Optional[float] = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="Penalty for token presence"
    )

    stop: Optional[List[str]] = Field(
        default=None,
        description="Stop sequences"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "temperature": 0.7,
                "top_p": 0.9,
                "max_tokens": 2048
            }
        }


class ModelResponse(BaseModel):
    """
    Response from a single model

    Includes both the content and metadata about the query/response
    """
    model_id: str = Field(
        ...,
        description="Model identifier (e.g., 'gpt-4', 'claude-3-opus')"
    )

    anonymous_id: str = Field(
        default_factory=lambda: f"response_{uuid.uuid4().hex[:8]}",
        description="Anonymous identifier for peer evaluation"
    )

    content: str = Field(
        ...,
        description="The model's response text"
    )

    success: bool = Field(
        default=True,
        description="Whether the query succeeded"
    )

    error: Optional[str] = Field(
        default=None,
        description="Error message if query failed"
    )

    # Metadata
    tokens_used: Optional[int] = Field(
        default=None,
        description="Total tokens used (prompt + completion)"
    )

    latency_ms: Optional[float] = Field(
        default=None,
        description="Response latency in milliseconds"
    )

    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the response was received"
    )

    parameters: Optional[ModelParameters] = Field(
        default=None,
        description="Parameters used for this query"
    )

    # Verbalized Sampling Support
    response_index: Optional[int] = Field(
        default=None,
        description="Response variant index (1-N) for verbalized sampling. None for single responses."
    )

    probability: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Probability score from verbalized sampling (0.0-1.0). None for single responses."
    )

    # Additional metadata (e.g., finish_reason, input/output token breakdown)
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional metadata about the response (finish_reason, token breakdown, etc.)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "model_id": "gpt-4",
                "anonymous_id": "response_a3f2b1c4",
                "content": "Quantum entanglement is a phenomenon...",
                "success": True,
                "tokens_used": 256,
                "latency_ms": 1234.5,
                "parameters": {
                    "temperature": 0.7,
                    "top_p": 0.9
                }
            }
        }


class AnonymousResponseMapping(BaseModel):
    """
    Bidirectional mapping between model IDs and anonymous IDs

    Used to track which model produced which response while
    maintaining anonymity during evaluation

    Supports both single responses (model -> anonymous_id) and multiple
    responses per model (model -> list of anonymous_ids) for verbalized sampling
    """
    model_to_anonymous: Dict[str, Union[str, List[str]]] = Field(
        default_factory=dict,
        description="Map: model_id -> anonymous_id (single) or List[anonymous_id] (multiple for verbalized sampling)"
    )

    anonymous_to_model: Dict[str, str] = Field(
        default_factory=dict,
        description="Map: anonymous_id -> model_id (always 1:1)"
    )

    def add_mapping(self, model_id: str, anonymous_id: str) -> None:
        """Add a bidirectional mapping for a single response"""
        self.model_to_anonymous[model_id] = anonymous_id
        self.anonymous_to_model[anonymous_id] = model_id

    def add_multi_mapping(self, model_id: str, anonymous_ids: List[str]) -> None:
        """Add mapping for multiple responses from same model (verbalized sampling)"""
        self.model_to_anonymous[model_id] = anonymous_ids
        for anon_id in anonymous_ids:
            self.anonymous_to_model[anon_id] = model_id

    def get_model_id(self, anonymous_id: str) -> Optional[str]:
        """Get model ID from anonymous ID"""
        return self.anonymous_to_model.get(anonymous_id)

    def get_anonymous_id(self, model_id: str) -> Optional[Union[str, List[str]]]:
        """Get anonymous ID(s) from model ID. Returns single string or list depending on mapping."""
        return self.model_to_anonymous.get(model_id)

    def reveal(self, anonymous_id: str) -> Optional[str]:
        """Reveal which model produced an anonymous response"""
        return self.get_model_id(anonymous_id)


# ============================================================================
# EVALUATION STRUCTURES
# ============================================================================

class EvaluationScores(BaseModel):
    """
    Scores for a single response across all criteria
    """
    accuracy: float = Field(
        ...,
        ge=0.0,
        le=10.0,
        description="Accuracy score (0-10)"
    )

    clarity: float = Field(
        ...,
        ge=0.0,
        le=10.0,
        description="Clarity score (0-10)"
    )

    completeness: float = Field(
        ...,
        ge=0.0,
        le=10.0,
        description="Completeness score (0-10)"
    )

    relevance: float = Field(
        ...,
        ge=0.0,
        le=10.0,
        description="Relevance score (0-10)"
    )

    def weighted_total(self, weights: Dict[str, float]) -> float:
        """
        Calculate weighted total score

        Args:
            weights: Dict mapping criterion name to weight (should sum to 1.0)

        Returns:
            Weighted score (0-10 scale)
        """
        total = (
            self.accuracy * weights.get("accuracy", 0.25) +
            self.clarity * weights.get("clarity", 0.25) +
            self.completeness * weights.get("completeness", 0.25) +
            self.relevance * weights.get("relevance", 0.25)
        )
        return total

    def average(self) -> float:
        """Calculate simple average across all criteria"""
        return (self.accuracy + self.clarity + self.completeness + self.relevance) / 4.0

    class Config:
        json_schema_extra = {
            "example": {
                "accuracy": 8.5,
                "clarity": 9.0,
                "completeness": 7.5,
                "relevance": 8.0
            }
        }


class CreativeWritingScores(BaseModel):
    """
    Scores for creative writing evaluation across 6 criteria
    Used by Writer's Room instead of standard EvaluationScores
    """
    voice_authenticity: float = Field(
        ...,
        ge=0.0,
        le=10.0,
        description="Voice authenticity score - human-like voice, avoids LLM artifacts (0-10)"
    )

    emotional_resonance: float = Field(
        ...,
        ge=0.0,
        le=10.0,
        description="Emotional resonance score - shows emotions through action/detail (0-10)"
    )

    originality: float = Field(
        ...,
        ge=0.0,
        le=10.0,
        description="Originality score - fresh metaphors, avoids clichés (0-10)"
    )

    style_consistency: float = Field(
        ...,
        ge=0.0,
        le=10.0,
        description="Style consistency score - maintains unified voice (0-10)"
    )

    narrative_coherence: float = Field(
        ...,
        ge=0.0,
        le=10.0,
        description="Narrative coherence score - clear structure and flow (0-10)"
    )

    llm_artifact_avoidance: float = Field(
        ...,
        ge=0.0,
        le=10.0,
        description="LLM artifact avoidance score - explicitly penalizes AI-sounding patterns (0-10)"
    )

    def weighted_total(self, weights: Dict[str, float]) -> float:
        """
        Calculate weighted total score

        Args:
            weights: Dict mapping criterion name to weight (should sum to 1.0)

        Returns:
            Weighted score (0-10 scale)
        """
        total = (
            self.voice_authenticity * weights.get("voice_authenticity", 0.25) +
            self.emotional_resonance * weights.get("emotional_resonance", 0.20) +
            self.originality * weights.get("originality", 0.20) +
            self.style_consistency * weights.get("style_consistency", 0.15) +
            self.narrative_coherence * weights.get("narrative_coherence", 0.15) +
            self.llm_artifact_avoidance * weights.get("llm_artifact_avoidance", 0.05)
        )
        return total

    def average(self) -> float:
        """Calculate simple average across all criteria"""
        return (
            self.voice_authenticity +
            self.emotional_resonance +
            self.originality +
            self.style_consistency +
            self.narrative_coherence +
            self.llm_artifact_avoidance
        ) / 6.0

    class Config:
        json_schema_extra = {
            "example": {
                "voice_authenticity": 8.5,
                "emotional_resonance": 9.0,
                "originality": 7.5,
                "style_consistency": 8.0,
                "narrative_coherence": 8.5,
                "llm_artifact_avoidance": 7.0
            }
        }


class Evaluation(BaseModel):
    """
    Single evaluation of one response by one model
    Supports both standard (EvaluationScores) and creative writing (CreativeWritingScores) scoring
    """
    evaluator_model_id: str = Field(
        ...,
        description="Model that performed the evaluation"
    )

    target_anonymous_id: str = Field(
        ...,
        description="Anonymous ID of the response being evaluated"
    )

    scores: Union[EvaluationScores, 'CreativeWritingScores'] = Field(
        ...,
        description="Scores across all criteria (supports both EvaluationScores and CreativeWritingScores)"
    )

    reasoning: Optional[str] = Field(
        default=None,
        description="Evaluator's reasoning for the scores"
    )

    raw_response: Optional[str] = Field(
        default=None,
        description="Raw evaluation response text (for debugging)"
    )

    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the evaluation was performed"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "evaluator_model_id": "claude-3-opus",
                "target_anonymous_id": "response_a3f2b1c4",
                "scores": {
                    "accuracy": 8.5,
                    "clarity": 9.0,
                    "completeness": 7.5,
                    "relevance": 8.0
                },
                "reasoning": "Strong technical explanation with clear examples..."
            }
        }


class AggregatedScores(BaseModel):
    """
    Aggregated scores for a single response from all evaluators
    Supports both standard (EvaluationScores) and creative writing (CreativeWritingScores) scoring
    """
    anonymous_id: str = Field(
        ...,
        description="Anonymous ID of the response"
    )

    individual_scores: List[Union[EvaluationScores, 'CreativeWritingScores']] = Field(
        default_factory=list,
        description="All individual scores from different evaluators"
    )

    average_scores: Optional[Union[EvaluationScores, 'CreativeWritingScores']] = Field(
        default=None,
        description="Average across all evaluators"
    )

    weighted_total: Optional[float] = Field(
        default=None,
        description="Weighted total score using configured weights"
    )

    rank: Optional[int] = Field(
        default=None,
        description="Rank among all responses (1 = best)"
    )

    evaluator_count: int = Field(
        default=0,
        description="Number of evaluators who scored this response"
    )

    def calculate_average(self) -> Union[EvaluationScores, 'CreativeWritingScores']:
        """Calculate average scores across all evaluators (supports both score types)"""
        if not self.individual_scores:
            # Return appropriate empty score based on type
            if isinstance(self.individual_scores, list) and len(self.individual_scores) == 0:
                # Default to EvaluationScores for empty list
                return EvaluationScores(
                    accuracy=0.0,
                    clarity=0.0,
                    completeness=0.0,
                    relevance=0.0
                )

        # Detect score type from first element
        first_score = self.individual_scores[0]
        n = len(self.individual_scores)

        if isinstance(first_score, EvaluationScores):
            # Standard 4-criterion evaluation
            return EvaluationScores(
                accuracy=sum(s.accuracy for s in self.individual_scores) / n,
                clarity=sum(s.clarity for s in self.individual_scores) / n,
                completeness=sum(s.completeness for s in self.individual_scores) / n,
                relevance=sum(s.relevance for s in self.individual_scores) / n
            )
        else:
            # Creative writing 6-criterion evaluation (CreativeWritingScores type)
            # Note: We can't directly construct it here due to forward reference,
            # so we need to get the class from the first element's type
            score_type = type(first_score)
            return score_type(
                voice_authenticity=sum(s.voice_authenticity for s in self.individual_scores) / n,
                emotional_resonance=sum(s.emotional_resonance for s in self.individual_scores) / n,
                originality=sum(s.originality for s in self.individual_scores) / n,
                style_consistency=sum(s.style_consistency for s in self.individual_scores) / n,
                narrative_coherence=sum(s.narrative_coherence for s in self.individual_scores) / n,
                llm_artifact_avoidance=sum(s.llm_artifact_avoidance for s in self.individual_scores) / n
            )

    def calculate_weighted_total(self, weights: Dict[str, float]) -> float:
        """Calculate weighted total using average scores"""
        if not self.average_scores:
            self.average_scores = self.calculate_average()
        return self.average_scores.weighted_total(weights)


# ============================================================================
# SYNTHESIS STRUCTURES
# ============================================================================

class SynthesisInput(BaseModel):
    """
    Input data for the synthesis phase
    """
    original_question: str = Field(
        ...,
        description="The user's original question"
    )

    top_responses: List[ModelResponse] = Field(
        ...,
        description="Top-ranked responses to synthesize from"
    )

    scores: Dict[str, AggregatedScores] = Field(
        ...,
        description="Aggregated scores for all responses"
    )

    lead_model_id: str = Field(
        ...,
        description="Model selected to perform synthesis"
    )

    criteria_weights: Dict[str, float] = Field(
        ...,
        description="Weights used for evaluation"
    )


# ============================================================================
# METADATA STRUCTURES
# ============================================================================

class CouncilMetadata(BaseModel):
    """
    Metadata passed through body["metadata"]["council_data"]

    This structure enables communication between:
    - Orchestrator pipe
    - Filter functions
    - Action functions
    """
    mode: CouncilMode = Field(
        default=CouncilMode.INITIAL_QUERY,
        description="Current processing mode"
    )

    session_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        description="Unique session ID for this Council invocation"
    )

    # Query phase data
    models_queried: List[str] = Field(
        default_factory=list,
        description="List of model IDs queried"
    )

    # Response phase data
    responses: List[ModelResponse] = Field(
        default_factory=list,
        description="All model responses"
    )

    anonymous_mapping: Optional[AnonymousResponseMapping] = Field(
        default=None,
        description="Mapping between model IDs and anonymous IDs"
    )

    # Evaluation phase data
    evaluations: List[Evaluation] = Field(
        default_factory=list,
        description="All evaluations"
    )

    aggregated_scores: Dict[str, AggregatedScores] = Field(
        default_factory=dict,
        description="Aggregated scores by anonymous_id"
    )

    # Synthesis phase data
    synthesis_input: Optional[SynthesisInput] = Field(
        default=None,
        description="Input for synthesis phase"
    )

    lead_model_id: Optional[str] = Field(
        default=None,
        description="Model selected for synthesis"
    )

    # Configuration
    criteria_weights: Dict[str, float] = Field(
        default_factory=lambda: {
            "accuracy": 0.3,
            "clarity": 0.25,
            "completeness": 0.25,
            "relevance": 0.2
        },
        description="Evaluation criteria weights"
    )

    # Timing & debugging
    started_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When Council processing started"
    )

    completed_at: Optional[datetime] = Field(
        default=None,
        description="When Council processing completed"
    )

    debug_mode: bool = Field(
        default=False,
        description="Enable debug output"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "mode": "evaluation",
                "session_id": "a1b2c3d4e5f6",
                "models_queried": ["gpt-4", "claude-3-opus", "gemini-pro"],
                "criteria_weights": {
                    "accuracy": 0.3,
                    "clarity": 0.25,
                    "completeness": 0.25,
                    "relevance": 0.2
                }
            }
        }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def create_council_metadata() -> CouncilMetadata:
    """Create a new CouncilMetadata instance with defaults"""
    return CouncilMetadata()


def extract_council_metadata(body: dict) -> Optional[CouncilMetadata]:
    """
    Extract CouncilMetadata from request body

    Args:
        body: Request body dict

    Returns:
        CouncilMetadata instance or None if not present
    """
    metadata = body.get("metadata", {})
    council_data = metadata.get("council_data")

    if council_data is None:
        return None

    try:
        return CouncilMetadata(**council_data)
    except Exception as e:
        print(f"Error parsing CouncilMetadata: {e}")
        return None


def inject_council_metadata(body: dict, council_metadata: CouncilMetadata) -> dict:
    """
    Inject CouncilMetadata into request body

    Args:
        body: Request body dict
        council_metadata: CouncilMetadata to inject

    Returns:
        Modified body with metadata injected
    """
    if "metadata" not in body:
        body["metadata"] = {}

    body["metadata"]["council_data"] = council_metadata.model_dump()

    return body


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    """
    Example usage and validation of data structures
    """
    print("=== Council Data Structures - Examples ===\n")

    # 1. Create model responses
    print("1. Model Responses:")
    response1 = ModelResponse(
        model_id="gpt-4",
        content="Quantum entanglement is a physical phenomenon...",
        tokens_used=150,
        latency_ms=1234.5,
        parameters=ModelParameters(temperature=0.7)
    )
    print(f"   {response1.model_id} -> {response1.anonymous_id}")
    print(f"   Tokens: {response1.tokens_used}, Latency: {response1.latency_ms}ms\n")

    # 2. Anonymous mapping
    print("2. Anonymous Mapping:")
    mapping = AnonymousResponseMapping()
    mapping.add_mapping("gpt-4", response1.anonymous_id)
    mapping.add_mapping("claude-3-opus", "response_xyz789")
    print(f"   Reveal {response1.anonymous_id}: {mapping.reveal(response1.anonymous_id)}\n")

    # 3. Evaluation
    print("3. Evaluation:")
    eval1 = Evaluation(
        evaluator_model_id="claude-3-opus",
        target_anonymous_id=response1.anonymous_id,
        scores=EvaluationScores(
            accuracy=8.5,
            clarity=9.0,
            completeness=7.5,
            relevance=8.0
        ),
        reasoning="Strong technical explanation with clear examples"
    )
    print(f"   Evaluator: {eval1.evaluator_model_id}")
    print(f"   Average Score: {eval1.scores.average():.2f}\n")

    # 4. Aggregated scores
    print("4. Aggregated Scores:")
    agg_scores = AggregatedScores(
        anonymous_id=response1.anonymous_id,
        individual_scores=[eval1.scores]
    )
    avg = agg_scores.calculate_average()
    print(f"   Average: {avg.average():.2f}")
    weights = {"accuracy": 0.3, "clarity": 0.25, "completeness": 0.25, "relevance": 0.2}
    weighted = agg_scores.calculate_weighted_total(weights)
    print(f"   Weighted Total: {weighted:.2f}\n")

    # 5. Council metadata
    print("5. Council Metadata:")
    metadata = create_council_metadata()
    metadata.mode = CouncilMode.EVALUATION
    metadata.models_queried = ["gpt-4", "claude-3-opus", "gemini-pro"]
    metadata.responses = [response1]
    print(f"   Mode: {metadata.mode}")
    print(f"   Session: {metadata.session_id}")
    print(f"   Models: {len(metadata.models_queried)}\n")

    print("✅ All data structures validated successfully!")


# ============================================================================
# MAIN COMPONENT CODE
# ============================================================================

class Action:
    """
    Show Details Action

    Interactive button that reveals Council session details
    """

    class Valves(BaseModel):
        """
        User-configurable options
        """
        SHOW_ANONYMOUS_IDS: bool = Field(
            default=True,
            description="Show anonymous response IDs in output"
        )

        SHOW_MODEL_IDENTITIES: bool = Field(
            default=True,
            description="Reveal which models produced which responses (de-anonymize)"
        )

        SHOW_EVALUATION_REASONING: bool = Field(
            default=False,
            description="Include evaluation reasoning in output"
        )

        SHOW_RESPONSE_CONTENT: bool = Field(
            default=True,
            description="Include full response content from each model"
        )

        SHOW_TIMING_INFO: bool = Field(
            default=True,
            description="Show timing and performance information"
        )

        ENABLE_DEBUG_LOGGING: bool = Field(
            default=False,
            description="Enable debug logging for this action"
        )

    def __init__(self):
        """Initialize the action"""
        self.valves = self.Valves()

    async def action(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__=None,
        __event_call__=None,
    ) -> dict:
        """
        Action execution: Display Council session details

        Args:
            body: Request body containing Council metadata
            __user__: User information
            __event_emitter__: Event emitter for status updates
            __event_call__: Event call for user interactions

        Returns:
            Dict with formatted details content
        """

        if self.valves.ENABLE_DEBUG_LOGGING:
            print("[Council Show Details] Action triggered")

        # Send status update
        if __event_emitter__:
            await __event_emitter__({
                "type": "status",
                "data": {
                    "description": "Loading Council details...",
                    "done": False
                }
            })

        # Extract Council metadata
        metadata = extract_council_metadata(body)

        if not metadata:
            return {
                "content": "**No Council Data Available**\n\nThis message was not generated by the Council of LLMs, or the session data is missing."
            }

        if self.valves.ENABLE_DEBUG_LOGGING:
            print(f"[Council Show Details] Session: {metadata.session_id}")
            print(f"[Council Show Details] Mode: {metadata.mode}")
            print(f"[Council Show Details] Responses: {len(metadata.responses)}")

        # Build detailed output
        output = self._build_details_output(metadata)

        # Send completion status
        if __event_emitter__:
            await __event_emitter__({
                "type": "status",
                "data": {
                    "description": "Details loaded",
                    "done": True
                }
            })

        return {"content": output}

    def _build_details_output(self, metadata) -> str:
        """
        Build formatted details output

        Args:
            metadata: CouncilMetadata object

        Returns:
            Markdown-formatted string with details
        """
        output = "# Council of LLMs - Session Details\n\n"

        # Session info
        output += f"**Session ID**: `{metadata.session_id}`\n"
        output += f"**Status**: {metadata.mode.value}\n"
        output += f"**Models Queried**: {len(metadata.models_queried)}\n"

        if metadata.completed_at and self.valves.SHOW_TIMING_INFO:
            duration = (metadata.completed_at - metadata.started_at).total_seconds()
            output += f"**Duration**: {duration:.2f}s\n"

        output += "\n---\n\n"

        # Individual responses with scores
        output += "## Individual Model Responses\n\n"

        if not metadata.responses:
            output += "*No responses available*\n\n"
        else:
            # Sort by rank
            sorted_responses = sorted(
                metadata.responses,
                key=lambda r: metadata.aggregated_scores.get(r.anonymous_id, type('obj', (), {'rank': 999})).rank
                if metadata.aggregated_scores.get(r.anonymous_id) else 999
            )

            for response in sorted_responses:
                output += self._format_response_detail(response, metadata)

        # Evaluation summary
        if metadata.aggregated_scores:
            output += "\n---\n\n"
            output += "## Evaluation Scores Summary\n\n"
            output += self._format_evaluation_summary(metadata)

        # Configuration
        output += "\n---\n\n"
        output += "## Configuration\n\n"
        output += self._format_configuration(metadata)

        return output

    def _format_response_detail(self, response, metadata) -> str:
        """
        Format a single response with its details

        Args:
            response: ModelResponse object
            metadata: CouncilMetadata object

        Returns:
            Formatted string for this response
        """
        output = ""

        # Get aggregated scores
        agg_scores = metadata.aggregated_scores.get(response.anonymous_id)

        # Header with rank
        if agg_scores and agg_scores.rank:
            output += f"### Rank #{agg_scores.rank}"
        else:
            output += f"### Response"

        # Anonymous ID (if enabled)
        if self.valves.SHOW_ANONYMOUS_IDS:
            output += f" ({response.anonymous_id})"

        # Reveal model identity (if enabled)
        if self.valves.SHOW_MODEL_IDENTITIES:
            output += f" - **{response.model_id}**"

        output += "\n\n"

        # Scores
        if agg_scores and agg_scores.average_scores:
            avg = agg_scores.average_scores
            output += f"**Scores**: "
            output += f"Accuracy: {avg.accuracy:.1f}/10, "
            output += f"Clarity: {avg.clarity:.1f}/10, "
            output += f"Completeness: {avg.completeness:.1f}/10, "
            output += f"Relevance: {avg.relevance:.1f}/10\n\n"
            output += f"**Weighted Total**: {agg_scores.weighted_total:.2f}/10 "
            output += f"(from {agg_scores.evaluator_count} evaluators)\n\n"

        # Performance metrics
        if response.tokens_used or response.latency_ms:
            output += "**Performance**: "
            if response.tokens_used:
                output += f"{response.tokens_used} tokens"
            if response.latency_ms:
                if response.tokens_used:
                    output += ", "
                output += f"{response.latency_ms:.0f}ms latency"
            output += "\n\n"

        # Response content (if enabled)
        if self.valves.SHOW_RESPONSE_CONTENT and response.content:
            output += "**Response**:\n\n"
            output += f"> {response.content}\n\n"

        # Error info (if failed)
        if not response.success and response.error:
            output += f"**Error**: {response.error}\n\n"

        output += "---\n\n"

        return output

    def _format_evaluation_summary(self, metadata) -> str:
        """
        Format evaluation scores summary

        Args:
            metadata: CouncilMetadata object

        Returns:
            Formatted evaluation summary
        """
        output = ""

        # Sort by rank
        sorted_scores = sorted(
            metadata.aggregated_scores.items(),
            key=lambda x: x[1].rank if x[1].rank else 999
        )

        output += "| Rank | Response | Accuracy | Clarity | Completeness | Relevance | Total |\n"
        output += "|------|----------|----------|---------|--------------|-----------|-------|\n"

        for anonymous_id, agg in sorted_scores:
            if not agg.average_scores:
                continue

            avg = agg.average_scores

            # Get response for model ID
            response = next((r for r in metadata.responses if r.anonymous_id == anonymous_id), None)
            model_display = response.model_id if (response and self.valves.SHOW_MODEL_IDENTITIES) else anonymous_id

            output += f"| {agg.rank} | {model_display} | "
            output += f"{avg.accuracy:.1f} | {avg.clarity:.1f} | "
            output += f"{avg.completeness:.1f} | {avg.relevance:.1f} | "
            output += f"**{agg.weighted_total:.2f}** |\n"

        output += "\n"

        # Show weights
        output += "**Evaluation Weights**: "
        weights = metadata.criteria_weights
        output += f"Accuracy: {weights.get('accuracy', 0):.0%}, "
        output += f"Clarity: {weights.get('clarity', 0):.0%}, "
        output += f"Completeness: {weights.get('completeness', 0):.0%}, "
        output += f"Relevance: {weights.get('relevance', 0):.0%}\n\n"

        # Show reasoning (if enabled)
        if self.valves.SHOW_EVALUATION_REASONING and metadata.evaluations:
            output += "\n### Evaluation Reasoning\n\n"
            # Show a sample of reasoning from evaluations
            for i, evaluation in enumerate(metadata.evaluations[:5]):  # Limit to 5
                if evaluation.reasoning:
                    output += f"- **{evaluation.evaluator_model_id}** on **{evaluation.target_anonymous_id}**: "
                    output += f"{evaluation.reasoning}\n"

        return output

    def _format_configuration(self, metadata) -> str:
        """
        Format configuration information

        Args:
            metadata: CouncilMetadata object

        Returns:
            Formatted configuration
        """
        output = ""

        output += f"**Models Queried**: {', '.join(metadata.models_queried)}\n\n"

        if metadata.lead_model_id:
            output += f"**Lead Synthesizer**: {metadata.lead_model_id}\n\n"

        if metadata.synthesis_input:
            output += f"**Top Responses Used for Synthesis**: {len(metadata.synthesis_input.top_responses)}\n\n"

        return output


# Module metadata
__version__ = "0.1.0"
__author__ = "Council Pipeline Team"
__description__ = "Show Details action with customizable display options"
