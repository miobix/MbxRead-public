const SENTENCE_END_RE = /[.?!…]+|\n/g;

/** Extracts the sentence around `centerIndex`, from the previous sentence-end to
 * the next one — mirrors server/paging.py's break-point heuristic. */
export function extractSentence(content: string, centerIndex: number): string {
  let start = 0;
  let end = content.length;

  SENTENCE_END_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = SENTENCE_END_RE.exec(content))) {
    const boundary = match.index + match[0].length;
    if (boundary <= centerIndex) {
      start = boundary;
    } else {
      end = boundary;
      break;
    }
  }

  return content.slice(start, end).trim();
}

/** How much of a raw selection the reader is willing to keep. */
export const MAX_SELECTED_SENTENCES = 2;
export const MAX_SELECTED_CHARS = 200;

/**
 * Trims a raw selection down to its **tail** — at most the last two sentences, and
 * never more than MAX_SELECTED_CHARS.
 *
 * Selecting inside the reader's multi-column flow can hand back far more than was
 * dragged over (see the reader's `readSelection`), and the runaway is always at the
 * *head*: the end of the selection is where the drag actually finished. So keep the
 * end, drop the front. The result is still a contiguous slice of the content, so a
 * caller can locate it with `indexOf`.
 */
export function capSelection(
  text: string,
  maxSentences = MAX_SELECTED_SENTENCES,
  maxChars = MAX_SELECTED_CHARS
): string {
  const trimmed = text.trim();

  // Every index just past a sentence terminator — a trailing one isn't a boundary
  // between two units, it just ends the last one.
  const bounds: number[] = [];
  SENTENCE_END_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = SENTENCE_END_RE.exec(trimmed))) {
    const boundary = match.index + match[0].length;
    if (boundary < trimmed.length) bounds.push(boundary);
  }

  let start = bounds.length >= maxSentences ? bounds[bounds.length - maxSentences] : 0;

  // Backstop for punctuation-free runs: cut into the last maxChars, at the first
  // word break, so the kept tail never starts mid-word.
  if (trimmed.length - start > maxChars) {
    const hard = trimmed.length - maxChars;
    const space = trimmed.indexOf(" ", hard);
    start = space === -1 ? hard : space + 1;
  }

  return trimmed.slice(start).trim();
}
