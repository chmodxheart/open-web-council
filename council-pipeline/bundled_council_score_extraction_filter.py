"""
title: Council Score Extraction Filter
author: chmodxheart
author_url: https://github.com/chmodxheart
funding_url: https://github.com/chmodxheart
version: 0.1.0
description: Extracts evaluation scores from model responses using configurable regex

Council of LLMs - Score Extraction Filter

This outlet filter extracts evaluation scores from model responses after
they've been generated. It parses the structured format that the Evaluation
Prompt Filter instructs models to use.

Key Features:
- Regex-based score parsing from text
- User-configurable patterns via Valves
- Fallback handling for malformed responses
- Robust error handling with defaults
- Debug logging for troubleshooting

This filter runs AFTER the model generates its evaluation response,
extracting the scores and making them available to the orchestrator.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict
import re

# Import Council data structures

# ============================================================================
# INLINED SCHEMAS (from schemas.py)
# ============================================================================


from pydantic import BaseModel, Field, validator
from typing import Dict, List, Optional, Any, Literal
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
    """
    model_to_anonymous: Dict[str, str] = Field(
        default_factory=dict,
        description="Map: model_id -> anonymous_id"
    )

    anonymous_to_model: Dict[str, str] = Field(
        default_factory=dict,
        description="Map: anonymous_id -> model_id"
    )

    def add_mapping(self, model_id: str, anonymous_id: str) -> None:
        """Add a bidirectional mapping"""
        self.model_to_anonymous[model_id] = anonymous_id
        self.anonymous_to_model[anonymous_id] = model_id

    def get_model_id(self, anonymous_id: str) -> Optional[str]:
        """Get model ID from anonymous ID"""
        return self.anonymous_to_model.get(anonymous_id)

    def get_anonymous_id(self, model_id: str) -> Optional[str]:
        """Get anonymous ID from model ID"""
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


