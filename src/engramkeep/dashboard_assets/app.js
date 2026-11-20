(() => {
  "use strict";

  const TOKEN_KEY = "engramkeep-dashboard-token";
  const state = {
    token: null,
    writes: false,
    projects: [],
    activeTag: null,
    currentCard: null,
  };

  function storageGet(key) {
    try {
      return sessionStorage.getItem(key);
    } catch (error) {
      return null;
    }
  }

  function storageSet(key, value) {
    try {
      sessionStorage.setItem(key, value);
    } catch (error) {
      // The token still works for this page load.
    }
  }

  function readToken() {
    const hash = new URLSearchParams(window.location.hash.slice(1));
    const fromHash = hash.get("token");
    if (fromHash) {
      storageSet(TOKEN_KEY, fromHash);
      try {
        history.replaceState(null, "", window.location.pathname + window.location.search);
      } catch (error) {
        // Keep the fragment when the browser refuses to rewrite history.
      }
      return fromHash;
    }
    return storageGet(TOKEN_KEY);
  }

  function setStatus(message, isError = false) {
    const node = document.getElementById("status");
    node.textContent = message;
    node.classList.toggle("error", isError);
  }

  async function api(path, options = {}) {
    if (!state.token) {
      throw new Error("No dashboard token. Open the URL printed by engramkeep dashboard.");
    }
    const headers = new Headers(options.headers || {});
    headers.set("X-Engramkeep-Token", state.token);
    if (options.body !== undefined) {
      headers.set("Content-Type", "application/json");
    }
    const response = await fetch(path, { ...options, headers, cache: "no-store" });
    let data = {};
    try {
      data = await response.json();
    } catch (error) {
      // Keep the status text when the body is not JSON.
    }
    if (!response.ok) {
      throw new Error(data.error || `${response.status} ${response.statusText}`);
    }
    return data;
  }

  function clear(node) {
    while (node.firstChild) {
      node.removeChild(node.firstChild);
    }
  }

  function text(tag, value, className) {
    const node = document.createElement(tag);
    node.textContent = value;
    if (className) {
      node.className = className;
    }
    return node;
  }

  function appendInlineMarkdown(parent, raw) {
    // Safe textContent-only inline parser for `code` and ~~strikethrough~~.
    const pattern = /(`[^`]+`|~~[^~]+~~)/g;
    let lastIndex = 0;
    let match = pattern.exec(raw);
    while (match !== null) {
      if (match.index > lastIndex) {
        parent.appendChild(document.createTextNode(raw.slice(lastIndex, match.index)));
      }
      const token = match[0];
      if (token.startsWith("`") && token.endsWith("`")) {
        parent.appendChild(text("code", token.slice(1, -1)));
      } else if (token.startsWith("~~") && token.endsWith("~~")) {
        parent.appendChild(text("del", token.slice(2, -2)));
      } else {
        parent.appendChild(document.createTextNode(token));
      }
      lastIndex = match.index + token.length;
      match = pattern.exec(raw);
    }
    if (lastIndex < raw.length) {
      parent.appendChild(document.createTextNode(raw.slice(lastIndex)));
    }
  }

  function renderStructuredMarkdown(body) {
    // Pure DOM construction via createElement + textContent (zero HTML injection).
    const container = document.createElement("div");
    container.className = "md-body";
    const lines = String(body || "").split(/\r?\n/);
    let inFence = false;
    let fenceLines = [];
    let currentList = null;

    function flushList() {
      if (currentList) {
        container.appendChild(currentList);
        currentList = null;
      }
    }

    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith("```")) {
        flushList();
        if (inFence) {
          container.appendChild(text("pre", fenceLines.join("\n"), "pre"));
          fenceLines = [];
          inFence = false;
        } else {
          inFence = true;
        }
        continue;
      }
      if (inFence) {
        fenceLines.push(line);
        continue;
      }
      if (!trimmed) {
        flushList();
        continue;
      }
      if (trimmed.startsWith("### ")) {
        flushList();
        container.appendChild(text("h5", trimmed.slice(4)));
        continue;
      }
      if (trimmed.startsWith("## ")) {
        flushList();
        container.appendChild(text("h4", trimmed.slice(3)));
        continue;
      }
      if (trimmed.startsWith("# ")) {
        flushList();
        container.appendChild(text("h3", trimmed.slice(2)));
        continue;
      }
      if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
        if (!currentList) {
          currentList = document.createElement("ul");
        }
        const li = document.createElement("li");
        appendInlineMarkdown(li, trimmed.slice(2));
        currentList.appendChild(li);
        continue;
      }
      flushList();
      const paragraph = document.createElement("p");
      appendInlineMarkdown(paragraph, trimmed);
      container.appendChild(paragraph);
    }
    flushList();
    if (inFence && fenceLines.length) {
      container.appendChild(text("pre", fenceLines.join("\n"), "pre"));
    }
    return container;
  }

  function makeTagButton(tag) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = state.activeTag === tag ? "tag-pill active" : "tag-pill";
    btn.textContent = `#${tag}`;
    btn.addEventListener("click", () => {
      state.activeTag = state.activeTag === tag ? null : tag;
      document.getElementById("search-tag").value = state.activeTag || "";
      renderProjects(state.projects);
    });
    return btn;
  }

  function renderTagBar(projects) {
    const bar = document.getElementById("tag-bar");
    const clearBtn = document.getElementById("clear-tag-btn");
    clear(bar);
    const counts = new Map();
    for (const project of projects) {
      for (const tag of project.tags || []) {
        counts.set(tag, (counts.get(tag) || 0) + 1);
      }
    }
    const tags = Array.from(counts.keys()).sort();
    for (const tag of tags) {
      bar.appendChild(makeTagButton(tag));
    }
    clearBtn.hidden = !state.activeTag;
  }

  function renderProjects(projects) {
    state.projects = projects;
    renderTagBar(projects);
    const list = document.getElementById("project-list");
    clear(list);
    const filtered = state.activeTag
      ? projects.filter((p) => (p.tags || []).includes(state.activeTag))
      : projects;
    if (!filtered.length) {
      list.appendChild(
        text("li", state.activeTag ? `No projects tagged '${state.activeTag}'.` : "No projects yet.", "muted")
      );
      return;
    }
    for (const project of filtered) {
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = project.title;
      button.addEventListener("click", () => loadCard(project.id));
      item.appendChild(button);
      item.appendChild(text("span", ` ${project.id}`, "muted"));
      if (project.tags.length) {
        const tagWrap = document.createElement("div");
        tagWrap.className = "inline-tags";
        for (const tag of project.tags) {
          tagWrap.appendChild(makeTagButton(tag));
        }
        item.appendChild(tagWrap);
      }
      list.appendChild(item);
    }
  }

  function renderSearch(hits) {
    const list = document.getElementById("search-results");
    clear(list);
    if (!hits.length) {
      list.appendChild(text("li", "No matches.", "muted"));
      return;
    }
    for (const hit of hits) {
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = hit.title;
      button.addEventListener("click", () => loadCard(hit.id));
      item.appendChild(button);
      item.appendChild(text("span", ` ${hit.id}`, "muted"));
      if (hit.snippet) {
        item.appendChild(text("p", hit.snippet, "snippet"));
      }
      list.appendChild(item);
    }
  }

  function renderCard(card) {
    state.currentCard = card;
    document.getElementById("copy-card-btn").hidden = false;
    const view = document.getElementById("card-view");
    clear(view);
    view.appendChild(text("h3", card.title));
    view.appendChild(text("p", `id: ${card.id} | updated: ${card.updated}`, "muted"));
    if (card.tags.length) {
      const tagWrap = document.createElement("div");
      tagWrap.className = "inline-tags";
      for (const tag of card.tags) {
        tagWrap.appendChild(makeTagButton(tag));
      }
      view.appendChild(tagWrap);
    }
    view.appendChild(renderStructuredMarkdown(card.body));
  }

  function renderRecent(entries) {
    const list = document.getElementById("recent-list");
    clear(list);
    if (!entries.length) {
      list.appendChild(text("li", "No activity yet.", "muted"));
      return;
    }
    for (const entry of entries) {
      list.appendChild(text("li", entry));
    }
  }

  function renderFixes(fixes) {
    const list = document.getElementById("fixes-list");
    clear(list);
    if (!fixes.length) {
      list.appendChild(text("li", "No fixes recorded yet.", "muted"));
      return;
    }
    for (const hit of fixes) {
      const item = document.createElement("li");
      item.appendChild(text("strong", `${hit.project} (${hit.date})`));
      item.appendChild(text("span", ` ${hit.workspace || "General"}`, "muted"));
      item.appendChild(text("p", `problem: ${hit.error}`, "snippet"));
      item.appendChild(text("p", `fix: ${hit.fix}`, "snippet"));
      list.appendChild(item);
    }
  }

  function renderDoctor(report) {
    document.getElementById("doctor-view").textContent = JSON.stringify(report, null, 2);
  }

  async function loadProjects() {
    const data = await api("/api/cards");
    renderProjects(data.projects);
  }

  async function loadCard(id) {
    const data = await api(`/api/cards/${encodeURIComponent(id)}`);
    renderCard(data.card);
  }

  async function loadRecent() {
    const data = await api("/api/recent?limit=10");
    renderRecent(data.entries);
  }

  async function loadFixes(query = "") {
    const params = new URLSearchParams({ limit: "10" });
    if (query) {
      params.set("q", query);
    }
    const data = await api(`/api/fixes?${params.toString()}`);
    renderFixes(data.fixes);
  }

  async function loadDoctor() {
    const data = await api("/api/doctor");
    renderDoctor(data.report);
  }

  async function refresh() {
    setStatus("Loading...");
    try {
      const health = await api("/api/health");
      state.writes = Boolean(health.writes);
      document.getElementById("remember-section").hidden = !state.writes;
      document.getElementById("fix-section").hidden = !state.writes;
      await Promise.all([loadProjects(), loadRecent(), loadFixes(), loadDoctor()]);
      setStatus(state.writes ? "Ready. Writes are enabled." : "Ready. Read-only mode.");
    } catch (error) {
      setStatus(error.message, true);
    }
  }

  document.getElementById("clear-tag-btn").addEventListener("click", () => {
    state.activeTag = null;
    document.getElementById("search-tag").value = "";
    renderProjects(state.projects);
  });

  document.getElementById("copy-card-btn").addEventListener("click", async () => {
    if (!state.currentCard) {
      return;
    }
    try {
      await navigator.clipboard.writeText(state.currentCard.body);
      setStatus(`Copied '${state.currentCard.id}' Markdown to clipboard.`);
    } catch (error) {
      setStatus("Clipboard copy unavailable in this browser context.", true);
    }
  });

  document.getElementById("export-btn").addEventListener("click", async () => {
    try {
      setStatus("Exporting JSON...");
      const doc = await api("/api/export");
      const blob = new Blob([JSON.stringify(doc, null, 2) + "\n"], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "engramkeep-export.json";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setStatus("Export downloaded.");
    } catch (error) {
      setStatus(error.message, true);
    }
  });

  document.getElementById("search-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const query = document.getElementById("search-query").value.trim();
    const tag = document.getElementById("search-tag").value.trim();
    if (!query) {
      setStatus("Enter a search query.", true);
      return;
    }
    const params = new URLSearchParams({ q: query });
    if (tag) {
      params.set("tag", tag);
    }
    try {
      setStatus("Searching...");
      const data = await api(`/api/search?${params.toString()}`);
      renderSearch(data.hits);
      setStatus(`${data.hits.length} result(s).`);
    } catch (error) {
      setStatus(error.message, true);
    }
  });

  document.getElementById("fixes-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const query = document.getElementById("fixes-query").value.trim();
    try {
      setStatus("Loading fixes...");
      await loadFixes(query);
      setStatus("Ready.");
    } catch (error) {
      setStatus(error.message, true);
    }
  });

  document.getElementById("remember-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.writes) {
      setStatus("Writes are disabled.", true);
      return;
    }
    if (!document.getElementById("remember-confirm").checked) {
      setStatus("Confirm the decision before saving.", true);
      return;
    }
    const project = document.getElementById("remember-project").value.trim();
    const decision = document.getElementById("remember-decision").value.trim();
    const tags = document.getElementById("remember-tags").value
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean);
    if (!project || !decision) {
      setStatus("Project and decision are required.", true);
      return;
    }
    try {
      setStatus("Saving...");
      await api("/api/remember", {
        method: "POST",
        body: JSON.stringify({ project, decision, tags, confirm: true }),
      });
      document.getElementById("remember-form").reset();
      setStatus("Decision remembered.");
      await Promise.all([loadProjects(), loadRecent(), loadDoctor()]);
    } catch (error) {
      setStatus(error.message, true);
    }
  });

  document.getElementById("record-fix-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!state.writes) {
      setStatus("Writes are disabled.", true);
      return;
    }
    if (!document.getElementById("fix-confirm").checked) {
      setStatus("Confirm the fix before saving.", true);
      return;
    }
    const errorText = document.getElementById("fix-error").value.trim();
    const solution = document.getElementById("fix-solution").value.trim();
    const project = document.getElementById("fix-project").value.trim() || undefined;
    const workspace = document.getElementById("fix-workspace").value.trim() || undefined;
    if (!errorText || !solution) {
      setStatus("Problem and verified fix are required.", true);
      return;
    }
    try {
      setStatus("Recording fix...");
      const res = await api("/api/fixes", {
        method: "POST",
        body: JSON.stringify({
          error: errorText,
          solution,
          project,
          workspace,
          confirm: true,
        }),
      });
      document.getElementById("record-fix-form").reset();
      setStatus(res.added ? "Fix recorded." : "Identical fix already recorded.");
      await Promise.all([loadFixes(), loadRecent(), loadDoctor()]);
    } catch (error) {
      setStatus(error.message, true);
    }
  });

  state.token = readToken();
  if (!state.token) {
    setStatus("No dashboard token. Open the URL printed by engramkeep dashboard.", true);
  } else {
    refresh();
  }
})();
