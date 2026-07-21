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
