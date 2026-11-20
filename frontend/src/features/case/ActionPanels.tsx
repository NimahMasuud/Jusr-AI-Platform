import { useEffect, useMemo, useState, type ReactNode } from "react";
import Alert from "../../components/ui/Alert";
import FlagBadges from "../../components/ui/FlagBadges";
import MessageDrafter from "../ai/MessageDrafter";
import { useUser } from "../../context/UserContext";
import type {
  AppointmentRecord,
  CaseDetail,
  ClosureChecklist,
  ClosureType,
  ContactAttemptRecord,
  ContactRoute,
  DelayReasonCode,
  DeclineCode,
  MessageRecord,
  PatientLinkRecord,
  PatientResponseRecord,
  ReferralRecord,
  ResultRecord,
  TreatmentStartRecord,
  UnderstandingLevel,
} from "../../services/api/v6.types";
import {
  addContactAttempt,
  addResult,
  assignCase,
  bookAppointment,
  classifyCase,
  closeCase,
  getClosureChecklist,
  listContactAttempts,
  recordAttendance,
  recordConfirmatoryOutcome,
  recordDelayReason,
  recordExplained,
  recordTreatmentStart,
  signOffClosure,
  startLinkedCase,
  transferCase,
  confirmContact,
  getSuggestedRouting,
  listAppointments,
  listResults,
  listTreatmentStarts,
} from "../../services/api/casesApi";
import {
  acceptUrgentCase,
  processDueRouting,
  reassignUrgentCase,
  routeUrgentCase,
} from "../../services/api/urgentApi";
import {
  acceptReferral,
  createReferral,
  declineReferral,
  listReferrals,
  markReferralNotAccepted,
  reassignReferral,
} from "../../services/api/referralsApi";
import {
  approveMessage,
  listMessages,
  rejectMessage,
  sendMessage,
} from "../../services/api/messagesApi";
import {
  createPatientPreviewLink,
  generatePatientLink,
  getPatientLinks,
  getPatientResponses,
  recordAssistedPatientResponse,
} from "../patient/patientAccessService";
import { listFacilities } from "../../services/api/adminApi";
import { normalizeSpecialty, useClosureApprovers, useStaff } from "./useStaff";
import { formatDateOnly, formatDateTime, humanize } from "../../utils/format";
import "./case.css";

export interface PanelProps {
  caseData: CaseDetail;
  busy: boolean;
  run: (action: () => Promise<unknown>, message?: string) => Promise<boolean>;
}

const DELAY_CODES: DelayReasonCode[] = [
  "PATIENT_UNREACHABLE",
  "PATIENT_DID_NOT_UNDERSTAND",
  "REFERRAL_DECLINED",
  "NO_SLOT_AVAILABLE",
  "RESULT_OR_DATA_MISSING",
  "PATIENT_MOVED",
  "OTHER",
];

const CONTACT_ROUTES: ContactRoute[] = ["PHONE", "SMS", "EMAIL", "VISIT", "OTHER"];

const DECLINE_CODES: DeclineCode[] = [
  "WRONG_SPECIALTY",
  "NO_CAPACITY",
  "INFORMATION_MISSING",
  "NOT_ELIGIBLE",
  "OTHER",
];

function field(label: string, value: ReactNode) {
  return (
    <div className="cd-field" key={label}>
      <div className="cd-field-label">{label}</div>
      <div className="cd-field-value">{value ?? "—"}</div>
    </div>
  );
}

