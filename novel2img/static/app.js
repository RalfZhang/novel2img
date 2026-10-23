import { applyTranslations, getLanguage, hasMessage, setLanguage, t, translate } from "./i18n.js";

const $ = (id) => document.getElementById(id);
const el = {
  novel: $("novel"),
  style: $("style"),
  chapterSelect: $("chapterSelect"),
  detectBtn: $("detectBtn"),
  generateBtn: $("generateBtn"),
  nextBtn: $("nextBtn"),
  stopBtn: $("stopBtn"),
  maxScenes: $("maxScenes"),
  seed: $("seed"),
  gallery: $("gallery"),
  empty: $("empty"),
  status: $("status"),
  log: $("log"),
  langBtn: $("langBtn"),
  modelInfo: $("modelInfo"),
};

const state = {
  chapters: [], // [{index, title, length}] from /api/split
  controller: null, // AbortController of the running generation
  detectTimer: null,
};

// ------------------------------------------------------------------ status & log

function setStatus(key, params = {}, kind = "") {
  translate(el.status, key, params);
  el.status.className = kind ? `status ${kind}` : "status";
}

function log(message, kind = "") {
  const line = document.createElement("div");
  if (kind) line.className = kind;
  line.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
  el.log.append(line);
  el.log.scrollTop = el.log.scrollHeight;
}

// ------------------------------------------------------------------ API

async function postJSON(path, body, signal) {
  const resp = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!resp.ok) throw new Error(await errorText(resp));
  return resp;
}

async function errorText(resp) {
  try {
    const { detail } = await resp.json();
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((d) => `${d.loc?.at(-1) ?? ""}: ${d.msg}`).join("; ");
  } catch {
    // not a JSON error body
  }
  return `HTTP ${resp.status}`;
}

// Read a Server-Sent Events response and call onEvent(type, data) for each event.
async function readEvents(resp, onEvent) {
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let end;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      let type = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) type = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (data) onEvent(type, JSON.parse(data));
    }
  }
}

async function loadConfig() {
  try {
    const config = await (await fetch("/api/config")).json();
    el.modelInfo.textContent = `${config.llm_model} · ${config.image_model}`;
    el.modelInfo.title = el.modelInfo.textContent;
    el.maxScenes.value = config.max_scenes;
    document.documentElement.style.setProperty("--img-aspect", `${config.width} / ${config.height}`);
  } catch {
    // the UI works without it
  }
}

// ------------------------------------------------------------------ chapters

function renderChapterOptions() {
  const selected = el.chapterSelect.value;
  el.chapterSelect.replaceChildren(
    ...state.chapters.map(
      (c) => new Option(t("chapter.option", { title: c.title || t("chapter.untitled"), length: c.length }), c.index),
    ),
  );
  if (selected !== "" && Number(selected) < state.chapters.length) el.chapterSelect.value = selected;
  el.chapterSelect.disabled = state.chapters.length <= 1 || state.controller !== null;
}

async function detectChapters({ quiet = false } = {}) {
  clearTimeout(state.detectTimer);
  const text = el.novel.value.trim();
  if (!text) {
    state.chapters = [];
    renderChapterOptions();
    if (!quiet) log(t("log.needText"), "err");
    return false;
  }
  if (!quiet) setStatus("status.detecting", {}, "busy");
  try {
    const resp = await postJSON("/api/split", { text });
    state.chapters = (await resp.json()).chapters;
    renderChapterOptions();
    if (!quiet) {
      setStatus("status.chapters", { count: state.chapters.length }, "ok");
      log(t("log.chapters", { count: state.chapters.length }));
    }
    return true;
  } catch (err) {
    setStatus("status.error", {}, "error");
    log(t("log.error", { message: err.message }), "err");
    return false;
  }
}

// Re-detect chapters shortly after the text changes, so the chapter list never goes stale.
function scheduleDetect() {
  clearTimeout(state.detectTimer);
  state.detectTimer = setTimeout(() => detectChapters({ quiet: true }), 500);
}

// ------------------------------------------------------------------ gallery

const cardAt = (index) => el.gallery.querySelector(`.card[data-index="${index}"]`);

function makeElement(tag, className) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  return element;
}

function setPlaceholder(card, key, { spinner = false, error = false, text = "" } = {}) {
  const box = makeElement("div", error ? "placeholder error" : "placeholder");
  if (spinner) box.append(makeElement("div", "spinner"));
  const label = makeElement("div");
  if (text) label.textContent = text;
  else translate(label, key);
  box.append(label);
  card.querySelector(".media").replaceChildren(box);
}

function addCard(index, scene) {
  const card = makeElement("article", "card");
  card.dataset.index = index;

  const meta = makeElement("div", "meta");
  const summary = makeElement("div", "summary");
  if (scene.summary) summary.textContent = scene.summary;
  else translate(summary, "card.scene", { n: index + 1 });
  const seed = makeElement("div", "seed");
  seed.hidden = true;
  const prompt = makeElement("div", "prompt");
  prompt.textContent = scene.prompt;
  const toggle = makeElement("button", "prompt-toggle");
  toggle.type = "button";
  translate(toggle, "card.showPrompt");
  toggle.addEventListener("click", () => {
    const expanded = prompt.classList.toggle("expanded");
    translate(toggle, expanded ? "card.hidePrompt" : "card.showPrompt");
  });
  meta.append(summary, seed, prompt, toggle);

  card.append(makeElement("div", "media"), meta);
  setPlaceholder(card, "card.queued", { spinner: true });
  el.gallery.append(card);
}

