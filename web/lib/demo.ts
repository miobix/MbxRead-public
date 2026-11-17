// The GitHub Pages demo's stand-in for the API: recorded responses from the real app
// (scripts/build_demo_data.py) plus the visitor's own terms, kept in their browser.
import type { Book, Settings, Term, TermSummary, TextWindow } from "./api";

export const IS_DEMO = process.env.NEXT_PUBLIC_DEMO === "1";

type Recorded = {
  generated: string;
  credits: Record<string, string>;
  seeded_usage_lemmas: string[];
  books: Book[];
  details: Record<string, unknown>;
  texts: Record<string, Omit<TextWindow, "terms">>;
  settings: Settings;
  stats: unknown;
  translations: Record<string, unknown>;
  dictionary: Record<string, unknown>;
  usage: Record<string, { usage: unknown; explain: unknown }>;
};

type Store = {
  terms: Term[];
  nextId: number;
  books: Record<string, Partial<Book>>;
  settings: Partial<Settings>;
};

const STORE_KEY = "mbxread-demo";
let recorded: Promise<Recorded> | null = null;
let memory: Store | null = null;

function load(): Promise<Recorded> {
  recorded ??= import("./demo-data.json").then((m) => m.default as unknown as Recorded);
  return recorded;
}

function store(): Store {
  if (!memory) {
    try {
      memory = JSON.parse(window.localStorage.getItem(STORE_KEY) ?? "null");
    } catch {
      memory = null;
    }
    memory ??= { terms: [], nextId: 1, books: {}, settings: {} };
  }
  return memory;
}

function save() {
  try {
    window.localStorage.setItem(STORE_KEY, JSON.stringify(store()));
  } catch {
    // private window or blocked storage: the demo still works for this visit
  }
}

export function resetDemo() {
  memory = { terms: [], nextId: 1, books: {}, settings: {} };
  save();
}

export async function demoCredits(): Promise<string[]> {
  return Object.values((await load()).credits);
}

export async function demoSeededLemmas(): Promise<string[]> {
  return (await load()).seeded_usage_lemmas;
}

class DemoError extends Error {}

const notInDemo = (what: string) => new DemoError(`${what} isn't available in the demo.`);

function summary(t: Term): TermSummary {
  const { id, lemma, translation, notes, status, deck, forms, examples, back_items } = t;
  return { id, lemma, translation, notes, status, deck, forms, examples, back_items };
}

function termsFor(lemmas: Set<string>): Record<string, TermSummary> {
  const out: Record<string, TermSummary> = {};
  for (const t of store().terms) if (lemmas.has(t.lemma)) out[t.lemma] = summary(t);
  for (const t of store().terms)
    for (const f of t.forms) if (lemmas.has(f.text) && !out[f.text]) out[f.text] = summary(t);
  return out;
}

type TermBody = Partial<Term>;

function applyTermBody(t: Term, body: TermBody) {
  Object.assign(t, body);
  t.lemma = t.lemma.trim();
  const seen = new Set([t.lemma]);
  t.forms = (t.forms ?? []).filter((f) => {
    const text = f.text.trim();
    if (!text || seen.has(text)) return false;
    seen.add(text);
    return true;
  });
  if (body.back_items) t.translation = body.back_items.map((b) => b.text).join("; ");
  t.updated = new Date().toISOString();
}

function lemmaTaken(lemma: string, exceptId?: number) {
  return store().terms.some((t) => t.lemma === lemma.trim() && t.id !== exceptId);
}

