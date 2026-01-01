"""
title: Council Synthesis Filter
author: chmodxheart
author_url: https://github.com/chmodxheart
funding_url: https://github.com/chmodxheart
version: 0.1.0
description: Injects user-editable synthesis instructions for lead model

Council of LLMs - Synthesis Prompt Filter

This inlet filter injects user-customizable synthesis instructions when
the Council orchestrator is in synthesis mode.

Key Features:
- User-editable synthesis template via Valves (editable in UI!)
- Multiple placeholder support: {original_question}, {top_responses}, {score_summary}
- Detects synthesis mode via CouncilMetadata
- Formats top responses with scores

Users can customize how the lead model synthesizes responses without
touching code - just edit in Open WebUI Admin Panel!
"""

from pydantic import BaseModel, Field
from typing import Optional

# Import Council data structures

# ============================================================================
# INLINED SCHEMAS (from schemas.py)
# ============================================================================


from pydantic import BaseModel, Field, validator, ConfigDict
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
        default=0,
        ge=0,
        description="Maximum tokens to generate (0 = no limit)"
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
        description="Probability score from verbalized sampling (0.0-1.0). None for single responses. Note: Constraints removed for JSON schema compatibility."
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
# STRUCTURED OUTPUT SCHEMAS
# ============================================================================

class StandardEvaluationResponse(BaseModel):
    """
    Structured evaluation response for standard Council evaluation
    Contains EvaluationScores (4 criteria) and reasoning
    """
    model_config = ConfigDict(extra='forbid')

    scores: EvaluationScores = Field(
        ...,
        description="Evaluation scores: accuracy, clarity, completeness, relevance (0-10)"
    )

    reasoning: str = Field(
        ...,
        description="Detailed reasoning for the scores provided"
    )


class CreativeEvaluationResponse(BaseModel):
    """
    Structured evaluation response for Writer's Room evaluation
    Contains CreativeWritingScores (6 criteria) and reasoning
    """
    model_config = ConfigDict(extra='forbid')

    scores: CreativeWritingScores = Field(
        ...,
        description="Creative writing scores: voice_authenticity, emotional_resonance, originality, style_consistency, narrative_coherence, llm_artifact_avoidance (0-10)"
    )

    reasoning: str = Field(
        ...,
        description="Detailed reasoning for the scores provided"
    )


class SingleStandardEvaluation(BaseModel):
    """
    Single evaluation within a bulk evaluation response (standard criteria)
    """
    model_config = ConfigDict(extra='forbid')

    response_id: str = Field(
        ...,
        description="The anonymous response ID being evaluated"
    )

    scores: EvaluationScores = Field(
        ...,
        description="Evaluation scores: accuracy, clarity, completeness, relevance (0-10)"
    )

    reasoning: str = Field(
        ...,
        description="Detailed reasoning for the scores provided"
    )


class SingleCreativeEvaluation(BaseModel):
    """
    Single evaluation within a bulk evaluation response (creative criteria)
    """
    model_config = ConfigDict(extra='forbid')

    response_id: str = Field(
        ...,
        description="The anonymous response ID being evaluated"
    )

    scores: CreativeWritingScores = Field(
        ...,
        description="Creative writing scores: voice_authenticity, emotional_resonance, originality, style_consistency, narrative_coherence, llm_artifact_avoidance (0-10)"
    )

    reasoning: str = Field(
        ...,
        description="Detailed reasoning for the scores provided"
    )


class BulkStandardEvaluationResponse(BaseModel):
    """
    Bulk evaluation response for Council (standard criteria)
    Evaluates multiple responses in one API call for better comparative context
    """
    model_config = ConfigDict(extra='forbid')

    evaluations: List[SingleStandardEvaluation] = Field(
        ...,
        min_length=1,
        description="List of evaluations, one per response being evaluated"
    )


class BulkCreativeEvaluationResponse(BaseModel):
    """
    Bulk evaluation response for Writer's Room (creative criteria)
    Evaluates multiple responses in one API call for better comparative context
    """
    model_config = ConfigDict(extra='forbid')

    evaluations: List[SingleCreativeEvaluation] = Field(
        ...,
        min_length=1,
        description="List of evaluations, one per response being evaluated"
    )


class ResponseVariant(BaseModel):
    """
    Single response variant for verbalized sampling
    """
    model_config = ConfigDict(extra='forbid')

    text: str = Field(
        ...,
        description="The full creative content for this variant"
    )

    probability: Optional[float] = Field(
        default=None,
        description="Probability score (0.0-1.0) representing how unusual/risky this approach is. Note: Constraints removed for JSON schema compatibility."
    )


