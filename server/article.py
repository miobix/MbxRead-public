"""Article/URL extraction — thin wrapper over trafilatura. Epic 12."""
import trafilatura


class ArticleError(Exception):
    """Raised when a URL can't be fetched or no article text can be extracted."""


def fetch_article(url: str) -> tuple[str, str]:
    """Returns (title, cleaned_text)."""
    downloaded = trafilatura.fetch_url(url)
    if downloaded is None:
        raise ArticleError(f"Could not fetch {url}")
    text = trafilatura.extract(downloaded, favor_recall=True)
    if not text or not text.strip():
        raise ArticleError(f"Could not extract article text from {url}")
    metadata = trafilatura.extract_metadata(downloaded)
    title = metadata.title if metadata and metadata.title else url
    return title, text
