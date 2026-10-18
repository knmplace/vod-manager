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

## 2026-10-18 (Radarr/Sonarr library handoff — backend)

- ✅ **Finished downloads can be handed to Radarr/Sonarr, so they land in
  Plex the normal way.** Off until a Radarr and/or Sonarr URL + API key are
  saved; nothing changes for existing setups. Backend only in this build (the
  settings card, import chips and notice bell come next), configured through
  the new API below.
  - **When a download is queued**, the movie or show is looked up in
    Radarr/Sonarr by TMDB id and added if missing, with no search: new movies
    unmonitored, new shows monitored for future episodes (both configurable).
    Titles with no match are marked for manual adding and picked up again
    once you add them yourself.
  - **When the download finishes**, vod-manager watches the finished folder
    (an encoder's output such as Tdarr's, or the download folder itself) for
    the file, which may have a new extension. Once the file has stopped
    growing for 60 s it asks Radarr (movie folder) or Sonarr (episode file)
    to import it, then confirms the import took. A rejection shows
    Radarr/Sonarr's own reason, e.g. a custom-format score.
  - **Stalled files**: if the file never reaches the finished folder, a notice
    fires at 4, 8 and 16 h (configurable) and the import is marked failed at
    24 h with the likely cause: still in the download folder (encoder hasn't
    finished) or nowhere (encoder failed or moved it). Notices stay until
    acknowledged and are also emailed when SMTP is set up.
  - API: `GET/POST /vod/handoff/settings/`, `POST /vod/handoff/test/{radarr|sonarr}`
    (connection check, returns root folders and quality profiles),
    `POST /vod/downloads/{id}/retry-import/`, `GET /vod/notices/`,
    `POST /vod/notices/{id}/ack/`. Download jobs gain `import_status` /
    `import_note`.
  - Before: a finished download stopped in the download folder (or the
    encoder's output folder). Radarr/Sonarr never knew about it, so it had
    to be moved into the library by hand. After: Radarr/Sonarr import it into
    their library folders, tell Plex, and keep tracking future episodes of a
    new show.

## 2026-10-18 (Download folders without the TMDB id)

- ✅ 🔀 [#58](https://github.com/jstevenscl/vod-manager/pull/58) **Downloads can leave the TMDB id out of folder names.** A new
  **TMDB id in folder names** checkbox in Configuration → Downloads (on by
  default, so nothing changes unless you turn it off). Off saves to
  `Title (Year)/Title (Year).mp4` and `Show (Year)/Season NN/…` instead of
  `Title (Year) [tmdbid-N]/…`. File names never included the id. The .strm
  export keeps its own naming.

## 2026-10-18 (Synced with upstream v0.3.03)

- 🔼 **Upstream v0.3.01 – v0.3.03 merged; the fork now reports version 0.3.03.**
  New from upstream: a **No TMDB ID** filter and select-all-filtered; Select
  all/none in category access; **automatic TMDB episode titles** (hourly,
  opt-in per series); one-click **genre categories**; **remove titles from a
  category**, and the removal sticks; bulk AI explains why items were skipped;
  List Sync in the category schedule dropdown; and opt-in **Downloads** into
  a movies/TV library folder (off by default), with optional re-encoding,
  GPU encoders, a CPU thread cap, and a processing folder so unfinished files
  never land in the library. The image now includes `vainfo` and the Intel
  media driver. Our open upstream PRs (#53–#56) are not part of these releases
  and stay in the fork as before.
- ✅ 🔀 [#57](https://github.com/jstevenscl/vod-manager/pull/57) **Automatic episode titles use the local TMDB library first.** Each pass
  fills placeholder episode names from the local TMDB library, and asks TMDB
  only for names still missing after that. A series the library already covers
  costs no TMDB request, not even the daily refresh of the newest season.
  "Run now" shows how many series were filled locally.

## 2026-10-15 (Archived movies get their TMDB year)

- ✅ 🔀 [#56](https://github.com/jstevenscl/vod-manager/pull/56) **Archived movies now show their year too.** The startup fix that gives
  held, yearless movies their year from the TMDB release date skipped movies
  archived by language or import rules, so they showed a blank year under
  **Show archived** and would come back still held if restored. They are now
  fixed the same way and stay archived.

## 2026-10-14 (TMDB library keeps popular titles)

- ✅ 🔀 [#55](https://github.com/jstevenscl/vod-manager/pull/55) **The TMDB library also stores the most popular TMDB titles.** It used to
  store only titles already in your catalog, so every newly imported title
  cost a TMDB call, even blockbusters. After your catalog, fill bursts now
  also fetch the top **Popular titles to keep** movies and TV shows from
  TMDB's daily export (default 25,000 of each; adult titles are never
  included; 0 = catalog only). New drops are then usually local already.
- ✅ 🔀 [#55](https://github.com/jstevenscl/vod-manager/pull/55) **Titles leaving the catalog are kept until the cache limit.** The daily
  cleanup deleted any title no longer in the catalog, so one that dropped out
  and came back was fetched again. Stored titles now stay until the 170-day
  cache limit, which still keeps the library inside TMDB's six-month rule.
- ✅ 🔀 [#55](https://github.com/jstevenscl/vod-manager/pull/55) **The library file is compacted.** Deletes left free space in the file
  that was never given back (about half of it on a long-running install).
  The daily cleanup now compacts the file when more than a quarter is free.

## 2026-10-14 (Metadata Review count and held movies)

- ✅ 🔀 [#54](https://github.com/jstevenscl/vod-manager/pull/54) **TMDB library jobs report their result.** "Run fill burst now", "Check
  TMDB changes" and "Refresh TMDB ID list" run in the background and showed
  nothing when done, so a burst with nothing to fetch looked like the button
  did nothing. Each job now shows a toast and a "Last ..." line with what it
  did, e.g. "nothing to fetch — every catalog title is stored and up to date".
- ✅ 🔀 [#56](https://github.com/jstevenscl/vod-manager/pull/56) **Movies held for a year review now take their year from TMDB.** A
  movie matched to TMDB but held because its year was unknown never got the
  year from TMDB's release date (TV shows already did). It stayed held out of
  every category, so XC players never saw it, and it was missing from Metadata
  Review too. Enrichment now fills in the year and releases the hold, and
  movies already affected are fixed automatically at startup.
- ✅ **Metadata Review lists TMDB-matched titles that still have no year.**
  If TMDB itself has no date (e.g. a show with no first air date), the title
  now appears in Metadata Review so you can set the year by hand.
- ✅ **The "Metadata Review (N)" button count matches the page.** It counted a
  different list, so it could show "(1)" over an empty page. It now uses
  the same list as the page and follows its "Hide adult titles" setting.
- ✅ **Language detection reads tags from the provider category too.**
  Import, Language Backfill and Language Recompute only looked at the title,
  so a title in a category like "CRUNCHYROLL SERIES (MULTI-SUBS)" was stored
  as English. Running Language Recompute once fixes existing rows. Upstream
  already behaved this way.

## 2026-10-14 (Updated to upstream v0.3.00)

- ✅ 🔼 **The fork now includes upstream release
  [v0.3.00](https://github.com/jstevenscl/vod-manager/releases/tag/v0.3.00)**,
  and the version shown in the app is now 0.3.00. v0.3.00 ships this fork's automatic TMDB matching
  ([#48](https://github.com/jstevenscl/vod-manager/pull/48)) and local TMDB
  answer cache ([#49](https://github.com/jstevenscl/vod-manager/pull/49)), plus
  upstream's fix for the series language split reported from this fork (GH#52).
  It also brings:
  - **.strm export** of the curated library for Emby/Jellyfin (Configuration >
    Emby / Jellyfin Library).
  - **TMDB episode titles per series** (fill placeholders or replace all). A
    renamed or hand-edited episode name is no longer reverted by a provider re-sync.
  - **Providers can be added inactive** (the default), so nothing imports
    before Exclude Categories is set. The Catalog status card names every
    active provider whose last import failed.
  - **MULTI-LANG / MULTI-SUB content** is its own language. Language filters
    never hide it, and it can merge with any language.
  - An Emby-type provider that is really Jellyfin 12.1 (no `/emby` alias) now
    plays and shows posters.
  - Gemini Flash-Lite model option; the Gemini key no longer appears in logs.
  - Bulk TMDB episode titles, MDBList Lists section, per-category schedule
    picker for list categories, and an All categories dropdown on Movies/TV Shows.
  - Every database connection is closed even when a write fails, so one
    failed write can no longer leave the database locked.
- **How the fork merged it:**
  - The fork's own database code was kept as the base, and upstream's
    functional changes were added to it (episode name lock, failed-import list,
    Jellyfin path flag, MULTI language, provider active flag on sources).
  - Upstream's connection cleanup was applied to the fork's code the same way.
  - The fork's TMDB retention preview and import-policy preview/apply screens
    are kept. The failed-import message appears in the fork's catalog panel.
  - The TMDB library now refreshes changed titles before filling missing ones
    (upstream's order). This replaces the fork's missing-first order.
- **Verification:** full backend suite: 704 passed, 2 skipped (upstream's own new
  tests included); `tsc` clean; frontend build OK.

## 2026-10-14 (Metadata Review picks and enrichment Stop)

- ✅ **A Metadata Review TMDB match with no release year can be selected.**
  TMDB has no year yet for some new or unreleased titles, and their candidate
  card was greyed out. Selecting it now sets the TMDB ID, the same as entering
  the ID by hand, and clears the item from review. Bulk AI resolve does the same
  for a confident yearless match, which it used to skip.
- ✅ **Stop works during the end of an enrichment run.** The duplicate-merge
  passes that run after enrichment ignored Stop, and a large run could only be
  ended by restarting the container. They now stop after the item in progress.

## 2026-10-13 (Updated to upstream v0.2.26)

- ✅ 🔼 **The fork now includes upstream releases [v0.2.25](https://github.com/jstevenscl/vod-manager/releases/tag/v0.2.25) and
  [v0.2.26](https://github.com/jstevenscl/vod-manager/releases/tag/v0.2.26).** v0.2.25 shipped three of this fork's
  PRs: Sync History ([#35](https://github.com/jstevenscl/vod-manager/pull/35)),
  the excluded-category skip, preview and cleanup flow
  ([#39](https://github.com/jstevenscl/vod-manager/pull/39)), and the opt-in local
  TMDB library ([#47](https://github.com/jstevenscl/vod-manager/pull/47)). It also
  fixed the Providers page series count for freshly imported providers.
  v0.2.26 brings:
  - MDBList lists are no longer cut off at 500 items.
  - Large list syncs no longer freeze the app.
  - TMDB charts (Top Rated, Popular and others) can be used as List Sync sources.
  - The MDBList API key is hidden in the logs.
- ✅ **Metadata Review stays fast with the new TMDB ID indexes.** v0.2.26 adds
  an index on `tmdb_id`, and SQLite started using it for the review list
  query. That index matches every unenriched row, so the review list would
  have slowed down. The query now keeps using the small review indexes.
- ✅ **Language split tools use upstream's version.** Split Movies / Split Series
  preview and apply now use upstream's implementation. The series split keeps
  the fork's episode handling: when one provider carries both languages, each
  episode goes to the matching language's card. Upstream moves every episode
  from that provider to the new card.
- ✅ **"Archive new categories" works as upstream ships it again.** New
  categories are stored separately as auto-archived instead of being written
  into your saved exclusion list (this replaces the 2026-10-05 change). Their
  content is imported archived. Categories that the old behaviour added to
  your saved exclusions stay there until you remove them.
- ✅ **Movie enrichment counts unchanged re-fetches** (upstream's backoff
  counter). The fork still never re-polls an enriched movie on a timer.
- **Deliberate differences from upstream** (unchanged by this update):
  - The fork's post-import pipeline is kept instead of upstream's known-series
    identity reconciliation.
  - Bulk enrichment never calls your providers for episodes, so a newly added
    provider's episodes are fetched alone.
  - Our fuller Sync History is kept (per-item events, Movies/Series tabs, deleteable reports).
- 🔼 [#48](https://github.com/jstevenscl/vod-manager/pull/48) and
  [#49](https://github.com/jstevenscl/vod-manager/pull/49) were rebuilt on
  v0.2.26 and shipped in upstream v0.3.00.
- **Verification:** full backend suite: 642 passed, 2 skipped (upstream timed
  movie re-poll tests); upstream's own v0.2.26 tests were also run against the
  fork code and every difference is explained above; `tsc` clean.

## 2026-10-11 (Fewer provider calls, language tools by source language, TMDB library opt-in)

- ✅ **Bulk enrichment no longer calls your providers for episodes.** A
  scheduled or manual "enrich all" used to request every show's episode list
  from the provider (~10,000 calls in one run on the test bed). Episodes now
  come only from opening or playing a show, the **Fetch Episodes** button, and
  the paced background episode trickle. Bulk enrichment stays local
  (Plex/library/TMDB).
- ✅ **Import Language exclusions work as a real policy.** Excluding an import
  language now archives cards whose every source is in an excluded language,
  independent of Playback Languages. **Re-apply** previews the exact
  archive/restore counts first and only touches archives it created; sources
  are never deleted and manual archives are left alone. The result also
  reports how many cards were **already archived**, so a re-run that changes
  nothing no longer looks like it did nothing.
- ✅ **Sync History is sturdier and easier to manage.** Run records are written
  without blocking imports, interrupted runs close cleanly after a restart, and
  a new **select-all** checkbox selects every report at once.
- ✅ **Excluded-category cleanup previews the change before saving.**
- ✅ **Language tools read each source's real language.** Title & Metadata
  Rules strip prefixes such as `ES|` from card names, which made the Import
  Language picker, the Library language filter, the Missing Artwork language
  filter and Smart Exclude treat almost everything as English. They now use
  each source's stored language, the picker always offers every known code
  (plus a custom code), and Smart Exclude judges sibling cards by their
  sources.
- ✅ **The local TMDB library is now opt-in.** New installs start with it off.
  While it is on, the daily TMDB ID list download keeps running so local name
  matching stays current; while it is off, nothing is downloaded. Existing
  installs that saved the setting as on keep it on. The "Pre-fill top N"
  setting was removed: the library fills only from titles in your catalog.
  This change is also on upstream PR
  [#47](https://github.com/jstevenscl/vod-manager/pull/47).
- **Verification:** full backend suite: 603 passed; frontend production build
  passed.

## 2026-10-10 (Updated to upstream v0.2.24)

- ✅ **Playback-language inventory is easier to scan.** The playback picker is
  wider, shows language codes only (the full name remains available as a
  hover label), and keeps movie/show/episode counts together without crowding.
  Its helper text now distinguishes stored source records from active catalog
  cards: unchecked-language-only cards are archived, while alternate disabled
  sources remain stored for safe review or later re-enabling.
- 🔼 **Upstream PR [#35](https://github.com/jstevenscl/vod-manager/pull/35) was
  rebuilt as a small Sync History lifecycle proposal** (shipped upstream in
  [v0.2.25](https://github.com/jstevenscl/vod-manager/releases/tag/v0.2.25)). It now records concise,
  durable start/finish summaries for each catalog import and closes interrupted
  runs after a restart. The proposal deliberately does not change country
  exclusions, Metadata Review performance queries, enrichment/language rules,
  Duplicate Finder, or reconciliation behavior; those need separate reviewable
  follow-ups. The fork keeps its own fuller Sync History (per-item change
  events, Movies/Series tabs, deleteable reports).

- ✅ 🔼 **The fork now includes upstream releases v0.2.21 through v0.2.24.**
  This brings in the vanished-item transaction fix, Jellyfin 12.1 authentication
  and native playback paths, TMDB attribution, repaired ongoing-series episode
  refreshes, enrichment scheduling/backoff, and the Gemini compatibility and
  error-reporting fixes.
- ✅ **New provider lanes are fetched before broad series rechecks.** If an
  existing show gains another provider, only that provider's missing episode
  list is requested first. Existing provider lanes are refreshed later when
  their own change signal or fallback interval is due.
- ✅ **Language cleanup only restores its own archives.** Re-enabling a language
  cannot unarchive a title that was archived manually or by category cleanup.
- ✅ 🔼 **Saved excluded categories are skipped without a delete/recreate
  cycle.** Catalog refreshes no longer import and purge the same excluded XC
  titles every run. Import results now report how many movie and series rows
  were skipped. Shipped upstream in [v0.2.25](https://github.com/jstevenscl/vod-manager/releases/tag/v0.2.25) via [#39](https://github.com/jstevenscl/vod-manager/pull/39).
- ✅ 🔼 **Excluded-category cleanup is preview-first.** Saving XC exclusions
  shows exact affected source/card counts and sample titles. Existing stored
  content is deleted only after **Apply cleanup** is clicked; scheduled imports
  never run that destructive cleanup automatically. Cards with another source
  and manually curated cards remain protected.
- ✅ **The local TMDB library now follows the current catalog.** Its daily
  retention pass removes title details and season data that are no longer tied
  to a movie or show in this database, plus ephemeral non-empty search answers
  and unreferenced missing-title markers. Referenced titles are refreshed after
  150 days and no cached TMDB response is served at 170 days, safely inside
  TMDB's six-month maximum.
- ✅ **TMDB retention is previewable before a manual cleanup.** The TMDB Library
  page reports exactly how many referenced, unreferenced, expired, season,
  search, and missing-marker rows would be affected. **Apply retention cleanup**
  requires confirmation; the same policy runs automatically once per day.
- ✅ **Background TMDB fill is catalog-first.** Fill bursts request only current
  movie/show TMDB IDs that are missing, changed, or due for refresh. The daily
  ID/name export remains a freshly replaced matching index; unrelated popular
  title details are no longer pre-fetched.
- ✅ **Archived or settled titles no longer linger as approvals.** Auto-match
  decisions are now cleared whenever a title is archived, assigned a TMDB ID,
  merged, or deleted; startup also repairs old orphaned decisions. Archive and
  merge actions refresh every approval/review view immediately, so an archived
  duplicate cannot remain visible until a page reload.
- ✅ **Enabled Playback Languages now cleans up immediately.** Its dry-run
  confirmation reports both playback impact and the exact cards that would be
  language-archived or restored. Saving applies only that language-owned
  archive state, so unwanted-language cards leave active library/review views
  immediately while a later re-enable restores them safely.
- âœ… **Language changes now always require approval.** Enabling or disabling a
  playback language shows the same impact confirmation, with playback records
  clearly distinguished from review cards that would be language-archived or
  restored. Saving import-language or country exclusions now also asks for
  confirmation and states that those rules affect future imports only.
- âœ… **Improved dark-theme readability.** Muted helper text and sidebar labels
  are brighter across the built-in themes.
- âœ… **Playback-language counts now match playback.** The picker reports
  computed source-language inventory for active providers (movies, shows, and
  episodes separately), including provider tags such as `(ES)`, instead of
  incorrectly treating only raw `ES|` title prefixes as Spanish content.
- **Verification:** full backend suite: 565 passed; frontend production build
  passed (the existing large-chunk warning remains).

## 2026-10-07 (No episode fetches for languages you've turned off)

- ✅ **Episode lists are fetched only for sources in an enabled playback
  language.** When a show stayed visible because of an English source, its
  copies in disabled languages (for example a provider's Spanish "ES -"
  version) were still queued for an episode-list fetch. Playback filters those
  sources out, so each fetch was a wasted provider call. They're now skipped
  and no longer counted in the "Episode sources" progress. Turning a
  language back on queues them again.

## 2026-10-07 (Plex, Emby, Jellyfin and folder imports show their changes)

- ✅ **Sync History counts changes from Plex, Emby, Jellyfin and folder
  library imports.** These imports never reported which titles they added or
  changed, so a run that picked up new episodes showed "0 changes". They now
  report new titles, new episodes, replaced files, and detail or archive
  changes. Re-imports where nothing changed still show 0.
- ✅ **Follow-up work after these imports covers only what changed.** TMDB
  details and smart-category updates are now limited to the changed titles,
  as they already were for Xtream providers. A folder library import that
  removed files still updates all categories.
- ✅ **A file replaced under the same name counts as a change.** For example,
  a quality upgrade that keeps the filename, on a local folder, NFS/CIFS mount
  or rclone remote (SMB, SFTP, cloud), or in Plex, Emby or Jellyfin.

## 2026-10-07 (Local TMDB name search is fast again)

Shipped in upstream [v0.3.00](https://github.com/jstevenscl/vod-manager/releases/tag/v0.3.00). Added to upstream PR [#49](https://github.com/jstevenscl/vod-manager/pull/49).

- ✅ 🔼 **Matching titles without a TMDB ID no longer stalls.** Each name search
  in the local TMDB library was taking about 35 seconds once it held ~200K
  names, so automatic matching managed only about one title every 30 seconds.
  The search now takes milliseconds.

## 2026-10-06 (TMDB answers cached locally)

Shipped in upstream [v0.3.00](https://github.com/jstevenscl/vod-manager/releases/tag/v0.3.00). Proposed upstream as a standalone PR,
[#49](https://github.com/jstevenscl/vod-manager/pull/49), built on #48.

- ✅ 🔼 **Repeated questions are answered from the short-lived local cache.** Name searches and IMDb
  lookups made by automatic matching, library import, Metadata Review and the
  TMDB Library page are now saved in the local TMDB library. Asking again is
  answered locally and counts as a local lookup, not a TMDB request, until the
  daily catalog-first retention pass clears non-empty search responses.
- ✅ 🔼 **"Nothing found" is remembered for 7 days**, then TMDB is asked again.
- ✅ 🔼 **Search results are saved in full.** Full details for the top 5 results
  of each search are stored until the daily retention pass, so immediate repeat
  work can reuse them without retaining unrelated results long-term.
- ✅ 🔼 **TMDB list sync saves the titles it returns.** List contents are still
  checked live.

## 2026-10-05 (Automatic TMDB matching for titles without an ID)

Shipped in upstream [v0.3.00](https://github.com/jstevenscl/vod-manager/releases/tag/v0.3.00). Proposed upstream as a standalone PR,
[#48](https://github.com/jstevenscl/vod-manager/pull/48), built on #47 (it
needs the local TMDB library).

- ✅ 🔼 **Titles without a TMDB ID are matched automatically.** After each fill
  burst (or when you click "Match titles without a TMDB ID"), up to 2,000
  catalog titles without an ID are matched by name and year. Series are matched
  first. The local TMDB library is checked first, and TMDB is searched only if
  it has no match. A match is applied the same way a reviewer would apply it,
  so cards for the same show from different providers merge into one.
- ✅ 🔼 **Unclear results go to Metadata Review.** The title stays visible while
  it waits there, and nothing is guessed. Unclear means more than one possible
  match, a year that doesn't agree with TMDB's, or no year when TMDB has other
  titles with the same name. Titles TMDB doesn't know are tried again a week
  later.
- ✅ 🔼 **Local hit rate.** The TMDB Library page shows how many of today's
  lookups were answered locally.
- **Tests:** 13 new tests. Full backend suite: 487 passed. Frontend build is
  clean.

## 2026-10-05 (Local TMDB library)

Proposed upstream as a standalone PR,
[#47](https://github.com/jstevenscl/vod-manager/pull/47), based on current
upstream `main` and independent of #35. Shipped upstream in [v0.2.25](https://github.com/jstevenscl/vod-manager/releases/tag/v0.2.25).

- ✅ 🔼 **TMDB lookups are saved locally and reused.** Once a TMDB API key is
  set, every title the app looks up is stored in `data/tmdb.sqlite` and served
  from there next time. This covers enrichment, Metadata Review search, AI
  resolve candidates, library matching and episode lists. Name searches use
  the local copy only when it finds an exact title match; anything else still
  goes to TMDB.
- ✅ 🔼 **Background fill.** Current catalog titles that are missing, changed,
  or aging are fetched in small bursts (defaults: 2,000 × 4 bursts a day,
  20,000 requests/day cap, 4 at a time). TMDB's change feed keeps stored titles
  current.
- ✅ 🔼 **TMDB Library page** under Curation & Maintenance shows:
  - store status
  - fill settings
  - a lookup box
  - a Clear button
- ✅ 🔼 **On/off switch, off by default** (changed 2026-10-11). Off stops the
  fill and the daily ID list download, and sends every lookup straight to
  TMDB, as before. The existing file stays until you clear it.
- ✅ 🔼 **Shared toast messages.** "Settings saved" and future confirmations
  use one reusable toast component.
- **Disk usage.** Measured on the test bed: TMDB's ID lists (~1.4M IDs) are a
  fixed ~143 MB, and each stored title adds about 6 KB. Since 2026-10-11 the
  library fills only from titles in your catalog (the "Pre-fill top N" option
  was removed), so size tracks your library rather than TMDB's top lists.
- **Tests:**
  - 36 new tests cover the store, the fill and the on/off routing
  - full backend suite: 251 passed on the upstream PR branch
  - frontend build is clean
  - live: the first fill run stored ~2,000 titles, and lookups were then
    served locally; with the switch off they went to TMDB.

## 2026-10-05 (Auto-merge same TMDB ID up to 2 years apart)

All four entries below are proposed upstream as a follow-up commit on
[#35](https://github.com/jstevenscl/vod-manager/pull/35), which introduced the exact-year gate.

- ✅ ⛔ **Cards with the same TMDB ID now auto-merge when their years differ by
  1 or 2.** Providers often list a festival or regional year, which left the
  same film as two cards (e.g. *All Roads to Pearla* 2019 / *Sleeping in
  Plastic* 2020). A shared source language is still required, and gaps of 3+
  years stay for manual review.
- ✅ ⛔ **Duplicate Finder explains each group.** A line under the badges says
  why the cards were not auto-merged: no TMDB ID, different TMDB IDs, no
  shared language, years too far apart, auto-merge turned off, or that the
  group qualifies and merges on the next refresh.
- ✅ ⛔ **Year gap is adjustable.** Settings → Duplicate Finder has a 0–3 year
  dropdown (default 2; 0 = exact year only). Lowering it later does not split
  cards that already merged.
- ✅ ⛔ **"Merge existing duplicates now" button.** Automatic merges only
  re-check cards an import or refresh touched, so pairs that already qualify
  can sit split. The button runs the same auto-merge (same language and year
  rules) across the whole catalog once. Merges can't be undone, so download a
  database backup first. On the test bed it merged 219 movies and 26 TV shows,
  taking Duplicate Finder from 381 movie groups to 169.

## 2026-10-05 (Newly discovered categories stay excluded)

- ✅ (Replaced 2026-10-13 by upstream's auto-archived model.) **"Archive new categories" now keeps a new category excluded.** A
  category first seen on an import was only excluded for that one run; the
  next import imported its content as active. New categories are now added
  to the provider's saved category exclusions, where you can untick them to
  import. A provider's very first import no longer excludes every category.

## 2026-10-04 (Historical upstream PR consolidation)

- **Superseded plan.** An earlier broad rebuild placed import reporting,
  staged TMDB/episode workflow, episode preloading, artwork fingerprints, and
  load-on-open work under [#35](https://github.com/jstevenscl/vod-manager/pull/35).
  That scope was subsequently replaced by the focused Sync History lifecycle
  proposal documented above. The other work must be proposed again in separate
  current-upstream PRs; this historical entry is retained only to explain why
  #31, #43, #44, and #45 were closed at the time. Entries that pointed at the
  old #35 scope are now marked ⛔ (not upstream; fork only until re-proposed).

## 2026-10-04 (Excluded-category purge review fixes)

- ✅ 🔼 **The excluded-category cleanup now uses only your saved exclusion
  list.** Follow-up to the review of
  [#39](https://github.com/jstevenscl/vod-manager/pull/39). Categories that
  "archive new categories" flags for one run are no longer treated as
  excluded by the cleanup, so their content isn't deleted.
- ✅ 🔼 **The cleanup logs a warning summary** with counts and example titles
  every time it removes content during an import.
- ✅ 🔼 **The cleanup preview/apply endpoint is XC-only.** Plex, Emby and
  library providers get an error instead of risking removal of
  uncategorized content.

## 2026-10-04 (Artwork changes no longer count as catalog changes)

- ✅ ⛔ **New posters from a provider no longer count as catalog changes.**
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
- ✅ ⛔ **Opening a show loads its missing episodes.** Proposed upstream in
  [#35](https://github.com/jstevenscl/vod-manager/pull/35) (originally [#45](https://github.com/jstevenscl/vod-manager/pull/45), closed as superseded).
  Imports no longer wait on an episode-sync phase; the background preloader
  fills episodes over time, and opening a show fetches any provider that
  has none yet, even when another provider already supplied some.

## 2026-10-04 (Episode list preloading settings)

- ✅ ⛔ **Episode lists preload about 3x faster, still gently.** Proposed upstream
  in [#35](https://github.com/jstevenscl/vod-manager/pull/35) (originally [#43](https://github.com/jstevenscl/vod-manager/pull/43), closed as superseded). The background
  preloader now pauses 15 minutes between batches instead of 45, so it does
  about 290 shows per hour per provider instead of about 100. It still sends
  one request at a time with 3 seconds between requests.
- ✅ ⛔ **Preloading is adjustable in Settings → Refresh Schedule.** Proposed
  upstream in [#35](https://github.com/jstevenscl/vod-manager/pull/35) (originally [#43](https://github.com/jstevenscl/vod-manager/pull/43)). The new
  "Episode list preloading" section sets shows per batch, the pause between
  batches and the gap between requests. It explains what each one does and
  shows a live shows-per-hour estimate. Setting 0 shows turns preloading off.
  The card's help text is also brighter.
- ✅ ⛔ **Shows whose episode list failed to load move to the back of the
  queue.** Proposed upstream in [#35](https://github.com/jstevenscl/vod-manager/pull/35) (originally [#43](https://github.com/jstevenscl/vod-manager/pull/43)).
  The preloader used to keep a failed show at the front, so every batch started
  by re-trying the same dead shows. Now failed shows are tried only after every
  other pending show, and at most once a day. Opening or playing a show still
  loads its episodes right away.
- ✅ ⛔ **A provider that keeps failing stops its batch early, as intended.**
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
- ✅ 🔼 **Apply rules counts as a catalog refresh.** Shipped upstream in [v0.2.21](https://github.com/jstevenscl/vod-manager/releases/tag/v0.2.21) via [#42](https://github.com/jstevenscl/vod-manager/pull/42). It re-imports every
  provider but didn't reset the refresh timer, so the scheduler imported the
  same provider again shortly after.

## 2026-10-04 (Series merge keeps provider links)

- ✅ 🔼 **"Apply rules" no longer re-creates the same shows as "new" on every
  run.** Shipped upstream in [v0.2.21](https://github.com/jstevenscl/vod-manager/releases/tag/v0.2.21) via [#41](https://github.com/jstevenscl/vod-manager/pull/41). When two cards for the same show were merged, the provider link on
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

The credential fix and the "Provider 5 of 4" label fix shipped upstream in
[v0.2.21](https://github.com/jstevenscl/vod-manager/releases/tag/v0.2.21) via [#40](https://github.com/jstevenscl/vod-manager/pull/40) (follow-up to #39).
Episode trickle pacing stays fork only: it depends on fork-only episode
discovery changes that upstream doesn't have.

- ✅ 🔼 **Docker build no longer hangs.** The frontend stage now builds once on
  the runner's native platform instead of under arm64 emulation, and the
  build job is capped at 30 minutes. A build that had sat for 36+ minutes now
  completes in about 7. Shipped upstream in [v0.2.21](https://github.com/jstevenscl/vod-manager/releases/tag/v0.2.21) via [#39](https://github.com/jstevenscl/vod-manager/pull/39).
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
- ✅ 🔼 **Provider credentials hidden in "Apply rules" errors.** A failed
  provider in the apply-rules summary no longer shows the provider's
  username and password in the error URL. Shipped upstream in [v0.2.21](https://github.com/jstevenscl/vod-manager/releases/tag/v0.2.21) via [#40](https://github.com/jstevenscl/vod-manager/pull/40).
- ✅ **Episode trickle no longer collides with "Apply rules".** A trickle
  run that overlapped a catalog import queued episode writes behind the
  import and a few were skipped with "database is locked". The trickle now
  skips its run while a catalog import is in progress, and stops early if
  one starts mid-run; the skipped shows are picked up on the next run.
- ✅ 🔼 **"Provider 5 of 4" progress label fixed.** While "Apply rules" finished
  its final category re-sweep, the progress text counted one provider past
  the total and still named the last provider. It now reads "All N
  provider(s) synced — finalizing…". Shipped upstream in [v0.2.21](https://github.com/jstevenscl/vod-manager/releases/tag/v0.2.21) via [#40](https://github.com/jstevenscl/vod-manager/pull/40).

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
  - 🔼 **Excluded categories now remove content already imported.** Adding a
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
  - 🔼 TMDB review search (needs-review, missing-artwork, AI suggest, bulk AI)
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

- ✅🔼 Provider imports now retain a deleteable, per-run catalog report. Each
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

- ✅⛔ Post-import catalog processing now completes the intended staged
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

- ✅🔼 Playback relay recovery retries transient provider disconnects by
  reopening the upstream at the next byte range. Normal client disconnects
  and superseded range requests remain normal playback behavior, and incomplete
  capacity reservations are hidden from Activity instead of displaying as
  `undefined`/`NaN`. Shipped upstream in [v0.2.20](https://github.com/jstevenscl/vod-manager/releases/tag/v0.2.20) via
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

- ✅🔼 Xtream/Emby catalog refreshes now scope episode-source ranking to the
  requested series before SQLite runs its source-selection window, instead of
  ranking the entire episode catalog for every `get_series_info` request.
  Repeated client activity updates are also debounced, eliminating a SQLite
  write for every catalog item. This reduces CPU and refresh latency for direct
  Emby connections and for Dispatcharr instances using VOD Manager as their
  upstream catalog. Regression coverage and before/after measurements are
  recorded with the deployment validation: representative series requests fell
  from about 4.05–4.12 seconds to 16–28 milliseconds on the production-sized
  catalog snapshot. Shipped upstream in [v0.2.20](https://github.com/jstevenscl/vod-manager/releases/tag/v0.2.20) via
  [#33](https://github.com/jstevenscl/vod-manager/pull/33).

## 2026-09-18

- ✅ Post-import series episode discovery now runs with automatic concurrency
  of six provider requests, while preserving persistent provider HTTP clients.
  This is the current value documented in upstream [#35](https://github.com/jstevenscl/vod-manager/pull/35) (originally [#31](https://github.com/jstevenscl/vod-manager/pull/31)).

- ✅ Enrichment progress now counts canonical series once instead of counting
  each provider source separately, preventing misleading totals above 100%.

- ✅⛔ Metadata Review now provides an explicit **Merge into existing** action
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
