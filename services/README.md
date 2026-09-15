# services/

Python domain services. Each is an independent package with its own
`pyproject.toml`. In Phase 0 they are **stubs** — interfaces and docstrings only —
so the architecture and boundaries exist before the logic does.

| Service                | Phase | Responsibility                                                        |
| ---------------------- | ----- | ------------------------------------------------------------------- |
| `document-processing`  | 3     | Ingest legal sources → extract → clean → chunk → embed → pgvector   |
| `rag`                  | 4     | Query rewrite → hybrid search → rerank → context → Claude → guardrails |
| `legal-classifier`     | 5     | Classify a query into a legal category + jurisdiction scope         |
| `risk-engine`          | 5     | Score query risk (LOW/MEDIUM/HIGH/CRITICAL); decide advocate routing |
| *(document-assistant)* | 6     | Questionnaire + draft generation — no Phase 0 stub package; lives directly in `apps/api/app/services/document_assistant/` (docs/adr/0009) |
| `notifications`        | 11    | Fan out events to email / SMS / in-app; templates; provider adapters |

### How they are consumed

`apps/api` imports these as libraries (path dependencies). They do **not** run as
separate network services yet; if any needs to become one, it gets its own
FastAPI entrypoint + Dockerfile at that time.

### Local install

```bash
cd services/<name> && uv sync
```
