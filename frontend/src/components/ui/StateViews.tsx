import type { ReactNode } from "react";
import "./ui.css";

export function LoadingState({ message = "Loading…" }: { message?: string }) {
  return (
    <div className="ui-state">
      <div className="ui-spinner" />
      <p>{message}</p>
    </div>
  );
}

export function EmptyState({
  title,
  message,
  action,
}: {
  title: string;
  message?: string;
  action?: ReactNode;
}) {
  return (
    <div className="ui-state">
      <h3>{title}</h3>
      {message && <p>{message}</p>}
      {action}
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="ui-state">
      <h3>Something went wrong</h3>
      <p>{message}</p>
      {onRetry && (
        <button type="button" className="ui-btn ui-btn-secondary" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}
