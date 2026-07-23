export type BookStatus = "library" | "candidate" | "discarded";

export type Book = {
  id: number;
  title: string;
  source: string;
  current_page: number;
  page_count: number;
  created: string;
  coverage: number | null;
  new_per_page: number | null;
  scored_at: string | null;
  topic: string;
  tags: string[];
  source_url: string;
  source_ref: string | null;
  fetched: string | null;
  archived: boolean;
  read: boolean;
  status: BookStatus;
  general_coverage: number | null;
  general_level: "easy" | "medium" | "hard" | null;
};

export type ScoreResult = {
  coverage: number | null;
  new_lemmas: number;
  total_lemmas: number;
  new_per_page: number;
  general_coverage: number | null;
  general_level: "easy" | "medium" | "hard" | null;
};

export type FeedFetchResult = {
  checked_feeds: number;
  skipped_feed_types: number;
  candidates_created: number;
  feeds: {
    id: number;
    name: string;
    items_seen?: number;
    created?: number;
    skipped_duplicate?: number;
    failed?: number;
    fetch_error?: string;
    skipped_type?: string;
  }[];
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

async function handleResponse<T>(res: Response): Promise<T> {
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  return handleResponse<T>(res);
}

// No Content-Type header here — the browser sets multipart/form-data with the
// right boundary itself; forcing application/json (like `request` does) would
// break the upload.
async function requestForm<T>(path: string, formData: FormData): Promise<T> {
  const res = await fetch(`/api${path}`, { method: "POST", body: formData });
  return handleResponse<T>(res);
}

export const api = {
  listBooks: (params?: {
    topic?: string;
    archived?: boolean;
    source?: string;
    status?: BookStatus;
  }) => {
    const sp = new URLSearchParams();
    if (params?.topic) sp.set("topic", params.topic);
    if (params?.archived !== undefined) sp.set("archived", String(params.archived));
    if (params?.source) sp.set("source", params.source);
    if (params?.status) sp.set("status", params.status);
    const qs = sp.toString();
    return request<Book[]>(`/books${qs ? `?${qs}` : ""}`);
  },

  createBook: (body: {
    title: string;
    text: string;
    source?: string;
    topic?: string;
    tags?: string[];
  }) => request<Book>("/books", { method: "POST", body: JSON.stringify(body) }),

  getBook: (id: number) => request<BookDetail>(`/books/${id}`),

  scoreText: (text: string) =>
    request<ScoreResult>("/score", { method: "POST", body: JSON.stringify({ text }) }),

  scoreBook: (id: number) => request<Book>(`/books/${id}/score`, { method: "POST" }),

  patchBook: (
    id: number,
    body: {
      current_page?: number;
      title?: string;
      topic?: string;
      tags?: string[];
      archived?: boolean;
      read?: boolean;
      status?: BookStatus;
    }
  ) => request<Book>(`/books/${id}`, { method: "PATCH", body: JSON.stringify(body) }),

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

  importYoutube: (body: { url: string; topic?: string; tags?: string[] }) =>
    request<Book>("/import/youtube", { method: "POST", body: JSON.stringify(body) }),

  importArticle: (body: { url: string; topic?: string; tags?: string[] }) =>
    request<Book>("/import/article", { method: "POST", body: JSON.stringify(body) }),

  importPdf: (body: {
    file: File;
    title?: string;
    topic?: string;
    tags?: string;
    pages?: string;
  }) => {
    const fd = new FormData();
    fd.set("file", body.file);
    if (body.title) fd.set("title", body.title);
    if (body.topic) fd.set("topic", body.topic);
    if (body.tags) fd.set("tags", body.tags);
    if (body.pages) fd.set("pages", body.pages);
    return requestForm<Book>("/import/pdf", fd);
  },

  fetchFeeds: () => request<FeedFetchResult>("/feeds/fetch", { method: "POST" }),
};
