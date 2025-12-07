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
try:
    from schemas import CouncilMode, EvaluationScores, extract_council_metadata
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(__file__))
    from schemas import CouncilMode, EvaluationScores, extract_council_metadata


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
