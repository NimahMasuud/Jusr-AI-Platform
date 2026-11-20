export { formatDateTime } from "./formatDateTime";

export function formatDateOnly(value: string | null | undefined): string {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not available";
  return date.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function humanize(value: string | null | undefined): string {
  if (!value) return "—";
  return value
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/^\w/, (c) => c.toUpperCase());
}

export function formatHours(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) return "—";
  const absolute = Math.abs(hours);
  const wholeDays = Math.floor(absolute / 24);
  const remainder = Math.round(absolute % 24);
  if (wholeDays > 0) {
    return remainder > 0 ? `${wholeDays}d ${remainder}h` : `${wholeDays}d`;
  }
  if (absolute < 1) return `${Math.max(1, Math.round(absolute * 60))}m`;
  return `${Math.round(absolute)}h`;
}

export function formatTimeLeft(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) return "No limit";
  if (hours < 0) return `${formatHours(hours)} overdue`;
  return `${formatHours(hours)} left`;
}

export function initialsOf(label: string): string {
  return label
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}
