import { useEffect, useState } from "react";
import { api, STEP_LABELS } from "../lib/api";

type Template = {
  id: string;
  step_type: string;
  role_name: string;
  version: string;
  content: string;
  is_active: boolean;
};

export function PromptsPage() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selected, setSelected] = useState<Template | null>(null);

  useEffect(() => {
    api<Template[]>("/prompt-templates").then(setTemplates);
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-4xl">Prompt Templates</h1>
        <p className="mt-1 text-ink-600 dark:text-ink-300">
          Версионируемые system templates. Без «магических» персон.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="panel space-y-2">
          <h2 className="font-display text-xl">System templates</h2>
          {templates.map((t) => (
            <button
              key={t.id}
              className="block w-full rounded-xl border border-ink-200/70 p-3 text-left hover:bg-ink-50 dark:border-ink-700 dark:hover:bg-ink-800"
              onClick={() => setSelected(t)}
            >
              <p className="font-medium">
                {STEP_LABELS[t.step_type] || t.step_type} · v{t.version}
                {t.is_active ? " · active" : ""}
              </p>
              <p className="text-xs text-ink-400">{t.role_name}</p>
            </button>
          ))}
        </div>
        <div className="panel">
          <h2 className="mb-2 font-display text-xl">Содержимое</h2>
          {selected ? (
            <pre className="max-h-[480px] overflow-auto whitespace-pre-wrap rounded-xl bg-ink-950 p-3 font-mono text-xs text-ink-100">
              {selected.content}
            </pre>
          ) : (
            <p className="text-sm text-ink-500">Выберите шаблон слева</p>
          )}
        </div>
      </div>

      {/* Operator presets не используются в Prompt Templates */}
    </div>
  );
}
