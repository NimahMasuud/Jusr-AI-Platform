import { useCallback, useEffect, useState } from "react";
import { Bot, CheckCircle2, ShieldCheck, XCircle } from "lucide-react";

import Alert from "../../components/ui/Alert";
import Modal from "../../components/ui/Modal";
import Pagination from "../../components/ui/Pagination";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../../components/ui/StateViews";
import type { AISuggestionRecord } from "../../services/api/v6.types";
import { useUser } from "../../context/UserContext";
import type { UserRole } from "../../context/UserContext";
import { formatDateTime, humanize } from "../../utils/format";
import { aiService } from "./ai.service";
import type { BackendAIKind, SuggestionStatus } from "./ai.types";
import "./ai-review.css";

const PAGE_SIZE = 20;

const KIND_LABELS: Record<string, string> = {
  INTAKE: "Intake & next action",
  URGENCY: "Urgency assessment",
  MESSAGE_DRAFT: "Message draft",
  CASE_SUMMARY: "Case summary",
  REFERRAL_TARGET: "Referral target",
};

const KIND_OPTIONS: Array<{ value: BackendAIKind | ""; label: string }> = [
  { value: "", label: "All suggestion types" },
  { value: "INTAKE", label: KIND_LABELS.INTAKE },
  { value: "URGENCY", label: KIND_LABELS.URGENCY },
  { value: "MESSAGE_DRAFT", label: KIND_LABELS.MESSAGE_DRAFT },
  { value: "CASE_SUMMARY", label: KIND_LABELS.CASE_SUMMARY },
  { value: "REFERRAL_TARGET", label: KIND_LABELS.REFERRAL_TARGET },
];

const STATUS_OPTIONS: Array<{ value: SuggestionStatus | ""; label: string }> = [
  { value: "PENDING", label: "Pending review" },
  { value: "APPROVED", label: "Approved" },
  { value: "REJECTED", label: "Rejected" },
  { value: "", label: "All statuses" },
];

// Mirrors the backend approval matrix: each suggestion kind has a fixed set of approvers.
const APPROVERS: Record<BackendAIKind, UserRole[]> = {
  INTAKE: ["coordinator", "national_admin"],
  MESSAGE_DRAFT: ["coordinator", "national_admin"],
  URGENCY: ["referring_clinician", "receiving_clinician", "national_admin"],
  REFERRAL_TARGET: ["referring_clinician", "national_admin"],
  CASE_SUMMARY: [
    "coordinator",
    "referring_clinician",
    "receiving_clinician",
    "national_admin",
  ],
};

function canApprove(role: UserRole, kind: string): boolean {
  const approvers = APPROVERS[kind as BackendAIKind];
  return approvers ? approvers.includes(role) : false;
}

