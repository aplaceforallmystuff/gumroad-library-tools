#!/usr/bin/env python3
"""List every product in your Gumroad library, sorted by content staleness.

Useful for: spotting outdated content you bought years ago, finding repackage
opportunities, or just remembering what's in there.

Usage:
    python3 list_library.py                  # print summary table to stdout
    python3 list_library.py --md inv.md      # also write a Markdown table
    python3 list_library.py --json inv.json  # also write machine-readable JSON
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from gumroad_library_tools.api import (
    list_purchases, read_token, human_size, human_duration,
)


def parse_iso(s: str | None):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def years_since(dt, now: datetime):
    if not dt:
        return None
    return round((now - dt).days / 365.25, 1)


def summarise_files(file_data: list[dict]) -> dict:
    totals = {"count": len(file_data), "video_count": 0, "pdf_count": 0,
              "total_bytes": 0, "video_seconds": 0, "types": {}}
    for f in file_data:
        ft = f.get("filetype", "?")
        totals["types"][ft] = totals["types"].get(ft, 0) + 1
        totals["total_bytes"] += f.get("size") or 0
        if f.get("filegroup") == "video":
            totals["video_count"] += 1
            totals["video_seconds"] += f.get("duration") or 0
        if ft == "pdf":
            totals["pdf_count"] += 1
    return totals


def build_record(p: dict, now: datetime) -> dict:
    files = p.get("file_data") or []
    fs = summarise_files(files)
    cu = parse_iso(p.get("content_updated_at"))
    pa = parse_iso(p.get("purchased_at"))
    return {
        "name": p.get("name"),
        "creator": p.get("creator_name"),
        "permalink": p.get("unique_permalink"),
        "purchased_at": p.get("purchased_at"),
        "content_updated_at": p.get("content_updated_at"),
        "years_since_update": years_since(cu, now),
        "rating": p.get("product_rating"),
        "file_count": fs["count"],
        "video_count": fs["video_count"],
        "pdf_count": fs["pdf_count"],
        "total_bytes": fs["total_bytes"],
        "total_size_human": human_size(fs["total_bytes"]),
        "video_runtime_human": human_duration(fs["video_seconds"]) or "—",
        "file_types": fs["types"],
    }


def render_md(records: list[dict], now: datetime) -> str:
    lines = [
        f"# Gumroad Library Inventory",
        "",
        f"_{len(records)} products. Generated {now.strftime('%Y-%m-%d')}._",
        "",
        "Sorted by **content staleness** (longest since creator updated content).",
        "",
        "| # | Name | Creator | Updated | Files | Size | Runtime | Rating |",
        "|---|------|---------|---------|-------|------|---------|--------|",
    ]
    for i, r in enumerate(records, 1):
        upd = (r["content_updated_at"] or "—")[:10]
        rating = r["rating"] if r["rating"] is not None else "—"
        files_str = str(r["file_count"])
        if r["video_count"]:
            files_str += f" ({r['video_count']}v)"
        if r["pdf_count"]:
            files_str += f" ({r['pdf_count']}pdf)"
        lines.append(
            f"| {i} | **{r['name']}** | {r['creator']} | {upd} | "
            f"{files_str} | {r['total_size_human']} | {r['video_runtime_human']} | {rating} |"
        )
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--md", type=Path, help="Write Markdown table to this path")
    ap.add_argument("--json", type=Path, help="Write JSON inventory to this path")
    ap.add_argument("--no-stdout", action="store_true",
                    help="Suppress the stdout summary (useful when only writing files)")
    args = ap.parse_args()

    now = datetime.now()
    token = read_token()
    purchases = list(list_purchases(token))
    records = [build_record(p, now) for p in purchases]
    records.sort(key=lambda r: -(r["years_since_update"] or 0))

    if args.json:
        args.json.write_text(json.dumps(records, indent=2))
        print(f"✓ {args.json}")
    if args.md:
        args.md.write_text(render_md(records, now))
        print(f"✓ {args.md}")
    if not args.no_stdout:
        print(f"\n{len(records)} products in library:")
        for i, r in enumerate(records, 1):
            yrs = r["years_since_update"]
            stale = f"{yrs}y old" if yrs else "—"
            print(f"  {i:2d}. {r['name'][:55]:55} {r['creator'][:20]:20}  "
                  f"{stale:8}  {r['total_size_human']:>8}")


if __name__ == "__main__":
    main()