function showImage(data) {
  const card = cardAt(data.scene_index);
  if (!card) return;
  const link = makeElement("a");
  link.href = data.url;
  link.target = "_blank";
  link.rel = "noopener";
  const img = makeElement("img");
  img.src = data.url;
  img.alt = data.summary || "";
  link.append(img);
  card.querySelector(".media").replaceChildren(link);
  card.querySelector(".prompt").textContent = data.full_prompt || data.prompt;
  const seed = card.querySelector(".seed");
  translate(seed, "card.seed", { seed: data.seed });
  seed.hidden = false;
}

function clearGallery() {
  el.gallery.replaceChildren();
  el.empty.classList.add("hidden");
}

// ------------------------------------------------------------------ generation

function setBusy(busy) {
  el.generateBtn.disabled = busy;
  el.detectBtn.disabled = busy;
  el.stopBtn.disabled = !busy;
  el.nextBtn.disabled = true;
  el.chapterSelect.disabled = busy || state.chapters.length <= 1;
}

function handleEvent(type, data, run) {
  switch (type) {
    case "chapter":
      run.title = data.title || t("chapter.untitled");
      run.hasNext = data.has_next;
      log(t("log.chapter", { n: data.index + 1, total: data.total, title: run.title }));
      break;
    case "status": {
      const key = `stage.${data.stage}`;
      const params = { n: (data.scene_index ?? 0) + 1, total: data.total ?? "" };
      if (hasMessage(key)) setStatus(key, params, "busy");
      log(hasMessage(key) ? t(key, params) : data.message);
      if (data.stage === "rendering") {
        const card = cardAt(data.scene_index);
        if (card) setPlaceholder(card, "card.rendering", { spinner: true });
      }
      break;
    }
    case "scenes":
      log(t("log.scenes", { count: data.count }));
      if (data.scenes.some((s) => s.original_prompt)) log(t("log.adjusted"), "ok");
      data.scenes.forEach((scene, i) => addCard(i, scene));
      break;
    case "image":
      showImage(data);
      log(t("log.image", { n: data.scene_index + 1, seed: data.seed }), "ok");
      break;
    case "error": {
      const card = typeof data.scene_index === "number" ? cardAt(data.scene_index) : null;
      if (card) setPlaceholder(card, "", { error: true, text: data.message });
      log(t("log.error", { message: data.message }), "err");
      break;
    }
    case "done":
      run.finished = true;
      log(t("log.done"), "ok");
      break;
  }
}

async function generate() {
  if (!el.novel.value.trim()) {
    log(t("log.needText"), "err");
    return;
  }
  // Always split the current text, so chapter_index refers to what is in the box right now.
  if (!(await detectChapters({ quiet: true }))) return;

  const body = {
    text: el.novel.value,
    chapter_index: Number(el.chapterSelect.value || 0),
    style: el.style.value.trim(),
  };
  const maxScenes = parseInt(el.maxScenes.value, 10);
  if (maxScenes > 0) body.max_scenes = maxScenes;
  if (el.seed.value.trim() !== "") body.seed = parseInt(el.seed.value, 10);

  const run = { title: "", hasNext: false, finished: false };
  state.controller = new AbortController();
  clearGallery();
  setBusy(true);
  setStatus("status.generating", {}, "busy");
  try {
    const resp = await postJSON("/api/generate", body, state.controller.signal);
    await readEvents(resp, (type, data) => handleEvent(type, data, run));
    if (run.finished) setStatus("status.done", { title: run.title }, "ok");
    else setStatus("status.error", {}, "error");
  } catch (err) {
    if (err.name === "AbortError") {
      setStatus("status.stopped", {}, "error");
      log(t("log.stopped"), "err");
    } else {
      setStatus("status.error", {}, "error");
      log(t("log.error", { message: err.message }), "err");
    }
  } finally {
    state.controller = null;
    setBusy(false);
    el.nextBtn.disabled = !run.hasNext;
  }
}

async function generateNextChapter() {
  const next = Number(el.chapterSelect.value || 0) + 1;
  if (next >= state.chapters.length) return;
  el.chapterSelect.value = String(next);
  await generate();
}

// ------------------------------------------------------------------ wiring

el.detectBtn.addEventListener("click", () => detectChapters());
el.generateBtn.addEventListener("click", generate);
el.nextBtn.addEventListener("click", generateNextChapter);
el.stopBtn.addEventListener("click", () => state.controller?.abort());
el.novel.addEventListener("input", scheduleDetect);
el.langBtn.addEventListener("click", () => {
  setLanguage(getLanguage() === "en" ? "zh" : "en");
  renderChapterOptions();
});

applyTranslations();
loadConfig();
