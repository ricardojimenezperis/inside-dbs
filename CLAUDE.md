# Inside DBs — site conventions

Personal site + technical blog of Ricardo Jimenez-Peris (Ric). Domain: https://ricardojimenezperis.com. English only.

## Stack
- Hugo (extended) + PaperMod theme as a git submodule at `themes/PaperMod`.
- Deployed to GitHub Pages by `.github/workflows/deploy.yml` on push to `main`. `static/CNAME` carries the custom domain.
- Local preview: `hugo server -D` from the repo root. Production build: `hugo --gc --minify`.

## Layout
- `content/_index.md` — home (PaperMod `homeInfoParams` in `hugo.toml` supply the intro text).
- `content/about.md` — bio.
- `content/systems/<slug>/index.md` — one page bundle per article; images live next to `index.md` and are referenced relatively (`{{< figure src="x.png" >}}`).
- `figures/<slug>/` — editable figure sources (`.pptx`) and PDF exports. Not published (`ignoreFiles` in `hugo.toml`). The published PNG is exported from the pptx at ≥ 2000 px wide.
- Post drafts and all working material live in the sibling folder `../posts/<NN-slug>/` (outside this repo), one folder per article — draft versions, figure sources, cover illustration sources, LinkedIn/forum texts. Never drop files in `../posts/` itself. Copy into this repo only what the site needs.

## Writing conventions
- Articles are structured as "follow a transaction through the system"; components are introduced by what they do.
- Front matter: `title`, `date`, `description` (one sentence, used for SEO/cards), `summary` (2–3 sentences, shown on lists), `tags`, `series`. Set `draft = true` until reviewed.
- Slugs: lowercase, hyphenated, name the system first (`foundationdb-architecture`, `foundationdb-five-second-window`).
- Figure captions go in `<p class="figure-caption"><em>Figure N. …</em></p>` right after the figure shortcode.
- Never declare an article "final" — a post is done when it is published, not before.

## Adding a new post
1. `hugo new systems/<slug>/index.md` (uses `archetypes/default.md`).
2. Drop the figure PNG next to `index.md`; keep its `.pptx`/`.pdf` under `figures/<slug>/`.
3. Fill `description`, `summary`, `tags`, `series`; set `draft = false` when ready.
4. `hugo server -D` to check, then commit and push.

## Publishing schedule
Canonical publication and distribution are separate events.
- **Sunday (morning/midday, Madrid):** publish on the site (`draft = false`, commit, push). Same day: "Request indexing" for the URL in Google Search Console and Bing URL Inspection (IndexNow fires automatically from the deploy). Leaves 2–4 days for the original to be established before any full copy exists elsewhere.
- **Monday:** check in Search Console that the URL is crawled/indexed and that the chosen canonical is ours; fix anything (OG image, sitemap, figure) with margin.
- **Wednesday 08:00 `America/Los_Angeles`** (the audience is largely on the US West Coast; treat the LA time as the constant, never hard-code Madrid): public launch — LinkedIn post, HN, FDB Forum, per the Distribution table. Madrid is normally 17:00, 16:00 during the short US/EU DST mismatch weeks (mid-March; late October).
- **Thursday/Friday:** syndication with full text — LinkedIn newsletter, Medium, DEV — only once the original shows as indexed.
- DEV's RSS import must stay in "create as draft" mode (never auto-publish), otherwise the Sunday push would syndicate immediately.
- Keep this rule for ~8–10 posts before tuning it with the site's own impression/engagement data.

## Distribution
Goal: get the article read, let Google accumulate authority on this domain, and let LinkedIn / the FDB community learn who Ric is and what he writes about — not to maximize clicks to the site.

| Channel | When | What |
|---|---|---|
| ricardojimenezperis.com | First, always | Full original article; the canonical URL. |
| LinkedIn post | Wed 08:00 PT (≈ 17:00 Madrid) | Native document post: the carousel PDF (see "LinkedIn carousel" below) + 200–300 words (≤ 3,000 chars) that must be worth reading without clicking. Structure: hook → technical idea → what path the article follows → a conclusion or open question. Never open with "I published a new post". Give the document a title (the article title). Link in the first comment. |
| LinkedIn newsletter "Inside DBs" | Thursday, once Search Console shows the original indexed | Full article as a newsletter issue (article format; subscribers get in-app, push and email notifications). First line: "Originally published on Inside DBs: <article URL>". Set the SEO title/description fields to the post's `seoTitle`/`description`. LinkedIn has no canonical, so never publish it before the original is indexed. |
| Hacker News | Wed 17:00–17:05 Madrid | Original title + site URL only. Only posts with general interest. |
| FoundationDB Forum | Wed 17:10–17:20 Madrid | Fairly complete technical summary, 400–700 words + image + link, written to provoke discussion and corrections from FDB implementers. Category by content (Development / Community). |
| Medium | Once Search Console shows the URL indexed (Thu/Fri) | Full article, open, via "Import a story" from the site URL (canonical → site). |
| DEV.to | Same as Medium | Full article via RSS import with canonical → site. |
| Lobsters | Selectively | Title + link; only especially strong posts. Invitation needed. |
| Reddit | Selectively | Native summary with a few technical ideas + link; never a weekly routine. |
| Facebook | Not a channel | At most a share from the personal profile. |

