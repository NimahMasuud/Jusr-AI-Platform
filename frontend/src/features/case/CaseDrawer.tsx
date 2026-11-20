import { useCallback, useEffect, useState } from "react";
import { X } from "lucide-react";
import Alert, { type AlertTone } from "../../components/ui/Alert";
import StatusBadge from "../../components/ui/StatusBadge";
import FlagBadges, { PriorityBadge } from "../../components/ui/FlagBadges";
import { LoadingState, ErrorState } from "../../components/ui/StateViews";
import { useUser } from "../../context/UserContext";
import type { CaseDetail, CaseEvent } from "../../services/api/v6.types";
import { confirmPatientMatch, getCase, getCaseTimeline } from "../../services/api/casesApi";
import { formatDateTime, humanize } from "../../utils/format";
import {
  AdminPanel,
  AppointmentPanel,
  ClassifyPanel,
  ClosurePanel,
  ConfirmationPanel,
  MessagingPanel,
  PatientAccessPanel,
  ReferralPanel,
  RoutingPanel,
  type PanelProps,
} from "./ActionPanels";
import AiPanel from "./AiPanel";
import "./case.css";

function InfoGrid({ caseData }: { caseData: CaseDetail }) {
  const entries: [string, string][] = [
    ["Tracker ID", caseData.trackerId ?? "—"],
    ["Facility", caseData.facility?.name ?? "—"],
    ["Owner", caseData.owner?.displayName ?? "Unassigned"],
    ["Screening", caseData.screening ? `${caseData.screening.type} — ${caseData.screening.outcome}` : "—"],
    ["Patient", `${caseData.patient.displayLabel}${caseData.patient.ageYears ? ` · ${caseData.patient.ageYears}y` : ""}${caseData.patient.sex ? ` · ${caseData.patient.sex}` : ""}`],
    ["Preferred language", caseData.patient.preferredLanguage ?? "—"],
    ["Required specialty", caseData.requiredSpecialty ?? "—"],
    ["Confirmatory required", caseData.confirmatoryRequired ? "Yes" : "No"],
    ["Match confidence", caseData.matchConfidence === null ? "—" : `${Math.round(caseData.matchConfidence * 100)}%`],
    ["Entered status", formatDateTime(caseData.statusEnteredAt)],
    ["Due at", formatDateTime(caseData.dueAt)],
    ["Created", formatDateTime(caseData.createdAt)],
    ["Linked case", caseData.linkedCaseId ?? "—"],
    ["Records", `${caseData.counts.results} results · ${caseData.counts.appointments} appointments · ${caseData.counts.treatmentStarts} starts · ${caseData.counts.consultations} consultations`],
  ];

  return (
    <div className="cd-section">
      <div className="cd-section-head">
        <div>
          <h3>Case information</h3>
        </div>
      </div>
      <div className="cd-section-body">
        <div className="cd-grid">
          {entries.map(([label, value]) => (
            <div className="cd-field" key={label}>
              <div className="cd-field-label">{label}</div>
              <div className="cd-field-value">{value}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Timeline({ events }: { events: CaseEvent[] }) {
  return (
    <div className="cd-section">
      <div className="cd-section-head">
        <div>
          <h3>Case history</h3>
          <p>Every transition, flag change and decision is recorded.</p>
        </div>
      </div>
      <div className="cd-section-body">
        {events.length === 0 ? (
          <p className="cd-empty">No events recorded yet.</p>
        ) : (
          <div className="cd-timeline">
            {[...events].reverse().map((event) => (
              <div className="cd-event" key={event.id}>
                <div className="cd-event-title">
                  {event.transition ? `${event.transition} · ` : ""}
                  {event.description}
                </div>
                <div className="cd-event-meta">
                  {formatDateTime(event.occurredAt)}
                  {event.actorRole ? ` · ${humanize(event.actorRole)}` : ""}
                  {event.eventType ? ` · ${humanize(event.eventType)}` : ""}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function CaseDrawer({
  caseId,
  onClose,
  onChanged,
}: {
  caseId: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { activeUser } = useUser();
  const [caseData, setCaseData] = useState<CaseDetail | null>(null);
  const [events, setEvents] = useState<CaseEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: AlertTone; message: string } | null>(null);

  const load = useCallback(async () => {
    try {
      const [detail, timeline] = await Promise.all([
        getCase(caseId),
        getCaseTimeline(caseId),
      ]);
      setCaseData(detail);
      setEvents(timeline);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load this case.");
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    setLoading(true);
    void load();
  }, [load]);

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const run = useCallback(
    async (action: () => Promise<unknown>, message?: string) => {
      setBusy(true);
      setNotice(null);
      try {
        await action();
        if (message) setNotice({ tone: "success", message });
        await load();
        onChanged();
        return true;
      } catch (err) {
        setNotice({
          tone: "danger",
          message:
            err instanceof Error
              ? err.message
              : "The action could not be completed.",
        });
        return false;
      } finally {
        setBusy(false);
      }
    },
    [load, onChanged]
  );

  const panelProps: PanelProps | null = caseData
    ? { caseData, busy, run }
    : null;

  const role = activeUser?.role;
  const isClinician =
    role === "referring_clinician" || role === "receiving_clinician";
  const isCoordinator = role === "coordinator" || role === "national_admin";

  const status = caseData?.status;

  return (
    <div
      className="cd-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <aside className="cd-panel" role="dialog" aria-modal="true" aria-label="Case details">
        {loading && !caseData ? (
          <div style={{ padding: 32 }}>
            <LoadingState message="Loading case…" />
          </div>
        ) : error && !caseData ? (
          <div style={{ padding: 32 }}>
            <ErrorState message={error} onRetry={() => void load()} />
          </div>
        ) : caseData && panelProps ? (
          <>
            <header className="cd-header">
              <div>
                <h2>
                  {caseData.patient.displayLabel}
                  <StatusBadge status={caseData.status} />
                  <PriorityBadge priority={caseData.priority} />
                </h2>
                <div className="cd-header-meta">
                  <span>
                    Case <strong>{caseData.caseId}</strong>
                  </span>
                  {caseData.trackerId && (
                    <span>
                      Tracker <strong>{caseData.trackerId}</strong>
                    </span>
                  )}
                  <span>
                    Facility <strong>{caseData.facility.name}</strong>
                  </span>
                  <span>
                    Owner <strong>{caseData.owner?.displayName ?? "Unassigned"}</strong>
                  </span>
                </div>
                <div className="cd-header-badges">
                  <FlagBadges flags={caseData.flags} />
                  {caseData.delayReason && (
                    <span className="ui-badge ui-badge-warning">
                      Delay: {humanize(caseData.delayReason.code)}
                    </span>
                  )}
                </div>
              </div>
              <button type="button" className="cd-close" onClick={onClose} aria-label="Close case details">
                <X size={18} />
              </button>
            </header>

            <div className="cd-body">
              {notice && <Alert tone={notice.tone}>{notice.message}</Alert>}
              {error && <Alert tone="danger">{error}</Alert>}

              {caseData.nextAction && (
                <div className="cd-next-action">
                  <strong>Next action</strong>
                  {caseData.nextAction.label ?? humanize(caseData.nextAction.code)}
                </div>
              )}

              {status === "NEW" && (
                <div className="cd-section">
                  <div className="cd-section-head">
                    <div>
                      <h3>Patient match</h3>
                      <p>Confirm the matched patient before classification (T2).</p>
                    </div>
                  </div>
                  <div className="cd-section-body">
                    <div className="cd-grid">
                      <div className="cd-field">
                        <div className="cd-field-label">Matched patient</div>
                        <div className="cd-field-value">{caseData.patient.displayLabel}</div>
                      </div>
                      <div className="cd-field">
                        <div className="cd-field-label">Confidence</div>
                        <div className="cd-field-value">
                          {caseData.matchConfidence === null
                            ? "Not scored"
                            : `${Math.round(caseData.matchConfidence * 100)}%`}
                        </div>
                      </div>
                    </div>
                    {isCoordinator ? (
                      <div className="cd-actions">
                        <button
                          type="button"
                          className="ui-btn ui-btn-primary"
                          disabled={busy}
                          onClick={() =>
                            run(
                              () => confirmPatientMatch(caseData.id),
                              "Patient match confirmed (T2)."
                            )
                          }
                        >
                          Confirm match
                        </button>
                      </div>
                    ) : (
                      <p className="cd-small">
                        A coordinator confirms the patient match; clinicians classify afterwards.
                      </p>
                    )}
                  </div>
                </div>
              )}

              {status === "AWAITING_CLASSIFICATION" && (
                <ClassifyPanel {...panelProps} />
              )}

              {status === "URGENT_ROUTING" && <RoutingPanel {...panelProps} />}

              {status === "NOTIFYING" && <MessagingPanel {...panelProps} />}

              {status === "AWAITING_ACK" && (
                <>
                  <ReferralPanel {...panelProps} />
                  <MessagingPanel {...panelProps} />
                </>
              )}

              {status === "AWAITING_CONFIRMATION" && (
                <>
                  <ConfirmationPanel {...panelProps} />
                  <ReferralPanel {...panelProps} />
                </>
              )}

              {status === "REFERRAL_PENDING" && <ReferralPanel {...panelProps} />}

              {(status === "AWAITING_APPOINTMENT" ||
                status === "AWAITING_TREATMENT") && <AppointmentPanel {...panelProps} />}

              {(status === "READY_TO_CLOSE" ||
                (status !== "CLOSED" && isClinician)) && (
                <ClosurePanel {...panelProps} />
              )}

              {status === "CLOSED" && <ClosurePanel {...panelProps} />}

              <PatientAccessPanel {...panelProps} />

              <InfoGrid caseData={caseData} />
              <AdminPanel {...panelProps} />
              <AiPanel caseId={caseData.id} onChanged={() => void load()} />
              <Timeline events={events} />
            </div>
          </>
        ) : null}
      </aside>
    </div>
  );
}
