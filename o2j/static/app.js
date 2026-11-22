"use strict";

const $ = (id) => document.getElementById(id);
const state = {
  file: null, url: null, json: null, busy: false, limit: 50 * 1024 * 1024,
  preview: { url: null, page: 1, total: 0, loading: false, request: 0 },
};

function status(message = "", error = false) {
  $("status").textContent = message;
  $("status").classList.toggle("error", error);
}

function controls() {
  $("run").disabled = state.busy || !state.file;
  $("pick").disabled = state.busy;
  $("file").disabled = state.busy;
  $("copy").disabled = state.busy || !state.json;
  $("download").disabled = state.busy || state.json === null;
  $("run").firstChild.textContent = state.busy ? "Analizowanie… " : "Analizuj ";
  const preview = state.preview;
  $("prev").disabled = preview.loading || preview.page <= 1;
  $("next").disabled = preview.loading || preview.page >= preview.total;
  $("page-count").textContent = preview.total ? preview.page + " / " + preview.total : "";
}

async function requestPdf(route, file) {
  const response = await fetch(route, {
    method: "POST",
    headers: { "Content-Type": "application/pdf" },
    body: file,
  });
  if (!response.ok) {
    const result = await response.json();
    throw new Error(result.error || "Nie udało się odczytać dokumentu.");
  }
  return response;
}

async function previewPage(page) {
  const preview = state.preview;
  const request = ++preview.request;
  preview.loading = true;
  controls();
  try {
    const response = await requestPdf("/api/preview?page=" + page, state.file);
    const image = await response.blob();
    if (request !== preview.request) return;
    if (preview.url) URL.revokeObjectURL(preview.url);
    preview.url = URL.createObjectURL(image);
    preview.total = Number(response.headers.get("X-PDF-Pages"));
    preview.page = page;
    $("pdf").src = preview.url;
    $("pdf").alt = "Strona " + page + " dokumentu " + state.file.name;
    $("pdf-empty").hidden = true;
    $("preview-scroll").hidden = false;
    $("preview-scroll").scrollTop = 0;
  } catch (error) {
    if (request !== preview.request) return;
    $("pdf-empty").hidden = false;
    $("preview-scroll").hidden = true;
    $("preview-message").textContent = "Podgląd niedostępny";
    $("preview-hint").textContent = error.message;
  } finally {
    if (request === preview.request) {
      preview.loading = false;
      controls();
    }
  }
}

function select(file) {
  if (!file || state.busy) return;
  if (!/\.pdf$/i.test(file.name) || !file.size || file.size > state.limit) {
    status("Wybierz plik PDF o rozmiarze do 50 MB.", true);
    return;
  }
  if (state.url) URL.revokeObjectURL(state.url);
  state.file = file;
  state.url = URL.createObjectURL(new Blob([file], { type: "application/pdf" }));
  state.json = null;
  $("file-name").textContent = file.name;
  $("file-detail").textContent = new Intl.NumberFormat("pl", { maximumFractionDigits: 1 }).format(file.size / 1024) + " kB";
  $("open-pdf").href = state.url;
  $("preview-controls").hidden = false;
  $("preview-scroll").hidden = true;
  $("pdf-empty").hidden = false;
  $("preview-message").textContent = "Wczytywanie podglądu";
  $("preview-hint").textContent = "";
  state.preview.total = 0;
  $("json-empty").hidden = false;
  $("result").hidden = true;
  $("trace").open = false;
  status();
  previewPage(1);
}

