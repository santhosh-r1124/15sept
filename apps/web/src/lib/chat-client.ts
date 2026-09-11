import { apiFetch } from './api-client';

export interface ChatMessageOut {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  legal_category: string | null;
  jurisdiction_scope: string | null;
  is_out_of_scope: boolean | null;
  created_at: string;
}

export interface SendMessageResponse {
  conversation_id: string;
  user_message: ChatMessageOut;
  assistant_message: ChatMessageOut;
  disclaimer: string;
}

export interface ConversationSummary {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail {
  id: string;
  title: string | null;
  messages: ChatMessageOut[];
}

/** Bindings for `/api/v1/chat/*`. Works with or without a token (public tier). */
export const chatClient = {
  sendMessage: (message: string, conversationId: string | null, token: string | null) =>
    apiFetch<SendMessageResponse>('/api/v1/chat/messages', {
      method: 'POST',
      body: { message, conversation_id: conversationId ?? undefined },
      token,
    }),

  listConversations: (token: string) =>
    apiFetch<ConversationSummary[]>('/api/v1/chat/conversations', { token }),

  getConversation: (conversationId: string, token: string | null) =>
    apiFetch<ConversationDetail>(`/api/v1/chat/conversations/${conversationId}`, { token }),
};
