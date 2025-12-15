"""
title: Council of LLMs
author: chmodxheart
author_url: https://github.com/chmodxheart
funding_url: https://github.com/chmodxheart
version: 0.6.0
description: Multi-LLM consultation system with anonymous peer review

Council of LLMs - Main Orchestrator Pipe

This is the core pipeline that orchestrates the entire Council workflow:
1. Query Distribution - Fan out to multiple models
2. Anonymization - Strip model identifiers
3. Evaluation Distribution - All models evaluate all responses
4. Score Aggregation - Rank responses
5. Synthesis - Lead model creates final answer

This pipe coordinates with Filter and Action functions through CouncilMetadata.
"""

from typing import List, Union, Generator, Iterator, Dict, Optional, Any
from pydantic import BaseModel, Field
import asyncio
import aiohttp
import json
import time
import re
from datetime import datetime

# Import our data structures

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

class Pipe:
    """
    Council of LLMs Orchestrator Pipe

    Main workflow controller that coordinates query distribution,
    anonymization, evaluation, aggregation, and synthesis.
    """

    class Valves(BaseModel):
        """
        User-configurable parameters (editable via Open WebUI Admin Panel)
        """

        # ============================================================
        # Model Selection
        # ============================================================
        MODELS_TO_QUERY: str = Field(
            default="gpt-5.1,anthropic/claude-sonnet-4.5,groq.moonshotai/kimi-k2-instruct",
            description="Comma-separated list of model IDs to query for initial responses"
        )

        EVALUATION_MODELS: str = Field(
            default="",
            description="Comma-separated list of model IDs to use for evaluation (leave empty to use same models as MODELS_TO_QUERY)"
        )

        LEAD_SYNTHESIZER: str = Field(
            default="auto",
            description="Lead model for synthesis ('auto' for highest-scoring, or specific model ID)"
        )

        MIN_MODELS_REQUIRED: int = Field(
            default=3,
            ge=2,
            description="Minimum number of successful model responses required (recommended: 3-5, not total models configured)"
        )

        # ============================================================
        # Per-Model Parameters (JSON Configuration)
        # ============================================================
        MODEL_PARAMS_JSON: str = Field(
            default="{}",
            description='Per-model parameters as JSON: {"gpt-4": {"temperature": 0.7}, "claude-3-opus": {"temperature": 0.5}}'
        )

        # ============================================================
        # Default Model Parameters
        # ============================================================
        DEFAULT_TEMPERATURE: float = Field(
            default=0.7,
            ge=0.0,
            le=2.0,
            description="Default temperature for all models"
        )

        DEFAULT_TOP_P: float = Field(
            default=1.0,
            ge=0.0,
            le=1.0,
            description="Default top_p (nucleus sampling)"
        )

        DEFAULT_MAX_TOKENS: int = Field(
            default=2048,
            ge=1,
            description="Default max tokens to generate"
        )

        # ============================================================
        # Evaluation Configuration
        # ============================================================
        EVALUATION_WEIGHT_ACCURACY: float = Field(
            default=0.3,
            ge=0.0,
            le=1.0,
            description="Weight for accuracy criterion"
        )

        EVALUATION_WEIGHT_CLARITY: float = Field(
            default=0.25,
            ge=0.0,
            le=1.0,
            description="Weight for clarity criterion"
        )

        EVALUATION_WEIGHT_COMPLETENESS: float = Field(
            default=0.25,
            ge=0.0,
            le=1.0,
            description="Weight for completeness criterion"
        )

        EVALUATION_WEIGHT_RELEVANCE: float = Field(
            default=0.2,
            ge=0.0,
            le=1.0,
            description="Weight for relevance criterion"
        )

        TOP_N_FOR_SYNTHESIS: int = Field(
            default=0,
            ge=0,
            description="Number of top-ranked responses to use for synthesis (0 = all responses, regardless of score)"
        )

        MIN_SCORE_FOR_SYNTHESIS: float = Field(
            default=0.0,
            ge=0.0,
            le=10.0,
            description="Minimum score threshold for synthesis (0 = include all, even low-scoring responses). Responses below this score are excluded from synthesis input."
        )

        # ============================================================
        # Performance Configuration
        # ============================================================
        TIMEOUT_SECONDS: int = Field(
            default=60,
            ge=5,
            le=360,
            description="Timeout for individual model queries (seconds)"
        )

        EVAL_TIMEOUT_SECONDS: int = Field(
            default=90,
            ge=5,
            le=360,
            description="Timeout for evaluation queries (seconds). Often needs to be higher due to rate limits."
        )

        ENABLE_PARALLEL_REQUESTS: bool = Field(
            default=True,
            description="Enable parallel model queries (recommended)"
        )

        # ============================================================
        # Synthesis Mode Configuration
        # ============================================================
        SYNTHESIS_MODE: str = Field(
            default="full",
            description="Synthesis mode: 'full' (synthesize from all responses), 'highest_rated' (return only the top-scoring response), 'none' (show responses and scores only, no synthesis)"
        )

        # ============================================================
        # Token & Cost Tracking
        # ============================================================
        SHOW_TOKEN_USAGE: bool = Field(
            default=True,
            description="Show detailed token usage breakdown per model (initial + evaluation)"
        )

        MODEL_COSTS_JSON: str = Field(
            default="{}",
            description='Per-model costs as JSON: {"gpt-4": {"input": 0.03, "output": 0.06}, "claude-3-opus": {"input": 0.015, "output": 0.075}}. Costs are per 1M tokens.'
        )

        SHOW_COST_ESTIMATE: bool = Field(
            default=False,
            description="Show estimated cost breakdown (requires MODEL_COSTS_JSON to be configured)"
        )

        # ============================================================
        # Output Configuration
        # ============================================================
        SHOW_EVALUATION_SCORES: bool = Field(
            default=True,
            description="Include evaluation scores summary in output"
        )

        SHOW_INDIVIDUAL_RESPONSES: bool = Field(
            default=False,
            description="Include all individual model responses in output (can be very large!)"
        )

        SHOW_REASONING: bool = Field(
            default=False,
            description="Include detailed evaluation reasoning in output (can be very large!)"
        )

        SHOW_PROGRESS: bool = Field(
            default=True,
            description="Stream progress updates during execution (queries, evaluations, synthesis phases)"
        )

        ENABLE_STREAMING: bool = Field(
            default=True,
            description="Stream output progressively as Council works (recommended for transparency)"
        )

        # ============================================================
        # Prompting Techniques Configuration
        # ============================================================

        # Initial Query Techniques
        QUERY_USE_HERMENEUTIC_CIRCLE: bool = Field(
            default=True,
            description="Apply hermeneutic circle (parts/whole interplay) in initial responses"
        )

        QUERY_USE_CHAIN_OF_THOUGHT: bool = Field(
            default=False,
            description="Request step-by-step reasoning in initial responses"
        )

        QUERY_USE_VERBALIZED_SAMPLING: bool = Field(
            default=False,
            description="Request models to show intermediate thinking in initial responses"
        )

        # Evaluation Techniques
        EVAL_USE_HERMENEUTIC_CIRCLE: bool = Field(
            default=True,
            description="Apply hermeneutic circle in evaluations"
        )

        EVAL_USE_VERBALIZED_SAMPLING: bool = Field(
            default=True,
            description="Request detailed reasoning process in evaluations"
        )

        EVAL_USE_SOCRATIC_QUESTIONING: bool = Field(
            default=True,
            description="Probe assumptions, gaps, and weaknesses in evaluations"
        )

        EVAL_USE_ADVERSARIAL_STANCE: bool = Field(
            default=True,
            description="Actively look for flaws and edge cases in evaluations"
        )

        EVAL_USE_CONSTITUTIONAL_PRINCIPLES: bool = Field(
            default=True,
            description="Justify scores against explicit quality principles in evaluations"
        )

        # Synthesis Techniques
        SYNTH_USE_META_COGNITIVE: bool = Field(
            default=True,
            description="Reflect on uncertainty and confidence levels in synthesis"
        )

        # ============================================================
        # Evaluation Prompt Template
        # ============================================================
        # Note: This template is dynamically built based on enabled prompting techniques.
        # See _build_evaluation_prompt() method for the actual template construction.

        # ============================================================
        # Synthesis Prompt Template
        # ============================================================
        # Note: This template is dynamically built based on enabled prompting techniques.
        # See _build_synthesis_prompt() method for the actual template construction.

        # ============================================================
        # Score Parsing Patterns
        # ============================================================
        ACCURACY_PATTERN: str = Field(
            default=r"ACCURACY:\s*(\d+(?:\.\d+)?)",
            description="Regex pattern to extract accuracy score"
        )

        CLARITY_PATTERN: str = Field(
            default=r"CLARITY:\s*(\d+(?:\.\d+)?)",
            description="Regex pattern to extract clarity score"
        )

        COMPLETENESS_PATTERN: str = Field(
            default=r"COMPLETENESS:\s*(\d+(?:\.\d+)?)",
            description="Regex pattern to extract completeness score"
        )

        RELEVANCE_PATTERN: str = Field(
            default=r"RELEVANCE:\s*(\d+(?:\.\d+)?)",
            description="Regex pattern to extract relevance score"
        )

        REASONING_PATTERN: str = Field(
            default=r"REASONING:\s*(.+?)(?=\n\n|\Z)",
            description="Regex pattern to extract reasoning text"
        )

        DEFAULT_SCORE: float = Field(
            default=5.0,
            ge=0.0,
            le=10.0,
            description="Default score if parsing fails"
        )

        STRICT_SCORE_PARSING: bool = Field(
            default=False,
            description="If True, reject evaluations with missing scores. If False, use defaults."
        )

        # ============================================================
        # Debug Configuration
        # ============================================================
        DEBUG_MODE: bool = Field(
            default=False,
            description="Enable verbose debug logging"
        )

    def __init__(self):
        """Initialize the Council Orchestrator"""
        self.name = ""

        # Initialize valves with environment variable support
        self.valves = self.Valves()

        # Internal state
        self.available_models: List[str] = []
        self.evaluation_models: List[str] = []  # Models used for evaluation (can differ from generation models)
        self.token_usage: int = 0
        self._last_models_string: str = ""  # Cache to avoid re-parsing

        # Token tracking per model and phase
        self.token_tracking: Dict[str, Dict[str, Dict[str, int]]] = {}
        # Structure: {model_id: {"initial": {"input": X, "output": Y}, "evaluation": {"input": X, "output": Y}, "synthesis": {"input": X, "output": Y}}}

    async def on_startup(self):
        """Called when the Pipelines server starts"""
        print(f"[Council] Starting up: {self.name}")
        self._parse_models()
        print(f"[Council] Configured models: {self.available_models}")
        print(f"[Council] Min required: {self.valves.MIN_MODELS_REQUIRED}")

    async def on_shutdown(self):
        """Called when the Pipelines server stops"""
        print(f"[Council] Shutting down: {self.name}")

    async def on_valves_updated(self):
        """Called when valves are updated via Admin Panel"""
        print(f"[Council] Valves updated")
        # Force cache invalidation
        self._last_models_string = ""
        self.available_models = []
        self._parse_models()
        print(f"[Council] Updated models: {self.available_models}")


    # ================================================================
    # MAIN PIPE FUNCTION
    # ================================================================

    async def pipe(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __request__: Optional[Any] = None,
    ):
        """
        Main pipeline execution function (async generator for streaming)

        This is called by Open WebUI when the user sends a message
        to the Council of LLMs model.

        Args:
            body: Request body containing messages, model, and other parameters
            __user__: User information dict (optional)
            __request__: Request object (optional)

        Yields:
            str: Chunks of output as the Council workflow progresses
        """

        # Check if this is a title generation request
        if body.get("title", False):
            yield "Council Discussion"
            return

        # Extract parameters from body
        messages = body.get("messages", [])
        if not messages:
            yield "[ERROR] No messages provided in request"
            return

        # Get the user message from the last message in the conversation
        user_message = messages[-1].get("content", "") if messages else ""

        # Always re-parse models from configuration to catch valve updates
        self._parse_models()

        # Validate configuration
        if len(self.available_models) < self.valves.MIN_MODELS_REQUIRED:
            yield f"[ERROR] Council requires at least {self.valves.MIN_MODELS_REQUIRED} models. Currently configured: {len(self.available_models)}.\n\n"
            yield f"**Configured models:**\n"
            for i, model in enumerate(self.available_models, 1):
                yield f"{i}. {model}\n"
            yield f"\n**Raw MODELS_TO_QUERY value (first 500 chars):**\n```\n{self.valves.MODELS_TO_QUERY[:500]}\n```\n\n"
            yield f"Please check that MODELS_TO_QUERY in Valves contains all your models separated by commas. Long strings may be truncated by the UI - try editing in a text editor and pasting.\n"
            return

        if self.valves.DEBUG_MODE:
            print(f"[Council] Processing query: {user_message[:100]}...")
            print(f"[Council] Models: {self.available_models}")

        # Run the streaming workflow
        try:
            if self.valves.ENABLE_STREAMING:
                async for chunk in self._run_council_workflow_streaming(
                    user_message,
                    messages,
                    body,
                    __user__,
                    __request__
                ):
                    yield chunk
            else:
                # Non-streaming fallback
                result = await self._run_council_workflow(
                    user_message,
                    messages,
                    body,
                    __user__,
                    __request__
                )
                yield result
        except Exception as e:
            error_msg = f"\n\n[ERROR] Council error: {str(e)}"
            print(f"[Council] Error: {e}")
            if self.valves.DEBUG_MODE:
                import traceback
                traceback.print_exc()
            yield error_msg

    # ================================================================
    # CORE WORKFLOW
    # ================================================================

    async def _run_council_workflow(
        self,
        user_message: str,
        messages: List[dict],
        body: dict,
        user: Optional[dict],
        request: Optional[Any],
    ) -> str:
        """
        Execute the complete Council workflow asynchronously

        Phases:
        1. Query Distribution
        2. Anonymization
        3. Evaluation Distribution
        4. Score Aggregation & Ranking
        5. Synthesis
        """

        # Initialize Council metadata
        metadata = create_council_metadata()
        metadata.mode = CouncilMode.INITIAL_QUERY
        metadata.models_queried = self.available_models
        metadata.criteria_weights = self._get_criteria_weights()
        metadata.debug_mode = self.valves.DEBUG_MODE

        if self.valves.DEBUG_MODE:
            print(f"[Council] Session ID: {metadata.session_id}")

        # ============================================================
        # PHASE 1: Query Distribution
        # ============================================================
        if self.valves.DEBUG_MODE:
            print(f"[Council] Phase 1: Query Distribution")

        responses = await self._query_all_models(
            messages,
            request,
            user
        )

        # Check if we have enough successful responses
        successful_responses = [r for r in responses if r.success]
        failed_responses = [r for r in responses if not r.success]

        if len(successful_responses) < self.valves.MIN_MODELS_REQUIRED:
            error_details = f"❌ **Error**: Only {len(successful_responses)} models responded successfully. Need {self.valves.MIN_MODELS_REQUIRED}.\n\n"

            if successful_responses:
                error_details += f"**✓ Successful ({len(successful_responses)}):** {', '.join([r.model_id for r in successful_responses])}\n\n"

            if failed_responses:
                error_details += f"**✗ Failed ({len(failed_responses)}):**\n"
                for resp in failed_responses:
                    error_msg = resp.error if resp.error else "Unknown error"
                    error_details += f"  - {resp.model_id}: {error_msg}\n"

            return error_details

        metadata.responses = successful_responses

        if self.valves.DEBUG_MODE:
            print(f"[Council] Received {len(successful_responses)} successful responses")

        # ============================================================
        # PHASE 2: Anonymization
        # ============================================================
        if self.valves.DEBUG_MODE:
            print(f"[Council] Phase 2: Anonymization")

        metadata.anonymous_mapping = self._create_anonymous_mapping(successful_responses)

        # ============================================================
        # PHASE 3: Evaluation Distribution
        # ============================================================
        if self.valves.DEBUG_MODE:
            print(f"[Council] Phase 3: Evaluation Distribution")

        metadata.mode = CouncilMode.EVALUATION

        # Note: In full implementation, this would use Filter functions
        # For now, we'll simulate evaluations for testing
        evaluations = await self._evaluate_responses(
            successful_responses,
            messages,
            request,
            user,
            metadata
        )

        metadata.evaluations = evaluations

        if self.valves.DEBUG_MODE:
            print(f"[Council] Collected {len(evaluations)} evaluations")

        # ============================================================
        # PHASE 4: Score Aggregation & Ranking
        # ============================================================
        if self.valves.DEBUG_MODE:
            print(f"[Council] Phase 4: Score Aggregation")

        metadata.aggregated_scores = self._aggregate_scores(
            evaluations,
            metadata.criteria_weights
        )

        ranked_responses = self._rank_responses(
            successful_responses,
            metadata.aggregated_scores
        )

        if self.valves.DEBUG_MODE:
            for i, resp in enumerate(ranked_responses):
                agg = metadata.aggregated_scores[resp.anonymous_id]
                print(f"[Council]   Rank {i+1}: {resp.anonymous_id} (score: {agg.weighted_total:.2f})")

        # ============================================================
        # PHASE 5: Synthesis
        # ============================================================
        if self.valves.DEBUG_MODE:
            print(f"[Council] Phase 5: Synthesis")

        metadata.mode = CouncilMode.SYNTHESIS

        # Select responses for synthesis based on TOP_N_FOR_SYNTHESIS and MIN_SCORE_FOR_SYNTHESIS
        # First, filter by score threshold if set
        if self.valves.MIN_SCORE_FOR_SYNTHESIS > 0:
            filtered_responses = [
                r for r in ranked_responses
                if metadata.aggregated_scores[r.anonymous_id].weighted_total >= self.valves.MIN_SCORE_FOR_SYNTHESIS
            ]
            if self.valves.DEBUG_MODE:
                excluded = len(ranked_responses) - len(filtered_responses)
                print(f"[Council] Filtered out {excluded} responses below score threshold {self.valves.MIN_SCORE_FOR_SYNTHESIS}")
        else:
            filtered_responses = ranked_responses

        # Then apply top-N limit if set
        if self.valves.TOP_N_FOR_SYNTHESIS == 0:
            responses_for_synthesis = filtered_responses  # All responses that passed threshold
        else:
            responses_for_synthesis = filtered_responses[:self.valves.TOP_N_FOR_SYNTHESIS]

        # Determine lead model
        lead_model_id = self._select_lead_model(ranked_responses)
        metadata.lead_model_id = lead_model_id

        if self.valves.DEBUG_MODE:
            print(f"[Council] Lead model: {lead_model_id}")
            print(f"[Council] Using {len(responses_for_synthesis)}/{len(ranked_responses)} responses for synthesis")

        # Prepare synthesis input
        metadata.synthesis_input = SynthesisInput(
            original_question=user_message,
            top_responses=responses_for_synthesis,
            scores=metadata.aggregated_scores,
            lead_model_id=lead_model_id,
            criteria_weights=metadata.criteria_weights
        )

        # Synthesize answer
        final_answer = await self._synthesize_answer(
            user_message,
            responses_for_synthesis,
            metadata.aggregated_scores,
            lead_model_id,
            messages,
            request,
            user,
            metadata
        )

        # ============================================================
        # PHASE 6: Format Final Output
        # ============================================================
        metadata.mode = CouncilMode.COMPLETE
        metadata.completed_at = datetime.utcnow()

        output = self._format_final_output(
            final_answer,
            metadata,
            ranked_responses
        )

        # Store metadata in body for Actions to access
        inject_council_metadata(body, metadata)

        return output

    async def _run_council_workflow_streaming(
        self,
        user_message: str,
        messages: List[dict],
        body: dict,
        user: Optional[dict],
        request: Optional[Any],
    ):
        """
        Execute the complete Council workflow with streaming output

        Yields output at each major step for real-time visibility.
        """

        # Reset token tracking for this session
        self._reset_token_tracking()

        # Initialize Council metadata
        metadata = create_council_metadata()
        metadata.mode = CouncilMode.INITIAL_QUERY
        metadata.models_queried = self.available_models
        metadata.criteria_weights = self._get_criteria_weights()
        metadata.debug_mode = self.valves.DEBUG_MODE

        # ============================================================
        # PHASE 1 & 2 (OVERLAPPED): Query Distribution + Evaluation
        # ============================================================
        if self.valves.SHOW_PROGRESS:
            yield f"## 🔄 Querying Council Models\n\n"
            yield f"Consulting {len(self.available_models)} models: {', '.join(self.available_models)}\n\n"
            yield f"*(Evaluations will start as responses arrive for maximum performance)*\n\n"

        metadata.mode = CouncilMode.INITIAL_QUERY
        responses, evaluations = await self._query_and_evaluate_overlapped(
            messages,
            request,
            user,
            metadata
        )

        # Check if we have enough successful responses
        successful_responses = [r for r in responses if r.success]
        failed_responses = [r for r in responses if not r.success]

        if len(successful_responses) < self.valves.MIN_MODELS_REQUIRED:
            yield f"\n\n❌ **Error**: Only {len(successful_responses)} models responded successfully. Need {self.valves.MIN_MODELS_REQUIRED}.\n\n"

            if successful_responses:
                yield f"**✓ Successful ({len(successful_responses)}):** {', '.join([r.model_id for r in successful_responses])}\n\n"

            if failed_responses:
                yield f"**✗ Failed ({len(failed_responses)}):**\n"
                for resp in failed_responses:
                    error_msg = resp.error if resp.error else "Unknown error"
                    yield f"  - {resp.model_id}: {error_msg}\n"
                yield "\n"

            return

        metadata.responses = successful_responses

        if self.valves.SHOW_PROGRESS:
            yield f"✓ Received {len(successful_responses)} successful responses"
            if failed_responses:
                yield f" ({len(failed_responses)} failed)"
            yield "\n\n"

        # Show individual responses if enabled
        if self.valves.SHOW_INDIVIDUAL_RESPONSES:
            yield "## 📝 Individual Model Responses\n\n"
            for i, response in enumerate(successful_responses, 1):
                yield f"<details>\n<summary>Response {i}: {response.model_id}</summary>\n\n"
                yield f"{response.content}\n\n"
                yield f"*({response.tokens_used} tokens, {response.latency_ms:.0f}ms)*\n\n"
                yield "</details>\n\n"

        # ============================================================
        # PHASE 2: Anonymization (already done during overlapped execution)
        # ============================================================
        if self.valves.SHOW_PROGRESS:
            yield "## 🎭 Anonymizing Responses\n\n"
            # Anonymous IDs already assigned during overlapped execution
            yield f"Assigned anonymous IDs for anonymous peer review (during query phase)\n\n"

        # ============================================================
        # PHASE 3: Evaluation Results (completed during query phase)
        # ============================================================
        if self.valves.SHOW_PROGRESS:
            yield "## ⚖️ Anonymous Peer Evaluation\n\n"

        metadata.evaluations = evaluations
        metadata.mode = CouncilMode.EVALUATION

        if self.valves.SHOW_PROGRESS:
            expected_evals = len(successful_responses) * len(self.evaluation_models)
            yield f"✓ Collected {len(evaluations)}/{expected_evals} evaluations (gathered in parallel with queries)"

            # Warn if many evaluations failed
            if len(evaluations) < expected_evals:
                failed_evals = expected_evals - len(evaluations)
                failure_rate = (failed_evals / expected_evals) * 100
                if failure_rate > 20:
                    yield f" ⚠️ **{failed_evals} evaluations failed ({failure_rate:.0f}%)**"

            yield "\n\n"

        # Show evaluations with reasoning if enabled
        if self.valves.SHOW_REASONING and evaluations:
            yield "## 📊 Detailed Evaluations\n\n"

            # Use anonymous_to_model for reverse mapping (anonymous_id -> real model_id)
            reverse_mapping = metadata.anonymous_mapping.anonymous_to_model

            # Group evaluations by target
            from collections import defaultdict
            evals_by_target = defaultdict(list)
            for ev in evaluations:
                evals_by_target[ev.target_anonymous_id].append(ev)

            for target_id, target_evals in evals_by_target.items():
                # De-anonymize the target response for user display
                real_target_id = reverse_mapping.get(target_id, target_id)
                yield f"<details>\n<summary>Evaluations for {real_target_id}'s Response</summary>\n\n"
                yield f"*(Anonymous ID during review: {target_id})*\n\n"

                for ev in target_evals:
                    yield f"**Evaluator**: {ev.evaluator_model_id}\n\n"
                    yield f"- **Accuracy**: {ev.scores.accuracy:.1f}/10\n"
                    yield f"- **Clarity**: {ev.scores.clarity:.1f}/10\n"
                    yield f"- **Completeness**: {ev.scores.completeness:.1f}/10\n"
                    yield f"- **Relevance**: {ev.scores.relevance:.1f}/10\n\n"
                    if ev.reasoning:
                        yield f"*Reasoning*: {ev.reasoning}\n\n"
                    yield "---\n\n"
                yield "</details>\n\n"

        # ============================================================
        # PHASE 4: Score Aggregation & Ranking
        # ============================================================
        if self.valves.SHOW_PROGRESS:
            yield "## 📈 Score Aggregation\n\n"

        metadata.aggregated_scores = self._aggregate_scores(
            evaluations,
            metadata.criteria_weights
        )

        ranked_responses = self._rank_responses(
            successful_responses,
            metadata.aggregated_scores
        )

        # Show evaluation summary if enabled
        if self.valves.SHOW_EVALUATION_SCORES:
            # Use anonymous_to_model for reverse mapping (anonymous_id -> real model_id)
            reverse_mapping = metadata.anonymous_mapping.anonymous_to_model

            yield "<details>\n<summary>🏆 Evaluation Summary</summary>\n\n"
            for i, response in enumerate(ranked_responses, 1):
                agg = metadata.aggregated_scores[response.anonymous_id]
                # De-anonymize for user display
                real_model_id = reverse_mapping.get(response.anonymous_id, response.anonymous_id)
                yield f"**Rank {i}** - **{real_model_id}**: "
                yield f"**{agg.weighted_total:.2f}/10** "
                yield f"(from {agg.evaluator_count} evaluators)\n\n"
                if agg.average_scores:
                    yield f"  - Accuracy: {agg.average_scores.accuracy:.1f}\n"
                    yield f"  - Clarity: {agg.average_scores.clarity:.1f}\n"
                    yield f"  - Completeness: {agg.average_scores.completeness:.1f}\n"
                    yield f"  - Relevance: {agg.average_scores.relevance:.1f}\n\n"
            yield "</details>\n\n"

        # ============================================================
        # PHASE 5: Synthesis (based on SYNTHESIS_MODE)
        # ============================================================
        metadata.mode = CouncilMode.SYNTHESIS

        # Select responses for synthesis based on TOP_N_FOR_SYNTHESIS and MIN_SCORE_FOR_SYNTHESIS
        # First, filter by score threshold if set
        if self.valves.MIN_SCORE_FOR_SYNTHESIS > 0:
            filtered_responses = [
                r for r in ranked_responses
                if metadata.aggregated_scores[r.anonymous_id].weighted_total >= self.valves.MIN_SCORE_FOR_SYNTHESIS
            ]
            excluded = len(ranked_responses) - len(filtered_responses)
            if self.valves.SHOW_PROGRESS and excluded > 0:
                yield f"*Filtered out {excluded} response(s) below score threshold {self.valves.MIN_SCORE_FOR_SYNTHESIS}/10*\n\n"
        else:
            filtered_responses = ranked_responses

        # Then apply top-N limit if set
        if self.valves.TOP_N_FOR_SYNTHESIS == 0:
            responses_for_synthesis = filtered_responses  # All responses that passed threshold
        else:
            responses_for_synthesis = filtered_responses[:self.valves.TOP_N_FOR_SYNTHESIS]

        lead_model_id = self._select_lead_model(ranked_responses)
        metadata.lead_model_id = lead_model_id

        # Use anonymous_to_model for reverse mapping (anonymous_id -> real model_id)
        reverse_mapping = metadata.anonymous_mapping.anonymous_to_model

        # Handle based on SYNTHESIS_MODE
        synthesis_mode = self.valves.SYNTHESIS_MODE.lower().strip()

        if synthesis_mode == "none":
            # No synthesis - just show responses and scores are done
            if self.valves.SHOW_PROGRESS:
                yield "## 📋 Results (No Synthesis)\n\n"
                yield f"*Synthesis disabled. Showing {len(ranked_responses)} evaluated responses.*\n\n"

            yield "---\n\n"
            yield "## 💡 Highest-Rated Response\n\n"
            top_response = ranked_responses[0]
            top_model = reverse_mapping.get(top_response.anonymous_id, top_response.anonymous_id)
            top_score = metadata.aggregated_scores[top_response.anonymous_id].weighted_total
            yield f"**Winner: {top_model}** (Score: {top_score:.2f}/10)\n\n"
            yield top_response.content
            yield "\n\n"

            final_answer = None  # No synthesis performed

        elif synthesis_mode == "highest_rated":
            # Return only the highest-rated response
            if self.valves.SHOW_PROGRESS:
                yield "## 🏆 Returning Highest-Rated Response\n\n"

            top_response = ranked_responses[0]
            top_model = reverse_mapping.get(top_response.anonymous_id, top_response.anonymous_id)
            top_score = metadata.aggregated_scores[top_response.anonymous_id].weighted_total

            yield "---\n\n"
            yield "## 💡 Council Response\n\n"
            yield f"*Selected response from **{top_model}** (Score: {top_score:.2f}/10)*\n\n"
            yield top_response.content
            yield "\n\n"

            final_answer = top_response.content

        else:
            # Full synthesis mode (default)
            if self.valves.SHOW_PROGRESS:
                yield "## 🎯 Synthesizing Final Answer\n\n"
                yield f"Lead model: **{lead_model_id}**\n\n"
                if self.valves.MIN_SCORE_FOR_SYNTHESIS > 0:
                    yield f"Synthesizing from {len(responses_for_synthesis)} response(s) scoring ≥{self.valves.MIN_SCORE_FOR_SYNTHESIS}/10...\n\n"
                elif self.valves.TOP_N_FOR_SYNTHESIS == 0:
                    yield f"Synthesizing from all {len(responses_for_synthesis)} responses with their evaluations...\n\n"
                else:
                    yield f"Synthesizing from top {len(responses_for_synthesis)} responses with their evaluations...\n\n"

            metadata.synthesis_input = SynthesisInput(
                original_question=user_message,
                top_responses=responses_for_synthesis,
                scores=metadata.aggregated_scores,
                lead_model_id=lead_model_id,
                criteria_weights=metadata.criteria_weights
            )

            final_answer = await self._synthesize_answer(
                user_message,
                responses_for_synthesis,
                metadata.aggregated_scores,
                lead_model_id,
                messages,
                request,
                user,
                metadata
            )

            yield "---\n\n"
            yield "## 💡 Council Response\n\n"
            yield final_answer
            yield "\n\n"

        # ============================================================
        # PHASE 6: Final Output & Statistics
        # ============================================================
        metadata.mode = CouncilMode.COMPLETE
        metadata.completed_at = datetime.utcnow()
        duration = (metadata.completed_at - metadata.started_at).total_seconds()

        yield f"\n\n---\n\n"

        # Show token usage breakdown if enabled
        if self.valves.SHOW_TOKEN_USAGE and self.token_tracking:
            yield "<details>\n<summary>📊 Token Usage Breakdown</summary>\n\n"
            yield self._format_token_usage_output()
            yield "\n</details>\n\n"

        # Show cost estimate if enabled
        if self.valves.SHOW_COST_ESTIMATE:
            cost_output = self._format_cost_output()
            if "requires MODEL_COSTS_JSON" not in cost_output:
                yield "<details>\n<summary>💰 Cost Estimate</summary>\n\n"
                yield cost_output
                yield "\n</details>\n\n"

        yield f"*Council session completed in {duration:.1f}s • {self.token_usage:,} tokens used*\n"

        # Store metadata in body for Actions to access
        inject_council_metadata(body, metadata)

    # ================================================================
    # HELPER METHODS
    # ================================================================

    def _reset_token_tracking(self):
        """Reset token tracking for a new session"""
        self.token_tracking = {}
        self.token_usage = 0

    def _track_tokens(self, model_id: str, phase: str, input_tokens: int, output_tokens: int):
        """
        Track token usage for a model in a specific phase

        Args:
            model_id: The model identifier
            phase: One of "initial", "evaluation", or "synthesis"
            input_tokens: Number of input/prompt tokens
            output_tokens: Number of output/completion tokens
        """
        if model_id not in self.token_tracking:
            self.token_tracking[model_id] = {
                "initial": {"input": 0, "output": 0},
                "evaluation": {"input": 0, "output": 0},
                "synthesis": {"input": 0, "output": 0}
            }

        self.token_tracking[model_id][phase]["input"] += input_tokens
        self.token_tracking[model_id][phase]["output"] += output_tokens
        self.token_usage += input_tokens + output_tokens

    def _get_model_costs(self) -> Dict[str, Dict[str, float]]:
        """
        Parse model costs from JSON configuration

        Returns dict mapping model_id to {"input": cost_per_1k, "output": cost_per_1k}
        """
        try:
            return json.loads(self.valves.MODEL_COSTS_JSON)
        except:
            return {}

    def _calculate_cost_summary(self) -> Dict[str, Any]:
        """
        Calculate cost summary based on token usage and configured costs

        Returns dict with per-model costs and totals
        """
        costs = self._get_model_costs()
        summary = {
            "by_model": {},
            "by_phase": {"initial": 0.0, "evaluation": 0.0, "synthesis": 0.0},
            "total": 0.0
        }

        for model_id, phases in self.token_tracking.items():
            model_costs = costs.get(model_id, {})
            input_cost_per_1m = model_costs.get("input", 0.0)
            output_cost_per_1m = model_costs.get("output", 0.0)

            model_total = 0.0
            model_breakdown = {}

            for phase, tokens in phases.items():
                input_cost = (tokens["input"] / 1000000.0) * input_cost_per_1m
                output_cost = (tokens["output"] / 1000000.0) * output_cost_per_1m
                phase_cost = input_cost + output_cost

                model_breakdown[phase] = {
                    "input_tokens": tokens["input"],
                    "output_tokens": tokens["output"],
                    "cost": phase_cost
                }

                model_total += phase_cost
                summary["by_phase"][phase] += phase_cost

            summary["by_model"][model_id] = {
                "breakdown": model_breakdown,
                "total": model_total
            }
            summary["total"] += model_total

        return summary

    def _format_token_usage_output(self) -> str:
        """Format token usage breakdown for display"""
        lines = []
        lines.append("## 📊 Token Usage Breakdown\n")

        # Per-model breakdown
        for model_id, phases in self.token_tracking.items():
            total_input = sum(p["input"] for p in phases.values())
            total_output = sum(p["output"] for p in phases.values())
            total = total_input + total_output

            lines.append(f"**{model_id}**: {total:,} tokens")
            lines.append(f"  - Initial query: {phases['initial']['input']:,} in / {phases['initial']['output']:,} out")
            if phases['evaluation']['input'] > 0 or phases['evaluation']['output'] > 0:
                lines.append(f"  - Evaluations: {phases['evaluation']['input']:,} in / {phases['evaluation']['output']:,} out")
            if phases['synthesis']['input'] > 0 or phases['synthesis']['output'] > 0:
                lines.append(f"  - Synthesis: {phases['synthesis']['input']:,} in / {phases['synthesis']['output']:,} out")
            lines.append("")

        # Totals by phase
        total_initial = sum(p["initial"]["input"] + p["initial"]["output"] for p in self.token_tracking.values())
        total_eval = sum(p["evaluation"]["input"] + p["evaluation"]["output"] for p in self.token_tracking.values())
        total_synth = sum(p["synthesis"]["input"] + p["synthesis"]["output"] for p in self.token_tracking.values())

        lines.append("**Totals by Phase:**")
        lines.append(f"  - Initial queries: {total_initial:,} tokens")
        lines.append(f"  - Evaluations: {total_eval:,} tokens")
        lines.append(f"  - Synthesis: {total_synth:,} tokens")
        lines.append(f"  - **Grand Total: {self.token_usage:,} tokens**")

        return "\n".join(lines)

    def _format_cost_output(self) -> str:
        """Format cost breakdown for display"""
        summary = self._calculate_cost_summary()

        if summary["total"] == 0:
            return "\n*Cost estimation requires MODEL_COSTS_JSON to be configured*\n"

        lines = []
        lines.append("## 💰 Cost Estimate\n")

        # Per-model costs
        for model_id, data in summary["by_model"].items():
            if data["total"] > 0:
                lines.append(f"**{model_id}**: ${data['total']:.4f}")
                for phase, phase_data in data["breakdown"].items():
                    if phase_data["cost"] > 0:
                        lines.append(f"  - {phase.capitalize()}: ${phase_data['cost']:.4f} ({phase_data['input_tokens']:,} in / {phase_data['output_tokens']:,} out)")
                lines.append("")

        # Totals
        lines.append("**Total by Phase:**")
        lines.append(f"  - Initial: ${summary['by_phase']['initial']:.4f}")
        lines.append(f"  - Evaluation: ${summary['by_phase']['evaluation']:.4f}")
        lines.append(f"  - Synthesis: ${summary['by_phase']['synthesis']:.4f}")
        lines.append(f"  - **Grand Total: ${summary['total']:.4f}**")

        return "\n".join(lines)

    def _parse_models(self) -> List[str]:
        """Parse model lists from Valves (with caching to avoid unnecessary re-parsing)"""
        raw_string = self.valves.MODELS_TO_QUERY
        raw_eval_string = self.valves.EVALUATION_MODELS

        # Skip parsing if the strings haven't changed
        if raw_string == self._last_models_string and self.available_models:
            if self.valves.DEBUG_MODE:
                print(f"[Council] Model list unchanged, using cached {len(self.available_models)} models")
            return self.available_models

        if self.valves.DEBUG_MODE:
            print(f"[Council] Raw MODELS_TO_QUERY string (len={len(raw_string)}): {raw_string[:200]}...")

        # Parse generation models
        models = [m.strip() for m in raw_string.split(",") if m.strip()]

        if self.valves.DEBUG_MODE:
            print(f"[Council] Parsed {len(models)} generation models: {models}")

        self.available_models = models
        self._last_models_string = raw_string

        # Parse evaluation models (defaults to same as generation models if not specified)
        if raw_eval_string and raw_eval_string.strip():
            eval_models = [m.strip() for m in raw_eval_string.split(",") if m.strip()]
            if self.valves.DEBUG_MODE:
                print(f"[Council] Parsed {len(eval_models)} evaluation models: {eval_models}")
        else:
            eval_models = models  # Use same models for evaluation
            if self.valves.DEBUG_MODE:
                print(f"[Council] Using same {len(eval_models)} models for evaluation")

        self.evaluation_models = eval_models

        return models

    def _get_model_params(self) -> Dict[str, ModelParameters]:
        """
        Get per-model parameters, falling back to defaults

        Returns dict mapping model_id to ModelParameters
        """
        try:
            custom_params = json.loads(self.valves.MODEL_PARAMS_JSON)
        except:
            custom_params = {}

        model_params = {}
        for model_id in self.available_models:
            model_custom = custom_params.get(model_id, {})

            model_params[model_id] = ModelParameters(
                temperature=model_custom.get("temperature", self.valves.DEFAULT_TEMPERATURE),
                top_p=model_custom.get("top_p", self.valves.DEFAULT_TOP_P),
                max_tokens=model_custom.get("max_tokens", self.valves.DEFAULT_MAX_TOKENS),
                frequency_penalty=model_custom.get("frequency_penalty"),
                presence_penalty=model_custom.get("presence_penalty"),
                stop=model_custom.get("stop"),
            )

        return model_params

    def _get_criteria_weights(self) -> Dict[str, float]:
        """Get evaluation criteria weights from Valves"""
        return {
            "accuracy": self.valves.EVALUATION_WEIGHT_ACCURACY,
            "clarity": self.valves.EVALUATION_WEIGHT_CLARITY,
            "completeness": self.valves.EVALUATION_WEIGHT_COMPLETENESS,
            "relevance": self.valves.EVALUATION_WEIGHT_RELEVANCE,
        }

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

    def _build_initial_query_system_message(self) -> str:
        """Build system message for initial query based on enabled prompting techniques"""
        instructions = []

        instructions.append("You are responding to a user's query as part of a Council of LLMs consultation.")
        instructions.append("Provide a thorough, accurate, and helpful response.")

        # Add technique-specific instructions
        if self.valves.QUERY_USE_HERMENEUTIC_CIRCLE:
            instructions.append("\n**Hermeneutic Circle Approach:**")
            instructions.append("Apply Heidegger's theory of the hermeneutic circle in your response. Move iteratively between the parts and the whole of the question, considering how understanding each detail depends on the broader context and how the overall meaning emerges through that interplay. Show how specific details illuminate the larger picture and vice versa.")

        if self.valves.QUERY_USE_CHAIN_OF_THOUGHT:
            instructions.append("\n**Chain-of-Thought Reasoning:**")
            instructions.append("Break down your reasoning into clear, logical steps. Show the progression of your thinking from the question to your conclusion. Make your reasoning process transparent and easy to follow.")

        if self.valves.QUERY_USE_VERBALIZED_SAMPLING:
            instructions.append("\n**Verbalized Thinking:**")
            instructions.append("Show your intermediate thought process. Don't just present the final answer—reveal how you arrived at it, including any considerations, alternatives evaluated, or uncertainties you worked through.")

        instructions.append("\n**Quality Standards:**")
        instructions.append("Ensure your response is factually accurate, clearly expressed, thorough in addressing all aspects of the question, and directly relevant to what was asked.")

        return "\n".join(instructions)

    def _build_evaluation_prompt(self, response_text: str) -> str:
        """Build evaluation prompt dynamically based on enabled prompting techniques"""
        sections = []

        # Opening
        sections.append("You are participating in an anonymous peer review of AI responses. Your task is to evaluate the following anonymous response objectively and critically.")
        sections.append("")

        # Prompting techniques
        if self.valves.EVAL_USE_HERMENEUTIC_CIRCLE:
            sections.append("**Hermeneutic Circle Approach:**")
            sections.append("Apply Heidegger's theory of the hermeneutic circle in your evaluation. Move iteratively between specific details and the overall response, considering how each part contributes to the whole and how the whole illuminates the meaning of each part.")
            sections.append("")

        if self.valves.EVAL_USE_VERBALIZED_SAMPLING:
            sections.append("**Show Your Thinking:**")
            sections.append("Reveal your evaluation thought process. Don't just assign scores—show how you arrived at them. What did you notice? What considerations did you weigh? What makes this response strong or weak?")
            sections.append("")

        if self.valves.EVAL_USE_SOCRATIC_QUESTIONING:
            sections.append("**Socratic Examination:**")
            sections.append("Probe the response deeply:")
            sections.append("- What assumptions does it make?")
            sections.append("- What questions does it leave unanswered?")
            sections.append("- What could the user misunderstand?")
            sections.append("- What edge cases or scenarios does it not address?")
            sections.append("")

        if self.valves.EVAL_USE_ADVERSARIAL_STANCE:
            sections.append("**Critical Red Team Analysis:**")
            sections.append("Actively look for flaws, weaknesses, and potential issues:")
            sections.append("- What could go wrong if someone followed this advice?")
            sections.append("- Are there hidden assumptions or oversimplifications?")
            sections.append("- What important caveats or warnings are missing?")
            sections.append("- Where is this response potentially misleading or incomplete?")
            sections.append("")

        if self.valves.EVAL_USE_CONSTITUTIONAL_PRINCIPLES:
            sections.append("**Principle-Based Justification:**")
            sections.append("Ground your scores in explicit quality principles. For each score, justify it by reference to specific criteria below. Don't just give a number—explain WHY based on observable qualities.")
            sections.append("")

        # Evaluation criteria
        sections.append("**EVALUATION CRITERIA** (Rate each 1-10, where 1=poor, 10=excellent):")
        sections.append("")
        sections.append("1. **ACCURACY** (Factual Correctness)")
        sections.append("   - Are the facts, data, and claims correct?")
        sections.append("   - Is the information up-to-date and reliable?")
        sections.append("   - Are there any factual errors or misconceptions?")
        sections.append("")
        sections.append("2. **CLARITY** (Understandability)")
        sections.append("   - Is the explanation clear and easy to understand?")
        sections.append("   - Is the language appropriate for the audience?")
        sections.append("   - Are complex concepts explained well?")
        sections.append("")
        sections.append("3. **COMPLETENESS** (Thoroughness)")
        sections.append("   - Does it fully address the question?")
        sections.append("   - Are important aspects covered?")
        sections.append("   - Is anything significant missing?")
        sections.append("")
        sections.append("4. **RELEVANCE** (On-Topic & Useful)")
        sections.append("   - Does it stay focused on the question?")
        sections.append("   - Is the information useful and applicable?")
        sections.append("   - Is there unnecessary tangential content?")
        sections.append("")
        sections.append("---")
        sections.append("")
        sections.append("**ANONYMOUS RESPONSE TO EVALUATE:**")
        sections.append("")
        sections.append(response_text)
        sections.append("")
        sections.append("---")
        sections.append("")
        sections.append("**YOUR EVALUATION:**")
        sections.append("")
        sections.append("Please provide your scores in this EXACT format (this is critical for parsing):")
        sections.append("")
        sections.append("ACCURACY: [your score 1-10]")
        sections.append("CLARITY: [your score 1-10]")
        sections.append("COMPLETENESS: [your score 1-10]")
        sections.append("RELEVANCE: [your score 1-10]")
        sections.append("REASONING: [Provide a DETAILED analysis explaining your scores. Include:")
        sections.append("  - Specific strengths you observed")
        sections.append("  - Specific weaknesses or issues you identified")
        sections.append("  - Evidence from the response supporting your scores")
        sections.append("  - How you weighted different factors in your evaluation")
        sections.append("  - Any important caveats or context")
        sections.append("  Be thorough—several paragraphs are expected, not just 2-3 sentences.]")
        sections.append("")
        sections.append("Be critical but fair. Focus on objective quality, not stylistic preferences.")

        return "\n".join(sections)

    def _build_synthesis_prompt(
        self,
        original_question: str,
        all_responses: List[ModelResponse],
        aggregated_scores: Dict[str, AggregatedScores],
        criteria_weights: Dict[str, float]
    ) -> str:
        """Build synthesis prompt dynamically based on enabled prompting techniques"""
        sections = []

        # Opening
        sections.append("You are synthesizing insights from multiple AI models to create a comprehensive, high-quality response.")
        sections.append("")
        sections.append("You have access to ALL responses (not just the highest-rated), ranked from best to worst according to anonymous peer evaluation. This allows you to learn from both successful approaches AND common pitfalls.")
        sections.append("")

        # Meta-cognitive technique
        if self.valves.SYNTH_USE_META_COGNITIVE:
            sections.append("**Meta-Cognitive Reflection:**")
            sections.append("As you synthesize, reflect on:")
            sections.append("- Where are you most confident in the responses? Least confident?")
            sections.append("- What aspects have consensus vs. divergence across models?")
            sections.append("- What uncertainties or caveats should you communicate to the user?")
            sections.append("- Where might reasonable people disagree?")
            sections.append("")

        # Format all responses with scores
        sections.append("**ORIGINAL QUESTION:**")
        sections.append(original_question)
        sections.append("")
        sections.append("---")
        sections.append("")
        sections.append("**ALL MODEL RESPONSES** (ranked by anonymous peer evaluation):")
        sections.append("")

        # Include ALL responses with their scores
        for i, response in enumerate(all_responses, 1):
            anon_id = response.metadata.get("anonymous_id", "unknown")
            agg = aggregated_scores.get(anon_id)

            if agg:
                sections.append(f"### Response #{i} (Score: {agg.weighted_average:.2f}/10)")
                sections.append(f"**Evaluation Summary:**")
                sections.append(f"- Accuracy: {agg.average_scores.accuracy:.1f}/10")
                sections.append(f"- Clarity: {agg.average_scores.clarity:.1f}/10")
                sections.append(f"- Completeness: {agg.average_scores.completeness:.1f}/10")
                sections.append(f"- Relevance: {agg.average_scores.relevance:.1f}/10")
            else:
                sections.append(f"### Response #{i}")

            sections.append(f"**Content:**")
            sections.append(response.content)
            sections.append("")
            sections.append("---")
            sections.append("")

        # Synthesis task
        sections.append("**YOUR SYNTHESIS TASK:**")
        sections.append("")
        sections.append("Create a final response that:")
        sections.append("")
        sections.append("1. **Learns from Success**: Identify and integrate the strongest points from highly-rated responses")
        sections.append("2. **Avoids Pitfalls**: Understand what didn't work in lower-rated responses and avoid those issues")
        sections.append("3. **Synthesizes, Not Copies**: Weave insights together rather than repeating any single response")
        sections.append("4. **Addresses Gaps**: If even the best responses missed something important, fill that gap")
        sections.append("5. **Handles Disagreement**: If responses contradict each other, evaluate which is more correct or present both perspectives")
        sections.append("6. **Maximizes Value**: Your synthesis should be better than any individual response")
        sections.append("")

        sections.append("**QUALITY STANDARDS:**")
        sections.append("")
        sections.append("- **Accuracy**: Prioritize factual correctness")
        sections.append("- **Clarity**: Explain concepts clearly and accessibly")
        sections.append("- **Completeness**: Address all aspects of the question thoroughly")
        sections.append("- **Relevance**: Stay focused on what the user actually asked")
        sections.append("")

        sections.append("**Output your synthesized response below:**")

        return "\n".join(sections)

    async def _query_and_evaluate_overlapped(
        self,
        messages: List[dict],
        request: Any,
        user: Optional[dict],
        metadata: CouncilMetadata,
    ) -> tuple[List[ModelResponse], List[Evaluation]]:
        """
        Query all models and start evaluations as responses arrive (overlapped execution)

        This optimizes performance by not waiting for all queries to finish before
        starting evaluations. As soon as a response arrives, we immediately spawn
        evaluation tasks for it.

        Returns: (all_responses, all_evaluations)
        """
        # Build system message with prompting technique instructions
        system_message = self._build_initial_query_system_message()

        # Replace or prepend system message
        messages_with_system = []
        system_added = False
        for msg in messages:
            if msg.get("role") == "system" and not system_added:
                messages_with_system.append({"role": "system", "content": system_message})
                system_added = True
            else:
                messages_with_system.append(msg)

        if not system_added:
            messages_with_system = [{"role": "system", "content": system_message}] + messages_with_system

        model_params = self._get_model_params()

        # Start all initial query tasks
        query_tasks = {
            model_id: asyncio.create_task(
                self._query_single_model(model_id, messages_with_system, model_params[model_id], request, user)
            )
            for model_id in self.available_models
        }

        # Track all responses and evaluation tasks
        all_responses = []
        evaluation_tasks = []

        # Initialize anonymous mapping in metadata
        metadata.anonymous_mapping = AnonymousResponseMapping()

        # We need to assign anonymous IDs immediately for evaluations
        import secrets

        # Process responses as they complete
        for coro in asyncio.as_completed(query_tasks.values()):
            try:
                response = await coro

                # Assign anonymous ID immediately if successful
                if response.success:
                    response.anonymous_id = f"response_{secrets.token_hex(4)}"
                    # Update metadata mapping
                    metadata.anonymous_mapping.model_to_anonymous[response.model_id] = response.anonymous_id
                    metadata.anonymous_mapping.anonymous_to_model[response.anonymous_id] = response.model_id

                all_responses.append(response)

                # If this response succeeded, immediately spawn evaluation tasks for it
                if response.success:
                    # All models (that have responded so far) will evaluate this response
                    for evaluator_response in all_responses:
                        if evaluator_response.success:
                            eval_task = self._query_for_evaluation(
                                evaluator_model_id=evaluator_response.model_id,
                                target_response=response,
                                params=model_params[evaluator_response.model_id],
                                request=request,
                                user=user,
                                metadata=metadata
                            )
                            evaluation_tasks.append(eval_task)

                    # This response will also evaluate all previous responses
                    for previous_response in all_responses[:-1]:  # Exclude the one we just added
                        if previous_response.success:
                            eval_task = self._query_for_evaluation(
                                evaluator_model_id=response.model_id,
                                target_response=previous_response,
                                params=model_params[response.model_id],
                                request=request,
                                user=user,
                                metadata=metadata
                            )
                            evaluation_tasks.append(eval_task)
            except Exception as e:
                # Find which model this was for
                failed_model = None
                for model_id, task in query_tasks.items():
                    if task == coro:
                        failed_model = model_id
                        break

                all_responses.append(ModelResponse(
                    model_id=failed_model or "unknown",
                    content="",
                    success=False,
                    error=f"{type(e).__name__}: {str(e)}"
                ))

        # Wait for all evaluations to complete
        if evaluation_tasks:
            eval_results = await asyncio.gather(*evaluation_tasks, return_exceptions=True)
            evaluations = [ev for ev in eval_results if ev is not None and not isinstance(ev, Exception)]
        else:
            evaluations = []

        return all_responses, evaluations

    async def _query_all_models(
        self,
        messages: List[dict],
        request: Any,
        user: Optional[dict],
    ) -> List[ModelResponse]:
        """
        Query all configured models in parallel via Open WebUI API

        Returns list of ModelResponse objects (both successful and failed)
        """
        # Build system message with prompting technique instructions
        system_message = self._build_initial_query_system_message()

        # Replace or prepend system message
        messages_with_system = []
        system_added = False
        for msg in messages:
            if msg.get("role") == "system" and not system_added:
                # Replace existing system message with ours
                messages_with_system.append({"role": "system", "content": system_message})
                system_added = True
            else:
                messages_with_system.append(msg)

        # If no system message was found, prepend ours
        if not system_added:
            messages_with_system = [{"role": "system", "content": system_message}] + messages_with_system

        model_params = self._get_model_params()

        if self.valves.ENABLE_PARALLEL_REQUESTS:
            tasks = [
                self._query_single_model(model_id, messages_with_system, model_params[model_id], request, user)
                for model_id in self.available_models
            ]
            responses = await asyncio.gather(*tasks, return_exceptions=True)

            # Convert exceptions to failed ModelResponse objects
            processed_responses = []
            for i, result in enumerate(responses):
                if isinstance(result, Exception):
                    model_id = self.available_models[i]
                    processed_responses.append(ModelResponse(
                        model_id=model_id,
                        content="",
                        success=False,
                        error=f"{type(result).__name__}: {str(result)}"
                    ))
                else:
                    processed_responses.append(result)
            responses = processed_responses
        else:
            responses = []
            for model_id in self.available_models:
                response = await self._query_single_model(
                    model_id, messages_with_system, model_params[model_id], request, user
                )
                responses.append(response)

        return responses

    async def _query_single_model(
        self,
        model_id: str,
        messages: List[dict],
        params: ModelParameters,
        request: Any,
        user: Optional[dict],
    ) -> ModelResponse:
        """
        Query a single model via Open WebUI API

        Returns ModelResponse (success or error)
        """
        start_time = time.time()

        try:
            # Get base URL and auth token
            base_url = f"{request.url.scheme}://{request.url.netloc}" if request else "http://localhost:3000"
            auth_token = self._extract_token(request)

            if not auth_token:
                return ModelResponse(
                    model_id=model_id,
                    content="",
                    success=False,
                    error="No authentication token available"
                )

            # Build request payload
            payload = {
                "model": model_id,
                "messages": messages,
                "stream": False,
                "temperature": params.temperature,
                "top_p": params.top_p,
                "max_tokens": params.max_tokens,
            }

            if params.frequency_penalty is not None:
                payload["frequency_penalty"] = params.frequency_penalty
            if params.presence_penalty is not None:
                payload["presence_penalty"] = params.presence_penalty
            if params.stop is not None:
                payload["stop"] = params.stop

            # Make API call
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/api/chat/completions",
                    headers={
                        "Authorization": f"Bearer {auth_token}",
                        "Content-Type": "application/json"
                    },
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.valves.EVAL_TIMEOUT_SECONDS)
                ) as response:

                    latency_ms = (time.time() - start_time) * 1000

                    if response.status == 200:
                        data = await response.json()

                        # Safely extract content from response
                        if "choices" in data and len(data["choices"]) > 0:
                            content = data["choices"][0].get("message", {}).get("content", "")
                        else:
                            raise ValueError(f"Invalid API response format: missing choices")

                        usage = data.get("usage", {})
                        input_tokens = usage.get("prompt_tokens", 0)
                        output_tokens = usage.get("completion_tokens", 0)
                        tokens = usage.get("total_tokens", input_tokens + output_tokens)

                        # Track tokens for this initial query
                        self._track_tokens(model_id, "initial", input_tokens, output_tokens)

                        return ModelResponse(
                            model_id=model_id,
                            content=content,
                            success=True,
                            tokens_used=tokens,
                            latency_ms=latency_ms,
                            parameters=params,
                            metadata={"input_tokens": input_tokens, "output_tokens": output_tokens}
                        )
                    else:
                        error_text = await response.text()
                        return ModelResponse(
                            model_id=model_id,
                            content="",
                            success=False,
                            error=f"HTTP {response.status}: {error_text[:200]}",
                            latency_ms=latency_ms
                        )

        except asyncio.TimeoutError:
            latency_ms = (time.time() - start_time) * 1000
            return ModelResponse(
                model_id=model_id,
                content="",
                success=False,
                error=f"Timeout after {self.valves.TIMEOUT_SECONDS}s",
                latency_ms=latency_ms
            )
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return ModelResponse(
                model_id=model_id,
                content="",
                success=False,
                error=str(e),
                latency_ms=latency_ms
            )

    def _create_anonymous_mapping(
        self,
        responses: List[ModelResponse]
    ) -> AnonymousResponseMapping:
        """
        Create bidirectional mapping between model IDs and anonymous IDs

        Anonymous IDs are already generated in ModelResponse objects
        """
        mapping = AnonymousResponseMapping()

        for response in responses:
            mapping.add_mapping(response.model_id, response.anonymous_id)

        return mapping

    def _parse_scores(self, text: str) -> Optional[EvaluationScores]:
        """
        Parse evaluation scores from text using regex patterns from Valves

        Returns EvaluationScores or None if strict mode and scores missing
        """
        # Extract individual scores
        accuracy = self._extract_single_score(text, self.valves.ACCURACY_PATTERN, "accuracy")
        clarity = self._extract_single_score(text, self.valves.CLARITY_PATTERN, "clarity")
        completeness = self._extract_single_score(text, self.valves.COMPLETENESS_PATTERN, "completeness")
        relevance = self._extract_single_score(text, self.valves.RELEVANCE_PATTERN, "relevance")

        # Check if any scores are None
        if self.valves.STRICT_SCORE_PARSING:
            if None in [accuracy, clarity, completeness, relevance]:
                if self.valves.DEBUG_MODE:
                    print("[Council] Strict mode: Some scores missing, rejecting")
                return None

        # Use defaults for missing scores in non-strict mode
        accuracy = accuracy if accuracy is not None else self.valves.DEFAULT_SCORE
        clarity = clarity if clarity is not None else self.valves.DEFAULT_SCORE
        completeness = completeness if completeness is not None else self.valves.DEFAULT_SCORE
        relevance = relevance if relevance is not None else self.valves.DEFAULT_SCORE

        # Clamp scores to valid range (0-10)
        accuracy = max(0.0, min(10.0, accuracy))
        clarity = max(0.0, min(10.0, clarity))
        completeness = max(0.0, min(10.0, completeness))
        relevance = max(0.0, min(10.0, relevance))

        return EvaluationScores(
            accuracy=accuracy,
            clarity=clarity,
            completeness=completeness,
            relevance=relevance
        )

    def _extract_single_score(self, text: str, pattern: str, score_name: str) -> Optional[float]:
        """
        Extract a single score using a regex pattern

        Returns extracted score as float, or None if not found
        """
        try:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                score_str = match.group(1).strip()
                score = float(score_str)

                if self.valves.DEBUG_MODE:
                    print(f"[Council] {score_name}: {score}")

                return score
            else:
                if self.valves.DEBUG_MODE:
                    print(f"[Council] {score_name}: not found")
                return None

        except Exception as e:
            if self.valves.DEBUG_MODE:
                print(f"[Council] Error extracting {score_name}: {e}")
            return None

    def _extract_reasoning(self, text: str) -> str:
        """
        Extract reasoning text using regex pattern from Valves

        Returns extracted reasoning, or empty string if not found
        """
        try:
            match = re.search(self.valves.REASONING_PATTERN, text, re.IGNORECASE | re.DOTALL)
            if match:
                reasoning = match.group(1).strip()
                return reasoning
            return ""

        except Exception as e:
            if self.valves.DEBUG_MODE:
                print(f"[Council] Error extracting reasoning: {e}")
            return ""

    async def _query_for_evaluation(
        self,
        evaluator_model_id: str,
        target_response: ModelResponse,
        params: ModelParameters,
        request: Any,
        user: Optional[dict],
        metadata: CouncilMetadata,
    ) -> Optional[Evaluation]:
        """
        Query a model to evaluate an anonymous response

        Uses inline evaluation prompt from Valves.
        Parses scores using regex patterns from Valves.
        """
        try:
            # Get base URL and auth token
            base_url = f"{request.url.scheme}://{request.url.netloc}" if request else "http://localhost:3000"
            auth_token = self._extract_token(request)

            if not auth_token:
                if self.valves.DEBUG_MODE:
                    print(f"[Council] No auth token for evaluation")
                return None

            # Build evaluation prompt dynamically based on enabled techniques
            evaluation_prompt = self._build_evaluation_prompt(target_response.content)

            # Build request payload
            payload = {
                "model": evaluator_model_id,
                "messages": [
                    {
                        "role": "user",
                        "content": evaluation_prompt
                    }
                ],
                "stream": False,
                "temperature": params.temperature,
                "top_p": params.top_p,
                "max_tokens": params.max_tokens,
            }

            # Make API call
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/api/chat/completions",
                    headers={
                        "Authorization": f"Bearer {auth_token}",
                        "Content-Type": "application/json"
                    },
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.valves.EVAL_TIMEOUT_SECONDS)
                ) as response:

                    if response.status == 200:
                        data = await response.json()

                        # Safely extract content from response
                        if "choices" in data and len(data["choices"]) > 0:
                            evaluation_text = data["choices"][0].get("message", {}).get("content", "")
                        else:
                            if self.valves.DEBUG_MODE:
                                print(f"[Council] Invalid evaluation response format from {evaluator_model_id}")
                            return None

                        # Track evaluation tokens
                        usage = data.get("usage", {})
                        input_tokens = usage.get("prompt_tokens", 0)
                        output_tokens = usage.get("completion_tokens", 0)
                        self._track_tokens(evaluator_model_id, "evaluation", input_tokens, output_tokens)

                        # Parse scores from the evaluation text
                        scores = self._parse_scores(evaluation_text)

                        if scores:
                            # Extract reasoning
                            reasoning = self._extract_reasoning(evaluation_text)

                            evaluation = Evaluation(
                                evaluator_model_id=evaluator_model_id,
                                target_anonymous_id=target_response.anonymous_id,
                                scores=scores,
                                reasoning=reasoning
                            )

                            return evaluation
                        else:
                            if self.valves.DEBUG_MODE:
                                print(f"[Council] Failed to parse scores from {evaluator_model_id}")
                            return None
                    else:
                        if self.valves.DEBUG_MODE:
                            print(f"[Council] Evaluation query failed: HTTP {response.status}")
                        return None

        except Exception as e:
            if self.valves.DEBUG_MODE:
                print(f"[Council] Error in evaluation query: {e}")
            return None

    async def _evaluate_responses(
        self,
        responses: List[ModelResponse],
        messages: List[dict],
        request: Any,
        user: Optional[dict],
        metadata: CouncilMetadata,
    ) -> List[Evaluation]:
        """
        Distribute anonymous responses to evaluation models for scoring

        Each evaluation model evaluates ALL anonymous responses.
        Uses self.evaluation_models which may differ from generation models.

        All evaluations run in parallel for maximum performance.
        """
        # Get model parameters for evaluation queries
        model_params = self._get_model_params()

        # Build list of all evaluation tasks (all independent, can run in parallel)
        tasks = []
        for evaluator_model_id in self.evaluation_models:
            for target in responses:
                if self.valves.DEBUG_MODE:
                    print(f"[Council] Queuing: {evaluator_model_id} evaluating {target.anonymous_id}")

                task = self._query_for_evaluation(
                    evaluator_model_id=evaluator_model_id,
                    target_response=target,
                    params=model_params.get(evaluator_model_id, model_params[self.available_models[0]]),
                    request=request,
                    user=user,
                    metadata=metadata
                )
                tasks.append(task)

        # Execute ALL evaluation queries in parallel
        if self.valves.DEBUG_MODE:
            print(f"[Council] Executing {len(tasks)} evaluations in parallel...")

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out None results and exceptions (failed evaluations)
        evaluations = [ev for ev in results if ev is not None and not isinstance(ev, Exception)]
        none_results = [r for r in results if r is None]
        exceptions = [r for r in results if isinstance(r, Exception)]

        if self.valves.DEBUG_MODE and len(evaluations) < len(tasks):
            print(f"[Council] Completed {len(evaluations)}/{len(tasks)} evaluations successfully")
            if none_results:
                print(f"[Council] {len(none_results)} evaluation(s) returned None (likely timeout or parsing failure)")
            if exceptions:
                print(f"[Council] {len(exceptions)} evaluation(s) raised exceptions:")
                for exc in exceptions[:5]:  # Show first 5
                    print(f"  - {type(exc).__name__}: {str(exc)[:100]}")
        elif self.valves.DEBUG_MODE:
            print(f"[Council] Completed {len(evaluations)}/{len(tasks)} evaluations successfully")

        return evaluations

    def _aggregate_scores(
        self,
        evaluations: List[Evaluation],
        weights: Dict[str, float],
    ) -> Dict[str, AggregatedScores]:
        """
        Aggregate scores from all evaluators for each response

        Returns dict mapping anonymous_id to AggregatedScores
        """
        # Group evaluations by target response
        scores_by_response: Dict[str, List[EvaluationScores]] = {}

        for evaluation in evaluations:
            target_id = evaluation.target_anonymous_id
            if target_id not in scores_by_response:
                scores_by_response[target_id] = []
            scores_by_response[target_id].append(evaluation.scores)

        # Aggregate scores for each response
        aggregated = {}

        for anonymous_id, score_list in scores_by_response.items():
            agg = AggregatedScores(
                anonymous_id=anonymous_id,
                individual_scores=score_list,
                evaluator_count=len(score_list)
            )

            agg.average_scores = agg.calculate_average()
            agg.weighted_total = agg.calculate_weighted_total(weights)

            aggregated[anonymous_id] = agg

        return aggregated

    def _rank_responses(
        self,
        responses: List[ModelResponse],
        aggregated_scores: Dict[str, AggregatedScores],
    ) -> List[ModelResponse]:
        """
        Rank responses by weighted score (highest first)

        Updates rank in aggregated_scores and returns sorted responses
        """
        # Sort responses by weighted score
        sorted_responses = sorted(
            responses,
            key=lambda r: aggregated_scores[r.anonymous_id].weighted_total,
            reverse=True
        )

        # Assign ranks
        for i, response in enumerate(sorted_responses):
            aggregated_scores[response.anonymous_id].rank = i + 1

        return sorted_responses

    def _select_lead_model(
        self,
        ranked_responses: List[ModelResponse],
    ) -> str:
        """
        Select lead model for synthesis

        Either use configured model or highest-scoring model
        """
        if self.valves.LEAD_SYNTHESIZER == "auto":
            # Use highest-scoring model
            return ranked_responses[0].model_id
        else:
            # Use configured model (fall back to highest if not available)
            if self.valves.LEAD_SYNTHESIZER in self.available_models:
                return self.valves.LEAD_SYNTHESIZER
            else:
                return ranked_responses[0].model_id

    async def _synthesize_answer(
        self,
        original_question: str,
        top_responses: List[ModelResponse],
        aggregated_scores: Dict[str, AggregatedScores],
        lead_model_id: str,
        messages: List[dict],
        request: Any,
        user: Optional[dict],
        metadata: CouncilMetadata,
    ) -> str:
        """
        Synthesize final answer from top responses using lead model

        Uses inline synthesis prompt from Valves.
        """
        try:
            # Get base URL and auth token
            base_url = f"{request.url.scheme}://{request.url.netloc}" if request else "http://localhost:3000"
            auth_token = self._extract_token(request)

            if not auth_token:
                if self.valves.DEBUG_MODE:
                    print(f"[Council] No auth token for synthesis, using fallback")
                return self._fallback_synthesis(original_question, top_responses, metadata)

            # Get parameters for lead model
            model_params = self._get_model_params()
            params = model_params.get(lead_model_id, model_params[self.available_models[0]])

            # Build synthesis prompt dynamically with ALL responses
            synthesis_prompt = self._build_synthesis_prompt(
                original_question,
                top_responses,  # Actually contains ALL responses now
                aggregated_scores,
                metadata.criteria_weights
            )

            # Build request payload
            payload = {
                "model": lead_model_id,
                "messages": [
                    {
                        "role": "user",
                        "content": synthesis_prompt
                    }
                ],
                "stream": False,
                "temperature": params.temperature,
                "top_p": params.top_p,
                "max_tokens": params.max_tokens,
            }

            if self.valves.DEBUG_MODE:
                print(f"[Council] Requesting synthesis from {lead_model_id}")

            # Make API call
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/api/chat/completions",
                    headers={
                        "Authorization": f"Bearer {auth_token}",
                        "Content-Type": "application/json"
                    },
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.valves.EVAL_TIMEOUT_SECONDS)
                ) as response:

                    if response.status == 200:
                        data = await response.json()

                        # Safely extract content from response
                        if "choices" in data and len(data["choices"]) > 0:
                            content = data["choices"][0].get("message", {}).get("content", "")
                        else:
                            if self.valves.DEBUG_MODE:
                                print(f"[Council] Invalid synthesis response format from {lead_model_id}")
                            return self._fallback_synthesis(original_question, top_responses, metadata)

                        # Track synthesis tokens
                        usage = data.get("usage", {})
                        input_tokens = usage.get("prompt_tokens", 0)
                        output_tokens = usage.get("completion_tokens", 0)
                        self._track_tokens(lead_model_id, "synthesis", input_tokens, output_tokens)

                        if self.valves.DEBUG_MODE:
                            print(f"[Council] Synthesis received from {lead_model_id}")

                        return content
                    else:
                        if self.valves.DEBUG_MODE:
                            print(f"[Council] Synthesis query failed: HTTP {response.status}")
                        return self._fallback_synthesis(original_question, top_responses, metadata)

        except Exception as e:
            if self.valves.DEBUG_MODE:
                print(f"[Council] Error in synthesis: {e}")
            return self._fallback_synthesis(original_question, top_responses, metadata)

    def _format_top_responses(self, top_responses: List[ModelResponse], scores: Dict[str, AggregatedScores]) -> str:
        """
        Format top responses for inclusion in synthesis prompt
        """
        formatted = []

        for i, response in enumerate(top_responses, 1):
            agg_scores = scores.get(response.anonymous_id)

            header = f"**Response {i}**"
            if agg_scores:
                header += f" - Score: {agg_scores.weighted_total:.2f}/10 (Rank {agg_scores.rank})"

            formatted.append(f"{header}\n\n{response.content}\n")

        return "\n---\n\n".join(formatted)

    def _format_score_summary(self, top_responses: List[ModelResponse], scores: Dict[str, AggregatedScores], weights: Dict[str, float]) -> str:
        """
        Format score summary for inclusion in synthesis prompt
        """
        formatted = []

        for i, response in enumerate(top_responses, 1):
            agg_scores = scores.get(response.anonymous_id)

            if not agg_scores or not agg_scores.average_scores:
                continue

            avg = agg_scores.average_scores

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

    def _fallback_synthesis(
        self,
        original_question: str,
        top_responses: List[ModelResponse],
        metadata: CouncilMetadata
    ) -> str:
        """
        Fallback synthesis when lead model query fails

        Returns a formatted summary with the top response
        """
        synthesis = f"# Council of LLMs - Synthesized Response\n\n"
        synthesis += f"Based on evaluation of {len(metadata.responses)} model responses, "
        synthesis += f"here is the synthesized answer:\n\n"
        synthesis += top_responses[0].content

        return synthesis

    def _format_final_output(
        self,
        synthesized_answer: str,
        metadata: CouncilMetadata,
        ranked_responses: List[ModelResponse],
    ) -> str:
        """
        Format the final output including synthesis and optional details
        """
        output = synthesized_answer

        # Add evaluation scores if enabled
        if self.valves.SHOW_EVALUATION_SCORES:
            output += "\n\n---\n\n"
            output += "## Evaluation Summary\n\n"

            for i, response in enumerate(ranked_responses):
                agg = metadata.aggregated_scores[response.anonymous_id]
                output += f"**Rank {i+1}** ({response.anonymous_id}): "
                output += f"Score {agg.weighted_total:.2f}/10 "
                output += f"(from {agg.evaluator_count} evaluators)\n"

            output += f"\n*Lead synthesizer: {metadata.lead_model_id}*\n"

        # Add individual responses if enabled
        if self.valves.SHOW_INDIVIDUAL_RESPONSES:
            output += "\n\n---\n\n"
            output += "## Individual Responses\n\n"

            for response in ranked_responses:
                agg = metadata.aggregated_scores[response.anonymous_id]
                # Don't reveal model IDs in output (Actions can reveal via mapping)
                output += f"### {response.anonymous_id} (Rank {agg.rank})\n\n"
                output += f"{response.content}\n\n"

        # Add session info
        duration = (metadata.completed_at - metadata.started_at).total_seconds()
        output += f"\n\n*Council session completed in {duration:.1f}s*"
        output += f" • {self.token_usage} tokens used"

        return output


# Module-level metadata
__version__ = "0.6.0"
__author__ = "Council Pipeline Team"
__description__ = "Council of LLMs Orchestrator - Core workflow coordinator"
