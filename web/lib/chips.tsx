// Epic 18: one colored chip per source type on the Queue. Kept within the existing
// warm "paper" theme tokens (accent/border/muted) rather than introducing new hues,
// so it stays theme-aware in both light and dark without adding to app/globals.css.
const SOURCE_CHIPS: Record<string, { label: string; className: string }> = {
  yt: {
    label: "YouTube",
    className: "bg-accent/15 text-accent border border-accent/30",
  },
  article: {
    label: "Article",
    className: "bg-border/40 text-ink border border-border",
  },
};

export function SourceChip({ source }: { source: string }) {
  const chip = SOURCE_CHIPS[source] ?? {
    label: source,
    className: "bg-border/40 text-muted border border-border",
  };
  return (
    <span
      className={`inline-block shrink-0 text-xs font-medium px-2 py-0.5 rounded-full ${chip.className}`}
    >
      {chip.label}
    </span>
  );
}
