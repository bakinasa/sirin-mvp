import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Artifact } from "../lib/api";

type Props = {
  artifact: Artifact | null;
  onUpdated: () => void;
  runMeta?: {
    model_name?: string;
    provider_name?: string;
    error_message?: string;
  } | null;
};

type Content = Record<string, unknown>;

function isMock(content: unknown): boolean {
  if (!content || typeof content !== "object") return false;
  const c = content as Content;
  if (c._mock === true) return true;
  const g = c._generation as Content | undefined;
  return g?.mode === "mock";
}

/** Human-readable view for structured TZ artifacts (not raw JSON wall). */
function ReadableView({ content }: { content: Content }) {
  const gen = (content._generation as Content) || {};
  const steps = (content.workflow_steps as { name?: string; order?: number; actions?: string[] }[]) || [];
  const goals = (content.learning_goals as string[]) || [];
  const errors = (content.typical_errors as string[]) || [];
  const risks = (content.critical_risks as string[]) || [];
  const actions = (content.observable_actions as string[]) || [];
  const clarifications = (content.clarifications_needed as string[]) || [];
  const sections = (content.sections as { heading?: string; body?: string }[]) || [];
  const whatToDo = (gen.what_to_do as string[]) || [];

  return (
    <div className="space-y-4 text-sm">
      {typeof content.summary_ru === "string" && (
        <p className="leading-relaxed text-neutral-700 dark:text-neutral-200">
          {content.summary_ru}
        </p>
      )}

      {isMock(content) && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100">
          <p className="font-semibold">Это заглушка, не ответ нейросети</p>
          <p className="mt-1 leading-relaxed">
            {String(gen.explanation_ru || "Реальная модель не была вызвана.")}
          </p>
          {typeof gen.reason === "string" && gen.reason && (
            <p className="mt-2 text-xs opacity-80">Техническая причина: {gen.reason}</p>
          )}
          {whatToDo.length > 0 && (
            <ol className="mt-2 list-decimal space-y-1 pl-5">
              {whatToDo.map((item, i) => (
                <li key={i}>{String(item)}</li>
              ))}
            </ol>
          )}
          <Link to="/models" className="mt-3 inline-block font-semibold underline">
            Перейти в «Модели» и добавить ключ
          </Link>
        </div>
      )}

      <div>
        <h4 className="font-semibold">{String(content.title || "Без названия")}</h4>
      </div>

      {goals.length > 0 && (
        <section>
          <h5 className="mb-1 font-semibold">Цели обучения</h5>
          <ul className="list-disc space-y-1 pl-5">
            {goals.map((g, i) => (
              <li key={i}>{g}</li>
            ))}
          </ul>
        </section>
      )}

      {steps.length > 0 && (
        <section>
          <h5 className="mb-1 font-semibold">Последовательность действий</h5>
          <ol className="space-y-2">
            {steps.map((s, i) => (
              <li key={i} className="rounded-md border border-neutral-200 p-2 dark:border-neutral-700">
                <p className="font-medium">
                  {s.order ?? i + 1}. {s.name}
                </p>
                <ul className="mt-1 list-disc pl-5 text-neutral-600 dark:text-neutral-300">
                  {(s.actions || []).map((a, j) => (
                    <li key={j}>{a}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
        </section>
      )}

      {errors.length > 0 && (
        <section>
          <h5 className="mb-1 font-semibold">Типичные ошибки</h5>
          <ul className="list-disc pl-5">
            {errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </section>
      )}

      {risks.length > 0 && (
        <section>
          <h5 className="mb-1 font-semibold">Критичные риски</h5>
          <ul className="list-disc pl-5">
            {risks.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </section>
      )}

      {actions.length > 0 && (
        <section>
          <h5 className="mb-1 font-semibold">Наблюдаемые действия</h5>
          <ul className="list-disc pl-5">
            {actions.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </section>
      )}

      {sections.length > 0 && (
        <section className="space-y-2">
          {sections.map((s, i) => (
            <div key={i}>
              <h5 className="font-semibold">{s.heading}</h5>
              <p className="text-neutral-600 dark:text-neutral-300">{s.body}</p>
            </div>
          ))}
        </section>
      )}

      {clarifications.length > 0 && (
        <section>
          <h5 className="mb-1 font-semibold">Требуются уточнения</h5>
          <ul className="list-disc pl-5">
            {clarifications.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

export function ArtifactEditor({ artifact, onUpdated, runMeta }: Props) {
  const [edit, setEdit] = useState("");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<"readable" | "json" | "diff">("readable");

  useEffect(() => {
    if (artifact) setEdit(JSON.stringify(artifact.content, null, 2));
  }, [artifact?.id, artifact?.updated_at]);

  if (!artifact) {
    return (
      <div className="panel text-sm text-neutral-500">
        Результат ещё не создан. Нажмите «Запустить AI».
      </div>
    );
  }

  const content = (artifact.content || {}) as Content;
  const mock = isMock(content);
  const original = JSON.stringify(artifact.content, null, 2);
  const changed = edit !== original;

  async function save() {
    setBusy(true);
    try {
      const parsed = JSON.parse(edit);
      await api(`/artifacts/${artifact!.id}`, {
        method: "PATCH",
        body: JSON.stringify({ content: parsed, comment }),
      });
      onUpdated();
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    if (mock && !confirm("Это заглушка без реального ИИ. Всё равно утвердить и идти дальше?")) {
      return;
    }
    setBusy(true);
    try {
      await api(`/artifacts/${artifact!.id}/approve`, {
        method: "POST",
        body: JSON.stringify({ comment }),
      });
      onUpdated();
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function reject() {
    setBusy(true);
    try {
      await api(`/artifacts/${artifact!.id}/reject`, {
        method: "POST",
        body: JSON.stringify({ comment }),
      });
      onUpdated();
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-lg font-semibold">
            Результат v{artifact.version}
            {mock ? " · ЗАГЛУШКА" : ` · ${artifact.status}`}
          </h3>
          <p className="text-sm text-neutral-500">
            {runMeta?.model_name
              ? `Модель: ${runMeta.model_name}${runMeta.provider_name ? ` (${runMeta.provider_name})` : ""}`
              : "Просмотрите текст, поправьте при необходимости, затем утвердите"}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            className={tab === "readable" ? "btn-primary" : "btn-ghost"}
            type="button"
            onClick={() => setTab("readable")}
          >
            Читаемо
          </button>
          <button
            className={tab === "json" ? "btn-primary" : "btn-ghost"}
            type="button"
            onClick={() => setTab("json")}
          >
            JSON
          </button>
          <button
            className={tab === "diff" ? "btn-primary" : "btn-ghost"}
            type="button"
            onClick={() => setTab("diff")}
          >
            Diff
          </button>
        </div>
      </div>

      {tab === "readable" && <ReadableView content={content} />}

      {tab === "json" && (
        <div className="grid gap-4 lg:grid-cols-2">
          <div>
            <p className="label">Исходная версия</p>
            <pre className="max-h-[420px] overflow-auto rounded-lg bg-neutral-950 p-3 font-mono text-xs text-neutral-100">
              {original}
            </pre>
          </div>
          <div>
            <p className="label">Ваши правки (JSON)</p>
            <textarea
              className="input min-h-[420px] font-mono text-xs"
              value={edit}
              onChange={(e) => setEdit(e.target.value)}
            />
          </div>
        </div>
      )}

      {tab === "diff" && (
        <pre className="max-h-[420px] overflow-auto rounded-lg border border-neutral-200 bg-neutral-50 p-3 font-mono text-xs dark:border-neutral-700 dark:bg-neutral-900">
          {changed
            ? `Есть несохранённые правки (дельта ≈ ${edit.length - original.length} символов). Нажмите «Сохранить правки».`
            : "Нет отличий от сохранённой версии."}
        </pre>
      )}

      <div>
        <label className="label">Комментарий к решению</label>
        <input className="input" value={comment} onChange={(e) => setComment(e.target.value)} />
      </div>

      <div className="flex flex-wrap gap-2">
        <button className="btn-ghost" disabled={busy || !changed} onClick={save}>
          Сохранить правки
        </button>
        <button className="btn-primary" disabled={busy} onClick={approve}>
          Утвердить
        </button>
        <button className="btn-danger" disabled={busy} onClick={reject}>
          Отклонить
        </button>
      </div>
    </div>
  );
}