export async function demoRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const data = await load();
  const method = (init?.method ?? "GET").toUpperCase();
  const url = new URL(path, "http://demo");
  const q = url.searchParams;
  const parts = url.pathname.split("/").filter(Boolean);
  const body = init?.body && typeof init.body === "string" ? JSON.parse(init.body) : {};
  const s = store();
  const book = (id: string) => ({ ...data.books.find((b) => String(b.id) === id)!, ...s.books[id] });
  const ok = (v: unknown) => v as T;

  switch (parts[0]) {
    case "books": {
      const id = parts[1];
      if (!id && method === "GET") {
        const status = q.get("status") ?? "library";
        return ok(data.books.filter((b) => b.status === status).map((b) => book(String(b.id))));
      }
      if (id && !parts[2] && method === "GET") return ok({ ...data.details[id] as object, ...pick(s.books[id]) });
      if (id && parts[2] === "text") {
        const w = data.texts[id];
        return ok({ ...w, terms: termsFor(new Set(w.tokens.map((t) => t.lemma))) });
      }
      if (id && !parts[2] && method === "PATCH") {
        s.books[id] = { ...s.books[id], ...body };
        save();
        return ok(book(id));
      }
      if (id && parts[2] === "score") return ok(book(id));
      break;
    }
    case "reads":
      return ok({ counted: true });
    case "terms": {
      const id = Number(parts[1]);
      if (parts[1] === "by-lemma") {
        const t = s.terms.find((x) => x.lemma === (q.get("lemma") ?? "").trim());
        if (!t) throw new DemoError("term not found");
        return ok(t);
      }
      if (!parts[1] && method === "GET") {
        const needle = (q.get("q") ?? "").trim();
        return ok(
          s.terms
            .filter((t) => !q.get("status") || t.status === q.get("status"))
            .filter((t) => !q.get("deck") || t.deck === q.get("deck"))
            .filter((t) => !needle || t.lemma.includes(needle) || t.translation.includes(needle))
            .slice()
            .reverse()
        );
      }
      if (!parts[1] && method === "POST") {
        if (lemmaTaken(body.lemma ?? "")) throw new DemoError("a term with this lemma already exists");
        const now = new Date().toISOString();
        const t: Term = {
          id: s.nextId++, lemma: "", translation: "", notes: "", status: "learning", deck: "",
          sentence: "", forms: [], examples: [], back_items: [], anki_note_id: null,
          anki_dirty: false, created: now, updated: now,
        };
        applyTermBody(t, body);
        s.terms.push(t);
        save();
        return ok(t);
      }
      const t = s.terms.find((x) => x.id === id);
      if (!t) throw new DemoError("term not found");
      if (method === "PATCH") {
        if (body.lemma !== undefined && lemmaTaken(body.lemma, id))
          throw new DemoError("a term with this lemma already exists");
        applyTermBody(t, body);
        save();
        return ok(t);
      }
      if (method === "DELETE") {
        s.terms = s.terms.filter((x) => x.id !== id);
        save();
        return ok(undefined);
      }
      break;
    }
    case "translate": {
      const hit = data.translations[(body.text ?? "").trim()];
      if (!hit) throw new DemoError("The demo only has translations for words in the sample texts.");
      return ok(hit);
    }
    case "dict": {
      const hit = data.dictionary[(q.get("word") ?? "").trim()];
      if (!hit) throw new DemoError("No dictionary entry was recorded for this word in the demo.");
      return ok(hit);
    }
    case "usage": {
      const hit = data.usage[`${body.lemma}|${body.sentence}`];
      if (!hit) {
        throw new DemoError(
          `Similar usage isn't live in the demo. Seeded words: ${data.seeded_usage_lemmas.join(", ")}.`
        );
      }
      return ok(parts[1] === "explain" ? hit.explain : hit.usage);
    }
    case "settings":
      if (method === "PUT") {
        s.settings = { ...s.settings, ...body };
        save();
      }
      return ok({ ...data.settings, ...s.settings });
    case "stats":
      return ok(data.stats);
    case "feeds":
      if (method === "GET" && !parts[1]) return ok([]);
      throw notInDemo("Feeds");
    case "import":
      throw notInDemo("Importing");
    case "anki":
      throw notInDemo("Anki sync");
    case "score":
      throw notInDemo("Scoring new text");
  }
  throw notInDemo("This action");
}

function pick(b?: Partial<Book>) {
  return b?.current_offset === undefined ? {} : { current_offset: b.current_offset };
}
