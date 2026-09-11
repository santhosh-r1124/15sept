"""Legal query classification (Phase 5).

Assigns every query one category from (mirrors ``@legal-platform/shared``)::

    CONSUMER_LAW CONTRACT_LAW IT_LAW CYBER_LAW DATA_PROTECTION IP_LAW
    PROPERTY_LAW EMPLOYMENT_LAW CORPORATE_LAW FAMILY_LAW CRIMINAL_LAW TAX_LAW
    DOCUMENT_GUIDANCE ADVOCATE_REQUIRED OUT_OF_SCOPE

plus a jurisdiction scope hint (central / state / local / ...). OUT_OF_SCOPE
short-circuits the RAG pipeline.
"""

__all__: list[str] = []
