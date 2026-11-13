# AEROINTEL — Open-Source Defence Aviation News

One screen, curated open-source defence aviation news. Installable on iPhone and Android (PWA), free to host on GitHub Pages.

Built by [Vural Avcı](https://www.linkedin.com/in/vural-avci-759635315/).

## How it works

```
sources.json ──► GitHub Actions (every 30 min) ──► scripts/fetch_feeds.py ──► feeds.json ──► index.html (GitHub Pages)
```

- **sources.json**: the curated source list (name, feed URL, category, tags, paywall flag).
- **scripts/fetch_feeds.py**: fetches every RSS/Atom feed server-side (Python standard library only), keeps the last 30 days, removes duplicates, records per-source health (`ok`, `stale`, `empty`, `error`) and writes **feeds.json**.
- **index.html**: the app. Reads `feeds.json`; if it is missing it falls back to fetching feeds in the browser via rss2json; if that also fails it shows a clearly labelled preview with sample data.
- **sw.js + manifest.webmanifest + icons/**: make it installable and usable offline with the last copy.

## Deploy (about 5 minutes)

1. Create a new **public** repository on GitHub, e.g. `aerointel`, and upload all files (keep the folder structure, including `.github/workflows/`).
2. **Settings → Actions → General → Workflow permissions →** select *Read and write permissions* → Save.
3. **Actions → Update feeds → Run workflow** (first run creates `feeds.json`; after that it runs every 30 minutes).
4. **Settings → Pages → Build and deployment →** Source: *Deploy from a branch*, Branch: `main` / `(root)` → Save.
5. Open `https://<your-username>.github.io/aerointel/` after a minute.

## Edit the sources

Change `sources.json`, and update the embedded copy at the top of the `<script>` in `index.html` (`FALLBACK_SOURCES`) so preview/fallback mode matches. Pushing `sources.json` triggers a new feed run. Check each source's status in the app's **SOURCES** tab or in the Actions log.

## Visit counter (optional, cookie-free)

Create a free [GoatCounter](https://www.goatcounter.com) site, then set `const GC_CODE = "yourcode";` in `index.html`.

## Features

- Curated sources in news, analysis, Europe/NATO and Türkiye categories, with live source health and 🔒 marks for paywalled publications
- Automatic topic chips (CCA / Loyal Wingman, MUM-T, 6th Gen, SEAD / EW, Air Defence, C-UAS…)
- **My Watchlist**: personal keywords, stored only on the device; matches highlighted with ★
- "New for you" counter since the last visit, offline support, installable on iOS and Android

## Licence

© 2026 Vural Avcı. All rights reserved. See [LICENSE](LICENSE).

## Notes

- Headlines, excerpts and images belong to their publishers; every card links to the original article.
- Independent, non-commercial project; not affiliated with any listed publication, company or government body.
