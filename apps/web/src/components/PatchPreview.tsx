import { ArtifactPatch } from "../lib/api";

export function PatchPreview({
  patch,
  onApply,
  onDiscard,
  busy,
}: {
  patch: ArtifactPatch;
  onApply: () => void;
  onDiscard: () => void;
  busy?: boolean;
}) {
  const changes = extractChanges(patch.patch_json);
  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-800 dark:bg-amber-950/30">
      <p className="mb-2 font-semibold">Превью правки ({patch.scope})</p>
      <p className="mb-2 text-xs text-neutral-600 dark:text-neutral-300">{patch.instruction}</p>
      {changes.length === 0 ? (
        <pre className="max-h-40 overflow-auto whitespace-pre-wrap text-xs">
          {JSON.stringify(patch.patch_json, null, 2)}
        </pre>
      ) : (
        <ul className="space-y-2">
          {changes.map((c, i) => (
            <li key={i} className="rounded border border-neutral-200 p-2 dark:border-neutral-700">
              <p className="text-xs font-semibold">{c.target_id}</p>
              {c.rationale && <p className="text-xs text-neutral-500">{c.rationale}</p>}
              <div className="mt-1 grid gap-2 md:grid-cols-2">
                <pre className="max-h-28 overflow-auto whitespace-pre-wrap text-[11px] text-red-800">
                  {fmt(c.old)}
                </pre>
                <pre className="max-h-28 overflow-auto whitespace-pre-wrap text-[11px] text-emerald-800">
                  {fmt(c.new)}
                </pre>
              </div>
            </li>
          ))}
        </ul>
      )}
      {patch.status === "draft" && (
        <div className="mt-3 flex gap-2">
          <button type="button" className="btn-primary" disabled={busy} onClick={onApply}>
            Применить
          </button>
          <button type="button" className="btn-ghost" disabled={busy} onClick={onDiscard}>
            Отклонить
          </button>
        </div>
      )}
    </div>
  );
}

function extractChanges(patch: unknown): { target_id: string; old?: unknown; new?: unknown; rationale?: string }[] {
  if (!patch || typeof patch !== "object") return [];
  const p = patch as Record<string, unknown>;
  if (Array.isArray(p.changes)) {
    return p.changes.filter((c) => c && typeof c === "object") as {
      target_id: string;
      old?: unknown;
      new?: unknown;
      rationale?: string;
    }[];
  }
  if (typeof p.target_id === "string") {
    return [{ target_id: p.target_id, old: p.old, new: p.new, rationale: p.rationale as string | undefined }];
  }
  return [];
}

function fmt(v: unknown) {
  if (v == null) return "—";
  if (typeof v === "string") return v;
  return JSON.stringify(v, null, 2);
}
