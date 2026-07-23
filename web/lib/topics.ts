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
