"use client";

import { useState } from "react";
import { api, errorText, useApi } from "@/lib/api";
import { fmtDate } from "@/lib/labels";
import type { Plant } from "@/lib/types";
import { Badge, ErrorBox, Field, Loading, Modal, NotAvailable } from "@/components/ui";
import { useCan, useMe } from "@/components/Shell";
import { NotificationsAdmin } from "@/components/NotificationsAdmin";

type AdminUser = { id: string; email: string; display_name: string; is_active: boolean; created_at: string; roles: string[]; plant_ids: string[] };
const ROLES: Record<string, string> = { admin: "Administrador", quality_manager: "Gerente de calidad", engineer: "Ingeniero de calidad", viewer: "Consulta" };

function PlantPicker({ plants, value, onChange }: { plants: Plant[]; value: string[]; onChange: (v: string[]) => void }) {
  return (
    <div className="stack" style={{ gap: 4 }}>
      <label className="row small" style={{ gap: 6 }}><input type="checkbox" style={{ width: "auto" }} checked={!value.length} onChange={() => onChange([])} />Todas las plantas</label>
      {plants.map((p) => (
        <label key={p.id} className="row small" style={{ gap: 6 }}>
          <input type="checkbox" style={{ width: "auto" }} checked={value.includes(p.id)}
            onChange={(e) => onChange(e.target.checked ? [...value, p.id] : value.filter((x) => x !== p.id))} />{p.code} — {p.name}
        </label>))}
    </div>
  );
}

function UserForm({ plants, onClose, onSaved }: { plants: Plant[]; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({ email: "", display_name: "", password: "", role: "engineer" });
  const [plantIds, setPlantIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api("/admin/users", { body: { email: f.email, display_name: f.display_name, password: f.password, roles: [f.role], plant_ids: plantIds } });
      onSaved();
      onClose();
    } catch (err) {
      setError(errorText(err));
    }
  }
  return (
    <Modal title="Nuevo usuario" onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <Field label="Nombre" required><input value={f.display_name} onChange={set("display_name")} required /></Field>
        <Field label="Correo" required><input type="email" value={f.email} onChange={set("email")} required /></Field>
        <Field label="Contraseña inicial" required hint="Mínimo 10 caracteres. Pide al usuario cambiarla al entrar."><input type="password" value={f.password} onChange={set("password")} minLength={10} required autoComplete="new-password" /></Field>
        <Field label="Rol" required><select value={f.role} onChange={set("role")}>{Object.entries(ROLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
        <Field label="Plantas visibles"><PlantPicker plants={plants} value={plantIds} onChange={setPlantIds} /></Field>
        <ErrorBox error={error} />
        <div className="row"><button type="button" className="btn" onClick={onClose}>Cancelar</button><button className="btn primary right">Crear</button></div>
      </form>
    </Modal>
  );
}

function EditUser({ u, plants, onClose, onSaved }: { u: AdminUser; plants: Plant[]; onClose: () => void; onSaved: () => void }) {
  const [plantIds, setPlantIds] = useState<string[]>(u.plant_ids);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api(`/admin/users/${u.id}`, { method: "PATCH", body: { plant_ids: plantIds, ...(password ? { password } : {}) } });
      onSaved();
      onClose();
    } catch (err) {
      setError(errorText(err));
    }
  }
  return (
    <Modal title={u.display_name} onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <Field label="Plantas visibles"><PlantPicker plants={plants} value={plantIds} onChange={setPlantIds} /></Field>
        <Field label="Restablecer contraseña" hint="Opcional. Cierra todas sus sesiones."><input type="password" minLength={10} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" /></Field>
        <ErrorBox error={error} />
        <div className="row"><button type="button" className="btn" onClick={onClose}>Cancelar</button><button className="btn primary right">Guardar</button></div>
      </form>
    </Modal>
  );
}

function PlantForm({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({ code: "", name: "", timezone: "America/Mexico_City" });
  const [error, setError] = useState<string | null>(null);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: k === "code" ? e.target.value.toUpperCase() : e.target.value });
  return (
    <Modal title="Nueva planta" onClose={onClose}>
      <form className="stack" onSubmit={async (e) => {
        e.preventDefault();
        try { await api("/admin/plants", { body: f }); onSaved(); onClose(); } catch (x) { setError(errorText(x)); }
      }}>
        <div className="grid g2">
          <Field label="Código" required hint="2–20: letras, números, - o _"><input value={f.code} onChange={set("code")} pattern="[A-Z0-9_\-]{2,20}" required /></Field>
          <Field label="Nombre" required><input value={f.name} onChange={set("name")} required /></Field>
        </div>
        <Field label="Zona horaria" hint="Formato IANA; se usa en la fecha de emisión de documentos."><input value={f.timezone} onChange={set("timezone")} required /></Field>
        <ErrorBox error={error} />
        <div className="row"><button type="button" className="btn" onClick={onClose}>Cancelar</button><button className="btn primary right">Crear</button></div>
      </form>
    </Modal>
  );
}