class MultipleResponses(BaseModel):
    """
    Wrapper for multiple response variants from a single model
    Used for verbalized sampling to get diverse creative outputs
    """
    model_config = ConfigDict(extra='forbid')

    variants: List[ResponseVariant] = Field(
        ...,
        min_length=1,
        description="List of response variants, each with text and optional probability"
    )


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _sanitize_schema_for_openai_strict(schema: dict) -> dict:
    """
    Recursively sanitize a JSON schema to comply with OpenAI's strict mode requirements.

    OpenAI strict mode requires:
    1. additionalProperties: false on ALL object types (including nested and $defs)
    2. All properties must be in the 'required' array
    3. No unsupported constructs like empty schemas or certain union types
    4. $ref MUST be standalone - cannot have other keywords like 'description'

    This function modifies the schema in-place and returns it.
    """
    if not isinstance(schema, dict):
        return schema

    # Process $defs first (these are referenced schemas)
    if "$defs" in schema:
        for def_name, def_schema in schema["$defs"].items():
            _sanitize_schema_for_openai_strict(def_schema)

    # CRITICAL: If this has $ref, it MUST be standalone (OpenAI requirement)
    # Remove any other keywords like 'description', 'title', 'default', etc.
    if "$ref" in schema:
        ref_value = schema["$ref"]
        # Keep only the $ref, remove everything else
        schema.clear()
        schema["$ref"] = ref_value
        return schema

    # Handle object types
    if schema.get("type") == "object":
        # Set additionalProperties to false
        schema["additionalProperties"] = False

        # Ensure all properties are required
        if "properties" in schema:
            # Make all properties required
            schema["required"] = list(schema["properties"].keys())

            # Recursively process nested properties
            for prop_name, prop_schema in schema["properties"].items():
                _sanitize_schema_for_openai_strict(prop_schema)

    # Handle array types - process items schema
    if schema.get("type") == "array" and "items" in schema:
        _sanitize_schema_for_openai_strict(schema["items"])

    # Handle allOf, anyOf, oneOf
    for key in ["allOf", "anyOf", "oneOf"]:
        if key in schema:
            for sub_schema in schema[key]:
                _sanitize_schema_for_openai_strict(sub_schema)

    return schema


def get_structured_output_format(schema_model: type[BaseModel], name: str, strict: bool = True) -> dict:
    """
    Generate OpenAI/OpenRouter compatible response_format for structured outputs

    Args:
        schema_model: Pydantic model class to use as schema
        name: Name for the schema (e.g., "evaluation_response")
        strict: Whether to enforce strict schema adherence

    Returns:
        Dict ready to use as response_format parameter

    Note:
        When strict=True, the schema is sanitized to comply with OpenAI's
        strict mode requirements (additionalProperties: false on all objects,
        all properties required).
    """
    schema = schema_model.model_json_schema()

    # Sanitize schema for OpenAI strict mode compliance
    if strict:
        _sanitize_schema_for_openai_strict(schema)

    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "schema": schema,
            "strict": strict
        }
    }


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

