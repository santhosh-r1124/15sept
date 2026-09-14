"""Claude-backed query classification and grounded answer generation.

Classification (Phase 2) is intentionally lightweight (one forced tool call).
Phase 5 formalises this into a proper `services/legal-classifier` +
`services/risk-engine` pair; when that lands, this module should delegate to
them instead of reimplementing the taxonomy inline.

Generation (Phase 4) is grounded: the caller (app/api/v1/routes/chat.py) runs
`app.services.rag.retrieval.hybrid_search` first and passes the retrieved
chunks in as `context`. The model is instructed to answer only from that
context and to cite it — see `_GROUNDED_ANSWER_SYSTEM_PROMPT`. There is no
ungrounded generation path: per the product's "grounded, not guessed" rule
(docs/roadmap.md), if retrieval finds nothing, the caller returns
`INSUFFICIENT_EVIDENCE_MESSAGE` without calling this module at all.
"""

from __future__ import annotations

from dataclasses import dataclass

import anthropic

from app.core.config import Settings
from app.core.errors import ServiceUnavailableError
from app.core.logging import get_logger
from app.services.rag.retrieval import RetrievedChunk

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

_GROUNDED_ANSWER_SYSTEM_PROMPT = (
    "You are the Legal Advisor assistant: a general Indian legal-information "
    "helper for consumers, IT professionals, startups and organisations.\n\n"
    "Each user turn includes a SOURCES block: numbered excerpts retrieved from "
    "verified Indian legal documents, followed by the actual QUESTION.\n\n"
    "Rules:\n"
    "- Answer using ONLY the SOURCES provided. Do not use outside knowledge of "
    "Indian law, and do not fill gaps with assumptions.\n"
    "- Cite the source(s) backing every factual claim with its bracketed "
    "number, e.g. [1], right after the claim. Do not cite a source for a "
    "sentence it doesn't actually support.\n"
    "- If the sources don't fully answer the question, say plainly what they "
    "don't cover instead of guessing, and recommend consulting a qualified "
    "advocate for that part.\n"
    "- Provide general legal information and document guidance only — never "
    "individualised legal advice — and never claim to be a lawyer or to create "
    "an advocate-client relationship.\n"
    "- If the answer genuinely depends on state law, local rules, stamp duty, "
    "registration procedure, or court jurisdiction and the sources don't "
    "specify which, say so explicitly and ask which Indian state/city is "
    "involved rather than quoting one figure as universal.\n"
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


def _format_context(context: list[RetrievedChunk]) -> str:
    parts: list[str] = []
    for index, chunk in enumerate(context, start=1):
        label = chunk.document_title
        if chunk.section:
            label += f", Section {chunk.section}"
        if chunk.article:
            label += f", Article {chunk.article}"
        parts.append(f"[{index}] {label}\n{chunk.content}")
    return "\n\n".join(parts)


async def generate_grounded_answer(
    message: str,
    *,
    history: list[tuple[str, str]],
    context: list[RetrievedChunk],
    settings: Settings,
) -> str:
    """`history` is a list of (role, content) pairs, oldest first. `context`
    is the hybrid-search result for the *current* message only — prior turns
    in `history` keep whatever plain text was actually said, not their
    original sources block, since that's what the conversation actually was.
    """
    client = _client(settings)
    messages: list[dict[str, object]] = [
        {"role": role, "content": content} for role, content in history
    ]
    messages.append(
        {
            "role": "user",
            "content": f"SOURCES:\n{_format_context(context)}\n\nQUESTION: {message}",
        }
    )

    try:
        response = await client.messages.create(
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            system=_GROUNDED_ANSWER_SYSTEM_PROMPT,
            messages=messages,  # type: ignore[arg-type]
        )
    except Exception as exc:  # Anthropic SDK: network/auth/rate-limit/etc.
        logger.warning("llm_generate_failed", error=str(exc))
        raise ServiceUnavailableError(
            "Could not reach the legal assistant. Please try again shortly.", code="llm_error"
        ) from exc

    text = "\n".join(block.text for block in response.content if block.type == "text").strip()
    return text or "I couldn't generate a response just now. Please try again in a moment."
