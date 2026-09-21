/** Treat API timestamps without a zone as UTC (legacy naive ISO strings). */
export function asUtcDate(value: string | Date | null | undefined): Date | null {
  if (value == null || value === '') return null;
  if (value instanceof Date) return value;
  const raw = String(value).trim();
  if (!raw) return null;
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw);
  return new Date(hasZone ? raw : `${raw}Z`);
}
