from __future__ import annotations

import time
from typing import Any

from openai import OpenAI

from fastapi import HTTPException

from app.core.config import settings


class NemotronService:
    def __init__(self) -> None:
        self.client = OpenAI(
            api_key=settings.nvidia_api_key,
            base_url=settings.nvidia_base_url,
        )
        self._availability: bool | None = None
        self._response_times: list[float] = []
        self._success_count: int = 0
        self._error_count: int = 0
        self._total_calls: int = 0

    @property
    def available(self) -> bool:
        """Check if Nemotin is available (lazy initialization)."""
        if self._availability is None:
            # Check availability on first access
            self._availability = self._check_availability()
        return self._availability

    def _check_availability(self) -> bool:
        """Check if the Nemotin API is reachable."""
        try:
            # Try a minimal API call to verify availability
            response = self.client.chat.completions.create(
                model=settings.nemotron_model,
                messages=[{"role": "system", "content": "test"}],
                max_tokens=1,
            )
            return response is not None
        except Exception:
            return False

    def generate(self, prompt: str) -> str:
        """Generate a response from Nemotin with observability tracking."""
        start_time = time.time()
        self._total_calls += 1

        try:
            response = self.client.chat.completions.create(
                model=settings.nemotron_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are the RISK-ERA AI risk investigation engine. "
                            "Analyze information carefully and provide evidence-based "
                            "responses. Do not invent transaction data or evidence."
                        ),
                    },
                ],
            )
            elapsed = time.time() - start_time
            self._success_count += 1
            self._response_times.append(elapsed)

            # Keep response times bounded
            if len(self._response_times) > 100:
                self._response_times = self._response_times[-50:]

            return response.choices[0].message.content or ""
        except Exception as e:
            elapsed = time.time() - start_time
            self._error_count += 1
            raise HTTPException(
                status_code=503,
                detail=f"Nemotin API unavailable: {str(e)}",
            )

    @property
    def metrics(self) -> dict[str, Any]:
        """Get Nemotin service metrics for observability."""
        avg_time = (
            sum(self._response_times) / len(self._response_times)
            if self._response_times else 0.0
        )
        availability = self.available
        return {
            "total_calls": self._total_calls,
            "success_count": self._success_count,
            "error_count": self._error_count,
            "availability": availability,
            "average_response_time_ms": round(avg_time * 1000, 2),
            "model": settings.nemotron_model,
        }


nemotron_service = NemotronService()