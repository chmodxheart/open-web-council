"""
title: LLM Roundtable
author: @chmodxheart
version: 0.1.1
"""

from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
import asyncio
import aiohttp
import time


class Pipe:
    """
    LLM Roundtable - Parallel Multi-Model Query

    Sends your query to multiple LLMs simultaneously and displays all responses
    without evaluation or synthesis. Get diverse perspectives at a glance.
    """

    class Valves(BaseModel):
        """Configuration for LLM Roundtable"""

        MODELS_TO_QUERY: str = Field(
            default="gpt-5.1,o3,anthropic/claude-sonnet-4.5",
            description="Comma-separated list of model IDs to query"
        )

        TIMEOUT_SECONDS: int = Field(
            default=60,
            ge=5,
            le=360,
            description="Timeout for each model query (seconds)"
        )

        SHOW_MODEL_NAMES: bool = Field(
            default=True,
            description="Show which model gave which response"
        )

        INCLUDE_TIMESTAMPS: bool = Field(
            default=False,
            description="Show response time for each model"
        )

        DEBUG_MODE: bool = Field(
            default=False,
            description="Enable debug logging"
        )

    def __init__(self):
        self.type = "pipe"
        self.id = "llm_roundtable"
        self.name = "LLM Roundtable"
        self.valves = self.Valves()

    def _extract_token(self, request: Any) -> Optional[str]:
        """Extract authentication token from request"""
        if not request:
            return None
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header.replace("Bearer ", "")
        return None

    async def _query_single_model(
        self,
        model_id: str,
        messages: List[dict],
        request: Any,
    ) -> Dict[str, Any]:
        """Query a single model and return its response"""
        start_time = time.time()

        try:
            # Get base URL and auth token
            base_url = f"{request.url.scheme}://{request.url.netloc}" if request else "http://localhost:3000"
            auth_token = self._extract_token(request)

            if not auth_token:
                return {
                    "model": model_id,
                    "content": "Error: No authentication token",
                    "success": False,
                    "elapsed": time.time() - start_time
                }

            # Build request payload
            payload = {
                "model": model_id,
                "messages": messages,
                "stream": False,
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
                    timeout=aiohttp.ClientTimeout(total=self.valves.TIMEOUT_SECONDS)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

                        return {
                            "model": model_id,
                            "content": content,
                            "success": True,
                            "elapsed": time.time() - start_time
                        }
                    else:
                        return {
                            "model": model_id,
                            "content": f"Error: HTTP {response.status}",
                            "success": False,
                            "elapsed": time.time() - start_time
                        }

        except Exception as e:
            return {
                "model": model_id,
                "content": f"Error: {str(e)}",
                "success": False,
                "elapsed": time.time() - start_time
            }

    async def pipe(
        self,
        body: Dict[str, Any],
        __user__: Optional[Dict] = None,
        __event_emitter__: Any = None,
        __request__: Optional[Any] = None,
    ):
        """Main pipeline execution"""

        # Extract messages and request from parameters
        messages = body.get("messages", [])
        request = __request__

        # Parse models
        models = [m.strip() for m in self.valves.MODELS_TO_QUERY.split(",") if m.strip()]

        if not models:
            yield "Error: No models configured. Please set MODELS_TO_QUERY in Valves."
            return

        if len(models) < 2:
            yield "Error: Please configure at least 2 models for the Roundtable."
            return

        # Emit initial status
        if __event_emitter__:
            await __event_emitter__({
                "type": "status",
                "data": {"description": f"Querying {len(models)} models...", "done": False}
            })

        # Query all models in parallel
        tasks = [
            self._query_single_model(model, messages, request)
            for model in models
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to error results
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "model": models[i],
                    "content": f"Error: {str(result)}",
                    "success": False,
                    "elapsed": 0
                })
            else:
                processed_results.append(result)

        # Format output
        yield "# LLM Roundtable Results\n\n"
        yield f"**Query sent to {len(models)} models**\n\n"
        yield "---\n\n"

        for result in processed_results:
            model_name = result["model"]
            content = result["content"]
            success = result["success"]
            elapsed = result["elapsed"]

            # Model header
            if self.valves.SHOW_MODEL_NAMES:
                header = f"## {model_name}"
                if self.valves.INCLUDE_TIMESTAMPS and success:
                    header += f" ({elapsed:.1f}s)"
                yield header + "\n\n"

            # Content
            if success:
                yield content + "\n\n"
            else:
                yield f"*{content}*\n\n"

            yield "---\n\n"

        # Final status
        if __event_emitter__:
            successful = sum(1 for r in processed_results if r["success"])
            await __event_emitter__({
                "type": "status",
                "data": {"description": f"Completed: {successful}/{len(models)} models responded", "done": True}
            })
