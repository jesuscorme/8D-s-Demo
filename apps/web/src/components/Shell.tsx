"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useState, type ReactNode } from "react";
import { api, errorText, useApi } from "@/lib/api";
import type { Me } from "@/lib/types";
import { ErrorBox, Field, Loading, Modal } from "./ui";

const SessionContext = createContext<Me | null>(null);

export function useMe(): Me {
  const me = useContext(SessionContext);
  if (!me) throw new Error("useMe fuera de la sesión");
  return me;
}

export function useCan(permission: string): boolean {
  return useMe().permissions.includes(permission);
}

const NAV: { href: string; label: string; icon: string; soon?: boolean; perm?: string }[] = [
  { href: "/", label: "Inicio", icon: "⌂" },
  { href: "/casos", label: "Casos 8D", icon: "▤" },
  { href: "/alertas", label: "Alertas", icon: "⚠" },
  { href: "/catalogo", label: "Catálogo de causas", icon: "⌗" },
  { href: "/lecciones", label: "Lecciones aprendidas", icon: "✎" },
  { href: "/reportes", label: "Reportes", icon: "▦" },
  { href: "/admin", label: "Administración", icon: "⚙", perm: "admin.users" },
];

function PasswordDialog({ onClose }: { onClose: () => void }) {
  const [f, setF] = useState({ current_password: "", new_password: "", confirm: "" });
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (f.new_password !== f.confirm) return setError("La confirmación no coincide.");
    try {
      await api("/auth/password", { body: { current_password: f.current_password, new_password: f.new_password } });
      setDone(true);
      setError(null);
    } catch (x) {
      setError(errorText(x));
    }
  }
  return (
    <Modal title="Cambiar contraseña" onClose={onClose}>
      {done ? <div className="stack"><div className="notice ok">Contraseña actualizada. Se cerraron tus otras sesiones.</div>
        <button className="btn primary" onClick={onClose}>Cerrar</button></div> : (
        <form className="stack" onSubmit={submit}>
          <Field label="Contraseña actual" required><input type="password" autoComplete="current-password" value={f.current_password} onChange={set("current_password")} required /></Field>
          <Field label="Nueva contraseña" required hint="Mínimo 10 caracteres."><input type="password" autoComplete="new-password" minLength={10} value={f.new_password} onChange={set("new_password")} required /></Field>
          <Field label="Confirmar nueva contraseña" required><input type="password" autoComplete="new-password" value={f.confirm} onChange={set("confirm")} required /></Field>
          <ErrorBox error={error} />
          <div className="row"><button type="button" className="btn" onClick={onClose}>Cancelar</button><button className="btn primary right">Guardar</button></div>
        </form>)}
    </Modal>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const { data: me, error, reload } = useApi<Me>("/auth/me");
  const path = usePathname();
  const router = useRouter();
  const [password, setPassword] = useState(false);

  async function logout() {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    router.replace("/login");
  }

  if (error) return <div className="content"><ErrorBox error={error} onRetry={reload} /></div>;
  if (!me) return <div className="content"><Loading rows={5} /></div>;
  const initials = me.user.display_name.split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();

  return (
    <SessionContext.Provider value={me}>
      <div className="shell">
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-mark">8D</div>
            <div><b>8D PRO</b><small>Gestión de problemas</small></div>
          </div>
          <nav className="nav">
            {NAV.filter((n) => !n.perm || me.permissions.includes(n.perm)).map((n) => {
              const active = n.href === "/" ? path === "/" : path.startsWith(n.href);
              return (
                <Link key={n.href} href={n.href} className={active ? "active" : ""}>
                  <span aria-hidden>{n.icon}</span>{n.label}{n.soon && <span className="soon">Próx.</span>}
                </Link>
              );
            })}
          </nav>
          <div className="sidebar-foot">v1.0 · MVP D0–D8</div>
        </aside>
        <div className="main">
          <header className="topbar">
            <span className="org">{me.organization.name}</span>
            <div className="who">
              <div style={{ textAlign: "right" }}>
                <div style={{ fontWeight: 600 }}>{me.user.display_name}</div>
                <div className="small muted">{me.role_names.join(", ")}</div>
              </div>
              <div className="avatar">{initials}</div>
              <button className="btn sm ghost" onClick={() => setPassword(true)}>Contraseña</button>
              <button className="btn sm" onClick={logout}>Salir</button>
            </div>
          </header>
          <main className="content">{children}</main>
          {password && <PasswordDialog onClose={() => setPassword(false)} />}
        </div>
      </div>
    </SessionContext.Provider>
  );
}
