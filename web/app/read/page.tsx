"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import {
  api,
  type Page as PageData,
  type Settings,
  type Term,
  type Token,
  type TermSummary,
} from "@/lib/api";
import { extractSentence } from "@/lib/sentence";
import { TokenPopover, type PopoverTarget } from "./TokenPopover";

// A page only counts as "read" once it's been visible this long — filters out
// flicking past a page, and (with the server's INSERT OR IGNORE) revisits never
// double-count. See docs/DECISIONS.md.
const READ_DWELL_MS = 5000;

export default function ReadPage() {
  return (
    <Suspense fallback={<main className="flex-1 px-4 py-6 text-muted">Loading…</main>}>
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
  const [target, setTarget] = useState<PopoverTarget | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);

  useEffect(() => {
    api.getSettings().then(setSettings).catch(() => {
      // best-effort — TokenPopover falls back to sane defaults if this never loads
    });
  }, []);

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
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load item."));
  }, [bookId, loadPage]);

  // Log a genuine read once the current page has stayed visible for the dwell
  // window. Re-runs per page; pauses while the tab is hidden.
  useEffect(() => {
    if (bookId === null || !page) return;
    const pageNo = page.page_no;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let logged = false;

    const start = () => {
      if (logged || timer) return;
      timer = setTimeout(() => {
        logged = true;
        api.markPageRead(bookId, pageNo).catch(() => {
          // best-effort — a missed read-log ping shouldn't disrupt reading
        });
      }, READ_DWELL_MS);
    };
    const stop = () => {
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
    };
    const onVisibility = () => (document.hidden ? stop() : start());

    if (!document.hidden) start();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [bookId, page]);

  const goToPage = (pageNo: number) => {
    if (bookId === null || !page || pageNo < 1 || pageNo > page.page_count) return;
    loadPage(bookId, pageNo);
    api.patchBook(bookId, { current_page: pageNo }).catch(() => {
      // best-effort — navigation shouldn't block on persisting current_page
    });
  };

  const handleArticleClick = (e: React.MouseEvent<HTMLElement>) => {
    if (!page) return;

    const selectionText = window.getSelection()?.toString().trim();
    if (selectionText) {
      window.getSelection()?.removeAllRanges();
      const centerIndex = Math.max(page.content.indexOf(selectionText), 0);
      const sentence = extractSentence(page.content, centerIndex);

      // A multi-word selection is a phrase — the popover shows a translate-only UI
      // (no dictionary/forms/examples), per the words-vs-phrases distinction.
      const isPhrase = /\s/.test(selectionText);

      const known = page.terms[selectionText] ?? null;
      if (known) {
        setTarget({
          surface: selectionText,
          lemma: selectionText,
          sentence,
          existing: known,
          isPhrase,
        });
        return;
      }

      // Multi-word phrase lemmas never match a tokenizer lemma, so they never show up
      // in page.terms even when saved — fall back to an exact-match terms search.
      api
        .listTerms({ q: selectionText })
        .then((matches) => matches.find((t) => t.lemma === selectionText) ?? null)
        .catch(() => null)
        .then((exact) => {
          setTarget({
            surface: selectionText,
            lemma: selectionText,
            sentence,
            isPhrase,
            existing: exact
              ? {
                  id: exact.id,
                  lemma: exact.lemma,
                  translation: exact.translation,
                  notes: exact.notes,
                  status: exact.status,
                  deck: exact.deck,
                  forms: exact.forms,
                  examples: exact.examples,
                  back_items: exact.back_items,
                }
              : null,
          });
        });
      return;
    }

    const el = (e.target as HTMLElement).closest<HTMLElement>("[data-token-index]");
    if (!el) return;
    const token = page.tokens[Number(el.dataset.tokenIndex)];
    if (!token) return;
    setTarget({
      surface: token.surface,
      lemma: token.lemma,
      sentence: extractSentence(page.content, token.s),
      existing: page.terms[token.lemma] ?? null,
      isPhrase: false,
    });
  };

  const handleSaved = (term: Term) => {
    const summary: TermSummary = {
      id: term.id,
      lemma: term.lemma,
      translation: term.translation,
      notes: term.notes,
      status: term.status,
      deck: term.deck,
      forms: term.forms,
      examples: term.examples,
      back_items: term.back_items,
    };
    setPage((prev) => {
      if (!prev) return prev;
      const nextTerms = { ...prev.terms };
      // Drop every key this term currently occupies (its old lemma and any removed
      // forms), then re-key it by its current lemma + forms so highlights refresh
      // without a refetch. A form that collides with another term's lemma keeps the
      // direct lemma (matching the server's precedence).
      for (const key of Object.keys(nextTerms)) {
        if (nextTerms[key].id === term.id) delete nextTerms[key];
      }
      nextTerms[term.lemma] = summary;
      for (const f of term.forms) if (!(f.text in nextTerms)) nextTerms[f.text] = summary;
      return { ...prev, terms: nextTerms };
    });
  };

  const handleDeleted = (term: TermSummary) => {
    setPage((prev) => {
      if (!prev) return prev;
      const nextTerms = { ...prev.terms };
      for (const key of Object.keys(nextTerms)) {
        if (nextTerms[key].id === term.id) delete nextTerms[key];
      }
      return { ...prev, terms: nextTerms };
    });
  };

  return (
    <main className="flex-1 mx-auto w-full max-w-lg px-4 py-6 flex flex-col gap-4">
      <Link href="/" className="text-sm text-muted hover:text-ink transition-colors self-start">
        ← Library
      </Link>

      {bookId === null && (
        <p className="text-danger text-sm">No item selected.</p>
      )}

      {error && <p className="text-danger text-sm">{error}</p>}

      {bookId !== null && !page && !error && (
        <p className="text-muted">Loading…</p>
      )}

      {page && (
        <>
          <article
            className="leading-loose text-lg whitespace-pre-wrap select-text"
            onClick={handleArticleClick}
          >
            {renderContent(page.content, page.tokens, page.terms)}
          </article>

          <div className="flex items-center justify-between mt-4 pt-4 border-t border-border">
            <button
              onClick={() => goToPage(page.page_no - 1)}
              disabled={page.page_no <= 1 || loading}
              className="px-4 py-2 text-sm rounded-full border border-border hover:border-accent transition-colors disabled:opacity-40"
            >
              ← Prev
            </button>
            <span className="text-sm text-muted">
              {page.page_no} / {page.page_count}
            </span>
            <button
              onClick={() => goToPage(page.page_no + 1)}
              disabled={page.page_no >= page.page_count || loading}
              className="px-4 py-2 text-sm rounded-full border border-border hover:border-accent transition-colors disabled:opacity-40"
            >
              Next →
            </button>
          </div>
        </>
      )}

      {target && (
        <TokenPopover
          target={target}
          bookId={bookId}
          pageNo={page?.page_no ?? null}
          decks={settings?.decks ?? ["Korean"]}
          defaultDeck={settings?.default_deck ?? "Korean"}
          translatorBackend={settings?.translator_backend}
          onClose={() => setTarget(null)}
          onSaved={handleSaved}
          onDeleted={handleDeleted}
        />
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
        data-token-index={i}
        className={isLearning ? "bg-highlight/70 rounded-sm" : undefined}
      >
        {content.slice(tok.s, tok.e)}
      </span>
    );
    cursor = tok.e;
  });

  if (cursor < content.length) nodes.push(content.slice(cursor));

  return nodes;
}
