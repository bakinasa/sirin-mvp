import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api, Brief, PipelineStep, Project, ProjectSource } from "../lib/api";
import { PipelineStepper } from "../components/PipelineStepper";
import { ModelSelector } from "../components/ModelSelector";
import { Modal } from "../components/Modal";

const DEFAULT_OBJECTIVES =
  "Обучение безопасному и корректному выполнению рабочей операции. Диагностика навыка через поиск нарушений.";

type Tab = "main" | "sources" | "notes";

export function BriefEditorPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [brief, setBrief] = useState<Brief | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [steps, setSteps] = useState<PipelineStep[]>([]);
  const [sources, setSources] = useState<ProjectSource[]>([]);
  const [tab, setTab] = useState<Tab>("main");
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState("");
  const [approving, setApproving] = useState(false);
  const [message, setMessage] = useState("");
  const [uploading, setUploading] = useState(false);
  const [busySourceId, setBusySourceId] = useState("");
  const [primaryId, setPrimaryId] = useState("");
  const [fallbackId, setFallbackId] = useState("");
  const [preview, setPreview] = useState<ProjectSource | null>(null);
  const [summaryPrompt, setSummaryPrompt] = useState<{ content: string; version: string; role_name: string } | null>(
    null
  );
  const [promptError, setPromptError] = useState("");
  const timer = useRef<number | null>(null);

  const reloadSources = useCallback(async () => {
    if (!projectId) return;
    setSources(await api<ProjectSource[]>(`/projects/${projectId}/sources`));
  }, [projectId]);

  useEffect(() => {
    if (!projectId || tab !== "sources") return;
    const hasPending = sources.some(
      (s) => s.parse_status === "summarizing" || s.parse_status === "parsing" || s.parse_status === "pending"
    );
    if (!hasPending) return;
    const timerId = window.setInterval(() => {
      void reloadSources();
    }, 3000);
    return () => window.clearInterval(timerId);
  }, [projectId, tab, sources, reloadSources]);

  useEffect(() => {
    if (!projectId) return;
    Promise.all([
      api<Brief>(`/projects/${projectId}/brief`),
      api<Project>(`/projects/${projectId}`),
      api<PipelineStep[]>(`/projects/${projectId}/pipeline`),
      api<ProjectSource[]>(`/projects/${projectId}/sources`),
    ]).then(([b, p, s, src]) => {
      if (!b.content_json.learning_objectives) {
        b.content_json.learning_objectives = DEFAULT_OBJECTIVES;
      }
      setBrief(b);
      setProject(p);
      setSteps(s);
      setSources(src);
    });
  }, [projectId]);

  useEffect(() => {
    if (tab !== "sources") return;
    api<{ content: string; version: string; role_name: string; is_active: boolean }[]>(
      "/prompt-templates?step_type=source_summary"
    )
      .then((rows) => {
        const active = rows.find((r) => r.is_active) || rows[0] || null;
        setSummaryPrompt(active);
        setPromptError(active ? "" : "Шаблон source_summary не найден. Используется запасной текст в коде.");
      })
      .catch((e) => setPromptError(String(e)));
  }, [tab]);

  function scheduleBriefSave(next: Brief) {
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(async () => {
      setSaving(true);
      try {
        const saved = await api<Brief>(`/projects/${projectId}/brief`, {
          method: "PUT",
          body: JSON.stringify({ content_json: next.content_json }),
        });
        setBrief(saved);
        setSavedAt(new Date().toLocaleTimeString("ru"));
      } finally {
        setSaving(false);
      }
    }, 600);
  }

  function scheduleProjectSave(next: Project) {
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(async () => {
      setSaving(true);
      try {
        const saved = await api<Project>(`/projects/${projectId}`, {
          method: "PATCH",
          body: JSON.stringify({
            title: next.title,
            client_name: next.client_name,
            profession: next.profession,
            delivery_format: next.delivery_format,
            constraints: next.constraints,
          }),
        });
        setProject(saved);
        setSavedAt(new Date().toLocaleTimeString("ru"));
      } finally {
        setSaving(false);
      }
    }, 600);
  }

  async function approve() {
    if (!projectId) return;
    setApproving(true);
    setMessage("");
    try {
      const saved = await api<Brief>(`/projects/${projectId}/brief/approve`, { method: "POST" });
      setBrief(saved);
      const nextSteps = await api<PipelineStep[]>(`/projects/${projectId}/pipeline`);
      setSteps(nextSteps);
      await queryClient.invalidateQueries({ queryKey: ["pipeline", projectId] });
      setMessage("Brief утверждён. Переходим к карте профессии…");
      window.setTimeout(() => navigate(`/projects/${projectId}/profession-map`), 700);
    } catch (e) {
      setMessage(`Не удалось утвердить: ${e}`);
    } finally {
      setApproving(false);
    }
  }

  async function onFiles(files: FileList | null) {
    if (!files || !projectId) return;
    setUploading(true);
    setMessage("");
    try {
      for (const file of Array.from(files)) {
        const fd = new FormData();
        fd.append("file", file);
        if (primaryId) fd.append("primary_model_id", primaryId);
        if (fallbackId) fd.append("fallback_model_id", fallbackId);
        await api(`/projects/${projectId}/sources`, { method: "POST", body: fd });
      }
      await reloadSources();
    } catch (e) {
      setMessage(`Загрузка не удалась: ${e}`);
    } finally {
      setUploading(false);
    }
  }

  async function reprocess(id: string) {
    setBusySourceId(id);
    setMessage("");
    try {
      await api(`/sources/${id}/reprocess`, {
        method: "POST",
        body: JSON.stringify({
          primary_model_id: primaryId || null,
          fallback_model_id: fallbackId || null,
        }),
      });
      await reloadSources();
    } catch (e) {
      setMessage(`Пересобрать не удалось: ${e}`);
    } finally {
      setBusySourceId("");
    }
  }

  async function removeSource(id: string, title: string) {
    if (!window.confirm(`Удалить файл «${title}» и его выжимку?`)) return;
    await api(`/sources/${id}`, { method: "DELETE" });
    if (preview?.id === id) setPreview(null);
    await reloadSources();
  }

  async function showSource(id: string) {
    setPreview(await api<ProjectSource>(`/sources/${id}`));
  }

  if (!projectId || !brief || !project) return <div className="panel">Загрузка brief…</div>;

  const alreadyApproved = brief.status === "approved";
  const cj = brief.content_json;

  return (
    <div>
      <PipelineStepper projectId={projectId} steps={steps} />
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Brief и материалы</h1>
          <p className="mt-1 max-w-2xl text-sm text-neutral-600 dark:text-neutral-300">
            Короткий старт проекта. Основной контекст дают загруженные документы по профессии.
          </p>
          <p className="mt-1 text-xs text-neutral-500">
            Автосохранение · v{brief.version} · {brief.status}
            {savedAt && ` · сохранено ${savedAt}`}
            {saving && " · сохраняем…"}
          </p>
        </div>
        <button className="btn-primary" onClick={approve} disabled={approving || alreadyApproved}>
          {alreadyApproved ? "Brief уже утверждён" : approving ? "Утверждаем…" : "Утвердить и перейти к карте"}
        </button>
      </div>

      {message && (
        <div className="mb-4 rounded-lg border border-neutral-200 bg-neutral-50 px-4 py-3 text-sm dark:border-neutral-700 dark:bg-neutral-900">
          {message}
        </div>
      )}

      <div className="mb-4 flex gap-2">
        {(
          [
            ["main", "Основное"],
            ["sources", "Материалы"],
            ["notes", "Заметки"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={tab === id ? "btn-primary" : "btn-ghost"}
            onClick={() => setTab(id)}
          >
            {label}
            {id === "sources" ? ` (${sources.length})` : ""}
          </button>
        ))}
      </div>

      {tab === "main" && (
        <div className="panel grid gap-5">
          <Field label="Название проекта" value={project.title} disabled={alreadyApproved} onChange={(v) => {
            const next = { ...project, title: v };
            setProject(next);
            scheduleProjectSave(next);
          }} />
          <Field label="Заказчик" value={project.client_name} disabled={alreadyApproved} onChange={(v) => {
            const next = { ...project, client_name: v };
            setProject(next);
            scheduleProjectSave(next);
          }} />
          <Field label="Профессия" value={project.profession} disabled={alreadyApproved} onChange={(v) => {
            const next = { ...project, profession: v };
            setProject(next);
            scheduleProjectSave(next);
          }} />
          <Field
            label="Рабочая операция"
            value={cj.work_operation || ""}
            disabled={alreadyApproved}
            onChange={(v) => {
              const next = { ...brief, content_json: { ...cj, work_operation: v } };
              setBrief(next);
              scheduleBriefSave(next);
            }}
          />
          <div>
            <label className="label">Формат</label>
            <select
              className="input"
              value={project.delivery_format || ""}
              disabled={alreadyApproved}
              onChange={(e) => {
                const next = { ...project, delivery_format: e.target.value };
                setProject(next);
                scheduleProjectSave(next);
              }}
            >
              <option value="">Не выбран</option>
              <option value="VR">VR</option>
              <option value="планшет">Планшет</option>
              <option value="VR / планшет">VR / планшет</option>
            </select>
          </div>
          <Area
            label="Короткое описание задачи"
            value={cj.task_description || ""}
            disabled={alreadyApproved}
            onChange={(v) => {
              const next = { ...brief, content_json: { ...cj, task_description: v } };
              setBrief(next);
              scheduleBriefSave(next);
            }}
          />
          <Area
            label="Ограничения"
            value={project.constraints}
            disabled={alreadyApproved}
            onChange={(v) => {
              const next = { ...project, constraints: v };
              setProject(next);
              scheduleProjectSave(next);
            }}
          />
          <Area
            label="Цели модуля"
            hint="Можно оставить почти как есть."
            value={cj.learning_objectives || DEFAULT_OBJECTIVES}
            disabled={alreadyApproved}
            onChange={(v) => {
              const next = { ...brief, content_json: { ...cj, learning_objectives: v } };
              setBrief(next);
              scheduleBriefSave(next);
            }}
          />
        </div>
      )}

      {tab === "sources" && (
        <div className="space-y-4">
          <SourceSummaryHelp prompt={summaryPrompt} error={promptError} />
          <div className="panel space-y-3">
            <h3 className="font-semibold">Модель для выжимок</h3>
            <ModelSelector
              primaryId={primaryId}
              fallbackId={fallbackId}
              onPrimary={setPrimaryId}
              onFallback={setFallbackId}
            />
          </div>
          <label
            className="panel flex cursor-pointer flex-col items-center justify-center gap-2 border-dashed py-10 text-sm text-neutral-500"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              void onFiles(e.dataTransfer.files);
            }}
          >
            <input
              type="file"
              className="hidden"
              multiple
              accept=".pdf,.docx,.txt,.md,.doc,application/pdf"
              onChange={(e) => void onFiles(e.target.files)}
            />
            {uploading ? "Загружаем и ставим в очередь…" : "Перетащите файлы сюда или нажмите, чтобы выбрать (PDF, DOCX, TXT)"}
          </label>
          {sources.length === 0 ? (
            <div className="panel text-sm text-neutral-500">Пока нет материалов. Загрузите СОП, инструкции, регламенты.</div>
          ) : (
            <ul className="space-y-3">
              {sources.map((s) => (
                <li key={s.id} className="panel space-y-2">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <p className="font-semibold">{s.title}</p>
                      <p className="text-xs text-neutral-500">
                        {s.source_type} · {s.parse_status}
                        {s.parse_status === "summarizing" && s.summary_progress?.part_total
                          ? ` · ${s.summary_progress.message || `часть ${s.summary_progress.part_done}/${s.summary_progress.part_total}`}`
                          : ""}
                        {s.parse_error && s.parse_status !== "summarizing" ? ` · ${s.parse_error}` : ""}
                        {s.parse_error && s.parse_status === "summarizing" && !s.summary_progress?.part_total
                          ? ` · ${s.parse_error}`
                          : ""}
                      </p>
                      {s.parse_status === "summarizing" && (s.summary_progress?.part_total ?? 0) > 0 && (
                        <div className="mt-1 h-1.5 w-full max-w-xs overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-800">
                          <div
                            className="h-full rounded-full bg-sky-500 transition-all"
                            style={{ width: `${s.summary_progress?.percent ?? 0}%` }}
                          />
                        </div>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button type="button" className="btn-ghost" onClick={() => void showSource(s.id)}>
                        Выжимка
                      </button>
                      <button
                        type="button"
                        className="btn-ghost"
                        disabled={busySourceId === s.id}
                        onClick={() => void reprocess(s.id)}
                      >
                        {busySourceId === s.id ? "Собираем…" : "Пересобрать"}
                      </button>
                      <button
                        type="button"
                        className="btn-ghost text-red-700 dark:text-red-400"
                        onClick={() => void removeSource(s.id, s.title)}
                      >
                        Удалить
                      </button>
                    </div>
                  </div>
                  {Array.isArray(s.summary_short_json) && s.summary_short_json.length > 0 && (
                    <ul className="list-disc pl-5 text-sm">
                      {(s.summary_short_json as string[]).slice(0, 6).map((line, i) => (
                        <li key={i}>{typeof line === "string" ? line : JSON.stringify(line)}</li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {tab === "notes" && (
        <div className="panel">
          <Area
            label="Заметки после разговора с заказчиком"
            value={cj.customer_notes || cj.notes || ""}
            disabled={alreadyApproved}
            onChange={(v) => {
              const next = { ...brief, content_json: { ...cj, customer_notes: v, notes: v } };
              setBrief(next);
              scheduleBriefSave(next);
            }}
          />
        </div>
      )}

      {preview && (
        <Modal title={preview.title} onClose={() => setPreview(null)} wide>
          <p className="mb-2 text-xs text-neutral-500">
            {preview.parse_status}
            {preview.has_parsed_text ? " · текст извлечён" : " · текст не извлечён"}
          </p>
          {preview.parse_error && (
            <p className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm dark:border-amber-800 dark:bg-amber-950/40">
              {preview.parse_error}
            </p>
          )}
          <h3 className="mb-1 font-semibold">Краткая выжимка</h3>
          <pre className="mb-4 max-h-40 overflow-auto whitespace-pre-wrap text-sm">
            {JSON.stringify(preview.summary_short_json, null, 2)}
          </pre>
          <h3 className="mb-1 font-semibold">Структура</h3>
          <pre className="mb-4 max-h-40 overflow-auto whitespace-pre-wrap text-sm">
            {JSON.stringify(preview.summary_structured_json, null, 2)}
          </pre>
          <h3 className="mb-1 font-semibold">Важные фрагменты</h3>
          <pre className="mb-4 max-h-40 overflow-auto whitespace-pre-wrap text-sm">
            {JSON.stringify(preview.important_chunks_json, null, 2)}
          </pre>
          {preview.parsed_text ? (
            <>
              <h3 className="mb-1 font-semibold">Извлечённый текст (начало)</h3>
              <pre className="max-h-40 overflow-auto whitespace-pre-wrap text-xs text-neutral-600 dark:text-neutral-300">
                {preview.parsed_text.slice(0, 2500)}
              </pre>
            </>
          ) : null}
        </Modal>
      )}
    </div>
  );
}

const FALLBACK_SUMMARY_PROMPT = `Ты выполняешь высокоточную выжимку документа по профессии, операции, инструкции, процедуре или нормативным требованиям.

Твоя цель — сократить текст без потери существенного смысла. Приоритет: полнота критически важной информации выше краткости. Ты не пишешь свободное резюме; ты извлекаешь опорные факты из текста.

Правила:
1. Используй только информацию, явно содержащуюся в документе.
2. Ничего не додумывай, не обобщай сверх текста и не подменяй формулировки более общими.
3. Если фрагмент неясен, оборван, противоречив или выглядит неполным, укажи unclear.
4. Не смешивай разные требования, этапы, ограничения или запреты в один пункт, если в тексте они различаются.
5. Обязательно сохраняй числа, сроки, единицы, условия, исключения, запреты, порядок действий, роли и критерии проверки.
6. Убирай только буквальные повторы, не удаляй смысловые различия.
7. Если видна только часть документа, отрази это в constraints.
8. Верни только валидный JSON без markdown и комментариев.
9. Если для поля нет данных, верни пустой массив [].

Поля: brief_points, operations, skills, violations, visual_points, constraints, terms, important_fragments.`;

function SourceSummaryHelp({
  prompt,
  error,
}: {
  prompt: { content: string; version: string; role_name: string } | null;
  error: string;
}) {
  const [open, setOpen] = useState(true);
  const [promptOpen, setPromptOpen] = useState(true);
  const systemText = prompt?.content || FALLBACK_SUMMARY_PROMPT;

  return (
    <div className="rounded-xl border border-neutral-200 bg-neutral-50 px-4 py-3 dark:border-neutral-700 dark:bg-neutral-900/50">
      <button
        type="button"
        className="flex w-full items-start justify-between gap-3 text-left"
        onClick={() => setOpen((v) => !v)}
      >
        <span>
          <span className="block font-semibold">Как делается выжимка</span>
          <span className="text-sm text-neutral-500">
            Правила, ограничения и промпт, который уходит в модель при обработке файла.
          </span>
        </span>
        <span className="shrink-0 text-xs text-neutral-400">{open ? "скрыть" : "показать"}</span>
      </button>
      {open && (
        <div className="mt-3 space-y-3 text-sm text-neutral-700 dark:text-neutral-300">
          <ol className="list-decimal space-y-1.5 pl-5">
            <li>Файл сохраняется, из PDF / DOCX / TXT извлекается текст.</li>
            <li>Текст режется на фрагменты (~1100 символов с перекрытием 150) — они нужны для поиска, не для самой выжимки.</li>
            <li>
              Модель получает системный промпт ниже и <b>весь извлечённый текст</b>. Длинный документ режется на части
              по границам страниц; до 3 частей обрабатываются параллельно, затем выжимки объединяются. Ответ — JSON:
              пункты, операции, навыки, нарушения, визуальные точки, ограничения, термины и цитаты.
            </li>
            <li>
              Загрузка возвращается сразу после извлечения текста; выжимка идёт в фоне со статусом summarizing и
              прогрессом по частям.
            </li>
            <li>
              В карту и сценарий потом уходит эта выжимка, а не весь файл. По запросу добавляются несколько найденных
              фрагментов.
            </li>
          </ol>
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm dark:border-amber-800 dark:bg-amber-950/40">
            <p className="font-semibold">Ограничения и зачем так</p>
            <ul className="mt-1 list-disc space-y-1 pl-5">
              <li>
                Картинки и сканы без текстового слоя не разбираются: OCR не включён, чтобы не тащить тяжёлый контур и не
                гадать по пикселям.
              </li>
              <li>
                В модель на выжимку идёт весь извлечённый текст. Если файл длинный, он обрабатывается по частям, чтобы
                не обрезать СОП и не терять нормы.
              </li>
              <li>
                Карта/чат не получают сырой PDF целиком — только готовую выжимку и релевантные фрагменты по запросу.
              </li>
              <li>
                Если модель не ответила, статус будет ошибкой, а не пустой «успешной» выжимкой. Нажмите «Пересобрать».
              </li>
            </ul>
          </div>
          <div className="rounded-lg border border-neutral-200 px-3 py-2 dark:border-neutral-700">
            <button
              type="button"
              className="flex w-full items-start justify-between gap-3 text-left"
              onClick={() => setPromptOpen((v) => !v)}
            >
              <span>
                <span className="block font-semibold">Промпт выжимки</span>
                <span className="text-xs text-neutral-500">
                  {prompt
                    ? `Шаблон source_summary · роль ${prompt.role_name} · v${prompt.version}. Меняется в разделе «Промты».`
                    : "Активный шаблон не загрузился — показан запасной текст из кода."}
                </span>
              </span>
              <span className="shrink-0 text-xs text-neutral-400">{promptOpen ? "скрыть" : "показать"}</span>
            </button>
            {promptOpen && (
              <div className="mt-2 space-y-2">
                {error && <p className="text-xs text-amber-700">{error}</p>}
                <p className="text-xs font-medium text-neutral-500">Системный промпт</p>
                <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded-lg bg-neutral-950 p-3 font-mono text-xs text-neutral-100">
                  {systemText}
                </pre>
                <p className="text-xs font-medium text-neutral-500">User-сообщение (собирается при загрузке)</p>
                <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded-lg bg-neutral-100 p-3 font-mono text-xs dark:bg-neutral-900">
                  {`Файл: <имя файла>
Тип: <sop | checklist | regulation | …>

Проанализируй только текст между маркерами.
Если текст выглядит обрезанным, неполным или начинается/заканчивается на середине мысли, отрази это в constraints.
Сохраняй критические детали: числа, единицы измерения, сроки, роли, последовательности действий, условия, исключения, запреты, критерии проверки и основания для нарушений.
Не объединяй разные нормы в один общий пункт.
Верни ТОЛЬКО JSON.

=== DOCUMENT TEXT ===
<извлечённый текст целиком; длинный файл — по частям>
=== END ===`}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  disabled,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <div>
      <label className="label">{label}</label>
      <input className="input" value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

function Area({
  label,
  value,
  onChange,
  disabled,
  hint,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
  hint?: string;
}) {
  return (
    <div>
      <label className="label">{label}</label>
      {hint && <p className="mb-1.5 text-xs text-neutral-500">{hint}</p>}
      <textarea
        className="input min-h-[88px]"
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
