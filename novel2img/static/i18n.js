// UI strings. English is the default; to add a language, add a block with the same keys.
const MESSAGES = {
  en: {
    "lang.switch": "中文",
    "status.ready": "Ready",
    "status.detecting": "Detecting chapters…",
    "status.chapters": "{count} chapter(s)",
    "status.generating": "Generating…",
    "status.done": "Done: {title}",
    "status.stopped": "Stopped",
    "status.error": "Error",
    "empty.title": "Generated scenes will appear here.",
    "empty.hint": "Paste a chapter on the right, then click “Generate chapter”.",
    "field.style": "Style / adjustments (optional)",
    "field.stylePlaceholder": "e.g. watercolor, soft lighting; make the hero a silver-haired girl",
    "field.novel": "Novel text: one chapter or a whole book (chapters are detected automatically)",
    "field.novelPlaceholder": "Paste the novel text here…",
    "field.maxScenes": "Max scenes per chapter",
    "field.seed": "Seed (optional)",
    "field.seedPlaceholder": "random",
    "btn.detect": "Detect chapters",
    "btn.generate": "Generate chapter",
    "btn.next": "Next chapter →",
    "btn.stop": "Stop",
    "chapter.untitled": "Untitled",
    "chapter.option": "{title} ({length} chars)",
    "card.queued": "Queued…",
    "card.rendering": "Rendering…",
    "card.scene": "Scene {n}",
    "card.seed": "Seed {seed}",
    "card.showPrompt": "Show prompt",
    "card.hidePrompt": "Hide prompt",
    "stage.planning": "Planning scenes…",
    "stage.adjusting": "Applying your style description…",
    "stage.unloading_llm": "Freeing LLM memory…",
    "stage.loading_model": "Loading the image model (slow the first time)…",
    "stage.rendering": "Rendering image {n}/{total}…",
    "log.needText": "Paste some novel text first.",
    "log.chapters": "Found {count} chapter(s).",
    "log.chapter": "Chapter {n}/{total}: {title}",
    "log.scenes": "Planned {count} scene(s).",
    "log.adjusted": "Prompts adjusted to your style description.",
    "log.image": "✓ Scene {n} done (seed {seed})",
    "log.done": "Chapter finished.",
    "log.stopped": "Stopped.",
    "log.error": "Error: {message}",
  },
  zh: {
    "lang.switch": "English",
    "status.ready": "就绪",
    "status.detecting": "正在识别章节…",
    "status.chapters": "共 {count} 章",
    "status.generating": "生成中…",
    "status.done": "完成：{title}",
    "status.stopped": "已停止",
    "status.error": "出错",
    "empty.title": "生成的画面会显示在这里。",
    "empty.hint": "在右侧粘贴小说正文，然后点击「生成本章」。",
    "field.style": "风格 / 调整描述（可留空）",
    "field.stylePlaceholder": "例如：水彩画风，柔和光线；把主角改成银发少女",
    "field.novel": "小说正文：可粘贴单章或整本（自动识别章节）",
    "field.novelPlaceholder": "在此粘贴小说原文…",
    "field.maxScenes": "每章最多场景数",
    "field.seed": "种子（可留空）",
    "field.seedPlaceholder": "随机",
    "btn.detect": "识别章节",
    "btn.generate": "生成本章",
    "btn.next": "下一章 →",
    "btn.stop": "停止",
    "chapter.untitled": "未命名",
    "chapter.option": "{title}（{length} 字）",
    "card.queued": "排队中…",
    "card.rendering": "生成中…",
    "card.scene": "场景 {n}",
    "card.seed": "种子 {seed}",
    "card.showPrompt": "展开 prompt",
    "card.hidePrompt": "收起 prompt",
    "stage.planning": "正在切分场景…",
    "stage.adjusting": "正在按风格描述调整 prompt…",
    "stage.unloading_llm": "正在释放 LLM 内存…",
    "stage.loading_model": "正在加载图像模型（首次较慢）…",
    "stage.rendering": "正在生成第 {n}/{total} 张图…",
    "log.needText": "请先粘贴小说正文。",
    "log.chapters": "识别到 {count} 章。",
    "log.chapter": "第 {n}/{total} 章：{title}",
    "log.scenes": "切分为 {count} 个场景。",
    "log.adjusted": "已按风格描述调整 prompt。",
    "log.image": "✓ 场景 {n} 完成（种子 {seed}）",
    "log.done": "本章完成。",
    "log.stopped": "已停止。",
    "log.error": "错误：{message}",
  },
};

const STORAGE_KEY = "novel2img.lang";

let language = "en";
try {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved in MESSAGES) language = saved;
} catch {
  // storage unavailable (private mode, blocked cookies): stay in English
}

export const getLanguage = () => language;

export const hasMessage = (key) => key in MESSAGES.en;

export function t(key, params = {}) {
  const template = MESSAGES[language][key] ?? MESSAGES.en[key] ?? key;
  return template.replace(/\{(\w+)\}/g, (match, name) => (name in params ? String(params[name]) : match));
}

// Set an element's text to a message and remember the key, so a language switch updates it.
export function translate(element, key, params) {
  element.dataset.i18n = key;
  if (params) element.dataset.i18nParams = JSON.stringify(params);
  else delete element.dataset.i18nParams;
  element.textContent = t(key, params);
}

export function applyTranslations(root = document) {
  document.documentElement.lang = language === "zh" ? "zh-CN" : language;
  for (const element of root.querySelectorAll("[data-i18n]")) {
    const params = element.dataset.i18nParams ? JSON.parse(element.dataset.i18nParams) : {};
    element.textContent = t(element.dataset.i18n, params);
  }
  for (const element of root.querySelectorAll("[data-i18n-placeholder]")) {
    element.placeholder = t(element.dataset.i18nPlaceholder);
  }
}

export function setLanguage(next) {
  language = next in MESSAGES ? next : "en";
  try {
    localStorage.setItem(STORAGE_KEY, language);
  } catch {
    // not persisted; the choice still applies to this page
  }
  applyTranslations();
}
