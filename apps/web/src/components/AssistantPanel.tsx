import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import {
  api,
  ArtifactPatch,
  ChatMessage,
  ChatSession,
  ProjectSource,
} from "../lib/api";
import { PatchPreview } from "./PatchPreview";

type PanelTab = "edit" | "files";
type ChatMode = "ask" | "local_edit" | "global_edit" | "comments" | "add_item";

type UserModel = {
  id: string;
  model_id: string;
  label: string;
  provider_name?: string | null;
};

const CHAT_MODES: { id: ChatMode; short: string; hint: string }[] = [
  { id: "ask", short: "Вопрос", hint: "Без изменения документа" },
  { id: "local_edit", short: "Цель", hint: "Блок или раздел" },
  { id: "global_edit", short: "Всё", hint: "Весь документ" },
  { id: "comments", short: "Коммент.", hint: "Заметка в списке раздела" },
  { id: "add_item", short: "Пункт", hint: "Новая карточка в разделе" },
];

export function AssistantPanel({
  projectId,
  stageType,
  targetId,
  sectionId,
  sectionTitle,
  readOnly,
  onPatched,
  onCommentAdded,
  onItemAdded,
}: {
  projectId: string;
  stageType: string;
  targetId: string;
  sectionId: string;
  sectionTitle?: string;
  readOnly?: boolean;
  onPatched: () => void;
  onCommentAdded?: () => void;
  onItemAdded?: (itemId: string, artifact: unknown) => void;
}) {
  const [panelTab, setPanelTab] = useState<PanelTab>("edit");
  const [chatMode, setChatMode] = useState<ChatMode>("ask");
  const [text, setText] = useState("");
  const [itemTitle, setItemTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [modelId, setModelId] = useState("");
  const [models, setModels] = useState<UserModel[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [patch, setPatch] = useState<ArtifactPatch | null>(null);
  const [sources, setSources] = useState<ProjectSource[]>([]);
  const [modeMenuOpen, setModeMenuOpen] = useState(false);
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const modeBtnRef = useRef<HTMLButtonElement | null>(null);
  const modelBtnRef = useRef<HTMLButtonElement | null>(null);

  const commentTargetId = targetId || sectionId || "";
  const commentTargetType = targetId ? "block" : sectionId ? "section" : "global";
  const currentChatMode = CHAT_MODES.find((m) => m.id === chatMode) || CHAT_MODES[0];
  const currentModel = models.find((m) => m.id === modelId);
  const aiChat = chatMode !== "comments" && chatMode !== "add_item";

  useEffect(() => {
    api<UserModel[]>("/user-models")
      .then((list) => {
        setModels(list);
        setModelId((prev) => (prev && list.some((m) => m.id === prev) ? prev : list[0]?.id || ""));
      })
      .catch(() => setModels([]));
  }, []);

  useEffect(() => {
    if (panelTab !== "edit" || chatMode === "comments" || chatMode === "add_item") return;
    loadHistory(chatMode);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, stageType, panelTab, chatMode]);

  useEffect(() => {
    if (panelTab === "files") {
      api<ProjectSource[]>(`/projects/${projectId}/sources`).then(setSources);
    }
  }, [projectId, panelTab]);

  async function loadHistory(mode: string) {
    try {
      const sessions = await api<ChatSession[]>(
        `/projects/${projectId}/stages/${stageType}/chat/sessions`
      );
      const s = sessions.find((x) => x.mode === mode);
      const msgs = [...(s?.messages || [])].sort(
        (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
      );
      setMessages(msgs);
    } catch {
      setMessages([]);
    }
  }

  const targetHint = useMemo(() => {
    if (chatMode === "comments") {
      if (targetId) return `комментарий к карточке ${targetId}`;
      if (sectionId) return `комментарий к разделу «${sectionTitle || sectionId}»`;
      return "откройте раздел слева";
    }
    if (chatMode === "add_item") {
      if (sectionId) return `новый пункт в «${sectionTitle || sectionId}»`;
      return "откройте раздел слева";
    }
    if (targetId) return `карточка ${targetId}`;
    if (sectionId) return `раздел «${sectionTitle || sectionId}»`;
    return "весь шаг";
  }, [targetId, sectionId, sectionTitle, chatMode]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;

    if (chatMode === "comments") {
      if (!commentTargetId) {
        setError("Откройте раздел слева.");
        return;
      }
      setBusy(true);
      setError("");
      try {
        await api(`/projects/${projectId}/comments`, {
          method: "POST",
          body: JSON.stringify({
            stage_type: stageType,
            target_type: commentTargetType,
            target_id: commentTargetId,
            body: text.trim(),
          }),
        });
        setText("");
        onCommentAdded?.();
      } catch (err) {
        setError(String(err));
      } finally {
        setBusy(false);
      }
      return;
    }

    if (chatMode === "add_item") {
      if (readOnly) {
        setError("Документ зафиксирован.");
        return;
      }
      if (!sectionId) {
        setError("Откройте раздел слева.");
        return;
      }
      if (!itemTitle.trim()) {
        setError("Укажите заголовок пункта.");
        return;
      }
      setBusy(true);
      setError("");
      try {
        const path =
          stageType === "profession_map"
            ? `/projects/${projectId}/profession-map/sections/${sectionId}/items`
            : `/projects/${projectId}/scenario/sections/${sectionId}/items`;
        const res = await api<{ artifact: unknown; item: { id: string } }>(path, {
          method: "POST",
          body: JSON.stringify({
            title: itemTitle.trim(),
            description: text.trim(),
          }),
        });
        setItemTitle("");
        setText("");
        onItemAdded?.(res.item.id, res.artifact);
      } catch (err) {
        setError(String(err));
      } finally {
        setBusy(false);
      }
      return;
    }

    if ((chatMode === "local_edit" || chatMode === "global_edit") && readOnly) {
      setError("Документ зафиксирован.");
      return;
    }
    const effectiveTargetId = targetId || sectionId || "";
    if (chatMode === "local_edit" && !effectiveTargetId) {
      setError("Откройте раздел или выберите карточку.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const res = await api<{ message: ChatMessage; patch: ArtifactPatch | null }>(
        `/projects/${projectId}/stages/${stageType}/chat`,
        {
          method: "POST",
          body: JSON.stringify({
            mode: chatMode,
            body: text,
            target_id:
              chatMode === "local_edit" || chatMode === "ask" ? effectiveTargetId || null : null,
            primary_model_id: modelId || null,
            fallback_model_id: null,
          }),
        }
      );
      setMessages((m) => [
        ...m,
        { id: "u", session_id: "", role: "user", body: text, created_at: new Date().toISOString() },
        res.message,
      ]);
      setPatch(res.patch);
      setText("");
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  async function applyPatch() {
    if (!patch) return;
    setBusy(true);
    try {
      await api(`/patches/${patch.id}/apply`, { method: "POST" });
      setPatch(null);
      onPatched();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  async function discardPatch() {
    if (!patch) return;
    await api(`/patches/${patch.id}/discard`, { method: "POST" });
    setPatch(null);
  }

  async function promoteAsk() {
    const last = [...messages].reverse().find((m) => m.role === "assistant");
    if (!last) return;
    const effectiveTargetId = targetId || sectionId || "";
    const created = await api<ArtifactPatch>(
      `/projects/${projectId}/stages/${stageType}/chat/promote-patch`,
      {
        method: "POST",
        body: JSON.stringify({
          mode: "local_edit",
          body: last.body,
          target_id: effectiveTargetId,
        }),
      }
    );
    setPatch(created);
    setChatMode("local_edit");
  }

  const modelLabel = currentModel ? shortModelLabel(currentModel) : models.length ? "Модель" : "Нет модели";

  return (
    <aside className="panel sticky top-[7.5rem] flex h-[calc(100vh-8.5rem)] max-h-[calc(100vh-8.5rem)] min-h-0 flex-col gap-3 self-start overflow-hidden">
      <div className="shrink-0 space-y-2">
        <div className="flex gap-1 rounded-lg border border-neutral-200 p-0.5 dark:border-neutral-700">
          <TopTab active={panelTab === "edit"} onClick={() => setPanelTab("edit")}>
            Редактирование
          </TopTab>
          <TopTab active={panelTab === "files"} onClick={() => setPanelTab("files")}>
            Файлы
          </TopTab>
        </div>
        {panelTab === "edit" && (
          <p className="text-xs text-neutral-500">Цель: {targetHint}</p>
        )}
      </div>

      {panelTab === "files" && (
        <div className="min-h-0 flex-1 space-y-2 overflow-auto text-sm">
          {sources.length === 0 && (
            <p className="text-neutral-500">Файлы не загружены. Добавьте в Brief → Материалы.</p>
          )}
          {sources.map((s) => (
            <div key={s.id} className="rounded-lg border border-neutral-200 p-2 dark:border-neutral-700">
              <p className="font-medium">{s.title}</p>
              <p className="text-xs text-neutral-500">{s.parse_status}</p>
            </div>
          ))}
        </div>
      )}

      {panelTab === "edit" && (
        <>
          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto overscroll-contain pr-1 text-sm">
            {chatMode === "comments" ? (
              <p className="text-xs text-neutral-400">
                Комментарии появляются в центральном списке открытого раздела
                {targetId ? " — у выбранной карточки" : sectionId ? "" : ". Откройте раздел слева."}
              </p>
            ) : chatMode === "add_item" ? (
              <p className="text-xs text-neutral-400">
                Новая карточка появится в центральном списке открытого раздела наравне с остальными.
                Поля совпадают с уже существующими пунктами раздела.
              </p>
            ) : messages.length === 0 ? (
              <p className="text-xs text-neutral-400">Напишите сообщение ниже.</p>
            ) : (
              messages.map((m) => (
                <div
                  key={m.id + m.created_at}
                  className={
                    m.role === "user"
                      ? "rounded-lg bg-neutral-100 p-2 dark:bg-neutral-800"
                      : "rounded-lg border border-neutral-200 p-2 dark:border-neutral-700"
                  }
                >
                  <p className="break-words whitespace-pre-wrap">{m.body}</p>
                </div>
              ))
            )}
            {chatMode === "ask" && messages.some((m) => m.role === "assistant") && !readOnly && (
              <button type="button" className="btn-ghost text-xs" onClick={() => void promoteAsk()}>
                Применить как изменение
              </button>
            )}
            {patch && patch.status === "draft" && (
              <PatchPreview
                patch={patch}
                busy={busy}
                onApply={() => void applyPatch()}
                onDiscard={() => void discardPatch()}
              />
            )}
          </div>

          <form
            onSubmit={(e) => void submit(e)}
            className="relative shrink-0 space-y-2 rounded-xl border border-neutral-200 p-2 dark:border-neutral-700"
          >
            {chatMode === "add_item" && (
              <input
                className="input w-full text-sm"
                placeholder="Заголовок пункта"
                value={itemTitle}
                onChange={(e) => setItemTitle(e.target.value)}
                disabled={readOnly}
              />
            )}
            <textarea
              className="w-full resize-none border-0 bg-transparent px-1 py-1 text-sm outline-none focus:ring-0"
              rows={3}
              placeholder={
                chatMode === "comments"
                  ? "Комментарий к открытому разделу…"
                  : chatMode === "add_item"
                    ? "Описание (необязательно)…"
                  : chatMode === "ask"
                    ? "Спросить…"
                    : chatMode === "local_edit"
                      ? "Что изменить в цели…"
                      : "Инструкция для всего документа…"
              }
              value={text}
              onChange={(e) => setText(e.target.value)}
              disabled={chatMode === "add_item" && readOnly}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void submit(e as unknown as FormEvent);
                }
              }}
            />
            <div className="flex items-center justify-between gap-2">
              <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                <button
                  ref={modeBtnRef}
                  type="button"
                  className="inline-flex items-center gap-1 rounded-full border border-neutral-300 bg-white px-2.5 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-600 dark:bg-neutral-900 dark:text-neutral-200"
                  onClick={() => {
                    setModeMenuOpen((v) => !v);
                    setModelMenuOpen(false);
                  }}
                >
                  {currentChatMode.short}
                  <span className="text-neutral-400">▾</span>
                </button>
                {aiChat && (
                  <button
                    ref={modelBtnRef}
                    type="button"
                    className="inline-flex max-w-[140px] items-center gap-1 truncate rounded-full border border-neutral-300 bg-white px-2.5 py-1 text-xs font-medium text-neutral-700 hover:bg-neutral-50 dark:border-neutral-600 dark:bg-neutral-900 dark:text-neutral-200"
                    onClick={() => {
                      setModelMenuOpen((v) => !v);
                      setModeMenuOpen(false);
                    }}
                  >
                    <span className="truncate">{modelLabel}</span>
                    <span className="shrink-0 text-neutral-400">▾</span>
                  </button>
                )}
              </div>
              <button
                className="shrink-0 rounded-full bg-neutral-900 px-3 py-1 text-xs font-semibold text-white disabled:opacity-50 dark:bg-white dark:text-neutral-900"
                disabled={
                  busy ||
                  (chatMode === "add_item" ? !itemTitle.trim() : !text.trim())
                }
                type="submit"
              >
                {busy ? "…" : chatMode === "comments" || chatMode === "add_item" ? "+" : "↑"}
              </button>
            </div>
            {readOnly && (chatMode === "local_edit" || chatMode === "global_edit" || chatMode === "add_item") && (
              <p className="text-[11px] text-amber-700">
                {chatMode === "add_item" ? "Документ зафиксирован — новые пункты недоступны." : "Только режим вопроса — документ зафиксирован."}
              </p>
            )}
            {error && <p className="text-[11px] text-red-600">{error}</p>}

            {modeMenuOpen && modeBtnRef.current && (
              <FloatingMenu anchor={modeBtnRef.current} onClose={() => setModeMenuOpen(false)}>
                {CHAT_MODES.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    className={`block w-full px-3 py-1.5 text-left text-xs hover:bg-neutral-50 dark:hover:bg-neutral-800 ${
                      chatMode === m.id ? "font-semibold" : ""
                    }`}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => {
                      setChatMode(m.id);
                      setModeMenuOpen(false);
                    }}
                  >
                    <span className="block">{m.short}</span>
                    <span className="text-[10px] text-neutral-400">{m.hint}</span>
                  </button>
                ))}
              </FloatingMenu>
            )}

            {modelMenuOpen && modelBtnRef.current && (
              <FloatingMenu anchor={modelBtnRef.current} onClose={() => setModelMenuOpen(false)}>
                {models.length === 0 ? (
                  <p className="px-3 py-2 text-xs text-neutral-500">
                    Нет моделей.{" "}
                    <Link to="/models" className="underline" onClick={() => setModelMenuOpen(false)}>
                      Добавить
                    </Link>
                  </p>
                ) : (
                  models.map((m) => (
                    <button
                      key={m.id}
                      type="button"
                      className={`block w-full truncate px-3 py-1.5 text-left text-xs hover:bg-neutral-50 dark:hover:bg-neutral-800 ${
                        modelId === m.id ? "font-semibold" : ""
                      }`}
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => {
                        setModelId(m.id);
                        setModelMenuOpen(false);
                      }}
                    >
                      {shortModelLabel(m)}
                    </button>
                  ))
                )}
              </FloatingMenu>
            )}
          </form>
        </>
      )}
    </aside>
  );
}