function messageText(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

// ------------------------------------------------------------------ classify (T2, T3, T4, T6)

export function ClassifyPanel({ caseData, busy, run }: PanelProps) {
  const [actionable, setActionable] = useState(true);
  const [urgent, setUrgent] = useState(false);
  const [priority, setPriority] = useState<"NORMAL" | "HIGH">("NORMAL");
  const [specialty, setSpecialty] = useState(caseData.requiredSpecialty ?? "");
  const [reason, setReason] = useState("");
  const [confirmatory, setConfirmatory] = useState(caseData.confirmatoryRequired);
  const [suggestion, setSuggestion] = useState<Awaited<ReturnType<typeof getSuggestedRouting>>>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getSuggestedRouting(caseData.id).then(setSuggestion).catch(() => setSuggestion(null));
  }, [caseData.id]);

  function applySuggestion() {
    if (!suggestion) return;
    if (suggestion.suggestedUrgency === "URGENT") setUrgent(true);
    setSpecialty(suggestion.specialty ?? specialty);
    setConfirmatory(suggestion.confirmatoryRequired);
  }

  async function submit() {
    setError("");
    if (!actionable && !reason.trim()) {
      setError("Marking a result not actionable needs a reason.");
      return;
    }
    if (urgent && !specialty.trim()) {
      setError("An urgent case needs a required specialty.");
      return;
    }
    const ok = await run(
      () =>
        classifyCase(caseData.id, {
          actionable,
          urgent: actionable ? urgent : false,
          priority: urgent ? "URGENT" : priority,
          specialty: urgent ? specialty.trim() : undefined,
          reason: reason.trim() || undefined,
          confirmatoryRequired: confirmatory,
        }),
      actionable
        ? urgent
          ? "Case marked urgent and routed."
          : "Case marked actionable."
        : "Case marked not actionable and closed."
    );
    if (ok) setReason("");
  }

  return (
    <div className="cd-section">
      <div className="cd-section-head">
        <div>
          <h3>Classification</h3>
          <p>A person always sets urgency. Suggestions come from the routing table.</p>
        </div>
      </div>
      <div className="cd-section-body">
        {suggestion && (
          <Alert tone="info" title="Suggested routing from the pathway table">
            <div className="cd-inline">
              <span>
                {suggestion.pathway} — {suggestion.resultCategory} — suggested urgency{" "}
                <strong>{suggestion.suggestedUrgency ?? "none"}</strong>
                {suggestion.specialty ? ` — specialty ${suggestion.specialty}` : ""}
              </span>
              <button type="button" className="ui-btn ui-btn-secondary ui-btn-sm" onClick={applySuggestion}>
                Use suggestion
              </button>
            </div>
          </Alert>
        )}

        <div className="cd-form">
          <div className="ui-field">
            <label>Decision</label>
            <select
              value={actionable ? "yes" : "no"}
              onChange={(event) => setActionable(event.target.value === "yes")}
              disabled={busy}
            >
              <option value="yes">Actionable — continue care</option>
              <option value="no">Not actionable — close (T6)</option>
            </select>
          </div>

          {actionable && (
            <>
              <div className="ui-field">
                <label>Urgency</label>
                <select
                  value={urgent ? "urgent" : "routine"}
                  onChange={(event) => setUrgent(event.target.value === "urgent")}
                  disabled={busy}
                >
                  <option value="routine">Routine</option>
                  <option value="urgent">Urgent — specialty routing</option>
                </select>
              </div>

              {!urgent && (
                <div className="ui-field">
                  <label>Priority</label>
                  <select
                    value={priority}
                    onChange={(event) => setPriority(event.target.value as "NORMAL" | "HIGH")}
                    disabled={busy}
                  >
                    <option value="NORMAL">Normal</option>
                    <option value="HIGH">High</option>
                  </select>
                </div>
              )}

              {urgent && (
                <div className="ui-field">
                  <label>Required specialty</label>
                  <input
                    value={specialty}
                    onChange={(event) => setSpecialty(event.target.value)}
                    placeholder="e.g. CARDIOLOGY"
                    disabled={busy}
                  />
                </div>
              )}
            </>
          )}

          <div className="ui-field cd-form-full">
            <label>{actionable ? "Reason (optional)" : "Reason for not actionable (required)"}</label>
            <textarea
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              rows={2}
              disabled={busy}
            />
          </div>

          <label className="ui-checkbox cd-form-full">
            <input
              type="checkbox"
              checked={confirmatory}
              onChange={(event) => setConfirmatory(event.target.checked)}
              disabled={busy}
            />
            <span>A confirmatory test is required before referral (T8 path)</span>
          </label>
        </div>

        {error && <Alert tone="danger">{error}</Alert>}

        <div className="cd-actions">
          <button type="button" className="ui-btn ui-btn-primary" onClick={submit} disabled={busy}>
            {actionable
              ? urgent
                ? "Mark urgent and route"
                : "Mark actionable"
              : "Mark not actionable"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ urgent routing (T4, T5, R-13)

export function RoutingPanel({ caseData, busy, run }: PanelProps) {
  const { activeUser } = useUser();
  const routing = caseData.routing;
  const specialty = caseData.requiredSpecialty ?? "";
  const { staff } = useStaff({
    role: "RECEIVING_CLINICIAN",
    facilityId: caseData.facility.id,
  });
  const [clinicianId, setClinicianId] = useState("");
  const [reason, setReason] = useState("");

  const matching = useMemo(
    () =>
      staff.filter(
        (person) =>
          !specialty || normalizeSpecialty(person.specialty) === normalizeSpecialty(specialty)
      ),
    [staff, specialty]
  );

  const isReceiving = activeUser?.role === "receiving_clinician";
  const canCoordinate = activeUser?.role === "coordinator" || activeUser?.role === "national_admin";

  const active =
    routing?.status === "AWAITING_ACCEPTANCE" || routing?.status === "ACCEPTED";

  return (
    <div className="cd-section">
      <div className="cd-section-head">
        <div>
          <h3>Urgent routing</h3>
          <p>First limit → escalation to coordinator → second limit → backup clinician → exception.</p>
        </div>
        {routing && (
          <span className="ui-badge ui-badge-info">Stage {routing.stage}</span>
        )}
      </div>
      <div className="cd-section-body">
        {routing ? (
          <div className="cd-grid">
            {field("Status", humanize(routing.status))}
            {field("Routed clinician", routing.routedClinician?.displayName ?? "Not assigned")}
            {field("Required specialty", routing.requiredSpecialty ?? "—")}
            {field("Due at", formatDateTime(routing.dueAt))}
            {field("First limit", `${routing.firstLimitMinutes ?? "—"} min`)}
            {field("Second limit", `${routing.secondLimitMinutes ?? "—"} min`)}
            {field("Accepted at", formatDateTime(routing.acceptedAt))}
            {routing.exceptionReason && field("Exception", routing.exceptionReason)}
          </div>
        ) : (
          <p className="cd-muted">
            Routing has not started. It begins when the case is marked urgent.
          </p>
        )}

        {routing?.status === "EXCEPTION" && (
          <Alert tone="danger" title="No clinician is currently accepting this case">
            Route it again to a qualified clinician, or reassign it explicitly.
          </Alert>
        )}

        {isReceiving &&
          routing?.status === "AWAITING_ACCEPTANCE" &&
          routing.routedClinician?.id === activeUser?.id && (
            <div className="cd-actions">
              <button
                type="button"
                className="ui-btn ui-btn-teal"
                disabled={busy}
                onClick={() =>
                  run(() => acceptUrgentCase(caseData.id), "Urgent case accepted.")
                }
              >
                Accept this case (T5)
              </button>
            </div>
          )}

        {canCoordinate && (!active || routing?.status === "EXCEPTION") && (
          <div className="cd-form">
            <div className="ui-field">
              <label>Route to clinician (optional)</label>
              <select
                value={clinicianId}
                onChange={(event) => setClinicianId(event.target.value)}
                disabled={busy}
              >
                <option value="">Auto — first qualified clinician</option>
                {staff.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.displayName}
                    {person.specialty ? ` — ${person.specialty}` : ""}
                  </option>
                ))}
              </select>
            </div>
            <div className="cd-actions">
              <button
                type="button"
                className="ui-btn ui-btn-primary"
                disabled={busy}
                onClick={() =>
                  run(
                    () =>
                      routeUrgentCase(caseData.id, {
                        receivingClinicianId: clinicianId || undefined,
                        specialty:
                          staff.find((person) => person.id === clinicianId)?.specialty ||
                          specialty,
                      }),
                    "Urgent routing started."
                  )
                }
              >
                {routing?.status === "EXCEPTION" ? "Route again" : "Start routing"}
              </button>
              <button
                type="button"
                className="ui-btn ui-btn-secondary"
                disabled={busy}
                onClick={() =>
                  run(() => processDueRouting(), "Acceptance limits checked; escalations applied.")
                }
              >
                Run escalation check
              </button>
            </div>
          </div>
        )}

        {canCoordinate &&
          routing?.status === "AWAITING_ACCEPTANCE" &&
          matching.length > 0 && (
            <div className="cd-form">
              <div className="ui-field">
                <label>Reassign to another clinician</label>
                <select
                  value={clinicianId}
                  onChange={(event) => setClinicianId(event.target.value)}
                  disabled={busy}
                >
                  <option value="">Select a clinician</option>
                  {matching.map((person) => (
                    <option key={person.id} value={person.id}>
                      {person.displayName}
                    </option>
                  ))}
                </select>
              </div>
              <div className="ui-field">
                <label>Reason</label>
                <input
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  disabled={busy}
                />
              </div>
              <div className="cd-actions cd-form-full">
                <button
                  type="button"
                  className="ui-btn ui-btn-secondary"
                  disabled={busy || !clinicianId || !reason.trim()}
                  onClick={() =>
                    run(
                      () =>
                        reassignUrgentCase(caseData.id, {
                          receivingClinicianId: clinicianId,
                          reason: reason.trim(),
                        }),
                      "Routing reassigned."
                    )
                  }
                >
                  Reassign
                </button>
              </div>
            </div>
          )}

        {matching.length === 0 && specialty && (
          <p className="cd-small">
            No active receiving clinician with specialty {specialty} is listed at this facility.
            Auto-routing searches all facilities.
          </p>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ messaging (T7, R-19, R-28)

export function MessagingPanel({ caseData, busy, run }: PanelProps) {
  const { activeUser } = useUser();
  const canMessage = activeUser?.role === "coordinator" || activeUser?.role === "national_admin";
  const [messages, setMessages] = useState<MessageRecord[]>([]);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    listMessages({ caseId: caseData.id, pageSize: 50 })
      .then((page) => {
        if (!cancelled) setMessages(page.items);
      })
      .catch((err) => {
        if (!cancelled) setError(messageText(err, "Unable to load messages."));
      });
    return () => {
      cancelled = true;
    };
  }, [caseData.id, reloadKey]);

  function refresh() {
    setReloadKey((value) => value + 1);
  }

  const closed = caseData.status === "CLOSED";

  return (
    <div className="cd-section">
      <div className="cd-section-head">
        <div>
          <h3>Patient messages</h3>
          <p>Draft → approve → send. Delivery is simulated; retries run automatically.</p>
        </div>
      </div>
      <div className="cd-section-body">
        {error && <Alert tone="danger">{error}</Alert>}

        <div className="cd-list">
          {messages.length === 0 && <p className="cd-empty">No messages yet.</p>}
          {messages.map((message) => (
            <div className="cd-item" key={message.id}>
              <div className="cd-item-head">
                <span className="cd-item-title">
                  {message.channel} · {message.kind.replaceAll("_", " ")}
                </span>
                <span className="ui-badge ui-badge-neutral">{humanize(message.status)}</span>
              </div>
              <p className="cd-muted" style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>
                {message.body}
              </p>
              <div className="cd-item-meta">
                <span>Created {formatDateTime(message.createdAt)}</span>
                {message.sentAt && <span>Sent {formatDateTime(message.sentAt)}</span>}
                <span>Attempts {message.attempts}</span>
                {message.lastError && <span>Last error: {message.lastError}</span>}
              </div>
              {canMessage && !closed && (
                <div className="cd-actions" style={{ marginTop: 8 }}>
                  {message.status === "DRAFT" && (
                    <>
                      <button
                        type="button"
                        className="ui-btn ui-btn-primary ui-btn-sm"
                        disabled={busy}
                        onClick={() =>
                          run(() => approveMessage(message.id), "Message approved.").then(refresh)
                        }
                      >
                        Approve
                      </button>
                      <button
                        type="button"
                        className="ui-btn ui-btn-secondary ui-btn-sm"
                        disabled={busy}
                        onClick={() => {
                          const reason = window.prompt("Reason for rejecting this message:");
                          if (!reason?.trim()) return;
                          void run(
                            () => rejectMessage(message.id, reason.trim()),
                            "Message rejected."
                          ).then(refresh);
                        }}
                      >
                        Reject
                      </button>
                    </>
                  )}
                  {message.status === "APPROVED" && (
                    <button
                      type="button"
                      className="ui-btn ui-btn-teal ui-btn-sm"
                      disabled={busy}
                      onClick={() =>
                        run(() => sendMessage(message.id), "Message sent.").then(refresh)
                      }
                    >
                      Send message
                    </button>
                  )}
                  {(message.status === "FAILED" || message.status === "PENDING") && (
                    <button
                      type="button"
                      className="ui-btn ui-btn-secondary ui-btn-sm"
                      disabled={busy}
                      onClick={refresh}
                    >
                      Refresh
                    </button>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>

        {canMessage && !closed && (
          <MessageDrafter
            caseId={caseData.id}
            priority={caseData.priority}
            onChanged={() => {
              refresh();
              void run(async () => undefined, "Case refreshed.");
            }}
          />
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ patient access and responses (T8, R-30, R-31)

export function PatientAccessPanel({ caseData, busy, run }: PanelProps) {
  const [links, setLinks] = useState<PatientLinkRecord[]>([]);
  const [responses, setResponses] = useState<PatientResponseRecord[]>([]);
  const [generated, setGenerated] = useState<{
    token: string;
    url: string;
    expiresAt: string;
    sms: { to: string; status: string; simulated: boolean } | null;
  } | null>(null);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [previewBusy, setPreviewBusy] = useState(false);

  const [acknowledged, setAcknowledged] = useState(true);
  const [level, setLevel] = useState<UnderstandingLevel>("YES");
  const [confidence, setConfidence] = useState(3);
  const [explanationStatus, setExplanationStatus] = useState<"EXPLAINED" | "NOT_EXPLAINED">("EXPLAINED");
  const [callbackRequested, setCallbackRequested] = useState(false);
  const [note, setNote] = useState("");

  async function openPreview() {
    // Open the tab before awaiting so the browser treats it as part of the click.
    const tab = window.open("about:blank", "_blank");
    setPreviewBusy(true);
    setError("");
    try {
      const preview = await createPatientPreviewLink(caseData.id);
      if (tab) {
        tab.location.href = preview.path;
      } else {
        window.open(preview.path, "_blank", "noopener");
      }
    } catch (err) {
      tab?.close();
      setError(messageText(err, "Unable to open the patient view."));
    } finally {
      setPreviewBusy(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    Promise.all([getPatientLinks(caseData.id), getPatientResponses(caseData.id)])
      .then(([linkRows, responseRows]) => {
        if (cancelled) return;
        setLinks(linkRows);
        setResponses(responseRows);
      })
      .catch((err) => {
        if (!cancelled) setError(messageText(err, "Unable to load patient access."));
      });
    return () => {
      cancelled = true;
    };
  }, [caseData.id, reloadKey]);

  const closed = caseData.status === "CLOSED";

  async function recordAssisted() {
    const ok = await run(
      () =>
        recordAssistedPatientResponse(caseData.id, {
          acknowledged,
          understood_level: level,
          confidence,
          explanationStatus,
          callbackRequested,
          note: note.trim() || undefined,
        }),
      "Patient response recorded as staff-assisted."
    );
    if (ok) {
      setNote("");
      setReloadKey((value) => value + 1);
    }
  }

  return (
    <div className="cd-section">
      <div className="cd-section-head">
        <div>
          <h3>Patient access and response</h3>
          <p>Secure one-case link. Staff-assisted responses are always attributed to staff.</p>
        </div>
      </div>
      <div className="cd-section-body">
        {error && <Alert tone="danger">{error}</Alert>}

        {!closed && (
          <div className="cd-actions">
            <button
              type="button"
              className="ui-btn ui-btn-primary"
              disabled={busy}
              onClick={async () => {
                const ok = await run(async () => {
                  const link = await generatePatientLink(caseData.id);
                  setGenerated({
                    token: link.token,
                    url: link.url,
                    expiresAt: link.expiresAt,
                    sms: link.sms
                      ? { to: link.sms.to, status: link.sms.status, simulated: link.sms.simulated }
                      : null,
                  });
                  setReloadKey((value) => value + 1);
                  return link;
                }, "Secure patient link generated.");
                if (!ok) setGenerated(null);
              }}
            >
              Generate / resend secure link
            </button>
          </div>
        )}

        <div className="cd-actions">
          <button
            type="button"
            className="ui-btn ui-btn-teal"
            disabled={previewBusy}
            onClick={() => void openPreview()}
            title="Open the exact page the patient will see (preview only)"
          >
            {previewBusy ? "Opening preview…" : "Preview patient view"}
          </button>
          <span className="cd-small">
            Opens the live patient page in a new tab. Preview only — no SMS is sent.
          </span>
        </div>

        {generated && (
          <Alert tone="success" title="Link generated — show it once">
            <div className="cd-list">
              <span className="cd-code">{generated.url}</span>
              <div className="cd-inline">
                <button
                  type="button"
                  className="ui-btn ui-btn-secondary ui-btn-sm"
                  onClick={() => void navigator.clipboard?.writeText(generated.url)}
                >
                  Copy link
                </button>
                <a
                  className="ui-btn ui-btn-teal ui-btn-sm"
                  href={`/p/${generated.token}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open patient view
                </a>
                <span className="cd-small">Expires {formatDateTime(generated.expiresAt)}</span>
              </div>
              {generated.sms ? (
                <p className="cd-small" style={{ marginTop: 8 }}>
                  <strong>SMS {generated.sms.status.toLowerCase()}</strong> to{" "}
                  {generated.sms.to}
                  {generated.sms.simulated ? " (simulated delivery — no SMS gateway)" : ""}.
                </p>
              ) : (
                <p className="cd-small" style={{ marginTop: 8 }}>
                  No phone number on file, so no SMS was sent. Register the patient
                  with a mobile number to deliver the link by SMS.
                </p>
              )}
            </div>
          </Alert>
        )}

        <div className="cd-list">
          {links.length === 0 && <p className="cd-empty">No patient links generated yet.</p>}
          {links.map((link) => (
            <div className="cd-item" key={link.id}>
              <div className="cd-item-head">
                <span className="cd-item-title">Link {link.id.slice(0, 8)}</span>
                <span className="ui-badge ui-badge-neutral">{humanize(link.status)}</span>
              </div>
              <div className="cd-item-meta">
                <span>Created {formatDateTime(link.createdAt)}</span>
                <span>Expires {formatDateTime(link.expiresAt)}</span>
                <span>Failed attempts {link.failedAttempts}</span>
                {link.verifiedAt && <span>Verified {formatDateTime(link.verifiedAt)}</span>}
                {link.deliveredTo && (
                  <span>
                    SMS {humanize(link.deliveryStatus ?? "sent")} to {link.deliveredTo}
                  </span>
                )}
                {link.deliveredAt && <span>Sent {formatDateTime(link.deliveredAt)}</span>}
              </div>
            </div>
          ))}
        </div>

        <div className="cd-divider" />
        <h4 className="cd-item-title">Responses</h4>
        <div className="cd-list">
          {responses.length === 0 && <p className="cd-empty">No patient responses yet.</p>}
          {responses.map((response) => (
            <div className="cd-item" key={response.id}>
              <div className="cd-item-head">
                <span className="cd-item-title">{humanize(response.kind)}</span>
                <span className="ui-badge ui-badge-neutral">
                  {response.source === "STAFF_ASSISTED" ? "Staff-assisted" : "Patient link"}
                </span>
              </div>
              <div className="cd-field-value" style={{ marginTop: 4 }}>
                {JSON.stringify(response.value)}
              </div>
              <div className="cd-item-meta">
                <span>{formatDateTime(response.recordedAt)}</span>
                {response.recordedBy && <span>by {response.recordedBy.displayName}</span>}
                {response.note && <span>{response.note}</span>}
              </div>
            </div>
          ))}
        </div>

        {!closed && (
          <>
            <div className="cd-divider" />
            <h4 className="cd-item-title">Record a response by phone or in person</h4>
            <p className="cd-small">
              The patient could not use the link. This is recorded as staff-assisted, never as
              the patient's own submission.
            </p>
            <div className="cd-form">
              <label className="ui-checkbox cd-form-full">
                <input
                  type="checkbox"
                  checked={acknowledged}
                  onChange={(event) => setAcknowledged(event.target.checked)}
                />
                <span>Patient acknowledged the result</span>
              </label>
              <div className="ui-field">
                <label>Understanding</label>
                <select
                  value={level}
                  onChange={(event) => setLevel(event.target.value as UnderstandingLevel)}
                >
                  <option value="YES">Yes — understood</option>
                  <option value="PARTLY">Partly</option>
                  <option value="NO">No</option>
                </select>
              </div>
              <div className="ui-field">
                <label>Confidence (1–5)</label>
                <select
                  value={confidence}
                  onChange={(event) => setConfidence(Number(event.target.value))}
                >
                  {[1, 2, 3, 4, 5].map((rating) => (
                    <option key={rating} value={rating}>
                      {rating}
                    </option>
                  ))}
                </select>
              </div>
              <div className="ui-field">
                <label>Explanation</label>
                <select
                  value={explanationStatus}
                  onChange={(event) =>
                    setExplanationStatus(event.target.value as "EXPLAINED" | "NOT_EXPLAINED")
                  }
                >
                  <option value="EXPLAINED">Explained</option>
                  <option value="NOT_EXPLAINED">Not explained</option>
                </select>
              </div>
              <label className="ui-checkbox cd-form-full">
                <input
                  type="checkbox"
                  checked={callbackRequested}
                  onChange={(event) => setCallbackRequested(event.target.checked)}
                />
                <span>Patient asked for a call-back</span>
              </label>
              <div className="ui-field cd-form-full">
                <label>Note</label>
                <textarea rows={2} value={note} onChange={(event) => setNote(event.target.value)} />
              </div>
            </div>
            <div className="cd-actions">
              <button type="button" className="ui-btn ui-btn-primary" disabled={busy} onClick={recordAssisted}>
                Record staff-assisted response
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ confirmation and results (T10, T11)

export function ConfirmationPanel({ caseData, busy, run }: PanelProps) {
  const { activeUser } = useUser();
  const [results, setResults] = useState<ResultRecord[]>([]);
  const [testCode, setTestCode] = useState("");
  const [testName, setTestName] = useState("");
  const [value, setValue] = useState("");
  const [abnormal, setAbnormal] = useState(false);
  const [outcome, setOutcome] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    listResults(caseData.id)
      .then(setResults)
      .catch(() => setResults([]));
  }, [caseData.id, reloadKey]);

  const confirmatory = results.filter((row) => row.kind === "CONFIRMATORY");
  const isClinician =
    activeUser?.role === "referring_clinician" || activeUser?.role === "receiving_clinician";

  async function addConfirmatory() {
    setError("");
    if (!testCode.trim() || !value.trim()) {
      setError("Test code and result value are required.");
      return;
    }
    const ok = await run(
      () =>
        addResult(caseData.id, {
          kind: "CONFIRMATORY",
          testCode: testCode.trim(),
          testName: testName.trim() || undefined,
          value: value.trim(),
          abnormal,
        }),
      "Confirmatory result stored."
    );
    if (ok) {
      setTestCode("");
      setTestName("");
      setValue("");
      setAbnormal(false);
      setReloadKey((key) => key + 1);
    }
  }

  return (
    <div className="cd-section">
      <div className="cd-section-head">
        <div>
          <h3>Confirmatory test</h3>
          <p>A confirmatory result must be stored before T10 or T11 can proceed.</p>
        </div>
      </div>
      <div className="cd-section-body">
        {error && <Alert tone="danger">{error}</Alert>}

        <div className="cd-list">
          {confirmatory.length === 0 && <p className="cd-empty">No confirmatory result stored.</p>}
          {confirmatory.map((row) => (
            <div className="cd-item" key={row.id}>
              <div className="cd-item-head">
                <span className="cd-item-title">{row.testName ?? row.testCode}</span>
                <span className={`ui-badge ${row.abnormal ? "ui-badge-danger" : "ui-badge-success"}`}>
                  {row.abnormal ? "Abnormal" : "Normal"}
                </span>
              </div>
              <div className="cd-field-value" style={{ marginTop: 4 }}>
                {row.value}
              </div>
              <div className="cd-item-meta">
                <span>{row.testCode}</span>
                <span>{formatDateTime(row.receivedAt)}</span>
                <span>{row.source}</span>
              </div>
            </div>
          ))}
        </div>

        {caseData.status !== "CLOSED" && (
          <div className="cd-form">
            <div className="ui-field">
              <label>Test code</label>
              <input value={testCode} onChange={(event) => setTestCode(event.target.value)} />
            </div>
            <div className="ui-field">
              <label>Test name</label>
              <input value={testName} onChange={(event) => setTestName(event.target.value)} />
            </div>
            <div className="ui-field">
              <label>Result value</label>
              <input value={value} onChange={(event) => setValue(event.target.value)} />
            </div>
            <label className="ui-checkbox">
              <input
                type="checkbox"
                checked={abnormal}
                onChange={(event) => setAbnormal(event.target.checked)}
              />
              <span>Abnormal</span>
            </label>
            <div className="cd-actions cd-form-full">
              <button type="button" className="ui-btn ui-btn-primary" disabled={busy} onClick={addConfirmatory}>
                Store confirmatory result
              </button>
            </div>
          </div>
        )}

        {confirmatory.length > 0 && isClinician && caseData.status !== "CLOSED" && (
          <>
            <div className="cd-divider" />
            <div className="cd-form">
              <div className="ui-field">
                <label>Outcome (for "no further care", T11)</label>
                <input
                  value={outcome}
                  onChange={(event) => setOutcome(event.target.value)}
                  placeholder="e.g. Abnormal result excluded"
                />
              </div>
              <div className="ui-field">
                <label>Reason</label>
                <input value={reason} onChange={(event) => setReason(event.target.value)} />
              </div>
              <div className="cd-actions cd-form-full">
                <button
                  type="button"
                  className="ui-btn ui-btn-secondary"
                  disabled={busy || !outcome.trim() || !reason.trim()}
                  onClick={() =>
                    run(
                      () => recordConfirmatoryOutcome(caseData.id, outcome.trim(), reason.trim()),
                      "Confirmatory outcome recorded; case is ready to close."
                    )
                  }
                >
                  No further care needed (T11)
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ referrals (T9, T10, T12, T13)

export function ReferralPanel({ caseData, busy, run }: PanelProps) {
  const { activeUser } = useUser();
  const [referral, setReferral] = useState<ReferralRecord | null>(null);
  const [facilities, setFacilities] = useState<{ id: string; name: string }[]>([]);
  const [receivingFacilityId, setReceivingFacilityId] = useState("");
  const [receivingClinicianId, setReceivingClinicianId] = useState("");
  const [reason, setReason] = useState("");
  const [targetSpecialty, setTargetSpecialty] = useState(caseData.requiredSpecialty ?? "");
  const [declineCode, setDeclineCode] = useState<DeclineCode>("NO_CAPACITY");
  const [declineReason, setDeclineReason] = useState("");
  const [reassignFacilityId, setReassignFacilityId] = useState("");
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  const { staff } = useStaff({ role: "RECEIVING_CLINICIAN" });

  useEffect(() => {
    let cancelled = false;
    listReferrals({ caseId: caseData.id, pageSize: 20 })
      .then((page) => {
        if (!cancelled) setReferral(page.items[0] ?? null);
      })
      .catch(() => {
        if (!cancelled) setReferral(null);
      });
    listFacilities()
      .then((rows) => {
        if (!cancelled) setFacilities(rows.map((row) => ({ id: row.id, name: row.name })));
      })
      .catch(() => {
        if (!cancelled) setFacilities([]);
      });
    return () => {
      cancelled = true;
    };
  }, [caseData.id, reloadKey]);

  const isReferring = activeUser?.role === "referring_clinician";
  const isReceiving = activeUser?.role === "receiving_clinician";
  const canCoordinate = activeUser?.role === "coordinator" || activeUser?.role === "national_admin";
  const canStartReferral =
    isReferring || isReceiving || activeUser?.role === "national_admin";

  const canCreate =
    canStartReferral &&
    (caseData.status === "AWAITING_ACK" ||
      caseData.status === "AWAITING_CONFIRMATION" ||
      caseData.status === "REFERRAL_PENDING") &&
    (!referral || referral.status === "DECLINED" || referral.status === "NOT_ACCEPTED_IN_TIME");

  const facilityClinicians = staff.filter(
    (person) => !receivingFacilityId || person.facilityId === receivingFacilityId
  );

  async function create() {
    setError("");
    if (!receivingFacilityId) {
      setError("Choose the receiving facility.");
      return;
    }
    const ok = await run(
      () =>
        createReferral({
          caseId: caseData.id,
          receivingFacilityId,
          receivingClinicianId: receivingClinicianId || undefined,
          reason: reason.trim() || undefined,
          targetSpecialty: targetSpecialty.trim() || undefined,
        }),
      "Referral sent (T9/T10)."
    );
    if (ok) setReloadKey((key) => key + 1);
  }

  return (
    <div className="cd-section">
      <div className="cd-section-head">
        <div>
          <h3>Referral</h3>
          <p>Sent → accepted (T12) or declined (T13). Every decision is logged.</p>
        </div>
        {referral && (
          <span
            className={`ui-badge ${
              referral.status === "ACCEPTED"
                ? "ui-badge-success"
                : referral.status === "SENT"
                  ? "ui-badge-warning"
                  : "ui-badge-danger"
            }`}
          >
            {humanize(referral.status)}
          </span>
        )}
      </div>
      <div className="cd-section-body">
        {error && <Alert tone="danger">{error}</Alert>}

        {referral ? (
          <>
            <div className="cd-grid">
              {field("Referring facility", referral.referringFacility?.name)}
              {field("Receiving facility", referral.receivingFacility?.name ?? "Not chosen")}
              {field("Receiving clinician", referral.receivingClinician?.displayName ?? "Not assigned")}
              {field("Target specialty", referral.targetSpecialty ?? "—")}
              {field("Reason", referral.reason ?? "—")}
              {field("Referred by", referral.referredBy?.displayName ?? "—")}
              {field("Sent at", formatDateTime(referral.createdAt))}
              {field("Decided at", formatDateTime(referral.decidedAt))}
              {referral.declineCode && field("Decline code", humanize(referral.declineCode))}
              {referral.declineReason && field("Decline reason", referral.declineReason)}
              {referral.escalated && field("Escalated", formatDateTime(referral.escalatedAt))}
            </div>

            {referral.status === "SENT" && isReceiving && (
              <>
                <Alert tone="info" title="Clinical decision required">
                  Accepting moves the case to awaiting appointment. Declining needs a reason code.
                </Alert>
                <div className="cd-form">
                  <div className="ui-field">
                    <label>Decline code</label>
                    <select
                      value={declineCode}
                      onChange={(event) => setDeclineCode(event.target.value as DeclineCode)}
                    >
                      {DECLINE_CODES.map((code) => (
                        <option key={code} value={code}>
                          {humanize(code)}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="ui-field">
                    <label>Decline reason</label>
                    <input
                      value={declineReason}
                      onChange={(event) => setDeclineReason(event.target.value)}
                    />
                  </div>
                  <div className="cd-actions cd-form-full">
                    <button
                      type="button"
                      className="ui-btn ui-btn-teal"
                      disabled={busy}
                      onClick={() =>
                        run(() => acceptReferral(referral.id), "Referral accepted (T12).").then(() =>
                          setReloadKey((key) => key + 1)
                        )
                      }
                    >
                      Accept referral
                    </button>
                    <button
                      type="button"
                      className="ui-btn ui-btn-danger"
                      disabled={busy || !declineReason.trim()}
                      onClick={() =>
                        run(
                          () =>
                            declineReferral(referral.id, {
                              code: declineCode,
                              reason: declineReason.trim(),
                            }),
                          "Referral declined (T13)."
                        ).then(() => setReloadKey((key) => key + 1))
                      }
                    >
                      Decline referral
                    </button>
                  </div>
                </div>
              </>
            )}

            {referral.status === "SENT" && canCoordinate && (
              <div className="cd-form">
                <div className="ui-field">
                  <label>Reassign to another facility</label>
                  <select
                    value={reassignFacilityId}
                    onChange={(event) => setReassignFacilityId(event.target.value)}
                  >
                    <option value="">Select a facility</option>
                    {facilities
                      .filter((facility) => facility.id !== referral.receivingFacility?.id)
                      .map((facility) => (
                        <option key={facility.id} value={facility.id}>
                          {facility.name}
                        </option>
                      ))}
                  </select>
                </div>
                <div className="cd-actions">
                  <button
                    type="button"
                    className="ui-btn ui-btn-secondary"
                    disabled={busy || !reassignFacilityId}
                    onClick={() =>
                      run(
                        () =>
                          reassignReferral(
                            referral.id,
                            reassignFacilityId,
                            "Routing to another facility"
                          ),
                        "Referral reassigned."
                      ).then(() => setReloadKey((key) => key + 1))
                    }
                  >
                    Reassign
                  </button>
                  <button
                    type="button"
                    className="ui-btn ui-btn-secondary"
                    disabled={busy}
                    onClick={() =>
                      run(
                        () =>
                          markReferralNotAccepted(referral.id),
                        "Referral marked not accepted in time."
                      ).then(() => setReloadKey((key) => key + 1))
                    }
                  >
                    Mark not accepted
                  </button>
                </div>
              </div>
            )}
          </>
        ) : (
          <p className="cd-muted">No referral has been sent for this case.</p>
        )}

        {canCreate && (
          <>
            <div className="cd-divider" />
            <h4 className="cd-item-title">
              {referral ? "Send a new referral" : "Send referral (T9/T10)"}
            </h4>
            <div className="cd-form">
              <div className="ui-field">
                <label>Receiving facility</label>
                <select
                  value={receivingFacilityId}
                  onChange={(event) => {
                    setReceivingFacilityId(event.target.value);
                    setReceivingClinicianId("");
                  }}
                >
                  <option value="">Select a facility</option>
                  {facilities.map((facility) => (
                    <option key={facility.id} value={facility.id}>
                      {facility.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="ui-field">
                <label>Receiving clinician (optional)</label>
                <select
                  value={receivingClinicianId}
                  onChange={(event) => setReceivingClinicianId(event.target.value)}
                >
                  <option value="">Unassigned — facility to assign</option>
                  {facilityClinicians.map((person) => (
                    <option key={person.id} value={person.id}>
                      {person.displayName}
                      {person.specialty ? ` — ${person.specialty}` : ""}
                    </option>
                  ))}
                </select>
              </div>
              <div className="ui-field">
                <label>Target specialty</label>
                <input
                  value={targetSpecialty}
                  onChange={(event) => setTargetSpecialty(event.target.value)}
                />
              </div>
              <div className="ui-field cd-form-full">
                <label>Reason</label>
                <textarea rows={2} value={reason} onChange={(event) => setReason(event.target.value)} />
              </div>
              <div className="cd-actions cd-form-full">
                <button type="button" className="ui-btn ui-btn-primary" disabled={busy} onClick={create}>
                  Send referral
                </button>
              </div>
            </div>
          </>
        )}

        {!canCreate && !referral && canStartReferral && (
          <p className="cd-small">
            A referral can be started once the patient has acknowledged the result
            (AWAITING_ACK) or the confirmatory result has been received
            (AWAITING_CONFIRMATION).
          </p>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ appointments and treatment (T14, T15, R-47, R-48)

export function AppointmentPanel({ caseData, busy, run }: PanelProps) {
  const [appointments, setAppointments] = useState<AppointmentRecord[]>([]);
  const [starts, setStarts] = useState<TreatmentStartRecord[]>([]);
  const [scheduledAt, setScheduledAt] = useState("");
  const [missedCode, setMissedCode] = useState<DelayReasonCode>("PATIENT_UNREACHABLE");
  const [attendanceNote, setAttendanceNote] = useState("");
  const [kind, setKind] = useState<"TREATMENT" | "MONITORING">("TREATMENT");
  const [startDate, setStartDate] = useState("");
  const [startNote, setStartNote] = useState("");
  const [attachmentRef, setAttachmentRef] = useState("");
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    listAppointments(caseData.id)
      .then((rows) => {
        if (!cancelled) setAppointments(rows);
      })
      .catch(() => {
        if (!cancelled) setAppointments([]);
      });
    listTreatmentStarts(caseData.id)
      .then((rows) => {
        if (!cancelled) setStarts(rows);
      })
      .catch(() => {
        if (!cancelled) setStarts([]);
      });
    return () => {
      cancelled = true;
    };
  }, [caseData.id, reloadKey]);

  const booked = appointments.find((appointment) => appointment.attendance === "BOOKED");

  async function book() {
    setError("");
    if (!scheduledAt) {
      setError("Choose the appointment date and time.");
      return;
    }
    const ok = await run(
      () => bookAppointment(caseData.id, new Date(scheduledAt).toISOString()),
      "Appointment booked."
    );
    if (ok) setReloadKey((key) => key + 1);
  }

  async function markAttendance(appointment: AppointmentRecord, attendance: "ATTENDED" | "MISSED") {
    setError("");
    if (attendance === "MISSED" && !missedCode) {
      setError("A missed appointment needs a reason code.");
      return;
    }
    const ok = await run(
      () =>
        recordAttendance(
          caseData.id,
          appointment.id,
          attendance,
          attendance === "MISSED" ? missedCode : undefined,
          attendanceNote.trim() || undefined
        ),
      attendance === "ATTENDED" ? "Attendance recorded (T14)." : "Missed appointment recorded."
    );
    if (ok) {
      setAttendanceNote("");
      setReloadKey((key) => key + 1);
    }
  }

  async function recordStart() {
    setError("");
    if (!startDate) {
      setError("Choose a start date.");
      return;
    }
    if (!startNote.trim() && !attachmentRef.trim()) {
      setError("Add a note or a document reference to the start record.");
      return;
    }
    const ok = await run(
      () =>
        recordTreatmentStart(caseData.id, {
          kind,
          startDate: new Date(startDate).toISOString(),
          note: startNote.trim() || undefined,
          attachmentRef: attachmentRef.trim() || undefined,
        }),
      "Treatment or monitoring start recorded (T15)."
    );
    if (ok) {
      setStartNote("");
      setAttachmentRef("");
      setReloadKey((key) => key + 1);
    }
  }

  return (
    <div className="cd-section">
      <div className="cd-section-head">
        <div>
          <h3>Appointments and treatment</h3>
          <p>Attendance moves the case on. Missed appointments need a reason and a rebooking.</p>
        </div>
      </div>
      <div className="cd-section-body">
        {error && <Alert tone="danger">{error}</Alert>}

        <div className="cd-list">
          {appointments.length === 0 && <p className="cd-empty">No appointments recorded.</p>}
          {appointments.map((appointment) => (
            <div className="cd-item" key={appointment.id}>
              <div className="cd-item-head">
                <span className="cd-item-title">{formatDateTime(appointment.scheduledAt)}</span>
                <span className="ui-badge ui-badge-neutral">{humanize(appointment.attendance)}</span>
              </div>
              {appointment.attendance === "BOOKED" && caseData.status !== "CLOSED" && (
                <div className="cd-form" style={{ marginTop: 8 }}>
                  <div className="ui-field">
                    <label>If missed, reason code</label>
                    <select
                      value={missedCode}
                      onChange={(event) => setMissedCode(event.target.value as DelayReasonCode)}
                    >
                      {DELAY_CODES.map((code) => (
                        <option key={code} value={code}>
                          {humanize(code)}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="ui-field">
                    <label>Note</label>
                    <input
                      value={attendanceNote}
                      onChange={(event) => setAttendanceNote(event.target.value)}
                    />
                  </div>
                  <div className="cd-actions cd-form-full">
                    <button
                      type="button"
                      className="ui-btn ui-btn-teal"
                      disabled={busy}
                      onClick={() => markAttendance(appointment, "ATTENDED")}
                    >
                      Record attended (T14)
                    </button>
                    <button
                      type="button"
                      className="ui-btn ui-btn-secondary"
                      disabled={busy}
                      onClick={() => markAttendance(appointment, "MISSED")}
                    >
                      Record missed
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>

        {caseData.status === "AWAITING_APPOINTMENT" && !booked && (
          <div className="cd-form">
            <div className="ui-field">
              <label>Book appointment</label>
              <input
                type="datetime-local"
                value={scheduledAt}
                onChange={(event) => setScheduledAt(event.target.value)}
              />
            </div>
            <div className="cd-actions">
              <button type="button" className="ui-btn ui-btn-primary" disabled={busy} onClick={book}>
                Book appointment
              </button>
            </div>
          </div>
        )}

        <div className="cd-divider" />
        <h4 className="cd-item-title">Treatment or monitoring start</h4>
        <div className="cd-list">
          {starts.length === 0 && <p className="cd-empty">No start record attached.</p>}
          {starts.map((start) => (
            <div className="cd-item" key={start.id}>
              <div className="cd-item-head">
                <span className="cd-item-title">
                  {humanize(start.kind)} — {formatDateOnly(start.startDate)}
                </span>
                <span className="cd-item-meta">{formatDateTime(start.recordedAt)}</span>
              </div>
              <div className="cd-field-value" style={{ marginTop: 4 }}>
                {start.note ?? start.attachmentRef ?? "—"}
              </div>
            </div>
          ))}
        </div>

        {caseData.status === "AWAITING_TREATMENT" && (
          <div className="cd-form">
            <div className="ui-field">
              <label>Type</label>
              <select
                value={kind}
                onChange={(event) => setKind(event.target.value as "TREATMENT" | "MONITORING")}
              >
                <option value="TREATMENT">Treatment</option>
                <option value="MONITORING">Monitoring</option>
              </select>
            </div>
            <div className="ui-field">
              <label>Start date</label>
              <input
                type="date"
                value={startDate}
                onChange={(event) => setStartDate(event.target.value)}
              />
            </div>
            <div className="ui-field">
              <label>Note</label>
              <input value={startNote} onChange={(event) => setStartNote(event.target.value)} />
            </div>
            <div className="ui-field">
              <label>Document reference</label>
              <input
                value={attachmentRef}
                onChange={(event) => setAttachmentRef(event.target.value)}
              />
            </div>
            <div className="cd-actions cd-form-full">
              <button type="button" className="ui-btn ui-btn-primary" disabled={busy} onClick={recordStart}>
                Record start (T15)
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ closure (T16, T17, R-53, R-54)

export function ClosurePanel({ caseData, busy, run }: PanelProps) {
  const { activeUser } = useUser();
  const validTypes = (caseData.validClosureTypes.length
    ? caseData.validClosureTypes
    : [
        "CARE_CONFIRMED",
        "NOT_ACTIONABLE",
        "NO_FURTHER_CARE",
        "PATIENT_DECLINED",
        "UNREACHABLE",
        "MOVED_OR_TRANSFERRED",
        "OTHER",
      ]) as ClosureType[];
  const defaultType = validTypes.includes("CARE_CONFIRMED") ? "CARE_CONFIRMED" : validTypes[0];

  const [closureType, setClosureType] = useState<ClosureType>(defaultType ?? "CARE_CONFIRMED");
  const [reason, setReason] = useState("");
  const [decision, setDecision] = useState("");
  const [evidence, setEvidence] = useState("");
  const [secondApproverId, setSecondApproverId] = useState("");
  const [checklist, setChecklist] = useState<ClosureChecklist | null>(null);
  const [error, setError] = useState("");
  const [pendingSignOff, setPendingSignOff] = useState(false);
  const [linkedCaseNumber, setLinkedCaseNumber] = useState("");
  const [linkedReason, setLinkedReason] = useState("");
  const { staff: approvers } = useClosureApprovers();

  const closed = caseData.status === "CLOSED";

  async function check() {
    setError("");
    try {
      const result = await getClosureChecklist(caseData.id, closureType, {
        reason: reason.trim() || undefined,
        decision: decision.trim() || undefined,
        evidence: evidence.trim() || undefined,
      });
      setChecklist(result);
    } catch (err) {
      setError(messageText(err, "Unable to load the closure checklist."));
    }
  }

  async function submit() {
    setError("");
    if (!reason.trim()) {
      setError("A reason is required for every closure.");
      return;
    }
    if (closureType === "OTHER" && !secondApproverId) {
      setError("Select a second authorised person for an OTHER closure.");
      return;
    }
    const ok = await run(
      async () => {
        const result = await closeCase(caseData.id, {
          closureType,
          reason: reason.trim(),
          decision: decision.trim() || undefined,
          evidence: evidence.trim() || undefined,
          secondApproverId: closureType === "OTHER" ? secondApproverId : undefined,
        });
        setPendingSignOff(result.pendingSignOff);
        return result;
      },
      closureType === "OTHER"
        ? "Closure requested; a second authorised person must sign off."
        : "Case closed."
    );
    if (ok) void check();
  }

  if (closed) {
    return (
      <div className="cd-section">
        <div className="cd-section-head">
          <div>
            <h3>Closed case</h3>
            <p>Closed cases are read-only. Start a new linked case for further care (R-56).</p>
          </div>
          <span className="ui-badge ui-badge-success">Closed</span>
        </div>
        <div className="cd-section-body">
          <div className="cd-grid">
            {field("Closure type", humanize(caseData.closureType))}
            {field("Closed at", formatDateTime(caseData.closedAt))}
            {field("Reason", caseData.closure?.reason ?? "—")}
            {field("Closed by", caseData.closure?.closedByName ?? caseData.closure?.closedById ?? "—")}
            {field(
              "Second sign-off",
              caseData.closure?.secondSignOffById ? "Recorded" : caseData.closure?.secondApproverId ? "Pending" : "Not required"
            )}
          </div>
          <div className="cd-divider" />
          <div className="cd-form">
            <div className="ui-field">
              <label>New linked case number</label>
              <input
                value={linkedCaseNumber}
                onChange={(event) => setLinkedCaseNumber(event.target.value)}
                placeholder="e.g. CASE-2026-0002"
              />
            </div>
            <div className="ui-field">
              <label>Reason for the new case</label>
              <input
                value={linkedReason}
                onChange={(event) => setLinkedReason(event.target.value)}
              />
            </div>
            <div className="cd-actions cd-form-full">
              <button
                type="button"
                className="ui-btn ui-btn-primary"
                disabled={busy || !linkedCaseNumber.trim() || !linkedReason.trim()}
                onClick={() =>
                  run(
                    () =>
                      startLinkedCase(caseData.id, linkedCaseNumber.trim(), linkedReason.trim()),
                    "Linked case started."
                  )
                }
              >
                Start linked case
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="cd-section">
      <div className="cd-section-head">
        <div>
          <h3>Close this case</h3>
          <p>Only a person closes a case. Evidence rules depend on the closure type (A-01).</p>
        </div>
      </div>
      <div className="cd-section-body">
        {caseData.flags.includes("DATA_MISSING") && (
          <Alert tone="warning" title="Data missing">
            This case cannot be closed while a facility feed is missing or incomplete (R-14).
          </Alert>
        )}
        {error && <Alert tone="danger">{error}</Alert>}

        <div className="cd-form">
          <div className="ui-field">
            <label>Closure type</label>
            <select
              value={closureType}
              onChange={(event) => {
                setClosureType(event.target.value as ClosureType);
                setChecklist(null);
              }}
            >
              {validTypes.map((type) => (
                <option key={type} value={type}>
                  {humanize(type)}
                </option>
              ))}
            </select>
          </div>
          <div className="ui-field cd-form-full">
            <label>Reason (required)</label>
            <textarea rows={2} value={reason} onChange={(event) => setReason(event.target.value)} />
          </div>
          <div className="ui-field cd-form-full">
            <label>Clinician decision (where required)</label>
            <textarea rows={2} value={decision} onChange={(event) => setDecision(event.target.value)} />
          </div>
          <div className="ui-field cd-form-full">
            <label>Evidence / documented hand-off (where required)</label>
            <textarea rows={2} value={evidence} onChange={(event) => setEvidence(event.target.value)} />
          </div>
          {closureType === "OTHER" && (
            <div className="ui-field cd-form-full">
              <label>Second authorised person</label>
              <select
                value={secondApproverId}
                onChange={(event) => setSecondApproverId(event.target.value)}
              >
                <option value="">Select a person</option>
                {approvers
                  .filter((person) => person.id !== activeUser?.id)
                  .map((person) => (
                    <option key={person.id} value={person.id}>
                      {person.displayName}
                    </option>
                  ))}
              </select>
            </div>
          )}
        </div>

        <div className="cd-actions">
          <button type="button" className="ui-btn ui-btn-secondary" disabled={busy} onClick={check}>
            Check evidence
          </button>
          <button type="button" className="ui-btn ui-btn-danger" disabled={busy} onClick={submit}>
            Close case ({caseData.status === "READY_TO_CLOSE" ? "T16" : "T17"})
          </button>
        </div>

        {checklist && (
          <div className="cd-check-list">
            {checklist.items.map((item) => (
              <div className="cd-check" key={item.item}>
                <span
                  className={`cd-check-mark ${
                    item.present ? "cd-check-ok" : "cd-check-missing"
                  }`}
                >
                  {item.present ? "✓" : "✗"}
                </span>
                <span>{item.item}</span>
              </div>
            ))}
            <p className="cd-small">
              {checklist.complete ? "Evidence complete." : "Evidence is not yet complete."}{" "}
              {checklist.canClose ? "You are authorised for this closure." : "You are not authorised for this closure type."}
            </p>
          </div>
        )}

        {pendingSignOff && (
          <Alert tone="info" title="Waiting for a second signature">
            The selected approver must sign off.{" "}
            {secondApproverId === activeUser?.id && (
              <button
                type="button"
                className="cd-link"
                onClick={() =>
                  run(() => signOffClosure(caseData.id), "Closure signed off; case closed.")
                }
              >
                Sign off now
              </button>
            )}
          </Alert>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ flags, contact, ownership, transfer

export function AdminPanel({ caseData, busy, run }: PanelProps) {
  const { activeUser } = useUser();
  const [attempts, setAttempts] = useState<ContactAttemptRecord[]>([]);
  const [route, setRoute] = useState<ContactRoute>("PHONE");
  const [outcome, setOutcome] = useState<"REACHED" | "NOT_REACHED">("NOT_REACHED");
  const [note, setNote] = useState("");
  const [delayCode, setDelayCode] = useState<DelayReasonCode>("PATIENT_UNREACHABLE");
  const [delayNote, setDelayNote] = useState("");
  const [explainedNote, setExplainedNote] = useState("");
  const [facilities, setFacilities] = useState<{ id: string; name: string }[]>([]);
  const [newFacilityId, setNewFacilityId] = useState("");
  const [transferReason, setTransferReason] = useState("");
  const [ownerId, setOwnerId] = useState(caseData.owner?.id ?? "");
  const [reloadKey, setReloadKey] = useState(0);
  const { staff } = useStaff({ facilityId: caseData.facility.id });

  useEffect(() => {
    let cancelled = false;
    listContactAttempts(caseData.id)
      .then((rows) => {
        if (!cancelled) setAttempts(rows);
      })
      .catch(() => {
        if (!cancelled) setAttempts([]);
      });
    listFacilities()
      .then((rows) => {
        if (!cancelled) setFacilities(rows.map((row) => ({ id: row.id, name: row.name })));
      })
      .catch(() => {
        if (!cancelled) setFacilities([]);
      });
    return () => {
      cancelled = true;
    };
  }, [caseData.id, reloadKey]);

  const canCoordinate = activeUser?.role === "coordinator" || activeUser?.role === "national_admin";
  const closed = caseData.status === "CLOSED";
  const ownerOptions = staff.filter((person) =>
    ["COORDINATOR", "REFERRING_CLINICIAN", "RECEIVING_CLINICIAN"].includes(person.role)
  );

  async function addAttempt() {
    const ok = await run(
      () =>
        addContactAttempt(caseData.id, {
          route,
          outcome,
          note: note.trim() || undefined,
        }),
      "Contact attempt logged."
    );
    if (ok) {
      setNote("");
      setReloadKey((key) => key + 1);
    }
  }

  return (
    <div className="cd-section">
      <div className="cd-section-head">
        <div>
          <h3>Flags, contact and ownership</h3>
          <p>Handling flags is auditable. Contact attempts support the UNREACHABLE closure rule.</p>
        </div>
      </div>
      <div className="cd-section-body">
        <div className="cd-inline">
          <FlagBadges flags={caseData.flags} />
        </div>

        {!closed && canCoordinate && (
          <div className="cd-form">
            <div className="ui-field">
              <label>Owner</label>
              <select value={ownerId} onChange={(event) => setOwnerId(event.target.value)}>
                <option value="">Unassigned</option>
                {ownerOptions.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.displayName} — {humanize(person.role)}
                  </option>
                ))}
              </select>
            </div>
            <div className="cd-actions">
              <button
                type="button"
                className="ui-btn ui-btn-secondary"
                disabled={busy || !ownerId || ownerId === caseData.owner?.id}
                onClick={() =>
                  run(() => assignCase(caseData.id, ownerId), "Owner assigned.")
                }
              >
                Assign owner
              </button>
            </div>
          </div>
        )}

        {caseData.flags.includes("OVERDUE") && (
          <div className="cd-form">
            <div className="ui-field">
              <label>Reason for delay (clears OVERDUE)</label>
              <select
                value={delayCode}
                onChange={(event) => setDelayCode(event.target.value as DelayReasonCode)}
              >
                {DELAY_CODES.map((code) => (
                  <option key={code} value={code}>
                    {humanize(code)}
                  </option>
                ))}
              </select>
            </div>
            <div className="ui-field">
              <label>Note {delayCode === "OTHER" ? "(required)" : ""}</label>
              <input value={delayNote} onChange={(event) => setDelayNote(event.target.value)} />
            </div>
            <div className="cd-actions cd-form-full">
              <button
                type="button"
                className="ui-btn ui-btn-primary"
                disabled={busy || (delayCode === "OTHER" && !delayNote.trim())}
                onClick={() =>
                  run(
                    () => recordDelayReason(caseData.id, delayCode, delayNote.trim() || undefined),
                    "Delay reason recorded; OVERDUE cleared."
                  )
                }
              >
                Record delay reason
              </button>
            </div>
          </div>
        )}

        {caseData.flags.includes("NOT_EXPLAINED") && (
          <div className="cd-form">
            <div className="ui-field cd-form-full">
              <label>Explain the result again (clears NOT_EXPLAINED)</label>
              <textarea
                rows={2}
                value={explainedNote}
                onChange={(event) => setExplainedNote(event.target.value)}
              />
            </div>
            <div className="cd-actions cd-form-full">
              <button
                type="button"
                className="ui-btn ui-btn-primary"
                disabled={busy || !explainedNote.trim()}
                onClick={() =>
                  run(
                    () => recordExplained(caseData.id, explainedNote.trim()),
                    "Explanation recorded; NOT_EXPLAINED cleared."
                  )
                }
              >
                Record explanation
              </button>
            </div>
          </div>
        )}

        {caseData.flags.includes("MESSAGE_FAILED") && (
          <div className="cd-form">
            <div className="ui-field">
              <label>Reached by another route</label>
              <select value={route} onChange={(event) => setRoute(event.target.value as ContactRoute)}>
                {CONTACT_ROUTES.map((item) => (
                  <option key={item} value={item}>
                    {humanize(item)}
                  </option>
                ))}
              </select>
            </div>
            <div className="ui-field">
              <label>Note</label>
              <input value={note} onChange={(event) => setNote(event.target.value)} />
            </div>
            <div className="cd-actions cd-form-full">
              <button
                type="button"
                className="ui-btn ui-btn-primary"
                disabled={busy}
                onClick={() =>
                  run(
                    () => confirmContact(caseData.id, route, note.trim() || undefined),
                    "Contact confirmed; MESSAGE_FAILED cleared."
                  )
                }
              >
                Confirm contact
              </button>
            </div>
          </div>
        )}

        <div className="cd-divider" />
        <h4 className="cd-item-title">Contact attempts</h4>
        <div className="cd-list">
          {attempts.length === 0 && <p className="cd-empty">No contact attempts logged.</p>}
          {attempts.map((attempt) => (
            <div className="cd-item" key={attempt.id}>
              <div className="cd-item-head">
                <span className="cd-item-title">
                  {humanize(attempt.route)} — {humanize(attempt.outcome)}
                </span>
                <span className="cd-item-meta">{formatDateTime(attempt.recordedAt)}</span>
              </div>
              {attempt.note && <div className="cd-small">{attempt.note}</div>}
            </div>
          ))}
        </div>

        {!closed && (
          <div className="cd-form">
            <div className="ui-field">
              <label>Route</label>
              <select value={route} onChange={(event) => setRoute(event.target.value as ContactRoute)}>
                {CONTACT_ROUTES.map((item) => (
                  <option key={item} value={item}>
                    {humanize(item)}
                  </option>
                ))}
              </select>
            </div>
            <div className="ui-field">
              <label>Outcome</label>
              <select
                value={outcome}
                onChange={(event) => setOutcome(event.target.value as "REACHED" | "NOT_REACHED")}
              >
                <option value="NOT_REACHED">Not reached</option>
                <option value="REACHED">Reached</option>
              </select>
            </div>
            <div className="ui-field">
              <label>Note</label>
              <input value={note} onChange={(event) => setNote(event.target.value)} />
            </div>
            <div className="cd-actions cd-form-full">
              <button type="button" className="ui-btn ui-btn-secondary" disabled={busy} onClick={addAttempt}>
                Log contact attempt
              </button>
            </div>
          </div>
        )}

        {canCoordinate && !closed && (
          <>
            <div className="cd-divider" />
            <h4 className="cd-item-title">Transfer to another facility</h4>
            <div className="cd-form">
              <div className="ui-field">
                <label>New facility</label>
                <select
                  value={newFacilityId}
                  onChange={(event) => setNewFacilityId(event.target.value)}
                >
                  <option value="">Select a facility</option>
                  {facilities
                    .filter((facility) => facility.id !== caseData.facility.id)
                    .map((facility) => (
                      <option key={facility.id} value={facility.id}>
                        {facility.name}
                      </option>
                    ))}
                </select>
              </div>
              <div className="ui-field cd-form-full">
                <label>Reason</label>
                <input
                  value={transferReason}
                  onChange={(event) => setTransferReason(event.target.value)}
                />
              </div>
              <div className="cd-actions cd-form-full">
                <button
                  type="button"
                  className="ui-btn ui-btn-danger"
                  disabled={busy || !newFacilityId || !transferReason.trim()}
                  onClick={() =>
                    run(
                      () =>
                        transferCase(caseData.id, newFacilityId, transferReason.trim()),
                      "Case transferred; history kept."
                    )
                  }
                >
                  Transfer case
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
