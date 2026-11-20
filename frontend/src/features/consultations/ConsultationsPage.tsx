import "./consultations.css";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  Clock,
  MessageSquare,
  Plus,
  RotateCcw,
  Search,
  Siren,
  X,
} from "lucide-react";
import { useSearchParams } from "react-router-dom";
import Alert from "../../components/ui/Alert";
import Pagination from "../../components/ui/Pagination";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../../components/ui/StateViews";
import { useUser } from "../../context/UserContext";
import type {
  ConsultationOutcomeType,
  ConsultationRecord,
  ConsultationState,
  ConsultationType,
} from "../../services/api/v6.types";
import {
  acceptConsultation,
  escalateConsultation,
  getConsultation,
  listConsultations,
  recordConsultationOutcome,
  replyToConsultation,
  requestConsultation,
} from "../../services/api/consultationsApi";
import { formatDateTime, humanize, initialsOf } from "../../utils/format";

const STATES: ConsultationState[] = [
  "REQUESTED",
  "ACCEPTED",
  "ESCALATED",
  "OUTCOME_RECORDED",
];

const OUTCOME_TYPES: ConsultationOutcomeType[] = [
  "ADVICE_GIVEN",
  "TEST_ORDERED",
  "REFERRAL_MADE",
  "NO_ACTION",
];

const SPECIALTIES = [
  "CARDIOLOGY",
  "ONCOLOGY",
  "RADIOLOGY",
  "PATHOLOGY",
  "GYNECOLOGY",
  "PEDIATRICS",
  "SURGERY",
  "DERMATOLOGY",
  "ENDOCRINOLOGY",
  "NEUROLOGY",
  "UROLOGY",
  "ORTHOPEDICS",
];

function stateTone(state: ConsultationState) {
  switch (state) {
    case "ACCEPTED":
      return "ui-badge ui-badge-info";
    case "ESCALATED":
      return "ui-badge ui-badge-danger";
    case "OUTCOME_RECORDED":
      return "ui-badge ui-badge-success";
    default:
      return "ui-badge ui-badge-warning";
  }
}

