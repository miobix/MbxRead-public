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

export type TermSummary = {
  id: number;
  translation: string;
  status: "learning" | "known" | "ignored";
  deck: string;
};

export type Page = {
  page_no: number;
  page_count: number;
  content: string;
  tokens: Token[];
  terms: Record<string, TermSummary>;
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
};
