import { useEffect, useMemo, useState } from "react";
import { api, Artifact } from "../lib/api";
import { Modal } from "./Modal";

export function VersionHistoryModal({
  projectId,
  stepType,
  current,
  onClose,
  onRestored,
}: {
  projectId: string;
  stepType: string;
  current: Artifact | null;
  onClose: () => void;
  onRestored: () => void;
}) {
  const [versions, setVersions] = useState<Artifact[]>([]);
  const [view, setView] = useState<Artifact | null>(null);
  const [compare, setCompare] = useState<Artifact | null>(null);
  const [busy, setBusy] = useState("");

  useEffect(() => {
    api<Artifact[]>(`/projects/${projectId}/artifacts?step_type=${stepType}`).then(setVersions);
  }, [projectId, stepType]);

  async function restore(v: Artifact) {
    if (!current) return;
    if (!confirm(`Восстановить v${v.version} как новую рабочую версию?`)) return;
    setBusy(v.id);
    try {
      await api(`/artifacts/${current.id}/restore/${v.id}`, { method: "POST" });
      onRestored();
      onClose();
    } finally {
      setBusy("");
    }
  }

  return (
    <Modal title="История версий" onClose={onClose} wide>
      <ul className="space-y-2">
        {versions.map((v) => (
          <li key={v.id} className="rounded-lg border border-neutral-200 p-3 text-sm dark:border-neutral-700">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <span className="font-semibold">v{v.version}</span>
                {v.frozen ? " · freeze" : ""}
                {v.id === current?.id ? " · текущая" : ""}
                <p className="text-xs text-neutral-500">
                  {v.change_type || "—"} · {v.change_summary || "без описания"} ·{" "}
                  {new Date(v.created_at).toLocaleString("ru")}
                </p>
              </div>
              <div className="flex gap-2">
                <button type="button" className="btn-ghost" onClick={() => setView(v)}>
                  Смотреть
                </button>
                <button type="button" className="btn-ghost" onClick={() => setCompare(v)}>
                  Сравнить
                </button>
                {v.id !== current?.id && (
                  <button
                    type="button"
                    className="btn-primary"
                    disabled={!!busy}
                    onClick={() => void restore(v)}
                  >
                    Восстановить
                  </button>
                )}
              </div>
            </div>
          </li>
        ))}
      </ul>
      {view && (
        <pre className="mt-4 max-h-64 overflow-auto rounded-lg bg-neutral-50 p-3 text-xs dark:bg-neutral-900">
          {JSON.stringify(view.content, null, 2)}
        </pre>
      )}
      {compare && current && (
        <CompareView a={compare} b={current} />
      )}
    </Modal>
  );
}

function CompareView({ a, b }: { a: Artifact; b: Artifact }) {
  const text = useMemo(
    () =>
      `v${a.version} vs текущая v${b.version}\n\n--- v${a.version} ---\n${JSON.stringify(a.content, null, 2).slice(0, 4000)}\n\n--- текущая ---\n${JSON.stringify(b.content, null, 2).slice(0, 4000)}`,
    [a, b]
  );
  return (
    <pre className="mt-4 max-h-64 overflow-auto rounded-lg bg-neutral-50 p-3 text-xs dark:bg-neutral-900">
      {text}
    </pre>
  );
}
