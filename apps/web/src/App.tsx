import { Navigate, Route, Routes, useParams } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { StepGuard } from "./components/StepGuard";
import { useAuthStore } from "./store/auth";
import { LoginPage } from "./pages/LoginPage";
import { DashboardPage } from "./pages/DashboardPage";
import { ProjectOverviewPage } from "./pages/ProjectOverviewPage";
import { BriefEditorPage } from "./pages/BriefEditorPage";
import { PipelineStudioPage } from "./pages/PipelineStudioPage";
import { ExpertsPage } from "./pages/ExpertsPage";
import { ScenesPage } from "./pages/ScenesPage";
import { StoryboardPage } from "./pages/StoryboardPage";
import { ModelsPage } from "./pages/ModelsPage";
import { PromptsPage } from "./pages/PromptsPage";
import { ExportsPage } from "./pages/ExportsPage";
import { FuturePage } from "./pages/FuturePage";
import { ProfessionMapPage } from "./pages/ProfessionMapPage";
import { ScenarioPage } from "./pages/ScenarioPage";
import { useEffect } from "react";

function Protected({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  if (!token) return <Navigate to="/login" replace />;
  return <AppShell>{children}</AppShell>;
}

function GuardedStudio() {
  const { stepType = "draft_tz" } = useParams();
  return (
    <StepGuard stepType={stepType}>
      <PipelineStudioPage />
    </StepGuard>
  );
}

export default function App() {
  const dark = useAuthStore((s) => s.dark);
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<Protected><DashboardPage /></Protected>} />
      <Route path="/models" element={<Protected><ModelsPage /></Protected>} />
      <Route path="/prompts" element={<Protected><PromptsPage /></Protected>} />
      <Route path="/future" element={<Protected><FuturePage /></Protected>} />
      <Route path="/projects/:projectId/overview" element={<Protected><ProjectOverviewPage /></Protected>} />
      <Route
        path="/projects/:projectId/brief"
        element={
          <Protected>
            <StepGuard stepType="brief">
              <BriefEditorPage />
            </StepGuard>
          </Protected>
        }
      />
      <Route
        path="/projects/:projectId/profession-map"
        element={
          <Protected>
            <StepGuard stepType="profession_map">
              <ProfessionMapPage />
            </StepGuard>
          </Protected>
        }
      />
      <Route
        path="/projects/:projectId/scenario"
        element={
          <Protected>
            <StepGuard stepType="scenario_plan">
              <ScenarioPage />
            </StepGuard>
          </Protected>
        }
      />
      <Route
        path="/projects/:projectId/experts"
        element={
          <Protected>
            <StepGuard stepType="expert_feedback">
              <ExpertsPage />
            </StepGuard>
          </Protected>
        }
      />
      <Route
        path="/projects/:projectId/scenes"
        element={
          <Protected>
            <StepGuard stepType="scene_breakdown">
              <ScenesPage />
            </StepGuard>
          </Protected>
        }
      />
      <Route
        path="/projects/:projectId/storyboard"
        element={
          <Protected>
            <StepGuard stepType="storyboard">
              <StoryboardPage />
            </StepGuard>
          </Protected>
        }
      />
      <Route
        path="/projects/:projectId/exports"
        element={
          <Protected>
            <StepGuard stepType="export">
              <ExportsPage />
            </StepGuard>
          </Protected>
        }
      />
      <Route
        path="/projects/:projectId/studio/:stepType"
        element={
          <Protected>
            <GuardedStudio />
          </Protected>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
