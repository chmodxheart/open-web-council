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
try:
    from schemas import CouncilMode, extract_council_metadata
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(__file__))
    from schemas import CouncilMode, extract_council_metadata


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
