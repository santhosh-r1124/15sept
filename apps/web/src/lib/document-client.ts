import { apiFetch } from './api-client';

export interface QuestionOut {
  key: string;
  label: string;
  required: boolean;
  help_text: string | null;
}

export interface DocumentTypeInfoOut {
  document_type: string;
  questions: QuestionOut[];
}

export interface DocumentRequestOut {
  id: string;
  document_type: string;
  state_code: string | null;
  answers: Record<string, string>;
  draft_text: string;
  created_at: string;
}

export interface CreateDocumentResponse {
  document: DocumentRequestOut;
  disclaimer: string;
}

/** Bindings for `/api/v1/documents/*`. Works with or without a token (public tier). */
export const documentClient = {
  listTypes: () => apiFetch<DocumentTypeInfoOut[]>('/api/v1/documents/types'),

  create: (documentType: string, answers: Record<string, string>, token: string | null) =>
    apiFetch<CreateDocumentResponse>('/api/v1/documents', {
      method: 'POST',
      body: { document_type: documentType, answers },
      token,
    }),

  listMine: (token: string) => apiFetch<DocumentRequestOut[]>('/api/v1/documents', { token }),

  get: (documentId: string, token: string | null) =>
    apiFetch<DocumentRequestOut>(`/api/v1/documents/${documentId}`, { token }),
};
