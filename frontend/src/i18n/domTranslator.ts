import { ar } from "./ar";

export type Language = "en" | "ar";

const dictionaries: Record<"ar", Record<string, string>> = { ar };
const ATTRS = ["placeholder", "aria-label", "title", "alt"] as const;
const SKIP_TAGS = new Set(["SCRIPT", "STYLE", "TEXTAREA", "INPUT", "CODE", "PRE", "KBD", "SVG"]);

const translatedText = new Map<Text, string>();
const translatedAttrs = new Map<Element, Record<string, string>>();
const writtenText = new WeakMap<Text, string>();
const writtenAttrs = new WeakMap<Element, Record<string, string>>();

let current: Language = "en";
let observer: MutationObserver | null = null;
let scheduled = false;
let applying = false;

function inPatientPortal(): boolean {
  return window.location.pathname.startsWith("/p/");
}

function shouldSkip(node: Node): boolean {
  const element = node.parentElement;
  if (!element) return true;
  if (SKIP_TAGS.has(element.tagName)) return true;
  if (element.closest("[data-no-translate]")) return true;
  return false;
}

function translateNode(node: Text, dictionary: Record<string, string>) {
  if (shouldSkip(node)) return;
  const raw = node.nodeValue ?? "";
  const trimmed = raw.trim();
  if (!trimmed) return;
  const translated = dictionary[trimmed];
  if (!translated || translated === trimmed) return;
  const start = raw.indexOf(trimmed);
  if (start < 0) return;
  if (!translatedText.has(node)) translatedText.set(node, raw);
  node.nodeValue =
    raw.slice(0, start) + translated + raw.slice(start + trimmed.length);
  writtenText.set(node, node.nodeValue);
}

function translateAttributes(element: Element, dictionary: Record<string, string>) {
  if (element.closest("[data-no-translate]")) return;
  let originals = translatedAttrs.get(element);
  for (const attr of ATTRS) {
    const value = element.getAttribute(attr);
    if (!value) continue;
    const trimmed = value.trim();
    const translated = dictionary[trimmed];
    if (!translated || translated === trimmed) continue;
    if (!originals) {
      originals = {};
      translatedAttrs.set(element, originals);
    }
    if (!(attr in originals)) originals[attr] = value;
    element.setAttribute(attr, translated);
    const written = writtenAttrs.get(element) ?? {};
    written[attr] = translated;
    writtenAttrs.set(element, written);
  }
}

function translateSubtree(root: Node) {
  if (current === "en" || inPatientPortal()) return;
  const dictionary = dictionaries.ar;
  applying = true;
  try {
    if (root.nodeType === Node.TEXT_NODE) {
      translateNode(root as Text, dictionary);
      return;
    }
    if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_NODE) {
      return;
    }
    const scope = root as ParentNode;
    const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT);
    const textNodes: Text[] = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode as Text);
    textNodes.forEach((node) => translateNode(node, dictionary));

    if (scope instanceof Element) translateAttributes(scope, dictionary);
    scope.querySelectorAll?.("*").forEach((element) => translateAttributes(element, dictionary));
  } finally {
    applying = false;
  }
}

function restoreAll() {
  translatedText.forEach((original, node) => {
    if (node.isConnected) node.nodeValue = original;
  });
  translatedText.clear();
  translatedAttrs.forEach((originals, element) => {
    if (!element.isConnected) return;
    Object.entries(originals).forEach(([attr, value]) => element.setAttribute(attr, value));
  });
  translatedAttrs.clear();
}

function scheduleTranslate() {
  if (scheduled || current === "en" || applying) return;
  scheduled = true;
  window.setTimeout(() => {
    scheduled = false;
    if (current !== "en") translateSubtree(document.body);
  }, 80);
}

function startObserver() {
  if (observer) return;
  observer = new MutationObserver((mutations) => {
    if (applying || current === "en" || inPatientPortal()) return;
    for (const mutation of mutations) {
      if (mutation.type === "characterData") {
        const node = mutation.target as Text;
        if (writtenText.get(node) === node.nodeValue) continue;
        translatedText.delete(node);
        translateNode(node, dictionaries.ar);
      } else {
        mutation.addedNodes.forEach((node) => translateSubtree(node));
        if (mutation.type === "attributes") {
          const element = mutation.target as Element;
          const attr = mutation.attributeName;
          if (attr && writtenAttrs.get(element)?.[attr] === element.getAttribute(attr)) {
            continue;
          }
          const originals = translatedAttrs.get(element);
          if (originals && attr) delete originals[attr];
          translateAttributes(element, dictionaries.ar);
        }
      }
    }
    scheduleTranslate();
  });
  observer.observe(document.body, {
    childList: true,
    subtree: true,
    characterData: true,
    attributes: true,
    attributeFilter: ["placeholder", "aria-label", "title", "alt"],
  });
}

export function applyLanguage(language: Language) {
  current = language;
  document.documentElement.lang = language;
  document.documentElement.dir = language === "ar" ? "rtl" : "ltr";
  document.documentElement.dataset.lang = language;

  if (language === "en") {
    restoreAll();
    observer?.disconnect();
    observer = null;
    return;
  }
  translateSubtree(document.body);
  startObserver();
}

export function getActiveLanguage(): Language {
  return current;
}
