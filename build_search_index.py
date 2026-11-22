#!/usr/bin/env python3
"""Build a section-level JSON search index from root-level HTML files.

No dependencies beyond Python's standard library. Run after editing your pages:
    python build_search_index.py

A result is generated for each <h1>, <h2>, or <h3> section in <main>.
Give section headings an id for direct links (e.g. <h2 id="projects">).
The script never edits your HTML, and reports headings missing an id.
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
    "address", "article", "blockquote", "br", "dd", "div", "dl", "dt",
    "h1", "h2", "h3", "h4", "h5", "h6", "hr", "li", "main", "ol",
    "p", "pre", "section", "table", "td", "th", "tr", "ul",
}
VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}
SECTION_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
EXCLUDED_FILES = {"404.html"}


def tidy(text: str) -> str:
    """Collapse whitespace while preserving Unicode letters and punctuation."""
    return re.sub(r"\s+", " ", text).strip()


class SectionParser(HTMLParser):
    """Extract searchable <main> sections without modifying the HTML source."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.in_title = False
        self.found_main = False
        self.in_main = False
        self.stack: list[tuple[str, bool]] = []  # (tag, ignored subtree)
        self.sections: list[dict] = []
        self.current = self._new_section("", None, "", "", 0)
        self.heading: dict | None = None
        self.page_heading = ""
        self.parent_h2 = ""
        self.warnings: list[str] = []
        self.used_section_ids: set[str] = set()

    @staticmethod
    def _new_section(title, anchor, parent, tag, line):
        return {
            "title": title, "anchor": anchor, "parent": parent,
            "tag": tag, "line": line, "parts": [],
        }

    @staticmethod
    def _ignored(tag, attrs, parent_ignored):
        attrs = dict(attrs)
        return (
            parent_ignored
            or tag in SKIP_ELEMENTS
            or "data-search-ignore" in attrs
            or "hidden" in attrs
            or (attrs.get("aria-hidden") or "").lower() == "true"
        )

    def _add_space(self):
        if self.heading is not None:
            self.heading["parts"].append(" ")
        else:
            self.current["parts"].append(" ")

    def _finish_section(self):
        content = tidy("".join(self.current["parts"]))
        if content or self.current["title"]:
            section = {key: value for key, value in self.current.items() if key != "parts"}
            section["content"] = content
            self.sections.append(section)

    def _finish_heading(self):
        heading = self.heading
        if heading is None:
            return
        label = tidy("".join(heading["parts"]))
        anchor = heading["anchor"]
        tag = heading["tag"]
        line = heading["line"]

        if tag == "h1":
            if not self.page_heading:
                self.page_heading = label
            self.parent_h2 = ""
        elif tag == "h2":
            self.parent_h2 = label

        if label and not anchor and tag in SECTION_HEADINGS - {"h1"}:
            self.warnings.append(
                f"line {line}: <{tag}> '{label}' has no id (link opens page top)"
            )
        if anchor:
            if anchor in self.used_section_ids:
                self.warnings.append(
                    f"line {line}: duplicate section id '{anchor}' (check your HTML)"
                )
            self.used_section_ids.add(anchor)

        parent = self.parent_h2 if tag == "h3" else ""
        self.current = self._new_section(label, anchor, parent, tag, line)
        self.heading = None

    def handle_starttag(self, tag, attrs):
        if tag == "title" and not self.in_main:
            self.in_title = True

        if tag == "main" and not self.in_main:
            self.found_main = True
            self.in_main = True
            self.stack = [("main", self._ignored(tag, attrs, False))]
            return

        if not self.in_main or not self.stack:
            return

        parent_ignored = self.stack[-1][1]
        ignored = self._ignored(tag, attrs, parent_ignored)

        if not ignored and tag in BLOCK_ELEMENTS:
            self._add_space()
        if not ignored and tag in SECTION_HEADINGS and self.heading is None:
            self._finish_section()
            self.heading = {
                "tag": tag,
                "anchor": dict(attrs).get("id") or None,
                "line": self.getpos()[0],
                "parts": [],
            }

        if tag not in VOID_ELEMENTS:
            self.stack.append((tag, ignored))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_ELEMENTS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if not self.in_main:
            return

        if self.heading is not None and tag == self.heading["tag"]:
            self._finish_heading()

        if tag in BLOCK_ELEMENTS:
            self._add_space()

        # Close the matching element and any incorrectly left-open children.
        for pos in range(len(self.stack) - 1, -1, -1):
            if self.stack[pos][0] == tag:
                del self.stack[pos:]
                if not self.stack:
                    self._finish_section()
                    self.in_main = False
                break

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)
        if not self.in_main or not self.stack or self.stack[-1][1]:
            return
        if self.heading is not None:
            self.heading["parts"].append(data)
        else:
            self.current["parts"].append(data)


def build_index(root: Path) -> int:
    entries = []
    pages = 0
    warnings = 0
    for path in sorted(root.glob("*.html")):
        if path.name in EXCLUDED_FILES:
            continue
        parser = SectionParser()
        parser.feed(path.read_text(encoding="utf-8-sig"))
        parser.close()

        if not parser.found_main:
            print(f"Skipping {path.name}: no <main> found")
            continue

        document_title = tidy("".join(parser.title_parts))
        page_name = parser.page_heading or document_title or path.stem
        page_url = quote(path.name)
        count = 0
        for section in parser.sections:
            title = section["title"] or "Overview"
            content = section["content"]
            if not content and not section["title"]:
                continue
            fragment = (
                "#" + quote(section["anchor"], safe="")
                if section["anchor"] else ""
            )
            entries.append({
                "page": page_name,
                "title": title,
                "parent": section["parent"],
                "url": page_url + fragment,
                "content": content,
            })
            count += 1
        if count:
            pages += 1
        else:
            print(f"Skipping {path.name}: no searchable sections")
        for warning in parser.warnings:
            warnings += 1
            print(f"WARNING {path.name}: {warning}")

    if not entries:
        raise SystemExit("No indexable sections found. Check your <main> elements.")

    output = root / "search-index.json"
    output.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Indexed {len(entries)} sections across {pages} page(s) -> {output.name}")
    if warnings:
        print(f"{warnings} warning(s): add unique id attributes to those headings for direct links.")
    return len(entries)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parent,
        help="Directory containing the HTML pages (default: script directory)",
    )
    root = cli.parse_args().root.resolve()
    if not root.is_dir():
        raise SystemExit(f"Not a directory: {root}")
    build_index(root)


if __name__ == "__main__":
    main()
