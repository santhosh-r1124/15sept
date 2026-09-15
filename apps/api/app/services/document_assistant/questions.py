"""Static per-document-type questionnaire (FRD §7).

A fixed schema per ``AssistantDocumentType``, not an LLM-driven dynamic
question flow: the FRD's own worked example (Affidavit -> Purpose, Name,
Address, Jurisdiction, Facts to declare, Supporting documents) is already a
fixed field list, and generating the *question set* with an LLM call would
add cost and latency for a result that's the same for every user of a given
document type anyway — see docs/adr/0009-document-assistant-scope.md.

Every set includes a ``state_code`` question: requirements for execution,
notarization, stamping and registration vary by Indian state (FRD §12), so
the state is always worth asking even where it isn't otherwise a "fact" of
the document itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.document_request import AssistantDocumentType


@dataclass(frozen=True, slots=True)
class Question:
    key: str
    label: str
    required: bool = True
    help_text: str | None = None


_STATE_QUESTION = Question(
    "state_code",
    "Which Indian state will this be used/executed in?",
    help_text="Stamp duty, registration and notarization requirements vary by state.",
)

QUESTION_SETS: dict[AssistantDocumentType, list[Question]] = {
    AssistantDocumentType.RENTAL_AGREEMENT: [
        Question("landlord_name", "Landlord's full name"),
        Question("tenant_name", "Tenant's full name"),
        Question("property_address", "Full address of the property"),
        _STATE_QUESTION,
        Question("monthly_rent", "Monthly rent amount"),
        Question("security_deposit", "Security deposit amount"),
        Question("lease_start_date", "Lease start date"),
        Question("lease_duration_months", "Lease duration (months)"),
        Question(
            "special_terms",
            "Any special terms (maintenance, notice period, pets, etc.)",
            required=False,
        ),
    ],
    AssistantDocumentType.EMPLOYMENT_AGREEMENT: [
        Question("employer_name", "Employer / company name"),
        Question("employee_name", "Employee's full name"),
        Question("designation", "Job title / designation"),
        _STATE_QUESTION,
        Question("monthly_salary", "Monthly salary / CTC"),
        Question("employment_start_date", "Employment start date"),
        Question("probation_period_months", "Probation period (months)", required=False),
        Question(
            "key_terms",
            "Any key terms to include (notice period, confidentiality, non-compete, etc.)",
            required=False,
        ),
    ],
    AssistantDocumentType.NDA: [
        Question("disclosing_party", "Disclosing party's name"),
        Question("receiving_party", "Receiving party's name"),
        Question("purpose", "Purpose of sharing confidential information"),
        _STATE_QUESTION,
        Question("effective_date", "Effective date"),
        Question("term_months", "How long should confidentiality obligations last (months)?"),
        Question(
            "mutual_or_one_way",
            "Is this mutual (both sides share info) or one-way?",
            required=False,
        ),
    ],
    AssistantDocumentType.AFFIDAVIT: [
        Question("purpose", "What is this affidavit for?"),
        Question("full_name", "Full name of the person making the affidavit (the deponent)"),
        Question("address", "Full residential address"),
        _STATE_QUESTION,
        Question("facts_to_declare", "The facts you want to declare, in your own words"),
        Question(
            "supporting_documents", "Any supporting documents you already have", required=False
        ),
    ],
    AssistantDocumentType.DECLARATION: [
        Question("declarant_name", "Name of the person making the declaration"),
        Question("address", "Full residential address"),
        _STATE_QUESTION,
        Question("purpose", "What is this declaration for?"),
        Question("facts_declared", "The facts being declared, in your own words"),
    ],
    AssistantDocumentType.BUSINESS_AGREEMENT: [
        Question("party_a_name", "First party's name"),
        Question("party_b_name", "Second party's name"),
        Question("business_purpose", "Purpose of the agreement"),
        _STATE_QUESTION,
        Question("effective_date", "Effective date"),
        Question("key_terms", "Key terms (payment, deliverables, term, termination, etc.)"),
    ],
    AssistantDocumentType.PARTNERSHIP_DOCUMENT: [
        Question("firm_name", "Name of the partnership firm"),
        Question("partner_names", "Names of all partners"),
        _STATE_QUESTION,
        Question("capital_contribution", "Capital contribution of each partner"),
        Question("profit_sharing_ratio", "Profit-sharing ratio"),
        Question("effective_date", "Effective date"),
    ],
    AssistantDocumentType.AUTHORIZATION_LETTER: [
        Question("authorizer_name", "Name of the person granting authorization"),
        Question("authorized_person_name", "Name of the person being authorized"),
        Question("purpose", "What is the authorized person being permitted to do?"),
        _STATE_QUESTION,
        Question("validity_period", "How long is this authorization valid for?", required=False),
    ],
    AssistantDocumentType.SERVICE_AGREEMENT: [
        Question("service_provider_name", "Service provider's name"),
        Question("client_name", "Client's name"),
        Question("service_description", "Description of the services to be provided"),
        _STATE_QUESTION,
        Question("fee_amount", "Fee / payment terms"),
        Question("effective_date", "Effective date"),
        Question("duration", "Duration of the agreement", required=False),
    ],
    AssistantDocumentType.LEGAL_NOTICE: [
        Question("sender_name", "Your name (the sender)"),
        Question("recipient_name", "Recipient's name"),
        Question("subject_matter", "What is this notice about?"),
        _STATE_QUESTION,
        Question("facts_and_grievance", "The facts and grievance, in your own words"),
        Question("relief_sought", "What outcome / relief are you seeking?"),
    ],
    AssistantDocumentType.OTHER: [
        Question("document_description", "Describe the document you need"),
        _STATE_QUESTION,
        Question("key_facts", "The key facts/details it should include"),
    ],
}


def questions_for(document_type: AssistantDocumentType) -> list[Question]:
    return QUESTION_SETS[document_type]


def missing_required_answers(
    document_type: AssistantDocumentType, answers: dict[str, str]
) -> list[str]:
    """Keys of required questions with no non-blank answer, in schema order."""
    return [
        q.key
        for q in questions_for(document_type)
        if q.required and not (answers.get(q.key) or "").strip()
    ]
