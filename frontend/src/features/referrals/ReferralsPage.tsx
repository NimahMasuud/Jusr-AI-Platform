import "./referrals.css";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowRightLeft,
  Ban,
  CheckCircle2,
  Clock,
  ExternalLink,
  RotateCcw,
  Search,
  Siren,
  X,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import Alert from "../../components/ui/Alert";
import Modal from "../../components/ui/Modal";
import Pagination from "../../components/ui/Pagination";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../../components/ui/StateViews";
import { useUser } from "../../context/UserContext";
import type {
  DeclineCode,
  FacilityRecord,
  ReferralRecord,
  ReferralStatus,
} from "../../services/api/v6.types";
import {
  acceptReferral,
  assignReferralClinician,
  createReferral,
  declineReferral,
  escalateReferral,
  getReferral,
  listReferrals,
  markReferralNotAccepted,
  reassignReferral,
  recordReferralConsultation,
} from "../../services/api/referralsApi";
import { listFacilities } from "../../services/api/adminApi";
import { useStaff } from "../case/useStaff";
import { formatDateTime, humanize } from "../../utils/format";

const STATUSES: ReferralStatus[] = [
  "SENT",
  "ACCEPTED",
  "DECLINED",
  "NOT_ACCEPTED_IN_TIME",
];

const DECLINE_CODES: DeclineCode[] = [
  "WRONG_SPECIALTY",
  "NO_CAPACITY",
  "INFORMATION_MISSING",
  "NOT_ELIGIBLE",
  "OTHER",
];

function ReferralStatusBadge({ status }: { status: ReferralStatus }) {
  const tone =
    status === "ACCEPTED"
      ? "ui-badge ui-badge-success"
      : status === "DECLINED"
        ? "ui-badge ui-badge-danger"
        : status === "NOT_ACCEPTED_IN_TIME"
          ? "ui-badge ui-badge-urgent"
          : "ui-badge ui-badge-warning";
  return <span className={tone}>{humanize(status)}</span>;
}