function TopTab({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      className={
        active
          ? "flex-1 rounded-md bg-neutral-900 px-3 py-1.5 text-xs font-medium text-white dark:bg-white dark:text-neutral-900"
          : "flex-1 rounded-md px-3 py-1.5 text-xs text-neutral-600 hover:bg-neutral-50 dark:text-neutral-300 dark:hover:bg-neutral-800"
      }
      onClick={onClick}
    >
      {children}
    </button>
  );
}

function FloatingMenu({
  anchor,
  children,
  onClose,
}: {
  anchor: HTMLElement;
  children: React.ReactNode;
  onClose: () => void;
}) {
  const menuRef = useRef<HTMLDivElement | null>(null);
  const rect = anchor.getBoundingClientRect();
  const menuWidth = 220;
  const left = Math.min(rect.left, window.innerWidth - menuWidth - 8);
  const bottom = window.innerHeight - rect.top + 4;

  useEffect(() => {
    function onPointerDown(e: PointerEvent) {
      const t = e.target as Node;
      if (anchor.contains(t) || menuRef.current?.contains(t)) return;
      onClose();
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [anchor, onClose]);

  return createPortal(
    <div
      ref={menuRef}
      className="fixed z-[101] max-h-52 min-w-[180px] overflow-auto rounded-lg border border-neutral-200 bg-white py-1 shadow-lg dark:border-neutral-700 dark:bg-neutral-900"
      style={{ left, bottom, width: menuWidth }}
      role="listbox"
      onMouseDown={(e) => e.stopPropagation()}
    >
      {children}
    </div>,
    document.body
  );
}

function shortModelLabel(m: UserModel): string {
  const name = m.label || m.model_id;
  return m.provider_name ? `${m.provider_name}: ${name}` : name;
}