class Filter:
    """
    Synthesis Prompt Filter

    Injects synthesis instructions when Council is in synthesis mode.
    Prompt is user-editable via Valves in Open WebUI UI!
    """

    class Valves(BaseModel):
        """
        User-configurable synthesis prompt template
        """
        PRIORITY: int = Field(
            default=10,
            description="Filter priority (higher runs first). Should run before model query."
        )

        SYNTHESIS_TEMPLATE: str = Field(
            default="""You are synthesizing insights from multiple AI models to create a comprehensive, high-quality response.

**ORIGINAL QUESTION:**
{original_question}

**TOP-RATED RESPONSES** (selected from peer evaluation):
{top_responses}

**EVALUATION SCORES:**
{score_summary}

---

**YOUR TASK:**

Synthesize a final response that:

1. **Combines the Best Elements**: Identify and integrate the strongest points from each top-rated response
2. **Ensures Accuracy**: Prioritize factually correct information from highly-scored responses
3. **Maximizes Clarity**: Present the synthesis in clear, understandable language
4. **Achieves Completeness**: Address all aspects of the original question thoroughly
5. **Maintains Relevance**: Stay focused on what the user asked

**SYNTHESIS GUIDELINES:**

- **Integration, not repetition**: Don't just list different answers; weave insights together
- **Acknowledge divergence**: If top responses disagree, note the different perspectives
- **Build on strengths**: Where responses complement each other, combine their insights
- **Critical thinking**: If you notice issues even in top-rated responses, address them
- **Add value**: Your synthesis should be more valuable than any single response

**Output your synthesized response below:**""",
            description="Synthesis prompt template. Use {original_question}, {top_responses}, {score_summary} as placeholders."
        )

        INCLUDE_ANONYMOUS_IDS: bool = Field(
            default=False,
            description="Include anonymous IDs in response listing (for debugging)"
        )

        ENABLE_DEBUG_LOGGING: bool = Field(
            default=False,
            description="Enable debug logging for this filter"
        )

    def __init__(self):
        """Initialize the filter"""
        self.valves = self.Valves()

    def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        """
        Inlet: Called before the request goes to the model

        Checks if Council is in synthesis mode, and if so, injects
        the synthesis prompt with top responses and scores.

        Args:
            body: Request body containing messages, metadata, etc.
            __user__: User information (optional)

        Returns:
            Modified body with synthesis prompt injected (if applicable)
        """

        # Extract Council metadata
        metadata = extract_council_metadata(body)

        # Only inject if in synthesis mode
        if not metadata or metadata.mode != CouncilMode.SYNTHESIS:
            # Not in synthesis mode, pass through unchanged
            return body

        # Extract synthesis input from metadata
        synthesis_input = metadata.synthesis_input

        if not synthesis_input:
            if self.valves.ENABLE_DEBUG_LOGGING:
                print("[Council Synthesis Filter] No synthesis input found in metadata")
            return body

        if self.valves.ENABLE_DEBUG_LOGGING:
            print(f"[Council Synthesis Filter] Injecting synthesis prompt")
            print(f"[Council Synthesis Filter] Top responses: {len(synthesis_input.top_responses)}")

        # Format the components
        original_question = synthesis_input.original_question

        # Format top responses
        top_responses_text = self._format_top_responses(
            synthesis_input.top_responses,
            synthesis_input.scores
        )

        # Format score summary
        score_summary_text = self._format_score_summary(
            synthesis_input.top_responses,
            synthesis_input.scores,
            synthesis_input.criteria_weights
        )

        # Build the synthesis prompt
        synthesis_prompt = self.valves.SYNTHESIS_TEMPLATE.format(
            original_question=original_question,
            top_responses=top_responses_text,
            score_summary=score_summary_text
        )

        # Replace the last user message with the synthesis prompt
        if body.get("messages") and len(body["messages"]) > 0:
            for i in range(len(body["messages"]) - 1, -1, -1):
                if body["messages"][i].get("role") == "user":
                    body["messages"][i]["content"] = synthesis_prompt
                    break
        else:
            body["messages"] = [
                {
                    "role": "user",
                    "content": synthesis_prompt
                }
            ]

        if self.valves.ENABLE_DEBUG_LOGGING:
            print(f"[Council Synthesis Filter] Synthesis prompt injected successfully")

        return body

    def _format_top_responses(self, top_responses, scores) -> str:
        """
        Format top responses for inclusion in synthesis prompt

        Args:
            top_responses: List of ModelResponse objects
            scores: Dict mapping anonymous_id to AggregatedScores

        Returns:
            Formatted string with responses
        """
        formatted = []

        # Include all responses (orchestrator controls this via synthesis_input.top_responses)
        responses_to_include = top_responses

        for i, response in enumerate(responses_to_include, 1):
            agg_scores = scores.get(response.anonymous_id)

            if self.valves.INCLUDE_ANONYMOUS_IDS:
                header = f"**Response {i}** ({response.anonymous_id})"
            else:
                header = f"**Response {i}**"

            if agg_scores:
                header += f" - Score: {agg_scores.weighted_total:.2f}/10 (Rank {agg_scores.rank})"

            formatted.append(f"{header}\n\n{response.content}\n")

        return "\n---\n\n".join(formatted)

    def _format_score_summary(self, top_responses, scores, weights) -> str:
        """
        Format score summary for inclusion in synthesis prompt

        Args:
            top_responses: List of ModelResponse objects
            scores: Dict mapping anonymous_id to AggregatedScores
            weights: Dict of criteria weights

        Returns:
            Formatted string with score breakdown
        """
        formatted = []

        # Include all responses (orchestrator controls this via synthesis_input.top_responses)
        responses_to_include = top_responses

        for i, response in enumerate(responses_to_include, 1):
            agg_scores = scores.get(response.anonymous_id)

            if not agg_scores or not agg_scores.average_scores:
                continue

            avg = agg_scores.average_scores

            if self.valves.INCLUDE_ANONYMOUS_IDS:
                line = f"Response {i} ({response.anonymous_id}):"
            else:
                line = f"Response {i}:"

            line += f" Accuracy: {avg.accuracy:.1f}, "
            line += f"Clarity: {avg.clarity:.1f}, "
            line += f"Completeness: {avg.completeness:.1f}, "
            line += f"Relevance: {avg.relevance:.1f} "
            line += f"| Weighted Total: {agg_scores.weighted_total:.2f}/10"

            formatted.append(line)

        # Add weights explanation
        formatted.append("\n**Scoring Weights:**")
        formatted.append(f"Accuracy: {weights.get('accuracy', 0):.0%}, "
                        f"Clarity: {weights.get('clarity', 0):.0%}, "
                        f"Completeness: {weights.get('completeness', 0):.0%}, "
                        f"Relevance: {weights.get('relevance', 0):.0%}")

        return "\n".join(formatted)


# Module metadata
__version__ = "0.1.0"
__author__ = "Council Pipeline Team"
__description__ = "Synthesis prompt filter with user-editable template"
