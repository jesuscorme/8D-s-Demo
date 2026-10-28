"use client";

import { useEffect, useState } from "react";
import { api, errorText } from "@/lib/api";
import type { Case } from "@/lib/types";
import { ErrorBox, Field } from "@/components/ui";

export type FieldSpec = {
  key: string;
  label: string;
  target: "case" | "content";
  kind?: "text" | "textarea" | "select" | "date" | "number";
  options?: Record<string, string>;
  required?: boolean;
  hint?: string;
  wide?: boolean;
};

type Value = string;

function initial(c: Case, code: string, fields: FieldSpec[]): Record<string, Value> {
  const content = c.workflow.find((d) => d.code === code)?.content ?? {};
  const out: Record<string, Value> = {};
  for (const f of fields) {
    const raw = f.target === "case" ? (c as unknown as Record<string, unknown>)[f.key] : content[f.key];
    out[f.key] = raw === null || raw === undefined ? "" : String(raw);
  }
  return out;
}

/** Formulario de una disciplina: guarda campos del caso (PATCH /cases) y del contenido (PATCH disciplina). */
export function DisciplineForm({ c, code, fields, editable, onSaved }: {
  c: Case; code: string; fields: FieldSpec[]; editable: boolean; onSaved: (c: Case) => void;
}) {
  const [values, setValues] = useState(() => initial(c, code, fields));
  const [saved, setSaved] = useState(() => initial(c, code, fields));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState(false);

  useEffect(() => {
    const v = initial(c, code, fields);
    setValues(v);
    setSaved(v);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [c.id, c.version, code, c.updated_at]);

  const dirty = fields.filter((f) => values[f.key] !== saved[f.key]);

  async function save() {
    setBusy(true);
    setError(null);
    setOk(false);
    try {
      let result: Case | null = null;
      const caseChanges = Object.fromEntries(dirty.filter((f) => f.target === "case").map((f) => {
        const v = values[f.key].trim();
        return [f.key, v === "" ? null : f.kind === "number" ? Number(v) : v];
      }));
      if (Object.keys(caseChanges).length) {
        result = await api<Case>(`/cases/${c.id}`, { method: "PATCH", body: { ...caseChanges, version: c.version } });
      }
      const contentChanges = Object.fromEntries(dirty.filter((f) => f.target === "content").map((f) => [f.key, values[f.key]]));
      if (Object.keys(contentChanges).length) {
        result = await api<Case>(`/cases/${c.id}/disciplines/${code}`, { method: "PATCH", body: { content: contentChanges } });
      }
      if (result) onSaved(result);
      setOk(true);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const locked = new Set(c.locked_fields);
  return (
    <div className="stack">
      <div className="grid g2">
        {fields.map((f) => {
          const disabled = !editable || (f.target === "case" && locked.has(f.key));
          const set = (v: string) => setValues({ ...values, [f.key]: v });
          const input = f.kind === "textarea" ? <textarea value={values[f.key]} onChange={(e) => set(e.target.value)} disabled={disabled} maxLength={4000} />
            : f.kind === "select" ? (
              <select value={values[f.key]} onChange={(e) => set(e.target.value)} disabled={disabled}>
                <option value="">Seleccionar…</option>
                {Object.entries(f.options ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>)
              : <input type={f.kind ?? "text"} min={f.kind === "number" ? 0 : undefined} value={values[f.key]} onChange={(e) => set(e.target.value)} disabled={disabled}
                  max={f.key === "defect_date" ? new Date().toISOString().slice(0, 10) : undefined} />;
          return <div key={f.key} style={f.wide || f.kind === "textarea" ? { gridColumn: "1 / -1" } : undefined}>
            <Field label={f.label} required={f.required} hint={f.hint}>{input}</Field></div>;
        })}
      </div>
      <ErrorBox error={error} />
      {editable && (
        <div className="row">
          {ok && !dirty.length && <span className="small" style={{ color: "var(--ok)" }}>Guardado</span>}
          <button className="btn primary right" onClick={save} disabled={busy || !dirty.length}>{busy ? "Guardando…" : "Guardar borrador"}</button>
        </div>
      )}
    </div>
  );
}