export default function ReferralsPage() {
  const { activeUser } = useUser();
  const navigate = useNavigate();
  const [items, setItems] = useState<ReferralRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [status, setStatus] = useState<ReferralStatus | "">("");
  const [direction, setDirection] = useState<"incoming" | "outgoing" | "">("");
  const [escalatedOnly, setEscalatedOnly] = useState(false);
  const [search, setSearch] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const [startOpen, setStartOpen] = useState(false);
  const [startCaseId, setStartCaseId] = useState("");
  const [startFacilityId, setStartFacilityId] = useState("");
  const [startClinicianId, setStartClinicianId] = useState("");
  const [startSpecialty, setStartSpecialty] = useState("");
  const [startReason, setStartReason] = useState("");
  const [startFacilities, setStartFacilities] = useState<FacilityRecord[]>([]);
  const [startBusy, setStartBusy] = useState(false);
  const [startError, setStartError] = useState("");
  const [notice, setNotice] = useState("");

  const canStart =
    activeUser?.role === "referring_clinician" ||
    activeUser?.role === "receiving_clinician" ||
    activeUser?.role === "national_admin";

  const { staff } = useStaff({ role: "RECEIVING_CLINICIAN" });

  useEffect(() => {
    if (!startOpen) return;
    listFacilities()
      .then(setStartFacilities)
      .catch(() => setStartFacilities([]));
  }, [startOpen]);

  async function submitStartReferral() {
    setStartError("");
    if (!startCaseId.trim() || !startFacilityId) {
      setStartError("Case ID and receiving facility are required.");
      return;
    }
    setStartBusy(true);
    try {
      await createReferral({
        caseId: startCaseId.trim(),
        receivingFacilityId: startFacilityId,
        receivingClinicianId: startClinicianId || undefined,
        targetSpecialty: startSpecialty.trim() || undefined,
        reason: startReason.trim() || undefined,
      });
      setNotice("Referral sent. It now appears in the receiving facility's incoming list.");
      setStartOpen(false);
      setStartCaseId("");
      setStartFacilityId("");
      setStartClinicianId("");
      setStartSpecialty("");
      setStartReason("");
      await load();
    } catch (err) {
      setStartError(err instanceof Error ? err.message : "Unable to send the referral.");
    } finally {
      setStartBusy(false);
    }
  }

  const startClinicians = staff.filter(
    (person) => !startFacilityId || person.facilityId === startFacilityId
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await listReferrals({
        page,
        pageSize,
        status: status || undefined,
        direction: direction || undefined,
        escalated: escalatedOnly || undefined,
      });
      setItems(response.items);
      setTotal(response.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load referrals.");
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, status, direction, escalatedOnly]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setPage(1);
  }, [status, direction, escalatedOnly]);

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return items;
    return items.filter((item) =>
      [
        item.case.patient.displayLabel,
        item.case.caseId,
        item.case.trackerId,
        item.targetSpecialty,
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(term))
    );
  }, [items, search]);

  const summary = useMemo(
    () => ({
      sent: items.filter((item) => item.status === "SENT").length,
      accepted: items.filter((item) => item.status === "ACCEPTED").length,
      declined: items.filter((item) => item.status === "DECLINED").length,
      missed: items.filter((item) => item.status === "NOT_ACCEPTED_IN_TIME").length,
      escalated: items.filter((item) => item.escalated).length,
    }),
    [items]
  );

  const hasFilters = Boolean(status || direction || escalatedOnly || search);
  const cards = [
    { label: "Awaiting decision", value: summary.sent, icon: Clock, tone: "amber" },
    { label: "Accepted", value: summary.accepted, icon: CheckCircle2, tone: "green" },
    { label: "Declined", value: summary.declined, icon: Ban, tone: "coral" },
    { label: "Not accepted in time", value: summary.missed, icon: Clock, tone: "coral" },
    { label: "Escalated", value: summary.escalated, icon: Siren, tone: "purple" },
  ];

  function clearFilters() {
    setStatus("");
    setDirection("");
    setEscalatedOnly(false);
    setSearch("");
  }

  return (
    <div className="referrals-page">
      <header className="referrals-page-heading">
        <div>
          <span className="referrals-eyebrow">REFERRALS</span>
          <h1>Referrals</h1>
          <p>
            Send, accept, decline and escalate referrals. A receiving clinician
            decides; the referring side keeps working until the patient is
            accepted.
          </p>
        </div>
        {canStart && (
          <button
            type="button"
            className="ui-btn ui-btn-primary"
            onClick={() => {
              setStartError("");
              setStartOpen(true);
            }}
          >
            Start referral
          </button>
        )}
      </header>

      {notice && <Alert tone="success">{notice}</Alert>}

      <section className="referral-stats">
        {cards.map((card) => (
          <article className="referral-stat-card" key={card.label}>
            <span className={`referral-stat-icon ${card.tone}`}>
              <card.icon size={18} />
            </span>
            <div>
              <span>{card.label}</span>
              <strong>{card.value}</strong>
            </div>
          </article>
        ))}
      </section>

      <section className="referral-filters">
        <div className="referral-filter-heading">
          <div>
            <h2>
              <ArrowRightLeft size={16} />
              Find a referral
            </h2>
            <p>Search the current page, or narrow the list by status.</p>
          </div>
          {hasFilters && (
            <button type="button" className="referral-clear-filters" onClick={clearFilters}>
              <RotateCcw size={13} /> Clear filters
            </button>
          )}
        </div>
        <div className="referral-filter-controls">
          <label className="referral-search">
            <Search size={15} />
            <input
              type="search"
              placeholder="Patient, case number or specialty"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value as ReferralStatus | "")}
            aria-label="Filter by status"
          >
            <option value="">All statuses</option>
            {STATUSES.map((value) => (
              <option key={value} value={value}>
                {humanize(value)}
              </option>
            ))}
          </select>
          <select
            value={direction}
            onChange={(event) =>
              setDirection(event.target.value as "incoming" | "outgoing" | "")
            }
            aria-label="Referral direction"
          >
            <option value="">All directions</option>
            <option value="incoming">Incoming (to my facility)</option>
            <option value="outgoing">Outgoing (from my facility)</option>
          </select>
          <label className="wl-checkbox" style={{ height: 42 }}>
            <input
              type="checkbox"
              checked={escalatedOnly}
              onChange={(event) => setEscalatedOnly(event.target.checked)}
            />
            Escalated only
          </label>
        </div>
      </section>

      {error ? (
        <ErrorState message={error} onRetry={() => void load()} />
      ) : loading ? (
        <LoadingState message="Loading referrals…" />
      ) : visible.length === 0 ? (
        <EmptyState
          title="No referrals here"
          message={
            hasFilters
              ? "Try clearing the filters."
              : "Referrals appear when a clinician sends a case to another facility."
          }
          action={
            hasFilters ? (
              <button type="button" className="ui-btn ui-btn-secondary" onClick={clearFilters}>
                Clear filters
              </button>
            ) : undefined
          }
        />
      ) : (
        <>
          <div className="referral-table-wrapper">
            <table className="referral-table">
              <thead>
                <tr>
                  <th>Patient</th>
                  <th>From → to</th>
                  <th>Specialty</th>
                  <th>Status</th>
                  <th>Receiving clinician</th>
                  <th>Created</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {visible.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <strong>{item.case.patient.displayLabel}</strong>
                      <span className="referral-muted">
                        {item.case.caseId} · {item.case.screening?.type ?? "No screening"}
                      </span>
                    </td>
                    <td>
                      <strong>{item.referringFacility?.name ?? "—"}</strong>
                      <span className="referral-muted">
                        → {item.receivingFacility?.name ?? "Not chosen"}
                      </span>
                    </td>
                    <td>{item.targetSpecialty ? humanize(item.targetSpecialty) : "—"}</td>
                    <td>
                      <div className="wl-status-cell">
                        <ReferralStatusBadge status={item.status} />
                        {item.escalated && (
                          <span className="ui-badge ui-badge-primary">Escalated</span>
                        )}
                      </div>
                    </td>
                    <td>{item.receivingClinician?.displayName ?? "Not assigned"}</td>
                    <td>{formatDateTime(item.createdAt)}</td>
                    <td>
                      <button
                        type="button"
                        className="referral-view-button"
                        onClick={() => setOpenId(item.id)}
                      >
                        View
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={page} pageSize={pageSize} total={total} onChange={setPage} />
        </>
      )}

      {openId && activeUser && (
        <ReferralDrawer
          referralId={openId}
          onClose={() => setOpenId(null)}
          onChanged={() => void load()}
          onOpenCase={(caseId) =>
            navigate(`/worklist?caseId=${encodeURIComponent(caseId)}`)
          }
        />
      )}

      <Modal
        open={startOpen}
        title="Start a referral"
        subtitle="Send a case to another facility. The receiving side accepts or declines."
        onClose={() => setStartOpen(false)}
        footer={
          <>
            <button
              type="button"
              className="ui-btn ui-btn-secondary"
              onClick={() => setStartOpen(false)}
              disabled={startBusy}
            >
              Cancel
            </button>
            <button
              type="button"
              className="ui-btn ui-btn-primary"
              onClick={submitStartReferral}
              disabled={startBusy}
            >
              {startBusy ? "Sending…" : "Send referral"}
            </button>
          </>
        }
      >
        {startError && <Alert tone="danger">{startError}</Alert>}
        <div style={{ display: "grid", gap: 12 }}>
          <div className="ui-field">
            <label>Case ID</label>
            <input
              value={startCaseId}
              placeholder="Case ID or case number (e.g. C-1234ABCD)"
              onChange={(event) => setStartCaseId(event.target.value)}
            />
          </div>
          <div className="ui-field">
            <label>Receiving facility</label>
            <select
              value={startFacilityId}
              onChange={(event) => {
                setStartFacilityId(event.target.value);
                setStartClinicianId("");
              }}
            >
              <option value="">Select a facility</option>
              {startFacilities.map((facility) => (
                <option key={facility.id} value={facility.id}>
                  {facility.name}
                </option>
              ))}
            </select>
          </div>
          <div className="ui-field">
            <label>Receiving clinician (optional)</label>
            <select
              value={startClinicianId}
              onChange={(event) => setStartClinicianId(event.target.value)}
            >
              <option value="">Unassigned — facility to assign</option>
              {startClinicians.map((person) => (
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
              value={startSpecialty}
              onChange={(event) => setStartSpecialty(event.target.value)}
            />
          </div>
          <div className="ui-field">
            <label>Reason</label>
            <textarea
              rows={3}
              value={startReason}
              onChange={(event) => setStartReason(event.target.value)}
            />
          </div>
        </div>
      </Modal>
    </div>
  );
}

function ReferralDrawer({
  referralId,
  onClose,
  onChanged,
  onOpenCase,
}: {
  referralId: string;
  onClose: () => void;
  onChanged: () => void;
  onOpenCase: (caseId: string) => void;
}) {
  const { activeUser } = useUser();
  const [record, setRecord] = useState<ReferralRecord | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const [declineCode, setDeclineCode] = useState<DeclineCode>("WRONG_SPECIALTY");
  const [declineNote, setDeclineNote] = useState("");
  const [acceptNote, setAcceptNote] = useState("");
  const [escalationReason, setEscalationReason] = useState("");
  const [reassignFacilityId, setReassignFacilityId] = useState("");
  const [reassignReason, setReassignReason] = useState("");
  const [consultationOutcome, setConsultationOutcome] = useState("");
  const [facilities, setFacilities] = useState<FacilityRecord[]>([]);
  const [assignClinicianId, setAssignClinicianId] = useState("");
  const { staff } = useStaff({
    role: "receiving_clinician",
    facilityId: record?.receivingFacility?.id,
  });

  const load = useCallback(async () => {
    try {
      const detail = await getReferral(referralId);
      setRecord(detail);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load this referral.");
    }
  }, [referralId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    listFacilities()
      .then(setFacilities)
      .catch(() => setFacilities([]));
  }, []);

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
        className="referral-drawer-overlay"
        onMouseDown={(event) => {
          if (event.target === event.currentTarget) onClose();
        }}
      >
        <aside className="referral-details-drawer">
          <div className="referral-drawer-header">
            <div>
              <span>REFERRAL</span>
              <h2>Loading…</h2>
            </div>
            <button type="button" onClick={onClose} aria-label="Close">
              <X size={16} />
            </button>
          </div>
          <div className="referral-drawer-content">
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
  const isReceivingCoordinator =
    isGlobal ||
    (role === "coordinator" &&
      activeUser.facility?.id !== undefined &&
      activeUser.facility.id === record.receivingFacility?.id);
  const canDecide =
    role === "receiving_clinician" &&
    activeUser.facility?.id === record.receivingFacility?.id &&
    (!record.receivingClinician || record.receivingClinician.id === activeUser.id);
  const canReferrerAct =
    isGlobal || role === "referring_clinician" || role === "coordinator";
  const canAssign = isGlobal || isReceivingCoordinator;
  const open = record.status === "SENT";
  const canReassign =
    canReferrerAct &&
    (record.status === "SENT" ||
      record.status === "DECLINED" ||
      record.status === "NOT_ACCEPTED_IN_TIME");
  const canConsult =
    role === "receiving_clinician" &&
    record.receivingClinician?.id === activeUser.id &&
    record.status === "ACCEPTED" &&
    !record.consultation;

  const reassignOptions = facilities.filter(
    (facility) =>
      facility.id !== record.receivingFacility?.id &&
      facility.id !== record.referringFacility?.id
  );

  return (
    <div
      className="referral-drawer-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <aside className="referral-details-drawer" role="dialog" aria-modal="true">
        <div className="referral-drawer-header">
          <div>
            <span>REFERRAL · {record.case.caseId}</span>
            <h2>{record.case.patient.displayLabel}</h2>
          </div>
          <button type="button" onClick={onClose} aria-label="Close referral">
            <X size={16} />
          </button>
        </div>

        <div className="referral-drawer-content">
          {notice && <Alert tone={notice.tone}>{notice.text}</Alert>}

          <div className="referral-detail-section">
            <h3>
              <ArrowRightLeft size={15} /> Referral
            </h3>
            <div className="wl-status-cell" style={{ marginBottom: 12 }}>
              <ReferralStatusBadge status={record.status} />
              {record.escalated && (
                <span className="ui-badge ui-badge-primary">
                  Escalated{record.escalationReason ? `: ${record.escalationReason}` : ""}
                </span>
              )}
            </div>
            <div className="referral-detail-field">
              <span>From</span>
              <strong>{record.referringFacility?.name ?? "—"}</strong>
            </div>
            <div className="referral-detail-field">
              <span>To</span>
              <strong>{record.receivingFacility?.name ?? "Not chosen"}</strong>
            </div>
            <div className="referral-detail-field">
              <span>Specialty</span>
              <strong>
                {record.targetSpecialty ? humanize(record.targetSpecialty) : "Not specified"}
              </strong>
            </div>
            <div className="referral-detail-field">
              <span>Receiving clinician</span>
              <strong>{record.receivingClinician?.displayName ?? "Not assigned"}</strong>
            </div>
            <div className="referral-detail-field">
              <span>Reason</span>
              <p>{record.reason ?? "No reason recorded."}</p>
            </div>
            {record.declineCode && (
              <div className="referral-detail-field">
                <span>Decline</span>
                <p>
                  {humanize(record.declineCode)}
                  {record.declineReason ? ` — ${record.declineReason}` : ""}
                </p>
              </div>
            )}
            <div className="referral-detail-field">
              <span>Sent</span>
              <strong>{formatDateTime(record.createdAt)}</strong>
            </div>
            <div className="referral-decision-actions">
              <button
                type="button"
                className="ui-btn ui-btn-secondary"
                onClick={() => onOpenCase(record.case.id)}
              >
                <ExternalLink size={14} /> Open case
              </button>
            </div>
          </div>

          {record.consultation && (
            <div className="referral-detail-section">
              <h3>
                <CheckCircle2 size={15} /> Consultation outcome
              </h3>
              <div className="referral-detail-field">
                <span>{humanize(record.consultation.outcomeType ?? "Outcome")}</span>
                <p>{record.consultation.outcome ?? "No note."}</p>
              </div>
              <div className="referral-detail-field">
                <span>Recorded</span>
                <strong>{formatDateTime(record.consultation.recordedAt)}</strong>
              </div>
            </div>
          )}

          {canDecide && open && (
            <div className="referral-detail-section">
              <h3>
                <Siren size={15} /> Your decision
              </h3>
              <div className="referral-rejection-form">
                <label htmlFor="accept-note">Accept this patient (T12)</label>
                <textarea
                  id="accept-note"
                  value={acceptNote}
                  onChange={(event) => setAcceptNote(event.target.value)}
                  placeholder="Optional note for the referring team"
                />
                <div className="referral-decision-actions">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      run(
                        () => acceptReferral(record.id, acceptNote.trim() || undefined),
                        "Referral accepted. You are now the named owner of the case."
                      )
                    }
                  >
                    Accept referral
                  </button>
                </div>
              </div>

              <div className="referral-rejection-form">
                <label htmlFor="decline-code">Or decline with a reason (T13)</label>
                <select
                  id="decline-code"
                  value={declineCode}
                  onChange={(event) => setDeclineCode(event.target.value as DeclineCode)}
                  style={{
                    height: 42,
                    border: "1px solid var(--color-border)",
                    borderRadius: 8,
                    padding: "0 10px",
                  }}
                >
                  {DECLINE_CODES.map((code) => (
                    <option key={code} value={code}>
                      {humanize(code)}
                    </option>
                  ))}
                </select>
                <textarea
                  value={declineNote}
                  onChange={(event) => setDeclineNote(event.target.value)}
                  placeholder={
                    declineCode === "OTHER"
                      ? "A note is required when the reason is 'other'"
                      : "Optional note"
                  }
                />
                <div className="referral-decision-actions">
                  <button
                    type="button"
                    disabled={busy || (declineCode === "OTHER" && !declineNote.trim())}
                    onClick={() =>
                      run(
                        () =>
                          declineReferral(record.id, {
                            code: declineCode,
                            reason: declineNote.trim() || undefined,
                          }),
                        "Referral declined. The referring team must choose another target."
                      )
                    }
                  >
                    Decline referral
                  </button>
                </div>
              </div>
            </div>
          )}

          {canAssign && open && (
            <div className="referral-detail-section">
              <h3>Assign a receiving clinician</h3>
              <div className="referral-detail-field">
                <span>
                  Staff at {record.receivingFacility?.name ?? "the receiving facility"}
                </span>
                <select
                  value={assignClinicianId}
                  onChange={(event) => setAssignClinicianId(event.target.value)}
                  style={{
                    height: 42,
                    border: "1px solid var(--color-border)",
                    borderRadius: 8,
                    padding: "0 10px",
                  }}
                >
                  <option value="">Choose a clinician</option>
                  {staff.map((person) => (
                    <option key={person.id} value={person.id}>
                      {person.displayName}
                      {person.specialty ? ` — ${humanize(person.specialty)}` : ""}
                    </option>
                  ))}
                </select>
              </div>
              <div className="referral-decision-actions">
                <button
                  type="button"
                  className="ui-btn ui-btn-secondary"
                  disabled={busy || !assignClinicianId}
                  onClick={() =>
                    run(
                      () => assignReferralClinician(record.id, assignClinicianId),
                      "Clinician assigned to this referral."
                    )
                  }
                >
                  Assign clinician
                </button>
              </div>
            </div>
          )}

          {canReferrerAct && (open || canReassign) && (
            <div className="referral-detail-section">
              <h3>Referring team actions</h3>
              {open && !record.escalated && (
                <div className="referral-rejection-form">
                  <label htmlFor="escalate-reason">
                    Escalate because the referral is stuck
                  </label>
                  <textarea
                    id="escalate-reason"
                    value={escalationReason}
                    onChange={(event) => setEscalationReason(event.target.value)}
                    placeholder="What is blocking the referral?"
                  />
                  <div className="referral-decision-actions">
                    <button
                      type="button"
                      disabled={busy || !escalationReason.trim()}
                      onClick={() =>
                        run(
                          () => escalateReferral(record.id, escalationReason.trim()),
                          "Referral escalated."
                        )
                      }
                    >
                      Escalate
                    </button>
                  </div>
                </div>
              )}

              {canReassign && (
                <div className="referral-rejection-form">
                  <label htmlFor="reassign-facility">Choose another facility (R-45)</label>
                  <select
                    id="reassign-facility"
                    value={reassignFacilityId}
                    onChange={(event) => setReassignFacilityId(event.target.value)}
                    style={{
                      height: 42,
                      border: "1px solid var(--color-border)",
                      borderRadius: 8,
                      padding: "0 10px",
                    }}
                  >
                    <option value="">Choose a facility</option>
                    {reassignOptions.map((facility) => (
                      <option key={facility.id} value={facility.id}>
                        {facility.name}
                      </option>
                    ))}
                  </select>
                  <textarea
                    value={reassignReason}
                    onChange={(event) => setReassignReason(event.target.value)}
                    placeholder="Why is the referral being reassigned?"
                  />
                  <div className="referral-decision-actions">
                    <button
                      type="button"
                      disabled={busy || !reassignFacilityId || !reassignReason.trim()}
                      onClick={() =>
                        run(
                          () =>
                            reassignReferral(
                              record.id,
                              reassignFacilityId,
                              reassignReason.trim()
                            ),
                          "Referral reassigned."
                        )
                      }
                    >
                      Reassign referral
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {(role === "coordinator" || isGlobal) && open && (
            <div className="referral-detail-section">
              <h3>Coordinator</h3>
              <p className="referral-muted" style={{ marginBottom: 10 }}>
                Mark the referral not accepted if the receiving facility let the
                time limit pass (R-46).
              </p>
              <div className="referral-decision-actions">
                <button
                  type="button"
                  className="ui-btn ui-btn-secondary"
                  disabled={busy}
                  onClick={() =>
                    run(
                      () => markReferralNotAccepted(record.id),
                      "Referral marked not accepted in time."
                    )
                  }
                >
                  Mark not accepted in time
                </button>
              </div>
            </div>
          )}

          {canConsult && (
            <div className="referral-detail-section">
              <h3>Record the consultation outcome</h3>
              <div className="referral-rejection-form">
                <textarea
                  value={consultationOutcome}
                  onChange={(event) => setConsultationOutcome(event.target.value)}
                  placeholder="Advice given to the referring team"
                />
                <div className="referral-decision-actions">
                  <button
                    type="button"
                    disabled={busy || !consultationOutcome.trim()}
                    onClick={() =>
                      run(
                        () =>
                          recordReferralConsultation(
                            record.id,
                            consultationOutcome.trim()
                          ),
                        "Consultation outcome recorded."
                      )
                    }
                  >
                    Record outcome
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
