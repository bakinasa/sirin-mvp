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

function downloadDocx(content: unknown, fallbackFilename: string) {
  const c = content as Record<string, string> | null;
  if (!c?.docx_base64) return;
  const binary = atob(c.docx_base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  const blob = new Blob([bytes], {
    type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = c.filename || fallbackFilename;
  a.click();
  URL.revokeObjectURL(url);
}

export function ExportsPage() {
  const { projectId } = useParams();
  const [steps, setSteps] = useState<PipelineStep[]>([]);
  const [job, setJob] = useState<ExportJob | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!projectId) return;
    api<PipelineStep[]>(`/projects/${projectId}/pipeline`).then(setSteps);
  }, [projectId]);

  async function runDocx() {
    setBusy(true);
    try {
      const created = await api<ExportJob>(`/projects/${projectId}/exports`, {
        method: "POST",
        body: JSON.stringify({ export_type: "docx_scenario" }),
      });
      const full = await api<ExportJob>(`/exports/${created.id}`);
      setJob(full);
      if (full.status === "ready") {
        downloadDocx(full.result_content, "scenario.docx");
      }
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
        <p className="text-sm text-neutral-500">Сценарий в формате Word (.docx).</p>
      </div>

      <div className="mb-6 flex gap-3">
        <button className="btn-primary" disabled={busy} onClick={runDocx}>
          {busy ? "Генерация…" : "Скачать сценарий DOCX"}
        </button>
        {job?.status === "ready" && (
          <button className="btn-ghost" onClick={() => downloadDocx(job.result_content, "scenario.docx")}>
            Скачать снова
          </button>
        )}
      </div>

      {job?.status === "failed" && (
        <div className="panel text-sm text-red-600">Ошибка: {job.error_message}</div>
      )}
    </div>
  );
}
