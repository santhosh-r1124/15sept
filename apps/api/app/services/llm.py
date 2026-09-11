"""Claude-backed query classification and answer generation (Phase 2).

No retrieval grounding yet — that's `services/document-processing` (Phase 3)
and `services/rag` (Phase 4). Generation is instructed to stay general and
defer to an advocate for anything needing case-specific judgement rather than
inventing specifics, which is the closest honest approximation of the
platform's "don't guess" rule until real grounding exists.

Classification is intentionally lightweight (one forced tool call). Phase 5
formalises this into a proper `services/legal-classifier` + `services/risk-engine`
pair; when that lands, this module should delegate to them instead of
reimplementing the taxonomy inline.
"""

from __future__ import annotations

from dataclasses import dataclass

import anthropic

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError
from app.core.logging import get_logger

logger = get_logger("app.llm")

# Mirrors packages/shared/src/legal.ts (LEGAL_CATEGORIES) — keep in sync.
LEGAL_CATEGORIES = (
    "CONSUMER_LAW",
    "CONTRACT_LAW",
    "IT_LAW",
    "CYBER_LAW",
    "DATA_PROTECTION",
    "IP_LAW",
    "PROPERTY_LAW",
    "EMPLOYMENT_LAW",
    "CORPORATE_LAW",
    "FAMILY_LAW",
    "CRIMINAL_LAW",
    "TAX_LAW",
    "DOCUMENT_GUIDANCE",
    "ADVOCATE_REQUIRED",
    "OUT_OF_SCOPE",
)

# Mirrors packages/shared/src/legal.ts (JURISDICTION_SCOPES) — keep in sync.
JURISDICTION_SCOPES = (
    "CENTRAL",
    "STATE",
    "LOCAL",
    "DISTRICT",
    "COURT",
    "REGISTRATION_AUTHORITY",
    "STAMP_DUTY",
    "UNKNOWN",
)

_CLASSIFY_TOOL: dict[str, object] = {
    "name": "classify_legal_query",
    "description": "Record the classification of a message to an Indian legal-info assistant.",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": list(LEGAL_CATEGORIES)},
            "jurisdiction_scope": {"type": "string", "enum": list(JURISDICTION_SCOPES)},
            "is_out_of_scope": {
                "type": "boolean",
                "description": "True only if the message has no connection to Indian law at all.",
            },
        },
        "required": ["category", "jurisdiction_scope", "is_out_of_scope"],
    },
}

_CLASSIFIER_SYSTEM_PROMPT = (
    "You triage messages for an Indian legal-information platform. Classify the "
    "user's message by calling classify_legal_query.\n"
    "- `category`: the closest legal domain. Use ADVOCATE_REQUIRED for disputes, "
    "notices, or matters clearly needing professional representation; use "
    "DOCUMENT_GUIDANCE for questions about drafting/understanding a document.\n"
    "- `jurisdiction_scope`: STATE, LOCAL, STAMP_DUTY, REGISTRATION_AUTHORITY, "
    "DISTRICT, or COURT if the answer likely depends on which Indian state/city "
    "is involved; CENTRAL if it's purely national law; UNKNOWN if unclear.\n"
    "- `is_out_of_scope`: true only for messages with no connection to Indian "
    "law, legal processes, or legal documents at all — general chit-chat, "
    "coding help, medical/financial advice, creative writing, other countries' "
    "law with no Indian angle, etc. A greeting that asks what the assistant can "
    "help with is NOT out of scope (category DOCUMENT_GUIDANCE, scope UNKNOWN)."
)

_ANSWER_SYSTEM_PROMPT = (
    "You are the Legal Advisor assistant: a general Indian legal-information "
    "helper for consumers, IT professionals, startups and organisations.\n\n"
    "Rules:\n"
    "- Provide general legal information and document guidance only — never "
    "individualised legal advice — and never claim to be a lawyer or to create "
    "an advocate-client relationship.\n"
    "- If the answer genuinely depends on state law, local rules, stamp duty, "
    "registration procedure, or court jurisdiction, say so explicitly and ask "
    "which Indian state/city is involved rather than quoting one figure as "
    "universal.\n"
    "- If a question needs case-specific judgement, document drafting, "
    "representation, or you are not confident of the current legal position, "
    "say that plainly and recommend consulting a qualified advocate instead of "
    "guessing.\n"
    "- Keep answers concise and in plain language, structured with short "
    "paragraphs or bullet points where useful.\n"
    "- Do not restate the platform's legal disclaimer yourself — it is shown "
    "separately by the product."
)


@dataclass(frozen=True, slots=True)
class Classification:
    category: str
    jurisdiction_scope: str
    is_out_of_scope: bool


def _client(settings: Settings) -> anthropic.AsyncAnthropic:
    if not settings.anthropic_api_key:
        raise ServiceUnavailableError(
            "The legal assistant isn't configured yet (missing ANTHROPIC_API_KEY).",
            code="llm_not_configured",
        )
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


async def classify_query(message: str, *, settings: Settings) -> Classification:
    """One forced tool call — fast, cheap, and reliably structured."""
    client = _client(settings)
    try:
        # The tool/tool_choice shapes are built as plain dicts (see _CLASSIFY_TOOL)
        # rather than the SDK's precise TypedDicts, so this doesn't match any
        # overload statically — it's correct at runtime (the SDK validates it).
        response = await client.messages.create(  # type: ignore[call-overload]
            model=settings.llm_model,
            max_tokens=settings.llm_classifier_max_tokens,
            system=_CLASSIFIER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": message}],
            tools=[_CLASSIFY_TOOL],
            tool_choice={"type": "tool", "name": "classify_legal_query"},
        )
    except Exception as exc:  # Anthropic SDK: network/auth/rate-limit/etc.
        logger.warning("llm_classify_failed", error=str(exc))
        raise ServiceUnavailableError(
            "Could not reach the legal assistant. Please try again shortly.", code="llm_error"
        ) from exc

    for block in response.content:
        if block.type == "tool_use" and block.name == "classify_legal_query":
            data = block.input if isinstance(block.input, dict) else {}
            category = data.get("category")
            scope = data.get("jurisdiction_scope")
            return Classification(
                category=category if category in LEGAL_CATEGORIES else "OUT_OF_SCOPE",
                jurisdiction_scope=scope if scope in JURISDICTION_SCOPES else "UNKNOWN",
                is_out_of_scope=bool(data.get("is_out_of_scope", False)),
            )

    # The model didn't call the forced tool — shouldn't happen, fail safe.
    logger.warning("llm_classify_no_tool_call")
    return Classification(
        category="OUT_OF_SCOPE", jurisdiction_scope="UNKNOWN", is_out_of_scope=True
    )


async def generate_answer(
    message: str, *, history: list[tuple[str, str]], settings: Settings
) -> str:
    """`history` is a list of (role, content) pairs, oldest first."""
    client = _client(settings)
    messages: list[dict[str, object]] = [
        {"role": role, "content": content} for role, content in history
    ]
    messages.append({"role": "user", "content": message})

    try:
        response = await client.messages.create(
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            system=_ANSWER_SYSTEM_PROMPT,
            messages=messages,  # type: ignore[arg-type]
        )
    except Exception as exc:  # Anthropic SDK: network/auth/rate-limit/etc.
        logger.warning("llm_generate_failed", error=str(exc))
        raise ServiceUnavailableError(
            "Could not reach the legal assistant. Please try again shortly.", code="llm_error"
        ) from exc

    text = "\n".join(block.text for block in response.content if block.type == "text").strip()
    return text or "I couldn't generate a response just now. Please try again in a moment."
