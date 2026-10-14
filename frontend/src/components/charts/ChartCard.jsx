import React, { useState } from 'react';

/**
 * Card wrapper for a chart with a chart/table toggle, so every chart's data
 * is also available as text (accessibility, and the relief for the gray
 * context colour sitting just under 3:1 contrast).
 *
 * table: { columns: [{ key, label, format? }], rows: [...] }
 */
export default function ChartCard({ title, subtitle, table, actions, children }) {
  const [asTable, setAsTable] = useState(false);
  return (
    <section className="bg-surface-container-lowest rounded-xl border border-outline-variant/30 p-4 flex flex-col">
      <div className="flex flex-wrap items-start justify-between gap-2 mb-3">
        <div>
          <h4 className="font-headline-md text-[16px] font-bold text-on-surface">{title}</h4>
          {subtitle && <p className="text-xs text-on-surface-variant mt-0.5">{subtitle}</p>}
        </div>
        <div className="flex items-center gap-2">
          {actions}
          {table && (
            <button
              onClick={() => setAsTable((v) => !v)}
              aria-pressed={asTable}
              className="text-xs font-semibold text-primary border border-outline-variant rounded-full px-3 py-1 hover:bg-surface-container-low cursor-pointer"
            >
              {asTable ? 'Show chart' : 'Show table'}
            </button>
          )}
        </div>
      </div>
      {asTable && table ? (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-on-surface-variant border-b border-outline-variant/40">
                {table.columns.map((c) => <th key={c.key} scope="col" className="py-1.5 pr-3 font-semibold">{c.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((row, i) => (
                <tr key={i} className="border-b border-outline-variant/20">
                  {table.columns.map((c) => (
                    <td key={c.key} className="py-1.5 pr-3">{c.format ? c.format(row[c.key], row) : (row[c.key] ?? '–')}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : children}
    </section>
  );
}
