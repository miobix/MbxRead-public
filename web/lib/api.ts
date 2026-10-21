export type BookStatus = "library" | "candidate" | "discarded";

export type Book = {
  id: number;
  title: string;
  source: string;
  current_offset: number;
  page_count: number;
  total_chars: number;
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
  word_count: number | null;
  duration_seconds: number | null;
  feed_id: number | null;
  discard_reason: "user" | "expired" | null;
  last_opened: string | null;
};

export type BookSort = "recent" | "opened" | "easiest" | "shortest";

// Subtitle import is a batch — a whole season goes in at once — so partial
// success is the normal outcome and the result is a per-file summary rather
// than a single Book.
export type SubtitleImportResult = {
  imported: Book[];
  skipped: { filename: string; reason: string }[];
  failed: { filename: string; error: string }[];
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
  candidates_created: number;
  expired: number;
  feeds: {
    id: number;
    name: string;
    items_seen?: number;
    created?: number;
    skipped_duplicate?: number;
    skipped_no_subs?: number;
    failed?: number;
    fetch_error?: string;
  }[];
};

export type FeedType = "rss" | "youtube";

export type Feed = {
  id: number;
  name: string;
  type: FeedType;
  url_or_channel_id: string;
  topic: string;
  enabled: boolean;
  last_fetched: string | null;
};

