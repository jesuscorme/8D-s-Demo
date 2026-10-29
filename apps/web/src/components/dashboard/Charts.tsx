"use client";

// Gráficos SVG propios (sin dependencias). Paleta categórica validada (orden fijo):
// azul #2a78d6, naranja #eb6834, aqua #1baf7a, amarillo #eda100. Contraste bajo de aqua/amarillo
// se compensa con etiquetas de valor visibles en cada gráfico (regla de alivio).
export const SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"];
const INK = "#15202e";
const MUTED = "#5d6a7c";
const GRID = "#e9edf3";

export function Donut({ data, total, label }: { data: { label: string; n: number; color: string }[]; total: number; label: string }) {
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
          const seg = <circle key={d.label} cx={size / 2} cy={size / 2} r={r} fill="none" stroke={d.color} strokeWidth={stroke}
            strokeDasharray={`${Math.max(len - 2, 0.1)} ${c}`} strokeDashoffset={-offset} transform={`rotate(-90 ${size / 2} ${size / 2})`}>
            <title>{`${d.label}: ${d.n} (${Math.round((100 * d.n) / sum)} %)`}</title></circle>;
          offset += len;
          return seg;
        })}
        <text x="50%" y="47%" textAnchor="middle" fontSize="40" fontWeight="700" fill={INK}>{total}</text>
        <text x="50%" y="61%" textAnchor="middle" fontSize="14" fill={MUTED}>Total</text>
      </svg>
      <div className="stack" style={{ gap: 10, flex: 1, minWidth: 170 }}>
        {data.map((d) => (
          <div key={d.label} className="row" style={{ gap: 10, flexWrap: "nowrap" }}>
            <span style={{ width: 12, height: 12, borderRadius: 3, background: d.color, flex: "none" }} />
            <span style={{ flex: 1, whiteSpace: "nowrap" }}>{d.label}</span>
            <b>{d.n}</b><span className="small muted" style={{ width: 44, textAlign: "right" }}>{sum ? Math.round((100 * d.n) / sum) : 0} %</span>
          </div>))}
      </div>
    </div>
  );
}

export function HBars({ data, color = SERIES[0] }: { data: { label: string; n: number }[]; color?: string }) {
  const max = Math.max(1, ...data.map((d) => d.n));
  if (!data.length) return <p className="muted small">Sin datos.</p>;
  return (
    <div className="stack" style={{ gap: 10 }}>
      {data.map((d) => (
        <div key={d.label} className="row" style={{ gap: 12, flexWrap: "nowrap" }} title={`${d.label}: ${d.n} 8D`}>
          <span style={{ width: 150, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{d.label}</span>
          <div style={{ flex: 1, height: 22, background: "#f3f6fa", borderRadius: 4 }}>
            <div style={{ width: `${(100 * d.n) / max}%`, height: 22, background: color, borderRadius: 4, minWidth: 4 }} />
          </div>
          <b style={{ width: 32, textAlign: "right" }}>{d.n}</b>
        </div>))}
    </div>
  );
}

const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

export function Trend({ data }: { data: { month: string; opened: number; closed: number }[] }) {
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
          const [yy, mm] = d.month.split("-");
          return (
            <g key={d.month}>
              {([["opened", SERIES[0], -1], ["closed", SERIES[2], 1]] as const).map(([k, color, side]) => {
                const v = d[k];
                const x = cx + (side < 0 ? -bw - 1 : 1);
                return (
                  <g key={k}>
                    <path d={v ? `M${x},${y(0)} V${y(v) + 4} q0,-4 4,-4 h${bw - 8} q4,0 4,4 V${y(0)} Z` : ""} fill={color}>
                      <title>{`${MONTHS[Number(mm) - 1]} ${yy}: ${v} ${k === "opened" ? "abiertos" : "cerrados"}`}</title></path>
                    {v > 0 && <text x={x + bw / 2} y={y(v) - 4} textAnchor="middle" fontSize="11" fontWeight="600" fill={INK}>{v}</text>}
                  </g>);
              })}
              <text x={cx} y={h - 8} textAnchor="middle" fontSize="12" fill={MUTED}>{MONTHS[Number(mm) - 1]}</text>
            </g>);
        })}
        <line x1={pad.l} x2={w - pad.r} y1={y(0)} y2={y(0)} stroke="#c9d2de" />
      </svg>
    </div>
  );
}
