import { FormEvent, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api, PipelineStep } from "../lib/api";
import { PipelineStepper } from "../components/PipelineStepper";
import { useAuthStore } from "../store/auth";

type Expert = {
  id: string;
  name: string;
  role: string;
  contact: string;
  status: string;
};

type Feedback = {
  id: string;
  expert_id: string;
  content: string;
  structured_tags: string[];
  created_at: string;
};

export function ExpertsPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [steps, setSteps] = useState<PipelineStep[]>([]);
  const [experts, setExperts] = useState<Expert[]>([]);
  const [feedback, setFeedback] = useState<Feedback[]>([]);
  const [form, setForm] = useState({ name: "", role: "", contact: "" });
  const [fb, setFb] = useState<{
    expert_id: string;
    content: string;
    tags: string;
    attachments: { url: string; filename: string }[];
  }>({ expert_id: "", content: "", tags: "", attachments: [] });

  async function load() {
    if (!projectId) return;
    const [s, e, f] = await Promise.all([
      api<PipelineStep[]>(`/projects/${projectId}/pipeline`),
      api<Expert[]>(`/projects/${projectId}/experts`),
      api<Feedback[]>(`/projects/${projectId}/expert-feedback`),
    ]);
    setSteps(s);
    setExperts(e);
    setFeedback(f);
  }

  useEffect(() => {
    load().catch(console.error);
  }, [projectId]);

  async function addExpert(e: FormEvent) {
    e.preventDefault();
    await api(`/projects/${projectId}/experts`, {
      method: "POST",
      body: JSON.stringify(form),
    });
    setForm({ name: "", role: "", contact: "" });
    await load();
  }

  async function addFeedback(e: FormEvent) {
    e.preventDefault();
    await api(`/projects/${projectId}/expert-feedback`, {
      method: "POST",
      body: JSON.stringify({
        expert_id: fb.expert_id,
        content: fb.content,
        structured_tags: fb.tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
        attachments: fb.attachments,
      }),
    });
    setFb({ expert_id: "", content: "", tags: "", attachments: [] });
    await load();
  }

  async function approveStep() {
    await api(`/projects/${projectId}/experts/approve-step`, { method: "POST" });
    await queryClient.invalidateQueries({ queryKey: ["pipeline", projectId] });
    await load();
    navigate(`/projects/${projectId}/studio/expert_synthesis`);
  }

  if (!projectId) return null;

  return (
    <div>
      <PipelineStepper projectId={projectId} steps={steps} />
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Экспертный фидбек</h1>
          <p className="text-sm text-neutral-600 dark:text-neutral-300">
            Соберите замечания экспертов. Можно утвердить шаг и с пустым списком, если экспертов
            пока нет — тогда синтез будет опираться на brief и ТЗ.
          </p>
        </div>
        <button className="btn-primary" onClick={approveStep}>
          Утвердить и перейти к сведению
        </button>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <form onSubmit={addExpert} className="panel space-y-3">
          <h2 className="font-display text-xl">Добавить эксперта</h2>
          <input
            className="input"
            placeholder="Имя"
            required
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <input
            className="input"
            placeholder="Роль"
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value })}
          />
          <input
            className="input"
            placeholder="Контакт"
            value={form.contact}
            onChange={(e) => setForm({ ...form, contact: e.target.value })}
          />
          <button className="btn-primary" type="submit">
            Добавить
          </button>
          <ul className="space-y-2 pt-2">
            {experts.map((ex) => (
              <li key={ex.id} className="rounded-lg border border-ink-200/70 p-2 text-sm dark:border-ink-700">
                <strong>{ex.name}</strong> — {ex.role} · {ex.status}
              </li>
            ))}
          </ul>
        </form>

        <form onSubmit={addFeedback} className="panel space-y-3">
          <h2 className="font-display text-xl">Фидбек эксперта</h2>
          <select
            className="input"
            required
            value={fb.expert_id}
            onChange={(e) => setFb({ ...fb, expert_id: e.target.value })}
          >
            <option value="">Выберите эксперта</option>
            {experts.map((ex) => (
              <option key={ex.id} value={ex.id}>
                {ex.name}
              </option>
            ))}
          </select>
          <textarea
            className="input min-h-[140px]"
            required
            placeholder="Комментарии, интервью, заметки…"
            value={fb.content}
            onChange={(e) => setFb({ ...fb, content: e.target.value })}
          />
          <input
            className="input"
            placeholder="Теги через запятую"
            value={fb.tags}
            onChange={(e) => setFb({ ...fb, tags: e.target.value })}
          />
          <input
            className="input"
            type="file"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file || !projectId) return;
              const fd = new FormData();
              fd.append("file", file);
              const res = await fetch(`/api/projects/${projectId}/attachments`, {
                method: "POST",
                headers: {
                  Authorization: `Bearer ${useAuthStore.getState().token || ""}`,
                },
                body: fd,
              });
              if (!res.ok) {
                alert("Не удалось загрузить файл");
                return;
              }
              const data = await res.json();
              setFb((prev) => ({
                ...prev,
                attachments: [...prev.attachments, data],
              }));
            }}
          />
          <button className="btn-primary" type="submit">
            Сохранить фидбек
          </button>
          <ul className="max-h-64 space-y-2 overflow-auto pt-2">
            {feedback.map((f) => (
              <li key={f.id} className="rounded-lg border border-ink-200/70 p-2 text-sm dark:border-ink-700">
                <p className="text-xs text-ink-400">{new Date(f.created_at).toLocaleString("ru")}</p>
                <p>{f.content}</p>
              </li>
            ))}
          </ul>
        </form>
      </div>
    </div>
  );
}
