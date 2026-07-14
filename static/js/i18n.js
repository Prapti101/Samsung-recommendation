/* i18n.js — AI-powered multilingual support (Gemini API, via server-side
   /api/translate proxy). No hardcoded translation dictionaries: all
   translations are fetched dynamically from Gemini and cached in
   localStorage so repeat views don't re-request them. */

(function () {
  const LANG_KEY = "gmLang";
  const CACHE_PREFIX = "gmTranslationCache_";
  const DEFAULT_LANG = "en";
  const SUPPORTED_LANGS = ["en", "hi", "bn", "ta", "te", "mr", "gu", "kn", "ml", "pa", "or", "ur"];
  const RTL_LANGS = new Set(["ur"]);
  const CHUNK_SIZE = 40;

  function getCurrentLang() {
    try {
      const stored = localStorage.getItem(LANG_KEY);
      if (stored && SUPPORTED_LANGS.includes(stored)) return stored;
    } catch (_) {}
    return DEFAULT_LANG;
  }

  function setCurrentLang(lang) {
    try {
      localStorage.setItem(LANG_KEY, lang);
    } catch (_) {}
  }

  function readCache(lang) {
    try {
      const raw = localStorage.getItem(CACHE_PREFIX + lang);
      return raw ? JSON.parse(raw) : {};
    } catch (_) {
      return {};
    }
  }

  function writeCache(lang, cacheObj) {
    try {
      localStorage.setItem(CACHE_PREFIX + lang, JSON.stringify(cacheObj));
    } catch (_) {}
  }

  function collectTranslatables(root) {
    const items = [];
    const SKIP_PARENT_TAGS = new Set(["SCRIPT", "STYLE", "NOSCRIPT"]);

    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const parentEl = node.parentElement;
        if (!parentEl) return NodeFilter.FILTER_REJECT;
        if (SKIP_PARENT_TAGS.has(parentEl.tagName)) return NodeFilter.FILTER_REJECT;
        if (parentEl.closest("[data-i18n-skip]")) return NodeFilter.FILTER_REJECT;
        if (!node.nodeValue || !node.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      },
    });

    let n;
    while ((n = walker.nextNode())) {
      items.push({ kind: "text", node: n, original: n.nodeValue });
    }

    const attrSelectors = ["placeholder", "aria-label", "title"];
    attrSelectors.forEach((attr) => {
      root.querySelectorAll(`[${attr}]`).forEach((el) => {
        if (el.closest("[data-i18n-skip]")) return;
        const val = el.getAttribute(attr);
        if (val && val.trim()) items.push({ kind: "attr", node: el, attr, original: val });
      });
    });

    return items;
  }

  function applyTranslations(items, cache) {
    items.forEach((item) => {
      const key = item.original.trim();
      const translated = cache[key];
      if (translated == null) return;
      if (item.kind === "text") {
        const leading = item.original.match(/^\s*/)[0];
        const trailing = item.original.match(/\s*$/)[0];
        item.node.nodeValue = leading + translated + trailing;
      } else {
        item.node.setAttribute(item.attr, translated);
      }
    });
  }

  function chunkArray(arr, size) {
    const chunks = [];
    for (let i = 0; i < arr.length; i += size) chunks.push(arr.slice(i, i + size));
    return chunks;
  }

  async function fetchTranslations(lang, texts) {
    try {
      const res = await fetch("/api/translate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_lang: lang, texts }),
      });
      if (!res.ok) return null;
      const data = await res.json();
      if (!data || !Array.isArray(data.translations) || data.translations.length !== texts.length) {
        return null;
      }
      return data.translations;
    } catch (_) {
      return null;
    }
  }

  async function translatePage(root) {
    root = root || document.body;
    const lang = getCurrentLang();

    document.documentElement.lang = lang;
    document.documentElement.dir = RTL_LANGS.has(lang) ? "rtl" : "ltr";

    if (lang === DEFAULT_LANG) return;

    const items = collectTranslatables(root);
    const cache = readCache(lang);

    // Apply anything already cached immediately (no network round-trip).
    applyTranslations(items, cache);

    const seen = new Set();
    const missing = [];
    items.forEach((item) => {
      const key = item.original.trim();
      if (!key || cache[key] != null || seen.has(key)) return;
      seen.add(key);
      missing.push(key);
    });

    if (!missing.length) return;

    const chunks = chunkArray(missing, CHUNK_SIZE);
    const results = await Promise.all(chunks.map((chunk) => fetchTranslations(lang, chunk)));

    const updatedCache = { ...cache };
    let changed = false;
    chunks.forEach((chunk, idx) => {
      const translated = results[idx];
      if (!translated) return; // Gemini unavailable for this batch -> stays English.
      chunk.forEach((original, i) => {
        const t = translated[i];
        if (typeof t === "string" && t.trim()) {
          updatedCache[original] = t;
          changed = true;
        }
      });
    });

    if (changed) {
      writeCache(lang, updatedCache);
      applyTranslations(items, updatedCache);
    }
  }

  function initLanguageSwitcher() {
    const select = document.getElementById("gm-lang-select");
    if (!select) return;
    select.value = getCurrentLang();
    select.addEventListener("change", () => {
      setCurrentLang(select.value);
      translatePage(document.body);
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initLanguageSwitcher();
    translatePage(document.body);
  });

  window.GalaxyMatchI18n = {
    translatePage: (root) => translatePage(root || document.body),
    getCurrentLang,
  };
})();