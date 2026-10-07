import { useState } from "react";
import { api, type Book, type ScoreResult, type SubtitleImportResult } from "@/lib/api";
import { coverageClass } from "@/lib/score-display";
import { Field, FilePicker, Sheet, TopicPicker } from "@/lib/sheet";

type Mode = "paste" | "youtube" | "pdf" | "epub" | "subs" | "article";

const MODES: { key: Mode; label: string }[] = [
  { key: "paste", label: "Paste text" },
  { key: "article", label: "Article" },
  { key: "youtube", label: "YouTube" },
  { key: "pdf", label: "PDF" },
  { key: "epub", label: "EPUB" },
  { key: "subs", label: "Subtitles" },
];

const splitTags = (tags: string) =>
  tags
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);

export function AddBookSheet({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [mode, setMode] = useState<Mode>("paste");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [source, setSource] = useState<"paste" | "txt">("paste");
  const [txtFile, setTxtFile] = useState<File[]>([]);
  const [url, setUrl] = useState("");
  const [pdfFile, setPdfFile] = useState<File[]>([]);
  const [pdfPages, setPdfPages] = useState("");
  const [epubFile, setEpubFile] = useState<File[]>([]);
  const [subsFiles, setSubsFiles] = useState<File[]>([]);
  const [subsResult, setSubsResult] = useState<SubtitleImportResult | null>(null);
  const [topic, setTopic] = useState("");
  const [tags, setTags] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<ScoreResult | null>(null);
  const [checking, setChecking] = useState(false);

  const handleTxtFile = async (files: File[]) => {
    setTxtFile(files);
    const file = files[0];
    if (!file) return;
    setText(await file.text());
    setSource("txt");
    setPreview(null);
    if (!title.trim()) setTitle(file.name.replace(/\.txt$/i, ""));
  };

  const checkDifficulty = async () => {
    if (!text.trim()) return;
    setChecking(true);
    setError(null);
    try {
      setPreview(await api.scoreText(text));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to score text.");
    } finally {
      setChecking(false);
    }
  };

  const run = async (work: () => Promise<void>) => {
    setSubmitting(true);
    try {
      await work();
      onCreated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed.");
      setSubmitting(false);
    }
  };

  const submit = async () => {
    setError(null);
    const tagList = splitTags(tags);

    if (mode === "paste") {
      if (!title.trim() || !text.trim()) {
        setError("Add a title and some text.");
        return;
      }
      return run(() =>
        api.createBook({ title: title.trim(), text, source, topic, tags: tagList }).then(() => {})
      );
    }

    if (mode === "youtube" || mode === "article") {
      if (!url.trim()) {
        setError("Paste a link first.");
        return;
      }
      const body = { url: url.trim(), topic, tags: tagList };
      return run(() =>
        (mode === "youtube" ? api.importYoutube(body) : api.importArticle(body)).then(() => {})
      );
    }

    if (mode === "subs") {
      if (subsFiles.length === 0) {
        setError("Choose one or more subtitle files first.");
        return;
      }
      setSubmitting(true);
      setSubsResult(null);
      try {
        const result = await api.importSubtitles({
          files: subsFiles,
          title: title.trim(),
          topic,
          tags,
        });
        // Re-dropping a season is mostly duplicates, so a batch that wasn't
        // perfectly clean reports per file instead of closing on a partial result.
        if (result.skipped.length === 0 && result.failed.length === 0) {
          onCreated();
          return;
        }
        setSubsResult(result);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Import failed.");
      }
      setSubmitting(false);
      return;
    }

    if (mode === "epub") {
      if (!epubFile[0]) {
        setError("Choose an EPUB file first.");
        return;
      }
      return run(() =>
        api.importEpub({ file: epubFile[0], title: title.trim(), topic, tags }).then(() => {})
      );
    }

    if (!pdfFile[0]) {
      setError("Choose a PDF file first.");
      return;
    }
    return run(() =>
      api
        .importPdf({ file: pdfFile[0], title: title.trim(), topic, tags, pages: pdfPages.trim() })
        .then(() => {})
    );
  };

  return (
    <Sheet
      title="Add to Library"
      onClose={onClose}
      footer={
        <>
          <button
            // A partial subtitle batch leaves the sheet open on its summary, so
            // closing still has to refresh the Library for whatever did import.
            onClick={subsResult?.imported.length ? onCreated : onClose}
            className="btn-secondary flex-1"
          >
            {subsResult ? "Close" : "Cancel"}
          </button>
          <button onClick={submit} disabled={submitting} className="btn-primary flex-1">
            {submitting ? "Adding…" : "Add"}
          </button>
        </>
      }
    >
      <div className="grid grid-cols-3 gap-1 rounded bg-paper p-1 text-sm" role="tablist">
        {MODES.map((m) => (
          <button
            key={m.key}
            role="tab"
            aria-selected={mode === m.key}
            onClick={() => {
              setMode(m.key);
              setError(null);
            }}
            className={`rounded px-2 py-2 transition-colors ${
              mode === m.key ? "bg-surface text-ink font-semibold" : "text-muted hover:text-ink"
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      {subsResult && (
        <div className="rounded border border-border bg-paper p-3 text-sm flex flex-col gap-1">
          <p className="font-medium">
            Imported {subsResult.imported.length} of{" "}
            {subsResult.imported.length + subsResult.skipped.length + subsResult.failed.length}
          </p>
          {subsResult.skipped.length > 0 && (
            <p className="text-muted text-xs">
              {subsResult.skipped.length} already in the Library:{" "}
              {subsResult.skipped.map((s) => s.filename).join(", ")}
            </p>
          )}
          {subsResult.failed.map((f) => (
            <p key={f.filename} className="text-danger text-xs">
              {f.filename}: {f.error}
            </p>
          ))}
        </div>
      )}

      {(mode === "youtube" || mode === "article") && (
        <Field
          label="Link"
          hint="Importing the same link again won't create a duplicate."
        >
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder={mode === "youtube" ? "https://youtube.com/watch?v=…" : "https://…"}
            inputMode="url"
            className="field"
          />
        </Field>
      )}

      {(mode === "pdf" || mode === "epub") && (
        <div className="flex flex-col gap-1.5">
          {mode === "pdf" ? (
            <FilePicker prompt="Choose a PDF file" accept=".pdf" files={pdfFile} onChange={setPdfFile} />
          ) : (
            <FilePicker
              prompt="Choose an EPUB file"
              accept=".epub,application/epub+zip"
              files={epubFile}
              onChange={setEpubFile}
            />
          )}
          <span className="text-xs text-muted">Uploading the same file again is skipped.</span>
        </div>
      )}
      {mode === "subs" && (
        <div className="flex flex-col gap-1.5">
          <FilePicker
            prompt="Choose subtitle files"
            accept=".srt,.vtt,.webvtt,.smi,.sami,.ass,.ssa,.ttml,.dfxp,.xml"
            multiple
            files={subsFiles}
            onChange={(files) => {
              setSubsFiles(files);
              setSubsResult(null);
            }}
          />
          <span className="text-xs text-muted">
            .srt, .vtt, .smi, .ass or .ttml. Several files become one item each, in file name
            order. Files already imported are skipped.
          </span>
        </div>
      )}

      {mode !== "youtube" && mode !== "article" && (
        <Field
          label="Title"
          hint={
            mode === "subs"
              ? "Only used for a single file. A batch is titled by file name."
              : mode !== "paste"
                ? "Leave empty to use the file name."
                : undefined
          }
        >
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Title"
            className="field"
          />
        </Field>
      )}

      {mode === "pdf" && (
        <Field label="Pages" hint="Optional, for example 1-20.">
          <input
            value={pdfPages}
            onChange={(e) => setPdfPages(e.target.value)}
            placeholder="All pages"
            className="field"
          />
        </Field>
      )}

      {mode === "paste" && (
        <div className="flex flex-col gap-2">
          <Field label="Text">
            <textarea
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setSource("paste");
                setPreview(null);
              }}
              placeholder="Paste Korean text here"
              rows={7}
              className="field resize-none"
            />
          </Field>
          <FilePicker
            prompt="Or load a .txt file"
            accept=".txt"
            files={txtFile}
            onChange={handleTxtFile}
          />
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <button
              type="button"
              onClick={checkDifficulty}
              disabled={checking || !text.trim()}
              className="btn-link"
            >
              {checking ? "Checking…" : "Check difficulty"}
            </button>
            {preview && (
              <span className="text-muted">
                {preview.coverage !== null && (
                  <span className={coverageClass(preview.coverage)}>
                    {Math.round(preview.coverage * 100)}% known
                  </span>
                )}
                {preview.coverage !== null && ", "}
                {preview.new_per_page} new per page
                {preview.general_level !== null && preview.general_coverage !== null && (
                  <>
                    , generally {preview.general_level} (
                    {Math.round(preview.general_coverage * 100)}%)
                  </>
                )}
              </span>
            )}
          </div>
        </div>
      )}

      <TopicPicker value={topic} onChange={setTopic} />

      <Field label="Tags" hint="Separate with commas.">
        <input
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          placeholder="drama, season 1"
          className="field"
        />
      </Field>

      {error && <p className="text-danger text-sm">{error}</p>}
    </Sheet>
  );
}

/** Edit an item's title, topic and tags. Source/source_ref stay fixed (they are the
 *  import's identity for dedupe), and scores are recomputed by Rescore. */
export function EditBookSheet({
  book,
  onClose,
  onSaved,
}: {
  book: Book;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [title, setTitle] = useState(book.title);
  const [topic, setTopic] = useState(book.topic);
  const [tags, setTags] = useState(book.tags.join(", "));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    if (!title.trim()) {
      setError("Title can't be empty.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.patchBook(book.id, { title: title.trim(), topic, tags: splitTags(tags) });
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save changes.");
      setSaving(false);
    }
  };

  return (
    <Sheet
      title="Edit details"
      onClose={onClose}
      footer={
        <>
          <button onClick={onClose} className="btn-secondary flex-1">
            Cancel
          </button>
          <button onClick={save} disabled={saving} className="btn-primary flex-1">
            {saving ? "Saving…" : "Save"}
          </button>
        </>
      }
    >
      <Field label="Title">
        <input value={title} onChange={(e) => setTitle(e.target.value)} className="field" />
      </Field>
      <TopicPicker value={topic} onChange={setTopic} />
      <Field label="Tags" hint="Separate with commas.">
        <input
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          placeholder="drama, season 1"
          className="field"
        />
      </Field>
      {error && <p className="text-danger text-sm">{error}</p>}
    </Sheet>
  );
}