function syntaxHighlight(source) {
  const tokens = /("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false|null)\b|(?<![\w.])-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/g;
  const content = document.createDocumentFragment();
  let previous = 0;
  for (const match of source.matchAll(tokens)) {
    content.append(source.slice(previous, match.index));
    const span = document.createElement("span");
    span.className = match[2] ? "json-key" : match[1] ? "json-string" : "json-literal";
    span.textContent = match[0];
    content.append(span);
    previous = match.index + match[0].length;
  }
  content.append(source.slice(previous));
  return content;
}

function showResult(result) {
  state.json = result.data === null ? "" : JSON.stringify(result.data, null, 2) + "\n";
  $("json-empty").hidden = true;
  $("result").hidden = false;
  $("result-class").textContent = result.label;
  $("result-time").textContent = result.seconds.toFixed(2).replace(".", ",") + " s";
  $("json").replaceChildren(state.json ? syntaxHighlight(state.json) : document.createTextNode("Pusty plik .json"));
  const ocrPages = result.pages.filter((page) => page.source === "ocr").map((page) => page.number);
  const engine = result.engine === "rules" ? "reguły lokalne" : result.engine;
  $("trace-meta").textContent = "Ekstrakcja · " + engine + " · "
    + (ocrPages.length ? "OCR stron " + ocrPages.join(", ") : "warstwa tekstowa PDF");
  $("warnings").replaceChildren(...result.warnings.map((message) => {
    const item = document.createElement("li");
    item.textContent = message;
    return item;
  }));
  $("evidence").replaceChildren(...Object.entries(result.evidence).map(([path, detail]) => {
    const item = document.createElement("li");
    const jump = document.createElement("button");
    jump.type = "button";
    jump.className = "evidence-page";
    jump.textContent = "Strona " + detail.page;
    jump.addEventListener("click", () => previewPage(detail.page));
    const quote = document.createElement("span");
    quote.className = "evidence-quote";
    quote.textContent = detail.text;
    item.append(jump, " · " + path, quote);
    return item;
  }));
  const reproduced = Object.keys(result.evidence).length;
  status(result.warnings.length ? "Zakończono analizę. Szczegóły w śladzie ekstrakcji."
    : reproduced ? "Zakończono analizę · " + reproduced + " pól z odnalezionym fragmentem źródła." : "Zakończono analizę.");
}

async function analyze() {
  if (!state.file || state.busy) return;
  state.busy = true;
  state.json = null;
  $("result").hidden = true;
  $("json-empty").hidden = false;
  status("Odczytywanie dokumentu i wyodrębnianie danych…");
  controls();
  try {
    const response = await requestPdf("/api/analyze", state.file);
    showResult(await response.json());
  } catch (error) {
    status(error.message, true);
  } finally {
    state.busy = false;
    controls();
  }
}

$("pick").addEventListener("click", () => $("file").click());
$("file").addEventListener("change", (event) => {
  select(event.target.files[0]);
  event.target.value = "";
});
$("run").addEventListener("click", analyze);
$("prev").addEventListener("click", () => previewPage(state.preview.page - 1));
$("next").addEventListener("click", () => previewPage(state.preview.page + 1));
for (const name of ["dragenter", "dragover", "dragleave", "drop"]) {
  $("drop").addEventListener(name, (event) => {
    event.preventDefault();
    $("drop").classList.toggle("dragging", !state.busy && (name === "dragenter" || name === "dragover"));
    if (name === "drop") select(event.dataTransfer.files[0]);
  });
}
$("copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(state.json);
    status("JSON skopiowany do schowka.");
  } catch {
    status("Schowek jest niedostępny. Możesz pobrać plik JSON.", true);
  }
});
$("download").addEventListener("click", () => {
  const url = URL.createObjectURL(new Blob([state.json], { type: "application/json;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = state.file.name.replace(/\.pdf$/i, ".json");
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
fetch("/api/status").then((response) => response.json()).then((settings) => {
  state.limit = settings.max_upload;
  $("classes").textContent = settings.classes.join(" · ");
  $("mode").classList.toggle("remote", Boolean(settings.model));
  $("mode").lastChild.textContent = settings.model ? " Tryb hybrydowy" : " Tryb lokalny";
  if (settings.model) $("mode").title = settings.model;
}).catch(() => { $("mode").lastChild.textContent = " Serwer niedostępny"; });
