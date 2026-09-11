'use client';

import { MANDATORY_DISCLAIMER } from '@legal-platform/shared';
import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { ApiRequestError } from '@/lib/api-client';
import { useAuth } from '@/lib/auth-context';
import {
  chatClient,
  type ChatMessageOut,
  type ConversationSummary,
} from '@/lib/chat-client';

const CONVERSATION_KEY = 'lp_chat_conversation_id';

// FRD example questions — shown as chips on a fresh conversation.
const SUGGESTED_QUESTIONS = [
  'What is an affidavit?',
  'What documents are generally required for an affidavit?',
  'What is the difference between an agreement and a contract?',
  'What information is normally included in a rental agreement?',
  'What are the basic requirements for an employment agreement?',
  'What is the process for registering a company in India?',
];

export default function ChatPage() {
  const { user, accessToken, loading: authLoading } = useAuth();
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessageOut[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [disclaimer, setDisclaimer] = useState(MANDATORY_DISCLAIMER);
  const [history, setHistory] = useState<ConversationSummary[] | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  // Restore a saved conversation once auth state has settled.
  useEffect(() => {
    if (authLoading) return;
    const saved = window.localStorage.getItem(CONVERSATION_KEY);
    if (!saved) return;
    let cancelled = false;
    chatClient
      .getConversation(saved, accessToken)
      .then((detail) => {
        if (cancelled) return;
        setConversationId(detail.id);
        setMessages(detail.messages);
      })
      .catch(() => {
        window.localStorage.removeItem(CONVERSATION_KEY);
      });
    return () => {
      cancelled = true;
    };
  }, [authLoading, accessToken]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  async function handleSend(text?: string) {
    const content = (text ?? input).trim();
    if (!content || sending) return;
    setError(null);
    setInput('');
    setSending(true);

    const pendingId = `pending-${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      {
        id: pendingId,
        role: 'user',
        content,
        legal_category: null,
        jurisdiction_scope: null,
        is_out_of_scope: null,
        created_at: new Date().toISOString(),
      },
    ]);

    try {
      const res = await chatClient.sendMessage(content, conversationId, accessToken);
      setDisclaimer(res.disclaimer);
      setConversationId(res.conversation_id);
      window.localStorage.setItem(CONVERSATION_KEY, res.conversation_id);
      setMessages((prev) => [
        ...prev.filter((m) => m.id !== pendingId),
        res.user_message,
        res.assistant_message,
      ]);
    } catch (err) {
      setMessages((prev) => prev.filter((m) => m.id !== pendingId));
      setInput(content);
      setError(
        err instanceof ApiRequestError
          ? err.message
          : 'Something went wrong reaching the assistant. Try again.',
      );
    } finally {
      setSending(false);
    }
  }

  function handleNewConversation() {
    setConversationId(null);
    setMessages([]);
    setError(null);
    window.localStorage.removeItem(CONVERSATION_KEY);
  }

  async function toggleHistory() {
    if (!showHistory && accessToken) {
      try {
        setHistory(await chatClient.listConversations(accessToken));
      } catch {
        setHistory([]);
      }
    }
    setShowHistory((s) => !s);
  }

  async function loadConversation(id: string) {
    try {
      const detail = await chatClient.getConversation(id, accessToken);
      setConversationId(detail.id);
      setMessages(detail.messages);
      window.localStorage.setItem(CONVERSATION_KEY, detail.id);
      setShowHistory(false);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : 'Could not load that conversation.');
    }
  }

  function onInputKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col px-4 py-6">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Legal Chat</h1>
          <p className="text-xs text-slate-500">
            {user ? `Signed in as ${user.email}` : 'Browsing anonymously — sign in to keep your history'}
          </p>
        </div>
        <div className="flex gap-2">
          {user && (
            <button
              type="button"
              onClick={() => void toggleHistory()}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
            >
              History
            </button>
          )}
          <button
            type="button"
            onClick={handleNewConversation}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            New conversation
          </button>
        </div>
      </div>

      {showHistory && (
        <div className="mb-4 max-h-48 overflow-y-auto rounded-lg border border-slate-200 bg-white p-2 text-sm">
          {history === null || history.length === 0 ? (
            <p className="p-2 text-slate-500">No past conversations yet.</p>
          ) : (
            <ul className="flex flex-col">
              {history.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => void loadConversation(c.id)}
                    className="w-full rounded px-2 py-1.5 text-left hover:bg-slate-50"
                  >
                    {c.title || 'Untitled conversation'}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="flex-1 overflow-y-auto rounded-xl border border-slate-200 bg-white p-4">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <p className="text-sm text-slate-500">Ask a general Indian legal question to start.</p>
            <div className="flex flex-wrap justify-center gap-2">
              {SUGGESTED_QUESTIONS.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => void handleSend(q)}
                  className="rounded-full border border-slate-300 px-3 py-1.5 text-xs text-slate-700 hover:border-blue-500 hover:text-blue-700"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {messages.map((m) => (
              <MessageBubble key={m.id} message={m} />
            ))}
            {sending && <MessageBubble message={null} />}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {error && <p className="mt-2 text-sm text-rose-600">{error}</p>}

      <div className="mt-3 flex gap-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onInputKeyDown}
          rows={2}
          placeholder="Ask a legal question…"
          className="flex-1 resize-none rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        />
        <button
          type="button"
          onClick={() => void handleSend()}
          disabled={sending || !input.trim()}
          className="self-end rounded-lg bg-blue-700 px-4 py-2 text-sm font-medium text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-60"
        >
          Send
        </button>
      </div>

      <p className="mt-4 text-center text-xs leading-relaxed text-slate-400">{disclaimer}</p>
    </main>
  );
}

function MessageBubble({ message }: { message: ChatMessageOut | null }) {
  if (message === null) {
    return (
      <div className="flex justify-start">
        <div className="max-w-[80%] rounded-2xl rounded-bl-sm bg-slate-100 px-4 py-2 text-sm text-slate-400">
          Thinking…
        </div>
      </div>
    );
  }

  const isUser = message.role === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm ${
          isUser
            ? 'rounded-br-sm bg-blue-700 text-white'
            : 'rounded-bl-sm bg-slate-100 text-slate-800'
        }`}
      >
        {message.content}
      </div>
    </div>
  );
}
