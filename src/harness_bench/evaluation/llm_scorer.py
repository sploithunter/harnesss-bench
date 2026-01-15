"""LLM-based scoring for subjective code evaluation criteria.

This module provides LLM-based scoring for criteria that are difficult
to evaluate programmatically, such as:
- Code style and readability
- Documentation quality
- Architecture decisions
- Best practices adherence

Similar to the approach used in ConnextDev benchmarks.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMScoreResult:
    """Result from LLM scoring."""

    score: float  # 0.0 to 1.0
    reasoning: str
    criterion: str
    raw_response: str | None = None


class LLMScorer(ABC):
    """Abstract base class for LLM-based code scoring."""

    @abstractmethod
    def score(self, code: str, criterion_prompt: str) -> float:
        """Score code against a criterion.

        Args:
            code: The code to evaluate
            criterion_prompt: Description of what to evaluate

        Returns:
            Score from 0.0 to 1.0
        """
        pass

    @abstractmethod
    def score_detailed(self, code: str, criterion_prompt: str) -> LLMScoreResult:
        """Score code with detailed reasoning.

        Args:
            code: The code to evaluate
            criterion_prompt: Description of what to evaluate

        Returns:
            LLMScoreResult with score and reasoning
        """
        pass

    def score_with_reference(
        self,
        submission: str,
        reference: str | None,
        solution_explanation: str | None,
        criterion: str,
    ) -> float:
        """Score submission code by comparing against reference solution.

        The reference code should have comments explaining key points,
        which serve as hints for the evaluation.

        Args:
            submission: The submitted code to evaluate
            reference: Reference solution code (with explanatory comments)
            solution_explanation: Optional solution.md content explaining the fix
            criterion: What aspect to evaluate

        Returns:
            Score from 0.0 to 1.0
        """
        # Default implementation builds an enhanced prompt
        # Subclasses can override for more sophisticated comparison
        result = self.score_with_reference_detailed(
            submission, reference, solution_explanation, criterion
        )
        return result.score

    def score_with_reference_detailed(
        self,
        submission: str,
        reference: str | None,
        solution_explanation: str | None,
        criterion: str,
    ) -> LLMScoreResult:
        """Score submission with detailed reasoning by comparing against reference.

        Args:
            submission: The submitted code to evaluate
            reference: Reference solution code (with explanatory comments)
            solution_explanation: Optional solution.md content explaining the fix
            criterion: What aspect to evaluate

        Returns:
            LLMScoreResult with score and reasoning
        """
        # Build enhanced prompt with reference
        enhanced_prompt = self._build_reference_prompt(
            submission, reference, solution_explanation, criterion
        )
        return self.score_detailed(submission, enhanced_prompt)

    def _build_reference_prompt(
        self,
        submission: str,
        reference: str | None,
        solution_explanation: str | None,
        criterion: str,
    ) -> str:
        """Build a prompt that includes reference code for comparison."""
        parts = [criterion]

        if reference:
            parts.append(
                "\n\n## Reference Solution\n"
                "The reference code below shows the correct implementation. "
                "Comments in the code explain WHY each part is important:\n"
                f"```python\n{reference}\n```"
            )

        if solution_explanation:
            parts.append(
                f"\n\n## Solution Explanation\n{solution_explanation}"
            )

        parts.append(
            "\n\n## Scoring Guidelines\n"
            "- Compare the submission against the reference solution\n"
            "- Give partial credit for correct concepts even if implementation differs\n"
            "- Note which key elements from the reference are present/missing\n"
            "- Comments in the reference highlight critical requirements"
        )

        return "\n".join(parts)


class AnthropicScorer(LLMScorer):
    """LLM scorer using Anthropic's Claude API."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: str | None = None,
    ):
        """Initialize with Anthropic API.

        Args:
            model: Claude model to use
            api_key: API key (defaults to ANTHROPIC_API_KEY env var)
        """
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")

        if not self.api_key:
            raise ValueError(
                "Anthropic API key required. Set ANTHROPIC_API_KEY env var "
                "or pass api_key parameter."
            )

    def _create_prompt(self, code: str, criterion_prompt: str) -> str:
        """Create the scoring prompt."""
        return f"""You are evaluating code quality for a benchmark. Score the following code on a scale of 0.0 to 1.0 based on the criterion provided.

## Criterion
{criterion_prompt}

## Code to Evaluate
```
{code}
```

## Instructions
1. Analyze the code against the criterion
2. Provide a brief reasoning (2-3 sentences)
3. Give a score from 0.0 (completely fails criterion) to 1.0 (perfectly meets criterion)

Respond in JSON format:
{{
    "score": <float between 0.0 and 1.0>,
    "reasoning": "<brief explanation>"
}}"""

    def score(self, code: str, criterion_prompt: str) -> float:
        """Score code against a criterion."""
        result = self.score_detailed(code, criterion_prompt)
        return result.score

    def score_detailed(self, code: str, criterion_prompt: str) -> LLMScoreResult:
        """Score code with detailed reasoning."""
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic package required for AnthropicScorer. "
                "Install with: pip install anthropic"
            )

        client = anthropic.Anthropic(api_key=self.api_key)

        prompt = self._create_prompt(code, criterion_prompt)

        message = client.messages.create(
            model=self.model,
            max_tokens=500,
            messages=[
                {"role": "user", "content": prompt}
            ],
        )

        response_text = message.content[0].text

        # Parse JSON response
        try:
            # Try to extract JSON from response
            response_text = response_text.strip()
            if response_text.startswith("```"):
                # Remove markdown code blocks
                lines = response_text.split("\n")
                response_text = "\n".join(
                    l for l in lines
                    if not l.startswith("```")
                )

            data = json.loads(response_text)
            score = float(data.get("score", 0.0))
            reasoning = data.get("reasoning", "")

            # Clamp score to valid range
            score = max(0.0, min(1.0, score))

            return LLMScoreResult(
                score=score,
                reasoning=reasoning,
                criterion=criterion_prompt[:100],
                raw_response=response_text,
            )

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            # Fallback: try to extract score from text
            import re
            match = re.search(r"(\d+\.?\d*)\s*(/\s*1|out of 1)?", response_text)
            if match:
                score = float(match.group(1))
                if score > 1.0:
                    score = score / 10.0 if score <= 10 else score / 100.0
                score = max(0.0, min(1.0, score))

                return LLMScoreResult(
                    score=score,
                    reasoning=f"Extracted from response: {response_text[:200]}",
                    criterion=criterion_prompt[:100],
                    raw_response=response_text,
                )

            # Complete failure to parse
            return LLMScoreResult(
                score=0.5,  # Neutral score on parse failure
                reasoning=f"Failed to parse LLM response: {e}",
                criterion=criterion_prompt[:100],
                raw_response=response_text,
            )


