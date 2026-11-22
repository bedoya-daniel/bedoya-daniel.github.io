#!/usr/bin/env python3
"""Build a client-side search index for HTML files in the website root.

Uses only the Python standard library. Run after editing your HTML pages:
    python build_search_index.py
"""

import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import quote

SKIP_ELEMENTS = {
    "script", "style", "template", "noscript", "svg", "nav", "aside", "form",
}
BLOCK_ELEMENTS = {
    "address", "article", "blockquote", "br", "dd", "div", "dl", "dt", "h1",
    "h2", "h3", "h4", "h5", "h6", "hr", "li", "main", "ol", "p",
    "pre", "section", "table", "td", "th", "tr", "ul",
}
VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}
HEADING_ELEMENTS = {"h1", "h2", "h3", "h4", "h5", "h6"}
EXCLUDED_FILES = {"404.html"}


def tidy(text: str) -> str:
    """Collapse whitespace without changing non-ASCII characters."""
    return re.sub(r"\s+", " ", text).strip()


class MainContentParser(HTMLParser):
    """Extract <title>, headings, and visible text inside <main>."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.in_title = False
        self.found_main = False
        self.in_main = False
        self.stack: list[tuple[str, bool]] = []  # (tag name, ignored subtree)
        self.content_parts: list[str] = []
        self.headings: list[str] = []
        self.current_heading: str | None = None
        self.heading_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "title" and not self.in_main:
            self.in_title = True

        if tag == "main" and not self.in_main:
            self.found_main = True
            self.in_main = True
            self.stack = [("main", self._ignored(tag, attrs, False))]
            return

        if not self.in_main:
            return

        if tag in BLOCK_ELEMENTS:
            self.content_parts.append(" ")

        parent_ignored = self.stack[-1][1]
        ignored = self._ignored(tag, attrs, parent_ignored)
        if tag not in VOID_ELEMENTS:
            self.stack.append((tag, ignored))

        if tag in HEADING_ELEMENTS and not ignored:
            self.current_heading = tag
            self.heading_parts = []

    def handle_startendtag(self, tag, attrs):
        # Self-closing tags must not remain on the open-element stack.
        self.handle_starttag(tag, attrs)
        if tag not in VOID_ELEMENTS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

        if not self.in_main:
            return

        if tag == self.current_heading:
            heading = tidy("".join(self.heading_parts))
            if heading:
                self.headings.append(heading)
            self.current_heading = None
            self.heading_parts = []

        if tag in BLOCK_ELEMENTS:
            self.content_parts.append(" ")

        # Close the matching open element and any malformed unclosed children.
        for pos in range(len(self.stack) - 1, -1, -1):
            if self.stack[pos][0] == tag:
                del self.stack[pos:]
                if not self.stack:
                    self.in_main = False
                break

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)
        if not self.in_main or not self.stack or self.stack[-1][1]:
            return
        self.content_parts.append(data)
        if self.current_heading is not None:
            self.heading_parts.append(data)

    @staticmethod
    def _ignored(tag, attrs, parent_ignored):
        attrs = dict(attrs)
        return (
            parent_ignored
            or tag in SKIP_ELEMENTS
            or "data-search-ignore" in attrs
            or "hidden" in attrs
            or attrs.get("aria-hidden", "").lower() == "true"
        )


def build_index(root: Path) -> int:
    pages = []
    for page_path in sorted(root.glob("*.html")):
        if page_path.name in EXCLUDED_FILES:
            continue

        parser = MainContentParser()
        parser.feed(page_path.read_text(encoding="utf-8-sig"))
        parser.close()

        if not parser.found_main:
            print(f"Skipping {page_path.name}: no <main> element found")
            continue

        content = tidy("".join(parser.content_parts))
        if not content:
            print(f"Skipping {page_path.name}: empty searchable content")
            continue

        title = tidy("".join(parser.title_parts))
        if not title:
            title = parser.headings[0] if parser.headings else page_path.stem

        pages.append({
            "title": title,
            "url": quote(page_path.name),
            "headings": parser.headings,
            "content": content,
        })

    if not pages:
        raise SystemExit("No indexable HTML pages found. Check <main> and --root.")

    output = root / "search-index.json"
    output.write_text(
        json.dumps(pages, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Indexed {len(pages)} pages -> {output}")
    return len(pages)


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parent,
        help="Directory with HTML pages (default: directory containing this script)",
    )
    parsed = args.parse_args()
    root = parsed.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"Not a directory: {root}")
    build_index(root)


if __name__ == "__main__":
    main()
