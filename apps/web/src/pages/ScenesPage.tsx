import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, Artifact, PipelineStep } from "../lib/api";
import { PipelineStepper } from "../components/PipelineStepper";
import { ArtifactEditor } from "../components/ArtifactEditor";
import { PromptPanel } from "../components/PromptPanel";
import { ModelSelector } from "../components/ModelSelector";

type Scene = {
  id?: string;
  goal?: string;
  attention_point?: string;
  risk_360?: string;
  timing_sec?: number;
  production_hint?: string;
  shots?: { id?: string; description?: string }[];
};

export function ScenesPage() {
  const { projectId } = useParams();
  const [steps, setSteps] = useState<PipelineStep[]>([]);
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [operatorPrompt, setOperatorPrompt] = useState("");
  const [primaryId, setPrimaryId] = useState("");
  const [fallbackId, setFallbackId] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    if (!projectId) return;
    const [s, arts] = await Promise.all([
      api<PipelineStep[]>(`/projects/${projectId}/pipeline`),
      api<Artifact[]>(`/projects/${projectId}/artifacts?step_type=scene_breakdown`),
    ]);
    setSteps(s);
    setArtifact(arts[0] || null);
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
          step_type: "scene_breakdown",
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

  const scenes: Scene[] = extractScenes(artifact?.content);

  if (!projectId) return null;

  return (
    <div>
      <PipelineStepper projectId={projectId} steps={steps} />
      <div className="mb-6 flex items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl">Scene / Shot Planner</h1>
          <p className="text-sm text-ink-500">Шаги → сцены → кадры · риски 360°</p>
        </div>
        <button className="btn-primary" disabled={busy} onClick={run}>
          Сгенерировать разбиение
        </button>
      </div>

      <div className="mb-4 grid gap-4 xl:grid-cols-2">
        <PromptPanel
          projectId={projectId}
          stepType="scene_breakdown"
          value={operatorPrompt}
          onChange={setOperatorPrompt}
        />
        <ModelSelector
          stepType="scene_breakdown"
          primaryId={primaryId}
          fallbackId={fallbackId}
          onPrimary={setPrimaryId}
          onFallback={setFallbackId}
        />
      </div>

      <div className="mb-6 grid gap-3 md:grid-cols-2">
        {scenes.map((sc, i) => (
          <div key={sc.id || i} className="panel space-y-2">
            <h3 className="font-display text-lg">{sc.goal || `Сцена ${i + 1}`}</h3>
            <p className="text-sm">
              <span className="text-ink-500">Внимание:</span> {sc.attention_point || "—"}
            </p>
            <p className="text-sm">
              <span className="text-ink-500">Риск 360°:</span> {sc.risk_360 || "—"}
            </p>
            <p className="text-sm">
              <span className="text-ink-500">Тайминг:</span> {sc.timing_sec ?? "—"} сек ·{" "}
              {sc.production_hint || "—"}
            </p>
            <ul className="list-disc pl-5 text-sm">
              {(sc.shots || []).map((sh, j) => (
                <li key={sh.id || j}>{sh.description}</li>
              ))}
            </ul>
          </div>
        ))}
        {scenes.length === 0 && (
          <div className="panel text-sm text-ink-500">Пока нет сцен — запустите генерацию.</div>
        )}
      </div>

      <ArtifactEditor artifact={artifact} onUpdated={load} />
    </div>
  );
}

function extractScenes(content: unknown): Scene[] {
  if (!content || typeof content !== "object") return [];
  const c = content as { steps?: { scenes?: Scene[] }[]; scenes?: Scene[] };
  if (Array.isArray(c.scenes)) return c.scenes;
  if (Array.isArray(c.steps)) {
    return c.steps.flatMap((s) => s.scenes || []);
  }
  return [];
}
