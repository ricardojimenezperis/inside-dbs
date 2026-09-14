# Inside DBs — site conventions

Personal site + technical blog of Ricardo Jiménez-Peris (Ric). Domain: https://ricardojimenezperis.com. English only.

## Stack
- Hugo (extended) + PaperMod theme as a git submodule at `themes/PaperMod`.
- Deployed to GitHub Pages by `.github/workflows/deploy.yml` on push to `main`. `static/CNAME` carries the custom domain.
- Local preview: `hugo server -D` from the repo root. Production build: `hugo --gc --minify`.

## Layout
- `content/_index.md` — home (PaperMod `homeInfoParams` in `hugo.toml` supply the intro text).
- `content/about.md` — bio.
- `content/systems/<slug>/index.md` — one page bundle per article; images live next to `index.md` and are referenced relatively (`{{< figure src="x.png" >}}`).
- `figures/<slug>/` — editable figure sources (`.pptx`) and PDF exports. Not published (`ignoreFiles` in `hugo.toml`). The published PNG is exported from the pptx at ≥ 2000 px wide.
- Post drafts are written in the sibling folder `../posts/` (outside this repo) and copied here when ready.

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
- **Weekly publishing time:** Wednesday at 08:00 `America/Los_Angeles` (the audience is largely on the US West Coast). Treat the Los Angeles time as the constant; never hard-code a Madrid time.
- Madrid is normally 17:00, except during the short US/EU DST mismatch periods (mid-March; late October), when it is 16:00.
- Ritual, in Pacific time: 07:30 publish the article on the site and check production; 08:00 LinkedIn post linking it, and HN / FoundationDB Forum at the same time when the article fits there.
- Keep this rule for ~8–10 posts before tuning it with the site's own impression/engagement data.

## Distribution
Pipeline per article: site (canonical, always first) → LinkedIn native post (idea + figure + 5–10 lines + link, never the full text) → FoundationDB Forum for FDB-specific pieces (short intro written for that community; pick Development / Using FoundationDB / Community by content) → HN / Lobsters / Reddit only when the piece fits (submit the site URL, never the Medium copy; keep self-promotion occasional) → Medium full text, open, imported via "Import a story" so canonical points here → DEV.to fed automatically from the site's RSS with canonical set.
- Every channel gets its own text; only Medium/DEV carry the article verbatim.
- No Substack as a second blog; a future email newsletter is a subscription to Inside DBs that links back here. Facebook is not a channel.

## RSS and the `channels` field
- `layouts/rss.xml` overrides the theme's feed: full article HTML in `<content:encoded>` with all `src`/`href` made absolute, `<link>`/`<guid>` = canonical site URL, home feed limited to `mainSections` (posts only, no About) and to the last 20 items. DEV.to imports from `https://ricardojimenezperis.com/index.xml` and uses the item link as canonical.
- `channels` in front matter is an editorial checklist, nothing reads it: keep only the channels the article should go to, from `linkedin`, `medium`, `dev`, `fdb-forum`, `hn`, `lobsters`. Do not automate publishing from it.
- Post covers: `cover.jpg` (≈1800 px wide JPEG) next to `index.md`, declared in `[cover]` front matter; PaperMod shows it at the top of the post, on list cards and as the social-share image. Sources stay in `figures/<slug>/`.

## `<title>` convention
- Home: `Inside DBs · Ricardo Jiménez-Peris`. Every other page: `Ricardo Jiménez-Peris · <seoTitle, else title>` — the name goes first so search-engine truncation never drops it; `Inside DBs` is not repeated on posts (site name reaches search results via `site.Title`/structured data).
- `seoTitle` in front matter is a short search title (≤ ~40 chars, e.g. `FoundationDB Transaction Architecture`); `title` stays the narrative H1 and is what lists, RSS, OG cards and Medium/DEV imports use.
- Implemented in `layouts/_partials/page_title.html`, called from `layouts/_partials/head.html`, which is a verbatim copy of PaperMod's `head.html` (theme commit d376885) with only the `<title>` line changed. When updating the theme, re-copy `head.html` and re-apply that one line.
- Files must stay UTF-8 without BOM (the `·` separator).

## IndexNow
- Key file `static/090439f987cf705792d4250c535738ae.txt` (content = the key) is served at the site root. `scripts/indexnow.sh` reads the live sitemap and POSTs every URL to api.indexnow.org; the deploy workflow runs it after each successful deploy (step "Notify IndexNow", with the key in `INDEXNOW_KEY`). The key is public by design; rotating it means a new file + updating the workflow.
- Manual run: `INDEXNOW_KEY=090439f987cf705792d4250c535738ae bash scripts/indexnow.sh`.