export type BookDetail = {
  id: number;
  title: string;
  current_offset: number;
  total_chars: number;
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

// Epic 22: a Front chip. 'dict' = clicked in from a dictionary headword, 'manual' =
// typed via the "Add entry" form. The lemma itself isn't in this list — it's always
// entry 0, carried by `Term.lemma`/`TermSummary.lemma`.
export type FormEntry = { text: string; kind: "dict" | "manual" };

// Epic 22: a Back chip. `group` is '' for the lemma's own group, or a FormEntry's
// `text` for a form's group — or, on a hanja term (Epic 26), the hanja spelling of
// the sense it belongs to. `korean_def` (kind "dict" only) is the krdict Korean
// definition (+ any glued-on example) — feeds the Anki Examples field, never shown
// on Back itself.
export type BackItem = {
  group: string;
  kind: "dict" | "translate" | "manual";
  text: string;
  korean_def: string;
};

export type TermSummary = {
  id: number;
  lemma: string;
  translation: string;
  notes: string;
  status: TermStatus;
  deck: string;
  forms: FormEntry[];
  examples: string[];
  back_items: BackItem[];
  hanja: string[];
};

export type Term = {
  id: number;
  lemma: string;
  translation: string;
  notes: string;
  status: TermStatus;
  deck: string;
  sentence: string;
  forms: FormEntry[];
  examples: string[];
  back_items: BackItem[];
  anki_note_id: number | null;
  anki_dirty: boolean;
  created: string;
  updated: string;
  hanja: string[];
};

// Epic 24: a character-addressed slice of a book, which the reader paginates itself
// with CSS columns. `offset` is where `content` starts in the whole book (the server
// snaps it back to a sentence boundary, so it may precede what was requested); token
// offsets are relative to `content`, so absolute position = offset + token.s.
export type TextWindow = {
  offset: number;
  total_chars: number;
  content: string;
  tokens: Token[];
  terms: Record<string, TermSummary>;
};

export type DictEntry = {
  word: string;
  pos: string;
  origin: string;
  target_code: string;
  definitions: { ko: string; en_word: string; en_def: string }[];
  examples: string[];
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
  candidate_retention_days: number;
  hanja_deck: string;
  // System-managed (stamped by POST /api/feeds/fetch) — read-only in the UI, see
  // SettingsPut on the backend, which deliberately has no field for this.
  last_fetch_attempt: string | null;
};

// `read` = how many books were read that day (Epic 24 — was a page count, which
// stopped being comparable once each device paginates for its own screen).
export type StatsActivity = { date: string; words: number; read: number };

export type StatsBookRow = {
  book_id: number;
  title: string;
  new_words: number;
  days_read: number;
};

export type CurationCounts = {
  promoted: number;
  user_discarded: number;
  expired: number;
  pending: number;
};

export type CurationByTopic = CurationCounts & { topic: string };
export type CurationByFeed = CurationCounts & { feed_id: number; feed_name: string };

export type Stats = {
  totals: {
    words_learning: number;
    words_known: number;
    words_total: number;
    books_finished: number;
    words_week: number;
    days_read_week: number;
  };
  streak: { current: number; longest: number };
  activity: StatsActivity[];
  new_words_per_book: StatsBookRow[];
  vocab_depth: {
    buckets: { A: number; B: number; C: number; unlisted: number };
    beginner_pct: number | null;
    total_a: number;
  };
  curation: {
    by_topic: CurationByTopic[];
    by_feed: CurationByFeed[];
  };
};

class ApiError extends Error {}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      if (Array.isArray(body.detail)) {
        // FastAPI/pydantic 422: a list of {loc, msg, ...} — stringify would
        // otherwise collapse this to "[object Object],[object Object],...".
        message = body.detail
          .map((d: { loc?: (string | number)[]; msg?: string }) =>
            d.msg ? `${(d.loc ?? []).join(".")}: ${d.msg}` : JSON.stringify(d)
          )
          .join("; ");
      } else {
        message = body.error ?? body.detail ?? message;
      }
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
    sort?: BookSort;
    limit?: number;
    offset?: number;
  }) => {
    const sp = new URLSearchParams();
    if (params?.topic) sp.set("topic", params.topic);
    if (params?.archived !== undefined) sp.set("archived", String(params.archived));
    if (params?.source) sp.set("source", params.source);
    if (params?.status) sp.set("status", params.status);
    if (params?.sort) sp.set("sort", params.sort);
    if (params?.limit !== undefined) sp.set("limit", String(params.limit));
    if (params?.offset !== undefined) sp.set("offset", String(params.offset));
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
      current_offset?: number;
      title?: string;
      topic?: string;
      tags?: string[];
      archived?: boolean;
      read?: boolean;
      status?: BookStatus;
    }
  ) => request<Book>(`/books/${id}`, { method: "PATCH", body: JSON.stringify(body) }),

  getText: (bookId: number, offset: number) =>
    request<TextWindow>(`/books/${bookId}/text?offset=${Math.max(0, Math.floor(offset))}`),

  createTerm: (body: {
    lemma: string;
    translation: string;
    status?: TermStatus;
    deck?: string;
    sentence?: string;
    notes?: string;
    forms?: FormEntry[];
    examples?: string[];
    back_items?: BackItem[];
    source_book_id?: number;
    source_page?: number;
    hanja?: string[];
  }) => request<Term>("/terms", { method: "POST", body: JSON.stringify(body) }),

  patchTerm: (
    id: number,
    body: Partial<
      Pick<
        Term,
        | "lemma"
        | "translation"
        | "notes"
        | "status"
        | "deck"
        | "sentence"
        | "forms"
        | "examples"
        | "back_items"
        | "hanja"
      >
    >
  ) => request<Term>(`/terms/${id}`, { method: "PATCH", body: JSON.stringify(body) }),

  deleteTerm: (id: number) => request<void>(`/terms/${id}`, { method: "DELETE" }),

  // Epic 26: exact-lemma lookup — "is this word already saved?", which the LIKE
  // search in listTerms can't answer. null rather than a throw on 404, since "not
  // saved yet" is the ordinary case at the call site.
  termByLemma: async (lemma: string) => {
    try {
      return await request<Term>(`/terms/by-lemma?lemma=${encodeURIComponent(lemma)}`);
    } catch {
      return null;
    }
  },

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

  importEpub: (body: { file: File; title?: string; topic?: string; tags?: string }) => {
    const fd = new FormData();
    fd.set("file", body.file);
    if (body.title) fd.set("title", body.title);
    if (body.topic) fd.set("topic", body.topic);
    if (body.tags) fd.set("tags", body.tags);
    return requestForm<Book>("/import/epub", fd);
  },

  importSubtitles: (body: {
    files: File[];
    title?: string;
    topic?: string;
    tags?: string;
  }) => {
    const fd = new FormData();
    for (const file of body.files) fd.append("files", file);
    if (body.title) fd.set("title", body.title);
    if (body.topic) fd.set("topic", body.topic);
    if (body.tags) fd.set("tags", body.tags);
    return requestForm<SubtitleImportResult>("/import/subtitles", fd);
  },

  fetchFeeds: () => request<FeedFetchResult>("/feeds/fetch", { method: "POST" }),

  listFeeds: () => request<Feed[]>("/feeds"),

  createFeed: (body: {
    name: string;
    type: FeedType;
    url_or_channel_id: string;
    topic?: string;
    enabled?: boolean;
  }) => request<Feed>("/feeds", { method: "POST", body: JSON.stringify(body) }),

  patchFeed: (
    id: number,
    body: Partial<Pick<Feed, "name" | "type" | "url_or_channel_id" | "topic" | "enabled">>
  ) => request<Feed>(`/feeds/${id}`, { method: "PATCH", body: JSON.stringify(body) }),

  deleteFeed: (id: number) => request<void>(`/feeds/${id}`, { method: "DELETE" }),

  getStats: () => request<Stats>("/stats"),

  // Logs "this book was read today" — once per book per day, deduped server-side.
  markRead: (bookId: number) =>
    request<{ counted: boolean }>("/reads", {
      method: "POST",
      body: JSON.stringify({ book_id: bookId }),
    }),
};
