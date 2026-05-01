# gumroad-library-tools

Tools for extracting your own purchased Gumroad library — list it, download files at original quality, and build a research dossier of every product's description and table of contents.

Works by reading the auth token cached on disk by the **Gumroad iOS-on-Mac app** (the iPhone/iPad app that runs natively on Apple Silicon Macs). No login flow, no cookie scraping, no Cloudflare workarounds — if you're signed into the app, the tools just work.

## Why this exists

Gumroad's web download page sits behind Cloudflare's bot challenge, which makes scraping with cookies fragile (the `cf_clearance` cookie is bound to TLS fingerprint, not just user-agent). The mobile API at `api.gumroad.com/mobile/` has none of that — it's a clean JSON API auth'd by a stable token.

The web download URLs also don't always serve original-quality video; the streaming endpoint transcodes to ~1080p HLS. The mobile API exposes a `/mobile/url_redirects/download/` endpoint that returns the original file the creator uploaded.

## Requirements

- Apple Silicon Mac (M1/M2/M3/M4)
- The [**Gumroad** iOS app](https://apps.apple.com/app/gumroad/id1067678944) installed via the Mac App Store and signed into your account
- Python 3.9+ (standard library only — no pip dependencies)

After installing the app, **open it once and load your library page** so it caches an authenticated request. That's the only setup.

## Install

Clone and run — there's nothing to install:

```bash
git clone https://github.com/<your-account>/gumroad-library-tools
cd gumroad-library-tools
```

## Usage

### List your library

```bash
python3 list_library.py
```

Prints a summary table sorted by content staleness (creators who haven't updated in years rise to the top). Add `--md inv.md` or `--json inv.json` to write structured output too.

### Download a product

```bash
# By Gumroad permalink (the bit after gumroad.com/l/)
python3 download_product.py --permalink abc123

# By name substring (case-insensitive)
python3 download_product.py --name "Some Course Title"

# Multiple at once
python3 download_product.py --name "First Product" --name "Second Product"

# Custom output folder
python3 download_product.py --permalink abc123 --out ~/Videos/my-course
```

Files are written as `NN - <name>.<ext>` per product, with a `_metadata.json` capturing the description, creator, purchase date, and Gumroad URLs.

For products with no Gumroad-hosted files (creators who deliver via external URLs), the script writes a `README.md` with the description and the gumroad.com/d/ download-page URL — open that in your browser for the actual delivery instructions.

### Build a research dossier

```bash
python3 build_dossier.py
# writes ./dossier.md
```

A single Markdown document with every product's full description (HTML→Markdown converted) and file-level table of contents. Useful for browsing your library, finding which old courses are gathering dust, or mining your back-catalogue for content ideas.

## How it works

1. Finds the Gumroad app's data container under `~/Library/Containers/<UUID>/Data/` by reading each container's `.com.apple.containermanagerd.metadata.plist` and matching on bundle identifier `com.GRD.Gumroad`.
2. Opens the NSURLCache SQLite database at `Library/Caches/com.GRD.Gumroad/Cache.db` in read-only mode.
3. Walks cached request URLs until it finds one with a `?mobile_token=...` query parameter. That's your auth token.
4. Calls the mobile API directly for purchases, product attributes, or download URLs.

The tools never modify the app's database, never trigger a network request to anything other than Gumroad's own API, and never persist your token to disk.

## Privacy

- **Your token isn't logged.** Scripts read it into memory and pass it through `urllib`. It does NOT appear in any output, file, or stderr message.
- **Your library data goes only to disk paths you specify.** No telemetry. No external services.
- **The auth token can be rotated** by signing out of the Gumroad app — useful if you've shared a debug log somewhere.

## What this is not

- **Not a piracy tool.** Only your own purchases — the API rejects requests for products you don't own. The download endpoints are the same ones the app uses; you're just calling them from a different client.
- **Not a Gumroad-creator tool.** This is for buyers extracting their library. If you're a creator looking to manage your products, use the official [Gumroad API](https://app.gumroad.com/api).
- **Not officially supported by Gumroad.** The mobile API is undocumented; expect breakage when Gumroad ships a new app version.

## Limitations

- macOS only. The iOS app's container path is the entire mechanism.
- Apple Silicon only. The iOS-on-Mac app doesn't run on Intel Macs.
- Requires the app to have loaded an authenticated request at least once since you signed in.
- Some products use **external delivery** — the creator hosts files outside Gumroad and uses Gumroad just for purchase + redirect. For those, the manifest has zero files; the script writes a README pointing you at the gumroad.com/d/ page.

## License

MIT. See `LICENSE`.

## Acknowledgements

This started as a one-off rabbit hole to extract an old course purchase the author wanted to mine for content ideas. The pivot from "scrape the web download page" to "the mobile app already has the data and a clean API, just read its cache" turned out to generalise nicely.