- Every channel gets its own text; only Medium/DEV carry the article verbatim. Medium/DEV are distribution, not funnels.
- No Substack as a second blog; a future email newsletter is a subscription to Inside DBs that links back here.
- Keep this routine for ~8–10 posts before optimizing channels or timing with own data.

## LinkedIn carousel
The LinkedIn launch visual is a carousel (PDF document post), one page per stage of the article, not the cover image alone and not a long infographic. Source: `../posts/<NN-slug>/<slug>-linkedin-post-vN.pptx`; export to PDF from PowerPoint (standard quality), check page count before uploading.

- **Page size:** 27 × 33.75 cm (4:5, = 1080 × 1350 px). Same proportion on every page. Safe margin ≈ 1 cm; LinkedIn overlays the page counter at the bottom.
- **Page order:** 1 cover (the city illustration + article title + "Ricardo Jimenez-Peris · Inside DBs"), then one page per stage in transaction order, then a closing page with the article URL as a hyperlink (clickable in the PDF), "Inside DBs · Ricardo Jimenez-Peris" and the site tagline.
- **Stage page layout:** the scene on top (full width, ≤ 18 cm tall) and a text block underneath. Text sizes are the constraint that drives everything: message names ≥ 25 pt (Consolas bold), details ≥ 20 pt (Calibri, muted grey); anything smaller is unreadable on a phone. Scene labels (roads, buildings, screens) go on the scene in the same style as the cover.
- **Callouts:** numbered orange badges (1, 2, 3 …) on the scene at the end of a thin grey leader line to the vehicle they refer to; the numbered explanations go in the text block below, in event order, so each page reads as a sequence. A red "!" badge marks a conflict/abort. No text pills inside the scene.
- **Visual vocabulary (must stay consistent with the cover):** cars = transactions, and a car's position shows the stage the transaction is in (a narrative simplification, stated as such); vans = batched request/response messages between components; trucks with containers = mutations from TLogs to storage servers. Cars are identified by colour, never by a label; the transaction followed across pages keeps its colour (blue). Buildings: GRV Proxy (glasses), Commit Proxy (barrier), Resolvers (three small temples), TLogs (containers) with the Durability Bridge, Storage Servers (disks), Master (city hall with two screens: Live Committed and Commit Version).
- **Numbers must be consistent across pages and with the article's mechanism.** Reference values for the FDB architecture carousel: liveCommittedVersion 1037, prevVersion 1041, batch commit version 1042; k5 v1/v2/v3 committed at 1010/1030/1042; blue tx readVersion 1037 → reads v2, writes k5 (v3 = 1042); green tx readVersion 1051 → reads v3; orange tx readVersion 1025 → aborted at the resolvers (read k5, written since). Invariants: readVersion ≤ liveCommittedVersion < commitVersion; all transactions in a batch share the commit version; a later transaction may hold a higher read version.
- **Message names are the real ones** (`GetRawCommittedVersion`, `GetCommitVersion` → `version`/`prevVersion`, `GetValueRequest`/`GetValueReply`, `ResolveTransactionBatch`, `TLogCommit`, `TLogPeek`); numbers are illustrative but never contradict the invariants.
- Rescaling in PowerPoint: use Format → Size → Scale % on the selection (scales text too); dragging a group's corner does not scale fonts.

## RSS and the `channels` field
- `layouts/rss.xml` overrides the theme's feed: full article HTML in `<content:encoded>` with all `src`/`href` made absolute, `<link>`/`<guid>` = canonical site URL, home feed limited to `mainSections` (posts only, no About) and to the last 20 items. DEV.to imports from `https://ricardojimenezperis.com/index.xml` and uses the item link as canonical.
- `channels` in front matter is an editorial checklist, nothing reads it: keep only the channels the article should go to, from `linkedin`, `medium`, `dev`, `fdb-forum`, `hn`, `lobsters`. Do not automate publishing from it.
- Post covers: `cover.jpg` (≈1800 px wide JPEG) next to `index.md`, declared in `[cover]` front matter; PaperMod shows it at the top of the post, on list cards and as the social-share image. Sources stay in `figures/<slug>/`.

## `<title>` convention
- Home: `Inside DBs · Ricardo Jimenez-Peris`. Every other page: `Ricardo Jimenez-Peris · <seoTitle, else title>` — the name goes first so search-engine truncation never drops it; `Inside DBs` is not repeated on posts (site name reaches search results via `site.Title`/structured data).
- `seoTitle` in front matter is a short search title (≤ ~40 chars, e.g. `FoundationDB Transaction Architecture`); `title` stays the narrative H1 and is what lists, RSS, OG cards and Medium/DEV imports use.
- Implemented in `layouts/_partials/page_title.html`, called from `layouts/_partials/head.html`, which is a verbatim copy of PaperMod's `head.html` (theme commit d376885) with only the `<title>` line changed. When updating the theme, re-copy `head.html` and re-apply that one line.
- Files must stay UTF-8 without BOM (the `·` separator).

## IndexNow
- Key file `static/090439f987cf705792d4250c535738ae.txt` (content = the key) is served at the site root. `scripts/indexnow.sh` reads the live sitemap and POSTs every URL to api.indexnow.org; the deploy workflow runs it after each successful deploy (step "Notify IndexNow", with the key in `INDEXNOW_KEY`). The key is public by design; rotating it means a new file + updating the workflow.
- Manual run: `INDEXNOW_KEY=090439f987cf705792d4250c535738ae bash scripts/indexnow.sh`.
