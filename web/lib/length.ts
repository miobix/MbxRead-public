// Epic 18: the Queue's length stat. duration_seconds is yt-dlp's real video
// length (not a transcript-based estimate); word_count is derived server-side
// from the full text at insert time. Exactly one of the two is ever non-null.
type Lengthy = { word_count: number | null; duration_seconds: number | null };

export function formatLength(book: Lengthy): string | null {
  if (book.duration_seconds != null) {
    const mins = Math.round(book.duration_seconds / 60);
    return mins < 1 ? "<1 min" : `${mins} min`;
  }
  if (book.word_count != null) {
    return `~${book.word_count.toLocaleString()} words`;
  }
  return null;
}

// A standard reading-speed heuristic used ONLY to make "Shortest first" sort
// mixed source types against each other — never shown to the user (formatLength
// above always shows the exact word count or exact duration).
const WORDS_PER_MINUTE = 250;

export function estimatedMinutes(book: Lengthy): number {
  if (book.duration_seconds != null) return book.duration_seconds / 60;
  if (book.word_count != null) return book.word_count / WORDS_PER_MINUTE;
  return Infinity; // unknown length sinks to the bottom of "shortest first"
}
