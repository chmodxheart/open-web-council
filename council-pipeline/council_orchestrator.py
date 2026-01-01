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
from schemas import (
    CouncilMetadata,
    CouncilMode,
    ModelResponse,
    ModelParameters,
    AnonymousResponseMapping,
    Evaluation,
    EvaluationScores,
    AggregatedScores,
    SynthesisInput,
    StandardEvaluationResponse,
    SingleStandardEvaluation,
    BulkStandardEvaluationResponse,
    MultipleResponses,
    get_structured_output_format,
    create_council_metadata,
    extract_council_metadata,
    inject_council_metadata,
)


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
            description="Comma-separated list of model IDs to query for initial responses (default: gpt-5.1,anthropic/claude-sonnet-4.5,groq.moonshotai/kimi-k2-instruct)"
        )

        EVALUATION_MODELS: str = Field(
            default="",
            description="Comma-separated list of model IDs to use for evaluation, leave empty to use same models as MODELS_TO_QUERY (default: empty)"
        )

        LEAD_SYNTHESIZER: str = Field(
            default="auto",
            description="Lead model for synthesis: 'auto' for highest-scoring, or specific model ID (default: auto)"
        )

        MIN_MODELS_REQUIRED: int = Field(
            default=3,
            ge=2,
            description="Minimum number of successful model responses required, recommended 3-5, not total models configured (default: 3)"
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
            description="Default temperature for all models (default: 0.7)"
        )

        DEFAULT_TOP_P: float = Field(
            default=1.0,
            ge=0.0,
            le=1.0,
            description="Default top_p nucleus sampling (default: 1.0)"
        )

        DEFAULT_MAX_TOKENS: int = Field(
            default=0,
            ge=0,
            description="Default max tokens to generate, 0 = no limit (default: 0)"
        )

        # ============================================================
        # Evaluation Configuration
        # ============================================================
        EVALUATION_WEIGHT_ACCURACY: float = Field(
            default=0.3,
            ge=0.0,
            le=1.0,
            description="Weight for accuracy criterion (default: 0.3)"
        )

        EVALUATION_WEIGHT_CLARITY: float = Field(
            default=0.25,
            ge=0.0,
            le=1.0,
            description="Weight for clarity criterion (default: 0.25)"
        )

        EVALUATION_WEIGHT_COMPLETENESS: float = Field(
            default=0.25,
            ge=0.0,
            le=1.0,
            description="Weight for completeness criterion (default: 0.25)"
        )

        EVALUATION_WEIGHT_RELEVANCE: float = Field(
            default=0.2,
            ge=0.0,
            le=1.0,
            description="Weight for relevance criterion (default: 0.2)"
        )

        TOP_N_FOR_SYNTHESIS: int = Field(
            default=0,
            ge=0,
            description="Number of top-ranked responses to use for synthesis, 0 = all responses regardless of score (default: 0)"
        )

        MIN_SCORE_FOR_SYNTHESIS: float = Field(
            default=0.0,
            ge=0.0,
            le=10.0,
            description="Minimum score threshold for synthesis, 0 = include all even low-scoring responses, responses below this are excluded (default: 0.0)"
        )

        # ============================================================
        # Performance Configuration
        # ============================================================
        TIMEOUT_SECONDS: int = Field(
            default=60,
            ge=5,
            le=600,
            description="Timeout for individual model queries in seconds (default: 60)"
        )

        EVAL_TIMEOUT_SECONDS: int = Field(
            default=90,
            ge=5,
            le=600,
            description="Timeout for evaluation queries in seconds, often needs to be higher due to rate limits (default: 90)"
        )

        ENABLE_PARALLEL_REQUESTS: bool = Field(
            default=True,
            description="Enable parallel model queries, recommended for performance (default: true)"
        )

        # ============================================================
        # Synthesis Mode Configuration
        # ============================================================
        SYNTHESIS_MODE: str = Field(
            default="full",
            description="Synthesis mode: 'full' (synthesize from all), 'highest_rated' (return top-scoring only), 'none' (show responses and scores only) (default: full)"
        )

        # ============================================================
        # Token & Cost Tracking
        # ============================================================
        SHOW_TOKEN_USAGE: bool = Field(
            default=True,
            description="Show detailed token usage breakdown per model for initial and evaluation queries (default: true)"
        )

        MODEL_COSTS_JSON: str = Field(
            default="{}",
            description='Per-model costs as JSON: {"gpt-4": {"input": 0.03, "output": 0.06}, "claude-3-opus": {"input": 0.015, "output": 0.075}}, costs are per 1M tokens (default: {})'
        )

        SHOW_COST_ESTIMATE: bool = Field(
            default=False,
            description="Show estimated cost breakdown, requires MODEL_COSTS_JSON to be configured (default: false)"
        )

        # ============================================================
        # Output Configuration
        # ============================================================
        SHOW_EVALUATION_SCORES: bool = Field(
            default=True,
            description="Include evaluation scores summary in output (default: true)"
        )

        SHOW_INDIVIDUAL_RESPONSES: bool = Field(
            default=True,
            description="Include all individual model responses in output, can be very large (default: true)"
        )

        SHOW_REASONING: bool = Field(
            default=True,
            description="Include detailed evaluation reasoning in output, can be very large (default: true)"
        )

        SHOW_PROGRESS: bool = Field(
            default=True,
            description="Stream progress updates during execution: queries, evaluations, synthesis phases (default: true)"
        )

        ENABLE_STREAMING: bool = Field(
            default=True,
            description="Stream output progressively as Council works, recommended for transparency (default: true)"
        )

        # ============================================================
        # Prompting Techniques Configuration
        # ============================================================

        # Initial Query Techniques
        QUERY_USE_HERMENEUTIC_CIRCLE: bool = Field(
            default=True,
            description="Apply hermeneutic circle approach (parts/whole interplay) in initial responses (default: true)"
        )

        QUERY_USE_CHAIN_OF_THOUGHT: bool = Field(
            default=False,
            description="Request step-by-step reasoning in initial responses (default: false)"
        )

        QUERY_USE_VERBALIZED_SAMPLING: bool = Field(
            default=False,
            description="Request models to show intermediate thinking in initial responses (default: false)"
        )

        # Evaluation Techniques
        EVAL_USE_HERMENEUTIC_CIRCLE: bool = Field(
            default=True,
            description="Apply hermeneutic circle approach in evaluations (default: true)"
        )

        EVAL_USE_VERBALIZED_SAMPLING: bool = Field(
            default=True,
            description="Request detailed reasoning process in evaluations (default: true)"
        )

        EVAL_USE_SOCRATIC_QUESTIONING: bool = Field(
            default=True,
            description="Probe assumptions, gaps, and weaknesses in evaluations (default: true)"
        )

        EVAL_USE_ADVERSARIAL_STANCE: bool = Field(
            default=True,
            description="Actively look for flaws and edge cases in evaluations (default: true)"
        )

        EVAL_USE_CONSTITUTIONAL_PRINCIPLES: bool = Field(
            default=True,
            description="Justify scores against explicit quality principles in evaluations (default: true)"
        )

        # Synthesis Techniques
        SYNTH_USE_META_COGNITIVE: bool = Field(
            default=True,
            description="Reflect on uncertainty and confidence levels in synthesis (default: true)"
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
        # Debug Configuration
        # ============================================================
        DEBUG_MODE: bool = Field(
            default=False,
            description="Enable verbose debug logging (default: false)"
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

            # Show details of any failed models
            if failed_responses:
                yield "<details>\n<summary>⚠️ Failed Models</summary>\n\n"
                for resp in failed_responses:
                    error_msg = resp.error if resp.error else "Unknown error"
                    yield f"- **{resp.model_id}**: {error_msg}\n"
                yield "\n</details>\n\n"

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

    def _supports_strict_json_schema(self, model_id: str) -> bool:
        """
        Check if a model supports OpenAI's strict JSON schema response_format.

        Returns True for providers with TESTED working structured output support:
        - OpenAI models (gpt-*, o1*, o3*) - native support
        - Google/Gemini models - works via OpenRouter
        - Groq models (groq.*) - native support

        Returns False for providers where structured outputs don't work reliably:
        - Anthropic/Claude via OpenRouter - ignores response_format, returns markdown
        """
        model_lower = model_id.lower()

        # Anthropic/Claude models - OpenRouter passes response_format but Claude ignores it
        # Must use prompt-based JSON instructions instead
        if "anthropic" in model_lower or "claude" in model_lower:
            return False

        # OpenAI models - native support, works reliably
        if model_lower.startswith("gpt-"):
            return True
        if model_lower.startswith("o1") or model_lower.startswith("o3"):
            return True

        # Google/Gemini models - works via OpenRouter
        if "gemini" in model_lower:
            return True
        if model_lower.startswith("google/"):
            return True

        # Groq models - native support
        if model_lower.startswith("groq."):
            return True

        # Mistral models - test carefully, may need fallback
        if "mistral" in model_lower:
            return True

        # Default: use fallback (safer)
        if self.valves.DEBUG_MODE:
            print(f"[Council] Unknown model '{model_id}' - using prompt-based JSON fallback")
        return False

    def _get_json_format_instructions(self, schema_type: str = "single") -> str:
        """
        Get JSON format instructions to append to prompts for models that don't support response_format.
        
        Args:
            schema_type: "single" for StandardEvaluationResponse, "bulk" for BulkStandardEvaluationResponse
        """
        if schema_type == "single":
            return '''

**IMPORTANT: Output your response as valid JSON in this exact format:**
```json
{
  "scores": {
    "accuracy": <number 0-10>,
    "clarity": <number 0-10>,
    "completeness": <number 0-10>,
    "relevance": <number 0-10>
  },
  "reasoning": "<your detailed reasoning as a single string>"
}
```
Output ONLY the JSON object, no additional text before or after.'''
        else:  # bulk
            return '''

**IMPORTANT: Output your response as valid JSON in this exact format:**
```json
{
  "evaluations": [
    {
      "response_id": "<the anonymous response ID>",
      "scores": {
        "accuracy": <number 0-10>,
        "clarity": <number 0-10>,
        "completeness": <number 0-10>,
        "relevance": <number 0-10>
      },
      "reasoning": "<your detailed reasoning>"
    }
  ]
}
```
Include one evaluation object per response. Output ONLY the JSON object, no additional text.'''

    def _parse_evaluation_json_fallback(self, raw_response: str, evaluator_model_id: str) -> Optional[dict]:
        """
        Parse evaluation JSON with fallback strategies for models without strict schema support.
        
        Tries multiple parsing strategies:
        1. Direct JSON parse
        2. Extract JSON from markdown code blocks
        3. Extract JSON from anywhere in the response
        """
        # Strategy 1: Direct JSON parse
        try:
            return json.loads(raw_response.strip())
        except json.JSONDecodeError:
            pass
        
        # Strategy 2: Extract from markdown code block
        code_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_response, re.DOTALL)
        if code_block_match:
            try:
                return json.loads(code_block_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Strategy 3: Find JSON object anywhere in response
        json_match = re.search(r'\{[^{}]*"scores"[^{}]*\{[^{}]*\}[^{}]*\}', raw_response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        
        # Strategy 4: More aggressive - find any JSON object with scores
        try:
            # Find the outermost braces
            start = raw_response.find('{')
            if start != -1:
                depth = 0
                for i, char in enumerate(raw_response[start:], start):
                    if char == '{':
                        depth += 1
                    elif char == '}':
                        depth -= 1
                        if depth == 0:
                            potential_json = raw_response[start:i+1]
                            return json.loads(potential_json)
        except (json.JSONDecodeError, ValueError):
            pass
        
        if self.valves.DEBUG_MODE:
            print(f"[Council] {evaluator_model_id}: Could not parse JSON from response")
            print(f"[Council] Raw response preview: {raw_response[:500]}...")
        
        return None

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
            }

            # Only set max_tokens if > 0 (0 means no limit)
            if params.max_tokens > 0:
                payload["max_tokens"] = params.max_tokens

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

    def _build_bulk_evaluation_prompt(self, responses: List[ModelResponse]) -> str:
        """Build bulk evaluation prompt with all anonymous responses"""
        sections = []

        # Opening
        sections.append("You are participating in an anonymous peer review of AI responses.")
        sections.append(f"Your task is to evaluate {len(responses)} anonymous responses.")
        sections.append("Compare them directly, calibrate your scores relative to each other, and be objective and critical.")
        sections.append("")

        # Add same prompting techniques as single evaluation
        if self.valves.EVAL_USE_HERMENEUTIC_CIRCLE:
            sections.append("**Hermeneutic Circle Approach:**")
            sections.append("For each response, move iteratively between specific details and the overall response.")
            sections.append("")

        if self.valves.EVAL_USE_VERBALIZED_SAMPLING:
            sections.append("**Show Your Thinking:**")
            sections.append("Reveal your evaluation thought process for each response.")
            sections.append("")

        if self.valves.EVAL_USE_SOCRATIC_QUESTIONING:
            sections.append("**Socratic Examination:**")
            sections.append("For each response, probe: What assumptions? What's missing? What edge cases?")
            sections.append("")

        if self.valves.EVAL_USE_ADVERSARIAL_STANCE:
            sections.append("**Critical Analysis:**")
            sections.append("Actively look for flaws, weaknesses, and potential issues in each response.")
            sections.append("")

        # List all responses with their IDs
        sections.append("**Responses to Evaluate:**")
        sections.append("")
        for i, response in enumerate(responses, 1):
            sections.append(f"--- Response {response.anonymous_id} ---")
            sections.append(response.content)
            sections.append("")

        sections.append("**Your Task:**")
        sections.append("Evaluate each response using structured output format.")
        sections.append("You'll return a JSON object with one evaluation per response.")
        sections.append("Include the response_id, scores (0-10 for accuracy, clarity, completeness, relevance), and detailed reasoning.")

        return "\n".join(sections)

    async def _query_for_bulk_evaluation(
        self,
        evaluator_model_id: str,
        target_responses: List[ModelResponse],
        params: ModelParameters,
        request: Any,
        user: Optional[dict],
        metadata: CouncilMetadata,
    ) -> List[Evaluation]:
        """
        Query a model to evaluate ALL anonymous responses in one API call

        Supports both strict JSON schema (for compatible models) and
        fallback JSON parsing (for models like Claude, Groq).
        
        Returns list of Evaluation objects (one per response)
        """
        try:
            # Get base URL and auth token
            base_url = f"{request.url.scheme}://{request.url.netloc}" if request else "http://localhost:3000"
            auth_token = self._extract_token(request)

            if not auth_token:
                if self.valves.DEBUG_MODE:
                    print(f"[Council] No auth token for bulk evaluation")
                return []

            # Build bulk evaluation prompt with all responses
            evaluation_prompt = self._build_bulk_evaluation_prompt(target_responses)
            
            # Check if model supports strict JSON schema
            use_strict_schema = self._supports_strict_json_schema(evaluator_model_id)
            
            if not use_strict_schema:
                # Add JSON format instructions for models without structured output support
                evaluation_prompt += self._get_json_format_instructions("bulk")
                if self.valves.DEBUG_MODE:
                    print(f"[Council] {evaluator_model_id}: Using prompt-based JSON for bulk eval (no strict schema support)")

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
            }
            
            # Only add response_format for models that support it
            if use_strict_schema:
                payload["response_format"] = get_structured_output_format(
                    BulkStandardEvaluationResponse,
                    "bulk_standard_evaluation"
                )

            # Only set max_tokens if > 0 (0 means no limit)
            if params.max_tokens > 0:
                payload["max_tokens"] = params.max_tokens

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
                            choice = data["choices"][0]
                            evaluation_json = choice.get("message", {}).get("content", "")
                            finish_reason = choice.get("finish_reason", "unknown")

                            # Warn if evaluation response was truncated
                            if finish_reason not in ["stop", "end_turn", None]:
                                if self.valves.DEBUG_MODE:
                                    print(f"[Council] {evaluator_model_id}: Bulk evaluation stopped with finish_reason='{finish_reason}' (may be incomplete)")
                        else:
                            if self.valves.DEBUG_MODE:
                                print(f"[Council] Invalid bulk evaluation response format from {evaluator_model_id}")
                            return []

                        # Track evaluation tokens
                        usage = data.get("usage", {})
                        input_tokens = usage.get("prompt_tokens", 0)
                        output_tokens = usage.get("completion_tokens", 0)
                        self._track_tokens(evaluator_model_id, "evaluation", input_tokens, output_tokens)

                        # Parse JSON response - use appropriate strategy based on model support
                        try:
                            if use_strict_schema:
                                # Strict schema - use Pydantic validation directly
                                bulk_response = BulkStandardEvaluationResponse.model_validate_json(evaluation_json)
                            else:
                                # Fallback parsing for models without strict schema support
                                parsed = self._parse_evaluation_json_fallback(evaluation_json, evaluator_model_id)
                                if parsed is None:
                                    return []
                                bulk_response = BulkStandardEvaluationResponse.model_validate(parsed)

                            # Convert to individual Evaluation objects
                            evaluations = []
                            for single_eval in bulk_response.evaluations:
                                evaluation = Evaluation(
                                    evaluator_model_id=evaluator_model_id,
                                    target_anonymous_id=single_eval.response_id,
                                    scores=single_eval.scores,
                                    reasoning=single_eval.reasoning,
                                    raw_response=evaluation_json
                                )
                                evaluations.append(evaluation)

                            if self.valves.DEBUG_MODE:
                                print(f"[Council] {evaluator_model_id}: Bulk evaluated {len(evaluations)} responses")

                            return evaluations

                        except Exception as parse_error:
                            if self.valves.DEBUG_MODE:
                                print(f"[Council] Failed to parse bulk structured response from {evaluator_model_id}: {parse_error}")
                                print(f"[Council] Raw response: {evaluation_json[:500]}...")
                            return []
                    else:
                        if self.valves.DEBUG_MODE:
                            error_text = await response.text()
                            print(f"[Council] Bulk evaluation query failed: HTTP {response.status}")
                            print(f"[Council] Error: {error_text[:300]}...")
                        return []

        except Exception as e:
            if self.valves.DEBUG_MODE:
                print(f"[Council] Error in bulk evaluation query: {e}")
            return []

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
        Supports both strict JSON schema (for compatible models) and
        fallback JSON parsing (for models like Claude, Groq).
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
            
            # Check if model supports strict JSON schema
            use_strict_schema = self._supports_strict_json_schema(evaluator_model_id)
            
            if not use_strict_schema:
                # Add JSON format instructions for models without structured output support
                evaluation_prompt += self._get_json_format_instructions("single")
                if self.valves.DEBUG_MODE:
                    print(f"[Council] {evaluator_model_id}: Using prompt-based JSON (no strict schema support)")

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
            }
            
            # Only add response_format for models that support it
            if use_strict_schema:
                payload["response_format"] = get_structured_output_format(
                    StandardEvaluationResponse,
                    "standard_evaluation"
                )

            # Only set max_tokens if > 0 (0 means no limit)
            if params.max_tokens > 0:
                payload["max_tokens"] = params.max_tokens

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
                            choice = data["choices"][0]
                            evaluation_json = choice.get("message", {}).get("content", "")
                            finish_reason = choice.get("finish_reason", "unknown")

                            # Warn if evaluation response was truncated
                            if finish_reason not in ["stop", "end_turn", None]:
                                if self.valves.DEBUG_MODE:
                                    print(f"[Council] {evaluator_model_id}: Evaluation stopped with finish_reason='{finish_reason}' (may be incomplete)")
                        else:
                            if self.valves.DEBUG_MODE:
                                print(f"[Council] Invalid evaluation response format from {evaluator_model_id}")
                            return None

                        # Track evaluation tokens
                        usage = data.get("usage", {})
                        input_tokens = usage.get("prompt_tokens", 0)
                        output_tokens = usage.get("completion_tokens", 0)
                        self._track_tokens(evaluator_model_id, "evaluation", input_tokens, output_tokens)

                        # Parse JSON response - use appropriate strategy based on model support
                        try:
                            if use_strict_schema:
                                # Strict schema - use Pydantic validation directly
                                eval_response = StandardEvaluationResponse.model_validate_json(evaluation_json)
                            else:
                                # Fallback parsing for models without strict schema support
                                parsed = self._parse_evaluation_json_fallback(evaluation_json, evaluator_model_id)
                                if parsed is None:
                                    return None
                                eval_response = StandardEvaluationResponse.model_validate(parsed)

                            evaluation = Evaluation(
                                evaluator_model_id=evaluator_model_id,
                                target_anonymous_id=target_response.anonymous_id,
                                scores=eval_response.scores,
                                reasoning=eval_response.reasoning,
                                raw_response=evaluation_json
                            )

                            return evaluation
                        except Exception as parse_error:
                            if self.valves.DEBUG_MODE:
                                print(f"[Council] Failed to parse structured response from {evaluator_model_id}: {parse_error}")
                                print(f"[Council] Raw response: {evaluation_json[:500]}...")
                            return None
                    else:
                        if self.valves.DEBUG_MODE:
                            error_text = await response.text()
                            print(f"[Council] Evaluation query failed: HTTP {response.status}")
                            print(f"[Council] Error: {error_text[:300]}...")
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
        Distribute anonymous responses to evaluation models for scoring (BULK MODE)

        Each evaluation model evaluates ALL anonymous responses in ONE API call.
        This provides better comparative context and is far more efficient.

        All evaluators run in parallel for maximum performance.
        """
        # Get model parameters for evaluation queries
        model_params = self._get_model_params()

        # Build list of bulk evaluation tasks (one per evaluator)
        tasks = []
        for evaluator_model_id in self.evaluation_models:
            if self.valves.DEBUG_MODE:
                print(f"[Council] Queuing BULK: {evaluator_model_id} evaluating {len(responses)} responses")

            task = self._query_for_bulk_evaluation(
                evaluator_model_id=evaluator_model_id,
                target_responses=responses,
                params=model_params.get(evaluator_model_id, model_params[self.available_models[0]]),
                request=request,
                user=user,
                metadata=metadata
            )
            tasks.append(task)

        # Execute ALL bulk evaluation queries in parallel
        if self.valves.DEBUG_MODE:
            print(f"[Council] Executing {len(tasks)} BULK evaluations in parallel...")

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Flatten results (each task returns a list of evaluations)
        all_evaluations = []
        failed_evaluators = []

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                if self.valves.DEBUG_MODE:
                    evaluator = self.evaluation_models[i]
                    print(f"[Council] {evaluator}: Bulk evaluation raised exception: {type(result).__name__}: {str(result)[:100]}")
                    failed_evaluators.append(evaluator)
            elif isinstance(result, list):
                all_evaluations.extend(result)
                if self.valves.DEBUG_MODE and len(result) > 0:
                    evaluator = self.evaluation_models[i]
                    print(f"[Council] {evaluator}: Successfully evaluated {len(result)} responses")
            elif result is None or len(result) == 0:
                if self.valves.DEBUG_MODE:
                    evaluator = self.evaluation_models[i]
                    print(f"[Council] {evaluator}: Bulk evaluation returned no results")
                    failed_evaluators.append(evaluator)

        expected_count = len(responses) * len(self.evaluation_models)
        if self.valves.DEBUG_MODE:
            print(f"[Council] Completed {len(all_evaluations)}/{expected_count} total evaluations")
            if failed_evaluators:
                print(f"[Council] Failed evaluators: {', '.join(failed_evaluators)}")

        return all_evaluations

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
            }

            # Only set max_tokens if > 0 (0 means no limit)
            if params.max_tokens > 0:
                payload["max_tokens"] = params.max_tokens

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
