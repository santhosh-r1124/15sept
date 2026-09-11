"""Document processing / ingestion (Phase 3).

    legal source
      -> download
      -> PDF / HTML extraction
      -> text cleaning
      -> document metadata  (document_id, law_name, section, jurisdiction, state,
                             source_url, effective_date, version, page_number, ...)
      -> chunking
      -> embeddings
      -> pgvector upsert

Tracks ingestion failures for the admin dashboard (Phase 12).
"""

__all__: list[str] = []
