import { useEffect, useMemo, useState } from "react";
import { api, STEP_LABELS } from "../lib/api";

type Template = {
  id: string;
  step_type: string;
  role_name: string;
  version: string;
  content: string;
  is_active: boolean;
};

/** Only these are used in the current pipeline — show one active template each. */
const PIPELINE_PROMPTS = [
  "source_summary",
  "profession_map",
  "scenario_plan",
  "chat_ask",
  "chat_local_edit",
  "chat_global_edit",
] as const;

export function PromptsPage() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selected, setSelected] = useState<Template | null>(null);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  async function reload() {
    const rows = await api<Template[]>("/prompt-templates");
    // One active template per pipeline step — no version history in the list.
    const byStep = new Map<string, Template>();
    for (const row of rows) {
      if (!PIPELINE_PROMPTS.includes(row.step_type as (typeof PIPELINE_PROMPTS)[number])) continue;
      if (!row.is_active) continue;
      const prev = byStep.get(row.step_type);
      if (!prev || Number(row.version) > Number(prev.version)) {
        byStep.set(row.step_type, row);
      }
    }
    const visible = PIPELINE_PROMPTS.map((k) => byStep.get(k)).filter(Boolean) as Template[];
    setTemplates(visible);
    setSelected((prev) => {
      if (!prev) return prev;
      return visible.find((r) => r.id === prev.id) || visible.find((r) => r.step_type === prev.step_type) || null;
    });
  }

  useEffect(() => {
    reload().catch(console.error);
  }, []);

  useEffect(() => {
    setDraft(selected?.content || "");
    setMessage("");
  }, [selected?.id]);

  const list = useMemo(() => templates, [templates]);

  async function save() {
    if (!selected) return;
    setSaving(true);
    setMessage("");
    try {
      const updated = await api<Template>(`/prompt-templates/${selected.id}`, {
        method: "PATCH",
        body: JSON.stringify({ content: draft, is_active: true }),
      });
      setSelected(updated);
      await reload();
      setMessage("Сохранено. Новые генерации и выжимки возьмут этот текст.");
    } catch (e) {
      setMessage(`Не удалось сохранить: ${e}`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Промты</h1>
        <p className="mt-1 max-w-3xl text-sm text-neutral-600 dark:text-neutral-300">
          Только рабочие системные шаблоны пайплайна. Правьте текст — он уходит в модель как system prompt.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="panel space-y-2">
          <h2 className="text-lg font-semibold">Системные шаблоны</h2>
          <p className="text-xs text-neutral-500">
            Выжимка файлов, карта профессии, сценарий и три режима чата.
          </p>
          {list.length === 0 && (
            <p className="text-sm text-neutral-500">Шаблоны ещё не загружены. Перезапустите API / seed.</p>
          )}
          {list.map((t) => (
            <button
              key={t.id}
              type="button"
              className={
                selected?.id === t.id
                  ? "block w-full rounded-xl border border-neutral-900 bg-neutral-900 p-3 text-left text-white dark:border-white dark:bg-white dark:text-neutral-900"
                  : "block w-full rounded-xl border border-neutral-200 p-3 text-left hover:bg-neutral-50 dark:border-neutral-700 dark:hover:bg-neutral-800"
              }
              onClick={() => setSelected(t)}
            >
              <p className="font-medium">{STEP_LABELS[t.step_type] || t.step_type}</p>
              <p className="text-xs opacity-70">{t.role_name}</p>
            </button>
          ))}
        </div>

        <div className="panel space-y-3">
          <h2 className="text-lg font-semibold">Редактирование</h2>
          {selected ? (
            <>
              <p className="text-sm text-neutral-500">
                {STEP_LABELS[selected.step_type] || selected.step_type}
              </p>
              <textarea
                className="input min-h-[360px] font-mono text-xs"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
              />
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="btn-primary"
                  disabled={saving || draft === selected.content}
                  onClick={() => void save()}
                >
                  {saving ? "Сохраняем…" : "Сохранить"}
                </button>
                <button
                  type="button"
                  className="btn-ghost"
                  disabled={draft === selected.content}
                  onClick={() => setDraft(selected.content)}
                >
                  Сбросить
                </button>
              </div>
              {message && <p className="text-sm text-neutral-600 dark:text-neutral-300">{message}</p>}
            </>
          ) : (
            <p className="text-sm text-neutral-500">Выберите шаблон слева</p>
          )}
        </div>
      </div>
    </div>
  );
}