class Evaluation(BaseModel):
    """
    Single evaluation of one response by one model
    """
    evaluator_model_id: str = Field(
        ...,
        description="Model that performed the evaluation"
    )

    target_anonymous_id: str = Field(
        ...,
        description="Anonymous ID of the response being evaluated"
    )

    scores: EvaluationScores = Field(
        ...,
        description="Scores across all criteria"
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
    """
    anonymous_id: str = Field(
        ...,
        description="Anonymous ID of the response"
    )

    individual_scores: List[EvaluationScores] = Field(
        default_factory=list,
        description="All individual scores from different evaluators"
    )

    average_scores: Optional[EvaluationScores] = Field(
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

    def calculate_average(self) -> EvaluationScores:
        """Calculate average scores across all evaluators"""
        if not self.individual_scores:
            return EvaluationScores(
                accuracy=0.0,
                clarity=0.0,
                completeness=0.0,
                relevance=0.0
            )

        n = len(self.individual_scores)
        return EvaluationScores(
            accuracy=sum(s.accuracy for s in self.individual_scores) / n,
            clarity=sum(s.clarity for s in self.individual_scores) / n,
            completeness=sum(s.completeness for s in self.individual_scores) / n,
            relevance=sum(s.relevance for s in self.individual_scores) / n
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

class Filter:
    """
    Score Extraction Filter

    Parses evaluation scores from model responses.
    Patterns are user-configurable via Valves!
    """

    class Valves(BaseModel):
        """
        User-configurable score extraction patterns
        """
        PRIORITY: int = Field(
            default=10,
            description="Filter priority. Should run after model response."
        )

        # Regex patterns for score extraction
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

        # Fallback configuration
        DEFAULT_SCORE: float = Field(
            default=5.0,
            ge=0.0,
            le=10.0,
            description="Default score if parsing fails"
        )

        STRICT_MODE: bool = Field(
            default=False,
            description="If True, reject evaluations with missing scores. If False, use defaults."
        )

        ENABLE_DEBUG_LOGGING: bool = Field(
            default=False,
            description="Enable debug logging for this filter"
        )

    def __init__(self):
        """Initialize the filter"""
        self.valves = self.Valves()

    def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        """
        Outlet: Called after the model generates a response

        Extracts evaluation scores from the response text and stores
        them in the Council metadata for the orchestrator to use.

        Args:
            body: Response body containing messages, metadata, etc.
            __user__: User information (optional)

        Returns:
            Modified body with extracted scores in metadata
        """

        # Extract Council metadata
        metadata = extract_council_metadata(body)

        # Only process if in evaluation mode
        if not metadata or metadata.mode != CouncilMode.EVALUATION:
            return body

        # Get the model's response
        if not body.get("messages") or len(body["messages"]) == 0:
            if self.valves.ENABLE_DEBUG_LOGGING:
                print("[Council Score Extraction] No messages found in body")
            return body

        # Find the last assistant message (the evaluation response)
        evaluation_text = None
        for message in reversed(body["messages"]):
            if message.get("role") == "assistant":
                evaluation_text = message.get("content", "")
                break

        if not evaluation_text:
            if self.valves.ENABLE_DEBUG_LOGGING:
                print("[Council Score Extraction] No assistant message found")
            return body

        if self.valves.ENABLE_DEBUG_LOGGING:
            print(f"[Council Score Extraction] Extracting scores from response ({len(evaluation_text)} chars)")

        # Extract scores
        scores_result = self._extract_scores(evaluation_text)

        if scores_result is None:
            if self.valves.ENABLE_DEBUG_LOGGING:
                print("[Council Score Extraction] Failed to extract scores (strict mode)")
            # In strict mode, None indicates failure
            # The orchestrator should handle this appropriately
            return body

        if self.valves.ENABLE_DEBUG_LOGGING:
            print(f"[Council Score Extraction] Extracted scores: "
                  f"Acc={scores_result.accuracy:.1f}, "
                  f"Cla={scores_result.clarity:.1f}, "
                  f"Com={scores_result.completeness:.1f}, "
                  f"Rel={scores_result.relevance:.1f}")

        # Store extracted scores in metadata for orchestrator
        # The orchestrator will read this and create Evaluation objects
        if "metadata" not in body:
            body["metadata"] = {}

        body["metadata"]["extracted_scores"] = {
            "accuracy": scores_result.accuracy,
            "clarity": scores_result.clarity,
            "completeness": scores_result.completeness,
            "relevance": scores_result.relevance,
        }

        # Also extract reasoning if present
        reasoning = self._extract_reasoning(evaluation_text)
        if reasoning:
            body["metadata"]["extracted_reasoning"] = reasoning
            if self.valves.ENABLE_DEBUG_LOGGING:
                print(f"[Council Score Extraction] Extracted reasoning ({len(reasoning)} chars)")

        # Store the raw evaluation text for debugging
        body["metadata"]["raw_evaluation_text"] = evaluation_text

        return body

    def _extract_scores(self, text: str) -> Optional[EvaluationScores]:
        """
        Extract evaluation scores from text using regex patterns

        Args:
            text: Evaluation response text

        Returns:
            EvaluationScores object, or None if strict mode and scores missing
        """
        # Extract individual scores
        accuracy = self._extract_single_score(
            text,
            self.valves.ACCURACY_PATTERN,
            "accuracy"
        )

        clarity = self._extract_single_score(
            text,
            self.valves.CLARITY_PATTERN,
            "clarity"
        )

        completeness = self._extract_single_score(
            text,
            self.valves.COMPLETENESS_PATTERN,
            "completeness"
        )

        relevance = self._extract_single_score(
            text,
            self.valves.RELEVANCE_PATTERN,
            "relevance"
        )

        # Check if any scores are None (extraction failed)
        if self.valves.STRICT_MODE:
            if None in [accuracy, clarity, completeness, relevance]:
                if self.valves.ENABLE_DEBUG_LOGGING:
                    print("[Council Score Extraction] Strict mode: Some scores missing, rejecting")
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

    def _extract_single_score(
        self,
        text: str,
        pattern: str,
        score_name: str
    ) -> Optional[float]:
        """
        Extract a single score using a regex pattern

        Args:
            text: Text to search
            pattern: Regex pattern
            score_name: Name of the score (for logging)

        Returns:
            Extracted score as float, or None if not found
        """
        try:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                score_str = match.group(1).strip()
                score = float(score_str)

                if self.valves.ENABLE_DEBUG_LOGGING:
                    print(f"[Council Score Extraction] {score_name}: {score}")

                return score
            else:
                if self.valves.ENABLE_DEBUG_LOGGING:
                    print(f"[Council Score Extraction] {score_name}: not found")
                return None

        except Exception as e:
            if self.valves.ENABLE_DEBUG_LOGGING:
                print(f"[Council Score Extraction] Error extracting {score_name}: {e}")
            return None

    def _extract_reasoning(self, text: str) -> Optional[str]:
        """
        Extract reasoning text using regex pattern

        Args:
            text: Text to search

        Returns:
            Extracted reasoning, or None if not found
        """
        try:
            match = re.search(
                self.valves.REASONING_PATTERN,
                text,
                re.IGNORECASE | re.DOTALL
            )
            if match:
                reasoning = match.group(1).strip()
                return reasoning
            return None

        except Exception as e:
            if self.valves.ENABLE_DEBUG_LOGGING:
                print(f"[Council Score Extraction] Error extracting reasoning: {e}")
            return None


# Module metadata
__version__ = "0.1.0"
__author__ = "Council Pipeline Team"
__description__ = "Score extraction filter with user-configurable patterns"
