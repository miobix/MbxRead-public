// Shared taxonomy used by the home filter, the add-book modal, and the /feeds
// editor. Epic 14 added ideas/science/tech alongside the original set.
export const TOPICS = [
  "gaming",
  "ideas",
  "science",
  "tech",
  "fitness",
  "news",
  "literature",
  "other",
] as const;

export const FEED_TYPES = ["rss", "youtube", "scraper"] as const;

// Book/candidate source values (server's `books.source` column) — shared by the
// Library and Queue filters.
export const SOURCES = ["paste", "txt", "yt", "pdf", "epub", "subs", "article"] as const;
