# Changelog

> ⚠️ **Beta fork — expect rough edges.** This is a community fork of
> [jstevenscl/vod-manager](https://github.com/jstevenscl/vod-manager), the
> actual upstream project. Changes here are still being validated in real
> deployments and some may not have been reviewed/merged upstream yet — treat
> this build as beta, keep backups of your data, and report anything odd.
>
> 🔗 For the original project, official releases, and the primary issue
> tracker, go to **[jstevenscl/vod-manager](https://github.com/jstevenscl/vod-manager)**.

All notable user-facing changes to this fork are documented here. Entries are
grouped by date and describe what changed in the deployed image — not every
internal commit, just additions and fixes worth knowing about if you're
running this build.

✅ = shipped and running in this fork only. Once work is proposed upstream,
add its second status marker and link to the pull request: 🔀 = open/under
review, 🔼 = included in an upstream release, ⛔ = closed without being
included.

### Upstream PR hygiene

Upstream submissions are prepared from a clean branch based on the current
upstream `main`, with one focused commit whenever possible. Never use the
fork's development `main` as a PR head. Before opening a PR, compare the
branch with upstream and remove fork-only changelog entries, internal issue or
bead references, AI/co-author attribution, private deployment/provider data,
hostnames, IPs, credentials, and unrelated tooling. Test data and URLs must be
synthetic placeholders. If upstream already contains equivalent or evolved
work, update the existing changelog entry with that PR/release reference
instead of opening a duplicate request.

## 2026-10-06 (Every TMDB answer is kept locally)

Proposed upstream as a standalone PR,
[#49](https://github.com/jstevenscl/vod-manager/pull/49), built on #48.

- ✅ 🔀 **The same question is never sent to TMDB twice.** Name searches and IMDb
  lookups made by automatic matching, library import, Metadata Review and the
  TMDB Library page are now saved in the local TMDB library. Asking again is
  answered locally and counts as a local lookup, not a TMDB request.
- ✅ 🔀 **"Nothing found" is remembered for 7 days**, then TMDB is asked again.
  Found answers don't expire.
- ✅ 🔀 **Search results are saved in full.** Full details for the top 5 results
  of each search are stored, so they can be matched locally later.
- ✅ 🔀 **TMDB list sync saves the titles it returns.** List contents are still
  checked live.

## 2026-10-05 (Automatic TMDB matching for titles without an ID)

Proposed upstream as a standalone PR,
[#48](https://github.com/jstevenscl/vod-manager/pull/48), built on #47 (it
needs the local TMDB library).

- ✅ 🔀 **Titles without a TMDB ID are matched automatically.** After each fill
  burst (or when you click "Match titles without a TMDB ID"), up to 2,000
  catalog titles without an ID are matched by name and year. Series are matched
  first. The local TMDB library is checked first, and TMDB is searched only if
  it has no match. A match is applied the same way a reviewer would apply it,
  so cards for the same show from different providers merge into one.
- ✅ 🔀 **Unclear results go to Metadata Review.** The title stays visible while
  it waits there, and nothing is guessed. Unclear means more than one possible
  match, a year that doesn't agree with TMDB's, or no year when TMDB has other
  titles with the same name. Titles TMDB doesn't know are tried again a week
  later.
- ✅ 🔀 **Local hit rate.** The TMDB Library page shows how many of today's
  lookups were answered locally.
- **Tests:** 13 new tests. Full backend suite: 487 passed. Frontend build is
  clean.

## 2026-10-05 (Local TMDB library)

Proposed upstream as a standalone PR,
[#47](https://github.com/jstevenscl/vod-manager/pull/47), based on current
upstream `main` and independent of #35.

- ✅ 🔀 **TMDB lookups are saved locally and reused.** Once a TMDB API key is
  set, every title the app looks up is stored in `data/tmdb.sqlite` and served
  from there next time. This covers enrichment, Metadata Review search, AI
  resolve candidates, library matching and episode lists. Name searches use
  the local copy only when it finds an exact title match; anything else still
  goes to TMDB.
- ✅ 🔀 **Background fill.** The most popular titles are pre-fetched in small
  bursts (defaults: 2,000 × 4 bursts a day, 20,000 requests/day cap,
  4 at a time, top 100,000 per type). TMDB's change feed keeps stored titles
  current.
- ✅ 🔀 **TMDB Library page** under Curation & Maintenance shows:
  - store status
  - fill settings
  - a lookup box
  - a Clear button
- ✅ 🔀 **On/off switch.** Off stops the fill and sends every lookup straight
  to TMDB, as before. Use it if disk space is tight. The existing file stays
  until you clear it.
- ✅ 🔀 **Shared toast messages.** "Settings saved" and future confirmations
  use one reusable toast component.
- **Disk usage — expect up to ~1.5 GB.** Measured on the test bed:
  - after loading TMDB's ID lists (~1.4M IDs) and ~2,000 titles, the file was
    ~155 MB, of which ~143 MB is a fixed cost for the ID lists
  - each stored title adds about 6 KB
  - a full pre-fill at the defaults (100k movies + 100k shows) comes to
    roughly 1.3–1.5 GB and takes a few weeks at the default rate
  - lowering "Pre-fill top N" shrinks that proportionally
- **Tests:**
  - 36 new tests cover the store, the fill and the on/off routing
  - full backend suite: 251 passed on the upstream PR branch
  - frontend build is clean
  - live: the first fill run stored ~2,000 titles, and lookups were then
    served locally; with the switch off they went to TMDB.

## 2026-10-05 (Auto-merge same TMDB ID up to 2 years apart)

All four entries below are proposed upstream as a follow-up commit on
[#35](https://github.com/jstevenscl/vod-manager/pull/35), which introduced the exact-year gate.

- ✅ 🔀 **Cards with the same TMDB ID now auto-merge when their years differ by
  1 or 2.** Providers often list a festival or regional year, which left the
  same film as two cards (e.g. *All Roads to Pearla* 2019 / *Sleeping in
  Plastic* 2020). A shared source language is still required, and gaps of 3+
  years stay for manual review.
- ✅ 🔀 **Duplicate Finder explains each group.** A line under the badges says
  why the cards were not auto-merged: no TMDB ID, different TMDB IDs, no
  shared language, years too far apart, auto-merge turned off, or that the
  group qualifies and merges on the next refresh.
- ✅ 🔀 **Year gap is adjustable.** Settings → Duplicate Finder has a 0–3 year
  dropdown (default 2; 0 = exact year only). Lowering it later does not split
  cards that already merged.
- ✅ 🔀 **"Merge existing duplicates now" button.** Automatic merges only
  re-check cards an import or refresh touched, so pairs that already qualify
  can sit split. The button runs the same auto-merge (same language and year
  rules) across the whole catalog once. Merges can't be undone, so download a
  database backup first. On the test bed it merged 219 movies and 26 TV shows,
  taking Duplicate Finder from 381 movie groups to 169.

## 2026-10-05 (Newly discovered categories stay excluded)

- ✅ **"Archive new categories" now keeps a new category excluded.** A
  category first seen on an import was only excluded for that one run; the
  next import imported its content as active. New categories are now added
  to the provider's saved category exclusions, where you can untick them to
  import. A provider's very first import no longer excludes every category.

## 2026-10-04 (Upstream PRs consolidated into #35)

- 🔀 **[#35](https://github.com/jstevenscl/vod-manager/pull/35) now carries the import reporting, staged TMDB/episode
  workflow, episode preloading, artwork-fingerprint and load-on-open work.**
  It was rebuilt as one commit on upstream v0.2.20 and answers every review
  finding from #31 and #35. [#31](https://github.com/jstevenscl/vod-manager/pull/31), [#43](https://github.com/jstevenscl/vod-manager/pull/43), [#44](https://github.com/jstevenscl/vod-manager/pull/44) and [#45](https://github.com/jstevenscl/vod-manager/pull/45) were
  closed as superseded. #39–#42 remain open as separate PRs.

## 2026-10-04 (Excluded-category purge review fixes)

- ✅ 🔀 **The excluded-category cleanup now uses only your saved exclusion
  list.** Follow-up to the review of
  [#39](https://github.com/jstevenscl/vod-manager/pull/39). Categories that
  "archive new categories" flags for one run are no longer treated as
  excluded by the cleanup, so their content isn't deleted.
- ✅ 🔀 **The cleanup logs a warning summary** with counts and example titles
  every time it removes content during an import.
- ✅ 🔀 **The cleanup preview/apply endpoint is XC-only.** Plex, Emby and
  library providers get an error instead of risking removal of
  uncategorized content.

## 2026-10-04 (Artwork changes no longer count as catalog changes)

- ✅ 🔀 **New posters from a provider no longer count as catalog changes.**
  Proposed upstream in [#35](https://github.com/jstevenscl/vod-manager/pull/35) (originally [#44](https://github.com/jstevenscl/vod-manager/pull/44), closed as superseded).
  A refresh now counts a title as changed only when something that affects
  playback or placement changes: stream id, file type, TMDB id, name,
  category, or (for series) the provider's new-episodes timestamp. Posters,
  plots, genres and cast come from TMDB, so a provider swapping its image
  links no longer marks thousands of titles as changed in Sync History or
  re-runs TMDB matching for all of them. Titles imported before this change
  switch over quietly on their next refresh, without being counted as
  changed.
  Verified live: the first refresh after upgrading showed 0 changed titles
  on all 4 providers (one provider had shown about 25,800 the run before),
  and no TMDB re-matching ran.
- ✅ 🔀 **Opening a show loads its missing episodes.** Proposed upstream in
  [#35](https://github.com/jstevenscl/vod-manager/pull/35) (originally [#45](https://github.com/jstevenscl/vod-manager/pull/45), closed as superseded).
  Imports no longer wait on an episode-sync phase; the background preloader
  fills episodes over time, and opening a show fetches any provider that
  has none yet, even when another provider already supplied some.

## 2026-10-04 (Episode list preloading settings)

- ✅ 🔀 **Episode lists preload about 3x faster, still gently.** Proposed upstream
  in [#35](https://github.com/jstevenscl/vod-manager/pull/35) (originally [#43](https://github.com/jstevenscl/vod-manager/pull/43), closed as superseded). The background
  preloader now pauses 15 minutes between batches instead of 45, so it does
  about 290 shows per hour per provider instead of about 100. It still sends
  one request at a time with 3 seconds between requests.
- ✅ 🔀 **Preloading is adjustable in Settings → Refresh Schedule.** Proposed
  upstream in [#35](https://github.com/jstevenscl/vod-manager/pull/35) (originally [#43](https://github.com/jstevenscl/vod-manager/pull/43)). The new
  "Episode list preloading" section sets shows per batch, the pause between
  batches and the gap between requests. It explains what each one does and
  shows a live shows-per-hour estimate. Setting 0 shows turns preloading off.
  The card's help text is also brighter.
- ✅ 🔀 **Shows whose episode list failed to load move to the back of the
  queue.** Proposed upstream in [#35](https://github.com/jstevenscl/vod-manager/pull/35) (originally [#43](https://github.com/jstevenscl/vod-manager/pull/43)).
  The preloader used to keep a failed show at the front, so every batch started
  by re-trying the same dead shows. Now failed shows are tried only after every
  other pending show, and at most once a day. Opening or playing a show still
  loads its episodes right away.
- ✅ 🔀 **A provider that keeps failing stops its batch early, as intended.**
  Proposed upstream in [#35](https://github.com/jstevenscl/vod-manager/pull/35) (originally [#43](https://github.com/jstevenscl/vod-manager/pull/43)).
  A failed episode-list request was not counted toward the "3 failures in a row"
  stop, so a failing provider was still sent the whole batch.
- Verified live after deploy: batches of 100 now start about 20.6 minutes
  apart (was about 51), about 291 shows per hour per provider (was about
  118). Requests stay about 3.3 seconds apart, with 0 failures and 0 errors
  logged.

## 2026-10-04 (Sync History completeness)

- ✅ **Scheduled refreshes no longer stay "running" in Sync History.** The
  background refresher finished its import but never closed the run, so a
  refresh that found nothing new sat at "running" forever. Manual Plex/Emby
  imports had the same gap. Runs now close as "ready" (or "failed"), and any
  run a restart leaves open is closed on startup.
- ✅ **Plex, Emby, Jellyfin and library refreshes now show in Sync History.**
  Only XC providers wrote a history row; scheduled and Apply-rules refreshes
  of the other types left no trace. Apply rules also handled library
  (rclone/SMB) providers as XC, which failed; they now use the library importer.
- ✅ 🔀 **Apply rules counts as a catalog refresh.** Proposed upstream in [#42](https://github.com/jstevenscl/vod-manager/pull/42). It re-imports every
  provider but didn't reset the refresh timer, so the scheduler imported the
  same provider again shortly after.

## 2026-10-04 (Series merge keeps provider links)

- ✅ 🔀 **"Apply rules" no longer re-creates the same shows as "new" on every
  run.** Proposed upstream in [#41](https://github.com/jstevenscl/vod-manager/pull/41). When two cards for the same show were merged, the provider link on
  the card being merged away was deleted along with it. On the next import
  that provider's show looked unknown, so it was created again as "new" and
  auto-merged again — about 30–50 shows per provider churned on every run.
  - Merging series now moves every provider source onto the surviving card,
    the same way movie merges already did.
  - Links lost before this fix are rebuilt by the next import. Expect one
    more run with some "new" shows, then the counts should drop to real
    additions only.
- ✅ **Plex, Emby, Jellyfin and library shows no longer come back as "new"
  after a merge.** When a show from one of these sources was merged into
  another card (for example "Show (2025)" into "Show"), the next import
  couldn't find it and created a fresh card every run. These importers now
  find the show through its saved source link, as provider imports already
  did.

## 2026-10-03 (Episode trickle pacing)

The credential fix and the "Provider 5 of 4" label fix are proposed upstream in
[#40](https://github.com/jstevenscl/vod-manager/pull/40) (follow-up to #39).
Episode trickle pacing stays fork only: it depends on fork-only episode
discovery changes that upstream doesn't have.

- ✅ 🔀 **Docker build no longer hangs.** The frontend stage now builds once on
  the runner's native platform instead of under arm64 emulation, and the
  build job is capped at 30 minutes. A build that had sat for 36+ minutes now
  completes in about 7. Proposed upstream in [#39](https://github.com/jstevenscl/vod-manager/pull/39).
- ✅ **Paced background episode discovery.** Episode lists and stream ids
  for shows that haven't been opened yet are now fetched on their own
  schedule instead of a handful at a time once every enrichment cycle.
  - Every 45 minutes, up to 100 pending series sources per provider are
    fetched, one request at a time with 3 seconds between requests.
  - A provider's batch stops early as soon as it goes into backoff or fails
    3 requests in a row; the rest stay pending for the next run.
  - Batch size, interval and spacing are config settings
    (`episode_trickle_batch`, `episode_trickle_interval_seconds`,
    `episode_trickle_spacing_seconds`).
  - Opening a show still fetches its episodes immediately.
- ✅ 🔀 **Provider credentials hidden in "Apply rules" errors.** A failed
  provider in the apply-rules summary no longer shows the provider's
  username and password in the error URL. Proposed upstream in [#40](https://github.com/jstevenscl/vod-manager/pull/40).
- ✅ **Episode trickle no longer collides with "Apply rules".** A trickle
  run that overlapped a catalog import queued episode writes behind the
  import and a few were skipped with "database is locked". The trickle now
  skips its run while a catalog import is in progress, and stops early if
  one starts mid-run; the skipped shows are picked up on the next run.
- ✅ 🔀 **"Provider 5 of 4" progress label fixed.** While "Apply rules" finished
  its final category re-sweep, the progress text counted one provider past
  the total and still named the last provider. It now reads "All N
  provider(s) synced — finalizing…". Proposed upstream in [#40](https://github.com/jstevenscl/vod-manager/pull/40).

## 2026-10-03 (Curation layout)

- ✅ **Curation tab: language and country filters side by side.** Separate
  from the v0.2.20 adoption below — layout only, no behavior change.
  - Import Language Exclusion, Enabled Playback Languages and Import Country
    Exclusion now sit together in one row as three equal-width columns on
    wide screens, and stack on narrow ones.
  - Language Backfill & Retroactive Split moves below that row.
  - Descriptions that said "above" now just name the sibling section.

## 2026-10-03

- ✅ **Upstream v0.2.20 adopted into the fork (version label now 0.2.20).**
  One combined change: the upstream merge plus the fixes found while
  validating it. A single upstream pull request will be proposed once this
  build has been validated live.

  **Adopted from upstream v0.2.20**
  - Library sources (local folder, SMB, SFTP, S3, Google Drive, Dropbox, Box)
    via rclone, alongside XC/Plex/Emby/Jellyfin providers. The Docker image
    now installs rclone; rclone daemons are stopped on provider delete and on
    shutdown. Library imports follow the fork's skip-at-import exclusion model
    (excluded files are never stored, but still count as "seen").
  - Import country exclusion (country-suffix tags), wired into XC, Plex, Emby
    and library imports, with its own Curation card.
  - Duplicate Finder partial groups: check only the candidates you want to
    merge or ignore.
  - Cross-process config lock: every settings write now goes through one
    locked read-modify-write, including the fork-only duplicate-finder and
    enabled-language settings.
  - TMDB lookup-failure queue, metadata-review partial indexes, and
    archive preservation fixes.
  - Jellyfin `X-Emby-Token` fallback and Dispatcharr same-name profile adoption.
  - Recovered stream failures now clear only recoverable failures; terminal
    failures are kept.

  **Kept fork behavior where the two overlapped**
  - Fork post-import enrichment pipeline (changed-ids-only TMDB passes,
    per-run sync reports) instead of upstream's known-series identity
    reconciliation.
  - Fork language backfill / retroactive split and Enabled Playback Languages
    UI; upstream's parallel language backfill/split routes and cards were
    removed so there is one implementation.
  - Fork catalog-status panel and workflow banner in the header.
  - Language detection: fork prefix and country-suffix checks run first;
    upstream's category-tag fallback is used last.

  **Fixes found during validation**
  - 🔀 **Excluded categories now remove content already imported.** Adding a
    provider category to the import exclusion list used to stop only *new*
    items; anything imported earlier stayed forever. XC imports now remove that
    provider's sources in excluded categories (and uncategorized sources when
    "exclude uncategorized" is on). A card is deleted only when it has no
    source left from any provider, and manually curated cards are never touched.
    A preview/apply endpoint is also available:
    `POST /api/vod/providers/{id}/purge-excluded-content/?dry_run=true`
    (default is preview; `dry_run=false` applies).
    **Back up your database before upgrading** — the first XC import after
    upgrading applies this cleanup automatically. Proposed upstream in
    [#39](https://github.com/jstevenscl/vod-manager/pull/39).
  - Possible Metadata Matches:
    - Reciprocal pairs (A→B and B→A) are now listed once.
    - Pairs that share no source language (which the merge always refuses) are
      no longer listed.
    - Candidates are ordered best first (has a TMDB id, then has a year), so
      the pre-selected candidate is the strongest match.
    - A failing pair in a bulk merge is reported as skipped with its reason
      instead of aborting the batch, and the UI now shows an error if the
      request fails.
  - Sync History reports: movie and series counters no longer overwrite each
    other in the combined summary. Each run's phase timings stay with that run
    even when a newer import starts. Review timing now starts after enrichment
    instead of wrapping it. A cancelled enrichment (shutdown or redeploy) now
    marks its run as failed instead of leaving it "running".
  - 🔀 TMDB review search (needs-review, missing-artwork, AI suggest, bulk AI)
    strips a trailing year and country tag from the stored name before
    searching, so titles like `Show (2014) (US)` find their match. Proposed
    upstream in [#39](https://github.com/jstevenscl/vod-manager/pull/39).
  - Removed an internal tracker reference from the Language Backfill card text
    and fixed garbled characters (`â€¦`/`â€”`) in the UI.

  Database migrations were tested against a copy of a production-sized
  database: additive only (new library-match table, indexes and columns),
  repeat runs are no-ops, there are no row-count changes, and integrity and
  foreign-key checks pass.

## 2026-09-24

- ✅ Provider Sync History now separates catalog change events into Movies and
  Series tabs below the unchanged run summary, with per-tab counts and
  independent scrolling. Import “matched” counters remain source/catalog
  match counts; automatic merges remain separate canonical-card merge actions.
  A clean upstream follow-up will be submitted after the sync-history
  implementation in [#35](https://github.com/jstevenscl/vod-manager/pull/35)
  lands.

## 2026-09-22

- ✅🔀 Provider imports now retain a deleteable, per-run catalog report. Each
  report records movie/series cards that were added or changed, preserves the
  provider-import, metadata/episode enrichment, and review-preparation timings,
  and can be opened or multi-selected from Curation & Maintenance without
  deleting catalog content. The completion banner reports import and automatic
  follow-up durations separately so a long-lived workflow timer cannot be
  mistaken for a slow provider import.
  The same import pass automatically merges an existing movie or series with
  the same normalized title and exact year into its sole TMDB-backed card when
  the duplicate is missing a TMDB ID. Year mismatches and competing TMDB
  candidates remain available for review, and the report records the merge
  action. Proposed upstream in [#35](https://github.com/jstevenscl/vod-manager/pull/35).

- ✅🔗 Header readability improved: the application version and commit are now
  brighter and slightly larger, and the catalog-status banner uses a larger,
  brighter title/detail treatment with a slightly larger status bar. Upstream
  applied the equivalent fix in [f1b4b2a](https://github.com/jstevenscl/vod-manager/commit/f1b4b2a)
  after closing [#36](https://github.com/jstevenscl/vod-manager/pull/36).

## 2026-09-19

- ✅🔀 Post-import catalog processing now completes the intended staged
  handoff: TMDB metadata resolution runs first, then series-only provider
  detail calls discover episode streams. Movie metadata never falls back to a
  second provider call in this workflow. Automatic TMDB merges require
  matching non-null years; conflicting or missing years remain for user review.
  Episode progress reports provider sources separately from canonical series,
  and bounded work drains incrementally in the background. Proposed upstream
  in [#35](https://github.com/jstevenscl/vod-manager/pull/35) (originally [#31](https://github.com/jstevenscl/vod-manager/pull/31), closed as superseded).

- ✅🔼 Language policy now applies consistently at import: XC, Plex, and
  Emby catalogs use the enabled playback languages, classify from the raw
  provider title before display rules can remove a prefix, and skip excluded
  items before they enter the catalog. Legacy automatically excluded entries
  are safely cleaned up while manual archives remain untouched. Regression
  coverage: 53 focused language-policy tests passed. Proposed upstream in
  [#29](https://github.com/jstevenscl/vod-manager/pull/29). The submitted PR
  was closed without a merge commit; the functionality was incorporated in
  upstream [v0.2.18](https://github.com/jstevenscl/vod-manager/releases/tag/v0.2.18).

- ✅🔼 Configuration now includes preview-before-apply language maintenance:
  backfill missing source-language values or recompute values that no longer
  match the raw provider title. These operations correct source metadata only;
  catalog entries are not changed. Regression tests and the production
  frontend build passed. Proposed upstream in
  [#30](https://github.com/jstevenscl/vod-manager/pull/30). The submitted PR
  was closed without a merge commit; the functionality was incorporated in
  upstream [v0.2.18](https://github.com/jstevenscl/vod-manager/releases/tag/v0.2.18).

- ✅ The fork image version label now tracks upstream **v0.2.19**. This aligns
  the release baseline with the latest upstream release while retaining the
  fork-only workflow and operational improvements documented below.

- ✅🔀 Playback relay recovery retries transient provider disconnects by
  reopening the upstream at the next byte range. Normal client disconnects
  and superseded range requests remain normal playback behavior, and incomplete
  capacity reservations are hidden from Activity instead of displaying as
  `undefined`/`NaN`. Proposed upstream in
  [#34](https://github.com/jstevenscl/vod-manager/pull/34).

- ✅ Production validation with placeholder Provider A confirmed the staged
  import path: 22,884 movies completed in 8.75s fetch / 1.14s database time
  with 0 errors, and 5,228 series completed in 10.03s fetch / 0.42s database
  time with 296 created, 4,931 matched, 376 source changes, 48 review flags,
  and one item-level error. Post-import enrichment was queued after the
  import drained. During the same validation window, a representative movie
  continued playing at 60% after a mid-stream upstream disconnect: the relay
  issued range recovery and Dispatcharr opened the following range request
  successfully. The obsolete failed range request still appeared in Failed
  Streams in the deployed build; the follow-up now clears that row when a
  matching successor range request opens successfully, while preserving
  genuine terminal failures.

- ✅ Episode-source progress now uses the exact bounded pending-source snapshot
  that the worker processes, instead of calculating the denominator from one
  list and processing a larger list later. This prevents displays such as
  `317 / 113` during staged episode discovery. The stale recovered-failure
  cleanup and bounded-progress regression coverage passed 24 focused backend
  tests.

- ✅🔀 Xtream/Emby catalog refreshes now scope episode-source ranking to the
  requested series before SQLite runs its source-selection window, instead of
  ranking the entire episode catalog for every `get_series_info` request.
  Repeated client activity updates are also debounced, eliminating a SQLite
  write for every catalog item. This reduces CPU and refresh latency for direct
  Emby connections and for Dispatcharr instances using VOD Manager as their
  upstream catalog. Regression coverage and before/after measurements are
  recorded with the deployment validation: representative series requests fell
  from about 4.05–4.12 seconds to 16–28 milliseconds on the production-sized
  catalog snapshot. Proposed upstream in
  [#33](https://github.com/jstevenscl/vod-manager/pull/33).

## 2026-09-18

- ✅ Post-import series episode discovery now runs with automatic concurrency
  of six provider requests, while preserving persistent provider HTTP clients.
  This is the current value documented in upstream [#35](https://github.com/jstevenscl/vod-manager/pull/35) (originally [#31](https://github.com/jstevenscl/vod-manager/pull/31)).

- ✅ Enrichment progress now counts canonical series once instead of counting
  each provider source separately, preventing misleading totals above 100%.

- ✅🔀 Metadata Review now provides an explicit **Merge into existing** action
  when a reviewer confirms a same-title catalog match that has no TMDB ID.
  Automatic matching remains disabled in that case; the merge requires an
  explicit confirmation. Proposed upstream in
  [#35](https://github.com/jstevenscl/vod-manager/pull/35) (originally [#31](https://github.com/jstevenscl/vod-manager/pull/31)).

- ✅ Stream Recovery is now a dedicated Operations page for movies blocked
  after every playable source repeatedly fails. It lists the blocked title,
  provider copies, failure counts, and last failure time. Test source opens
  the real authenticated provider-preview path; a successful stream clears
  the block and restores the movie to client VOD listings automatically.
  Failed Streams remains the diagnostic history. TV recovery remains
  episode-level work so one bad episode never hides an entire series.

- ✅🔼 A movie is now automatically blocked from exported client catalogs when
  every active, enabled-language provider source has repeatedly failed. The
  source rows and failure history remain available for diagnosis; a successful
  retry clears the block and returns the title to the catalog. Deployment also
  sweeps already-exhausted titles, so existing all-404 entries are removed
  without needing another playback attempt. Live validation confirmed the
  reported all-404 case was an upstream provider issue; after the provider was
  corrected, the affected movies played normally again. Proposed upstream in
  [#28](https://github.com/jstevenscl/vod-manager/pull/28). The submitted PR
  was closed without a merge commit; the functionality was incorporated in
  upstream [v0.2.18](https://github.com/jstevenscl/vod-manager/releases/tag/v0.2.18).

- ✅🔼 Series refreshes now preserve the canonical row already attached to a
  provider's source ID, including when that provider is a secondary source.
  This fixes a regression that could reassign a source during a refresh and
  leave a duplicate zero-source series row in Metadata Review or Duplicate
  Finder. Successful imports now also purge existing rows with neither a
  provider source nor playable episode source; normal newly listed series
  awaiting episode detail are retained. Proposed upstream in
  [#28](https://github.com/jstevenscl/vod-manager/pull/28). The submitted PR
  was closed without a merge commit; the functionality was incorporated in
  upstream [v0.2.18](https://github.com/jstevenscl/vod-manager/releases/tag/v0.2.18).

- ✅ Metadata Review now calls out likely existing catalog matches when a row is
  expanded. Same-title rows from another provider show their year, source
  count, and match reason. Choosing a candidate with a confirmed TMDB ID
  applies its identity/year and immediately uses the existing merge-safe
  resolver; no second Duplicate Finder action is required. Rows without an ID
  remain informational so title-only matches are never auto-merged.

- ✅ Automatic post-import processing is now **import-first and provider-safe**.
  Imported TMDB IDs continue through the bounded TMDB metadata pass; titles
  without an ID remain in Metadata Review instead of triggering automatic
  `get_vod_info` or `get_series_info` requests. Provider detail and episode
  discovery remain explicit, user-initiated actions. This prevents a normal
  catalog import from turning into thousands of provider calls.

- ✅ Bulk enrichment now excludes disabled providers at selection time, even
  when old source rows still reference them. Progress totals are scoped to
  active providers, so an inactive provider cannot continue receiving requests
  or inflate the displayed workload. Validated against a live disabled-provider
  cleanup and a separate multi-provider import test.

- ✅ Stale bulk-enrichment progress is cleared when a new import or automatic
  workflow starts, and cancelled runs no longer leave old totals and completion
  time visible. This prevents one provider's previous run from being mistaken
  for the current import.

- ✅ The sidebar now displays the manager host's current external IP using a
  cached, authenticated lookup. The value refreshes periodically and shows
  unavailable cleanly when the lookup service cannot be reached.

- ✅ Provider sources now record `provider_detail_deferred` explicitly. A
  source imported without a TMDB ID is marked for later review rather than
  being silently treated as an automatic enrichment failure; approving an ID
  or completing explicit provider detail clears the marker. This leaves a
  durable hook for future review and on-demand actions.

## 2026-09-15

- ✅ Bulk enrichment now has a cooperative **Cancel enrichment** action in the
  UI and API. Cancellation stops scheduling new provider-detail requests while
  allowing the current request to finish, so a large fallback pass can be
  halted without restarting the container. Added cancellation regression tests.

- ✅ XC movie imports now capture TMDB identity from either the provider's
  `tmdb` or `tmdb_id` bulk-list field. This prevents valid WarpTV-style IDs from
  being mistaken for missing identities and triggering thousands of unnecessary
  provider-detail requests.

- ✅🔼 Cross-provider matches now preserve an existing automatic archive by
  default. If a movie or series was archived and a later provider supplies the
  same title, that source is attached without resurrecting the catalog item;
  only an exact re-import of the already-known source can clear an automatic
  archive. Manual archive decisions remain protected. Regression coverage now
  includes both movies and series. Submitted as clean upstream PR
  [#26](https://github.com/jstevenscl/vod-manager/pull/26). The submitted PR
  was closed without a merge commit; the functionality was incorporated in
  upstream [v0.2.17](https://github.com/jstevenscl/vod-manager/releases/tag/v0.2.17).

- ✅ Undated cross-provider movie/series cards now inherit a confirmed TMDB
  identity when exactly one normalized-title candidate already exists in the
  pool. This prevents a second provider from creating a duplicate Metadata
  Review row for an already-fixed title; ambiguous candidates remain manual.
  Regression tests cover both safe inheritance and ambiguity protection.

- ✅🔼 Provider-supplied `trailer`/`youtube_trailer` values are now preserved
  during movie and series imports and exposed through Dispatcharr list/detail
  responses. This avoids unnecessary TMDB/YouTube requests and keeps the
  provider's own verified trailer reference. Synthetic movie/series fixtures
  cover persistence and exclusion of already-saved values from the review
  queue. PR [#25](https://github.com/jstevenscl/vod-manager/pull/25) was closed
  because the submitted branch contained the full fork history and unrelated
  files. The functionality was subsequently incorporated in upstream
  [v0.2.17](https://github.com/jstevenscl/vod-manager/releases/tag/v0.2.17)
  without merging that PR.

- ✅ Provider imports now have one shared **Catalog workflow** handoff instead
  of leaving people to infer readiness from separate progress bars. The
  centered header advances through queued import, TMDB identity resolution,
  provider enrichment, and safe duplicate reconciliation; only after every
  automatic phase finishes does it show **Import complete · Catalog ready for
  review**. That ready banner includes the visible (non-adult) movie/TV
  identity-review counts and incorrect-TMDB-ID count. The sidebar now gives a
  clickable review order: Metadata Review, Incorrect TMDB IDs, remaining
  ambiguous duplicates, then missing artwork.

- ✅ Known-TMDB movie cards now receive the same final database collision
  sweep as series. A newly imported movie that already has a valid TMDB ID no
  longer misses auto-merge merely because it did not require provider-detail
  enrichment; the normal same-language and explicit-ignore safeguards still
  apply. This closes the live multi-provider import case where exact-TMDB
  movie pairs remained in Duplicate Finder after all progress bars completed.

- ✅🔼 Provider-free TMDB enrichment for known series IDs now also records TMDB's
  first-air year. A confirmed series no longer remains falsely held in
  **Metadata Review** merely because its provider omitted a year; the existing
  held records are safely picked up and backfilled on the next enrichment run.
  The final series reconciliation also discovers current exact-TMDB-ID
  collision groups directly from the database, so a card created during a
  coalesced import cannot be stranded in Duplicate Finder. It retains the
  existing same-language and explicit-ignore safeguards, so different-language
  variants and human decisions remain untouched. A reviewer-selected TMDB ID
  in Metadata Review now invokes that same safe merge path immediately rather
  than waiting for the next import.
  The submitted PR [#24](https://github.com/jstevenscl/vod-manager/pull/24) was
  closed without a merge commit; this functionality was incorporated, with
  upstream hardening, in
  [v0.2.16](https://github.com/jstevenscl/vod-manager/releases/tag/v0.2.16).

- ✅ Metadata Review now has an **Incorrect TMDB IDs** tab for titles whose
  stored ID receives a confirmed TMDB 404. It supports a pending-ID scan,
  per-title TMDB search and correction/clear actions, and high-confidence
  bulk AI correction. The issue and content-type controls are grouped with a
  plain-language key; adult filtering is shown only for Missing identity and
  states both the hidden-adult and visible-item counts. Adult titles are
  excluded from repeat pending-ID enrichment; Activity and Failed Streams no
  longer crowd the Metadata Review page.

- ✅ Manual Plex, Emby, Jellyfin, and DVR imports now update the shared
  sidebar lifecycle from queued to running and then finished/failed, matching
  XC imports. This makes a queued non-XC import visibly confirm that its
  background worker started instead of appearing to remain idle.

- ✅ Metadata Review now renders its queue in 50-item pages instead of
  mounting every review row at once. This keeps the page responsive when a
  provider has a large adult or unresolved-title queue; switching Movies/TV
  Shows and using Hide adult titles no longer creates thousands of row
  components in one browser frame. Selection is intentionally scoped to the
  visible page.

- ✅ XC provider refreshes now apply a source-level catalog delta after fetching
  the required full upstream snapshot. New, changed, and removed provider
  sources still follow the normal import/reconciliation workflow, but an
  unchanged source is no longer rewritten just to confirm it remains
  available. Smart-category evaluation and post-import enrichment now run
  only when a refresh actually changes the catalog, reducing SQLite writes,
  CPU work, and contention during ordinary daily refreshes.

- ✅ Provider catalog imports now queue in the background instead of holding
  the browser request open for the full catalog pass. Imports are serialized,
  their large record-normalization work no longer occupies the API event loop,
  and post-import enrichment waits until the manual import queue drains. The
  sidebar reports queued/running work, so Metadata Review and other pages stay
  usable while a provider refresh is underway.

- ✅ Provider catalog refreshes now reconcile removed content as well as new
  content: a source that is no longer advertised by a provider is removed,
  while the same movie or series remains available whenever another provider
  still has a source. Stale episode streams are also removed only after that
  provider has no remaining source for the series, preserving valid fallback
  playback. Validated with isolated catalog snapshots covering removed,
  retained alternate-provider, and stale-episode sources, plus a mocked
  provider-import flow; no live provider catalog was modified for the test.

## 2026-09-14

- ✅🔼 **Live on the server (`f0b9c0b`):** The sidebar Status card now
  reports active bulk AI review jobs (for example, `AI review: 13/55`) and
  switches to its live polling interval while they run, instead of incorrectly
  displaying Idle.

- ✅🔼 **Live on the server (`a77d9fc`):** Metadata Review now supports a
  Hide adult titles filter, filtered Select all, Archive selected, and an explicit
  Bulk resolve with AI action for both movies and TV shows. AI runs only on
  the titles the reviewer selected and writes a TMDB ID/year only for a
  high-confidence result; unresolved items remain for manual review. Each row
  also accepts a direct TMDB ID, with an optional year for the safe
  identity/merge path.

- ✅🔼 **Follow-up shipped in beta image (`4db93be`):** Corrected the initial
  Metadata Review filter to show only actionable no-identity records (both
  TMDB ID and release year absent), plus explicitly held ambiguous-year rows.
  A provider omitting only a release year is common and is not a repair queue;
  this prevents a normal catalog from producing thousands of false positives.

- ✅🔼 **Shipped in beta image (`e9c40de`):** Added a dedicated **Metadata
  Review** workspace under Operations, so TMDB
  corrections no longer need to live in Curation or a library modal. It lists
  active movies and TV shows missing both a TMDB ID and release year, plus the
  existing ambiguous-year hold queue. A reviewer searches TMDB and explicitly
  selects the result; that records its ID/year and safely merges
  sources/categories only when the corrected pool identity already exists.
  The queue's selection criteria and existing reconciliation/enrichment
  regressions were validated in 7 automated tests; the frontend production
  build also passed. Browser validation reached the first-run screen from a
  static build; the authenticated, data-backed queue must be checked after
  deployment.

- ✅🔼 **Shipped in beta image (`245f6a0`):** The sidebar now includes a compact
  live Status card below Configuration. It reports the importing provider,
  TMDB/enrichment progress, idle state, and app-process CPU sampling without
  requiring users to leave their current page. Python compilation, 6 focused
  backend regression tests, and the frontend production build passed; live
  workload states require an actual import/enrichment run to observe.

- ✅ Imports now run a TMDB-first canonical metadata pass for series with an
  imported TMDB ID before provider episode discovery. It uses one bounded,
  batched TMDB lookup per canonical series to set the user-visible TMDB title
  and US content rating, while retaining every provider's original title in
  its source row. Provider suffixes therefore stay available for provenance
  without replacing clean card titles, and the existing language-aware merge
  guard still keeps correctly classified EN/ES/IT siblings separate.

- ✅🔼 Bulk enrichment now divides its request-concurrency budget among only
  providers that actually have pending movies or series sources. Previously,
  empty configured providers could consume a fairness share: with five
  configured providers and only one needing work, an 8-request budget was
  reduced to one request at a time. Active providers still retain their own
  adaptive rate limiter, backoff handling, and isolated movie-then-series
  lanes.

- ✅🔼 Fixed automatic startup recovery for pending series episode discovery
  after the active-provider concurrency change. Providers with already
  completed or review-excluded series no longer count as pending work; the
  remaining source-level episode work resumes normally after a restart.

- ✅🔼 Automatic series episode discovery now tracks and processes every
  retained source variant, rather than stopping after the first source on a
  canonical series card. This preserves episode-stream fallbacks when one
  provider supplies multiple variants of the same show, and the progress
  counter now reflects pending sources rather than only canonical titles.

- ✅🔼 The Curation page now notices the automatic handoff from the TMDB-ID
  metadata pass to provider fallback/series episode work without requiring a
  manual browser refresh. While idle it checks for server-started enrichment
  every 10 seconds, then returns to its existing 2-second live progress
  updates once work begins.

- ✅ Bulk movie-enrichment writes now commit up to 250 completed movies per
  SQLite transaction (previously 25). The single global writer, FIFO queue,
  per-item savepoints, and bounded transactions remain in place, reducing
  commit/fsync overhead on large imports without allowing concurrent database
  writes or holding one catalog-sized transaction open.

- ✅ Imports now queue a provider-free TMDB metadata pass for movies that
  already include a TMDB ID in the catalog list. It has its own visible
  progress indicator and batch-writes results to reduce database contention.
  Provider detail calls are deferred to genuinely unmatched new movies, while
  series detail remains dedicated to episode discovery. Normal catalog
  refreshes no longer re-fetch stable movie metadata or previously discovered
  episode lists merely because a timer elapsed.

- ✅🔼 XC movie catalog imports now retain the provider's bulk artwork URL
  (`stream_icon`) immediately, matching the existing series-cover behavior.
  Movie cards no longer need an expensive per-title enrichment request merely
  to display a poster; enrichment and TMDB remain fallbacks for missing or
  improved artwork. The importer keeps the first usable poster for a
  canonical movie, so alternate source variants cannot cause artwork to
  flip on later refreshes.
  [#23](https://github.com/jstevenscl/vod-manager/pull/23); the submitted PR
  was closed without a merge commit and the functionality was incorporated in
  upstream [v0.2.17](https://github.com/jstevenscl/vod-manager/releases/tag/v0.2.17).

- ✅ Bulk enrichment no longer creates a task for every movie/series in a
  provider's catalog up front. It used to launch all of them at once (a
  full-catalog provider could mean tens of thousands queued simultaneously)
  even though only a handful actually run at a time — the rest just sat in
  memory adding scheduling overhead. Enrichment now uses a fixed-size pool
  of workers (matching the existing concurrency limit) that pull items one
  at a time from a queue. Same enrichment speed and same number of items
  running at once, just without the up-front pile-up.

- ✅ Fixed bulk enrichment writing every movie's enrichment result to the
  database in its own transaction, which could stall other providers'
  enrichment lanes with "database is locked" errors during a full bulk run.
  Movie writes are now batched (25 per transaction) instead of one write per
  movie. Verified with a full-catalog live dry-run (56,978 movies, 5
  providers, concurrency 8): zero lock errors, zero enrichment errors.
- ✅🔼 Fixed bulk series enrichment silently under-processing a provider's
  series: a newly imported series wasn't selected for that provider's
  enrichment phase until it had already been enriched by that provider at
  least once, which meant series that most needed enrichment could be
  permanently skipped by every bulk run. The per-provider series list now
  uses the provider-membership data recorded at import time instead of
  requiring prior episode data to already exist.
- ✅🔼 Fixed bulk enrichment's end-of-run duplicate-merge sweep spiking host
  CPU to 1200%+ (near-total saturation on a 14-core host) for the duration
  of the sweep. It was launching one background thread per affected title
  instead of merging sequentially, which added no real speed (every merge
  already had to wait its turn for the database anyway) but generated heavy
  thread-scheduling overhead at full-catalog scale. Merges now run
  sequentially in a single background task; total merge sweep work is
  unchanged, just without the thread pile-up.
- ✅🔼 Fixed a provider's bulk series-enrichment lane also fetching series
  metadata from OTHER providers whenever a series was carried by more than
  one provider (e.g. matched by name/year across two catalogs). This
  weakened each provider's intended request/concurrency isolation and
  backoff handling during a bulk run. Each provider's lane now fetches only
  its own series source.
- ✅🔼 Bulk enrichment now serializes every movie/series database write for
  the whole run through one background writer task instead of each
  provider's movie or series phase independently reaching its own
  batch-commit point. Since different providers' phases run concurrently by
  design, two providers could previously flush to SQLite at the same
  instant; now only one write is ever in flight at a time, regardless of
  how many provider lanes are enriching concurrently. Single/on-demand
  enrich calls outside a bulk run are unaffected.
- ✅🔼 Pooled per-provider HTTP connections are now explicitly closed at
  application shutdown, and whenever a provider is deleted or its connection
  settings (base URL, username/password, custom user agent) change. Before,
  a stale pooled connection could keep being reused under old credentials
  (or against a provider that no longer exists) until an unrelated failure
  happened to evict it, which might never happen for a deleted provider.

## 2026-09-13

- ✅🔼 Fixed a regression (introduced earlier today) where the automatic
  TMDB-ID merge could merge a movie or series with its different-language
  sibling (e.g. an EN card and its ES card) whenever that other language
  wasn't in your enabled playback languages. This is what was causing the
  "Movie language split" maintenance tool to keep finding thousands of
  movies to fix every single day even after running it — the auto-merge was
  quietly re-merging them right back. Existing content that was already
  incorrectly merged by this bug is not automatically un-merged; use the
  Duplicate Finder / language-split maintenance tool to split any titles
  that still show up mixed-language after updating.
  ([#21](https://github.com/jstevenscl/vod-manager/pull/21))
- ✅🔼 Movies/series whose content isn't in any of your enabled playback
  languages are now automatically archived (not deleted) instead of just
  quietly hidden from playback while still showing up everywhere else.
  This is a one-time catch-up for anyone who was already running before
  today's language-merge fix above — those titles had been accumulating
  without ever getting flagged for review. Runs automatically after each
  provider scan; re-enabling a language later automatically un-archives
  anything that qualifies again. A title you've manually archived or
  unarchived yourself is never touched by this.
  ([#22](https://github.com/jstevenscl/vod-manager/pull/22))
- ✅🔼 Movies and series that end up sharing the same TMDB ID after enrichment
  are now merged automatically, instead of sitting side-by-side as duplicates
  until someone merges them by hand in the Duplicate Finder.
  ([#20](https://github.com/jstevenscl/vod-manager/pull/20))
- ✅🔼 Series metadata lookups can now fail over between multiple providers
  instead of giving up when the primary provider doesn't have a match, the
  same way movie lookups already could.
  ([#19](https://github.com/jstevenscl/vod-manager/pull/19))

## 2026-09-10

- ✅🔼 Fixed a crash (`FOREIGN KEY constraint failure`) that could occur when
  auto-merge encountered a cycle of duplicate rows all sharing the same TMDB
  ID during a batch merge.
  ([#18](https://github.com/jstevenscl/vod-manager/pull/18))
- ✅🔼 Fixed archived movies/series occasionally re-appearing in normal category
  listings after being archived.
  ([#17](https://github.com/jstevenscl/vod-manager/pull/17))

## 2026-09-09 – 2026-09-10

- ✅🔼 Duplicate Finder: fixed matches being missed when one of the two
  candidate rows has no release year, and fixed a blank `()` showing in the
  UI when a candidate has no year.
  ([#16](https://github.com/jstevenscl/vod-manager/pull/16))
- ✅🔼 Duplicate Finder: improved name normalization to correctly strip
  language/quality prefixes (e.g. `FR -`, `RU -`) and country suffixes before
  comparing titles, so more real duplicates are found and fewer false
  positives are flagged.
  ([#16](https://github.com/jstevenscl/vod-manager/pull/16))
- ✅🔼 Fixed a rare false-archive of French/Russian-prefixed titles caused by
  the dash-prefix detector, and added a guard against hitting TMDB's rate
  limit during bulk lookups.
  ([#14](https://github.com/jstevenscl/vod-manager/pull/14))

## 2026-09-08

- ✅🔼 Added a "Bulk Apply TMDB Titles" action, plus better progress/resume
  visibility and clearer error reporting during bulk operations.
  ([#13](https://github.com/jstevenscl/vod-manager/pull/13))
- ✅🔼 Raised TMDB year-lookup concurrency for faster bulk enrichment.
  ([#12](https://github.com/jstevenscl/vod-manager/pull/12))
- ✅🔼 Fixed high CPU usage during import and improved movie/series duplicate
  matching accuracy.
  ([#11](https://github.com/jstevenscl/vod-manager/pull/11))
- ✅ Reused persistent HTTP connections for provider/TMDB calls, raised TMDB
  request concurrency further, and added automatic backoff when TMDB starts
  rate-limiting.

## Earlier

Everything before 2026-09-08 predates this changelog. See the git history for
the full record.
