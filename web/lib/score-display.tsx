import type { Book } from "@/lib/api";

// Personal-coverage bands from docs/NEXT_STAGE_OPTIONS.md: ~0.95+ comfortable,
// 0.90-0.95 productive study zone, <0.85 a slog. Colour the % so difficulty
// reads at a glance.
export function coverageClass(coverage: number): string {
  if (coverage >= 0.95) return "text-accent";
  if (coverage < 0.85) return "text-danger";
  return "text-ink";
}

// General/public difficulty bands (Epic 15) — see score_general_difficulty in
// server/difficulty.py for why these are lower than the personal-coverage bands.
export function generalLevelClass(level: "easy" | "medium" | "hard"): string {
  if (level === "easy") return "text-accent";
  if (level === "hard") return "text-danger";
  return "text-ink";
}

export function ScoreLine({ book }: { book: Book }) {
  if (!book.scored_at) return null;
  return (
    <span className="text-xs text-muted">
      {book.coverage !== null && (
        <span className={coverageClass(book.coverage)}>
          {Math.round(book.coverage * 100)}% known
        </span>
      )}
      {book.coverage !== null && book.new_per_page !== null && " · "}
      {book.new_per_page !== null && `${book.new_per_page} new/pg`}
    </span>
  );
}

export function GeneralScoreLine({ book }: { book: Book }) {
  if (!book.scored_at || book.general_coverage === null || book.general_level === null) {
    return null;
  }
  return (
    <span className="text-xs text-muted">
      general: <span className={generalLevelClass(book.general_level)}>{book.general_level}</span>{" "}
      ({Math.round(book.general_coverage * 100)}%)
    </span>
  );
}