export default function ConsultationsPage() {
  const { activeUser } = useUser();
  const [searchParams] = useSearchParams();
  const caseId = searchParams.get("caseId") ?? "";
  const [items, setItems] = useState<ConsultationRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [state, setState] = useState<ConsultationState | "">("");
  const [type, setType] = useState<ConsultationType | "">("");
  const [mine, setMine] = useState(false);
  const [search, setSearch] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const [showRequest, setShowRequest] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await listConsultations({
        page,
        pageSize,
        state: state || undefined,
        type: type || undefined,
        caseId: caseId || undefined,
        mine,
      });
      setItems(response.items);
      setTotal(response.total);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load consultations."
      );
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, state, type, caseId, mine]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setPage(1);
  }, [state, type, mine]);

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return items;
    return items.filter((item) =>
      [
        item.caseId,
        item.question,
        item.requester?.displayName,
        item.recipient?.displayName,
        item.recipientSpecialty,
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(term))
    );
  }, [items, search]);

  const summary = useMemo(
    () => ({
      open: items.filter(
        (item) => item.state === "REQUESTED" || item.state === "ESCALATED"
      ).length,
      accepted: items.filter((item) => item.state === "ACCEPTED").length,
      callbacks: items.filter((item) => item.type === "PATIENT_CALLBACK").length,
      done: items.filter((item) => item.state === "OUTCOME_RECORDED").length,
    }),
    [items]
  );

  const hasFilters = Boolean(state || type || mine || search || caseId);
  const canRequest =
    activeUser &&
    ["coordinator", "referring_clinician", "receiving_clinician", "national_admin"].includes(
      activeUser.role
    );

  return (
    <div className="consultation-page">
      <header className="consultation-heading">
        <div>
          <span className="consultation-eyebrow">CONSULTATIONS</span>
          <h1>Consultations</h1>
          <p>
            Ask a colleague, answer a question and record the outcome. A
            consultation never changes the case status on its own.
          </p>
        </div>
        {canRequest && (
          <button
            type="button"
            className="ui-btn ui-btn-primary"
            onClick={() => setShowRequest(true)}
          >
            <Plus size={15} /> Request consultation
          </button>
        )}
      </header>

      <section className="consultation-summary">
        <button type="button" className="consultation-summary-card" onClick={() => setState("")}>
          <span>Open</span>
          <strong>{summary.open}</strong>
        </button>
        <button type="button" className="consultation-summary-card" onClick={() => setState("ACCEPTED")}>
          <span>Accepted</span>
          <strong>{summary.accepted}</strong>
        </button>
        <button type="button" className="consultation-summary-card" onClick={() => setType("PATIENT_CALLBACK")}>
          <span>Patient call-backs</span>
          <strong>{summary.callbacks}</strong>
        </button>
        <button type="button" className="consultation-summary-card" onClick={() => setState("OUTCOME_RECORDED")}>
          <span>Completed</span>
          <strong>{summary.done}</strong>
        </button>
      </section>

      <section className="consultation-toolbar">
        <label className="referral-search">
          <Search size={15} />
          <input
            type="search"
            placeholder="Search this page by case or question"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
        <select
          value={state}
          onChange={(event) => setState(event.target.value as ConsultationState | "")}
          aria-label="Filter by state"
        >
          <option value="">All states</option>
          {STATES.map((value) => (
            <option key={value} value={value}>
              {humanize(value)}
            </option>
          ))}
        </select>
        <select
          value={type}
          onChange={(event) => setType(event.target.value as ConsultationType | "")}
          aria-label="Filter by type"
        >
          <option value="">All types</option>
          <option value="CLINICIAN_TO_CLINICIAN">Clinician to clinician</option>
          <option value="PATIENT_CALLBACK">Patient call-back</option>
        </select>
        <label className="wl-checkbox">
          <input
            type="checkbox"
            checked={mine}
            onChange={(event) => setMine(event.target.checked)}
          />
          Only mine
        </label>
        {hasFilters && (
          <button
            type="button"
            className="ui-btn ui-btn-secondary ui-btn-sm"
            onClick={() => {
              setSearch("");
              setState("");
              setType("");
              setMine(false);
            }}
          >
            <RotateCcw size={13} /> Clear
          </button>
        )}
      </section>

      {error ? (
        <ErrorState message={error} onRetry={() => void load()} />
      ) : loading ? (
        <LoadingState message="Loading consultations…" />
      ) : visible.length === 0 ? (
        <EmptyState
          title="No consultations here"
          message="Ask a colleague for advice, or answer a question addressed to your specialty."
        />
      ) : (
        <>
          <div className="consultation-list">
            {visible.map((item) => (
              <article className="consultation-card" key={item.id}>
                <div className="consultation-card-top">
                  <div>
                    <h3>
                      {item.type === "PATIENT_CALLBACK"
                        ? "Patient call-back"
                        : "Clinician to clinician"}
                      {item.urgent && (
                        <span className="ui-badge ui-badge-urgent">Urgent</span>
                      )}
                    </h3>
                    <p>
                      Case {item.caseId} · {item.trackerId}
                    </p>
                  </div>
                  <span className={stateTone(item.state)}>{humanize(item.state)}</span>
                </div>
                {item.question && (
                  <p className="consultation-question">{item.question}</p>
                )}
                <div className="consultation-meta">
                  <span>
                    {item.requester?.displayName ?? "Unknown"} →{" "}
                    {item.recipient?.displayName ??
                      (item.recipientSpecialty
                        ? humanize(item.recipientSpecialty)
                        : "Any available clinician")}
                  </span>
                  <span>
                    <Clock size={12} /> Due {formatDateTime(item.dueAt)}
                  </span>
                  {item.escalationStage > 0 && (
                    <span className="consultation-escalated">
                      <Siren size={12} /> Escalated ×{item.escalationStage}
                    </span>
                  )}
                </div>
                <div className="consultation-actions">
                  <button
                    type="button"
                    className="ui-btn ui-btn-secondary ui-btn-sm"
                    onClick={() => setOpenId(item.id)}
                  >
                    <MessageSquare size={13} /> Open
                  </button>
                </div>
              </article>
            ))}
          </div>
          <Pagination page={page} pageSize={pageSize} total={total} onChange={setPage} />
        </>
      )}

      {openId && activeUser && (
        <ConsultationDrawer
          consultationId={openId}
          onClose={() => setOpenId(null)}
          onChanged={() => void load()}
        />
      )}

      {showRequest && activeUser && (
        <RequestConsultationDialog
          defaultCaseId={caseId}
          onClose={() => setShowRequest(false)}
          onCreated={() => {
            setShowRequest(false);
            void load();
          }}
        />
      )}
    </div>
  );
}

