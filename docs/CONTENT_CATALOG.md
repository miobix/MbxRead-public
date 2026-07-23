# Content catalog — Epic 10

Answers `docs/NEXT_STAGE_OPTIONS.md`'s open questions and ranks real sources, per its own
rule: **build the interest list before the automation.** This doc is the input Epic 12
(import wiring) and Epic 14 (daily fetch job) iterate over — it is not itself code.

Everything under "provisional / needs verification" was found via web search on
2026-07-21 and only spot-checked, not personally vetted by the user — treat picks (esp.
YouTube channels and specific authors) as a shortlist to react to, not a final answer.

## Reader profile (answered 2026-07-21)

- **Level:** solid — comfortable with everyday/simplified Korean, native content doable
  with effort. Catalog leans native-but-approachable first, not a beginner ramp.
- **Register:** both spoken (YouTube) and written (articles) equally — don't pick a lead.
- **Current Korean-content habits:** doesn't watch Korean YouTube today — hard to follow,
  off-putting. **This app is explicitly the bridge**; Korean YouTube is a stretch goal to
  grow into, not current-state content.
- **Games:** PS5, mostly free monthly PS Plus titles, rarely buys new — wants guides/
  reviews of *whatever's currently being played*, not a fixed game list. Currently
  defaults to English sites (Polygon, Kotaku) and doesn't know the Korean equivalents.
- **Fitness:** YouTubers/vloggers, not written blogs.
- **News:** Reddit + Hacker News (English) for general/tech. Open to Yonhap for tech
  content **only if it's actually interesting** — not a forced/automated source.
- **Literature (new category, not in the original doc):** wants a "high school reading
  experience" but for **modern** texts only — explicitly no archaic language, no
  centuries-old poetry, nothing built on unused vocabulary/structures. Likes thrillers/
  propulsive plots (*The Da Vinci Code*), pessimistic/thoughtful sci-fi (cites the game
  *Citizen Sleeper*'s tone), short literary fiction (Cortázar, García Márquez — short,
  interesting). Read *Lord of the Flies* recently as a "assigned-reading I missed" pick.
  Open to Korean authors, hasn't read any yet. Goal is everyday + hobby vocabulary usable
  in speech — not literary/archaic vocab.

## Games

