"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  Suspense,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import {
  api,
  type Settings,
  type Term,
  type TextWindow,
  type Token,
  type TermSummary,
} from "@/lib/api";
import { useReaderLines } from "@/lib/reader-lines";
import { capSelection, extractSentence } from "@/lib/sentence";
import { TokenPopover, type PopoverTarget } from "./TokenPopover";

// Below this, a press-and-release is a tap, not a drag, and there's nothing to
// reconstruct from two points that are the same point.
const DRAG_MIN_PX = 6;

// A page only counts as "read" once it's been visible this long — filters out
// flicking past a page, and (with the server's INSERT OR IGNORE) later pages the
// same day are a silent no-op. See docs/DECISIONS.md.
const READ_DWELL_MS = 5000;

// Term provenance (terms.source_page) still wants a discrete unit. 1500 chars is the
// same unit difficulty's new_per_page uses (server/difficulty.py), and unlike a
// rendered page it means the same thing on a phone and a laptop.
const READ_BUCKET_CHARS = 1500;
const bucketOf = (offset: number) => Math.floor(offset / READ_BUCKET_CHARS) + 1;

// How far back to reach when paging backwards off the front of the loaded window.
// Smaller than the server's window so the fetched slice always overlaps the current
// one, and the character we're paging back to is guaranteed to be inside it.
const BACK_STEP_CHARS = 12_000;

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

  const [win, setWin] = useState<TextWindow | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [target, setTarget] = useState<PopoverTarget | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);

  const lines = useReaderLines();
  const [col, setCol] = useState(0);
  const [colCount, setColCount] = useState(1);
  const [colStarts, setColStarts] = useState<number[]>([]);
  const [width, setWidth] = useState(0);
  const [lineHeight, setLineHeight] = useState(0);

  const viewportRef = useRef<HTMLDivElement>(null);
  const articleRef = useRef<HTMLElement>(null);
  // Set when a load needs to land on a specific character offset, and consumed once
  // the columns have been measured — the target column can't be known until the
  // browser has actually laid the text out.
  const pendingOffset = useRef<number | null>(null);
  // Where a mouse selection started, so the released drag can be turned back into a
  // character range by hit-testing both ends (see readSelection).
  const dragStart = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    api.getSettings().then(setSettings).catch(() => {
      // best-effort — TokenPopover falls back to sane defaults if this never loads
    });
  }, []);

  const loadWindow = useCallback(
    (id: number, offset: number, landOn?: number) => {
      setLoading(true);
      setError(null);
      pendingOffset.current = landOn ?? offset;
      api
        .getText(id, offset)
        .then(setWin)
        .catch((e) => setError(e instanceof Error ? e.message : "Failed to load text."))
        .finally(() => setLoading(false));
    },
    []
  );

  useEffect(() => {
    if (bookId === null) return;
    api
      .getBook(bookId)
      .then((book) => loadWindow(bookId, book.current_offset))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load item."));
  }, [bookId, loadWindow]);

  // The viewport's width is the column width — one column exactly fills the screen.
  // Its line-height gives the page height in real pixels: `height: {N}lh` would say
  // the same thing more elegantly, but `lh` needs Chrome 109+/Safari 16.4+ and
  // silently degrades to `height: auto` when unsupported — which drops the column
  // breaking entirely. Measuring is exact everywhere.
  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    const measure = () => {
      setWidth(el.clientWidth);
      const lh = Number.parseFloat(window.getComputedStyle(el).lineHeight);
      if (Number.isFinite(lh) && lh > 0) setLineHeight(lh);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // One DOM pass per layout produces everything position-related: how many columns
  // the browser made, and the absolute character offset each one starts at. Reading
  // it here rather than per-navigation keeps `position` a pure derivation during
  // render (colStarts[col]) instead of state that has to be synced in an effect.
  useLayoutEffect(() => {
    const article = articleRef.current;
    if (!article || !win || width <= 0) return;

    const count = Math.max(1, Math.round(article.scrollWidth / width));
    const starts: number[] = [];
    for (const span of article.querySelectorAll<HTMLElement>("[data-token-index]")) {
      const c = Math.round(span.offsetLeft / width);
      if (starts[c] === undefined) {
        const tok = win.tokens[Number(span.dataset.tokenIndex)];
        if (tok) starts[c] = win.offset + tok.s;
      }
    }
    // A column can hold no tokens at all (a run of blank lines), leaving a hole —
    // carry the previous column's offset forward so every index has a position.
    let carried = win.offset;
    for (let c = 0; c < count; c++) {
      if (starts[c] === undefined) starts[c] = carried;
      else carried = starts[c];
    }

    setColCount(count);
    setColStarts(starts);

    const target = pendingOffset.current;
    if (target !== null) {
      pendingOffset.current = null;
      let landing = 0;
      for (let c = 0; c < count; c++) if (starts[c] <= target) landing = c;
      setCol(landing);
    } else {
      setCol((c) => Math.min(c, count - 1));
    }
    // lineHeight is a dependency because it sets the page height, and the page
    // height is what decides where the browser breaks each column.
  }, [win, width, lines, lineHeight]);

  useEffect(() => {
    const el = viewportRef.current;
    if (el && width > 0) el.scrollLeft = col * width;
  }, [col, width, win]);

  // Nothing but the line above is allowed to scroll the viewport. It's overflow:hidden,
  // but that only stops the *user* scrolling it: while a selection drag is in progress
  // the browser still scrolls it to keep the selection's edge in view, which slides the
  // columns sideways under the cursor mid-drag — the jitter. Snapping back on every
  // stray scroll pins the page. (Assigning scrollLeft re-fires `scroll`, but by then
  // it already equals `want`, so this settles immediately.)
  useEffect(() => {
    const el = viewportRef.current;
    if (!el || width <= 0) return;
    const pin = () => {
      const want = col * width;
      if (el.scrollLeft !== want) el.scrollLeft = want;
    };
    el.addEventListener("scroll", pin);
    return () => el.removeEventListener("scroll", pin);
  }, [col, width]);

  // Pure derivation — no effect, no synced state. Falls back to the window's own
  // start before the first measurement has landed.
  const position = colStarts[col] ?? win?.offset ?? 0;

  // Persist position, and log a genuine read once the current column has stayed
  // visible for the dwell window. Re-runs per column; pauses while the tab is hidden.
  useEffect(() => {
    if (bookId === null || !win || width <= 0) return;
    const absolute = position;

    const save = setTimeout(() => {
      api.patchBook(bookId, { current_offset: absolute }).catch(() => {
        // best-effort — navigation shouldn't block on persisting position
      });
    }, 500);

    let timer: ReturnType<typeof setTimeout> | null = null;
    let logged = false;
    const start = () => {
      if (logged || timer) return;
      timer = setTimeout(() => {
        logged = true;
        api.markRead(bookId).catch(() => {
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
      clearTimeout(save);
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [bookId, win, width, position]);

  const atStart = !!win && win.offset === 0 && col === 0;
  const atEnd =
    !!win && col >= colCount - 1 && win.offset + win.content.length >= win.total_chars;

  const goNext = () => {
    if (!win || bookId === null) return;
    if (col < colCount - 1) {
      setCol(col + 1);
      return;
    }
    const end = win.offset + win.content.length;
    if (end < win.total_chars) loadWindow(bookId, end);
  };

  const goPrev = () => {
    if (!win || bookId === null) return;
    if (col > 0) {
      setCol(col - 1);
      return;
    }
    if (win.offset > 0) {
      loadWindow(bookId, Math.max(0, win.offset - BACK_STEP_CHARS), win.offset - 1);
    }
  };

  /**
   * What the user actually selected, as text plus where it starts in the content —
   * or null when this was a plain tap.
   *
   * The article is one multi-column flow that's horizontally scrolled to the current
   * column, and dragging inside it makes Chrome pull the selection's anchor back to
   * the start of the flow: `getSelection()` then returns everything from the top of
   * the loaded window down to the phrase. So when a real drag happened, rebuild the
   * range by hit-testing the press and release points instead. Touch selection
   * (long-press, then tap to open) has no drag to rebuild from and falls back to the
   * native string. Either way the result is capped to the last two sentences.
   */
  const readSelection = (e: React.MouseEvent<HTMLElement>) => {
    const down = dragStart.current;
    dragStart.current = null;
    if (!win) return null;

    // The browser deciding there's no selection is still authoritative — that's what
    // keeps a tap on a word a tap on a word.
    const native = window.getSelection()?.toString().trim();
    if (!native) return null;

    const article = articleRef.current;
    const dragged =
      down && Math.hypot(e.clientX - down.x, e.clientY - down.y) >= DRAG_MIN_PX;
    if (article && dragged) {
      const a = caretIndexAt(article, down.x, down.y);
      const b = caretIndexAt(article, e.clientX, e.clientY);
      if (a !== null && b !== null && a !== b) {
        const from = Math.min(a, b);
        const text = capSelection(win.content.slice(from, Math.max(a, b)));
        if (text) return { text, index: Math.max(win.content.indexOf(text, from), 0) };
      }
    }

    const text = capSelection(native);
    if (!text) return null;
    return { text, index: Math.max(win.content.indexOf(text), 0) };
  };

  const handleArticleClick = (e: React.MouseEvent<HTMLElement>) => {
    if (!win) return;

    const picked = readSelection(e);
    if (picked) {
      const selectionText = picked.text;
      window.getSelection()?.removeAllRanges();
      const sentence = extractSentence(win.content, picked.index);

      // A multi-word selection is a phrase — the popover shows a translate-only UI
      // (no dictionary/forms/examples), per the words-vs-phrases distinction.
      const isPhrase = /\s/.test(selectionText);

      const known = win.terms[selectionText] ?? null;
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
      // in the window's terms even when saved — fall back to an exact-match search.
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
                  hanja: exact.hanja,
                }
              : null,
          });
        });
      return;
    }

    const el = (e.target as HTMLElement).closest<HTMLElement>("[data-token-index]");
    if (!el) return;
    const token = win.tokens[Number(el.dataset.tokenIndex)];
    if (!token) return;
    setTarget({
      surface: token.surface,
      lemma: token.lemma,
      sentence: extractSentence(win.content, token.s),
      existing: win.terms[token.lemma] ?? null,
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
      hanja: term.hanja,
    };
    setWin((prev) => {
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
    setWin((prev) => {
      if (!prev) return prev;
      const nextTerms = { ...prev.terms };
      for (const key of Object.keys(nextTerms)) {
        if (nextTerms[key].id === term.id) delete nextTerms[key];
      }
      return { ...prev, terms: nextTerms };
    });
  };

  const percent =
    win && win.total_chars > 0
      ? Math.min(100, Math.round((position / win.total_chars) * 100))
      : 0;

  return (
    <main className="flex-1 mx-auto w-full max-w-lg px-4 py-6 flex flex-col gap-4">
      <Link href="/" className="text-sm text-muted hover:text-ink transition-colors self-start">
        ← Library
      </Link>

      {bookId === null && (
        <p className="text-danger text-sm">No item selected.</p>
      )}

      {error && <p className="text-danger text-sm">{error}</p>}

      {bookId !== null && !win && !error && (
        <p className="text-muted">Loading…</p>
      )}

      {/* Always mounted, and always exactly N lines tall, so the divider and the
          nav buttons below never move — not while a window loads, and not when a
          phone's address bar slides away and changes the available height.
          `shrink-0` matters: <body> and <main> are both flex columns, so without it
          this box is a shrinkable flex item and gets squeezed whenever vertical
          space is tight, which is what made the buttons jump on mobile.
          The article inside is the multi-column container: a fixed height of N line
          boxes plus a column width of exactly one screen means the browser breaks a
          column every N *rendered* lines — no estimate, correct on any device. */}
      <div
        ref={viewportRef}
        className="overflow-hidden w-full shrink-0 leading-loose text-lg"
        style={{ height: lineHeight > 0 ? lines * lineHeight : undefined }}
      >
        {win && (
          <article
            ref={articleRef}
            onMouseDown={(e) => {
              dragStart.current = { x: e.clientX, y: e.clientY };
            }}
            onClick={handleArticleClick}
            className="leading-loose text-lg whitespace-pre-wrap select-text [word-break:keep-all] [overflow-wrap:break-word]"
            style={{
              height: "100%",
              columnWidth: width > 0 ? `${width}px` : undefined,
              columnGap: 0,
              // Without this, multicol *balances* content across columns inside the
              // fixed height instead of filling each one — which would defeat the
              // whole point of a fixed line count per page.
              columnFill: "auto",
            }}
          >
            {renderContent(win.content, win.tokens, win.terms)}
          </article>
        )}
      </div>

      {win && (
        <div className="flex shrink-0 items-center justify-between mt-4 pt-4 border-t border-border">
          <button
            onClick={goPrev}
            disabled={atStart || loading}
            className="px-4 py-2 text-sm rounded-full border border-border hover:border-accent transition-colors disabled:opacity-40"
          >
            ← Prev
          </button>
          {/* Percentage rather than "7 / 150": page numbers are per-device now (a
              phone fits fewer lines' worth of text than a laptop), but a percentage
              derives from the character offset, so it reads the same on both. */}
          <span className="text-sm text-muted">{percent}%</span>
          <button
            onClick={goNext}
            disabled={atEnd || loading}
            className="px-4 py-2 text-sm rounded-full border border-border hover:border-accent transition-colors disabled:opacity-40"
          >
            Next →
          </button>
        </div>
      )}

      {target && (
        <TokenPopover
          target={target}
          bookId={bookId}
          pageNo={bucketOf(position)}
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

/**
 * Character offset into the window's content at a viewport point, or null if the
 * point isn't over the article's text.
 *
 * `caretPositionFromPoint` is a *visual* hit test, so unlike the browser's own
 * drag-to-extend logic it lands in the column the user is actually looking at.
 * Firefox/Chrome ≥128 have the standard method; older WebKit/Blink only have the
 * deprecated `caretRangeFromPoint`.
 */
function caretIndexAt(article: HTMLElement, x: number, y: number): number | null {
  let node: Node | null = null;
  let offset = 0;

  if (typeof document.caretPositionFromPoint === "function") {
    const pos = document.caretPositionFromPoint(x, y);
    if (!pos) return null;
    node = pos.offsetNode;
    offset = pos.offset;
  } else if (typeof document.caretRangeFromPoint === "function") {
    const range = document.caretRangeFromPoint(x, y);
    if (!range) return null;
    node = range.startContainer;
    offset = range.startOffset;
  }

  if (!node || node.nodeType !== Node.TEXT_NODE || !article.contains(node)) return null;

  // renderContent emits the content's text nodes in order and covers every
  // character exactly once, so summing their lengths up to `node` is the offset.
  const walker = document.createTreeWalker(article, NodeFilter.SHOW_TEXT);
  let total = 0;
  while (walker.nextNode()) {
    if (walker.currentNode === node) return total + offset;
    total += walker.currentNode.textContent?.length ?? 0;
  }
  return null;
}
