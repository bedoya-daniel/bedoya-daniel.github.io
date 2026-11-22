/* Dependency-free search for a six-page static website. */
(() => {
  "use strict";

  const input = document.getElementById("site-search");
  const results = document.getElementById("search-results");
  const status = document.getElementById("search-status");
  const dropdown = document.getElementById("search-dropdown");
  if (!input || !results || !status) return;

  // All HTML pages and search-index.json are in the same directory.
  // Relative URLs also work for GitHub Pages project sites (/repository/).
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
          indexPromise = undefined; // Permit another attempt after a network error.
          throw error;
        });
    }
    return indexPromise;
  }

  function findMatches(pages, query) {
    const terms = normalize(query).trim().split(/\s+/).filter(Boolean);
    if (!terms.length) return [];

    return pages
      .map((page) => {
        const title = normalize(page.title);
        const headings = normalize(page.headings.join(" "));
        const content = normalize(page.content);
        // All query terms must occur, possibly in different fields.
        if (!terms.every((term) =>
          title.includes(term) || headings.includes(term) || content.includes(term)
        )) return null;

        const score = terms.reduce((total, term) =>
          total + (title.includes(term) ? 10 : 0)
                + (headings.includes(term) ? 5 : 0)
                + (content.includes(term) ? 1 : 0), 0);
        return { page, score };
      })
      .filter(Boolean)
      .sort((a, b) => b.score - a.score || a.page.title.localeCompare(b.page.title));
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

    for (const { page } of matches) {
      const item = document.createElement("li");
      item.className = "search-result";

      const link = document.createElement("a");
      link.href = new URL(page.url, indexURL).href;
      link.textContent = page.title;

      const summary = document.createElement("p");
      summary.textContent = excerpt(page.content, query);

      item.append(link, summary);
      results.append(item);
    }
  }

  input.addEventListener("input", async () => {
    const query = input.value.trim();
    const version = ++searchVersion;
    if (!query) {
      dropdown.hidden = true;
      results.replaceChildren();
      status.textContent = "";
      return;
    }

    dropdown.hidden = false;

    status.textContent = "Searching…";
    try {
      const pages = await getIndex();
      if (version !== searchVersion) return; // Ignore stale asynchronous responses.
      showResults(findMatches(pages, query), query);
    } catch (error) {
      if (version !== searchVersion) return;
      results.replaceChildren();
      status.textContent = "Search index could not be loaded. Please try again.";
      console.error("Site search:", error);
    }
  });

  status.textContent = "";
})();