| Source | Type | Feed | Topic | Notes |
|---|---|---|---|---|
| [인벤 (Inven) news](http://webzine.inven.co.kr/news/rss.php) | RSS | ✅ live, verified 2026-07-21 | games/news | Broad Korean game-industry news, general-audience register. |
| [루리웹 (Ruliweb) PS news](https://bbs.ruliweb.com/news/524/rss) | RSS | ✅ live, verified 2026-07-21 | games/PS | PS3/PS4-labeled board but currently carries current-gen PlayStation news too (confirmed: Unity/Unite Seoul, Indie Live Expo, Korean-package pre-order items dated 2026-07-20/21). Also has a general news feed (`/news/rss`) and a per-board pattern (`/[top-menu]/board/[id]/rss`) for narrower topics later. |
| [게임메카 (Gamemeca)](https://www.gamemeca.com/) | needs-scraper | ❌ no RSS URL found | games/news | Large Korean game news site; no working feed surfaced by search. Custom scraper or drop. |
| Per-game guide wikis (e.g. Namu Wiki game pages, community wikis) | needs-scraper | ❌ | games/guides | Depends entirely on *which* game is current — can't pre-catalog. Realistic path: on-demand lookup ("what's the Korean guide site for [current PS+ game]") rather than a standing feed. Good Epic 12 manual-import candidate, bad Epic 14 automation candidate. |
| **대도서관 (Daedosanggwan)** — [channel](https://www.youtube.com/channel/UCSHVH_AWVUc-C8-D8mh8W6A) | YouTube | RSS-able via `youtube.com/feeds/videos.xml?channel_id=…` once channel ID is confirmed | games/YouTube | Male, one of Korea's longest-running, most mainstream gaming YouTubers — broad variety content, clear/standard register (good first-YouTuber pick, not slang-heavy niche content). |
| **감스트 (Gamst)** | YouTube | needs channel ID lookup | games/YouTube | Male, hugely popular, football/FIFA + variety gaming; energetic, fast, more slang — harder register, stretch goal rather than starter. |
| **우왁굳 (Woowakgood)** | YouTube | needs channel ID lookup | games/YouTube | Male, popular variety/gaming + virtual-streamer collab content. |
| 악동 김블루 | YouTube | needs channel ID lookup + gender verify | games/YouTube | Surfaced as a top-ranked PUBG-focused channel; gender not confirmed in search results — verify before adding. |

**Games gap:** the user's actual habit ("guides/reviews for whatever's currently free on
PS Plus this month") doesn't map to a fixed RSS list — it's inherently a moving target.
Best fit: Inven/Ruliweb feeds for *awareness* (what's news-worthy), plus an **on-demand
manual import** path (Epic 12) for "look up the Korean guide/review for [this month's
game]" rather than trying to pre-subscribe to every possible game's guide site.

## Fitness

| Source | Type | Feed | Topic | Notes |
|---|---|---|---|---|
| **피지컬갤러리 (PhysicalGallery) / 김계란** — [channel](https://www.youtube.com/channel/UCdtRAcd3L_UpV4tMXCw63NQ) | YouTube | RSS-able via channel ID (have the channel URL, need the `UC…` id — visible in the URL above) | fitness/YouTube | Male (ex-UDT/special forces), #1-ranked Korean fitness YouTuber per search. Mix of workout technique, injury/pain explainers, some comedy — solid clear-register starting pick. |
| 박승현 | YouTube | needs channel ID lookup | fitness/YouTube | Male, surfaced as popular for physique + live workout-feedback content; less-detailed search confirmation — verify before adding. |

## News

| Source | Type | Feed | Topic | Notes |
|---|---|---|---|---|
| Yonhap (연합뉴스) tech section | RSS | ⚠️ **unverified** — candidate URLs (`en.yna.co.kr/RSS/news.xml`, `www.yna.co.kr/RSS/technology.xml`) both failed to fetch (likely anti-bot blocking the fetch tool, not necessarily dead — try a plain `curl`/browser check before relying on it) | news/tech | Explicitly "only if genuinely interesting" per the user, not a forced source — low priority to automate even once verified. |
| Reddit / Hacker News | — | — | — | English-language; these are where the user already gets news, not a Korean-text source. Not a catalog row — could inform *what topics* to manually seek Korean coverage of, but nothing to subscribe to here. |

## Literature (new category — not RSS/feed-based)

Books aren't a subscription source — each is a one-time acquisition (buy an ebook, import
it directly via the **EPUB** importer — `POST /api/import/epub`, the "EPUB" mode in the
add-book modal — or the PDF importer, or paste a chapter to try it first). EPUB gives the
cleanest text (real XHTML, no PDF layout artifacts) so prefer it when a book is available
in that format. Listed here as *candidates to react to*, not a feed list.

| Candidate | Format | Why it fits | Notes |
|---|---|---|---|
| **다빈치 코드 (The Da Vinci Code), Korean translation** | Novel | Direct match for the stated taste; a **young-adult/simplified Korean edition exists** ("청소년용") — genuinely good scaffolding since the plot is already known, lowering cognitive load while reading Korean. | Confirmed in print via 교보문고; both full and YA translations exist. |
| **정유정 (Jeong Yu-jeong)** | Novels | Korea's leading thriller author — dark, tightly-plotted, propulsive pacing. Her newest, *영원한 천국*, blends her usual thriller style with SF (mind-upload premise) — close match to the "pessimistic sci-fi, well-written" *Citizen Sleeper* comparison. | Start with a shorter/earlier work before her longer thrillers (*7년의 밤* is well-regarded but long). |
| **김영하 (Kim Young-ha)** | Novels | Literary-but-plot-driven psychological fiction (*살인자의 기억법* / "Diary of a Murderer" is short, punchy, widely translated); known for clean, modern, accessible prose — not archaic in any sense. | Good "famous Korean author" entry point. |
| **김초엽 (Kim Cho-yeop)** | Novel/short stories | Contemporary SF, huge domestic bestseller (*우리가 빛의 속도로 갈 수 없다면*, "If We Cannot Travel at the Speed of Light"), thoughtful/humanistic tone — closer to *Citizen Sleeper*'s reflective mood than action-thriller pacing. | Short-story collection format matches the Cortázar/García Márquez preference for shorter pieces. |
| **정보라 (Bora Chung)** | Short stories | *저주토끼* ("Cursed Bunny") — horror/SF/magical-realism short stories, International Booker Prize shortlist 2022. Closest available match to Cortázar/García Márquez: short, strange, dark, literary but readable. | Probably the single best fit for the specific "short stories, interesting, not a slog" ask. |

**Not investigated (flagging, not answering):** none of these authors' actual prose
difficulty was measured — Epic 9's scorer can do that once a sample chapter is pasted in
via "Check difficulty," which is the fast way to find out if a candidate is readable
*before* committing to a full book.

## TOPIK — the two Epic 10 sub-tasks

**(a) TOPIK past-exam reading passages as content.** Past TOPIK exams (levels I and II)
are published by 국립국제교육원 (NIIED, the exam's administering body) as downloadable
PDFs, reading sections included — genuinely level-graded modern Korean, a good ramp
alongside the harder native sources above. Fits the *existing* `import_tools/pdf_text.py`
path directly (no new import type needed). Exact current download URLs weren't verified
in this pass — locate via the official TOPIK site (topik.go.kr) when Epic 12 wires up
in-app PDF import.

**(b) TOPIK/frequency word list for Epic 13's cold-start scorer signal.** Not sourced yet
in this pass — candidates to check when Epic 13 starts: the official NIIED TOPIK vocab
lists (graded 1–6), or 국립국어원's (National Institute of Korean Language) published
frequency-ranked word lists. Either works as the Epic 13 input; NIIED's has the advantage
of being pre-graded by level rather than needing a rank cutoff.

## Ranked shortlist

**Automate now (Epic 14, once Epics 11–12 exist):**
- Inven game news (RSS, verified live)
- Ruliweb PS/game news (RSS, verified live)

**Needs a scraper or manual step (do later / on-demand, not a standing feed):**
- Gamemeca (no RSS found)
- Per-game guide sites (target changes monthly with whatever's on PS Plus — on-demand
  lookup fits this better than a subscription anyway)
- Yonhap tech (unverified feed + explicitly "only if interesting" — low automation value)

**YouTube (needs channel-ID lookup before any feed works — Epic 12 prep, not blocked on
anything else):** 대도서관, 감스트, 우왁굳 (games); 피지컬갤러리, 박승현 (fitness).
`youtube.com/feeds/videos.xml?channel_id=…` is the feed pattern once IDs are in hand.

**One-time imports, not feeds (Epic 12's PDF/paste path, not Epic 14's daily job):**
- TOPIK past-exam passages
- The five literature candidates above — try a sample chapter via "Check difficulty"
  before committing to a full book

## Epic 14 — final curated roster (2026-07-23, verified live & seeded)

Selected to the user's tastes (male-presenter, idea-exposition/science over variety), each
feed verified live this session and seeded via `db._SEED_FEEDS`. YouTube feeds store the
bare `UC…` channel id. Editable at runtime via the `/feeds` page.

| Source | Topic | Type | id / URL |
|---|---|---|---|
| 인벤 (Inven) | gaming | rss | https://webzine.inven.co.kr/news/rss.php |
| 루리웹 (Ruliweb) | gaming | rss | https://bbs.ruliweb.com/news/524/rss |
| 김성회의 G식백과 | gaming | youtube | `UCZ0bi2aVJngKLwFTU5g_fLQ` |
| 중년게이머 김실장 | gaming | youtube | `UCSgvQDek_7CQj08fu7kp1Iw` |
| 슈카월드 | ideas | youtube | `UCsJ6RuBiTVWRX156FVbeaGg` |
| 충코의 철학 | ideas | youtube | `UCUV9bHklegmYbdt091TNvjA` |
| 셜록현준 (유현준) | ideas | youtube | `UC7uDyFIqExDnfXAIZqumFrQ` |
| 최준영 박사의 지구본 연구소 | ideas | youtube | `UCstI8HwGQsHdqLDgyH0PImw` |
| 리뷰엉이 | science | youtube | `UCrBpV_pG2kyMMEHCMTNzjAQ` |
| 김명섭의 헬스교실 | fitness | youtube | `UCc5mVNF4R6ywMqbty91J0rQ` |
| 조코딩 | tech | youtube | `UCQNE2JmbasNYbjGAcuBiRRg` |
| 요즘IT | tech | rss | https://yozm.wishket.com/magazine/feed/ |
| ㅍㅍㅅㅅ | news | rss | https://www.ppss.kr/rss/allArticle.xml |
| 슬로우뉴스 | news | rss | https://slownews.kr/feed |
| 뉴스페퍼민트 | news | rss | https://newspeppermint.com/feed/ |

**Dropped in review (with reasons):** 김지윤 지식Play (user cut), 1분과학 (dead ~1yr),
과학드림 (biology / low cadence), 피지컬갤러리·핏블리 (variety / mixed-gender), 씨리얼
(documentary, no single host), 운동하는 물리치료사 자반 (too clinical/rehab), 얄팍한
코딩사전 (user cut), 디스이즈게임 (RSS hard-403s every path tried).

**Still open / future curation:** a true Not-Just-Bikes-style Korean urbanism/transit-critique
channel (none found; 셜록현준 carries the urban-design angle for now); literature is still
one-time PDF/paste imports, not feeds.
