import { useState, useEffect, useRef, useMemo } from "react";
import { createPortal } from "react-dom";
import {
  Undo,
  Redo,
  Bold,
  Italic,
  Underline as UnderlineIcon,
  Strikethrough,
  List,
  ListOrdered,
  Quote,
  Link as LinkIcon,
  Code,
  Heading1,
  Heading2,
  Heading3,
  Minus,
  Unlink,
} from "lucide-react";
import { extractStyleFromHtml } from "./extractStyle";
import { installPrintLayoutEmulation, paginateResumeDom } from "./domPagination";

interface EditableResumePreviewProps {
  initialHtml: string;
  onSave?: (html: string) => void;
  onSaveAs?: (html: string) => void;
  onChange?: (html: string) => void;
  onSelectionChange?: (text: string) => void;
  onReset?: () => void;
  placeholder?: string;
  className?: string;
  showSaveButton?: boolean;
  showResetButton?: boolean;
  showAutoSave?: boolean;
  /** When true, the Save button shows a spinner and is disabled. */
  saving?: boolean;
  /** Optional page-level mount point for the experience library panel. */
  libraryPortalTarget?: HTMLElement | null;
  /**
   * Called once when the iframe DOM is ready. The parent can use the
   * returned ref to perform imperative DOM operations (e.g. injecting
   * AI-rewritten text directly into the document).
   */
  onIframeReady?: (iframe: HTMLIFrameElement | null) => void;
}

