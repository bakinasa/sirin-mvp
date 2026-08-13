import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";

type Model = {
  id: string;
  model_id: string;
  label: string;
  is_free: boolean;
  provider_name?: string | null;
};

type Props = {
  primaryId: string;
  fallbackId: string;
  onPrimary: (id: string) => void;
  onFallback: (id: string) => void;
  stepType?: string;
  compact?: boolean;
};

export function ModelSelector({ primaryId, fallbackId, onPrimary, onFallback, compact }: Props) {
  const [models, setModels] = useState<Model[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const list = await api<Model[]>("/user-models");
      setModels(list);

      const ids = new Set(list.map((m) => m.id));
      if (!primaryId && list[0]) onPrimary(list[0].id);
      else if (primaryId && !ids.has(primaryId)) onPrimary(list[0]?.id || "");

      if (!fallbackId && list[1]) onFallback(list[1].id);
      else if (fallbackId && !ids.has(fallbackId)) onFallback(list[1]?.id || "");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load().catch(console.error);
    const onFocus = () => load().catch(console.error);
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (compact) {
    return (
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs font-medium text-neutral-500">Модель</p>
          <button type="button" className="btn-ghost px-2 py-0.5 text-xs" onClick={() => load()} disabled={loading}>
            {loading ? "…" : "Обновить"}
          </button>
        </div>
        {loading ? (
          <p className="text-xs text-neutral-500">Загрузка…</p>
        ) : models.length === 0 ? (
          <p className="text-xs text-amber-700">
            Нет моделей. Добавьте ключ в{" "}
            <Link to="/models" className="underline">
              «Модели»
            </Link>
            .
          </p>
        ) : (
          <div className="grid gap-2">
            <div>
              <label className="label">Primary</label>
              <select className="input" value={primaryId} onChange={(e) => onPrimary(e.target.value)}>
                {models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {(m.provider_name ? `${m.provider_name}: ` : "") + m.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Fallback</label>
              <select className="input" value={fallbackId} onChange={(e) => onFallback(e.target.value)}>
                <option value="">Нет</option>
                {models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {(m.provider_name ? `${m.provider_name}: ` : "") + m.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="panel space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-lg font-semibold">Выбор модели</h3>
          <p className="text-sm text-neutral-500 dark:text-neutral-300">
            В списке только модели, которые вы добавили в разделе «Модели» (и которые
            содержат ваш BYOK).
          </p>
        </div>
        <button type="button" className="btn-ghost" onClick={() => load()} disabled={loading}>
          Обновить список
        </button>
      </div>

      {loading ? (
        <p className="text-sm text-neutral-500">Загрузка моделей…</p>
      ) : models.length === 0 ? (
        <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-3 text-sm text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100">
          <p className="font-semibold">Нет доступных моделей</p>
          <p className="mt-1">Добавьте ключ в «Модели», затем Sync models или Add model manually.</p>
          <Link to="/models" className="mt-2 inline-block font-semibold underline">
            Открыть «Модели»
          </Link>
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <label className="label">Primary</label>
            <select className="input" value={primaryId} onChange={(e) => onPrimary(e.target.value)}>
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {(m.provider_name ? `${m.provider_name}: ` : "") + m.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Fallback</label>
            <select className="input" value={fallbackId} onChange={(e) => onFallback(e.target.value)}>
              <option value="">Нет</option>
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {(m.provider_name ? `${m.provider_name}: ` : "") + m.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}
    </div>
  );
}
