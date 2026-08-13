import { FormEvent, useEffect, useState } from "react";
import {
  api,
  ArtifactPatch,
  ChatMessage,
  ChatSession,
  CommentThread,
  ProjectSource,
} from "../lib/api";
import { ModelSelector } from "./ModelSelector";
import { PatchPreview } from "./PatchPreview";

type Tab = "ask" | "local_edit" | "global_edit" | "comments" | "sources";

export function AssistantPanel({
  projectId,
  stageType,
  targetId,
  readOnly,
  onPatched,
}: {
  projectId: string;
  stageType: string;
  targetId: string;
  readOnly?: boolean;
  onPatched: () => void;
}) {
  const [tab, setTab] = useState<Tab>("ask");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [primaryId, setPrimaryId] = useState("");
  const [fallbackId, setFallbackId] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [patch, setPatch] = useState<ArtifactPatch | null>(null);
  const [comments, setComments] = useState<CommentThread[]>([]);
  const [sources, setSources] = useState<ProjectSource[]>([]);
  const [commentBody, setCommentBody] = useState("");

  useEffect(() => {
    loadHistory(tab === "comments" ? "ask" : tab);
    if (tab === "comments") {
      api<CommentThread[]>(`/projects/${projectId}/comments?stage=${stageType}`).then(setComments);
    }
    if (tab === "sources") {
      api<ProjectSource[]>(`/projects/${projectId}/sources`).then(setSources);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, stageType, tab]);

  async function loadHistory(mode: string) {
    if (mode === "comments" || mode === "sources") return;
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

  async function send(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    if ((tab === "local_edit" || tab === "global_edit") && readOnly) {
      setError("Документ зафиксирован. Создайте новую редакцию, чтобы править.");
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
            mode: tab,
            body: text,
            target_id: tab === "local_edit" ? targetId || null : null,
            primary_model_id: primaryId || null,
            fallback_model_id: fallbackId || null,
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

  async function addComment(e: FormEvent) {
    e.preventDefault();
    if (!commentBody.trim()) return;
    await api(`/projects/${projectId}/comments`, {
      method: "POST",
      body: JSON.stringify({
        stage_type: stageType,
        target_type: targetId ? "block" : "global",
        target_id: targetId,
        body: commentBody,
      }),
    });
    setCommentBody("");
    setComments(await api<CommentThread[]>(`/projects/${projectId}/comments?stage=${stageType}`));
  }

  async function resolve(id: string) {
    await api(`/comments/${id}/resolve`, { method: "POST" });
    setComments(await api<CommentThread[]>(`/projects/${projectId}/comments?stage=${stageType}`));
  }

  async function promoteAsk() {
    const last = [...messages].reverse().find((m) => m.role === "assistant");
    if (!last) return;
    const created = await api<ArtifactPatch>(
      `/projects/${projectId}/stages/${stageType}/chat/promote-patch`,
      {
        method: "POST",
        body: JSON.stringify({
          mode: "local_edit",
          body: last.body,
          target_id: targetId || "",
        }),
      }
    );
    setPatch(created);
    setTab("local_edit");
  }

  const chatMode = tab === "ask" || tab === "local_edit" || tab === "global_edit";

  return (
    <aside className="panel sticky top-[7.5rem] flex h-[calc(100vh-8.5rem)] max-h-[calc(100vh-8.5rem)] min-h-0 flex-col gap-3 self-start overflow-hidden">
      <div className="flex shrink-0 flex-wrap gap-1">
        {(
          [
            ["ask", "Вопрос"],
            ["local_edit", "Блок"],
            ["global_edit", "Всё"],
            ["comments", "Коммент."],
            ["sources", "Источники"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={tab === id ? "btn-primary px-2 py-1 text-xs" : "btn-ghost px-2 py-1 text-xs"}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="shrink-0">
        <ModelSelector
          compact
          primaryId={primaryId}
          fallbackId={fallbackId}
          onPrimary={setPrimaryId}
          onFallback={setFallbackId}
        />
      </div>

      {tab === "ask" && (
        <p className="shrink-0 text-xs text-neutral-500">
          Вопрос к AI без изменения документа. Если ответ ок — можно «Применить ответ как изменение».
        </p>
      )}
      {tab === "local_edit" && (
        <p className="shrink-0 text-xs text-neutral-500">
          {targetId
            ? `Точечная правка выбранной карточки (${targetId}). Сначала появится превью — его нужно применить.`
            : "Сначала кликните карточку в центре, затем опишите, что изменить в этом блоке."}
        </p>
      )}
      {tab === "global_edit" && (
        <p className="shrink-0 text-xs text-neutral-500">
          Правка всего документа. Модель предложит патч; примените или отклоните его.
        </p>
      )}
      {tab === "comments" && (
        <p className="shrink-0 text-xs text-neutral-500">
          {targetId
            ? `Заметка к выбранной карточке (${targetId}). Это не вызов AI и не меняет текст само.`
            : "Общий комментарий к шагу. Чтобы привязать к блоку — кликните карточку в центре."}
        </p>
      )}
      {readOnly && (tab === "local_edit" || tab === "global_edit") && (
        <p className="shrink-0 text-xs text-amber-700">Редактирование закрыто. Доступен только режим вопроса.</p>
      )}

      {chatMode && (
        <>
          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto overscroll-contain pr-1 text-sm">
            {messages.length === 0 && (
              <p className="text-xs text-neutral-400">Ответы появятся здесь. Длинный текст можно прокрутить.</p>
            )}
            {messages.map((m) => (
              <div
                key={m.id + m.created_at}
                className={
                  m.role === "user"
                    ? "rounded-lg bg-neutral-100 p-2 dark:bg-neutral-800"
                    : "rounded-lg border border-neutral-200 p-2 dark:border-neutral-700"
                }
              >
                <p className="text-[10px] uppercase text-neutral-400">{m.role}</p>
                <p className="break-words whitespace-pre-wrap">{m.body}</p>
              </div>
            ))}
            {tab === "ask" && messages.some((m) => m.role === "assistant") && !readOnly && (
              <button type="button" className="btn-ghost text-xs" onClick={() => void promoteAsk()}>
                Применить ответ как изменение
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
          <form onSubmit={(e) => void send(e)} className="shrink-0 space-y-2 border-t border-neutral-200 pt-2 dark:border-neutral-700">
            <textarea
              className="input min-h-[72px]"
              placeholder={
                tab === "ask"
                  ? "Задать вопрос без изменения текста…"
                  : tab === "local_edit"
                    ? "Как изменить выбранный блок?"
                    : "Глобальная инструкция для всего документа"
              }
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
            {error && <p className="text-xs text-red-600">{error}</p>}
            <button className="btn-primary w-full" disabled={busy} type="submit">
              {busy ? "Думаем…" : "Отправить"}
            </button>
          </form>
        </>
      )}

      {tab === "comments" && (
        <div className="min-h-0 flex-1 space-y-3 overflow-auto">
          <form onSubmit={(e) => void addComment(e)} className="space-y-2">
            <textarea
              className="input min-h-[64px]"
              placeholder={targetId ? `Комментарий к ${targetId}` : "Общий комментарий"}
              value={commentBody}
              onChange={(e) => setCommentBody(e.target.value)}
            />
            <button className="btn-primary w-full" type="submit">
              Добавить
            </button>
          </form>
          {comments.map((t) => (
            <div key={t.id} className="rounded-lg border border-neutral-200 p-2 text-sm dark:border-neutral-700">
              <p className="text-xs text-neutral-500">
                {t.target_id || "global"} · {t.status}
              </p>
              {t.messages.map((m) => (
                <p key={m.id} className="mt-1">
                  {m.body}
                </p>
              ))}
              {t.status === "open" && (
                <button type="button" className="btn-ghost mt-2 text-xs" onClick={() => void resolve(t.id)}>
                  Закрыть
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {tab === "sources" && (
        <div className="min-h-0 flex-1 space-y-2 overflow-auto text-sm">
          {sources.length === 0 && <p className="text-neutral-500">Файлы ещё не загружены.</p>}
          {sources.map((s) => (
            <div key={s.id} className="rounded-lg border border-neutral-200 p-2 dark:border-neutral-700">
              <p className="font-medium">{s.title}</p>
              <p className="text-xs text-neutral-500">{s.parse_status}</p>
            </div>
          ))}
        </div>
      )}
    </aside>
  );
}
