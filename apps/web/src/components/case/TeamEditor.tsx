"use client";

import { useEffect, useState } from "react";
import { api, errorText, useApi } from "@/lib/api";
import { TEAM_ROLE } from "@/lib/labels";
import type { Case, User } from "@/lib/types";
import { ErrorBox, Field } from "@/components/ui";

type Member = { user_id: string; team_role: string };

export function TeamEditor({ c, editable, onSaved }: { c: Case; editable: boolean; onSaved: (c: Case) => void }) {
  const users = useApi<User[]>("/users");
  const [owner, setOwner] = useState(c.owner_user_id ?? "");
  const [members, setMembers] = useState<Member[]>(c.team.map((t) => ({ user_id: t.user_id, team_role: t.team_role })));
  const [adding, setAdding] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setOwner(c.owner_user_id ?? "");
    setMembers(c.team.map((t) => ({ user_id: t.user_id, team_role: t.team_role })));
  }, [c.version, c.updated_at, c.owner_user_id, c.team]);

  const name = (id: string) => users.data?.find((u) => u.id === id)?.display_name ?? c.team.find((t) => t.user_id === id)?.display_name ?? id;
  const available = users.data?.filter((u) => !members.some((m) => m.user_id === u.id)) ?? [];

  async function save() {
    setBusy(true);
    setError(null);
    try {
      let result = c;
      if (owner && owner !== c.owner_user_id) {
        result = await api<Case>(`/cases/${c.id}`, { method: "PATCH", body: { owner_user_id: owner, version: c.version } });
      }
      result = await api<Case>(`/cases/${c.id}/team`, { method: "PUT", body: { members } });
      onSaved(result);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  function setRole(id: string, role: string) {
    setMembers(members.map((m) => (m.user_id === id ? { ...m, team_role: role }
      : role === "leader" && m.team_role === "leader" ? { ...m, team_role: "member" } : m)));
  }

  return (
    <div className="stack">
      <ErrorBox error={users.error} />
      <Field label="Responsable del caso" required>
        <select value={owner} onChange={(e) => setOwner(e.target.value)} disabled={!editable}>
          <option value="">Seleccionar…</option>
          {users.data?.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
        </select>
      </Field>
      <div className="card">
        <div className="table-wrap"><table>
          <thead><tr><th>Integrante</th><th>Rol en el equipo</th><th></th></tr></thead>
          <tbody>
            {members.length === 0 && <tr><td colSpan={3} className="muted">Sin integrantes.</td></tr>}
            {members.map((m) => (
              <tr key={m.user_id}>
                <td>{name(m.user_id)}{m.user_id === owner && <span className="badge blue" style={{ marginLeft: 6 }}>Responsable</span>}</td>
                <td style={{ width: 200 }}>
                  <select value={m.team_role} onChange={(e) => setRole(m.user_id, e.target.value)} disabled={!editable}>
                    {Object.entries(TEAM_ROLE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </td>
                <td style={{ width: 90 }}>{editable && <button className="btn sm danger" onClick={() => setMembers(members.filter((x) => x.user_id !== m.user_id))}>Quitar</button>}</td>
              </tr>))}
          </tbody>
        </table></div>
      </div>
      {editable && (
        <div className="row">
          <select value={adding} onChange={(e) => setAdding(e.target.value)} style={{ maxWidth: 280 }} aria-label="Agregar integrante">
            <option value="">Agregar integrante…</option>
            {available.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}
          </select>
          <button className="btn" disabled={!adding} onClick={() => { setMembers([...members, { user_id: adding, team_role: "member" }]); setAdding(""); }}>Agregar</button>
          <button className="btn primary right" onClick={save} disabled={busy}>{busy ? "Guardando…" : "Guardar equipo"}</button>
        </div>
      )}
      <ErrorBox error={error} />
    </div>
  );
}
