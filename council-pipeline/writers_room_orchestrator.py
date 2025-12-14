"""
title: LLM Writer's Room
author: chmodxheart
author_url: https://github.com/chmodxheart
funding_url: https://github.com/chmodxheart
version: 0.1.0
description: Multi-LLM creative writing system with peer review focused on human-like voice and style

LLM Writer's Room - Creative Writing Orchestrator Pipe

This is the core pipeline that orchestrates creative writing collaboration:
1. Query Distribution - Multiple models generate creative content
2. Anonymization - Strip model identifiers for unbiased review
3. Peer Evaluation - All models evaluate writing on voice, emotion, originality, etc.
4. Score Aggregation - Rank creative outputs
5. Synthesis - Lead model creates polished final version

Evaluation criteria are specifically designed for creative writing:
- Voice Authenticity (avoid LLM artifacts)
- Emotional Resonance (show don't tell)
- Originality & Risk-Taking (avoid clichés)
- Style Consistency (match the brief)
- Narrative Coherence
- Dialogue Naturalness (if applicable)

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
from schemas import (
    CouncilMetadata,
    CouncilMode,
    ModelResponse,
    ModelParameters,
    AnonymousResponseMapping,
    Evaluation,
    EvaluationScores,
    CreativeWritingScores,
    AggregatedScores,
    SynthesisInput,
    create_council_metadata,
    extract_council_metadata,
    inject_council_metadata,
)


class Pipe:
    """
    LLM Writer's Room Orchestrator Pipe

    Creative writing workflow controller that coordinates:
    - Multi-model creative generation
    - Anonymous peer review with creative writing rubrics
    - Evaluation focused on voice, emotion, and originality
    - Synthesis that maintains human-like writing quality
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
        # Creative Writing Evaluation Configuration
        # ============================================================
        EVALUATION_WEIGHT_VOICE_AUTHENTICITY: float = Field(
            default=0.25,
            ge=0.0,
            le=1.0,
            description="Weight for voice authenticity (human-like, avoids LLM artifacts)"
        )

        EVALUATION_WEIGHT_EMOTIONAL_RESONANCE: float = Field(
            default=0.20,
            ge=0.0,
            le=1.0,
            description="Weight for emotional resonance (show don't tell, evokes feelings)"
        )

        EVALUATION_WEIGHT_ORIGINALITY: float = Field(
            default=0.20,
            ge=0.0,
            le=1.0,
            description="Weight for originality & risk-taking (avoids clichés, fresh metaphors)"
        )

        EVALUATION_WEIGHT_STYLE_CONSISTENCY: float = Field(
            default=0.15,
            ge=0.0,
            le=1.0,
            description="Weight for style consistency (matches project brief/voice bible)"
        )

        EVALUATION_WEIGHT_NARRATIVE_COHERENCE: float = Field(
            default=0.15,
            ge=0.0,
            le=1.0,
            description="Weight for narrative coherence (clear through-line, good pacing)"
        )

        EVALUATION_WEIGHT_LLM_ARTIFACT_AVOIDANCE: float = Field(
            default=0.05,
            ge=0.0,
            le=1.0,
            description="Weight for LLM artifact avoidance (penalizes AI-sounding phrases)"
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
            le=180,
            description="Timeout for individual model queries (seconds)"
        )

        EVAL_TIMEOUT_SECONDS: int = Field(
            default=90,
            ge=5,
            le=300,
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
            default="self_revision",
            description="Synthesis mode: 'self_revision' (each model revises its own work based on critiques), 'full' (synthesize from all responses), 'highest_rated' (return only the top-scoring response), 'none' (show responses and scores only, no synthesis)"
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
            description="Request models to generate multiple response variants with probability scores"
        )

        VERBALIZED_SAMPLING_COUNT: int = Field(
            default=5,
            ge=1,
            le=10,
            description="Number of response variants when QUERY_USE_VERBALIZED_SAMPLING enabled"
        )

        VERBALIZED_SAMPLING_SELECTION_STRATEGY: str = Field(
            default="best_per_model",
            description="Selection strategy: 'best_per_model' (keep top from each model) or 'top_n_overall' (keep top N regardless of source)"
        )

        VERBALIZED_SAMPLING_TOP_N: int = Field(
            default=5,
            ge=1,
            description="Top N responses to keep when using 'top_n_overall' selection strategy"
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
        # Score Parsing Patterns - Creative Writing Criteria
        # ============================================================
        VOICE_AUTHENTICITY_PATTERN: str = Field(
            default=r"VOICE[_\s]*AUTHENTICITY\s*:?\s*(\d+(?:\.\d+)?)",
            description="Regex pattern to extract voice authenticity score (flexible format)"
        )

        EMOTIONAL_RESONANCE_PATTERN: str = Field(
            default=r"EMOTIONAL[_\s]*RESONANCE\s*:?\s*(\d+(?:\.\d+)?)",
            description="Regex pattern to extract emotional resonance score (flexible format)"
        )

        ORIGINALITY_PATTERN: str = Field(
            default=r"ORIGINALITY\s*:?\s*(\d+(?:\.\d+)?)",
            description="Regex pattern to extract originality score (flexible format)"
        )

        STYLE_CONSISTENCY_PATTERN: str = Field(
            default=r"STYLE[_\s]*CONSISTENCY\s*:?\s*(\d+(?:\.\d+)?)",
            description="Regex pattern to extract style consistency score (flexible format)"
        )

        NARRATIVE_COHERENCE_PATTERN: str = Field(
            default=r"NARRATIVE[_\s]*COHERENCE\s*:?\s*(\d+(?:\.\d+)?)",
            description="Regex pattern to extract narrative coherence score (flexible format)"
        )

        LLM_ARTIFACT_AVOIDANCE_PATTERN: str = Field(
            default=r"LLM[_\s]*ARTIFACT[_\s]*AVOIDANCE\s*:?\s*(\d+(?:\.\d+)?)",
            description="Regex pattern to extract LLM artifact avoidance score (flexible format)"
        )

        REASONING_PATTERN: str = Field(
            default=r"REASONING:\s*(.+)",
            description="Regex pattern to extract reasoning text (captures everything after REASONING:)"
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
            yield "Writer's Room Session"
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
            yield f"[ERROR] Writer's Room requires at least {self.valves.MIN_MODELS_REQUIRED} models. Currently configured: {len(self.available_models)}.\n\n"
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

        # Check if we have any successful evaluations
        if not metadata.aggregated_scores:
            error_msg = (
                "❌ FATAL ERROR: All evaluations failed. Cannot proceed with ranking or synthesis.\n\n"
                "Possible causes:\n"
                "- Evaluation models are not responding\n"
                "- Score parsing is failing (models not following the required format)\n"
                "- API authentication issues\n\n"
                "Try enabling DEBUG_MODE in valves to see detailed error messages."
            )
            if self.valves.DEBUG_MODE:
                print(f"[Council] {error_msg}")
            return error_msg

        ranked_responses = self._rank_responses(
            successful_responses,
            metadata.aggregated_scores
        )

        # Apply selection strategy (filters responses for verbalized sampling)
        ranked_responses = self._apply_selection_strategy(
            ranked_responses,
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
            yield f"## 🔄 Querying Writer's Room Models\n\n"
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
            # Check if verbalized sampling was used
            has_variants = any(r.response_index is not None for r in successful_responses)
            if has_variants:
                unique_models = len(set(r.model_id for r in successful_responses))
                yield f"✓ Received {len(successful_responses)} total response variants from {unique_models} models"
            else:
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
            has_variants = any(r.response_index is not None for r in successful_responses)

            yield f"✓ Collected {len(evaluations)}/{expected_evals} evaluations (gathered in parallel with queries)"

            # Add context if verbalized sampling
            if has_variants:
                unique_models = len(set(r.model_id for r in successful_responses))
                variants_per_model = len(successful_responses) // unique_models if unique_models > 0 else 0
                yield f" ({unique_models} models × {variants_per_model} variants × {len(self.evaluation_models)} evaluators)"

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

            # Create reverse mapping (anonymous_id -> real model_id) for de-anonymization
            reverse_mapping = {anon_id: model_id for model_id, anon_id in metadata.anonymous_mapping.model_to_anonymous.items()}

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
                    yield f"- **Voice Authenticity**: {ev.scores.voice_authenticity:.1f}/10\n"
                    yield f"- **Emotional Resonance**: {ev.scores.emotional_resonance:.1f}/10\n"
                    yield f"- **Originality**: {ev.scores.originality:.1f}/10\n"
                    yield f"- **Style Consistency**: {ev.scores.style_consistency:.1f}/10\n"
                    yield f"- **Narrative Coherence**: {ev.scores.narrative_coherence:.1f}/10\n"
                    yield f"- **LLM Artifact Avoidance**: {ev.scores.llm_artifact_avoidance:.1f}/10\n\n"
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

        # Check if we have any successful evaluations
        if not metadata.aggregated_scores:
            yield "❌ **FATAL ERROR**: All evaluations failed. Cannot proceed with ranking or synthesis.\n\n"
            yield "**Possible causes:**\n"
            yield "- Evaluation models are not responding\n"
            yield "- Score parsing is failing (models not following the required format)\n"
            yield "- API authentication issues\n\n"
            yield "**Try enabling DEBUG_MODE in valves to see detailed error messages.**\n\n"
            return

        ranked_responses = self._rank_responses(
            successful_responses,
            metadata.aggregated_scores
        )

        # Apply selection strategy (filters responses for verbalized sampling)
        ranked_responses = self._apply_selection_strategy(
            ranked_responses,
            metadata.aggregated_scores
        )

        # Show evaluation summary if enabled
        if self.valves.SHOW_EVALUATION_SCORES:
            # Create reverse mapping for de-anonymization
            reverse_mapping = {anon_id: model_id for model_id, anon_id in metadata.anonymous_mapping.model_to_anonymous.items()}

            yield "<details>\n<summary>🏆 Evaluation Summary</summary>\n\n"
            for i, response in enumerate(ranked_responses, 1):
                agg = metadata.aggregated_scores[response.anonymous_id]
                # De-anonymize for user display
                real_model_id = reverse_mapping.get(response.anonymous_id, response.anonymous_id)
                yield f"**Rank {i}** - **{real_model_id}**: "
                yield f"**{agg.weighted_total:.2f}/10** "
                yield f"(from {agg.evaluator_count} evaluators)"

                # Add variant info if verbalized sampling
                if response.response_index is not None:
                    yield f" [variant {response.response_index}"
                    if response.probability is not None:
                        yield f", p={response.probability:.2f}"
                    yield "]"

                yield "\n\n"
                if agg.average_scores:
                    yield f"  - Voice Authenticity: {agg.average_scores.voice_authenticity:.1f}\n"
                    yield f"  - Emotional Resonance: {agg.average_scores.emotional_resonance:.1f}\n"
                    yield f"  - Originality: {agg.average_scores.originality:.1f}\n"
                    yield f"  - Style Consistency: {agg.average_scores.style_consistency:.1f}\n"
                    yield f"  - Narrative Coherence: {agg.average_scores.narrative_coherence:.1f}\n"
                    yield f"  - LLM Artifact Avoidance: {agg.average_scores.llm_artifact_avoidance:.1f}\n\n"
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

        # Create reverse mapping for de-anonymization in output
        reverse_mapping = {anon_id: model_id for model_id, anon_id in metadata.anonymous_mapping.model_to_anonymous.items()}

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
            yield "## 💡 Writer's Room Final Draft\n\n"
            yield f"*Selected response from **{top_model}** (Score: {top_score:.2f}/10)*\n\n"
            yield top_response.content
            yield "\n\n"

            final_answer = top_response.content

        elif synthesis_mode == "self_revision":
            # Self-revision mode: each model revises its own work based on critiques
            if self.valves.SHOW_PROGRESS:
                yield "## ✍️ Self-Revision Round\n\n"
                yield f"Each model is revising its draft based on peer critiques...\n\n"

            # Run self-revision for all models
            top_revised = await self._self_revision_round(
                user_message,
                successful_responses,
                metadata.evaluations,
                metadata.aggregated_scores,
                messages,
                request,
                user,
                metadata
            )

            # Get the model name for display
            top_model = reverse_mapping.get(top_revised.anonymous_id, top_revised.anonymous_id)
            original_score = metadata.aggregated_scores[top_revised.anonymous_id].weighted_total

            yield "---\n\n"
            yield "## 💡 Writer's Room Final Draft\n\n"
            yield f"*Revised draft from **{top_model}** (Original score: {original_score:.2f}/10)*\n\n"
            yield top_revised.content
            yield "\n\n"

            final_answer = top_revised.content

        else:
            # Full synthesis mode
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
            yield "## 💡 Writer's Room Final Draft\n\n"
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

        yield f"*Writer's Room session completed in {duration:.1f}s • {self.token_usage:,} tokens used*\n"

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
        """Get creative writing evaluation criteria weights from Valves"""
        return {
            "voice_authenticity": self.valves.EVALUATION_WEIGHT_VOICE_AUTHENTICITY,
            "emotional_resonance": self.valves.EVALUATION_WEIGHT_EMOTIONAL_RESONANCE,
            "originality": self.valves.EVALUATION_WEIGHT_ORIGINALITY,
            "style_consistency": self.valves.EVALUATION_WEIGHT_STYLE_CONSISTENCY,
            "narrative_coherence": self.valves.EVALUATION_WEIGHT_NARRATIVE_COHERENCE,
            "llm_artifact_avoidance": self.valves.EVALUATION_WEIGHT_LLM_ARTIFACT_AVOIDANCE,
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
        """Build system message for creative writing generation"""
        instructions = []

        instructions.append("You are participating in a Writer's Room - a collaborative creative writing session with multiple AI writers.")
        instructions.append("Your goal is to produce human-like, emotionally resonant creative writing that avoids generic AI patterns.")

        # Add technique-specific instructions
        if self.valves.QUERY_USE_HERMENEUTIC_CIRCLE:
            instructions.append("\n**Hermeneutic Circle Approach:**")
            instructions.append("Apply the hermeneutic circle to creative writing: each scene detail should illuminate the whole emotional arc, and the whole story context should give meaning to each specific moment. Let the reader's understanding build through this interplay of part and whole.")

        if self.valves.QUERY_USE_CHAIN_OF_THOUGHT:
            instructions.append("\n**Narrative Development:**")
            instructions.append("Build the scene step by step. Consider: What's the emotional core? What sensory details ground the reader? How do we show (not tell) the character's state? What specific moments carry the most weight?")

        if self.valves.QUERY_USE_VERBALIZED_SAMPLING:
            count = self.valves.VERBALIZED_SAMPLING_COUNT
            instructions.append(f"\n**Creative Exploration (Multiple Variants):**")
            instructions.append(
                f"Generate exactly {count} different creative approaches to this request. "
                f"For each approach, provide a complete response within a <response> tag containing:\n"
                f"  - <text>Your full creative content</text>\n"
                f"  - <probability>A decimal between 0.0-0.10 representing how unusual/risky this approach is</probability>\n\n"
                f"Sample from the tails of the distribution - avoid safe, predictable responses. "
                f"Each variant should explore different: imagery, tone, metaphors, narrative choices, stylistic risks.\n\n"
                f"Format example:\n"
                f"<response>\n"
                f"  <text>First creative variant here...</text>\n"
                f"  <probability>0.08</probability>\n"
                f"</response>\n"
                f"<response>\n"
                f"  <text>Second creative variant here...</text>\n"
                f"  <probability>0.06</probability>\n"
                f"</response>\n"
                f"...and so on for all {count} variants."
            )

        instructions.append("\n**Creative Writing Standards:**")
        instructions.append("- Write in a distinctive, human-like voice with personality and idiosyncrasies")
        instructions.append("- Use concrete sensory details and specific images rather than abstractions")
        instructions.append("- Show emotions through action, dialogue, and subtext rather than stating them")
        instructions.append("- Avoid LLM artifacts: no meta-commentary, no hedging ('perhaps', 'somewhat'), no generic transitions")
        instructions.append("- Take creative risks - unusual metaphors and surprising choices are better than safe, predictable prose")
        instructions.append("- Make every word earn its place - cut anything that sounds like filler")

        instructions.append("\n**⚠️ Avoid LLM Slop Patterns:**")
        instructions.append("Actively avoid these overused AI writing patterns:")
        instructions.append("- Physical clichés: 'heart pounding', 'breath hitched', 'eyes widened', 'mind racing'")
        instructions.append("- Atmospheric words: 'shimmered', 'palpable', 'ethereal', 'tendrils', 'wisps'")
        instructions.append("- Over-descriptive verbs: 'beckoned', 'whispered', 'murmured', 'trembled', 'flickered'")
        instructions.append("- Adverb abuse: 'cautiously', 'carefully', 'slowly', 'gently', 'barely'")
        instructions.append("- Generic phrases: 'felt a strange sense', 'couldn't shake the feeling', 'something stirred'")
        instructions.append("- Rhetorical negations: 'Not X, but Y', 'This is not X. It is Y.', 'Not out of X, but out of Y'")
        instructions.append("- Use fresh, specific descriptions instead of these tired patterns")

        return "\n".join(instructions)

    def _build_evaluation_prompt(self, response_text: str) -> str:
        """Build creative writing evaluation prompt"""
        sections = []

        # Opening
        sections.append("You are an experienced fiction editor participating in a Writer's Room peer review.")
        sections.append("Your task is to evaluate creative writing for human-like quality, emotional impact, and originality.")
        sections.append("Be tough on AI-sounding phrases, clichés, and generic patterns.")
        sections.append("")

        # Prompting techniques
        if self.valves.EVAL_USE_HERMENEUTIC_CIRCLE:
            sections.append("**Hermeneutic Circle Approach:**")
            sections.append("Evaluate how each specific detail (word choice, image, beat) contributes to the whole emotional arc, and how the overall tone and purpose illuminate each part. Does the piece hold together as a unified artistic vision?")
            sections.append("")

        if self.valves.EVAL_USE_VERBALIZED_SAMPLING:
            sections.append("**Show Your Thinking:**")
            sections.append("Reveal your editorial thought process. What grabbed you? What felt flat? Where did you notice AI patterns? What specific lines or moments work well or poorly?")
            sections.append("")

        if self.valves.EVAL_USE_SOCRATIC_QUESTIONING:
            sections.append("**Socratic Examination:**")
            sections.append("Probe the writing deeply:")
            sections.append("- Does it SHOW emotions or just TELL us about them?")
            sections.append("- Are the images concrete and specific, or vague and abstract?")
            sections.append("- Does dialogue sound like real people, or exposition in disguise?")
            sections.append("- What makes this feel human vs. machine-generated?")
            sections.append("")

        if self.valves.EVAL_USE_ADVERSARIAL_STANCE:
            sections.append("**Critical Editorial Analysis:**")
            sections.append("Actively hunt for creative weaknesses:")
            sections.append("- Where does it fall into LLM clichés or safe choices?")
            sections.append("- What metaphors or phrasings feel generic or overused?")
            sections.append("- Where does it hedge, over-explain, or break voice?")
            sections.append("- What creative risks did it AVOID taking?")
            sections.append("")

        if self.valves.EVAL_USE_CONSTITUTIONAL_PRINCIPLES:
            sections.append("**Principle-Based Justification:**")
            sections.append("Ground your scores in specific craft principles. For each score, cite concrete examples from the text. Don't just rate—show exactly what works or doesn't work.")
            sections.append("")

        # Creative Writing Evaluation Criteria
        sections.append("**CREATIVE WRITING EVALUATION CRITERIA** (Rate each 1-10, where 1=poor, 10=excellent):")
        sections.append("")
        sections.append("1. **VOICE_AUTHENTICITY** (Human-Like Voice)")
        sections.append("   - Does this read like a specific human wrote it, with personality and idiosyncrasies?")
        sections.append("   - Or does it sound like generic AI output?")
        sections.append("   - PENALIZE: hedging ('perhaps', 'somewhat'), meta-commentary, over-explanation")
        sections.append("   - REWARD: distinctive word choices, consistent quirks, authentic tone")
        sections.append("")
        sections.append("2. **EMOTIONAL_RESONANCE** (Evokes Feelings)")
        sections.append("   - Does it make the reader FEEL something, not just understand something?")
        sections.append("   - Uses concrete sensory details and interiority vs. abstract emotion words?")
        sections.append("   - Shows subtext and lets emotions breathe vs. spelling everything out?")
        sections.append("   - PENALIZE: 'telling' emotions ('she felt sad'); abstract statements")
        sections.append("   - REWARD: specific sensory details; actions that imply emotion; interiority")
        sections.append("")
        sections.append("3. **ORIGINALITY** (Risk-Taking & Freshness)")
        sections.append("   - Avoids stock phrases, predictable beats, and clichéd metaphors?")
        sections.append("   - Takes creative risks with unusual images or surprising choices?")
        sections.append("   - Feels fresh and unexpected vs. safe and generic?")
        sections.append("   - PENALIZE: clichés ('her heart raced'); predictable plot beats; safe word choices")
        sections.append("   - REWARD: unusual but fitting metaphors; surprising narrative choices; bold style")
        sections.append("")
        sections.append("4. **STYLE_CONSISTENCY** (Matches the Brief)")
        sections.append("   - Maintains consistent voice and tone throughout?")
        sections.append("   - Matches the requested style or genre conventions?")
        sections.append("   - Appropriate register and narrative distance?")
        sections.append("   - PENALIZE: tonal inconsistency; breaking voice; mismatched register")
        sections.append("   - REWARD: unified style; consistent perspective; genre-appropriate choices")
        sections.append("")
        sections.append("5. **NARRATIVE_COHERENCE** (Structure & Flow)")
        sections.append("   - Has clear through-line and purpose?")
        sections.append("   - Pacing is appropriate and transitions are smooth?")
        sections.append("   - Doesn't try to resolve everything tidily if that breaks the aesthetic?")
        sections.append("   - PENALIZE: confusing jumps; rushed or dragging pacing; forced conclusions")
        sections.append("   - REWARD: natural flow; purposeful structure; satisfying arc")
        sections.append("")
        sections.append("6. **LLM_ARTIFACT_AVOIDANCE** (Doesn't Sound Like AI)")
        sections.append("   - Explicitly: Does this sound like an AI wrote it?")
        sections.append("   - Check for common slop patterns:")
        sections.append("     * Overused verbs: shimmered, flickered, whispered, murmured, trembled, beckoned")
        sections.append("     * Physical clichés: heart pounding, breath hitched, eyes widened, mind racing")
        sections.append("     * Atmospheric words: palpable, ethereal, tendrils, cascade, wisps")
        sections.append("     * Generic phrases: felt strange sense, couldn't shake feeling, something stirred")
        sections.append("     * Rhetorical negations: 'Not X, but Y', 'This is not X. It is Y.', 'Not out of X, but out of Y'")
        sections.append("   - Also check for: generic transitions ('overall', 'in conclusion'), balanced structures ('on one hand...'), weak intensifiers ('very', 'really'), meta-signposting")
        sections.append("   - PENALIZE heavily for slop density - multiple slop patterns = AI-generated feel")
        sections.append("   - REWARD: natural rhythm; varied sentence structure; confident choices without hedging; fresh language")
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
        sections.append("VOICE_AUTHENTICITY: [your score 1-10]")
        sections.append("EMOTIONAL_RESONANCE: [your score 1-10]")
        sections.append("ORIGINALITY: [your score 1-10]")
        sections.append("STYLE_CONSISTENCY: [your score 1-10]")
        sections.append("NARRATIVE_COHERENCE: [your score 1-10]")
        sections.append("LLM_ARTIFACT_AVOIDANCE: [your score 1-10]")
        sections.append("REASONING: [Provide a DETAILED editorial analysis explaining your scores. Include:")
        sections.append("  - Specific lines or moments that work well or poorly")
        sections.append("  - Concrete examples of LLM artifacts or fresh creative choices")
        sections.append("  - How well it achieves human-like voice and emotional impact")
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
        sections.append("You are a lead editor in a Writer's Room, synthesizing multiple creative drafts into a polished final piece.")
        sections.append("")
        sections.append("You have ALL drafts (ranked from best to worst by anonymous peer editorial review), showing both successful creative choices AND common pitfalls to avoid.")
        sections.append("")

        # Meta-cognitive technique
        if self.valves.SYNTH_USE_META_COGNITIVE:
            sections.append("**Editorial Reflection:**")
            sections.append("As you synthesize, reflect on:")
            sections.append("- Which creative choices feel fresh and human vs. generic AI?")
            sections.append("- Where do drafts agree on emotional beats vs. take different approaches?")
            sections.append("- What risky creative choices work vs. which fall flat?")
            sections.append("- How can you maintain voice authenticity while improving on the drafts?")
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
                sections.append(f"- Voice Authenticity: {agg.average_scores.voice_authenticity:.1f}/10")
                sections.append(f"- Emotional Resonance: {agg.average_scores.emotional_resonance:.1f}/10")
                sections.append(f"- Originality: {agg.average_scores.originality:.1f}/10")
                sections.append(f"- Style Consistency: {agg.average_scores.style_consistency:.1f}/10")
                sections.append(f"- Narrative Coherence: {agg.average_scores.narrative_coherence:.1f}/10")
                sections.append(f"- LLM Artifact Avoidance: {agg.average_scores.llm_artifact_avoidance:.1f}/10")
            else:
                sections.append(f"### Response #{i}")

            sections.append(f"**Content:**")
            sections.append(response.content)
            sections.append("")
            sections.append("---")
            sections.append("")

        # Synthesis task
        sections.append("**YOUR EDITORIAL SYNTHESIS TASK:**")
        sections.append("")
        sections.append("⚠️ **CRITICAL: DO NOT simply copy one of the drafts verbatim. You MUST synthesize.**")
        sections.append("")
        sections.append("Create a final polished piece that:")
        sections.append("")
        sections.append("1. **Learns from Success**: Extract the most human-sounding moments, vivid images, and authentic voice from top drafts")
        sections.append("2. **Avoids Pitfalls**: Learn what didn't work in lower-rated drafts (LLM artifacts, clichés, telling vs. showing)")
        sections.append("3. **Synthesizes, Not Copies**: Weave the best creative choices into a unified voice—NEVER just return one draft unchanged")
        sections.append("4. **Elevates the Writing**: Your synthesis should feel more human, more emotionally resonant, and more original than any single draft")
        sections.append("5. **Handles Divergence**: If drafts take different creative approaches, choose the freshest one or combine complementary strengths")
        sections.append("6. **Maintains Consistency**: Ensure the final piece has one coherent voice and emotional arc")
        sections.append("")
        sections.append("Remember: Even if one draft is perfect, make at least subtle improvements to justify the synthesis process.")
        sections.append("")

        sections.append("**CREATIVE WRITING STANDARDS:**")
        sections.append("")
        sections.append("- **Voice Authenticity**: Write in a distinctive, human voice—avoid generic AI patterns")
        sections.append("- **Emotional Resonance**: Show emotions through concrete details, not abstract statements")
        sections.append("- **Originality**: Use fresh images and bold choices—avoid stock phrases and safe writing")
        sections.append("- **Style Consistency**: Maintain consistent tone, register, and narrative distance")
        sections.append("- **Narrative Coherence**: Clear structure and smooth flow without forced tidy endings")
        sections.append("- **No LLM Artifacts**: Cut hedging, meta-commentary, generic transitions, and overly balanced structures")
        sections.append("")
        sections.append("**⚠️ AVOID LLM SLOP PATTERNS:**")
        sections.append("- Physical clichés: 'heart pounding', 'breath hitched', 'eyes widened', 'mind racing'")
        sections.append("- Atmospheric words: 'shimmered', 'palpable', 'ethereal', 'tendrils', 'wisps'")
        sections.append("- Overused verbs: 'beckoned', 'whispered', 'murmured', 'trembled', 'flickered'")
        sections.append("- Generic phrases: 'felt strange sense', 'couldn't shake feeling', 'something stirred'")
        sections.append("- Replace these with fresh, specific language that sounds human-written")
        sections.append("")

        sections.append("**Output your synthesized creative piece below:**")

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
                # NOTE: Now returns List[ModelResponse] instead of single ModelResponse
                response_list = await coro

                # Track anonymous IDs for this model
                model_anonymous_ids = []

                for response in response_list:
                    # Anonymous ID already assigned in _query_single_model()
                    if response.success:
                        model_anonymous_ids.append(response.anonymous_id)

                        # Spawn evaluation tasks for this response
                        for evaluator_model_id in self.evaluation_models:
                            eval_task = self._query_for_evaluation(
                                evaluator_model_id=evaluator_model_id,
                                target_response=response,
                                params=model_params.get(evaluator_model_id, model_params[self.available_models[0]]),
                                request=request,
                                user=user,
                                metadata=metadata
                            )
                            evaluation_tasks.append(eval_task)

                    all_responses.append(response)

                # Update anonymous mapping
                if len(model_anonymous_ids) == 1:
                    # Single response (backwards compatible)
                    metadata.anonymous_mapping.add_mapping(
                        response_list[0].model_id,
                        model_anonymous_ids[0]
                    )
                elif len(model_anonymous_ids) > 1:
                    # Multiple responses from verbalized sampling
                    metadata.anonymous_mapping.add_multi_mapping(
                        response_list[0].model_id,
                        model_anonymous_ids
                    )
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

    async def _query_single_model_raw(
        self,
        model_id: str,
        messages: List[dict],
        params: ModelParameters,
        request: Any,
        user: Optional[dict],
    ) -> ModelResponse:
        """
        Query a single model via Open WebUI API (raw response)

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

    async def _query_single_model(
        self,
        model_id: str,
        messages: List[dict],
        params: ModelParameters,
        request: Any,
        user: Optional[dict],
    ) -> List[ModelResponse]:
        """
        Query a single model and return one or more ModelResponse objects.

        When verbalized sampling is enabled, parses multiple response variants.
        Otherwise returns single response (current behavior).

        Returns:
            List[ModelResponse]: One or more responses (always non-empty if successful)
        """
        # Call existing query logic
        raw_response = await self._query_single_model_raw(
            model_id, messages, params, request, user
        )

        # If query failed, return single failed response
        if not raw_response.success:
            return [raw_response]

        # If verbalized sampling is disabled, return single response
        if not self.valves.QUERY_USE_VERBALIZED_SAMPLING:
            return [raw_response]

        # Try to parse multiple responses
        parsed_variants = self._parse_verbalized_sampling_responses(raw_response.content)

        # If parsing failed or returned no variants, fall back to single response
        if not parsed_variants:
            if self.valves.DEBUG_MODE:
                print(f"[Writer's Room] {model_id}: Verbalized sampling enabled but no <response> tags found. Falling back to single response.")
            return [raw_response]

        # Create ModelResponse for each variant
        import secrets
        responses = []

        for variant in parsed_variants:
            variant_response = ModelResponse(
                model_id=model_id,
                content=variant["text"],  # Clean text without XML tags
                success=True,
                response_index=variant["index"],
                probability=variant["probability"],
                tokens_used=None,  # Will be distributed across variants in token tracking
                latency_ms=raw_response.latency_ms / len(parsed_variants) if raw_response.latency_ms else None,  # Approximate per-variant latency
                parameters=raw_response.parameters,
                anonymous_id=f"response_{secrets.token_hex(4)}"  # Unique ID for each variant
            )
            responses.append(variant_response)

        if self.valves.DEBUG_MODE:
            print(f"[Writer's Room] {model_id}: Generated {len(responses)} variants via verbalized sampling")

        return responses

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

    def _parse_verbalized_sampling_responses(self, raw_text: str) -> List[Dict[str, Any]]:
        """
        Extract multiple <response> blocks from verbalized sampling output.

        Expected format:
        <response>
          <text>The actual creative content here...</text>
          <probability>0.08</probability>
        </response>
        <response>
          <text>Another variant...</text>
          <probability>0.07</probability>
        </response>

        Returns:
            List of dicts with 'text', 'probability', and 'index' keys.
            Empty list if no valid responses found (triggers fallback).
        """
        if self.valves.DEBUG_MODE:
            print(f"[Writer's Room] Parsing verbalized sampling responses...")

        response_pattern = r'<response>(.*?)</response>'
        responses = []

        for idx, match in enumerate(re.finditer(response_pattern, raw_text, re.DOTALL | re.IGNORECASE), 1):
            response_block = match.group(1)

            # Extract text
            text_match = re.search(r'<text>(.*?)</text>', response_block, re.DOTALL | re.IGNORECASE)
            if not text_match:
                if self.valves.DEBUG_MODE:
                    print(f"[Writer's Room] Response {idx}: No <text> tag found, skipping")
                continue

            text = text_match.group(1).strip()
            if not text:
                if self.valves.DEBUG_MODE:
                    print(f"[Writer's Room] Response {idx}: Empty text, skipping")
                continue

            # Extract probability (optional)
            probability = None
            prob_match = re.search(r'<probability>(.*?)</probability>', response_block, re.DOTALL | re.IGNORECASE)
            if prob_match:
                try:
                    probability = float(prob_match.group(1).strip())
                    probability = max(0.0, min(1.0, probability))  # Clamp to [0, 1]
                except (ValueError, TypeError):
                    if self.valves.DEBUG_MODE:
                        print(f"[Writer's Room] Response {idx}: Invalid probability value, setting to None")

            responses.append({
                "text": text,
                "probability": probability,
                "index": idx
            })

        if self.valves.DEBUG_MODE:
            print(f"[Writer's Room] Parsed {len(responses)} response variants")

        return responses

    def _parse_scores(self, text: str) -> Optional[CreativeWritingScores]:
        """
        Parse creative writing evaluation scores from text using regex patterns from Valves

        Returns CreativeWritingScores or None if strict mode and scores missing
        """
        # Extract individual creative writing scores
        voice = self._extract_single_score(text, self.valves.VOICE_AUTHENTICITY_PATTERN, "voice_authenticity")
        emotion = self._extract_single_score(text, self.valves.EMOTIONAL_RESONANCE_PATTERN, "emotional_resonance")
        original = self._extract_single_score(text, self.valves.ORIGINALITY_PATTERN, "originality")
        style = self._extract_single_score(text, self.valves.STYLE_CONSISTENCY_PATTERN, "style_consistency")
        coherence = self._extract_single_score(text, self.valves.NARRATIVE_COHERENCE_PATTERN, "narrative_coherence")
        no_artifacts = self._extract_single_score(text, self.valves.LLM_ARTIFACT_AVOIDANCE_PATTERN, "llm_artifact_avoidance")

        # Check if any scores are None
        if self.valves.STRICT_SCORE_PARSING:
            if None in [voice, emotion, original, style, coherence, no_artifacts]:
                if self.valves.DEBUG_MODE:
                    print("[Writer's Room] Strict mode: Some scores missing, rejecting")
                return None

        # Use defaults for missing scores in non-strict mode
        voice = voice if voice is not None else self.valves.DEFAULT_SCORE
        emotion = emotion if emotion is not None else self.valves.DEFAULT_SCORE
        original = original if original is not None else self.valves.DEFAULT_SCORE
        style = style if style is not None else self.valves.DEFAULT_SCORE
        coherence = coherence if coherence is not None else self.valves.DEFAULT_SCORE
        no_artifacts = no_artifacts if no_artifacts is not None else self.valves.DEFAULT_SCORE

        # Clamp scores to valid range (0-10)
        voice = max(0.0, min(10.0, voice))
        emotion = max(0.0, min(10.0, emotion))
        original = max(0.0, min(10.0, original))
        style = max(0.0, min(10.0, style))
        coherence = max(0.0, min(10.0, coherence))
        no_artifacts = max(0.0, min(10.0, no_artifacts))

        # Return proper CreativeWritingScores with all 6 fields
        return CreativeWritingScores(
            voice_authenticity=voice,
            emotional_resonance=emotion,
            originality=original,
            style_consistency=style,
            narrative_coherence=coherence,
            llm_artifact_avoidance=no_artifacts
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

    def _apply_selection_strategy(
        self,
        ranked_responses: List[ModelResponse],
        aggregated_scores: Dict[str, AggregatedScores],
    ) -> List[ModelResponse]:
        """
        Apply selection strategy to filter responses for synthesis.

        Strategies:
        - 'best_per_model': Keep highest-scoring response from each source model
        - 'top_n_overall': Keep top N responses overall (configured by VERBALIZED_SAMPLING_TOP_N)

        Only applies when verbalized sampling is enabled. Otherwise returns all responses.
        """
        if not self.valves.QUERY_USE_VERBALIZED_SAMPLING:
            return ranked_responses

        # Check if any responses have response_index set (indicates verbalized sampling was used)
        has_variants = any(r.response_index is not None for r in ranked_responses)
        if not has_variants:
            return ranked_responses

        strategy = self.valves.VERBALIZED_SAMPLING_SELECTION_STRATEGY

        if strategy == "best_per_model":
            # Group by source model, take highest-scoring from each
            model_groups = {}
            for response in ranked_responses:
                if response.model_id not in model_groups:
                    model_groups[response.model_id] = []
                model_groups[response.model_id].append(response)

            selected = []
            for model_id, responses in model_groups.items():
                # Sort by score, take best
                best = max(responses, key=lambda r: aggregated_scores[r.anonymous_id].weighted_total)
                selected.append(best)

            # Re-sort by score
            selected.sort(
                key=lambda r: aggregated_scores[r.anonymous_id].weighted_total,
                reverse=True
            )

            if self.valves.DEBUG_MODE:
                print(f"[Writer's Room] Selection strategy 'best_per_model': {len(ranked_responses)} -> {len(selected)} responses")

            return selected

        elif strategy == "top_n_overall":
            top_n = self.valves.VERBALIZED_SAMPLING_TOP_N
            selected = ranked_responses[:top_n]

            if self.valves.DEBUG_MODE:
                print(f"[Writer's Room] Selection strategy 'top_n_overall': {len(ranked_responses)} -> {len(selected)} responses")

            return selected

        else:
            # Unknown strategy, return all
            if self.valves.DEBUG_MODE:
                print(f"[Writer's Room] Unknown selection strategy '{strategy}', returning all responses")
            return ranked_responses

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

    async def _self_revision_round(
        self,
        original_question: str,
        all_responses: List[ModelResponse],
        evaluations: List[Evaluation],
        aggregated_scores: Dict[str, AggregatedScores],
        messages: List[dict],
        request: Any,
        user: Optional[dict],
        metadata: CouncilMetadata,
    ) -> ModelResponse:
        """
        Self-revision: Each model revises its own work based on peer critiques

        Returns the highest-rated revised response
        """
        try:
            # Get base URL and auth token
            base_url = f"{request.url.scheme}://{request.url.netloc}" if request else "http://localhost:3000"
            auth_token = self._extract_token(request)

            if not auth_token:
                if self.valves.DEBUG_MODE:
                    print(f"[Writer's Room] No auth token for revision, returning top-rated original")
                # Return highest-rated original
                top_response = max(all_responses, key=lambda r: aggregated_scores[r.anonymous_id].weighted_total)
                return top_response

            # Create revision tasks for all models
            revision_tasks = []
            for response in all_responses:
                # Get all evaluations for this response
                response_evals = [e for e in evaluations if e.target_anonymous_id == response.anonymous_id]

                # Build revision prompt
                revision_prompt = self._build_revision_prompt(
                    original_question,
                    response.content,
                    response_evals,
                    aggregated_scores[response.anonymous_id]
                )

                # Create revision task
                task = self._revise_single_response(
                    response.model_id,
                    revision_prompt,
                    request,
                    auth_token,
                    base_url
                )
                revision_tasks.append((response, task))

            # Execute all revisions in parallel
            revised_responses = []
            for original_response, task in revision_tasks:
                revised_content = await task
                if revised_content:
                    # Create new ModelResponse with revised content
                    revised_response = ModelResponse(
                        model_id=original_response.model_id,
                        content=revised_content,
                        success=True,
                        anonymous_id=original_response.anonymous_id,
                        metadata={**original_response.metadata, "revised": True}
                    )
                    revised_responses.append(revised_response)
                else:
                    # Keep original if revision failed
                    revised_responses.append(original_response)

            # Return the highest-rated revised response (using original scores)
            top_revised = max(revised_responses, key=lambda r: aggregated_scores[r.anonymous_id].weighted_total)

            if self.valves.DEBUG_MODE:
                print(f"[Writer's Room] Selected revised response from {top_revised.model_id}")

            return top_revised

        except Exception as e:
            if self.valves.DEBUG_MODE:
                print(f"[Writer's Room] Error in self-revision: {e}")
            # Return highest-rated original on error
            top_response = max(all_responses, key=lambda r: aggregated_scores[r.anonymous_id].weighted_total)
            return top_response

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

    def _build_revision_prompt(
        self,
        original_question: str,
        original_draft: str,
        evaluations: List[Evaluation],
        aggregated_score: AggregatedScores
    ) -> str:
        """Build revision prompt: original draft + peer critiques"""
        sections = []

        sections.append("You are revising your creative writing based on anonymous peer editorial feedback.")
        sections.append("")
        sections.append("**ORIGINAL PROMPT:**")
        sections.append(original_question)
        sections.append("")
        sections.append("**YOUR ORIGINAL DRAFT:**")
        sections.append(original_draft)
        sections.append("")
        sections.append("---")
        sections.append("")
        sections.append("**PEER EDITORIAL CRITIQUES:**")
        sections.append("")
        sections.append(f"Your draft received an average score of **{aggregated_score.weighted_total:.1f}/10** from {aggregated_score.evaluator_count} peer editors.")
        sections.append("")

        # Include all evaluations with scores and reasoning
        for i, evaluation in enumerate(evaluations, 1):
            sections.append(f"**Critique #{i}:**")
            sections.append("")
            scores = evaluation.scores
            sections.append(f"- Voice Authenticity: {scores.voice_authenticity:.1f}/10")
            sections.append(f"- Emotional Resonance: {scores.emotional_resonance:.1f}/10")
            sections.append(f"- Originality: {scores.originality:.1f}/10")
            sections.append(f"- Style Consistency: {scores.style_consistency:.1f}/10")
            sections.append(f"- Narrative Coherence: {scores.narrative_coherence:.1f}/10")
            sections.append(f"- LLM Artifact Avoidance: {scores.llm_artifact_avoidance:.1f}/10")
            sections.append("")
            if evaluation.reasoning:
                sections.append(f"**Reasoning:** {evaluation.reasoning}")
                sections.append("")
            sections.append("---")
            sections.append("")

        sections.append("**YOUR REVISION TASK:**")
        sections.append("")
        sections.append("Based on the peer critiques above, revise your original draft to address the feedback.")
        sections.append("")
        sections.append("**Guidelines:**")
        sections.append("1. **Address weaknesses** identified in the critiques (low scores, specific issues)")
        sections.append("2. **Preserve strengths** that received high scores")
        sections.append("3. **Fix slop patterns** if criticized (heart pounding, shimmered, etc.)")
        sections.append("4. **Improve weak areas** like voice, originality, or emotional impact")
        sections.append("5. **Don't over-revise** - if critiques are minor, make subtle improvements")
        sections.append("6. **Maintain your voice** - revise, don't rewrite from scratch")
        sections.append("")
        sections.append("**Output only your revised creative piece below (no meta-commentary):**")

        return "\n".join(sections)

    async def _revise_single_response(
        self,
        model_id: str,
        revision_prompt: str,
        request: Any,
        auth_token: str,
        base_url: str
    ) -> Optional[str]:
        """Execute a single revision API call"""
        try:
            # Get model parameters
            model_params = self._get_model_params()
            params = model_params.get(model_id, model_params[self.available_models[0]])

            payload = {
                "model": model_id,
                "messages": [
                    {
                        "role": "user",
                        "content": revision_prompt
                    }
                ],
                "stream": False,
                "temperature": params.temperature,
                "top_p": params.top_p,
                "max_tokens": params.max_tokens,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/api/chat/completions",
                    headers={
                        "Authorization": f"Bearer {auth_token}",
                        "Content-Type": "application/json"
                    },
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.valves.TIMEOUT_SECONDS)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if "choices" in data and len(data["choices"]) > 0:
                            content = data["choices"][0].get("message", {}).get("content", "")

                            # Track revision tokens
                            usage = data.get("usage", {})
                            input_tokens = usage.get("prompt_tokens", 0)
                            output_tokens = usage.get("completion_tokens", 0)
                            self._track_tokens(model_id, "synthesis", input_tokens, output_tokens)

                            return content
                        else:
                            if self.valves.DEBUG_MODE:
                                print(f"[Writer's Room] Invalid revision response from {model_id}")
                            return None
                    else:
                        if self.valves.DEBUG_MODE:
                            print(f"[Writer's Room] Revision failed for {model_id}: HTTP {response.status}")
                        return None

        except Exception as e:
            if self.valves.DEBUG_MODE:
                print(f"[Writer's Room] Error revising response for {model_id}: {e}")
            return None

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
            line += f" Voice: {avg.voice_authenticity:.1f}, "
            line += f"Emotion: {avg.emotional_resonance:.1f}, "
            line += f"Originality: {avg.originality:.1f}, "
            line += f"Style: {avg.style_consistency:.1f}, "
            line += f"Coherence: {avg.narrative_coherence:.1f}, "
            line += f"No-Artifacts: {avg.llm_artifact_avoidance:.1f} "
            line += f"| Weighted Total: {agg_scores.weighted_total:.2f}/10"

            formatted.append(line)

        # Add weights explanation
        formatted.append("\n**Scoring Weights:**")
        formatted.append(f"Voice: {weights.get('voice_authenticity', 0):.0%}, "
                        f"Emotion: {weights.get('emotional_resonance', 0):.0%}, "
                        f"Originality: {weights.get('originality', 0):.0%}, "
                        f"Style: {weights.get('style_consistency', 0):.0%}, "
                        f"Coherence: {weights.get('narrative_coherence', 0):.0%}, "
                        f"No-Artifacts: {weights.get('llm_artifact_avoidance', 0):.0%}")

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
        output += f"\n\n*Writer's Room session completed in {duration:.1f}s*"
        output += f" • {self.token_usage} tokens used"

        return output


# Module-level metadata
__version__ = "0.6.0"
__author__ = "Council Pipeline Team"
__description__ = "Council of LLMs Orchestrator - Core workflow coordinator"
