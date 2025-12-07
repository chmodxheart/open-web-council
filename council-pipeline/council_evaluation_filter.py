"""
title: Council Evaluation Filter
author: chmodxheart
author_url: https://github.com/chmodxheart
funding_url: https://github.com/chmodxheart
version: 0.1.0
description: Injects user-editable evaluation rubric for anonymous peer review

Council of LLMs - Evaluation Prompt Filter

This inlet filter injects user-customizable evaluation instructions when
the Council orchestrator is in evaluation mode.

Key Features:
- User-editable evaluation rubric via Valves (editable in UI!)
- Template support with {response_text} placeholder
- Detects evaluation mode via CouncilMetadata
- Injects structured evaluation prompt

Users can customize the evaluation criteria and instructions without
touching code - just edit in Open WebUI Admin Panel!
"""

from pydantic import BaseModel, Field
from typing import Optional

# Import Council data structures
try:
    from schemas import CouncilMode, extract_council_metadata
except ImportError:
    # Fallback if schemas not in same directory
    import sys
    import os
    sys.path.insert(0, os.path.dirname(__file__))
    from schemas import CouncilMode, extract_council_metadata


class Filter:
    """
    Evaluation Prompt Filter

    Injects evaluation instructions when Council is in evaluation mode.
    Prompt is user-editable via Valves in Open WebUI UI!
    """

    class Valves(BaseModel):
        """
        User-configurable evaluation prompt template
        """
        PRIORITY: int = Field(
            default=10,
            description="Filter priority (higher runs first). Should run before model query."
        )

        EVALUATION_RUBRIC_TEMPLATE: str = Field(
            default="""You are participating in an anonymous peer review of AI responses. Your task is to evaluate the following anonymous response objectively and critically.

**EVALUATION CRITERIA** (Rate each 1-10, where 1=poor, 10=excellent):

1. **ACCURACY** (Factual Correctness)
   - Are the facts, data, and claims correct?
   - Is the information up-to-date and reliable?
   - Are there any factual errors or misconceptions?

2. **CLARITY** (Understandability)
   - Is the explanation clear and easy to understand?
   - Is the language appropriate for the audience?
   - Are complex concepts explained well?

3. **COMPLETENESS** (Thoroughness)
   - Does it fully address the question?
   - Are important aspects covered?
   - Is anything significant missing?

4. **RELEVANCE** (On-Topic & Useful)
   - Does it stay focused on the question?
   - Is the information useful and applicable?
   - Is there unnecessary tangential content?

---

**ANONYMOUS RESPONSE TO EVALUATE:**

{response_text}

---

**YOUR EVALUATION:**

Please provide your scores in this EXACT format (this is critical for parsing):

ACCURACY: [your score 1-10]
CLARITY: [your score 1-10]
COMPLETENESS: [your score 1-10]
RELEVANCE: [your score 1-10]
REASONING: [2-3 sentences explaining your scores, focusing on strengths and weaknesses]

Be critical but fair. Focus on objective quality, not stylistic preferences.""",
            description="Evaluation prompt template. Use {response_text} as placeholder for the anonymous response."
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

        Checks if Council is in evaluation mode, and if so, injects
        the evaluation rubric prompt.

        Args:
            body: Request body containing messages, metadata, etc.
            __user__: User information (optional)

        Returns:
            Modified body with evaluation prompt injected (if applicable)
        """

        # Extract Council metadata
        metadata = extract_council_metadata(body)

        # Only inject if in evaluation mode
        if not metadata or metadata.mode != CouncilMode.EVALUATION:
            # Not in evaluation mode, pass through unchanged
            return body

        # Get the anonymous response to evaluate from metadata
        # The orchestrator should have placed this in body metadata
        anonymous_response = body.get("metadata", {}).get("anonymous_response_text", "")

        if not anonymous_response:
            # No response to evaluate, pass through
            if self.valves.ENABLE_DEBUG_LOGGING:
                print("[Council Evaluation Filter] No anonymous response found in metadata")
            return body

        if self.valves.ENABLE_DEBUG_LOGGING:
            print(f"[Council Evaluation Filter] Injecting evaluation prompt")
            print(f"[Council Evaluation Filter] Response length: {len(anonymous_response)} chars")

        # Format the evaluation rubric with the anonymous response
        evaluation_prompt = self.valves.EVALUATION_RUBRIC_TEMPLATE.format(
            response_text=anonymous_response
        )

        # Replace the last user message with the evaluation prompt
        # (The orchestrator should have set this up appropriately)
        if body.get("messages") and len(body["messages"]) > 0:
            # Find the last user message
            for i in range(len(body["messages"]) - 1, -1, -1):
                if body["messages"][i].get("role") == "user":
                    body["messages"][i]["content"] = evaluation_prompt
                    break
        else:
            # No messages found, create one
            body["messages"] = [
                {
                    "role": "user",
                    "content": evaluation_prompt
                }
            ]

        if self.valves.ENABLE_DEBUG_LOGGING:
            print(f"[Council Evaluation Filter] Prompt injected successfully")

        return body


# Module metadata
__version__ = "0.1.0"
__author__ = "Council Pipeline Team"
__description__ = "Evaluation prompt filter with user-editable rubric"