function Logo() {
  const [version, setVersion] = useState(0);
  const [missing, setMissing] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  async function upload(file: File) {
    const form = new FormData();
    form.append("file", file);
    try {
      await api("/admin/organization/logo", { form });
      setMissing(false);
      setVersion(version + 1);
      setMsg({ ok: true, text: "Logo actualizado; aparecerá en los próximos documentos emitidos." });
    } catch (e) {
      setMsg({ ok: false, text: errorText(e) });
    }
  }
  return (
    <div className="card">
      <div className="card-head"><h2>Logo de la organización</h2><span className="small muted">PNG o JPEG, máx. 1 MB. Se usa en el encabezado de los PDF.</span></div>
      <div className="card-pad row">
        <div style={{ width: 120, height: 80, border: "1px dashed var(--line)", borderRadius: 8, display: "grid", placeItems: "center", background: "#fafbfd" }}>
          {missing ? <span className="small muted">Sin logo</span> : <img key={version} src={`/api/organization/logo?v=${version}`} alt="Logo" style={{ maxWidth: 110, maxHeight: 70 }} onError={() => setMissing(true)} />}
        </div>
        <label className="btn sm">Subir logo<input type="file" accept="image/png,image/jpeg" hidden onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void upload(f); }} /></label>
        {msg && <div className={`notice ${msg.ok ? "ok" : "error"}`}>{msg.text}</div>}
      </div>
    </div>
  );
}

export default function AdminPage() {
  const me = useMe();
  const allowed = useCan("admin.users");
  const users = useApi<AdminUser[]>(allowed ? "/admin/users" : null);
  const plants = useApi<Plant[]>("/plants");
  const [modal, setModal] = useState<"user" | "plant" | AdminUser | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!allowed) return <NotAvailable title="Administración" phase="Acceso restringido" description="Esta sección requiere el rol de administrador." />;

  async function update(u: AdminUser, body: Record<string, unknown>) {
    try {
      await api(`/admin/users/${u.id}`, { method: "PATCH", body });
      void users.reload();
      setError(null);
    } catch (e) {
      setError(errorText(e));
    }
  }
  const plantCodes = (ids: string[]) => ids.length ? ids.map((id) => plants.data?.find((p) => p.id === id)?.code ?? "?").join(", ") : "Todas";

  return (
    <>
      <div className="page-head">
        <div><h1>Administración</h1><div className="sub">{me.organization.name}</div></div>
        <div className="actions"><button className="btn" onClick={() => setModal("plant")}>+ Planta</button><button className="btn primary" onClick={() => setModal("user")}>+ Nuevo usuario</button></div>
      </div>
      <div className="stack" style={{ gap: 16 }}>
        <div className="card">
          <div className="card-head"><h2>Usuarios y roles</h2><span className="small muted">Cambiar rol o plantas cierra las sesiones del usuario.</span></div>
          <ErrorBox error={users.error ?? error} onRetry={users.reload} />
          {users.loading && !users.data ? <div className="card-pad"><Loading /></div> : (
            <div className="table-wrap"><table>
              <thead><tr><th>Nombre</th><th>Correo</th><th>Rol</th><th>Plantas</th><th>Estado</th><th>Alta</th><th></th></tr></thead>
              <tbody>{users.data?.map((u) => (
                <tr key={u.id}>
                  <td>{u.display_name}</td><td>{u.email}</td>
                  <td style={{ width: 200 }}>
                    <select value={u.roles[0] ?? ""} onChange={(e) => update(u, { roles: [e.target.value] })} disabled={u.id === me.user.id} aria-label="Rol">
                      {Object.entries(ROLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                    </select>
                  </td>
                  <td className="small">{plantCodes(u.plant_ids)}</td>
                  <td>{u.is_active ? <Badge tone="green">Activo</Badge> : <Badge tone="red">Inactivo</Badge>}</td>
                  <td className="small">{fmtDate(u.created_at)}</td>
                  <td>{u.id !== me.user.id && <div className="row" style={{ gap: 4 }}>
                    <button className="btn sm" onClick={() => setModal(u)}>Plantas / contraseña</button>
                    <button className="btn sm" onClick={() => update(u, { is_active: !u.is_active })}>{u.is_active ? "Desactivar" : "Activar"}</button></div>}</td>
                </tr>))}</tbody>
            </table></div>
          )}
        </div>
        <div className="card">
          <div className="card-head"><h2>Plantas</h2></div>
          <div className="table-wrap"><table>
            <thead><tr><th>Código</th><th>Nombre</th></tr></thead>
            <tbody>{plants.data?.map((p) => <tr key={p.id}><td className="mono">{p.code}</td><td>{p.name}</td></tr>)}</tbody>
          </table></div>
        </div>
        <NotificationsAdmin plants={plants.data ?? []} />
        <Logo />
      </div>
      {modal === "user" && <UserForm plants={plants.data ?? []} onClose={() => setModal(null)} onSaved={users.reload} />}
      {modal === "plant" && <PlantForm onClose={() => setModal(null)} onSaved={plants.reload} />}
      {modal && typeof modal === "object" && <EditUser u={modal} plants={plants.data ?? []} onClose={() => setModal(null)} onSaved={users.reload} />}
    </>
  );
}
