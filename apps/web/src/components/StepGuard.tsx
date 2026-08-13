import { useEffect } from "react";
import { Navigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, PipelineStep } from "../lib/api";
import { isStepAccessible, stepPath, getCurrentStepIndex } from "../lib/pipelineAccess";

/** Blocks direct URL access to future pipeline steps. */
export function StepGuard({
  stepType,
  children,
}: {
  stepType: string;
  children: React.ReactNode;
}) {
  const { projectId } = useParams();
  const { data: steps, isLoading } = useQuery({
    queryKey: ["pipeline", projectId],
    enabled: !!projectId,
    queryFn: () => api<PipelineStep[]>(`/projects/${projectId}/pipeline`),
    staleTime: 0,
    refetchOnMount: "always",
  });

  if (!projectId) return null;
  if (isLoading || !steps) {
    return <div className="panel text-sm text-neutral-500">Проверяем доступ к шагу…</div>;
  }

  if (!isStepAccessible(steps, stepType)) {
    const sorted = [...steps].sort((a, b) => a.order_index - b.order_index);
    const current = sorted[getCurrentStepIndex(steps)];
    return <Navigate to={stepPath(projectId, current.step_type)} replace />;
  }

  return <>{children}</>;
}

/** Helper hook-free wrapper that syncs query cache after mutations if needed. */
export function useRefreshPipeline(projectId: string | undefined, steps: PipelineStep[]) {
  useEffect(() => {
    // placeholder for future cache sync
  }, [projectId, steps]);
}
