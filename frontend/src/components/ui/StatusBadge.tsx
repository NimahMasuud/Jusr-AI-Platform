import type { CaseStatus } from "../../services/api/v6.types";
import "./ui.css";

const STATUS_LABELS: Record<string, string> = {
  NEW: "New",
  AWAITING_CLASSIFICATION: "Awaiting classification",
  URGENT_ROUTING: "Urgent routing",
  NOTIFYING: "Notifying",
  AWAITING_ACK: "Awaiting acknowledgement",
  AWAITING_CONFIRMATION: "Awaiting confirmation",
  REFERRAL_PENDING: "Referral pending",
  AWAITING_APPOINTMENT: "Awaiting appointment",
  AWAITING_TREATMENT: "Awaiting treatment",
  READY_TO_CLOSE: "Ready to close",
  CLOSED: "Closed",
};

const STATUS_TONES: Record<string, string> = {
  NEW: "ui-badge-neutral",
  AWAITING_CLASSIFICATION: "ui-badge-info",
  URGENT_ROUTING: "ui-badge-danger",
  NOTIFYING: "ui-badge-warning",
  AWAITING_ACK: "ui-badge-warning",
  AWAITING_CONFIRMATION: "ui-badge-warning",
  REFERRAL_PENDING: "ui-badge-teal",
  AWAITING_APPOINTMENT: "ui-badge-teal",
  AWAITING_TREATMENT: "ui-badge-teal",
  READY_TO_CLOSE: "ui-badge-primary",
  CLOSED: "ui-badge-success",
};

export function statusLabel(status: string | null | undefined): string {
  if (!status) return "Unknown";
  return STATUS_LABELS[status] ?? status.replaceAll("_", " ").toLowerCase();
}

export default function StatusBadge({
  status,
}: {
  status: CaseStatus | string | null | undefined;
}) {
  if (!status) return null;
  return (
    <span
      className={`ui-badge ${STATUS_TONES[status] ?? "ui-badge-neutral"}`}
      title={status}
    >
      <span className="ui-badge-dot" />
      {statusLabel(status)}
    </span>
  );
}