function RequestConsultationDialog({
  defaultCaseId,
  onClose,
  onCreated,
}: {
  defaultCaseId: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [caseId, setCaseId] = useState(defaultCaseId);
  const [type, setType] = useState<ConsultationType>("CLINICIAN_TO_CLINICIAN");
  const [question, setQuestion] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [preferredTime, setPreferredTime] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit() {
    setBusy(true);
    setError("");
    try {
      await requestConsultation({
        caseId: caseId.trim(),
        type,
        question: question.trim() || undefined,
        recipientSpecialty: specialty || undefined,
        preferredTime: preferredTime.trim() || undefined,
      });
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create the consultation.");
    } finally {
      setBusy(false);
    }
  }

  const valid =
    caseId.trim() &&
    (type === "PATIENT_CALLBACK" || (question.trim() && specialty));

  return (
    <div
      className="consultation-drawer-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <aside className="consultation-dialog" role="dialog" aria-modal="true">
        <div className="consultation-drawer-header">
          <div>
            <span>NEW CONSULTATION</span>
            <h2>Ask for advice</h2>
          </div>
          <button type="button" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        <div className="consultation-drawer-content">
          {error && <Alert tone="danger">{error}</Alert>}
          <div className="ui-field">
            <label>Case number or ID</label>
            <input
              value={caseId}
              onChange={(event) => setCaseId(event.target.value)}
              placeholder="e.g. JC-2026-0001"
            />
          </div>
          <div className="ui-field">
            <label>Type</label>
            <select
              value={type}
              onChange={(event) => setType(event.target.value as ConsultationType)}
            >
              <option value="CLINICIAN_TO_CLINICIAN">Clinician to clinician</option>
              <option value="PATIENT_CALLBACK">Patient call-back</option>
            </select>
          </div>
          {type === "CLINICIAN_TO_CLINICIAN" && (
            <>
              <div className="ui-field">
                <label>Question</label>
                <textarea
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  placeholder="What do you need advice on?"
                />
              </div>
              <div className="ui-field">
                <label>Recipient specialty</label>
                <input
                  list="consultation-specialties"
                  value={specialty}
                  onChange={(event) => setSpecialty(event.target.value.toUpperCase())}
                  placeholder="e.g. CARDIOLOGY"
                />
                <datalist id="consultation-specialties">
                  {SPECIALTIES.map((value) => (
                    <option key={value} value={value} />
                  ))}
                </datalist>
              </div>
            </>
          )}
          <div className="ui-field">
            <label>Preferred time (optional)</label>
            <input
              value={preferredTime}
              onChange={(event) => setPreferredTime(event.target.value)}
              placeholder="e.g. Weekday mornings"
            />
          </div>
          <div className="consultation-actions">
            <button
              type="button"
              className="ui-btn ui-btn-primary"
              disabled={busy || !valid}
              onClick={() => void submit()}
            >
              Send consultation
            </button>
            <button type="button" className="ui-btn ui-btn-secondary" onClick={onClose}>
              Cancel
            </button>
          </div>
        </div>
      </aside>
    </div>
  );
}

function ConsultationDrawer({
  consultationId,
  onClose,
  onChanged,
}: {
  consultationId: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { activeUser } = useUser();
  const [record, setRecord] = useState<ConsultationRecord | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const [reply, setReply] = useState("");
  const [escalationReason, setEscalationReason] = useState("");
  const [outcomeType, setOutcomeType] = useState<ConsultationOutcomeType>("ADVICE_GIVEN");
  const [outcomeNote, setOutcomeNote] = useState("");

  const load = useCallback(async () => {
    try {
      const detail = await getConsultation(consultationId);
      setRecord(detail);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load this consultation.");
    }
  }, [consultationId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const run = useCallback(
    async (action: () => Promise<unknown>, message: string) => {
      setBusy(true);
      setNotice(null);
      try {
        await action();
        setNotice({ tone: "success", text: message });
        await load();
        onChanged();
      } catch (err) {
        setNotice({
          tone: "danger",
          text:
            err instanceof Error
              ? err.message
              : "The action could not be completed.",
        });
      } finally {
        setBusy(false);
      }
    },
    [load, onChanged]
  );

  if (!record || !activeUser) {
    return (
      <div
        className="consultation-drawer-overlay"
        onMouseDown={(event) => {
          if (event.target === event.currentTarget) onClose();
        }}
      >
        <aside className="consultation-drawer">
          <div className="consultation-drawer-header">
            <div>
              <span>CONSULTATION</span>
              <h2>Loading…</h2>
            </div>
            <button type="button" onClick={onClose} aria-label="Close">
              <X size={16} />
            </button>
          </div>
          <div className="consultation-drawer-content">
            {error ? (
              <ErrorState message={error} onRetry={() => void load()} />
            ) : (
              <LoadingState />
            )}
          </div>
        </aside>
      </div>
    );
  }

  const role = activeUser.role;
  const isGlobal = role === "national_admin";
  const isParticipant = [
    record.requester?.id,
    record.recipient?.id,
    record.acceptedBy?.id,
  ].includes(activeUser.id);
  const isMayAnswer =
    isGlobal ||
    (record.type === "PATIENT_CALLBACK"
      ? role === "coordinator" || record.recipient?.id === activeUser.id
      : (role === "referring_clinician" || role === "receiving_clinician") &&
        (record.recipient?.id === activeUser.id ||
          (!record.recipient &&
            record.recipientSpecialty &&
            activeUser.specialty === record.recipientSpecialty)));

  const open = record.state === "REQUESTED" || record.state === "ESCALATED";
  const finished = record.state === "OUTCOME_RECORDED";

  return (
    <div
      className="consultation-drawer-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <aside className="consultation-drawer" role="dialog" aria-modal="true">
        <div className="consultation-drawer-header">
          <div>
            <span>
              CONSULTATION · {record.caseId} · {humanize(record.type)}
            </span>
            <h2>
              {record.question
                ? "Clinical question"
                : "Patient call-back requested"}
            </h2>
          </div>
          <button type="button" onClick={onClose} aria-label="Close consultation">
            <X size={16} />
          </button>
        </div>
        <div className="consultation-drawer-content">
          {notice && <Alert tone={notice.tone}>{notice.text}</Alert>}
          <div className="wl-status-cell">
            <span className={stateTone(record.state)}>{humanize(record.state)}</span>
            {record.urgent && <span className="ui-badge ui-badge-urgent">Urgent</span>}
            {record.recipientSpecialty && (
              <span className="ui-badge ui-badge-neutral">
                {humanize(record.recipientSpecialty)}
              </span>
            )}
          </div>

          <div className="consultation-detail-grid">
            <div>
              <span>Requester</span>
              <strong>{record.requester?.displayName ?? "—"}</strong>
            </div>
            <div>
              <span>Recipient</span>
              <strong>
                {record.recipient?.displayName ??
                  (record.recipientSpecialty
                    ? humanize(record.recipientSpecialty)
                    : "Any available clinician")}
              </strong>
            </div>
            <div>
              <span>Requested</span>
              <strong>{formatDateTime(record.createdAt)}</strong>
            </div>
            <div>
              <span>Due</span>
              <strong>{formatDateTime(record.dueAt)}</strong>
            </div>
          </div>

          {record.question && (
            <div className="consultation-question-block">
              <span>Question</span>
              <p>{record.question}</p>
            </div>
          )}
          {record.preferredTime && (
            <p className="consultation-preferred">
              Preferred time: {record.preferredTime}
            </p>
          )}

          <div className="consultation-thread">
            <h3>
              <MessageSquare size={14} /> Conversation
            </h3>
            {record.thread.length === 0 ? (
              <p className="consultation-muted">No replies yet.</p>
            ) : (
              record.thread.map((entry, index) => (
                <div className="thread-entry" key={`${entry.byId}-${index}`}>
                  <span className="thread-avatar">{initialsOf(entry.byName)}</span>
                  <div>
                    <div className="thread-meta">
                      <strong>{entry.byName}</strong>
                      <span>
                        {humanize(entry.role)} · {formatDateTime(entry.at)}
                      </span>
                    </div>
                    <p>{entry.text}</p>
                  </div>
                </div>
              ))
            )}
            {!finished && (isParticipant || isMayAnswer) && (
              <div className="consultation-reply">
                <textarea
                  value={reply}
                  onChange={(event) => setReply(event.target.value)}
                  placeholder="Write a reply"
                />
                <button
                  type="button"
                  className="ui-btn ui-btn-secondary"
                  disabled={busy || !reply.trim()}
                  onClick={() =>
                    run(async () => {
                      await replyToConsultation(record.id, reply.trim());
                      setReply("");
                    }, "Reply sent.")
                  }
                >
                  Send reply
                </button>
              </div>
            )}
          </div>

          {record.outcome && (
            <div className="consultation-outcome">
              <h4>
                <CheckCircle2 size={15} /> Outcome · {humanize(record.outcome.type)}
              </h4>
              <p>{record.outcome.note}</p>
              <p className="consultation-muted">
                {record.outcome.recordedBy?.displayName ?? "—"} ·{" "}
                {formatDateTime(record.outcome.recordedAt)}
              </p>
            </div>
          )}

          {open && isMayAnswer && (
            <div className="consultation-section">
              <h3>Your response</h3>
              <div className="consultation-actions">
                <button
                  type="button"
                  className="ui-btn ui-btn-primary"
                  disabled={busy}
                  onClick={() =>
                    run(() => acceptConsultation(record.id), "Consultation accepted.")
                  }
                >
                  Accept consultation
                </button>
              </div>
              <div className="ui-field">
                <label>Escalate to the coordinator</label>
                <textarea
                  value={escalationReason}
                  onChange={(event) => setEscalationReason(event.target.value)}
                  placeholder="Why is this stuck?"
                />
              </div>
              <button
                type="button"
                className="ui-btn ui-btn-secondary"
                disabled={busy || !escalationReason.trim()}
                onClick={() =>
                  run(
                    () => escalateConsultation(record.id, escalationReason.trim()),
                    "Consultation escalated."
                  )
                }
              >
                Escalate
              </button>
            </div>
          )}

          {record.state === "ACCEPTED" && isMayAnswer && (
            <div className="consultation-section">
              <h3>Record the outcome (R-49)</h3>
              <div className="ui-field">
                <label>Outcome type</label>
                <select
                  value={outcomeType}
                  onChange={(event) =>
                    setOutcomeType(event.target.value as ConsultationOutcomeType)
                  }
                >
                  {OUTCOME_TYPES.map((value) => (
                    <option key={value} value={value}>
                      {humanize(value)}
                    </option>
                  ))}
                </select>
              </div>
              <div className="ui-field">
                <label>Note</label>
                <textarea
                  value={outcomeNote}
                  onChange={(event) => setOutcomeNote(event.target.value)}
                  placeholder="What was decided?"
                />
              </div>
              <button
                type="button"
                className="ui-btn ui-btn-primary"
                disabled={busy || !outcomeNote.trim()}
                onClick={() =>
                  run(
                    () =>
                      recordConsultationOutcome(
                        record.id,
                        outcomeType,
                        outcomeNote.trim()
                      ),
                    "Outcome recorded. The case status is unchanged; the owner can act on it."
                  )
                }
              >
                Record outcome
              </button>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
