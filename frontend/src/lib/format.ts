// Shared human-readable formatting (audit P1-4: seven components used to keep
// private copies of these Intl formatters — keep new usages on lib/format).

export function formatBytes(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(0)} MB`;
  return `${(bytes / 1024).toFixed(0)} KB`;
}

/** "2026/08/31" — full date for lists that need the year (project cards, logs). */
export function formatDate(value: string | null | undefined): string {
  const date = new Date(value ?? "");
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" }).format(date);
}

/** "08-31 14:30" — compact date+time for version cards / recent rows. */
export function formatDateTime(value: string | null | undefined): string {
  const date = new Date(value ?? "");
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(
    date,
  );
}

/** "14:30" — clock time for generation history rows. */
export function formatClockTime(value: string | null | undefined): string {
  const date = new Date(value ?? "");
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit" }).format(date);
}

/** "08-31" — bare month/day for compact timeline labels. */
export function formatMonthDay(value: string | null | undefined): string {
  const date = new Date(value ?? "");
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit" }).format(date);
}
