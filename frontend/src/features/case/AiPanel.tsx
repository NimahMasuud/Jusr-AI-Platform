import { useCallback, useEffect, useState } from "react";
import Alert from "../../components/ui/Alert";
import { aiService, type ApprovedCaseSummary } from "../ai/ai.service";
import type { AISuggestionRecord } from "../../services/api/v6.types";
import { formatDateTime, humanize } from "../../utils/format";
import "./case.css";

export default function AiPanel({
  caseId,
  onChanged,
}: {
  caseId: string;
  onChanged: () => void;
}) {
  const [summary, setSummary] = useState<ApprovedCaseSummary | null>(null);
  const [suggestions, setSuggestions] = useState<AISuggestionRecord[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);

  const load = useCallback(() => {
    aiService
      .getCaseSummary(caseId)
      .then(setSummary)
      .catch(() => setSummary(null));
    aiService
      .listSuggestions({ caseId, pageSize: 20 })
      .then((page) => setSuggestions(page.items))
      .catch(() => setSuggestions([]));
  }, [caseId]);

  useEffect(load, [load]);

  async function generate() {
    setError("");
    setNotice("");
    setGenerating(true);
    try {
      const result = await aiService.generateSuggestions({
        caseId,
        kinds: ["CASE_SUMMARY", "URGENCY", "REFERRAL_TARGET", "MESSAGE_DRAFT"],
      });
      setNotice(
        result.items.length > 0
          ? `${result.items.length} new suggestion(s) created. A person must approve each one.`
          : "No new suggestions — the pending items below already cover this case."
      );
      load();
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to generate suggestions.");
    } finally {
      setGenerating(false);
    }
  }

  async function decide(
    suggestion: AISuggestionRecord,
    decision: "approve" | "reject"
  ) {
    setError("");
    setBusyId(suggestion.id);
    try {
      if (decision === "approve") {
        const payload = suggestion.payload as { body?: string };
        const editedBody =
          suggestion.kind === "MESSAGE_DRAFT" && payload.body
            ? window.prompt("Edit the message before approving (leave as is to keep it):", payload.body) ??
              undefined
            : undefined;
        await aiService.approveSuggestion(suggestion.id, {
          editedBody: editedBody?.trim() || undefined,
          note: "Reviewed in the case workspace.",
        });
      } else {
        const reason = window.prompt("Reason for rejecting this AI suggestion:");
        if (!reason?.trim()) return;
        await aiService.rejectSuggestion(suggestion.id, { reason: reason.trim() });
      }
      load();
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to record the decision.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="cd-section">
      <div className="cd-section-head">
        <div>
          <h3>AI assistance</h3>
          <p>Suggestions are advice. A person always decides; approvals are audited.</p>
        </div>
        <div className="cd-actions" style={{ alignItems: "center", paddingTop: 0 }}>
          <span className="ui-simulated-notice">
            <strong>SIMULATED</strong> rules-based
          </span>
          <button
            type="button"
            className="ui-btn ui-btn-secondary ui-btn-sm"
            disabled={generating}
            onClick={generate}
          >
            {generating ? "Generating…" : "Generate"}
          </button>
        </div>
      </div>
      <div className="cd-section-body">
        {error && <Alert tone="danger">{error}</Alert>}
        {notice && <Alert tone="success">{notice}</Alert>}

        {summary ? (
          <div className="cd-item">
            <div className="cd-item-head">
              <span className="cd-item-title">Approved case summary</span>
              <span className="ui-badge ui-badge-success">Approved</span>
            </div>
            <p className="cd-muted" style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>
              {String((summary.payload as { summary?: string }).summary ?? "")}
            </p>
            {Array.isArray((summary.payload as { citations?: unknown[] }).citations) &&
              ((summary.payload as { citations: { sourceType: string; sourceId: string }[] })
                .citations.length > 0) && (
                <div className="cd-item-meta">
                  {(summary.payload as { citations: { sourceType: string; sourceId: string }[] })
                    .citations.map((citation, index) => (
                      <span key={`${citation.sourceType}-${citation.sourceId}-${index}`}>
                        {humanize(citation.sourceType)} · {citation.sourceId.slice(0, 8)}
                      </span>
                    ))}
                </div>
              )}
          </div>
        ) : (
          <p className="cd-empty">No approved AI summary for this case.</p>
        )}

        <div className="cd-list">
          {suggestions.length === 0 && (
            <p className="cd-empty">No AI suggestions recorded for this case.</p>
          )}
          {suggestions.map((suggestion) => {
            const payload = suggestion.payload as Record<string, unknown>;
            return (
              <div className="cd-item" key={suggestion.id}>
                <div className="cd-item-head">
                  <span className="cd-item-title">{humanize(suggestion.kind)}</span>
                  <span
                    className={`ui-badge ${
                      suggestion.status === "APPROVED"
                        ? "ui-badge-success"
                        : suggestion.status === "REJECTED"
                          ? "ui-badge-danger"
                          : "ui-badge-warning"
                    }`}
                  >
                    {humanize(suggestion.status)}
                  </span>
                </div>
                {typeof payload.body === "string" && (
                  <p className="cd-muted" style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>
                    {payload.body}
                  </p>
                )}
                {typeof payload.summary === "string" && (
                  <p className="cd-muted" style={{ marginTop: 6 }}>
                    {payload.summary}
                  </p>
                )}
                {typeof payload.rationale === "string" && (
                  <p className="cd-muted" style={{ marginTop: 6 }}>
                    {payload.rationale}
                  </p>
                )}
                <div className="cd-item-meta">
                  <span>{formatDateTime(suggestion.createdAt)}</span>
                  <span>{suggestion.model ?? "model not recorded"}</span>
                  {suggestion.decisionNote && <span>{suggestion.decisionNote}</span>}
                </div>
                {suggestion.status === "PENDING" && (
                  <div className="cd-actions" style={{ marginTop: 8 }}>
                    <button
                      type="button"
                      className="ui-btn ui-btn-primary ui-btn-sm"
                      disabled={busyId === suggestion.id}
                      onClick={() => decide(suggestion, "approve")}
                    >
                      Approve
                    </button>
                    <button
                      type="button"
                      className="ui-btn ui-btn-secondary ui-btn-sm"
                      disabled={busyId === suggestion.id}
                      onClick={() => decide(suggestion, "reject")}
                    >
                      Reject
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
