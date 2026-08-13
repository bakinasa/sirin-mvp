import { useEffect, useState } from "react";
import { api } from "../lib/api";

type PreviewBlock = {
  id?: string;
  title?: string;
  kind?: string;
  content?: unknown;
};

type Preview = {
  system_prompt: string;
  operator_prompt: string;
  blocks: PreviewBlock[];
  prompt_template_version: string;
  context_text?: string;
  user_message?: string;
};

type Props = {
  projectId: string;
  stepType: string;
  value: string;
  onChange: (v: string) => void;
  readOnly?: boolean;
};

/**
 * Collapsed-by-default preview of what the agent will receive.
 */
export function PromptPanel({ projectId, stepType, value, onChange, readOnly }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [system, setSystem] = useState("");
  const [blocks, setBlocks] = useState<PreviewBlock[]>([]);
  const [version, setVersion] = useState("");
  const [defaultOp, setDefaultOp] = useState("");
  const [userMessage, setUserMessage] = useState("");
  const [open, setOpen] = useState({
    system: false,
    context: false,
    operator: false,
    full: false,
  });
  const [history, setHistory] = useState<{ content: string; created_at: string }[]>([]);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadPreview() {
    setLoading(true);
    setError("");
    try {
      const preview = await api<Preview>(
        `/projects/${projectId}/prompt-preview?step_type=${encodeURIComponent(stepType)}`
      );
      setSystem(preview.system_prompt);
      setBlocks(preview.blocks || []);
      setVersion(preview.prompt_template_version);
      setDefaultOp(preview.operator_prompt);
      setUserMessage(preview.user_message || preview.context_text || "");
      if (!value) onChange(preview.operator_prompt);

      const hist = await api<{ content: string; created_at: string }[]>(
        `/projects/${projectId}/prompt-history?step_type=${encodeURIComponent(stepType)}`
      );
      setHistory(hist);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadPreview().catch(console.error);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, stepType]);

  async function savePreset() {
    setSaving(true);
    try {
      await api("/operator-prompt-presets", {
        method: "POST",
        body: JSON.stringify({
          step_type: stepType,
          title: `Custom ${new Date().toLocaleString("ru")}`,
          content: value,
          is_default: false,
        }),
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="panel space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <button
          type="button"
          className="flex min-w-0 flex-1 items-start justify-between gap-3 text-left"
          onClick={() => setExpanded((v) => !v)}
        >
          <span>
            <span className="block text-lg font-semibold">Что уйдёт в агента</span>
            <span className="text-sm text-neutral-500">
              {expanded
                ? "Системный промпт, контекст и задача. Разверните нужный подблок."
                : "Свёрнуто, чтобы не мешать работе. Нажмите, чтобы посмотреть вход модели."}
              {version ? ` · шаблон v${version}` : ""}
            </span>
          </span>
          <span className="shrink-0 text-xs text-neutral-400">{expanded ? "свернуть" : "развернуть"}</span>
        </button>
        {expanded && (
          <button type="button" className="btn-ghost" disabled={loading} onClick={() => void loadPreview()}>
            {loading ? "Обновляем…" : "Обновить превью"}
          </button>
        )}
      </div>

      {expanded && (
        <>
          {error && <p className="text-sm text-red-600">{error}</p>}

          <Section
            title="1. Системный промпт"
            hint="Роль и правила модели. Меняется в разделе «Промты»."
            open={open.system}
            onToggle={() => setOpen((s) => ({ ...s, system: !s.system }))}
          >
            <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded-lg bg-neutral-950 p-3 font-mono text-xs text-neutral-100">
              {system || "Нет системного промпта для этого шага."}
            </pre>
          </Section>

          <Section
            title="2. Контекст проекта"
            hint="Brief, выжимки файлов и релевантные фрагменты. Чтобы изменить — правьте Brief и материалы."
            open={open.context}
            onToggle={() => setOpen((s) => ({ ...s, context: !s.context }))}
          >
            {blocks.length === 0 ? (
              <p className="text-sm text-neutral-500">Контекст пока пустой.</p>
            ) : (
              <div className="space-y-3">
                {blocks.map((block, i) => (
                  <div
                    key={block.id || String(i)}
                    className="rounded-lg border border-neutral-200 p-3 dark:border-neutral-700"
                  >
                    <p className="mb-1 text-sm font-semibold">{block.title || block.id || `Блок ${i + 1}`}</p>
                    <pre className="max-h-48 overflow-auto whitespace-pre-wrap font-mono text-xs text-neutral-700 dark:text-neutral-200">
                      {formatBlock(block.content)}
                    </pre>
                  </div>
                ))}
              </div>
            )}
          </Section>

          <Section
            title="3. Задача оператора"
            hint="Можно править прямо здесь. Этот текст уйдёт в модель вместе с контекстом."
            open={open.operator}
            onToggle={() => setOpen((s) => ({ ...s, operator: !s.operator }))}
          >
            <textarea
              className="input min-h-[140px] font-mono text-sm"
              value={value}
              disabled={readOnly}
              onChange={(e) => onChange(e.target.value)}
            />
            <div className="mt-2 flex flex-wrap gap-2">
              <button type="button" className="btn-ghost" onClick={() => onChange(defaultOp)}>
                Сбросить к шаблону
              </button>
              <button
                type="button"
                className="btn-ghost"
                disabled={saving || readOnly}
                onClick={() => void savePreset()}
              >
                Сохранить как preset
              </button>
            </div>
          </Section>

          <Section
            title="4. Полное user-сообщение"
            hint="Итоговый текст, который модель получит как user (контекст + задача + схема)."
            open={open.full}
            onToggle={() => setOpen((s) => ({ ...s, full: !s.full }))}
          >
            <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-neutral-100 p-3 font-mono text-xs dark:bg-neutral-900">
              {userMessage || "Нажмите «Обновить превью», чтобы увидеть полный текст."}
            </pre>
          </Section>

          {history.length > 0 && (
            <div>
              <p className="label">История задач оператора</p>
              <ul className="space-y-2 text-sm">
                {history.slice(0, 5).map((h, i) => (
                  <li key={i}>
                    <button
                      type="button"
                      className="text-left underline"
                      onClick={() => onChange(h.content)}
                    >
                      {new Date(h.created_at).toLocaleString("ru")} — восстановить
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function Section({
  title,
  hint,
  open,
  onToggle,
  children,
}: {
  title: string;
  hint: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-neutral-200 px-3 py-2 dark:border-neutral-700">
      <button type="button" className="flex w-full items-start justify-between gap-3 text-left" onClick={onToggle}>
        <span>
          <span className="block font-semibold">{title}</span>
          <span className="text-xs text-neutral-500">{hint}</span>
        </span>
        <span className="shrink-0 text-xs text-neutral-400">{open ? "скрыть" : "показать"}</span>
      </button>
      {open && <div className="mt-2">{children}</div>}
    </div>
  );
}

function formatBlock(content: unknown): string {
  if (content == null) return "—";
  if (typeof content === "string") return content;
  return JSON.stringify(content, null, 2);
}
