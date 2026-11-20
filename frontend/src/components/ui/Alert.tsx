import type { ReactNode } from "react";
import "./ui.css";

export type AlertTone = "info" | "success" | "warning" | "danger";

export default function Alert({
  tone = "info",
  title,
  children,
}: {
  tone?: AlertTone;
  title?: string;
  children?: ReactNode;
}) {
  return (
    <div className={`ui-alert ui-alert-${tone}`} role="status">
      <div>
        {title && <div className="ui-alert-title">{title}</div>}
        {children && <div>{children}</div>}
      </div>
    </div>
  );
}
