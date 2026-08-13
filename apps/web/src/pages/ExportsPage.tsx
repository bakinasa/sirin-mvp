import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, PipelineStep } from "../lib/api";
import { PipelineStepper } from "../components/PipelineStepper";

type ExportJob = {
  id: string;
  export_type: string;
  status: string;
  result_content: unknown;
  error_message: string;
};

export function ExportsPage() {
  const { projectId } = useParams();
  const [steps, setSteps] = useState<PipelineStep[]>([]);
  const [job, setJob] = useState<ExportJob | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!projectId) return;
    api<PipelineStep[]>(`/projects/${projectId}/pipeline`).then(setSteps);
  }, [projectId]);

  async function run(export_type: string) {
    setBusy(true);
    try {
      const created = await api<ExportJob>(`/projects/${projectId}/exports`, {
        method: "POST",
        body: JSON.stringify({ export_type }),
      });
      const full = await api<ExportJob>(`/exports/${created.id}`);
      setJob(full);
    } finally {
      setBusy(false);
    }
  }

  if (!projectId) return null;

  return (
    <div>
      <PipelineStepper projectId={projectId} steps={steps} />
      <div className="mb-6">
        <h1 className="text-3xl font-semibold tracking-tight">Экспорт</h1>
        <p className="text-sm text-neutral-500">Markdown · JSON · text bundle. Содержимое: brief, карта профессии, сценарий.</p>
      </div>
      <div className="mb-4 flex flex-wrap gap-2">
        {["markdown", "json", "text_bundle"].map((t) => (
          <button key={t} className="btn-primary" disabled={busy} onClick={() => run(t)}>
            Export {t}
          </button>
        ))}
      </div>
      {job && (
        <div className="panel space-y-2">
          <p className="text-sm">
            {job.export_type} · {job.status}
            {job.error_message && ` · ${job.error_message}`}
          </p>
          <pre className="max-h-[560px] overflow-auto rounded-xl bg-ink-950 p-3 font-mono text-xs text-ink-100">
            {typeof job.result_content === "object"
              ? JSON.stringify(job.result_content, null, 2)
              : String(job.result_content)}
          </pre>
        </div>
      )}
    </div>
  );
}
