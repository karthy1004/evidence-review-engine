"""Claude-backed extractor. Optional: install with `pip install .[llm]` and set
ANTHROPIC_API_KEY (or sign in with `ant auth login`).

The model only *proposes* fields. The pipeline validates and grounds them; nothing
the model returns reaches the scoring engine without passing those checks.

Not exercised in CI (CI has no key and must not spend money). Coverage excludes this
file for that reason; the pipeline is tested with a scripted fake that hits the same
code paths (refusal, invalid output, retry with feedback).
"""

from __future__ import annotations

import anthropic

from evidence_review.extraction.base import ExtractedFields, RawExtraction

MODEL = "claude-opus-5-5"
# USD per million tokens for MODEL, from Anthropic's published price list (Oct 2026).
PRICE_IN, PRICE_OUT = 4.00, 20.00

SYSTEM = """You extract fields from supply-chain due-diligence documents.

Rules:
- Return only what the document states. If a field is not stated, return null.
  Never infer, normalise names, or fill gaps from general knowledge.
- Copy holder_name, reference_number and issuer exactly as written.
- Dates as YYYY-MM-DD. If a date is ambiguous or missing, return null.
- document_type must be one of the allowed values; if none fits, return null."""


class ClaudeExtractor:
    name = f"claude:{MODEL}"
    supports_feedback = True
    cost_per_mtok_in = PRICE_IN
    cost_per_mtok_out = PRICE_OUT

    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        self._client = client or anthropic.Anthropic()

    def extract(self, text: str, feedback: str | None = None) -> RawExtraction:
        content = f"<document>\n{text}\n</document>"
        if feedback:
            content += (
                "\n\nYour previous extraction failed validation:\n"
                f"{feedback}\nRe-read the document and correct only what is wrong. "
                "Use null where the document does not state a value."
            )
        try:
            response = self._client.messages.parse(
                model=MODEL,
                max_tokens=2048,
                system=SYSTEM,
                output_config={"effort": "low"},  # short, well-specified extraction
                messages=[{"role": "user", "content": content}],
                output_format=ExtractedFields,
            )
        except anthropic.RateLimitError as exc:  # SDK already retried twice
            return RawExtraction(data=None, model=MODEL, notes=[f"rate limited: {exc.message}"])
        except anthropic.APIConnectionError:
            return RawExtraction(data=None, model=MODEL, notes=["connection error"])
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                return RawExtraction(
                    data=None, model=MODEL, notes=[f"server error {exc.status_code}"]
                )
            raise  # 4xx = configuration problem; fail loudly

        usage = response.usage
        if response.stop_reason == "refusal":
            return RawExtraction(
                data=None,
                refused=True,
                model=MODEL,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
            )
        parsed = response.parsed_output
        return RawExtraction(
            data=parsed.model_dump() if parsed is not None else None,
            model=MODEL,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )
