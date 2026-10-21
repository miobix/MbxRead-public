"use client";

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
import { BackLink } from "@/lib/back-link";
import { useReaderLines } from "@/lib/reader-lines";
import { capSelection, extractSentence } from "@/lib/sentence";
import { ProgressStations } from "./ProgressStations";
import { TokenPopover, type PopoverTarget } from "./TokenPopover";

// Below this, a press-and-release is a tap, not a drag, and there's nothing to
// reconstruct from two points that are the same point.
const DRAG_MIN_PX = 6;

// A page counts as read only after this long on screen, so flicking past doesn't count.
const READ_DWELL_MS = 5000;

// terms.source_page unit: the same 1500 chars as difficulty's new_per_page, which,
// unlike a rendered page, means the same thing on every device.
const READ_BUCKET_CHARS = 1500;
const bucketOf = (offset: number) => Math.floor(offset / READ_BUCKET_CHARS) + 1;

// Reach when paging back off the loaded window; smaller than the server's window so
// the new slice overlaps the current one and contains the target character.
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
  // The tapped token stays marked while its popover is open.
  const [tapped, setTapped] = useState<number | null>(null);
  const [title, setTitle] = useState("");
  const [settings, setSettings] = useState<Settings | null>(null);

  const lines = useReaderLines();
  const [col, setCol] = useState(0);
  const [colCount, setColCount] = useState(1);
  const [colStarts, setColStarts] = useState<number[]>([]);
  const [width, setWidth] = useState(0);
  const [lineHeight, setLineHeight] = useState(0);

  const viewportRef = useRef<HTMLDivElement>(null);
  const articleRef = useRef<HTMLElement>(null);
  // Offset a load must land on; consumed after layout, since the target column is
  // unknown until the browser has laid the text out.
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
      .then((book) => {
        setTitle(book.title);
        loadWindow(bookId, book.current_offset);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load item."));
  }, [bookId, loadWindow]);

  // Measured line-height, not `height: {N}lh`: where `lh` is unsupported it degrades
  // to `height: auto` and column breaking silently stops.
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

  // One DOM pass per layout: column count and each column's start offset, so
  // `position` stays a pure derivation (colStarts[col]) rather than synced state.
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

  // overflow:hidden doesn't stop the browser scrolling during a selection drag, which
  // slides the columns under the cursor. Snap back on every stray scroll.
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
   * The selected text and its start in the content, or null for a plain tap. In the
   * multi-column flow Chrome drags the anchor back to the window's start, so a mouse
   * drag is rebuilt by hit-testing press and release; touch uses the native string.
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
    const index = Number(el.dataset.tokenIndex);
    const token = win.tokens[index];
    if (!token) return;
    setTapped(index);
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
      // Re-key the term by its current lemma + forms so highlights refresh without a
      // refetch; another term's direct lemma wins a collision, as on the server.
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
    <main className="flex-1 mx-auto w-full max-w-lg px-4 py-5 flex flex-col gap-4">
      <div className="flex shrink-0 flex-col gap-3">
        <div className="flex items-center justify-between gap-4">
          <BackLink />
          {title && <span className="min-w-0 truncate text-sm font-medium">{title}</span>}
        </div>
        {win && <ProgressStations percent={percent} />}
      </div>

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
              // Otherwise multicol balances text across columns instead of filling each.
              columnFill: "auto",
            }}
          >
            {renderContent(win.content, win.tokens, win.terms, target ? tapped : null)}
          </article>
        )}
      </div>

      {win && (
        <div className="flex shrink-0 items-center justify-between gap-3 mt-2 pt-4 border-t border-border">
          <button onClick={goPrev} disabled={atStart || loading} className="btn-secondary min-w-24">
            Previous
          </button>
          <button onClick={goNext} disabled={atEnd || loading} className="btn-secondary min-w-24">
            Next
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
          onClose={() => {
            setTarget(null);
            setTapped(null);
          }}
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
  terms: Record<string, TermSummary>,
  tapped: number | null
) {
  const nodes: React.ReactNode[] = [];
  let cursor = 0;

  tokens.forEach((tok, i) => {
    if (tok.s > cursor) nodes.push(content.slice(cursor, tok.s));

    const isLearning = terms[tok.lemma]?.status === "learning";
    // Vertical padding on an inline span paints the full line-box height without
    // moving any text, so the column breaks measured above are unaffected.
    const mark =
      i === tapped
        ? "bg-accent text-accent-ink rounded-[2px] py-0.5"
        : isLearning
          ? "bg-highlight rounded-[2px] py-0.5"
          : undefined;
    nodes.push(
      <span key={i} data-token-index={i} className={mark}>
        {content.slice(tok.s, tok.e)}
      </span>
    );
    cursor = tok.e;
  });

  if (cursor < content.length) nodes.push(content.slice(cursor));

  return nodes;
}

/**
 * Content offset at a viewport point, or null off the text. A visual hit test, so it
 * lands in the visible column; older WebKit/Blink only have `caretRangeFromPoint`.
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
