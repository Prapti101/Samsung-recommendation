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
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        // Surface the server's precise reason so we can message the user
        // instead of silently staying English.
        const message = (data && data.message) ||
          "Translation is temporarily unavailable.";
        return { translations: null, error: (data && data.error) || "http_" + res.status, message };
      }
      if (!data || !Array.isArray(data.translations) || data.translations.length !== texts.length) {
        return { translations: null, error: "bad_response",
                 message: "Translation is temporarily unavailable." };
      }
      return { translations: data.translations, error: null, message: null };
    } catch (_) {
      return { translations: null, error: "network_error",
               message: "Couldn't reach the translation service." };
    }
  }

  /* Lightweight, non-blocking toast so translation failures are never silent
     and never leave the UI looking "stuck". Reuses design tokens via inline
     styles to avoid touching the stylesheet. */
  function showToast(message) {
    let toast = document.getElementById("gm-i18n-toast");
    if (!toast) {
      toast = document.createElement("div");
      toast.id = "gm-i18n-toast";
      toast.setAttribute("role", "status");
      toast.setAttribute("data-i18n-skip", "");
      toast.style.cssText = [
        "position:fixed", "left:50%", "bottom:24px", "transform:translateX(-50%)",
        "background:#10131A", "color:#fff", "padding:12px 20px", "border-radius:100px",
        "font:500 .88rem/1.3 'Inter',sans-serif", "box-shadow:0 16px 40px rgba(16,20,40,.28)",
        "z-index:9999", "max-width:90vw", "text-align:center", "opacity:0",
        "transition:opacity .25s ease, transform .25s ease", "pointer-events:none",
      ].join(";");
      document.body.appendChild(toast);
    }
    toast.textContent = message;
    requestAnimationFrame(() => {
      toast.style.opacity = "1";
      toast.style.transform = "translateX(-50%) translateY(-4px)";
    });
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(-50%)";
    }, 4200);
  }

  async function translatePage(root) {
    root = root || document.body;
    const lang = getCurrentLang();

    document.documentElement.lang = lang;
    document.documentElement.dir = RTL_LANGS.has(lang) ? "rtl" : "ltr";

    if (lang === DEFAULT_LANG) return { ok: true };

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

    if (!missing.length) return { ok: true };

    const chunks = chunkArray(missing, CHUNK_SIZE);
    const results = await Promise.all(chunks.map((chunk) => fetchTranslations(lang, chunk)));

    const updatedCache = { ...cache };
    let changed = false;
    let firstError = null;
    chunks.forEach((chunk, idx) => {
      const result = results[idx];
      const translated = result && result.translations;
      if (!translated) {
        if (!firstError && result) firstError = result;
        return; // this batch stays English
      }
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

    if (firstError) {
      return { ok: false, error: firstError.error, message: firstError.message };
    }
    return { ok: true };
  }

  function initLanguageSwitcher() {
    const select = document.getElementById("gm-lang-select");
    if (!select) return;
    select.value = getCurrentLang();
    select.addEventListener("change", async () => {
      const chosen = select.value;
      setCurrentLang(chosen);
      const status = await translatePage(document.body);
      if (status && status.ok === false) {
        // Never leave a half-translated page: message the user and fall back
        // cleanly to English.
        showToast(status.message || "Translation is temporarily unavailable. Showing English.");
        setCurrentLang(DEFAULT_LANG);
        select.value = DEFAULT_LANG;
        document.documentElement.lang = DEFAULT_LANG;
        document.documentElement.dir = "ltr";
        // If some text was already swapped from a prior cached session, reload
        // to restore clean English — but defer so the toast is readable first.
        const hadCachedText = Object.keys(readCache(chosen)).length > 0;
        if (chosen !== DEFAULT_LANG && hadCachedText) {
          setTimeout(() => window.location.reload(), 1800);
        }
      }
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