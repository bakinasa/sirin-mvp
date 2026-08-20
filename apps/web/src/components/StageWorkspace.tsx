import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  api,
  Artifact,
  BlockDocument,
  CommentThread,
  DocItem,
  PipelineStep,
} from "../lib/api";
import { PipelineStepper } from "./PipelineStepper";
import { AssistantPanel } from "./AssistantPanel";
import { VersionHistoryModal } from "./VersionHistoryModal";
import { StatusBadge } from "./StatusBadge";
import { ModelSelector } from "./ModelSelector";
import { PromptPanel } from "./PromptPanel";
import { SceneCard, StringListEditor } from "./SceneCard";
import { exportDocx } from "../lib/docxExport";

type Props = {
  projectId: string;
  stageType: "profession_map" | "scenario_plan";
  title: string;
  subtitle: string;
  allowAcceptReject?: boolean;
};

export function StageWorkspace({
  projectId,
  stageType,
  title,
  subtitle,
  allowAcceptReject,
}: Props) {
  const navigate = useNavigate();
  const [steps, setSteps] = useState<PipelineStep[]>([]);
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [sectionId, setSectionId] = useState("");
  const [targetId, setTargetId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [historyOpen, setHistoryOpen] = useState(false);
  const [primaryId, setPrimaryId] = useState("");
  const [fallbackId, setFallbackId] = useState("");
  const [operatorPrompt, setOperatorPrompt] = useState("");
  const [helpOpen, setHelpOpen] = useState(true);
  const [comments, setComments] = useState<CommentThread[]>([]);
  const saveTimer = useRef<number | null>(null);
  const pendingSaveItemRef = useRef<DocItem | null>(null);
  const autoSaveInFlight = useRef(false);

  const step = steps.find((s) => s.step_type === stageType);
  const mapStep = steps.find((s) => s.step_type === "profession_map");
  const frozen = !!artifact?.frozen;
  const outdated = step?.status === "outdated";

  async function reload() {
    const [s, art] = await Promise.all([
      api<PipelineStep[]>(`/projects/${projectId}/pipeline`),
      api<Artifact | null>(
        stageType === "profession_map"
          ? `/projects/${projectId}/profession-map`
          : `/projects/${projectId}/scenario`
      ),
    ]);
    setSteps(s);
    setArtifact(art);
    const doc = asDoc(art?.content);
    if (!sectionId && doc.sections?.[0]) setSectionId(doc.sections[0].id);
  }

  useEffect(() => {
    reload().catch((e) => setError(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, stageType]);

  async function loadComments() {
    setComments(await api<CommentThread[]>(`/projects/${projectId}/comments?stage=${stageType}`));
  }

  useEffect(() => {
    if (artifact) loadComments().catch(console.error);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, stageType, artifact?.id]);

  // Автосохранение: раз в пару минут создаём snapshot версии.
  useEffect(() => {
    if (!artifact) return;
    if (artifact.frozen) return;

    const intervalMs = 2 * 60 * 1000;
    const id = window.setInterval(async () => {
      if (busy) return;
      if (autoSaveInFlight.current) return;
      autoSaveInFlight.current = true;
      try {
        await api(`/artifacts/${artifact.id}/save-version`, {
          method: "POST",
          body: JSON.stringify({ change_summary: "Auto snapshot" }),
        });
        await reload();
      } catch (e) {
        console.error("Auto snapshot failed:", e);
      } finally {
        autoSaveInFlight.current = false;
      }
    }, intervalMs);

    return () => window.clearInterval(id);
  }, [artifact?.id, artifact?.frozen, projectId, stageType, busy]);

  const doc = useMemo(() => asDoc(artifact?.content), [artifact]);
  const sections = doc.sections || [];
  const parseWarnings = useMemo(() => {
    const raw = artifact?.content;
    if (!raw || typeof raw !== "object") return [] as string[];
    const notes = (raw as Record<string, unknown>).clarifications_needed;
    return Array.isArray(notes) ? notes.map(String) : [];
  }, [artifact?.content]);
  const currentSection = sections.find((s) => s.id === sectionId) || sections[0];

  const sectionComments = useMemo(
    () =>
      comments.filter(
        (c) =>
          c.target_type === "section" &&
          c.target_id === (currentSection?.id || sectionId)
      ),
    [comments, currentSection?.id, sectionId]
  );

  function itemComments(itemId: string) {
    return comments.filter((c) => c.target_id === itemId);
  }

  async function resolveComment(threadId: string) {
    await api(`/comments/${threadId}/resolve`, { method: "POST" });
    await loadComments();
  }

  async function generate() {
    setBusy(true);
    setError("");
    try {
      await api(
        stageType === "profession_map"
          ? `/projects/${projectId}/profession-map/generate`
          : `/projects/${projectId}/scenario/generate`,
        {
          method: "POST",
          body: JSON.stringify({
            operator_prompt: operatorPrompt || null,
            primary_model_id: primaryId || null,
            fallback_model_id: fallbackId || null,
          }),
        }
      );
      await reload();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  function scheduleItemSave(item: DocItem) {
    if (!artifact) return;
    pendingSaveItemRef.current = item;
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(async () => {
      const latest = pendingSaveItemRef.current;
      pendingSaveItemRef.current = null;
      saveTimer.current = null;
      if (!latest) return;
      const path =
        stageType === "profession_map"
          ? `/projects/${projectId}/profession-map/items/${latest.id}`
          : `/projects/${projectId}/scenario/items/${latest.id}`;
      const updated = await api<Artifact>(path, {
        method: "PATCH",
        body: JSON.stringify({ content: latest }),
      });
      setArtifact(updated);
    }, 700);
  }

  async function flushScheduledItemSave() {
    if (!saveTimer.current || !pendingSaveItemRef.current) return;
    const latest = pendingSaveItemRef.current;
    window.clearTimeout(saveTimer.current);
    saveTimer.current = null;
    pendingSaveItemRef.current = null;

    const path =
      stageType === "profession_map"
        ? `/projects/${projectId}/profession-map/items/${latest.id}`
        : `/projects/${projectId}/scenario/items/${latest.id}`;
    const updated = await api<Artifact>(path, {
      method: "PATCH",
      body: JSON.stringify({ content: latest }),
    });
    setArtifact(updated);
  }

  async function decide(itemId: string, kind: "accept" | "reject") {
    const updated = await api<Artifact>(
      `/projects/${projectId}/profession-map/items/${itemId}/${kind}`,
      { method: "POST" }
    );
    setArtifact(updated);
  }

  async function freeze() {
    setBusy(true);
    try {
      await flushScheduledItemSave();
      // Ensure everything is persisted before locking the step.
      await saveVersion();
      const updated = await api<Artifact>(
        stageType === "profession_map"
          ? `/projects/${projectId}/profession-map/freeze`
          : `/projects/${projectId}/scenario/freeze`,
        { method: "POST", body: JSON.stringify({ change_summary: "Freeze" }) }
      );
      setArtifact(updated);
      await reload();
      if (stageType === "profession_map") {
        navigate(`/projects/${projectId}/scenario`);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function saveVersion() {
    if (!artifact) return;
    await api(`/artifacts/${artifact.id}/save-version`, {
      method: "POST",
      body: JSON.stringify({ change_summary: "Manual snapshot" }),
    });
    await reload();
  }

  async function exportStoryDocx() {
    setBusy(true);
    setError("");
    try {
      const job = await exportDocx(projectId, "docx_profession_map", "story.docx");
      if (job.status === "failed") {
        setError(job.error_message || "Не удалось сформировать DOCX");
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function newEdition() {
    if (!confirm("Создать новую редакцию сюжета? Сценарий будет помечен как устаревший.")) return;
    await api(`/projects/${projectId}/profession-map/new-edition`, { method: "POST" });
    await reload();
  }

  return (
    <div>
      <PipelineStepper projectId={projectId} steps={steps} />
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
          <p className="mt-1 max-w-2xl text-sm text-neutral-600 dark:text-neutral-300">{subtitle}</p>
          {artifact && (
            <p className="mt-1 text-xs text-neutral-500">
              v{artifact.version} · {artifact.change_type} · {frozen ? "frozen" : "draft"}
              {step && (
                <>
                  {" · "}
                  <StatusBadge status={step.status} />
                </>
              )}
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {stageType !== "profession_map" && stageType !== "scenario_plan" && (
            <button type="button" className="btn-ghost" onClick={() => setHistoryOpen(true)}>
              История
            </button>
          )}
          {stageType === "profession_map" && artifact && (
            <button type="button" className="btn-ghost" disabled={busy} onClick={() => void exportStoryDocx()}>
              Скачать DOCX
            </button>
          )}
          <button type="button" className="btn-ghost" disabled={busy || !artifact} onClick={() => void freeze()}>
            Зафиксировать
          </button>
          <button type="button" className="btn-primary" disabled={busy} onClick={() => void generate()}>
            {busy ? "Генерация…" : artifact ? "Пересобрать AI" : "Сформировать AI"}
          </button>
        </div>
      </div>
      <div className="mb-4">
        <ModelSelector primaryId={primaryId} fallbackId={fallbackId} onPrimary={setPrimaryId} onFallback={setFallbackId} />
      </div>
      <div className="mb-4">
        <PromptPanel
          projectId={projectId}
          stepType={stageType}
          value={operatorPrompt}
          onChange={setOperatorPrompt}
        />
      </div>

      <div className="mb-4 rounded-xl border border-neutral-200 bg-neutral-50 px-4 py-3 dark:border-neutral-700 dark:bg-neutral-900/50">
        <button
          type="button"
          className="flex w-full items-start justify-between gap-3 text-left"
          onClick={() => setHelpOpen((v) => !v)}
        >
          <span>
            <span className="block font-semibold">Как править документ</span>
            <span className="text-sm text-neutral-500">
              Клик по карточке выбирает блок. Текст правится вручную или через чат справа.
            </span>
          </span>
          <span className="shrink-0 text-xs text-neutral-400">{helpOpen ? "скрыть" : "показать"}</span>
        </button>
        {helpOpen && (
          <ul className="mt-3 list-disc space-y-1.5 pl-5 text-sm text-neutral-700 dark:text-neutral-300">
            <li>
              <b>Слева</b> — разделы (вкладки документа). Открытый раздел уже является целью для правки и комментария,
              даже если карточка не выбрана.
            </li>
            <li>
              <b>В центре</b> кликните карточку, чтобы править точечно. Поля карточки можно менять руками.
              Разделы слева фиксированы: для сюжета — работы и сюжет, точки оценки, вопросы экспертам;
              для сценария — обучающие и диагностические сцены.
            </li>
            <li>
              Справа: ввод → ниже <b>режим</b> (вопрос / правка цели / всё / коммент. / пункт) и <b>модель</b>.
              «Пункт» добавляет новую карточку в открытый раздел.
            </li>
            <li>
              AI-правка сначала показывает превью. Нажмите <b>Применить</b> или <b>Отклонить</b>.
            </li>
            <li>
              <b>Зафиксировать</b> сохраняет снимок версии. Правка снова открывает шаг и помечает следующие как устаревшие
              {stageType === "profession_map" ? " (сценарий не удаляется)." : "."}
            </li>
          </ul>
        )}
      </div>

      {parseWarnings.length > 0 && (
        <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm dark:border-amber-800 dark:bg-amber-950/40">
          <p className="font-semibold">Ответ модели не разобран полностью</p>
          <ul className="mt-1 list-disc pl-5">
            {parseWarnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-neutral-600 dark:text-neutral-400">
            Часто это обрезка JSON на лимите токенов. Пересоберите документ или сократите требования в промпте.
          </p>
        </div>
      )}
      {outdated && stageType === "profession_map" && (
        <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm dark:border-amber-800 dark:bg-amber-950/40">
          Brief изменился. Этот сюжет помечен как устаревший — пересоберите его, когда будете готовы. Артефакт сохранён.
        </div>
      )}
      {outdated && stageType === "scenario_plan" && (
        <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm dark:border-amber-800 dark:bg-amber-950/40">
          Предсценарный сюжет изменился. Этот сценарий устарел — пересоберите его. Артефакт сохранён.
        </div>
      )}
      {error && (
        <div className="mb-4 rounded-lg border border-red-200 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      {!artifact ? (
        <div className="panel text-sm text-neutral-500">
          Документа ещё нет. Проверьте промпт и контекст выше, затем нажмите «Сформировать AI».
        </div>
      ) : (
        <div className="grid gap-4 xl:grid-cols-[220px_minmax(0,1fr)_340px]">
          <nav className="panel space-y-1 self-start">
            {sections.map((s) => (
              <button
                key={s.id}
                type="button"
                className={
                  currentSection?.id === s.id
                    ? "w-full rounded-md bg-neutral-900 px-3 py-2 text-left text-sm text-white dark:bg-white dark:text-neutral-900"
                    : "w-full rounded-md px-3 py-2 text-left text-sm hover:bg-neutral-50 dark:hover:bg-neutral-800"
                }
                onClick={() => {
                  setSectionId(s.id);
                  setTargetId("");
                }}
              >
                {s.title}
                <span className="ml-1 text-xs opacity-60">({s.items?.length || 0})</span>
              </button>
            ))}
          </nav>

          <div className="space-y-3">
            {currentSection && sectionComments.length > 0 && (
              <CommentBlock
                title={`Комментарии к разделу «${currentSection.title}»`}
                threads={sectionComments}
                onResolve={(id) => void resolveComment(id)}
              />
            )}
            {(currentSection?.items || []).map((item) => {
              const isScene =
                currentSection?.id === "training_scenes" || currentSection?.id === "diagnostic_scenes";
              const cardProps = {
                item,
                selected: targetId === item.id,
                readOnly: false,
                commentThreads: itemComments(item.id),
                onResolveComment: (id: string) => void resolveComment(id),
                onSelect: () => setTargetId(targetId === item.id ? "" : item.id),
                onChange: (next: DocItem) => {
                  const copy = structuredClone(doc) as BlockDocument;
                  const sec = copy.sections?.find((s) => s.id === currentSection?.id);
                  if (!sec) return;
                  sec.items = sec.items.map((it) => (it.id === next.id ? next : it));
                  setArtifact({ ...artifact, content: copy });
                  scheduleItemSave(next);
                },
              };
              return isScene ? (
                <SceneCard
                  key={item.id}
                  variant={currentSection?.id === "diagnostic_scenes" ? "diagnostic" : "training"}
                  {...cardProps}
                />
              ) : (
                <ItemCard
                  key={item.id}
                  sectionId={currentSection?.id}
                  allowAcceptReject={!!allowAcceptReject}
                  onAccept={() => void decide(item.id, "accept")}
                  onReject={() => void decide(item.id, "reject")}
                  {...cardProps}
                />
              );
            })}
            {(!currentSection || currentSection.items.length === 0) && (
              <div className="panel text-sm text-neutral-500">В этой секции пока нет элементов.</div>
            )}
          </div>

          <AssistantPanel
            projectId={projectId}
            stageType={stageType}
            targetId={targetId}
            sectionId={currentSection?.id || sectionId || ""}
            sectionTitle={currentSection?.title}
            readOnly={false}
            onPatched={() => void reload()}
            onCommentAdded={() => void loadComments()}
            onItemAdded={(itemId, art) => {
              setArtifact(art as Artifact);
              setTargetId(itemId);
            }}
          />
        </div>
      )}

      {historyOpen && (
        <VersionHistoryModal
          projectId={projectId}
          stepType={stageType}
          current={artifact}
          onClose={() => setHistoryOpen(false)}
          onRestored={() => void reload()}
        />
      )}
    </div>
  );
}

function asDoc(content: unknown): BlockDocument {
  if (content && typeof content === "object" && Array.isArray((content as BlockDocument).sections)) {
    return content as BlockDocument;
  }
  return { sections: [] };
}

const FIELD_LABELS: Record<string, string> = {
  description: "Описание",
  why_selected: "Почему выбран",
  why_needed: "Зачем нужно",
  answer: "Ответ эксперта",
  attention_focus: "Фокус внимания",
  priority: "Приоритет",
  process_overview: "Ход работы",
  likely_location: "Локация",
  required_objects: "Объекты",
  main_risks: "Риски",
  related_work_ids: "Связанные работы",
  related_work_id: "Работа",
  observable_result: "Наблюдаемый результат",
  criticality: "Критичность",
  skill_id: "Навык",
  correct_observation: "Правильно",
  error_observation: "Ошибка",
  visual_cues: "Визуальные признаки",
  violation_category: "Категория нарушения",
  story_steps: "Шаги сюжета",
  training_focus: "Фокус обучения",
  diagnostic_focus: "Фокус диагностики",
  candidate_scene_groups: "Группы сцен",
  scene_no: "№ сцены",
  location: "Локация",
  actors: "Актёры",
  actions: "Действия",
  visual_accents: "Визуальные акценты",
  audio_text: "Аудиотекст",
  on_screen_training_texts: "Экран: обучение",
  on_screen_error_texts: "Экран: ошибка",
  linked_skill_ids: "Навыки",
  linked_assessment_point_ids: "Точки оценки",
  staged_errors: "Инсценированные ошибки",
  error_categories: "Категории ошибок",
  example_errors: "Примеры ошибок",
  text: "Текст",
  mode: "Режим",
  usage_context: "Контекст показа",
  scene_refs: "Сцены",
  setup_type: "Тип постановки",
  props: "Реквизит",
  notes: "Заметки",
};

function CommentBlock({
  title,
  threads,
  onResolve,
}: {
  title: string;
  threads: CommentThread[];
  onResolve: (id: string) => void;
}) {
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50/80 p-3 dark:border-amber-900 dark:bg-amber-950/30">
      <p className="mb-2 text-xs font-semibold text-amber-900 dark:text-amber-100">{title}</p>
      <ul className="space-y-2">
        {threads.map((t) => (
          <li key={t.id} className="rounded-md border border-amber-200/80 bg-white/80 px-2 py-1.5 text-sm dark:border-amber-900 dark:bg-neutral-900/60">
            {t.messages.map((m) => (
              <p key={m.id} className="whitespace-pre-wrap">
                {m.body}
              </p>
            ))}
            {t.status === "open" && (
              <button type="button" className="btn-ghost mt-1 px-1 py-0.5 text-xs" onClick={() => onResolve(t.id)}>
                Закрыть
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

type ErrorRow = { error: string; correct: string; visual_cues: string[] };

function asErrors(item: DocItem): ErrorRow[] {
  if (Array.isArray(item.errors)) {
    return (item.errors as unknown[]).map((r) => {
      const row = (r && typeof r === "object" ? r : {}) as Record<string, unknown>;
      return {
        error: String(row.error ?? ""),
        correct: String(row.correct ?? ""),
        visual_cues: Array.isArray(row.visual_cues) ? (row.visual_cues as unknown[]).map((x) => String(x ?? "")) : [],
      };
    });
  }
  // migrate from flat fields
  const hasFlat = item.error_observation != null || item.correct_observation != null || item.visual_cues != null;
  if (hasFlat) {
    return [{
      error: String(item.error_observation ?? ""),
      correct: String(item.correct_observation ?? ""),
      visual_cues: Array.isArray(item.visual_cues)
        ? (item.visual_cues as unknown[]).map((x) => String(x ?? ""))
        : typeof item.visual_cues === "string" && item.visual_cues ? [item.visual_cues] : [],
    }];
  }
  return [];
}

function ErrorsTable({
  item,
  readOnly,
  onChange,
}: {
  item: DocItem;
  readOnly: boolean;
  onChange: (item: DocItem) => void;
}) {
  const rows = asErrors(item);

  function update(next: ErrorRow[]) {
    const { error_observation: _e, correct_observation: _c, visual_cues: _v, ...rest } = item as DocItem & Record<string, unknown>;
    void _e; void _c; void _v;
    onChange({ ...rest, errors: next } as DocItem);
  }

  function setRow(idx: number, patch: Partial<ErrorRow>) {
    update(rows.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  }

  function addRow() {
    update([...rows, { error: "", correct: "", visual_cues: [] }]);
  }

  function removeRow(idx: number) {
    update(rows.filter((_, i) => i !== idx));
  }

  return (
    <div onClick={(e) => e.stopPropagation()}>
      <div className="mb-1 flex items-center justify-between">
        <label className="label text-xs">Ошибки и правильные действия</label>
        {!readOnly && (
          <button type="button" className="btn-ghost px-2 py-0.5 text-xs" onClick={addRow}>
            + ошибка
          </button>
        )}
      </div>
      <div className="overflow-x-auto rounded-lg border border-neutral-200 dark:border-neutral-700">
        <table className="min-w-full text-left text-xs">
          <thead className="bg-neutral-50 dark:bg-neutral-900">
            <tr>
              <th className="px-2 py-1.5 font-medium">Ошибка</th>
              <th className="px-2 py-1.5 font-medium">Правильно</th>
              <th className="px-2 py-1.5 font-medium">Визуальные признаки</th>
              {!readOnly && <th className="w-8 px-1 py-1.5" />}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td className="px-2 py-2 text-neutral-400" colSpan={readOnly ? 3 : 4}>
                  Нет ошибок. Добавьте строку.
                </td>
              </tr>
            )}
            {rows.map((row, idx) => (
              <tr key={idx} className="border-t border-neutral-200 dark:border-neutral-800">
                <td className="px-1 py-1 align-top">
                  <textarea
                    className="input min-h-[52px] text-xs"
                    disabled={readOnly}
                    placeholder="Что именно сделано неправильно"
                    value={row.error}
                    onChange={(e) => setRow(idx, { error: e.target.value })}
                  />
                </td>
                <td className="px-1 py-1 align-top">
                  <textarea
                    className="input min-h-[52px] text-xs"
                    disabled={readOnly}
                    placeholder="Как надо делать"
                    value={row.correct}
                    onChange={(e) => setRow(idx, { correct: e.target.value })}
                  />
                </td>
                <td className="px-1 py-1 align-top">
                  <StringListEditor
                    values={row.visual_cues}
                    readOnly={readOnly}
                    onChange={(values) => setRow(idx, { visual_cues: values })}
                  />
                </td>
                {!readOnly && (
                  <td className="px-1 py-1 align-top">
                    <button type="button" className="btn-ghost px-1 py-0.5 text-xs" onClick={() => removeRow(idx)}>
                      ×
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ItemCard({
  item,
  sectionId,
  selected,
  readOnly,
  allowAcceptReject,
  commentThreads,
  onResolveComment,
  onSelect,
  onChange,
  onAccept,
  onReject,
}: {
  item: DocItem;
  sectionId?: string;
  selected: boolean;
  readOnly: boolean;
  allowAcceptReject: boolean;
  commentThreads?: CommentThread[];
  onResolveComment?: (id: string) => void;
  onSelect: () => void;
  onChange: (item: DocItem) => void;
  onAccept: () => void;
  onReject: () => void;
}) {
  const isAssessment = sectionId === "assessment_points";
  // fields to render as generic inputs (skip errors[] and the migrated flat fields)
  const skip = new Set(["id", "status", "items", "frames", "segments", "errors", "error_observation", "correct_observation", "visual_cues"]);
  const fields = Object.keys(item).filter((k) => !skip.has(k));
  return (
    <article
      className={`panel cursor-pointer space-y-2 ${selected ? "ring-2 ring-neutral-900 dark:ring-white" : ""}`}
      onClick={onSelect}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          {!readOnly ? (
            <div>
              <label className="label text-xs">{isAssessment ? "Вид работ" : "title"}</label>
              <input
                className="input font-semibold"
                value={String(item.title || "")}
                onChange={(e) => onChange({ ...item, title: e.target.value })}
                onClick={(e) => e.stopPropagation()}
                placeholder={isAssessment ? "Название вида работ" : "Заголовок"}
              />
            </div>
          ) : (
            <h3 className="font-semibold">{String(item.title || item.id)}</h3>
          )}
          {selected && (
            <p className="mt-0.5 text-xs text-neutral-500">
              Выбрано: точечная правка (вкладка «Блок») и комментарий справа относятся к этой карточке.
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {item.status && <StatusBadge status={String(item.status)} />}
          {allowAcceptReject && (
            <>
              <button type="button" className="btn-ghost px-2 py-1 text-xs" onClick={(e) => { e.stopPropagation(); onAccept(); }}>
                Принять
              </button>
              <button type="button" className="btn-ghost px-2 py-1 text-xs" onClick={(e) => { e.stopPropagation(); onReject(); }}>
                Отклонить
              </button>
            </>
          )}
        </div>
      </div>
      {fields
        .filter((k) => k !== "title")
        .map((k) => (
          <div key={k}>
            <label className="label text-xs">{isAssessment && k === "description" ? "Контекст" : FIELD_LABELS[k] || k}</label>
            {typeof item[k] === "string" || typeof item[k] === "number" || item[k] == null ? (
              <textarea
                className="input min-h-[56px]"
                disabled={readOnly}
                value={item[k] == null ? "" : String(item[k])}
                onChange={(e) => onChange({ ...item, [k]: e.target.value })}
                onClick={(e) => e.stopPropagation()}
              />
            ) : Array.isArray(item[k]) && (item[k] as unknown[]).every((x) => typeof x === "string" || x == null) ? (
              <StringListEditor
                values={(item[k] as unknown[]).map((x) => String(x ?? ""))}
                readOnly={readOnly}
                onChange={(values) => onChange({ ...item, [k]: values })}
              />
            ) : (
              <pre className="max-h-32 overflow-auto whitespace-pre-wrap text-xs text-neutral-600">
                {JSON.stringify(item[k], null, 2)}
              </pre>
            )}
          </div>
        ))}
      {isAssessment && (
        <ErrorsTable item={item} readOnly={readOnly} onChange={onChange} />
      )}
      {Array.isArray(item.frames) && (
        <p className="text-xs text-neutral-500">Кадров: {(item.frames as unknown[]).length}</p>
      )}
      {commentThreads && commentThreads.length > 0 && (
        <div className="space-y-1 border-t border-neutral-200 pt-2 dark:border-neutral-700">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-neutral-400">Комментарии</p>
          {commentThreads.map((t) => (
            <div key={t.id} className="rounded-md bg-amber-50 px-2 py-1.5 text-xs dark:bg-amber-950/30">
              {t.messages.map((m) => (
                <p key={m.id} className="whitespace-pre-wrap">
                  {m.body}
                </p>
              ))}
              {t.status === "open" && onResolveComment && (
                <button type="button" className="btn-ghost mt-1 px-1 py-0 text-[10px]" onClick={(e) => { e.stopPropagation(); onResolveComment(t.id); }}>
                  Закрыть
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </article>
  );
}