class OpenAIScorer(LLMScorer):
    """LLM scorer using OpenAI's API."""

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
    ):
        """Initialize with OpenAI API.

        Args:
            model: OpenAI model to use
            api_key: API key (defaults to OPENAI_API_KEY env var)
        """
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")

        if not self.api_key:
            raise ValueError(
                "OpenAI API key required. Set OPENAI_API_KEY env var "
                "or pass api_key parameter."
            )

    def _create_prompt(self, code: str, criterion_prompt: str) -> str:
        """Create the scoring prompt."""
        return f"""You are evaluating code quality for a benchmark. Score the following code on a scale of 0.0 to 1.0 based on the criterion provided.

## Criterion
{criterion_prompt}

## Code to Evaluate
```
{code}
```

## Instructions
1. Analyze the code against the criterion
2. Provide a brief reasoning (2-3 sentences)
3. Give a score from 0.0 (completely fails criterion) to 1.0 (perfectly meets criterion)

Respond in JSON format:
{{
    "score": <float between 0.0 and 1.0>,
    "reasoning": "<brief explanation>"
}}"""

    def score(self, code: str, criterion_prompt: str) -> float:
        """Score code against a criterion."""
        result = self.score_detailed(code, criterion_prompt)
        return result.score

    def score_detailed(self, code: str, criterion_prompt: str) -> LLMScoreResult:
        """Score code with detailed reasoning."""
        try:
            import openai
        except ImportError:
            raise ImportError(
                "openai package required for OpenAIScorer. "
                "Install with: pip install openai"
            )

        client = openai.OpenAI(api_key=self.api_key)

        prompt = self._create_prompt(code, criterion_prompt)

        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
        )

        response_text = response.choices[0].message.content

        # Parse JSON response (same logic as Anthropic)
        try:
            response_text = response_text.strip()
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                response_text = "\n".join(
                    l for l in lines
                    if not l.startswith("```")
                )

            data = json.loads(response_text)
            score = float(data.get("score", 0.0))
            reasoning = data.get("reasoning", "")

            score = max(0.0, min(1.0, score))

            return LLMScoreResult(
                score=score,
                reasoning=reasoning,
                criterion=criterion_prompt[:100],
                raw_response=response_text,
            )

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            import re
            match = re.search(r"(\d+\.?\d*)\s*(/\s*1|out of 1)?", response_text)
            if match:
                score = float(match.group(1))
                if score > 1.0:
                    score = score / 10.0 if score <= 10 else score / 100.0
                score = max(0.0, min(1.0, score))

                return LLMScoreResult(
                    score=score,
                    reasoning=f"Extracted from response: {response_text[:200]}",
                    criterion=criterion_prompt[:100],
                    raw_response=response_text,
                )

            return LLMScoreResult(
                score=0.5,
                reasoning=f"Failed to parse LLM response: {e}",
                criterion=criterion_prompt[:100],
                raw_response=response_text,
            )


def create_scorer(provider: str = "anthropic", **kwargs) -> LLMScorer:
    """Create an LLM scorer for the specified provider.

    Args:
        provider: "anthropic" or "openai"
        **kwargs: Additional arguments for the scorer

    Returns:
        LLMScorer instance
    """
    if provider == "anthropic":
        return AnthropicScorer(**kwargs)
    elif provider == "openai":
        return OpenAIScorer(**kwargs)
    else:
        raise ValueError(f"Unknown provider: {provider}. Use 'anthropic' or 'openai'.")
