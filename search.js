/* Section-level search; no dependencies or external services. */
(() => {
  "use strict";

  const input = document.getElementById("site-search");
  const results = document.getElementById("search-results");
  const status = document.getElementById("search-status");
  const dropdown = document.getElementById("search-dropdown");
  if (!input || !results || !status) return;

  // All HTML pages and search-index.json are in the same directory.
  const indexURL = new URL("search-index.json", window.location.href);
  let indexPromise;
  let searchVersion = 0;

  const normalize = (text) =>
    String(text).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

  function getIndex() {
    if (!indexPromise) {
      indexPromise = fetch(indexURL)
        .then((response) => {
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          return response.json();
        })
        .catch((error) => {
          indexPromise = undefined; // A later keystroke can retry a failed fetch.
          throw error;
        });
    }
    return indexPromise;
  }

  function findMatches(sections, query) {
    const terms = normalize(query).trim().split(/\s+/).filter(Boolean);
    if (!terms.length) return [];

    return sections
      .map((section) => {
        // Match terms within ONE section rather than across the entire page.
        const title = normalize(section.title);
        const content = normalize(section.content);
        if (!terms.every((term) => title.includes(term) || content.includes(term))) {
          return null;
        }
        const score = terms.reduce((total, term) =>
          total + (title.includes(term) ? 5 : 0)
                + (content.includes(term) ? 1 : 0), 0);
        return { section, score };
      })
      .filter(Boolean)
      .sort((a, b) => b.score - a.score ||
        a.section.page.localeCompare(b.section.page) ||
        a.section.title.localeCompare(b.section.title));
  }

  function excerpt(content, query) {
    const folded = normalize(content);
    const terms = normalize(query).trim().split(/\s+/).filter(Boolean);
    const positions = terms.map((term) => folded.indexOf(term)).filter((pos) => pos >= 0);
    const matchPos = positions.length ? Math.min(...positions) : 0;
    const start = Math.max(0, matchPos - 65);
    const end = Math.min(content.length, Math.max(155, matchPos + 115));
    return `${start ? "…" : ""}${content.slice(start, end).trim()}${end < content.length ? "…" : ""}`;
  }

  function showResults(matches, query) {
    results.replaceChildren();
    status.textContent = `${matches.length} result${matches.length === 1 ? "" : "s"}`;

    for (const { section } of matches) {
      const item = document.createElement("li");
      item.className = "search-result";

      const link = document.createElement("a");
      link.href = new URL(section.url, indexURL).href;
      const sectionLabel = section.parent
        ? `${section.parent} › ${section.title}` : section.title;
      link.textContent = section.page === sectionLabel
        ? sectionLabel : `${sectionLabel} — ${section.page}`;
      item.append(link);

      if (section.content) {
        const summary = document.createElement("p");
        summary.textContent = excerpt(section.content, query);
        item.append(summary);
      }
      results.append(item);
    }
  }

  input.addEventListener("input", async () => {
    const query = input.value.trim();
    const version = ++searchVersion;
    if (!query) {
      if (dropdown) dropdown.hidden = true;
      results.replaceChildren();
      status.textContent = "";
      return;
    }

    if (dropdown) dropdown.hidden = false;
    status.textContent = "Searching…";
    try {
      const sections = await getIndex();
      if (version !== searchVersion) return;
      showResults(findMatches(sections, query), query);
    } catch (error) {
      if (version !== searchVersion) return;
      results.replaceChildren();
      status.textContent = "Search index could not be loaded. Please try again.";
      console.error("Site search:", error);
    }
  });

  if (dropdown) dropdown.hidden = true;
  status.textContent = "";
})();
