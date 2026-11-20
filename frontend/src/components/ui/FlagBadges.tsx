import type { CaseFlag, Priority } from "../../services/api/v6.types";
import "./ui.css";

const FLAG_LABELS: Record<CaseFlag, string> = {
  URGENT: "Urgent",
  OVERDUE: "Overdue",
  EXCEPTION: "Exception",
  UNASSIGNED: "Unassigned",
  DATA_MISSING: "Data missing",
  MESSAGE_FAILED: "Message failed",
  NOT_EXPLAINED: "Not explained",
};

const FLAG_CLASSES: Record<CaseFlag, string> = {
  URGENT: "ui-flag-urgent",
  OVERDUE: "ui-flag-overdue",
  EXCEPTION: "ui-flag-exception",
  UNASSIGNED: "ui-flag-unassigned",
  DATA_MISSING: "ui-flag-data-missing",
  MESSAGE_FAILED: "ui-flag-message-failed",
  NOT_EXPLAINED: "ui-flag-not-explained",
};

export default function FlagBadges({ flags }: { flags: CaseFlag[] }) {
  if (!flags?.length) return null;
  return (
    <span className="ui-flag-row">
      {flags.map((flag) => (
        <span key={flag} className={`ui-flag ${FLAG_CLASSES[flag] ?? ""}`}>
          {FLAG_LABELS[flag] ?? flag}
        </span>
      ))}
    </span>
  );
}

const PRIORITY_CLASSES: Record<string, string> = {
  URGENT: "ui-badge-urgent",
  HIGH: "ui-badge-warning",
  NORMAL: "ui-badge-neutral",
  LOW: "ui-badge-neutral",
};

export function PriorityBadge({ priority }: { priority: Priority | string }) {
  return (
    <span className={`ui-badge ${PRIORITY_CLASSES[priority] ?? "ui-badge-neutral"}`}>
      {priority}
    </span>
  );
}