export default function EditableResumePreview({
  initialHtml,
  onSave,
  onSaveAs,
  onChange,
  onSelectionChange,
  onReset,
  onIframeReady,
  placeholder = "开始编辑你的简历...",
  className = "",
  showSaveButton = true,
  showResetButton = true,
  showAutoSave = true,
  saving = false,
  libraryPortalTarget,
}: EditableResumePreviewProps) {
  const [currentHtml, setCurrentHtml] = useState(initialHtml);
  const [isDirty, setIsDirty] = useState(false);
  const [autoSaved, setAutoSaved] = useState<Date | null>(null);
  const debounceRef = useRef<number | null>(null);

  useEffect(() => {
    setIsDirty(currentHtml !== initialHtml);
  }, [currentHtml, initialHtml]);

  useEffect(() => {
    if (!isDirty || !showAutoSave) return;
    if (debounceRef.current) {
      window.clearTimeout(debounceRef.current);
    }
    debounceRef.current = window.setTimeout(() => {
      try {
        const key = `resume_edit_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
        localStorage.setItem(key, currentHtml);
        const allKeys = Object.keys(localStorage).filter((k) => k.startsWith("resume_edit_"));
        if (allKeys.length > 5) {
          allKeys
            .sort()
            .slice(0, allKeys.length - 5)
            .forEach((k) => localStorage.removeItem(k));
        }
        setAutoSaved(new Date());
      } catch (e) {
        console.warn("Auto-save failed:", e);
      }
    }, 1500);
    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
    };
  }, [currentHtml, isDirty, showAutoSave]);

  const handleChange = (html: string) => {
    setCurrentHtml(html);
    onChange?.(html);
  };

  const handleSave = () => {
    onSave?.(currentHtml);
  };

  const handleReset = () => {
    if (
      window.confirm(
        "确定要放弃所有修改，恢复到原始 LLM 生成的内容吗？"
      )
    ) {
      setCurrentHtml(initialHtml);
      onReset?.();
    }
  };

  return (
    <div className={className}>
      <EditableWYSIWYGEditor
        initialHtml={initialHtml}
        currentHtml={currentHtml}
        placeholder={placeholder}
        onChange={handleChange}
        onSelectionChange={onSelectionChange}
        onIframeReady={onIframeReady}
        libraryPortalTarget={libraryPortalTarget}
      />

      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400">
          {isDirty ? (
            <>
              <span className="inline-block h-2 w-2 rounded-full bg-amber-500" />
              <span>有未保存的修改</span>
            </>
          ) : (
            <>
              <span className="inline-block h-2 w-2 rounded-full bg-green-500" />
              <span>已是最新</span>
            </>
          )}
          {showAutoSave && autoSaved && (
            <span className="ml-2 text-gray-400 dark:text-gray-500">
              · 自动保存于 {autoSaved.toLocaleTimeString()}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {showResetButton && (
            <button
              type="button"
              onClick={handleReset}
              disabled={!isDirty}
              className="inline-flex items-center gap-1 rounded-lg border border-gray-300 bg-white px-3 py-1 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
              title="放弃修改，恢复原始"
            >
              ↻ 重置
            </button>
          )}
          {showSaveButton && onSave && (
            <>
              <button
                type="button"
                onClick={handleSave}
                disabled={!isDirty || saving}
                className="inline-flex items-center gap-1 rounded-lg bg-brand-600 px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
                title="覆盖保存到当前简历"
              >
                {saving ? "⏳ 保存中..." : "💾 保存"}
              </button>
              {onSaveAs && (
                <button
                  type="button"
                  onClick={() => onSaveAs(currentHtml)}
                  disabled={saving}
                  className="inline-flex items-center gap-1 rounded-lg border border-brand-300 bg-white px-3 py-1 text-xs font-medium text-brand-700 transition-colors hover:bg-brand-50 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-gray-800"
                  title="以当前名称创建新的简历文件"
                >
                  另存为
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------------
// WYSIWYG Editor using an iframe with designMode = "on"
// ----------------------------------------------------------------------------

function EditableWYSIWYGEditor({
  initialHtml,
  currentHtml,
  placeholder,
  onChange,
  onSelectionChange,
  onIframeReady,
  libraryPortalTarget,
}: {
  initialHtml: string;
  currentHtml: string;
  placeholder: string;
  onChange: (html: string) => void;
  onSelectionChange?: (text: string) => void;
  onIframeReady?: (iframe: HTMLIFrameElement | null) => void;
  libraryPortalTarget?: HTMLElement | null;
}) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const [isFocused, setIsFocused] = useState(false);
  const [isReady, setIsReady] = useState(false);
  const [lineHeight, setLineHeight] = useState(1.32);
  const [moduleSpacing, setModuleSpacing] = useState(8);
  const [libraryItems, setLibraryItems] = useState<ExperienceLibraryItem[]>([]);
  const initialBodyRef = useRef<string>("");
  const removedEntriesRef = useRef<RemovedExperienceRecord[]>([]);
  const lastSelectionRangeRef = useRef<Range | null>(null);

  const syncLibraryItems = () => {
    setLibraryItems(
      removedEntriesRef.current.map(({ id, category, title, summary }) => ({
        id,
        category,
        title,
        summary,
      })),
    );
  };

  const stripEditorState = (root: ParentNode) => {
    root
      .querySelectorAll("[data-buping-entry-action], [data-buping-module-action], [data-buping-empty-placeholder]")
      .forEach((el) => el.remove());
    root
      .querySelectorAll<HTMLElement>(
        "[data-buping-block], [data-buping-removable-entry], [data-buping-module], [data-buping-empty-field], [contenteditable]",
      )
      .forEach((el) => {
        el.removeAttribute("data-buping-block");
        el.removeAttribute("data-buping-removable-entry");
        el.removeAttribute("data-buping-module");
        el.removeAttribute("data-buping-empty-field");
        el.removeAttribute("contenteditable");
      });
    const rootElement = root as HTMLElement;
    if (typeof rootElement.removeAttribute === "function") {
      rootElement.removeAttribute("data-buping-block");
      rootElement.removeAttribute("data-buping-removable-entry");
      rootElement.removeAttribute("data-buping-module");
      rootElement.removeAttribute("contenteditable");
    }
  };

  const serializeDocument = (doc: Document) => {
    // Serialize a clone so editor-only affordances never leak into previews,
    // downloaded HTML, or PDFs. Layout controls intentionally remain because
    // line-height/module-spacing are user-visible document changes.
    const root = doc.documentElement.cloneNode(true) as HTMLElement;
    root.querySelector("#buping-editor-style")?.remove();
    root.querySelector("#buping-page-guide-style")?.remove();
    root.querySelector("#buping-page-guides")?.remove();
    root.querySelectorAll("[data-buping-page-break]").forEach((el) => el.remove());
    root.querySelector("#buping-print-layout-emulation")?.remove();
    root.querySelector("#buping-viewport-fit")?.remove();
    root.querySelector(`#${EXPERIENCE_LIBRARY_STORE_ID}`)?.remove();
    root
      .querySelectorAll('[data-buping-all-entries-removed="true"]')
      .forEach((section) => {
        section.removeAttribute("data-buping-all-entries-removed");
        section.setAttribute("data-buping-library-empty-section", "true");
        section.setAttribute("hidden", "");
      });
    stripEditorState(root);

    if (removedEntriesRef.current.length > 0) {
      const store = doc.createElement("div");
      store.id = EXPERIENCE_LIBRARY_STORE_ID;
      store.setAttribute("hidden", "");
      store.setAttribute("aria-hidden", "true");
      removedEntriesRef.current.forEach((record) => {
        const item = record.element.cloneNode(true) as HTMLElement;
        stripEditorState(item);
        item.setAttribute("data-buping-library-item", record.id);
        item.setAttribute("data-buping-library-section-id", record.sectionId);
        item.setAttribute("data-buping-library-category", record.category);
        item.setAttribute("data-buping-library-title", record.title);
        item.setAttribute("data-buping-library-summary", record.summary);
        item.setAttribute("data-buping-library-order", String(record.order));
        store.appendChild(item);
      });
      root.querySelector("body")?.appendChild(store);
    }
    const doctype = doc.doctype
      ? `<!DOCTYPE ${doc.doctype.name}>`
      : "<!DOCTYPE html>";
    return `${doctype}\n${root.outerHTML}`;
  };

  const emitDocumentChange = (doc: Document) => {
    onChange(serializeDocument(doc));
  };

  const normalizeResumeLists = (doc: Document) => {
    doc.querySelectorAll<HTMLElement>("section ul, section ol").forEach((list) => {
      if (!["compact-list", "stack-list", "inline-list"].some((name) => list.classList.contains(name))) {
        const section = list.closest("section");
        const reference = section?.querySelector<HTMLElement>(
          "ul.compact-list, ol.compact-list, ul.stack-list, ol.stack-list, ul.inline-list, ol.inline-list",
        );
        const layoutClasses = reference
          ? Array.from(reference.classList).filter((name) =>
              ["compact-list", "stack-list", "inline-list"].includes(name),
            )
          : ["compact-list"];
        list.classList.add(...layoutClasses);
      }

      // execCommand can produce invalid <p><ul>...</ul></p> markup. Move the
      // list beside that paragraph so browser/PDF layout stays deterministic.
      const paragraph = list.parentElement;
      if (paragraph?.tagName === "P" && paragraph.parentElement) {
        paragraph.parentElement.insertBefore(list, paragraph.nextSibling);
        if (!paragraph.textContent?.trim() && paragraph.children.length === 0) paragraph.remove();
      }
    });
  };

  const applyLayoutControls = (
    doc: Document,
    nextLineHeight = lineHeight,
    nextModuleSpacing = moduleSpacing,
  ) => {
    const spacing = nextModuleSpacing;
    const listSpacing = Math.max(1, Math.round(spacing / 4));
    const titleTop = Math.max(4, spacing + 2);
    const titleBottom = Math.max(2, Math.round(spacing / 2));
    const entryPaddingY = Math.max(4, Math.round(spacing * 0.75));
    const headerSpacing = Math.max(6, spacing + 2);

    let style = doc.getElementById("buping-layout-controls") as HTMLStyleElement | null;
    if (!style) {
      style = doc.createElement("style");
      style.id = "buping-layout-controls";
      doc.head.appendChild(style);
    }
    style.dataset.lineHeight = String(nextLineHeight);
    style.dataset.moduleSpacing = String(nextModuleSpacing);

    style.textContent = `
      body {
        line-height: ${nextLineHeight} !important;
      }
      header {
        margin-bottom: ${headerSpacing}px !important;
      }
      h2 {
        margin-top: ${titleTop}px !important;
        margin-bottom: ${titleBottom}px !important;
      }
      .entry,
      .resume-card {
        margin-bottom: ${spacing}px !important;
        padding-top: ${entryPaddingY}px !important;
        padding-bottom: ${entryPaddingY}px !important;
      }
      .compact-list,
      .stack-list,
      .inline-list {
        margin-top: ${listSpacing}px !important;
        margin-bottom: ${listSpacing}px !important;
      }
      .compact-list li,
      .stack-list li,
      .inline-list li {
        margin-bottom: ${listSpacing}px !important;
      }
    `;
  };

  const readSavedLayoutControls = (doc: Document) => {
    const style = doc.getElementById("buping-layout-controls") as HTMLStyleElement | null;
    if (!style) {
      const view = doc.defaultView;
      const bodyStyle = view && doc.body ? view.getComputedStyle(doc.body) : null;
      const fontSize = Number.parseFloat(bodyStyle?.fontSize || "");
      const lineHeightPx = Number.parseFloat(bodyStyle?.lineHeight || "");
      const computedLineHeight = fontSize > 0 && lineHeightPx > 0
        ? lineHeightPx / fontSize
        : 1.32;
      const firstEntry = doc.querySelector<HTMLElement>(".entry, .resume-card");
      const computedModuleSpacing = firstEntry && view
        ? Number.parseFloat(view.getComputedStyle(firstEntry).marginBottom)
        : Number.NaN;
      return {
        savedLineHeight: Math.min(1.7, Math.max(1.1, computedLineHeight)),
        savedModuleSpacing: Number.isFinite(computedModuleSpacing)
          ? Math.min(20, Math.max(2, computedModuleSpacing))
          : 8,
        hasSavedLayoutControls: false,
      };
    }

    const lineHeightFromData = style.dataset.lineHeight
      ? Number(style.dataset.lineHeight)
      : Number.NaN;
    const moduleSpacingFromData = style.dataset.moduleSpacing
      ? Number(style.dataset.moduleSpacing)
      : Number.NaN;
    const lineHeightFromCss = Number(
      style.textContent.match(/body\s*\{[^}]*line-height:\s*([0-9.]+)/s)?.[1],
    );
    const moduleSpacingFromCss = Number(
      style.textContent.match(/\.entry[\s\S]*?margin-bottom:\s*([0-9.]+)px/)?.[1],
    );

    return {
      savedLineHeight:
        lineHeightFromData > 0 ? lineHeightFromData : lineHeightFromCss > 0 ? lineHeightFromCss : 1.32,
      savedModuleSpacing:
        moduleSpacingFromData >= 0
          ? moduleSpacingFromData
          : moduleSpacingFromCss >= 0
            ? moduleSpacingFromCss
            : 8,
      hasSavedLayoutControls: true,
    };
  };

  const updateLayoutControl = (nextLineHeight: number, nextModuleSpacing: number) => {
    setLineHeight(nextLineHeight);
    setModuleSpacing(nextModuleSpacing);

    const iframe = iframeRef.current;
    const doc = iframe?.contentDocument;
    if (!doc) return;

    applyLayoutControls(doc, nextLineHeight, nextModuleSpacing);
    window.requestAnimationFrame(() => paginateResumeDom(doc));
    emitDocumentChange(doc);
  };

  const refreshSectionEmptyState = (section: HTMLElement) => {
    section.querySelectorAll("[data-buping-empty-placeholder]").forEach((el) => el.remove());
    const remaining = section.querySelector(
      ":scope > .entry, :scope > .resume-card, :scope > [data-buping-removable-entry]",
    );
    if (remaining) {
      section.removeAttribute("data-buping-all-entries-removed");
      return;
    }
    section.setAttribute("data-buping-all-entries-removed", "true");
    const placeholder = section.ownerDocument.createElement("div");
    placeholder.setAttribute("data-buping-empty-placeholder", "true");
    placeholder.setAttribute("contenteditable", "false");
    placeholder.textContent = "该模块中的经历已全部撤下，可从右侧经历库重新加入";
    section.appendChild(placeholder);
  };

  const getExperienceMeta = (entry: HTMLElement, section: HTMLElement) => {
    const sectionId = section.id;
    const category: ExperienceCategory = sectionId === "education"
      ? "education"
      : sectionId === "work-experience"
        ? "work"
        : "project";
    const preferredTitle = entry.querySelector<HTMLElement>(
      "h3, h4, .entry-title, .entry-header strong, strong",
    )?.innerText.trim();
    const text = entry.innerText.replace(/\s+/g, " ").trim();
    return {
      sectionId,
      category,
      title: preferredTitle || text.slice(0, 42) || "未命名经历",
      summary: text.slice(0, 90),
    };
  };

  const refreshEntryActionStates = (parent: HTMLElement) => {
    const entries = Array.from(
      parent.querySelectorAll<HTMLElement>(":scope > [data-buping-removable-entry]"),
    );
    entries.forEach((entry, index) => {
      const up = entry.querySelector<HTMLButtonElement>('[data-buping-entry-action="move-up"]');
      const down = entry.querySelector<HTMLButtonElement>('[data-buping-entry-action="move-down"]');
      if (up) up.disabled = index === 0;
      if (down) down.disabled = index === entries.length - 1;
    });
  };

  const moveResumeEntry = (entry: HTMLElement, direction: -1 | 1) => {
    const parent = entry.parentElement;
    if (!parent) return;
    const entries = Array.from(
      parent.querySelectorAll<HTMLElement>(":scope > [data-buping-removable-entry]"),
    );
    const index = entries.indexOf(entry);
    const target = entries[index + direction];
    if (index < 0 || !target) return;
    if (direction < 0) parent.insertBefore(entry, target);
    else parent.insertBefore(target, entry);
    refreshEntryActionStates(parent);
    emitDocumentChange(entry.ownerDocument);
    window.requestAnimationFrame(() => paginateResumeDom(entry.ownerDocument));
  };

  const removeResumeEntry = (entry: HTMLElement) => {
    const doc = entry.ownerDocument;
    const parent = entry.parentElement;
    const section = entry.closest<HTMLElement>("section");
    if (!parent || !section) return;
    const entries = Array.from(parent.querySelectorAll<HTMLElement>(":scope > .entry, :scope > .resume-card"));
    removedEntriesRef.current.push({
      id: `experience-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      element: entry,
      parent,
      nextSibling: entry.nextSibling,
      ...getExperienceMeta(entry, section),
      order: Math.max(0, entries.indexOf(entry)),
    });
    entry.remove();
    syncLibraryItems();
    refreshEntryActionStates(parent);
    refreshSectionEmptyState(section);
    emitDocumentChange(doc);
    window.requestAnimationFrame(() => paginateResumeDom(doc));
  };

  const decorateRemovableEntries = (doc: Document) => {
    const selectors = [
      "#education > .entry",
      "#education > .resume-card",
      "#work-experience > .entry",
      "#work-experience > .resume-card",
      "#side-projects > .entry",
      "#side-projects > .resume-card",
      "#projects > .entry",
      "#projects > .resume-card",
    ].join(",");
    doc.querySelectorAll<HTMLElement>(selectors).forEach((entry) => {
      if (entry.hasAttribute("data-buping-removable-entry")) return;
      entry.setAttribute("data-buping-removable-entry", "true");
      const actions = doc.createElement("div");
      actions.setAttribute("data-buping-entry-action", "group");
      actions.setAttribute("contenteditable", "false");
      const definitions = [
        { action: "move-up", text: "↑", title: "上移这段经历" },
        { action: "move-down", text: "↓", title: "下移这段经历" },
        { action: "remove", text: "撤下", title: "撤下到右侧经历库" },
      ] as const;
      definitions.forEach(({ action, text, title }) => {
        const button = doc.createElement("button");
        button.type = "button";
        button.setAttribute("data-buping-entry-action", action);
        button.setAttribute("contenteditable", "false");
        button.setAttribute("aria-label", title);
        button.title = title;
        button.textContent = text;
        button.addEventListener("mousedown", (event) => {
          event.preventDefault();
          event.stopPropagation();
        });
        button.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          if (action === "move-up") moveResumeEntry(entry, -1);
          else if (action === "move-down") moveResumeEntry(entry, 1);
          else removeResumeEntry(entry);
        });
        actions.appendChild(button);
      });
      entry.appendChild(actions);
    });
    ["education", "work-experience", "side-projects", "projects"].forEach((id) => {
      const section = doc.getElementById(id);
      if (section) refreshEntryActionStates(section);
    });
  };

  const decorateEditableModules = (doc: Document) => {
    let modules = Array.from(doc.body.querySelectorAll<HTMLElement>("header, section"));
    if (modules.length === 0) {
      modules = Array.from(doc.body.children).filter(
        (el) => !["SCRIPT", "STYLE", "LINK"].includes(el.tagName),
      ) as HTMLElement[];
    }
    modules.forEach((el) => {
      el.setAttribute("data-buping-block", "true");
      el.setAttribute("contenteditable", "false");
    });
    decorateModuleActions(doc);
  };

  const movableModules = (doc: Document) => {
    const main = doc.body.querySelector("main");
    if (main) return Array.from(main.querySelectorAll<HTMLElement>(":scope > section"));
    return Array.from(doc.body.querySelectorAll<HTMLElement>(":scope > section"));
  };

  const refreshModuleActionStates = (doc: Document) => {
    const modules = movableModules(doc);
    modules.forEach((module, index) => {
      const up = module.querySelector<HTMLButtonElement>(':scope > [data-buping-module-action="group"] [data-action="move-up"]');
      const down = module.querySelector<HTMLButtonElement>(':scope > [data-buping-module-action="group"] [data-action="move-down"]');
      if (up) up.disabled = index === 0;
      if (down) down.disabled = index === modules.length - 1;
    });
  };

  const moveResumeModule = (module: HTMLElement, direction: -1 | 1) => {
    const doc = module.ownerDocument;
    const modules = movableModules(doc);
    const index = modules.indexOf(module);
    const target = modules[index + direction];
    const parent = module.parentElement;
    if (index < 0 || !target || !parent || parent !== target.parentElement) return;
    if (direction < 0) parent.insertBefore(module, target);
    else parent.insertBefore(target, module);
    refreshModuleActionStates(doc);
    emitDocumentChange(doc);
    window.requestAnimationFrame(() => paginateResumeDom(doc));
  };

  const removeResumeModule = (module: HTMLElement) => {
    const doc = module.ownerDocument;
    module.remove();
    refreshModuleActionStates(doc);
    emitDocumentChange(doc);
    window.requestAnimationFrame(() => paginateResumeDom(doc));
  };

  const addResumeModuleAfter = (module: HTMLElement) => {
    const doc = module.ownerDocument;
    const section = doc.createElement("section");
    section.id = `custom-section-${Date.now()}`;
    section.innerHTML = "<h2>新模块</h2><p>点击这里填写内容</p>";
    module.insertAdjacentElement("afterend", section);
    decorateEditableModules(doc);
    refreshModuleActionStates(doc);
    emitDocumentChange(doc);
    window.requestAnimationFrame(() => paginateResumeDom(doc));
  };

  type ManualExperienceType = "education" | "work" | "internship" | "project";

  const addManualExperience = (section: HTMLElement, type: ManualExperienceType) => {
    const doc = section.ownerDocument;
    const entry = doc.createElement("div");
    entry.className = "entry";

    if (type === "education") {
      entry.innerHTML = `
        <div class="entry-header">
          <span class="entry-name">学校名称</span>
          <span class="entry-location">城市</span>
        </div>
        <div class="entry-details">
          <span class="entry-title">学历 · 专业</span>
          <span class="entry-year" data-buping-empty-field="时间段（选填）"></span>
        </div>
        <ul class="compact-list"><li>补充课程、研究方向、荣誉或其他教育信息</li></ul>`;
    } else if (type === "project") {
      entry.innerHTML = `
        <div class="entry-header">
          <span class="entry-name">项目名称</span>
          <span class="entry-tech">技术栈 / 项目角色</span>
        </div>
        <div class="entry-details">
          <span class="entry-title">项目经历</span>
          <span class="entry-year" data-buping-empty-field="时间段（选填）"></span>
        </div>
        <ul class="compact-list">
          <li><strong>项目背景：</strong>填写项目目标与背景</li>
          <li><strong>个人职责：</strong>填写你负责的工作与成果</li>
        </ul>`;
    } else {
      const isInternship = type === "internship";
      entry.innerHTML = `
        <div class="entry-header">
          <span class="entry-name">公司或组织名称</span>
          <span class="entry-location">城市</span>
        </div>
        <div class="entry-details">
          <span class="entry-title">${isInternship ? "实习岗位" : "工作岗位"}</span>
          <span class="entry-year" data-buping-empty-field="时间段（选填）"></span>
        </div>
        <ul class="compact-list">
          <li><strong>核心职责：</strong>填写工作内容、行动与结果</li>
          <li><strong>实践成果：</strong>填写可核验或可量化的成果</li>
        </ul>`;
    }

    section.removeAttribute("hidden");
    section.removeAttribute("data-buping-library-empty-section");
    section.querySelectorAll("[data-buping-empty-placeholder]").forEach((element) => element.remove());
    const moduleActions = section.querySelector(':scope > [data-buping-module-action="group"]');
    if (moduleActions) section.insertBefore(entry, moduleActions);
    else section.appendChild(entry);
    decorateRemovableEntries(doc);
    refreshSectionEmptyState(section);
    section.setAttribute("contenteditable", "true");
    emitDocumentChange(doc);
    window.requestAnimationFrame(() => paginateResumeDom(doc));
  };

  const decorateModuleActions = (doc: Document) => {
    movableModules(doc).forEach((module) => {
      module.setAttribute("data-buping-module", "true");
      if (module.querySelector(':scope > [data-buping-module-action="group"]')) return;
      const actions = doc.createElement("div");
      actions.setAttribute("data-buping-module-action", "group");
      actions.setAttribute("contenteditable", "false");
      const definitions: Array<{ action: string; text: string; title: string }> = [
        { action: "move-up", text: "↑", title: "上移整个模块" },
        { action: "move-down", text: "↓", title: "下移整个模块" },
      ];
      if (module.id === "education") {
        definitions.push({ action: "add-education", text: "+ 教育", title: "添加一段教育经历（含时间段）" });
      } else if (module.id === "work-experience") {
        definitions.push(
          { action: "add-work", text: "+ 工作", title: "添加一段工作经历（含时间段）" },
          { action: "add-internship", text: "+ 实习", title: "添加一段实习经历（含时间段）" },
        );
      } else if (module.id === "side-projects" || module.id === "projects") {
        definitions.push({ action: "add-project", text: "+ 项目", title: "添加一段项目经历（含时间段）" });
      }
      definitions.push(
        { action: "add", text: "+ 模块", title: "在下方添加新模块" },
        { action: "remove", text: "删除", title: "删除整个模块" },
      );
      definitions.forEach(({ action, text, title }) => {
        const button = doc.createElement("button");
        button.type = "button";
        button.dataset.action = action;
        button.title = title;
        button.setAttribute("aria-label", title);
        button.textContent = text;
        button.addEventListener("mousedown", (event) => {
          event.preventDefault();
          event.stopPropagation();
        });
        button.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          if (action === "move-up") moveResumeModule(module, -1);
          else if (action === "move-down") moveResumeModule(module, 1);
          else if (action === "add-education") addManualExperience(module, "education");
          else if (action === "add-work") addManualExperience(module, "work");
          else if (action === "add-internship") addManualExperience(module, "internship");
          else if (action === "add-project") addManualExperience(module, "project");
          else if (action === "add") addResumeModuleAfter(module);
          else removeResumeModule(module);
        });
        actions.appendChild(button);
      });
      module.appendChild(actions);
    });
    refreshModuleActionStates(doc);
  };

  const restoreLibraryEntry = (id: string) => {
    const index = removedEntriesRef.current.findIndex((record) => record.id === id);
    const removed = index >= 0 ? removedEntriesRef.current[index] : undefined;
    if (!removed) return;
    removedEntriesRef.current.splice(index, 1);
    const doc = removed.parent.ownerDocument;
    if (removed.nextSibling?.parentNode === removed.parent) {
      removed.parent.insertBefore(removed.element, removed.nextSibling);
    } else {
      removed.parent.appendChild(removed.element);
    }
    removed.element.removeAttribute("data-buping-removable-entry");
    decorateRemovableEntries(doc);
    const section = removed.element.closest<HTMLElement>("section");
    if (section) refreshSectionEmptyState(section);
    refreshEntryActionStates(removed.parent);
    syncLibraryItems();
    emitDocumentChange(doc);
    window.requestAnimationFrame(() => paginateResumeDom(doc));
  };

  const undoRemovedEntry = () => {
    const latest = removedEntriesRef.current[removedEntriesRef.current.length - 1];
    if (latest) restoreLibraryEntry(latest.id);
  };

  const hydrateExperienceLibrary = (doc: Document) => {
    removedEntriesRef.current = [];
    doc.querySelectorAll<HTMLElement>('[data-buping-library-empty-section="true"]').forEach((section) => {
      section.hidden = false;
      section.removeAttribute("data-buping-library-empty-section");
      section.setAttribute("data-buping-all-entries-removed", "true");
    });
    const store = doc.getElementById(EXPERIENCE_LIBRARY_STORE_ID);
    store?.querySelectorAll<HTMLElement>("[data-buping-library-item]").forEach((item) => {
      const sectionId = item.dataset.bupingLibrarySectionId || "";
      const parent = doc.getElementById(sectionId);
      if (!parent) return;
      const element = item.cloneNode(true) as HTMLElement;
      [
        "data-buping-library-item",
        "data-buping-library-section-id",
        "data-buping-library-category",
        "data-buping-library-title",
        "data-buping-library-summary",
        "data-buping-library-order",
      ].forEach((attribute) => element.removeAttribute(attribute));
      removedEntriesRef.current.push({
        id: item.dataset.bupingLibraryItem || `experience-${Date.now()}-${Math.random()}`,
        element,
        parent,
        nextSibling: null,
        sectionId,
        category: (item.dataset.bupingLibraryCategory as ExperienceCategory) || "project",
        title: item.dataset.bupingLibraryTitle || "未命名经历",
        summary: item.dataset.bupingLibrarySummary || "",
        order: Number(item.dataset.bupingLibraryOrder || 0),
      });
    });
    store?.remove();
    syncLibraryItems();
    doc.querySelectorAll<HTMLElement>('[data-buping-all-entries-removed="true"]').forEach((section) =>
      refreshSectionEmptyState(section),
    );
  };

  // Expose the iframe ref to the parent via the onIframeReady callback.
  // (We can't use forwardRef here because the parent component already
  // uses forwardRef internally — keeping it simple by calling back.)
  useEffect(() => {
    onIframeReady?.(iframeRef.current);
    return () => onIframeReady?.(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [iframeRef.current]);

  // Build the iframe srcdoc on mount/initial change
  const srcdoc = useMemo(() => {
    if (!initialHtml) {
      // Provide a minimal empty template so the iframe still loads
      return `<!DOCTYPE html><html><head><style>body{padding:20px;font-family:sans-serif;}</style></head><body><p>${placeholder}</p></body></html>`;
    }
    // Embed the FULL HTML document — the original CSS will be loaded as-is.
    // The iframe sandbox gives us perfect style isolation.
    return initialHtml;
  }, [initialHtml, placeholder]);

  // After iframe loads, set up module-scoped editing.
  //
  // Strategy: instead of `designMode = "on"` (which makes the whole
  // document editable), we make resume modules (header/section) editable.
  // A module can contain multiple paragraphs/list items, so users can select
  // and edit several bullets in one operation without crossing the whole CV.
  const handleIframeLoad = () => {
    const iframe = iframeRef.current;
    if (!iframe) return;
    try {
      const doc = iframe.contentDocument;
      if (!doc) return;
      // Notify parent again (in case iframe DOM changed after first mount)
      onIframeReady?.(iframe);

      // Make the whole document non-editable by default.
      doc.designMode = "off";
      doc.body.setAttribute("contenteditable", "false");
      lastSelectionRangeRef.current = null;

      // Save body innerHTML for reset
      initialBodyRef.current = doc.body?.innerHTML || "";

      // Restore saved layout values before applying editor controls. Without
      // this, opening a saved resume would overwrite its CSS with defaults.
      const {
        savedLineHeight,
        savedModuleSpacing,
        hasSavedLayoutControls,
      } = readSavedLayoutControls(doc);
      setLineHeight(savedLineHeight);
      setModuleSpacing(savedModuleSpacing);

      // Inject base styles + active-block highlight
      doc.getElementById("buping-editor-style")?.remove();
      const style = doc.createElement("style");
      style.id = "buping-editor-style";
      style.textContent = `
        body { cursor: default; }
        /* Modules are clickable but not editable until clicked */
        [data-buping-block] {
          cursor: pointer;
          transition: outline-color 0.15s ease;
          outline: 2px dashed transparent;
          outline-offset: 2px;
          border-radius: 2px;
        }
        [data-buping-block]:hover {
          outline-color: rgba(20, 184, 166, 0.35);
        }
        [data-buping-block][contenteditable="true"] {
          cursor: text;
          outline: 2px solid rgba(20, 184, 166, 0.6);
          outline-offset: 2px;
        }
        [contenteditable="true"]:focus { outline: none; }
        ::selection { background: rgba(20, 184, 166, 0.3); }
        [data-buping-removable-entry] { position: relative; }
        [data-buping-entry-action="group"] {
          position: absolute;
          top: 2px;
          right: 2px;
          z-index: 20;
          border-radius: 5px;
          background: rgba(255, 255, 255, 0.96);
          display: flex;
          overflow: hidden;
          opacity: 0;
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
          transition: opacity 0.15s;
        }
        [data-buping-entry-action="group"] > button {
          min-width: 26px;
          border: 1px solid rgba(107, 114, 128, 0.3);
          border-right: 0;
          background: transparent;
          color: #374151;
          padding: 2px 6px;
          font: 600 11px/1.5 system-ui, sans-serif;
          cursor: pointer;
        }
        [data-buping-entry-action="group"] > button:last-child {
          border-right: 1px solid rgba(220, 38, 38, 0.35);
          color: #b91c1c;
        }
        [data-buping-entry-action="group"] > button:disabled {
          cursor: not-allowed;
          opacity: 0.3;
        }
        [data-buping-removable-entry]:hover > [data-buping-entry-action="group"],
        [data-buping-entry-action="group"]:focus-within {
          opacity: 1;
        }
        [data-buping-entry-action="group"] > button:hover:not(:disabled) { background: #f3f4f6; }
        [data-buping-entry-action="group"] > button:last-child:hover { background: #fef2f2; }
        [data-buping-module] { position: relative; }
        [data-buping-module-action="group"] {
          position: absolute;
          top: 0;
          right: 0;
          transform: translateY(-100%);
          z-index: 21;
          display: flex;
          gap: 2px;
          opacity: 0;
          transition: opacity 0.15s;
        }
        [data-buping-module]:hover > [data-buping-module-action="group"],
        [data-buping-module-action="group"]:focus-within { opacity: 1; }
        [data-buping-module-action="group"] button {
          border: 1px solid rgba(20, 184, 166, 0.45);
          border-radius: 5px;
          background: rgba(240, 253, 250, 0.97);
          color: #0f766e;
          padding: 2px 6px;
          font: 600 10px/1.5 system-ui, sans-serif;
          cursor: pointer;
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
        }
        [data-buping-module-action="group"] button:disabled { cursor: not-allowed; opacity: 0.3; }
        [data-buping-module-action="group"] button[data-action="remove"] {
          border-color: rgba(220, 38, 38, 0.4);
          background: rgba(254, 242, 242, 0.97);
          color: #b91c1c;
        }
        [data-buping-empty-field]:empty::before {
          content: attr(data-buping-empty-field);
          color: #9ca3af;
          font-style: italic;
        }
        [data-buping-empty-placeholder] {
          margin: 8px 0;
          border: 1px dashed rgba(107, 114, 128, 0.45);
          border-radius: 6px;
          padding: 12px;
          color: #6b7280;
          background: rgba(249, 250, 251, 0.92);
          font: 13px/1.5 system-ui, sans-serif;
          text-align: center;
        }
      `;
      doc.head.appendChild(style);
      // A newly generated resume must keep the template's original layout so
      // editor pagination stays identical to preview/PDF. Only re-apply this
      // override when the user previously saved explicit layout controls.
      if (hasSavedLayoutControls) {
        applyLayoutControls(doc, savedLineHeight, savedModuleSpacing);
      }
      normalizeResumeLists(doc);
      installPrintLayoutEmulation(doc);
      window.requestAnimationFrame(() => paginateResumeDom(doc));
      void doc.fonts?.ready.then(() => paginateResumeDom(doc));

      // Prefer semantic resume modules. For older/custom templates without
      // header/section elements, fall back to direct body children.
      hydrateExperienceLibrary(doc);
      decorateEditableModules(doc);
      decorateRemovableEntries(doc);

      // Helper: activate a single block (make it editable, deactivate others)
      const activateBlock = (el: HTMLElement) => {
        doc.body
          .querySelectorAll<HTMLElement>('[data-buping-block="true"]')
          .forEach((other) => other.setAttribute("contenteditable", "false"));
        el.setAttribute("contenteditable", "true");
      };

      // Activate before the browser starts a drag selection. Avoid calling
      // focus() here because that would collapse a multi-item selection.
      doc.body.addEventListener("mousedown", (e) => {
        const target = e.target as HTMLElement;
        const block = target.closest<HTMLElement>('[data-buping-block="true"]');
        if (block) {
          activateBlock(block);
        }
      });

      // Hook input event to capture HTML changes (bubbles up from any block)
      doc.addEventListener("input", () => {
        emitDocumentChange(doc);
        window.setTimeout(() => paginateResumeDom(doc), 300);
      });

      // Selection change for AI rewrite feature
      doc.addEventListener("selectionchange", () => {
        const sel = doc.getSelection();
        if (sel && sel.rangeCount > 0 && !sel.isCollapsed) {
          lastSelectionRangeRef.current = sel.getRangeAt(0).cloneRange();
        }
        if (!onSelectionChange) return;
        const text = sel ? sel.toString() : "";
        onSelectionChange(text);
      });

      // Track focus on the iframe document
      doc.addEventListener("focus", () => setIsFocused(true), true);
      doc.addEventListener("blur", () => setIsFocused(false), true);
      doc.defaultView?.addEventListener("resize", () => {
        window.requestAnimationFrame(() => paginateResumeDom(doc));
      });

      setIsReady(true);
    } catch (e) {
      console.error("Failed to initialize editable iframe:", e);
    }
  };

  // Handle toolbar commands by talking to the iframe document
  const exec = (command: string, value?: string) => {
    const iframe = iframeRef.current;
    if (!iframe) return;
    const doc = iframe.contentDocument;
    if (!doc) return;
    doc.execCommand(command, false, value);
    if (command === "insertUnorderedList" || command === "insertOrderedList") {
      normalizeResumeLists(doc);
    }
    // Trigger an input event so React state updates
    emitDocumentChange(doc);
    window.requestAnimationFrame(() => paginateResumeDom(doc));
  };

  const deleteLibraryEntry = (id: string) => {
    const index = removedEntriesRef.current.findIndex((record) => record.id === id);
    const removed = index >= 0 ? removedEntriesRef.current[index] : undefined;
    if (!removed) return;
    if (!window.confirm(`确定永久删除经历“${removed.title}”吗？删除后无法从经历库恢复。`)) return;
    removedEntriesRef.current.splice(index, 1);
    syncLibraryItems();
    const doc = removed.parent.ownerDocument;
    emitDocumentChange(doc);
  };

  const restoreTextSelection = (doc: Document) => {
    const range = lastSelectionRangeRef.current;
    const selection = doc.getSelection();
    if (!range || !selection || !doc.contains(range.commonAncestorContainer)) return false;
    selection.removeAllRanges();
    selection.addRange(range);
    return true;
  };

  const applyFontFamily = (fontFamily: string) => {
    const doc = iframeRef.current?.contentDocument;
    if (!doc || !fontFamily || !restoreTextSelection(doc)) return;
    doc.execCommand("fontName", false, fontFamily);
    emitDocumentChange(doc);
    window.requestAnimationFrame(() => paginateResumeDom(doc));
  };

  const applyFontSize = (fontSizePx: number) => {
    const doc = iframeRef.current?.contentDocument;
    if (!doc || !restoreTextSelection(doc)) return;

    // Normalize legacy <font size="…"> elements before using execCommand as
    // a cross-node selection wrapper. The new wrapper is immediately changed
    // to an exact pixel size, so saved HTML and PDF keep the chosen value.
    doc.querySelectorAll<HTMLElement>("font[size]").forEach((font) => {
      const computedSize = doc.defaultView?.getComputedStyle(font).fontSize;
      if (computedSize) font.style.fontSize = computedSize;
      font.removeAttribute("size");
    });
    doc.execCommand("fontSize", false, "7");
    doc.querySelectorAll<HTMLElement>('font[size="7"]').forEach((font) => {
      font.style.fontSize = `${fontSizePx}px`;
      font.removeAttribute("size");
    });
    emitDocumentChange(doc);
    window.requestAnimationFrame(() => paginateResumeDom(doc));
  };

  const handleLink = () => {
    const iframe = iframeRef.current;
    if (!iframe) return;
    const doc = iframe.contentDocument;
    if (!doc) return;
    const previousUrl = doc.queryCommandValue("createLink");
    const url = window.prompt("链接地址", previousUrl || "https://");
    if (url === null) return; // cancelled
    if (url === "") {
      doc.execCommand("unlink", false);
    } else {
      doc.execCommand("createLink", false, url);
    }
    emitDocumentChange(doc);
  };

  // Public reset: rewrite iframe body to the original
  const resetContent = () => {
    const iframe = iframeRef.current;
    if (!iframe) return;
    const doc = iframe.contentDocument;
    if (!doc) return;
    doc.body.innerHTML = initialBodyRef.current;
    lastSelectionRangeRef.current = null;
    hydrateExperienceLibrary(doc);
    decorateEditableModules(doc);
    decorateRemovableEntries(doc);
    applyLayoutControls(doc);
    window.requestAnimationFrame(() => paginateResumeDom(doc));
    emitDocumentChange(doc);
  };

  // Expose resetContent via global so external Reset button can use it
  // (we keep it minimal — the parent component calls handleReset which re-renders)
  // The actual reset happens by reloading the iframe srcdoc.

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center gap-0.5 rounded-t-lg border border-b-0 border-gray-200 bg-gray-50 px-2 py-1.5 dark:border-gray-600 dark:bg-gray-900">
        <ToolButton title="撤销 (Ctrl+Z)" onClick={() => exec("undo")}>
          <Undo className="h-4 w-4" />
        </ToolButton>
        <ToolButton title="重做 (Ctrl+Y)" onClick={() => exec("redo")}>
          <Redo className="h-4 w-4" />
        </ToolButton>
        <ToolButton
          title="恢复上次撤下的教育、工作或项目经历"
          onClick={undoRemovedEntry}
          disabled={libraryItems.length === 0}
        >
          <span className="text-[10px]">恢复</span>
        </ToolButton>
        <Divider />
        <ToolButton title="一级标题" onClick={() => exec("formatBlock", "h1")}>
          <Heading1 className="h-4 w-4" />
        </ToolButton>
        <ToolButton title="二级标题" onClick={() => exec("formatBlock", "h2")}>
          <Heading2 className="h-4 w-4" />
        </ToolButton>
        <ToolButton title="三级标题" onClick={() => exec("formatBlock", "h3")}>
          <Heading3 className="h-4 w-4" />
        </ToolButton>
        <Divider />
        <select
          defaultValue=""
          title="先选择文字，再设置字体"
          aria-label="字体"
          onChange={(event) => {
            applyFontFamily(event.target.value);
            event.currentTarget.value = "";
          }}
          className="h-8 w-24 rounded border border-gray-200 bg-white px-1.5 text-xs text-gray-700 focus:border-brand-500 focus:outline-none dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
        >
          <option value="" disabled>字体</option>
          {FONT_FAMILY_OPTIONS.map((font) => (
            <option key={font.value} value={font.value}>{font.label}</option>
          ))}
        </select>
        <select
          defaultValue=""
          title="先选择文字，再设置精确字号"
          aria-label="字号"
          onChange={(event) => {
            applyFontSize(Number(event.target.value));
            event.currentTarget.value = "";
          }}
          className="h-8 w-[74px] rounded border border-gray-200 bg-white px-1.5 text-xs text-gray-700 focus:border-brand-500 focus:outline-none dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
        >
          <option value="" disabled>字号</option>
          {FONT_SIZE_OPTIONS.map((size) => (
            <option key={size} value={size}>{size}px</option>
          ))}
        </select>
        <Divider />
        <ToolButton title="粗体 (Ctrl+B)" onClick={() => exec("bold")}>
          <Bold className="h-4 w-4" />
        </ToolButton>
        <ToolButton title="斜体 (Ctrl+I)" onClick={() => exec("italic")}>
          <Italic className="h-4 w-4" />
        </ToolButton>
        <ToolButton title="下划线 (Ctrl+U)" onClick={() => exec("underline")}>
          <UnderlineIcon className="h-4 w-4" />
        </ToolButton>
        <ToolButton title="删除线" onClick={() => exec("strikeThrough")}>
          <Strikethrough className="h-4 w-4" />
        </ToolButton>
        <Divider />
        <ToolButton title="无序列表" onClick={() => exec("insertUnorderedList")}>
          <List className="h-4 w-4" />
        </ToolButton>
        <ToolButton title="有序列表" onClick={() => exec("insertOrderedList")}>
          <ListOrdered className="h-4 w-4" />
        </ToolButton>
        <ToolButton title="引用" onClick={() => exec("formatBlock", "blockquote")}>
          <Quote className="h-4 w-4" />
        </ToolButton>
        <ToolButton title="分隔线" onClick={() => exec("insertHorizontalRule")}>
          <Minus className="h-4 w-4" />
        </ToolButton>
        <Divider />
        <ToolButton title="添加链接" onClick={handleLink}>
          <LinkIcon className="h-4 w-4" />
        </ToolButton>
        <ToolButton title="清除格式" onClick={() => exec("removeFormat")}>
          <span className="text-[10px] font-bold">Tx</span>
        </ToolButton>
        <Divider />
        <div className="flex items-center gap-2 px-2 text-xs text-gray-600 dark:text-gray-300">
          <label className="flex items-center gap-1" title="调整正文行间距">
            <span>行距</span>
            <input
              type="range"
              min="1.1"
              max="1.7"
              step="0.02"
              value={lineHeight}
              onChange={(e) => updateLayoutControl(Number(e.target.value), moduleSpacing)}
              className="w-24 accent-brand-600"
            />
            <span className="w-8 tabular-nums">{lineHeight.toFixed(2)}</span>
          </label>
          <label className="flex items-center gap-1" title="调整模块和条目之间的距离">
            <span>模块</span>
            <input
              type="range"
              min="2"
              max="20"
              step="1"
              value={moduleSpacing}
              onChange={(e) => updateLayoutControl(lineHeight, Number(e.target.value))}
              className="w-24 accent-brand-600"
            />
            <span className="w-7 tabular-nums">{moduleSpacing}px</span>
          </label>
        </div>
        <Divider />
        <ToolButton
          title="重置为原始"
          onClick={() => {
            if (window.confirm("放弃所有修改，恢复原始内容？")) {
              resetContent();
            }
          }}
        >
          <span className="text-[10px]">↻</span>
        </ToolButton>
      </div>

      <iframe
        ref={iframeRef}
        srcDoc={srcdoc}
        title="Resume Editor"
        onLoad={handleIframeLoad}
        sandbox="allow-same-origin allow-scripts"
        className={`block min-h-0 w-full max-w-full flex-1 overflow-x-hidden bg-white transition-colors ${
          isFocused
            ? "border-brand-500 ring-2 ring-brand-500/20"
            : "border-gray-200 dark:border-gray-600"
        }`}
        style={{
          width: "100%",
          maxWidth: "100%",
          height: "100%",
          border: "1px solid",
          borderTop: "none",
          borderRadius: "0 0 0.5rem 0.5rem",
          borderColor: isFocused ? "#14b8a6" : "#e5e7eb",
        }}
      />
      {libraryPortalTarget && createPortal(
        <ExperienceLibraryPanel
          items={libraryItems}
          onRestore={restoreLibraryEntry}
          onDelete={deleteLibraryEntry}
        />,
        libraryPortalTarget,
      )}
      {!isReady && (
        <p className="mt-1 text-center text-xs text-gray-400">Loading editor...</p>
      )}
    </div>
  );
}

interface ToolButtonProps {
  onClick: () => void;
  title: string;
  children: React.ReactNode;
  disabled?: boolean;
}

type ExperienceCategory = "education" | "work" | "project";

interface RemovedExperienceRecord {
  id: string;
  element: HTMLElement;
  parent: HTMLElement;
  nextSibling: ChildNode | null;
  sectionId: string;
  category: ExperienceCategory;
  title: string;
  summary: string;
  order: number;
}

interface ExperienceLibraryItem {
  id: string;
  category: ExperienceCategory;
  title: string;
  summary: string;
}

const EXPERIENCE_LIBRARY_STORE_ID = "buping-experience-library-store";
const FONT_FAMILY_OPTIONS = [
  { label: "微软雅黑", value: "Microsoft YaHei" },
  { label: "宋体", value: "SimSun" },
  { label: "黑体", value: "SimHei" },
  { label: "Arial", value: "Arial" },
  { label: "Calibri", value: "Calibri" },
  { label: "Times New Roman", value: "Times New Roman" },
  { label: "Georgia", value: "Georgia" },
] as const;
const FONT_SIZE_OPTIONS = [9, 10, 11, 12, 13, 14, 16, 18, 20, 24, 28, 32] as const;

function ExperienceLibraryPanel({
  items,
  onRestore,
  onDelete,
}: {
  items: ExperienceLibraryItem[];
  onRestore: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  return (
    <aside className="w-full rounded-xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white">经历库</h3>
          <p className="text-[11px] text-gray-500 dark:text-gray-400">撤下的经历保存在这里</p>
        </div>
        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600 dark:bg-gray-700 dark:text-gray-300">
          {items.length}
        </span>
      </div>
      {items.length === 0 ? (
        <div className="rounded-md border border-dashed border-gray-300 px-3 py-6 text-center text-xs text-gray-400 dark:border-gray-600">
          暂无撤下的经历
        </div>
      ) : (
        <div className="max-h-[480px] space-y-2 overflow-y-auto overflow-x-hidden pr-1">
          {items.map((item) => (
            <div key={item.id} className="min-w-0 rounded-md border border-gray-200 p-2 dark:border-gray-700">
              <div className="mb-1 flex items-center gap-1.5">
                <span className="shrink-0 rounded bg-brand-50 px-1.5 py-0.5 text-[10px] text-brand-700 dark:bg-brand-950 dark:text-brand-300">
                  {{ education: "教育", work: "工作", project: "项目" }[item.category]}
                </span>
                <span className="min-w-0 truncate text-xs font-medium text-gray-800 dark:text-gray-100" title={item.title}>
                  {item.title}
                </span>
              </div>
              {item.summary && (
                <p className="mb-2 line-clamp-2 break-all text-[11px] leading-4 text-gray-500 dark:text-gray-400">
                  {item.summary}
                </p>
              )}
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => onRestore(item.id)}
                  className="min-w-0 flex-1 rounded-md bg-brand-600 px-2 py-1 text-xs font-medium text-white hover:bg-brand-700"
                >
                  加入当前简历
                </button>
                <button
                  type="button"
                  onClick={() => onDelete(item.id)}
                  className="rounded-md border border-red-200 px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50 dark:border-red-900 dark:text-red-400 dark:hover:bg-red-950"
                  title="从经历库永久删除"
                >
                  删除
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </aside>
  );
}

function ToolButton({ onClick, title, children, disabled = false }: ToolButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      disabled={disabled}
      className="flex h-8 w-8 items-center justify-center rounded text-gray-700 transition-colors hover:bg-gray-100 active:bg-gray-200 disabled:cursor-not-allowed disabled:opacity-35 dark:text-gray-300 dark:hover:bg-gray-700 dark:active:bg-gray-600"
    >
      {children}
    </button>
  );
}

function Divider() {
  return <div className="mx-1 h-5 w-px bg-gray-200 dark:bg-gray-700" />;
}
