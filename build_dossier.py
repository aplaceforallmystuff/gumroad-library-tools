#!/usr/bin/env python3
"""Build a research dossier from your Gumroad library.

For each product: full description (HTML→Markdown) + file-level table of
contents. Useful for mining your back-catalogue for content ideas, comparing
how creators framed similar products, or just remembering what you bought.

Usage:
    python3 build_dossier.py                       # write to ./dossier.md
    python3 build_dossier.py --out ~/notes/lib.md  # custom path
"""
from __future__ import annotations

import argparse
import re
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

from gumroad_library_tools.api import (
    list_purchases, read_token, human_size, human_duration,
)


class HtmlToMd(HTMLParser):
    """Minimal HTML → Markdown converter (headings, lists, links, emphasis)."""

    def __init__(self):
        super().__init__()
        self.out = []
        self.skip = 0
        self.list_stack = []
        self.ol_counters = []
        self.href = None

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in ("h1", "h2"):
            self.out.append("\n\n## ")
        elif tag == "h3":
            self.out.append("\n\n### ")
        elif tag in ("h4", "h5", "h6"):
            self.out.append("\n\n#### ")
        elif tag == "p":
            self.out.append("\n\n")
        elif tag == "br":
            self.out.append("  \n")
        elif tag in ("strong", "b"):
            self.out.append("**")
        elif tag in ("em", "i"):
            self.out.append("*")
        elif tag == "ul":
            self.list_stack.append("ul")
            self.out.append("\n")
        elif tag == "ol":
            self.list_stack.append("ol")
            self.ol_counters.append(0)
            self.out.append("\n")
        elif tag == "li":
            indent = "  " * (len(self.list_stack) - 1)
            if self.list_stack and self.list_stack[-1] == "ol":
                self.ol_counters[-1] += 1
                self.out.append(f"\n{indent}{self.ol_counters[-1]}. ")
            else:
                self.out.append(f"\n{indent}- ")
        elif tag == "a":
            self.href = dict(attrs).get("href", "")
            self.out.append("[")
        elif tag == "blockquote":
            self.out.append("\n\n> ")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in ("strong", "b"):
            self.out.append("**")
        elif tag in ("em", "i"):
            self.out.append("*")
        elif tag == "a" and self.href is not None:
            self.out.append(f"]({self.href})")
            self.href = None
        elif tag in ("ul", "ol"):
            if self.list_stack:
                self.list_stack.pop()
            if tag == "ol" and self.ol_counters:
                self.ol_counters.pop()

    def handle_data(self, data):
        if self.skip:
            return
        self.out.append(data)

    def get_md(self):
        text = "".join(self.out)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def html_to_md(html: str | None) -> str:
    if not html:
        return "_(no description)_"
    parser = HtmlToMd()
    try:
        parser.feed(html)
    except Exception:
        return unescape(re.sub(r"<[^>]+>", " ", html)).strip() or "_(no description)_"
    return parser.get_md() or "_(no description)_"


def file_toc(file_data: list[dict]) -> str:
    if not file_data:
        return "_(no files in manifest — likely external delivery via custom URL)_"
    lines = []
    for i, f in enumerate(file_data, 1):
        name = f.get("name_displayable") or f.get("name") or f"file_{i}"
        ft = f.get("filetype") or "?"
        size = human_size(f.get("size"))
        dur = human_duration(f.get("duration"))
        meta_bits = [ft]
        if size != "—":
            meta_bits.append(size)
        if dur:
            meta_bits.append(dur)
        lines.append(f"{i}. **{name}** _({', '.join(meta_bits)})_")
    return "\n".join(lines)


def build(records: list[dict], now: datetime) -> str:
    sections = [
        f"# Gumroad Library — Research Dossier",
        "",
        f"_{len(records)} products. Generated {now.strftime('%Y-%m-%d')}._",
        "",
        "Full descriptions and file-level tables of contents for every product",
        "in your library. Useful for mining your back-catalogue.",
        "",
    ]
    # sort: stalest first
    records.sort(key=lambda p: p.get("content_updated_at") or "")

    for i, p in enumerate(records, 1):
        name = p.get("name", "?")
        creator = p.get("creator_name", "?")
        creator_url = p.get("creator_profile_url", "")
        cu = p.get("content_updated_at") or ""
        pa = p.get("purchased_at") or ""
        permalink = p.get("unique_permalink", "")
        gumroad_url = f"https://gumroad.com/l/{permalink}" if permalink else ""
        rating = p.get("product_rating")
        files = p.get("file_data") or []

        sections.extend([
            f"## {i}. {name}",
            "",
            f"- **Creator:** [{creator}]({creator_url})",
            f"- **Product page:** {gumroad_url}",
            f"- **Content last updated:** {cu[:10] or '—'}",
            f"- **You purchased:** {pa[:10] or '—'}",
        ])
        if rating is not None:
            sections.append(f"- **Your rating:** {rating}/5")
        sections.extend([
            f"- **Files in manifest:** {len(files)}",
            "",
            "### Description",
            "",
            html_to_md(p.get("description") or ""),
            "",
            "### File manifest",
            "",
            file_toc(files),
            "",
            "---",
            "",
        ])
    return "\n".join(sections)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("./dossier.md"))
    args = ap.parse_args()

    now = datetime.now()
    token = read_token()
    purchases = list(list_purchases(token))
    args.out.write_text(build(purchases, now))
    print(f"✓ {args.out} ({len(purchases)} products, {args.out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
