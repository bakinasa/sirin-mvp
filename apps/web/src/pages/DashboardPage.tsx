import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, Project } from "../lib/api";
import { Modal } from "../components/Modal";

const FIELDS: {
  key: keyof typeof EMPTY_FORM;
  label: string;
  hint: string;
  placeholder: string;
  required?: boolean;
}[] = [
  {
    key: "title",
    label: "Название проекта",
    hint: "Как модуль будет называться внутри команды. Обязательное поле.",
    placeholder: "Например: Допуск к работе на высоте",
    required: true,
  },
  {
    key: "client_name",
    label: "Заказчик",
    hint: "Можно заполнить позже в Brief.",
    placeholder: "Например: Евраз / внутренний пилот",
  },
  {
    key: "profession",
    label: "Профессия",
    hint: "Кто проходит обучение. Остальное — на шаге Brief и в файлах.",
    placeholder: "Например: электромонтёр",
  },
];

const EMPTY_FORM = {
  title: "",
  client_name: "",
  profession: "",
  audience: "",
  delivery_format: "",
  expected_duration: "",
  constraints: "",
  source_materials: "",
};

export function DashboardPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  async function load() {
    setProjects(await api<Project[]>("/projects"));
  }

  useEffect(() => {
    load().catch(console.error);
  }, []);

  async function create(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const p = await api<Project>("/projects", {
        method: "POST",
        body: JSON.stringify(form),
      });
      setOpen(false);
      setForm(EMPTY_FORM);
      // Сразу на первый шаг пайплайна — Brief
      navigate(`/projects/${p.id}/brief`);
    } catch (err) {
      alert(String(err));
    } finally {
      setBusy(false);
    }
  }

  async function removeProject(id: string, title: string) {
    if (!confirm(`Удалить проект «${title}»? Он исчезнет из списка.`)) return;
    await api(`/projects/${id}`, { method: "DELETE" });
    await load();
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Проекты</h1>
          <p className="mt-1 max-w-xl text-neutral-600 dark:text-neutral-300">
            Создание 360°-тренажёров по шагам. На каждом этапе — проверка человеком.
          </p>
        </div>
        <button className="btn-primary" onClick={() => setOpen(true)}>
          Новый проект
        </button>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {projects.map((p) => (
          <div key={p.id} className="panel relative space-y-3">
            <Link to={`/projects/${p.id}/brief`} className="block space-y-1">
              <h2 className="text-lg font-semibold">{p.title}</h2>
              <p className="text-sm text-neutral-500">
                {p.client_name || "Без заказчика"}
                {p.profession ? ` · ${p.profession}` : ""}
              </p>
              {p.delivery_format && (
                <p className="text-xs text-neutral-400">{p.delivery_format}</p>
              )}
            </Link>
            <div className="flex gap-2">
              <Link className="btn-ghost flex-1 text-center" to={`/projects/${p.id}/brief`}>
                Открыть
              </Link>
              <button
                type="button"
                className="btn-danger"
                onClick={() => removeProject(p.id, p.title)}
              >
                Удалить
              </button>
            </div>
          </div>
        ))}
        {projects.length === 0 && (
          <div className="panel text-sm text-neutral-500">
            Пока нет проектов — создайте первый.
          </div>
        )}
      </div>

      {open && (
        <Modal title="Новый проект тренажёра" onClose={() => setOpen(false)} wide>
          <p className="mb-4 text-sm text-neutral-600 dark:text-neutral-300">
            Обязательно только название. Контекст и файлы добавляются на шаге Brief.
          </p>
          <form onSubmit={create} className="space-y-4">
            <div className="space-y-4 max-h-[60vh] overflow-y-auto pr-1">
              {FIELDS.map((f) => (
                <div key={f.key}>
                  <label className="label">
                    {f.label}
                    {f.required ? " *" : " (необязательно)"}
                  </label>
                  <p className="mb-1.5 text-xs leading-relaxed text-neutral-500">{f.hint}</p>
                  <input
                    className="input"
                    required={!!f.required}
                    placeholder={f.placeholder}
                    value={form[f.key]}
                    onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                  />
                </div>
              ))}
            </div>
            <div className="flex justify-end gap-2 border-t border-neutral-200 pt-4 dark:border-neutral-700">
              <button type="button" className="btn-ghost" onClick={() => setOpen(false)}>
                Отмена
              </button>
              <button type="submit" className="btn-primary" disabled={busy}>
                {busy ? "Создаём…" : "Создать и перейти к Brief"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
