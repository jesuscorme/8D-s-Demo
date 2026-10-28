"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api, errorText } from "@/lib/api";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/auth/login", { body: { email, password } });
      const next = params.get("next");
      router.replace(next && next.startsWith("/") && !next.startsWith("//") ? next : "/");
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="stack">
      <div><h1>Iniciar sesión</h1><p className="muted">Usa tu cuenta de 8D PRO.</p></div>
      {error && <div className="notice error" role="alert">{error}</div>}
      <label className="field">Correo<input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
      <label className="field">Contraseña<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
      <button className="btn primary" disabled={busy} style={{ justifyContent: "center" }}>{busy ? "Entrando…" : "Entrar"}</button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <div className="login-wrap">
      <div className="login-side">
        <div className="brand"><div className="brand-mark">8D</div><div><b>8D PRO</b><small>Gestión de problemas</small></div></div>
        <div>
          <h1>Del problema a la causa raíz, con evidencia.</h1>
          <p>Flujo D0–D8 guiado, contención con alerta de calidad versionada e investigación de causas trazable.</p>
        </div>
        <small style={{ color: "#7f93b2" }}>Las sugerencias del sistema son hipótesis; las decisiones requieren evidencia.</small>
      </div>
      <div className="login-form"><Suspense><LoginForm /></Suspense></div>
    </div>
  );
}
