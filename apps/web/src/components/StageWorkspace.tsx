import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  api,
  Artifact,
  BlockDocument,
  DocItem,
  PipelineStep,
} from "../lib/api";
import { PipelineStepper } from "./PipelineStepper";
import { AssistantPanel } from "./AssistantPanel";
import { VersionHistoryModal } from "./VersionHistoryModal";
import { StatusBadge } from "./StatusBadge";
import { ModelSelector } from "./ModelSelector";
import { PromptPanel } from "./PromptPanel";

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
  const saveTimer = useRef<number | null>(null);

  const step = steps.find((s) => s.step_type === stageType);
  const mapStep = steps.find((s) => s.step_type === "profession_map");
  const locked = step?.status === "locked" || !!artifact?.frozen;
  const outdated = step?.status === "outdated";
  const mapLocked = mapStep?.status === "locked";

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

  const doc = useMemo(() => asDoc(artifact?.content), [artifact]);
  const sections = doc.sections || [];
  const currentSection = sections.find((s) => s.id === sectionId) || sections[0];

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
    if (!artifact || locked) return;
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(async () => {
      const path =
        stageType === "profession_map"
          ? `/projects/${projectId}/profession-map/items/${item.id}`
          : `/projects/${projectId}/scenario/items/${item.id}`;
      const updated = await api<Artifact>(path, {
        method: "PATCH",
        body: JSON.stringify({ content: item }),
      });
      setArtifact(updated);
    }, 700);
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

  async function newEdition() {
    if (!confirm("Создать новую редакцию карты? Сценарий будет помечен как устаревший.")) return;
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
              v{artifact.version} · {artifact.change_type} · {artifact.frozen ? "frozen" : "draft"}
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
          <button type="button" className="btn-ghost" onClick={() => setHistoryOpen(true)}>
            История
          </button>
          {artifact && !locked && (
            <button type="button" className="btn-ghost" onClick={() => void saveVersion()}>
              Save version
            </button>
          )}
          {stageType === "profession_map" && mapLocked && (
            <button type="button" className="btn-ghost" onClick={() => void newEdition()}>
              Новая редакция шага 2
            </button>
          )}
          <button type="button" className="btn-ghost" disabled={busy || !artifact} onClick={() => void freeze()}>
            Зафиксировать
          </button>
          <button type="button" className="btn-primary" disabled={busy || locked} onClick={() => void generate()}>
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
          readOnly={locked}
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
              <b>Слева</b> — разделы. <b>В центре</b> кликните карточку: она подсветится и станет целью для точечной правки и комментария.
            </li>
            <li>
              Поля карточки можно менять руками. Сохранение идёт само через ~секунду. На карте профессии: <b>Принять</b> / <b>Отклонить</b> пункт.
            </li>
            <li>
              <b>Справа → Вопрос</b> — спросить у AI, документ не меняется. <b>Блок</b> — правка только выбранной карточки. <b>Всё</b> — правка всего документа.
            </li>
            <li>
              <b>Коммент.</b> — ваша заметка к выбранному блоку или ко всему шагу, без вызова модели. <b>Источники</b> — файлы из Brief.
            </li>
            <li>
              AI-правка сначала показывает превью. Нажмите <b>Применить</b> или <b>Отклонить</b>. Пока превью не принято, текст в документе не меняется.
            </li>
            <li>
              <b>Сформировать / Пересобрать AI</b> создаёт черновик с нуля. Перед этим при необходимости разверните «Что уйдёт в агента» и поправьте задачу.
            </li>
            <li>
              <b>Зафиксировать</b> закрывает правки этого шага
              {stageType === "profession_map" ? " и переводит к сценарию." : "."} После фиксации доступен только режим вопроса, пока не сделаете новую редакцию.
            </li>
          </ul>
        )}
      </div>

      {outdated && (
        <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm dark:border-amber-800 dark:bg-amber-950/40">
          Карта профессии изменилась. Этот сценарий устарел — пересоберите его.
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
                onClick={() => setSectionId(s.id)}
              >
                {s.title}
                <span className="ml-1 text-xs opacity-60">({s.items?.length || 0})</span>
              </button>
            ))}
          </nav>

          <div className="space-y-3">
            {(currentSection?.items || []).map((item) => (
              <ItemCard
                key={item.id}
                item={item}
                selected={targetId === item.id}
                readOnly={locked}
                allowAcceptReject={!!allowAcceptReject && !locked}
                onSelect={() => setTargetId(item.id)}
                onChange={(next) => {
                  const copy = structuredClone(doc) as BlockDocument;
                  const sec = copy.sections?.find((s) => s.id === currentSection?.id);
                  if (!sec) return;
                  sec.items = sec.items.map((it) => (it.id === next.id ? next : it));
                  setArtifact({ ...artifact, content: copy });
                  scheduleItemSave(next);
                }}
                onAccept={() => void decide(item.id, "accept")}
                onReject={() => void decide(item.id, "reject")}
              />
            ))}
            {(!currentSection || currentSection.items.length === 0) && (
              <div className="panel text-sm text-neutral-500">В этой секции пока нет элементов.</div>
            )}
          </div>

          <AssistantPanel
            projectId={projectId}
            stageType={stageType}
            targetId={targetId}
            readOnly={locked}
            onPatched={() => void reload()}
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

function ItemCard({
  item,
  selected,
  readOnly,
  allowAcceptReject,
  onSelect,
  onChange,
  onAccept,
  onReject,
}: {
  item: DocItem;
  selected: boolean;
  readOnly: boolean;
  allowAcceptReject: boolean;
  onSelect: () => void;
  onChange: (item: DocItem) => void;
  onAccept: () => void;
  onReject: () => void;
}) {
  const skip = new Set(["id", "status", "items", "frames", "segments"]);
  const fields = Object.keys(item).filter((k) => !skip.has(k));
  return (
    <article
      className={`panel cursor-pointer space-y-2 ${selected ? "ring-2 ring-neutral-900 dark:ring-white" : ""}`}
      onClick={onSelect}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold">{String(item.title || item.id)}</h3>
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
            <label className="label text-xs">{k}</label>
            {typeof item[k] === "string" || typeof item[k] === "number" || item[k] == null ? (
              <textarea
                className="input min-h-[56px]"
                disabled={readOnly}
                value={item[k] == null ? "" : String(item[k])}
                onChange={(e) => onChange({ ...item, [k]: e.target.value })}
                onClick={(e) => e.stopPropagation()}
              />
            ) : (
              <pre className="max-h-32 overflow-auto whitespace-pre-wrap text-xs text-neutral-600">
                {JSON.stringify(item[k], null, 2)}
              </pre>
            )}
          </div>
        ))}
      {Array.isArray(item.frames) && (
        <p className="text-xs text-neutral-500">Кадров: {(item.frames as unknown[]).length}</p>
      )}
    </article>
  );
}
