"use client";

// Gráficos SVG propios (sin dependencias). Paleta categórica validada (orden fijo):
// azul #2a78d6, naranja #eb6834, aqua #1baf7a, amarillo #eda100. Contraste bajo de aqua/amarillo
// se compensa con etiquetas de valor visibles en cada gráfico (regla de alivio).
// Todos aceptan `selected` + `onSelect`: clic para filtrar el tablero; lo no seleccionado se atenúa.
export const SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"];
const INK = "#15202e";
const MUTED = "#5d6a7c";
const GRID = "#e9edf3";
const DIM = 0.28;

type Pick = { selected?: string | null; onSelect?: (key: string) => void };
const dim = (selected: string | null | undefined, key: string) => (selected && selected !== key ? DIM : 1);
// Sin `style`: no debe pisar el estilo del elemento (el cursor lo pone la regla CSS [role=button]).
const hit = (onSelect: Pick["onSelect"], key: string) => onSelect ? {
  role: "button", tabIndex: 0, onClick: () => onSelect(key),
  onKeyDown: (e: React.KeyboardEvent) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(key); } },
} : {};

export function Donut({ data, total, label, selected, onSelect }:
  { data: { key: string; label: string; n: number; color: string }[]; total: number; label: string } & Pick) {
  const size = 168, stroke = 26, r = (size - stroke) / 2, c = 2 * Math.PI * r;
  const sum = data.reduce((s, d) => s + d.n, 0);
  let offset = 0;
  return (
    <div className="row" style={{ gap: 20, alignItems: "center", flexWrap: "wrap" }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${label}: ${data.map((d) => `${d.label} ${d.n}`).join(", ")}`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={GRID} strokeWidth={stroke} />
        {sum > 0 && data.filter((d) => d.n > 0).map((d) => {
          const len = (d.n / sum) * c;
          // 2px de separación entre segmentos
          const seg = <circle key={d.key} cx={size / 2} cy={size / 2} r={r} fill="none" stroke={d.color} strokeWidth={stroke}
            strokeDasharray={`${Math.max(len - 2, 0.1)} ${c}`} strokeDashoffset={-offset} transform={`rotate(-90 ${size / 2} ${size / 2})`}
            opacity={dim(selected, d.key)} {...hit(onSelect, d.key)}>
            <title>{`${d.label}: ${d.n} (${Math.round((100 * d.n) / sum)} %)`}</title></circle>;
          offset += len;
          return seg;
        })}
        <text x="50%" y="47%" textAnchor="middle" fontSize="40" fontWeight="700" fill={INK}>{total}</text>
        <text x="50%" y="61%" textAnchor="middle" fontSize="14" fill={MUTED}>{selected ? "Selección" : "Total"}</text>
      </svg>
      <div className="stack" style={{ gap: 4, flex: 1, minWidth: 170 }}>
        {data.map((d) => (
          <div key={d.key} className="row pick" style={{ gap: 10, flexWrap: "nowrap", opacity: dim(selected, d.key), fontWeight: selected === d.key ? 700 : 400 }}
            {...hit(onSelect, d.key)} aria-pressed={selected === d.key}>
            <span style={{ width: 12, height: 12, borderRadius: 3, background: d.color, flex: "none" }} />
            <span style={{ flex: 1, whiteSpace: "nowrap" }}>{d.label}</span>
            <b>{d.n}</b><span className="small muted" style={{ width: 44, textAlign: "right" }}>{sum ? Math.round((100 * d.n) / sum) : 0} %</span>
          </div>))}
      </div>
    </div>
  );
}

export function HBars({ data, color = SERIES[0], selected, onSelect, max: maxRows = 8 }:
  { data: { key?: string; label: string; n: number }[]; color?: string; max?: number } & Pick) {
  const max = Math.max(1, ...data.map((d) => d.n));
  if (!data.length) return <p className="muted small">Sin datos.</p>;
  return (
    <div className="stack" style={{ gap: 4, maxHeight: maxRows * 34, overflowY: data.length > maxRows ? "auto" : undefined, paddingRight: 4 }}>
      {data.map((d) => {
        const key = d.key ?? d.label;
        return (
          <div key={key} className="row pick" style={{ gap: 12, flexWrap: "nowrap", opacity: dim(selected, key) }} title={`${d.label}: ${d.n} 8D`}
            {...hit(onSelect, key)} aria-pressed={selected === key}>
            <span style={{ width: 140, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: selected === key ? 700 : 400 }}>{d.label}</span>
            <div style={{ flex: 1, height: 20, background: "#f3f6fa", borderRadius: 4 }}>
              <div style={{ width: `${(100 * d.n) / max}%`, height: 20, background: color, borderRadius: 4, minWidth: d.n ? 4 : 0 }} />
            </div>
            <b style={{ width: 28, textAlign: "right" }}>{d.n}</b>
          </div>);
      })}
    </div>
  );
}

export const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
export const monthLabel = (key: string) => { const [y, m] = key.split("-"); return `${MONTHS[Number(m) - 1]} ${y}`; };

export function Trend({ data, selected, onSelect }: { data: { month: string; opened: number; closed: number }[] } & Pick) {
  const w = 520, h = 210, pad = { l: 28, r: 8, t: 16, b: 28 };
  const max = Math.max(1, ...data.flatMap((d) => [d.opened, d.closed]));
  const step = (w - pad.l - pad.r) / data.length;
  const bw = Math.min(22, step / 3);
  const y = (v: number) => pad.t + (h - pad.t - pad.b) * (1 - v / max);
  const ticks = Array.from(new Set([0, Math.ceil(max / 2), max]));
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="row small" style={{ gap: 16 }}>
        <span className="row" style={{ gap: 6 }}><span style={{ width: 12, height: 12, borderRadius: 3, background: SERIES[0] }} />Abiertos</span>
        <span className="row" style={{ gap: 6 }}><span style={{ width: 12, height: 12, borderRadius: 3, background: SERIES[2] }} />Cerrados</span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} width="100%" role="img" aria-label={`8D abiertos y cerrados por mes: ${data.map((d) => `${d.month} ${d.opened} abiertos, ${d.closed} cerrados`).join("; ")}`}>
        {ticks.map((t) => <g key={t}><line x1={pad.l} x2={w - pad.r} y1={y(t)} y2={y(t)} stroke={GRID} />
          <text x={pad.l - 6} y={y(t) + 4} textAnchor="end" fontSize="11" fill={MUTED}>{t}</text></g>)}
        {data.map((d, i) => {
          const cx = pad.l + step * i + step / 2;
          const [, mm] = d.month.split("-");
          const on = selected === d.month;
          return (
            <g key={d.month} opacity={dim(selected, d.month)} {...hit(onSelect, d.month)}>
              {/* Área de clic de todo el mes (más grande que las barras). */}
              <rect x={pad.l + step * i + 2} y={pad.t - 10} width={step - 4} height={h - pad.t - pad.b + 34} rx={6}
                fill={on ? "#e8f1fd" : "transparent"} />
              {([["opened", SERIES[0], -1], ["closed", SERIES[2], 1]] as const).map(([k, color, side]) => {
                const v = d[k];
                const x = cx + (side < 0 ? -bw - 1 : 1);
                return (
                  <g key={k}>
                    <path d={v ? `M${x},${y(0)} V${y(v) + 4} q0,-4 4,-4 h${bw - 8} q4,0 4,4 V${y(0)} Z` : ""} fill={color} />
                    {v > 0 && <text x={x + bw / 2} y={y(v) - 4} textAnchor="middle" fontSize="11" fontWeight="600" fill={INK}>{v}</text>}
                  </g>);
              })}
              <text x={cx} y={h - 8} textAnchor="middle" fontSize="12" fontWeight={on ? 700 : 400} fill={on ? INK : MUTED}>{MONTHS[Number(mm) - 1]}</text>
              <title>{`${monthLabel(d.month)}: ${d.opened} abiertos, ${d.closed} cerrados — clic para ver los 8D trabajados en el mes`}</title>
            </g>);
        })}
        <line x1={pad.l} x2={w - pad.r} y1={y(0)} y2={y(0)} stroke="#c9d2de" />
      </svg>
    </div>
  );
}

/** Barras apiladas al 100 % por hito (estado de cumplimiento). Colores de estado con etiqueta, nunca solo color. */
export function MilestoneBars({ data, colors, labels }:
  { data: { label: string; counts: Record<string, number> }[]; colors: Record<string, string>; labels: Record<string, string> }) {
  const keys = Object.keys(colors);
  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="row small" style={{ gap: 12, flexWrap: "wrap" }}>
        {keys.map((k) => <span key={k} className="row" style={{ gap: 6 }}><span style={{ width: 12, height: 12, borderRadius: 3, background: colors[k] }} />{labels[k]}</span>)}
      </div>
      {data.map((row) => {
        const total = keys.reduce((s, k) => s + (row.counts[k] ?? 0), 0);
        const pct = total ? Math.round((100 * (row.counts.on_time ?? 0)) / total) : 0;
        return (
          <div key={row.label}>
            <div className="row small" style={{ justifyContent: "space-between" }}><span>{row.label}</span><span className="muted">{pct} % a tiempo</span></div>
            <div style={{ display: "flex", gap: 2, height: 18, borderRadius: 4, overflow: "hidden", background: "#f3f6fa" }}
              title={keys.map((k) => `${labels[k]}: ${row.counts[k] ?? 0}`).join(" · ")}>
              {keys.filter((k) => row.counts[k]).map((k) => (
                <div key={k} style={{ flex: row.counts[k], background: colors[k], color: "#fff", fontSize: 11, fontWeight: 700, textAlign: "center", lineHeight: "18px" }}>
                  {row.counts[k]}</div>))}
            </div>
          </div>);
      })}
    </div>
  );
}