function asText(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

function PayloadDetails({ record }: { record: AISuggestionRecord }) {
  const payload = record.payload ?? {};

  if (record.kind === "MESSAGE_DRAFT") {
    return (
      <dl className="air-payload">
        <div>
          <dt>Channel</dt>
          <dd>{asText(payload.channel)}</dd>
        </div>
        <div>
          <dt>Language</dt>
          <dd>{asText(payload.language)}</dd>
        </div>
        <div>
          <dt>Purpose</dt>
          <dd>{asText(payload.purpose)}</dd>
        </div>
        <div className="air-payload-wide">
          <dt>Body</dt>
          <dd className="air-payload-body">{asText(payload.body)}</dd>
        </div>
      </dl>
    );
  }

  if (record.kind === "URGENCY") {
    return (
      <dl className="air-payload">
        <div>
          <dt>Priority</dt>
          <dd>{humanize(asText(payload.priority))}</dd>
        </div>
        <div>
          <dt>Actionability</dt>
          <dd>{humanize(asText(payload.actionability))}</dd>
        </div>
        <div className="air-payload-wide">
          <dt>Rationale</dt>
          <dd>{asText(payload.rationale)}</dd>
        </div>
      </dl>
    );
  }

  if (record.kind === "CASE_SUMMARY") {
    const citations = Array.isArray(payload.citations) ? payload.citations : [];
    return (
      <>
        <dl className="air-payload">
          <div className="air-payload-wide">
            <dt>Summary</dt>
            <dd>{asText(payload.summary)}</dd>
          </div>
        </dl>
        {citations.length > 0 && (
          <div className="air-citations">
            <h4>Sources</h4>
            <ul>
              {citations.map((citation, index) => {
                const item = citation as Record<string, unknown>;
                return (
                  <li key={index}>
                    <strong>{humanize(asText(item.sourceType))}</strong>
                    <span>{asText(item.sourceId)}</span>
                    {item.excerpt ? <em>{asText(item.excerpt)}</em> : null}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </>
    );
  }

  if (record.kind === "INTAKE") {
    return (
      <dl className="air-payload">
        <div>
          <dt>Patient</dt>
          <dd>{asText(payload.patientId)}</dd>
        </div>
        <div>
          <dt>Priority</dt>
          <dd>{humanize(asText(payload.priority))}</dd>
        </div>
        <div>
          <dt>Next action</dt>
          <dd>{asText(payload.nextActionLabel ?? payload.nextActionCode)}</dd>
        </div>
        <div className="air-payload-wide">
          <dt>Rationale</dt>
          <dd>{asText(payload.rationale)}</dd>
        </div>
      </dl>
    );
  }

  if (record.kind === "REFERRAL_TARGET") {
    const alternatives = Array.isArray(payload.alternatives)
      ? payload.alternatives
      : [];
    return (
      <>
        <dl className="air-payload">
          <div>
            <dt>Receiving facility</dt>
            <dd>{asText(payload.receivingFacilityId)}</dd>
          </div>
          <div>
            <dt>Receiving clinician</dt>
            <dd>{asText(payload.receivingClinicianId)}</dd>
          </div>
          <div className="air-payload-wide">
            <dt>Rationale</dt>
            <dd>{asText(payload.rationale)}</dd>
          </div>
        </dl>
        {alternatives.length > 0 && (
          <div className="air-citations">
            <h4>Alternatives</h4>
            <ul>
              {alternatives.map((alternative, index) => {
                const item = alternative as Record<string, unknown>;
                return (
                  <li key={index}>
                    <strong>{asText(item.receivingFacilityId)}</strong>
                    <em>{asText(item.rationale)}</em>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </>
    );
  }

  return <pre className="air-raw">{JSON.stringify(payload, null, 2)}</pre>;
}

export default function AIReviewPage() {
  const { activeUser } = useUser();
  const [items, setItems] = useState<AISuggestionRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<SuggestionStatus | "">("PENDING");
  const [kind, setKind] = useState<BackendAIKind | "">("");
  const [caseId, setCaseId] = useState("");
  const [appliedCaseId, setAppliedCaseId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [selected, setSelected] = useState<AISuggestionRecord | null>(null);
  const [approving, setApproving] = useState(false);
  const [editedBody, setEditedBody] = useState("");
  const [approveNote, setApproveNote] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [generating, setGenerating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await aiService.listSuggestions({
        page,
        pageSize: PAGE_SIZE,
        kind: kind || undefined,
        status: status || undefined,
        caseId: appliedCaseId || undefined,
      });
      setItems(result.items);
      setTotal(result.total);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load AI suggestions."
      );
    } finally {
      setLoading(false);
    }
  }, [page, kind, status, appliedCaseId]);

  useEffect(() => {
    void load();
  }, [load]);

  function openRecord(record: AISuggestionRecord) {
    setSelected(record);
    setApprovedState(record);
  }

  function setApprovedState(record: AISuggestionRecord) {
    const body =
      record.kind === "MESSAGE_DRAFT"
        ? String(record.payload?.body ?? "")
        : "";
    setEditedBody(body);
    setApproveNote("");
    setRejectReason("");
    setRejecting(false);
  }

  function closeRecord() {
    setSelected(null);
    setApproving(false);
    setRejecting(false);
  }

  async function handleApprove() {
    if (!selected) return;
    setApproving(true);
    setError("");
    try {
      const edited =
        selected.kind === "MESSAGE_DRAFT" &&
        editedBody.trim() &&
        editedBody !== String(selected.payload?.body ?? "")
          ? editedBody.trim()
          : undefined;
      await aiService.approveSuggestion(selected.id, {
        editedBody: edited,
        note: approveNote.trim() || undefined,
      });
      setNotice(
        `Suggestion approved${edited ? " with your edits" : ""}. The case record has been updated.`
      );
      closeRecord();
      await load();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to approve this suggestion."
      );
    } finally {
      setApproving(false);
    }
  }

  async function handleReject() {
    if (!selected) return;
    if (!rejectReason.trim()) {
      setError("A rejection reason is required.");
      return;
    }
    setApproving(true);
    setError("");
    try {
      await aiService.rejectSuggestion(selected.id, {
        reason: rejectReason.trim(),
      });
      setNotice("Suggestion rejected. The AI service has been notified.");
      closeRecord();
      await load();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to reject this suggestion."
      );
    } finally {
      setApproving(false);
    }
  }

  async function handleGenerate() {
    setGenerating(true);
    setError("");
    try {
      const target = caseId.trim();
      const result = await aiService.generateSuggestions(
        target ? { caseId: target } : {}
      );
      setNotice(
        result.items.length > 0
          ? `Generated ${result.items.length} new suggestion(s) across ${result.cases} case(s). They are pending review.`
          : "No new suggestions were generated — these cases already have pending items or nothing eligible."
      );
      setPage(1);
      setStatus("PENDING");
      if (!target) setKind("");
      await load();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to generate suggestions."
      );
    } finally {
      setGenerating(false);
    }
  }

  function applyFilters() {
    setPage(1);
    setAppliedCaseId(caseId.trim());
  }

  const pendingDecision =
    selected &&
    selected.status === "PENDING" &&
    activeUser &&
    canApprove(activeUser.role, selected.kind);

  return (
    <div className="page-container">
      <div className="page-heading">
        <div>
          <span className="worklist-eyebrow">AI GOVERNANCE</span>
          <h1>AI suggestion review</h1>
          <p>
            Every AI output is a suggestion until a person approves it. Review
            what the assistant proposed, edit where needed, and accept or
            reject with a recorded reason.
          </p>
        </div>
        <button
          type="button"
          className="ui-btn ui-btn-primary"
          onClick={handleGenerate}
          disabled={generating || !activeUser}
        >
          {generating
            ? "Generating…"
            : caseId.trim()
              ? "Generate for this case"
              : "Generate suggestions"}
        </button>
      </div>

      <div className="air-filters">
        <label>
          Status
          <select
            value={status}
            onChange={(event) => {
              setPage(1);
              setStatus(event.target.value as SuggestionStatus | "");
            }}
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.label} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Type
          <select
            value={kind}
            onChange={(event) => {
              setPage(1);
              setKind(event.target.value as BackendAIKind | "");
            }}
          >
            {KIND_OPTIONS.map((option) => (
              <option key={option.label} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Case ID
          <input
            value={caseId}
            placeholder="Filter by internal case ID"
            onChange={(event) => setCaseId(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") applyFilters();
            }}
          />
        </label>
        <button type="button" className="ui-btn ui-btn-secondary" onClick={applyFilters}>
          Apply filters
        </button>
      </div>

      {notice && <Alert tone="success">{notice}</Alert>}
      {error && <Alert tone="danger">{error}</Alert>}

      {loading ? (
        <LoadingState message="Loading suggestions…" />
      ) : error && items.length === 0 ? (
        <ErrorState message={error} onRetry={() => void load()} />
      ) : items.length === 0 ? (
        <EmptyState
          title="No suggestions match these filters"
          message="When the AI service submits a suggestion, it appears here for human review."
        />
      ) : (
        <>
          <div className="air-list">
            {items.map((record) => (
              <article className="air-card" key={record.id}>
                <div className="air-card-main">
                  <div className="air-card-title">
                    <Bot size={18} />
                    <h3>{KIND_LABELS[record.kind] ?? humanize(record.kind)}</h3>
                    <span className={`air-status air-status-${record.status.toLowerCase()}`}>
                      {humanize(record.status)}
                    </span>
                  </div>
                  <p className="air-card-meta">
                    Case {record.caseId ?? "—"} · {formatDateTime(record.createdAt)}
                    {record.model ? ` · ${record.model}` : ""}
                    {record.confidence !== null
                      ? ` · ${Math.round(record.confidence * 100)}% confidence`
                      : ""}
                  </p>
                  {record.status !== "PENDING" && (
                    <p className="air-card-decision">
                      {record.status === "APPROVED" ? (
                        <CheckCircle2 size={15} />
                      ) : (
                        <XCircle size={15} />
                      )}
                      Decided {formatDateTime(record.decidedAt)}
                      {record.decisionNote ? ` — ${record.decisionNote}` : ""}
                    </p>
                  )}
                </div>
                <button
                  type="button"
                  className="ui-btn ui-btn-secondary ui-btn-sm"
                  onClick={() => openRecord(record)}
                >
                  Review
                </button>
              </article>
            ))}
          </div>
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={total}
            onChange={setPage}
          />
        </>
      )}

      <Modal
        open={selected !== null}
        title={
          selected
            ? `${KIND_LABELS[selected.kind] ?? humanize(selected.kind)}`
            : "Suggestion"
        }
        subtitle={
          selected
            ? `Case ${selected.caseId ?? "—"} · ${humanize(selected.status)}`
            : undefined
        }
        onClose={closeRecord}
        footer={
          selected && selected.status === "PENDING" ? (
            pendingDecision ? (
              rejecting ? (
                <div className="air-reject-form">
                  <label>
                    Rejection reason (required)
                    <textarea
                      rows={2}
                      value={rejectReason}
                      onChange={(event) => setRejectReason(event.target.value)}
                      placeholder="Explain why this suggestion is not appropriate…"
                    />
                  </label>
                  <div className="air-footer-actions">
                    <button
                      type="button"
                      className="ui-btn ui-btn-ghost"
                      onClick={() => setRejecting(false)}
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      className="ui-btn ui-btn-danger"
                      onClick={() => void handleReject()}
                      disabled={approving}
                    >
                      Confirm rejection
                    </button>
                  </div>
                </div>
              ) : (
                <div className="air-footer-actions">
                  <button
                    type="button"
                    className="ui-btn ui-btn-secondary"
                    onClick={() => setRejecting(true)}
                    disabled={approving}
                  >
                    <XCircle size={15} /> Reject
                  </button>
                  <button
                    type="button"
                    className="ui-btn ui-btn-primary"
                    onClick={() => void handleApprove()}
                    disabled={approving}
                  >
                    <ShieldCheck size={15} />{" "}
                    {approving ? "Approving…" : "Approve suggestion"}
                  </button>
                </div>
              )
            ) : (
              <p className="air-readonly-note">
                Your role can review this suggestion but not approve it. A
                colleague with the right role must make the decision.
              </p>
            )
          ) : null
        }
      >
        {selected && (
          <div className="air-detail">
            <div className="air-detail-meta">
              <span>Submitted {formatDateTime(selected.createdAt)}</span>
              {selected.confidence !== null && (
                <span>{Math.round(selected.confidence * 100)}% confidence</span>
              )}
              {selected.requiresStaffApproval && (
                <span className="air-requires">Staff approval required</span>
              )}
            </div>

            <PayloadDetails record={selected} />

            {selected.status === "PENDING" && pendingDecision && (
              <div className="air-decision-form">
                {selected.kind === "MESSAGE_DRAFT" && (
                  <label>
                    Message body (editable before approval)
                    <textarea
                      rows={5}
                      value={editedBody}
                      onChange={(event) => setEditedBody(event.target.value)}
                    />
                  </label>
                )}
                <label>
                  Decision note (optional)
                  <input
                    value={approveNote}
                    onChange={(event) => setApproveNote(event.target.value)}
                    placeholder="Add context for the audit trail"
                  />
                </label>
              </div>
            )}

            {selected.status !== "PENDING" && (
              <div className="air-decision-summary">
                <strong>{humanize(selected.status)}</strong>
                <span>
                  {formatDateTime(selected.decidedAt)}
                  {selected.decisionNote ? ` — ${selected.decisionNote}` : ""}
                </span>
                {selected.applied && (
                  <pre className="air-raw">
                    {JSON.stringify(selected.applied, null, 2)}
                  </pre>
                )}
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
