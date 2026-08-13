import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useAuthStore } from "../store/auth";

export function LoginPage() {
  const [email, setEmail] = useState("admin@aistudio.local");
  const [password, setPassword] = useState("admin123");
  const [error, setError] = useState("");
  const setToken = useAuthStore((s) => s.setToken);
  const navigate = useNavigate();

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const res = await api<{ access_token: string }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setToken(res.access_token);
      navigate("/");
    } catch (err) {
      setError(String(err));
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-neutral-50 px-4 dark:bg-neutral-950">
      <form onSubmit={onSubmit} className="panel w-full max-w-md space-y-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-neutral-500">
            Сирин
          </p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">AI Studio 360</h1>
          <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-300">
            Студия для создания 360°-тренажёров с проверкой человеком на каждом шаге
          </p>
        </div>
        <div>
          <label className="label">Email</label>
          <input className="input" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div>
          <label className="label">Пароль</label>
          <input
            className="input"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button className="btn-primary w-full" type="submit">
          Войти
        </button>
      </form>
    </div>
  );
}
