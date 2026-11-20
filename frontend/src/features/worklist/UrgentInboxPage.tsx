import { useCallback, useEffect, useState } from "react";
import { Siren } from "lucide-react";
import Alert from "../../components/ui/Alert";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../../components/ui/StateViews";
import type { RoutingStatus } from "../../services/api/v6.types";
import {
  acceptUrgentCase,
  listMyUrgentCases,
  type UrgentCaseItem,
} from "../../services/api/urgentApi";
import { formatDateTime, formatTimeLeft, humanize } from "../../utils/format";
import CaseDrawer from "../case/CaseDrawer";
import "./urgentInbox.css";

function remainingHours(dueAt: string | null) {
  if (!dueAt) return null;
  return (new Date(dueAt).getTime() - Date.now()) / 3600000;
}

export default function UrgentInboxPage() {
  const [items, setItems] = useState<UrgentCaseItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [tab, setTab] = useState<RoutingStatus | "">("AWAITING_ACCEPTANCE");
  const [openCaseId, setOpenCaseId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await listMyUrgentCases({
        pageSize: 50,
        status: tab || undefined,
      });
      setItems(result.items);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load incoming urgent cases."
      );
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleAccept(item: UrgentCaseItem) {
    setBusyId(item.id);
    setNotice("");
    try {
      await acceptUrgentCase(item.id);
      setNotice(`${item.caseId} accepted. You are now the owner of this case.`);
      await load();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to accept this urgent case."
      );
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="page-container">
      <div className="page-heading">
        <div>
          <span className="worklist-eyebrow">URGENT INBOX</span>
          <h1>Incoming urgent cases</h1>
          <p>
            Cases routed to you by specialty. Accept before the routing limit;
            otherwise the coordinator handles the exception.
          </p>
        </div>
      </div>

      <div className="wl-tabs" role="tablist" style={{ background: "transparent", padding: 0, border: 0 }}>
        {[
          { id: "AWAITING_ACCEPTANCE" as RoutingStatus, label: "Awaiting acceptance" },
          { id: "ACCEPTED" as RoutingStatus, label: "Accepted" },
          { id: "" as const, label: "All" },
        ].map((option) => (
          <button
            key={option.label}
            type="button"
            role="tab"
            aria-selected={tab === option.id}
            className={`wl-tab${tab === option.id ? " is-active" : ""}`}
            onClick={() => setTab(option.id)}
          >
            {option.label}
          </button>
        ))}
      </div>

      {notice && <Alert tone="success">{notice}</Alert>}
      {error && <Alert tone="danger">{error}</Alert>}

      {loading ? (
        <LoadingState message="Loading incoming cases…" />
      ) : error && items.length === 0 ? (
        <ErrorState message={error} onRetry={() => void load()} />
      ) : items.length === 0 ? (
        <EmptyState
          title={tab === "ACCEPTED" ? "Nothing accepted yet" : "No pending urgent cases"}
          message="Urgent cases routed to your clinical profile appear here."
        />
      ) : (
        <div className="urgent-inbox-list">
          {items.map((item) => {
            const routing = item.routing;
            const awaiting = item.routingStatus === "AWAITING_ACCEPTANCE";
            return (
              <article className="urgent-inbox-card" key={item.id}>
                <div className="urgent-inbox-card-header">
                  <div>
                    <span className="urgent-case-label">
                      <Siren size={11} /> URGENT
                    </span>
                    <h2>
                      {item.patientLabel} · {item.caseId}
                    </h2>
                    <p>
                      {item.age ? `${item.age}y` : "Age unknown"}
                      {item.sex ? ` · ${item.sex}` : ""} · {item.facility.name}
                    </p>
                  </div>
                  <span className="urgent-routing-status">
                    {item.routingStatus
                      ? humanize(item.routingStatus)
                      : "Not routed"}
                  </span>
                </div>

                <div className="urgent-inbox-details">
                  <div>
                    <span>Screening</span>
                    <strong>
                      {item.screening
                        ? `${item.screening.type} — ${item.screening.outcome}`
                        : "Not recorded"}
                    </strong>
                  </div>
                  <div>
                    <span>Required specialty</span>
                    <strong>
                      {item.specialty ? humanize(item.specialty) : "Not specified"}
                    </strong>
                  </div>
                  <div>
                    <span>Routing stage</span>
                    <strong>
                      {routing ? `Stage ${routing.stage}` : "—"}
                      {routing?.escalatedToCoordinator ? " · escalated" : ""}
                    </strong>
                  </div>
                  <div>
                    <span>Acceptance due</span>
                    <strong>{formatDateTime(item.routingDueAt ?? routing?.dueAt)}</strong>
                  </div>
                  <div>
                    <span>Time left</span>
                    <strong>
                      {formatTimeLeft(
                        remainingHours(item.routingDueAt ?? routing?.dueAt ?? null)
                      )}
                    </strong>
                  </div>
                  <div>
                    <span>Next action</span>
                    <strong>{item.nextAction?.label ?? item.nextAction?.code ?? "—"}</strong>
                  </div>
                  <div>
                    <span>Acceptance limits</span>
                    <strong>
                      {routing?.firstLimitMinutes ?? "—"} /{" "}
                      {routing?.secondLimitMinutes ?? "—"} minutes
                    </strong>
                  </div>
                  <div>
                    <span>Exception</span>
                    <strong>{routing?.exceptionReason ?? "None"}</strong>
                  </div>
                </div>

                <div className="urgent-inbox-action">
                  <button
                    type="button"
                    className="ui-btn ui-btn-secondary"
                    onClick={() => setOpenCaseId(item.id)}
                  >
                    Open case
                  </button>
                  {awaiting && (
                    <button
                      type="button"
                      className="ui-btn ui-btn-primary"
                      disabled={busyId !== null}
                      onClick={() => void handleAccept(item)}
                    >
                      {busyId === item.id ? "Accepting…" : "Accept case"}
                    </button>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}

      {openCaseId && (
        <CaseDrawer
          caseId={openCaseId}
          onClose={() => setOpenCaseId(null)}
          onChanged={() => void load()}
        />
      )}
    </div>
  );
}
