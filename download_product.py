#!/usr/bin/env python3
"""Download every file in one or more Gumroad products you've purchased.

Uses the mobile API's `/mobile/url_redirects/download/` endpoint, which
returns the original-quality file (not the transcoded HLS variant the web
streamer serves). Files are saved as `NN - <name>.<ext>` per product.

Usage:
    # by Gumroad permalink (the bit after gumroad.com/l/)
    python3 download_product.py --permalink abc123

    # by name substring (case-insensitive, matches first hit)
    python3 download_product.py --name "Some Course Title"

    # multiple at once
    python3 download_product.py --name "First Product" --name "Second Product"

    # different output folder (default: ./downloads/<product-name>/)
    python3 download_product.py --permalink abc123 --out ~/Videos/notion-course

For products with no Gumroad-hosted files (external delivery), the script
writes a README.md with the description + delivery URL instead.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

from gumroad_library_tools.api import (
    list_purchases, read_token, get_product_attributes,
    build_download_url, human_size, safe_filename,
)


def find_product(token: str, *, permalink: str | None = None,
                 name_contains: str | None = None) -> dict | None:
    for p in list_purchases(token):
        if permalink and p.get("unique_permalink") == permalink:
            return p
        if name_contains and name_contains.lower() in (p.get("name") or "").lower():
            return p
    return None


def download_file(api_url: str, target: Path, expected_size: int = 0) -> bool:
    if target.exists() and (not expected_size or target.stat().st_size == expected_size):
        print(f"    ↳ already complete, skipping")
        return True
    tmp = target.with_suffix(target.suffix + ".part")
    try:
        with urllib.request.urlopen(api_url, timeout=120) as r:
            total = int(r.headers.get("Content-Length") or expected_size or 0)
            written = 0
            with open(tmp, "wb") as out:
                while True:
                    chunk = r.read(1024 * 256)
                    if not chunk:
                        break
                    out.write(chunk)
                    written += len(chunk)
                    if total:
                        pct = written * 100 // total
                        print(f"\r    {human_size(written)}/{human_size(total)} ({pct}%)",
                              end="", flush=True)
            print()
        tmp.rename(target)
        return True
    except Exception as e:
        print(f"\n    ✗ failed: {e}")
        if tmp.exists():
            tmp.unlink()
        return False


def process(product: dict, token: str, out_dir: Path) -> tuple[int, int]:
    name = product.get("name", "?")
    redirect_token = product.get("url_redirect_token")
    external_id = product.get("url_redirect_external_id")
    files = product.get("file_data") or []

    print(f"\n=== {name} ===")
    print(f"  Creator: {product.get('creator_name')}")
    print(f"  Files in cached manifest: {len(files)}")

    # Refresh from API if cache shows no files (external-delivery case)
    if not files and external_id:
        print("  Fetching fresh manifest...")
        try:
            fresh = get_product_attributes(token, external_id)
            files = (fresh.get("product") or {}).get("file_data") or []
            print(f"  Files in fresh manifest: {len(files)}")
        except Exception as e:
            print(f"  ✗ refresh failed: {e}")

    folder = out_dir / safe_filename(name)
    folder.mkdir(parents=True, exist_ok=True)

    # Always save metadata for later reference
    meta = {
        "name": name,
        "creator": product.get("creator_name"),
        "creator_url": product.get("creator_profile_url"),
        "description": product.get("description"),
        "gumroad_url": f"https://gumroad.com/l/{product.get('unique_permalink')}",
        "download_page": f"https://gumroad.com/d/{redirect_token}",
        "purchased_at": product.get("purchased_at"),
        "content_updated_at": product.get("content_updated_at"),
        "file_count": len(files),
    }
    (folder / "_metadata.json").write_text(json.dumps(meta, indent=2))

    if not files:
        readme = folder / "README.md"
        readme.write_text(
            f"# {name}\n\n"
            f"_No Gumroad-hosted files. This product uses external delivery._\n\n"
            f"- Creator: {product.get('creator_name')}\n"
            f"- Download page: https://gumroad.com/d/{redirect_token}\n"
            f"  (Open in your browser — your Gumroad session will show the actual delivery instructions.)\n"
        )
        print(f"  → No downloadable files. Wrote {readme}.")
        return 0, 0

    ok = fail = 0
    for i, f in enumerate(files, 1):
        fname = f.get("name_displayable") or f.get("name") or f"file_{i}"
        ft = f.get("filetype") or "bin"
        size = f.get("size") or 0
        target = folder / f"{i:02d} - {safe_filename(fname)}.{ft}"
        print(f"  [{i}/{len(files)}] {fname} ({human_size(size)})")
        api_url = build_download_url(token, redirect_token, f["id"])
        if download_file(api_url, target, size):
            ok += 1
        else:
            fail += 1
    return ok, fail


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--permalink", action="append", default=[],
                    help="Gumroad permalink (e.g. 'abc123' from gumroad.com/l/abc123)")
    ap.add_argument("--name", action="append", default=[],
                    help="Substring of product name (case-insensitive). Repeatable.")
    ap.add_argument("--out", type=Path, default=Path("./downloads"),
                    help="Output directory (default: ./downloads/)")
    args = ap.parse_args()

    if not args.permalink and not args.name:
        ap.error("Specify at least one --permalink or --name.")

    token = read_token()

    targets = []
    for perm in args.permalink:
        p = find_product(token, permalink=perm)
        if p:
            targets.append(p)
        else:
            print(f"⚠ no product found for permalink '{perm}'", file=sys.stderr)
    for name in args.name:
        p = find_product(token, name_contains=name)
        if p:
            targets.append(p)
        else:
            print(f"⚠ no product found matching '{name}'", file=sys.stderr)

    print(f"Matched {len(targets)} products. Downloading to {args.out.resolve()}\n")

    total_ok = total_fail = 0
    for p in targets:
        ok, fail = process(p, token, args.out)
        total_ok += ok
        total_fail += fail

    print(f"\n=== Done. {total_ok} files downloaded, {total_fail} failed. ===")


if __name__ == "__main__":
    main()
