import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, Artifact, PipelineStep } from "../lib/api";
import { PipelineStepper } from "../components/PipelineStepper";
import { PromptPanel } from "../components/PromptPanel";
import { ModelSelector } from "../components/ModelSelector";
import { ArtifactEditor } from "../components/ArtifactEditor";

type Frame = {
  id?: string;
  scene_id?: string;
  order?: number;
  description?: string;
  narration?: string;
  interaction?: string | null;
  comment?: string;
};

export function StoryboardPage() {
  const { projectId } = useParams();
  const [steps, setSteps] = useState<PipelineStep[]>([]);
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [operatorPrompt, setOperatorPrompt] = useState("");
  const [primaryId, setPrimaryId] = useState("");
  const [fallbackId, setFallbackId] = useState("");
  const [frames, setFrames] = useState<Frame[]>([]);
  const [busy, setBusy] = useState(false);

  async function load() {
    if (!projectId) return;
    const [s, arts] = await Promise.all([
      api<PipelineStep[]>(`/projects/${projectId}/pipeline`),
      api<Artifact[]>(`/projects/${projectId}/artifacts?step_type=storyboard`),
    ]);
    setSteps(s);
    const art = arts[0] || null;
    setArtifact(art);
    const content = art?.content as { frames?: Frame[] } | undefined;
    setFrames(content?.frames || []);
  }

  useEffect(() => {
    load().catch(console.error);
  }, [projectId]);

  async function run() {
    setBusy(true);
    try {
      await api(`/projects/${projectId}/pipeline/run`, {
        method: "POST",
        body: JSON.stringify({
          step_type: "storyboard",
          operator_prompt: operatorPrompt,
          primary_model_id: primaryId || null,
          fallback_model_id: fallbackId || null,
        }),
      });
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function saveFrames() {
    if (!artifact) return;
    await api(`/artifacts/${artifact.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        content: { ...(artifact.content as object), frames },
        comment: "storyboard frame edits",
      }),
    });
    await load();
  }

  if (!projectId) return null;

  return (
    <div>
      <PipelineStepper projectId={projectId} steps={steps} />
      <div className="mb-6 flex items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl">Storyboard Workspace</h1>
          <p className="text-sm text-ink-500">Редактирование кадров и комментариев</p>
        </div>
        <div className="flex gap-2">
          <button className="btn-ghost" onClick={saveFrames} disabled={!artifact}>
            Сохранить кадры
          </button>
          <button className="btn-primary" disabled={busy} onClick={run}>
            Сгенерировать
          </button>
        </div>
      </div>

      <div className="mb-4 grid gap-4 xl:grid-cols-2">
        <PromptPanel
          projectId={projectId}
          stepType="storyboard"
          value={operatorPrompt}
          onChange={setOperatorPrompt}
        />
        <ModelSelector
          stepType="storyboard"
          primaryId={primaryId}
          fallbackId={fallbackId}
          onPrimary={setPrimaryId}
          onFallback={setFallbackId}
        />
      </div>

      <div className="mb-6 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {frames.map((f, i) => (
          <div key={f.id || i} className="panel space-y-2">
            <p className="label">Кадр {f.order ?? i + 1}</p>
            <textarea
              className="input min-h-[80px]"
              value={f.description || ""}
              onChange={(e) => {
                const next = [...frames];
                next[i] = { ...f, description: e.target.value };
                setFrames(next);
              }}
            />
            <input
              className="input"
              placeholder="Закадр"
              value={f.narration || ""}
              onChange={(e) => {
                const next = [...frames];
                next[i] = { ...f, narration: e.target.value };
                setFrames(next);
              }}
            />
            <input
              className="input"
              placeholder="Комментарий"
              value={f.comment || ""}
              onChange={(e) => {
                const next = [...frames];
                next[i] = { ...f, comment: e.target.value };
                setFrames(next);
              }}
            />
          </div>
        ))}
        {frames.length === 0 && (
          <div className="panel text-sm text-ink-500">Нет кадров — сгенерируйте storyboard.</div>
        )}
      </div>

      <ArtifactEditor artifact={artifact} onUpdated={load} />
    </div>
  );
}
