// Built from existing theme tokens so the chips follow light/dark with no new hues.
const SOURCE_CHIPS: Record<string, { label: string; className: string }> = {
  yt: {
    label: "YouTube",
    className: "bg-accent/15 text-accent border border-accent/30",
  },
  article: {
    label: "Article",
    className: "bg-border/40 text-ink border border-border",
  },
  pdf: { label: "Book", className: "bg-border/40 text-ink border border-border" },
  epub: { label: "Book", className: "bg-border/40 text-ink border border-border" },
  subs: { label: "Subtitles", className: "bg-border/40 text-ink border border-border" },
  paste: { label: "Text", className: "bg-border/40 text-ink border border-border" },
  txt: { label: "Text", className: "bg-border/40 text-ink border border-border" },
};

export function SourceChip({ source }: { source: string }) {
  const chip = SOURCE_CHIPS[source] ?? {
    label: source,
    className: "bg-border/40 text-muted border border-border",
  };
  return (
    <span
      className={`inline-block shrink-0 text-xs font-medium px-2 py-0.5 rounded ${chip.className}`}
    >
      {chip.label}
    </span>
  );
}
