/**
 * Client-side file export helpers. Everything exported here is built from
 * data the page already fetched from the backend -- nothing is invented.
 */

/** Trigger a browser download of `content` as `filename`. */
export function downloadFile(filename, content, mimeType = 'text/plain;charset=utf-8') {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function csvCell(value) {
  if (value === null || value === undefined) return '';
  let text = String(value);
  // Spreadsheet apps execute cells starting with these characters as
  // formulas ("CSV injection"); prefix text cells so they stay text.
  if (typeof value === 'string' && /^[=+\-@]/.test(text)) text = `'${text}`;
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/**
 * Build CSV text. `columns` is a list of { label, value } where `value` is a
 * property name or a function (row) => cell.
 */
export function toCsv(rows, columns) {
  const header = columns.map((c) => csvCell(c.label)).join(',');
  const body = rows.map((row) =>
    columns.map((c) => csvCell(typeof c.value === 'function' ? c.value(row) : row[c.value])).join(','),
  );
  return [header, ...body].join('\n');
}

/** Filename-safe slug, e.g. "Coimbatore Kharif 2024" -> "coimbatore-kharif-2024". */
export function slug(text) {
  return String(text).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}
