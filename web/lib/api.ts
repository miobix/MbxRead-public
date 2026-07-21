export type Book = {
  id: number;
  title: string;
  source: string;
  current_page: number;
  page_count: number;
  created: string;
};

export type BookDetail = {
  id: number;
  title: string;
  current_page: number;
  page_count: number;
};

export type Token = {
  s: number;
  e: number;
  surface: string;
  lemma: string;
  pos: string;
};

export type TermStatus = "learning" | "known" | "ignored";

export type TermSummary = {
  id: number;
  translation: string;
  status: TermStatus;
  deck: string;
};

export type Term = {
  id: number;
  lemma: string;
  translation: string;
  notes: string;
  status: TermStatus;
  deck: string;
  sentence: string;
  anki_note_id: number | null;
  anki_dirty: boolean;
  created: string;
  updated: string;
};

export type Page = {
  page_no: number;
  page_count: number;
  content: string;
  tokens: Token[];
  terms: Record<string, TermSummary>;
};

export type DictEntry = {
  word: string;
  pos: string;
  definitions: { ko: string; en_word: string; en_def: string }[];
};

export type TranslateResult = { translation: string; backend: string; cached: boolean };

export type AnkiSyncResult = {
  added: number;
  updated: number;
  failed: { lemma: string; error: string }[];
};

export type Settings = {
  decks: string[];
  default_deck: string;
  translator_backend: "deepl" | "claude";
};

class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });

  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message = body.error ?? body.detail ?? message;
    } catch {
      // response body wasn't JSON — fall back to statusText
    }
    throw new ApiError(message);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  listBooks: () => request<Book[]>("/books"),

  createBook: (body: { title: string; text: string; source?: string }) =>
    request<Book>("/books", { method: "POST", body: JSON.stringify(body) }),

  getBook: (id: number) => request<BookDetail>(`/books/${id}`),

  patchBook: (id: number, body: { current_page?: number; title?: string }) =>
    request<BookDetail>(`/books/${id}`, { method: "PATCH", body: JSON.stringify(body) }),

  getPage: (bookId: number, pageNo: number) =>
    request<Page>(`/books/${bookId}/pages/${pageNo}`),

  createTerm: (body: {
    lemma: string;
    translation: string;
    status?: TermStatus;
    deck?: string;
    sentence?: string;
  }) => request<Term>("/terms", { method: "POST", body: JSON.stringify(body) }),

  patchTerm: (
    id: number,
    body: Partial<Pick<Term, "lemma" | "translation" | "notes" | "status" | "deck" | "sentence">>
  ) => request<Term>(`/terms/${id}`, { method: "PATCH", body: JSON.stringify(body) }),

  deleteTerm: (id: number) => request<void>(`/terms/${id}`, { method: "DELETE" }),

  listTerms: (params?: { status?: TermStatus; deck?: string; q?: string }) => {
    const sp = new URLSearchParams();
    if (params?.status) sp.set("status", params.status);
    if (params?.deck) sp.set("deck", params.deck);
    if (params?.q) sp.set("q", params.q);
    const qs = sp.toString();
    return request<Term[]>(`/terms${qs ? `?${qs}` : ""}`);
  },

  translate: (text: string, backend?: string) =>
    request<TranslateResult>("/translate", {
      method: "POST",
      body: JSON.stringify({ text, backend }),
    }),

  dictLookup: (word: string) =>
    request<DictEntry[]>(`/dict?word=${encodeURIComponent(word)}`),

  syncAnki: () => request<AnkiSyncResult>("/anki/sync", { method: "POST" }),

  getSettings: () => request<Settings>("/settings"),

  putSettings: (body: Partial<Settings>) =>
    request<Settings>("/settings", { method: "PUT", body: JSON.stringify(body) }),
};
