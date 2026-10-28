"use client";

import { useState } from "react";
import { api, errorText, useApi } from "@/lib/api";
import type { Category, Idea } from "@/lib/types";
import { Badge, Empty, ErrorBox, Field, Loading, Modal } from "@/components/ui";
import { useCan } from "@/components/Shell";

function IdeaForm({ categories, onClose, onSaved }: { categories: Category[]; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({ category_id: categories[0]?.id ?? "", title_es: "", title_en: "", description_es: "", process_tags: "", defect_tags: "" });
  const [error, setError] = useState<string | null>(null);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });
  const tags = (s: string) => s.split(",").map((t) => t.trim()).filter(Boolean);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api("/cause-ideas", { body: { ...f, title_en: f.title_en || null, description_es: f.description_es || null, process_tags: tags(f.process_tags), defect_tags: tags(f.defect_tags) } });
      onSaved();
      onClose();
    } catch (err) {
      setError(errorText(err));
    }
  }
  return (
    <Modal title="Nueva idea de causa" onClose={onClose}>
      <form className="stack" onSubmit={submit}>
        <Field label="Categoría" required><select value={f.category_id} onChange={set("category_id")}>{categories.map((c) => <option key={c.id} value={c.id}>{c.name_es}</option>)}</select></Field>
        <Field label="Título (español)" required><input value={f.title_es} onChange={set("title_es")} minLength={3} required /></Field>
        <Field label="Título (inglés)"><input value={f.title_en} onChange={set("title_en")} /></Field>
        <Field label="Descripción"><textarea value={f.description_es} onChange={set("description_es")} /></Field>
        <div className="grid g2">
          <Field label="Etiquetas de proceso" hint="Separadas por coma: inyección, maquinado"><input value={f.process_tags} onChange={set("process_tags")} /></Field>
          <Field label="Etiquetas de defecto" hint="Separadas por coma: rebaba, dimensional"><input value={f.defect_tags} onChange={set("defect_tags")} /></Field>
        </div>
        <ErrorBox error={error} />
        <div className="row"><button type="button" className="btn" onClick={onClose}>Cancelar</button><button className="btn primary right">Guardar</button></div>
      </form>
    </Modal>
  );
}

export default function CatalogPage() {
  const canManage = useCan("catalog.manage");
  const categories = useApi<Category[]>("/ishikawa/categories");
  const ideas = useApi<Idea[]>(`/cause-ideas${canManage ? "?include_inactive=true" : ""}`);
  const [filter, setFilter] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle(i: Idea) {
    try {
      await api(`/cause-ideas/${i.id}`, { method: "PATCH", body: { is_active: !i.is_active } });
      void ideas.reload();
    } catch (e) {
      setError(errorText(e));
    }
  }

  const list = ideas.data?.filter((i) => !filter || i.category_id === filter) ?? [];
  return (
    <>
      <div className="page-head">
        <div><h1>Catálogo de causas</h1><div className="sub">Biblioteca de ideas por categoría 6M. Son hipótesis para investigar, no conclusiones.</div></div>
        <div className="actions">{canManage && categories.data && <button className="btn primary" onClick={() => setAdding(true)}>+ Nueva idea</button>}</div>
      </div>
      <div className="card">
        <div className="card-head">
          <select value={filter} onChange={(e) => setFilter(e.target.value)} style={{ maxWidth: 240 }} aria-label="Categoría">
            <option value="">Todas las categorías</option>{categories.data?.map((c) => <option key={c.id} value={c.id}>{c.name_es}</option>)}
          </select>
          <span className="right small muted">{list.length} idea(s)</span>
        </div>
        <ErrorBox error={ideas.error ?? categories.error ?? error} onRetry={ideas.reload} />
        {ideas.loading && !ideas.data ? <div className="card-pad"><Loading /></div> : !list.length ? <Empty title="Sin ideas" /> : (
          <div className="table-wrap"><table>
            <thead><tr><th>Categoría</th><th>Idea</th><th>Proceso</th><th>Defecto</th><th>Origen</th><th></th></tr></thead>
            <tbody>{list.map((i) => (
              <tr key={i.id} style={i.is_active ? undefined : { opacity: 0.5 }}>
                <td className="small">{categories.data?.find((c) => c.id === i.category_id)?.name_es}</td>
                <td><b>{i.title_es}</b>{i.title_en && <div className="small muted">{i.title_en}</div>}</td>
                <td className="small">{i.process_tags.join(", ") || "—"}</td><td className="small">{i.defect_tags.join(", ") || "—"}</td>
                <td>{i.is_base ? <Badge>Base</Badge> : <Badge tone="blue">Organización</Badge>}</td>
                <td>{canManage && !i.is_base && <button className="btn sm" onClick={() => toggle(i)}>{i.is_active ? "Desactivar" : "Activar"}</button>}</td>
              </tr>))}</tbody>
          </table></div>
        )}
      </div>
      {adding && categories.data && <IdeaForm categories={categories.data} onClose={() => setAdding(false)} onSaved={ideas.reload} />}
    </>
  );
}
