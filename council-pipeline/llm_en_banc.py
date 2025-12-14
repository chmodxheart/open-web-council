"""
title: LLM En Banc
author: @chmodxheart
version: 0.1.2
"""

from typing import Generator, Iterator, Optional, List, Dict, Any
from pydantic import BaseModel, Field
import asyncio
import aiohttp
import time
import re
import os


class Pipe:
    """
    LLM En Banc - Multi-Model Response Evaluation

    Have multiple LLMs evaluate a response using standardized criteria.
    Perfect for assessing quality, fact-checking, or getting peer review
    on AI-generated content.
    """

    class Valves(BaseModel):
        """Configuration for LLM En Banc"""

        MODELS_TO_QUERY: str = Field(
            default="gpt-5.1,o3,anthropic/claude-sonnet-4.5",
            description="Comma-separated list of evaluator model IDs"
        )

        EVALUATION_WEIGHT_ACCURACY: float = Field(
            default=0.3,
            description="Weight for accuracy criterion (0-1)"
        )

        EVALUATION_WEIGHT_CLARITY: float = Field(
            default=0.25,
            description="Weight for clarity criterion (0-1)"
        )

        EVALUATION_WEIGHT_COMPLETENESS: float = Field(
            default=0.25,
            description="Weight for completeness criterion (0-1)"
        )

        EVALUATION_WEIGHT_RELEVANCE: float = Field(
            default=0.2,
            description="Weight for relevance criterion (0-1)"
        )

        SHOW_DETAILED_EVALUATIONS: bool = Field(
            default=True,
            description="Show full evaluation reasoning from each model"
        )

        TIMEOUT_SECONDS: int = Field(
            default=60,
            description="Timeout for each evaluation (seconds)"
        )

        DEBUG_MODE: bool = Field(
            default=False,
            description="Enable debug logging"
        )

    def __init__(self):
        self.type = "pipe"
        self.id = "llm_en_banc"
        self.name = "LLM En Banc"
        self.valves = self.Valves()

    def get_models(self) -> List[str]:
        """Parse and return list of models from MODELS_TO_QUERY"""
        if not self.valves.MODELS_TO_QUERY:
            return []
        return [m.strip() for m in self.valves.MODELS_TO_QUERY.split(",") if m.strip()]

    def create_evaluation_prompt(self, response_to_evaluate: str, original_query: str = "") -> str:
        """Create the evaluation prompt"""
        prompt = f"""You are an expert evaluator. Please evaluate the following response using these criteria:

1. **Accuracy** (factual correctness, no hallucinations)
2. **Clarity** (easy to understand, well-structured)
3. **Completeness** (thorough, addresses all aspects)
4. **Relevance** (stays on topic, answers the question)

"""
        if original_query:
            prompt += f"**Original Question**: {original_query}\n\n"

        prompt += f"""**Response to Evaluate**:
{response_to_evaluate}

**Instructions**:
For each criterion, provide:
- A score from 1-10
- 2-3 sentences explaining your reasoning

Format your response exactly as:
ACCURACY: [score]/10
[reasoning]

CLARITY: [score]/10
[reasoning]

COMPLETENESS: [score]/10
[reasoning]

RELEVANCE: [score]/10
[reasoning]
"""
        return prompt

    async def evaluate_response(
        self,
        model_id: str,
        evaluation_prompt: str,
        request: Any,
        __event_emitter__: Any = None,
    ) -> Dict[str, Any]:
        """Have a model evaluate the response"""
        start_time = time.time()

        try:
            import aiohttp

            # Get base URL and auth token (same pattern as Council)
            base_url = f"{request.url.scheme}://{request.url.netloc}" if request else "http://localhost:3000"
            auth_token = self._extract_token(request)

            if not auth_token:
                return {
                    "model": model_id,
                    "content": "Error: No authentication token available",
                    "scores": {},
                    "success": False,
                    "elapsed": time.time() - start_time
                }

            payload = {
                "model": model_id,
                "messages": [{"role": "user", "content": evaluation_prompt}],
                "stream": False
            }

            if self.valves.DEBUG_MODE and __event_emitter__:
                await __event_emitter__({
                    "type": "status",
                    "data": {"description": f"Evaluating with {model_id}...", "done": False}
                })

            # Use aiohttp for async requests (same pattern as Council)
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
                        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        scores = self.parse_scores(content)

                        return {
                            "model": model_id,
                            "content": content,
                            "scores": scores,
                            "success": True,
                            "elapsed": time.time() - start_time
                        }
                    else:
                        error_text = await response.text()
                        return {
                            "model": model_id,
                            "content": f"Error: HTTP {response.status}: {error_text[:200]}",
                            "scores": {},
                            "success": False,
                            "elapsed": time.time() - start_time
                        }

        except Exception as e:
            return {
                "model": model_id,
                "content": f"Error: {str(e)}",
                "scores": {},
                "success": False,
                "elapsed": time.time() - start_time
            }

    def _extract_token(self, request: Any) -> str:
        """Extract authentication token from request (same pattern as Council)"""
        if not request:
            return ""

        try:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                return auth_header.replace("Bearer ", "")
        except:
            pass

        return ""

    def parse_scores(self, evaluation_text: str) -> Dict[str, float]:
        """Parse scores from evaluation text"""
        scores = {}
        criteria = ["ACCURACY", "CLARITY", "COMPLETENESS", "RELEVANCE"]

        for criterion in criteria:
            pattern = rf"{criterion}:\s*(\d+(?:\.\d+)?)\s*/\s*10"
            match = re.search(pattern, evaluation_text, re.IGNORECASE)
            if match:
                scores[criterion.lower()] = float(match.group(1))

        return scores

    def calculate_weighted_score(self, scores: Dict[str, float]) -> float:
        """Calculate weighted average score"""
        weights = {
            "accuracy": self.valves.EVALUATION_WEIGHT_ACCURACY,
            "clarity": self.valves.EVALUATION_WEIGHT_CLARITY,
            "completeness": self.valves.EVALUATION_WEIGHT_COMPLETENESS,
            "relevance": self.valves.EVALUATION_WEIGHT_RELEVANCE
        }

        total = 0.0
        weight_sum = 0.0

        for criterion, score in scores.items():
            if criterion in weights:
                total += score * weights[criterion]
                weight_sum += weights[criterion]

        return total / weight_sum if weight_sum > 0 else 0.0

    async def pipe(
        self,
        body: Dict[str, Any],
        __user__: Optional[Dict] = None,
        __event_emitter__: Any = None,
        __request__: Optional[Any] = None,
    ) -> Generator[str, None, None]:
        """Main pipeline execution"""

        # Extract messages from body
        messages = body.get("messages", [])
        user_message = messages[-1]["content"] if messages else ""

        models = self.get_models()

        if not models:
            yield "Error: No models configured. Please set MODELS_TO_QUERY in Valves."
            return

        if len(models) < 2:
            yield "Error: Please configure at least 2 models for En Banc evaluation."
            return

        # Extract the response to evaluate from the user message
        # User can either paste directly or use a prefix like "Evaluate: <response>"
        response_to_evaluate = user_message
        original_query = ""

        # Try to extract original query if provided
        if "Original question:" in user_message or "Original query:" in user_message:
            parts = re.split(r"Original (?:question|query):\s*", user_message, flags=re.IGNORECASE)
            if len(parts) > 1:
                query_and_response = parts[1].split("\n\n", 1)
                if len(query_and_response) == 2:
                    original_query = query_and_response[0].strip()
                    response_to_evaluate = query_and_response[1].strip()

        # Create evaluation prompt
        eval_prompt = self.create_evaluation_prompt(response_to_evaluate, original_query)

        # Emit initial status
        if __event_emitter__:
            await __event_emitter__({
                "type": "status",
                "data": {"description": f"Evaluating with {len(models)} models...", "done": False}
            })

        # Run evaluations in parallel
        tasks = [
            self.evaluate_response(model, eval_prompt, __request__, __event_emitter__)
            for model in models
        ]
        results = await asyncio.gather(*tasks)

        # Format output
        yield "# LLM En Banc Evaluation\n\n"
        yield f"**Response evaluated by {len(models)} models**\n\n"
        yield "---\n\n"

        # Individual evaluations
        all_scores = []
        for result in results:
            model_name = result["model"]
            content = result["content"]
            scores = result["scores"]
            success = result["success"]

            yield f"## Evaluator: {model_name}\n\n"

            if success and scores:
                # Calculate weighted score for this evaluator
                weighted = self.calculate_weighted_score(scores)
                yield f"**Overall Score: {weighted:.1f}/10**\n\n"

                if self.valves.SHOW_DETAILED_EVALUATIONS:
                    yield f"{content}\n\n"
                else:
                    # Just show scores
                    for criterion, score in scores.items():
                        yield f"- {criterion.title()}: {score}/10\n"
                    yield "\n"

                all_scores.append(scores)
            else:
                yield f"*Evaluation failed: {content}*\n\n"

            yield "---\n\n"

        # Aggregated scores
        if all_scores:
            yield "## Aggregated Results\n\n"

            # Average scores per criterion
            criteria = ["accuracy", "clarity", "completeness", "relevance"]
            avg_scores = {}

            for criterion in criteria:
                scores = [s[criterion] for s in all_scores if criterion in s]
                if scores:
                    avg_scores[criterion] = sum(scores) / len(scores)
                    yield f"**{criterion.title()}**: {avg_scores[criterion]:.1f}/10 (avg of {len(scores)} evaluations)\n"

            # Overall weighted average
            if avg_scores:
                overall = self.calculate_weighted_score(avg_scores)
                yield f"\n**Final Weighted Score: {overall:.1f}/10**\n"

        # Final status
        if __event_emitter__:
            successful = sum(1 for r in results if r["success"])
            await __event_emitter__({
                "type": "status",
                "data": {"description": f"Completed: {successful}/{len(models)} evaluations", "done": True}
            })
