"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { api, type Page as PageData, type Token, type TermSummary } from "@/lib/api";

export default function ReadPage() {
  return (
    <Suspense fallback={<main className="flex-1 px-4 py-6 text-zinc-500">Loading…</main>}>
      <ReadPageContent />
    </Suspense>
  );
}

function ReadPageContent() {
  const searchParams = useSearchParams();
  const idParam = searchParams.get("id");
  const bookId = idParam ? Number(idParam) : null;

  const [page, setPage] = useState<PageData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const loadPage = useCallback((id: number, pageNo: number) => {
    setLoading(true);
    setError(null);
    api
      .getPage(id, pageNo)
      .then(setPage)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load page."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (bookId === null) return;
    api
      .getBook(bookId)
      .then((book) => loadPage(bookId, book.current_page))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load book."));
  }, [bookId, loadPage]);

  const goToPage = (pageNo: number) => {
    if (bookId === null || !page || pageNo < 1 || pageNo > page.page_count) return;
    loadPage(bookId, pageNo);
    api.patchBook(bookId, { current_page: pageNo }).catch(() => {
      // best-effort — navigation shouldn't block on persisting current_page
    });
  };

  return (
    <main className="flex-1 mx-auto w-full max-w-lg px-4 py-6 flex flex-col gap-4">
      <Link href="/" className="text-sm text-zinc-500 self-start">
        ← Books
      </Link>

      {bookId === null && (
        <p className="text-red-600 dark:text-red-400 text-sm">No book selected.</p>
      )}

      {error && <p className="text-red-600 dark:text-red-400 text-sm">{error}</p>}

      {bookId !== null && !page && !error && (
        <p className="text-zinc-500">Loading…</p>
      )}

      {page && (
        <>
          <article className="leading-loose text-lg whitespace-pre-wrap">
            {renderContent(page.content, page.tokens, page.terms)}
          </article>

          <div className="flex items-center justify-between mt-4 pt-4 border-t border-zinc-200 dark:border-zinc-800">
            <button
              onClick={() => goToPage(page.page_no - 1)}
              disabled={page.page_no <= 1 || loading}
              className="px-4 py-2 text-sm rounded-full border border-zinc-300 dark:border-zinc-700 disabled:opacity-40"
            >
              ← Prev
            </button>
            <span className="text-sm text-zinc-500">
              {page.page_no} / {page.page_count}
            </span>
            <button
              onClick={() => goToPage(page.page_no + 1)}
              disabled={page.page_no >= page.page_count || loading}
              className="px-4 py-2 text-sm rounded-full border border-zinc-300 dark:border-zinc-700 disabled:opacity-40"
            >
              Next →
            </button>
          </div>
        </>
      )}
    </main>
  );
}

function renderContent(
  content: string,
  tokens: Token[],
  terms: Record<string, TermSummary>
) {
  const nodes: React.ReactNode[] = [];
  let cursor = 0;

  tokens.forEach((tok, i) => {
    if (tok.s > cursor) nodes.push(content.slice(cursor, tok.s));

    const isLearning = terms[tok.lemma]?.status === "learning";
    nodes.push(
      <span
        key={i}
        className={
          isLearning
            ? "bg-amber-200/70 dark:bg-amber-300/25 rounded-sm"
            : undefined
        }
      >
        {content.slice(tok.s, tok.e)}
      </span>
    );
    cursor = tok.e;
  });

  if (cursor < content.length) nodes.push(content.slice(cursor));

  return nodes;
}
