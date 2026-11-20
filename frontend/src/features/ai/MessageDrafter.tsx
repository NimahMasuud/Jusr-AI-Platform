
import { useState } from "react";
import { aiService } from "./ai.service";
import { sendMessage } from "../../services/api/messagesApi";
import type { AIMessageDraftResult } from "./ai.types";
import "./message-drafter.css";

interface MessageDrafterProps {
  caseId: string;
  priority: string;
  disabled?: boolean;
  onChanged?: () => void;
}

export default function MessageDrafter({
  caseId,
  priority,
  disabled = false,
  onChanged,
}: MessageDrafterProps) {
  const [language, setLanguage] = useState<"en" | "ar">("en");
  const [channel, setChannel] = useState<"SMS" | "EMAIL">("SMS");
  const [nextStep, setNextStep] = useState("");
  const [contact, setContact] = useState("");
  const [draft, setDraft] = useState<AIMessageDraftResult | null>(null);
  const [editedBody, setEditedBody] = useState("");
  const [loading, setLoading] = useState(false);
  const [decisionLoading, setDecisionLoading] = useState(false);
  const [approvedMessageId, setApprovedMessageId] = useState<string | null>(null);
  const [sendLoading, setSendLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const urgency = priority.toLowerCase().includes("urgent")
    ? "urgent"
    : "routine";

  async function handleGenerate() {
    if (!nextStep.trim() || !contact.trim()) {
      setError("Enter the next step and contact details.");
      return;
    }

    setLoading(true);
    setError("");
    setNotice("");
    setDraft(null);
    setApprovedMessageId(null);
    setSent(false);

    try {
      const result = await aiService.createMessageDraft({
        caseId,
        language,
        channel,
        urgency,
        nextStep: nextStep.trim(),
        contact: contact.trim(),
      });

      setDraft(result);
      setEditedBody(result.payload.body);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to generate the draft."
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleApprove() {
    if (!draft || !editedBody.trim()) return;

    setDecisionLoading(true);
    setError("");
    setNotice("");

    try {
      const approved = await aiService.approveSuggestion(draft.id, {
        editedBody: editedBody.trim(),
        note: "Coordinator reviewed and approved the message draft.",
      });

      const messageId =
        typeof approved.applied?.messageId === "string"
          ? approved.applied.messageId
          : null;

      setApprovedMessageId(messageId);
      setDraft({ ...draft, status: "APPROVED" });
      setNotice(
        messageId
          ? "Draft approved. Send it to complete the notification step."
          : "Draft approved and recorded."
      );
      onChanged?.();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to approve the draft."
      );
    } finally {
      setDecisionLoading(false);
    }
  }

  async function handleReject() {
    if (!draft) return;

    const reason = window.prompt("Enter a reason for rejecting this draft:");
    if (!reason?.trim()) return;

    setDecisionLoading(true);
    setError("");
    setNotice("");

    try {
      await aiService.rejectSuggestion(draft.id, {
        reason: reason.trim(),
      });

      setDraft({ ...draft, status: "REJECTED" });
      setNotice("Draft rejected and the decision has been recorded.");
      onChanged?.();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to reject the draft."
      );
    } finally {
      setDecisionLoading(false);
    }
  }

  async function handleSend() {
    if (!approvedMessageId) return;

    setSendLoading(true);
    setError("");
    setNotice("");

    try {
      await sendMessage(approvedMessageId);
      setSent(true);
      setNotice(
        "Message sent through the simulated provider. Delivery is recorded in the case history."
      );
      onChanged?.();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to send the message."
      );
    } finally {
      setSendLoading(false);
    }
  }

  return (
    <section className="message-drafter">
      <div className="message-drafter-heading">
        <div>
          <h3>Patient Message Drafter</h3>
          <p>Create a follow-up message for coordinator review.</p>
        </div>
        <span className="message-drafter-simulated">SIMULATED</span>
      </div>

      <div className="message-drafter-notice">
        All information is synthetic. Messages require coordinator approval.
        Approval does not send a real message.
      </div>

      {!draft && (
        <div className="message-drafter-form">
          <div className="message-drafter-field">
            <label htmlFor="message-language">Message language</label>
            <select
              id="message-language"
              value={language}
              onChange={(event) =>
                setLanguage(event.target.value as "en" | "ar")
              }
              disabled={disabled || loading}
            >
              <option value="en">English</option>
              <option value="ar">Arabic</option>
            </select>
          </div>

          <div className="message-drafter-field">
            <label htmlFor="message-channel">Channel</label>
            <select
              id="message-channel"
              value={channel}
              onChange={(event) =>
                setChannel(event.target.value as "SMS" | "EMAIL")
              }
              disabled={disabled || loading}
            >
              <option value="SMS">SMS</option>
              <option value="EMAIL">Email</option>
            </select>
          </div>

          <div className="message-drafter-field">
            <label htmlFor="message-next-step">Next step for the patient</label>
            <textarea
              id="message-next-step"
              rows={3}
              value={nextStep}
              onChange={(event) => setNextStep(event.target.value)}
              placeholder="e.g. Please visit the clinic for a follow-up appointment."
              disabled={disabled || loading}
            />
          </div>

          <div className="message-drafter-field">
            <label htmlFor="message-contact">Contact details</label>
            <input
              id="message-contact"
              value={contact}
              onChange={(event) => setContact(event.target.value)}
              placeholder="e.g. Facility A clinic, 000-000-0000"
              disabled={disabled || loading}
            />
          </div>

          <p className="message-drafter-urgency">
            Message priority: <strong>{urgency.toUpperCase()}</strong>
            <span>Based on the case priority.</span>
          </p>

          <button
            type="button"
            className="message-drafter-primary"
            onClick={handleGenerate}
            disabled={disabled || loading}
          >
            {loading ? "Generating draft..." : "Generate message draft"}
          </button>
        </div>
      )}

      {draft && (
        <div className="message-drafter-review">
          <div className="message-drafter-review-meta">
            <span>{draft.payload.channel}</span>
            <span>{sent ? "SENT" : draft.status}</span>
            <span>{draft.payload.templateVersion}</span>
          </div>

          <label htmlFor="message-draft-body">Review and edit message</label>
          <textarea
            id="message-draft-body"
            rows={10}
            value={editedBody}
            onChange={(event) => setEditedBody(event.target.value)}
            disabled={draft.status !== "PENDING" || decisionLoading}
          />

          {draft.status === "PENDING" && (
            <div className="message-drafter-actions">
              <button
                type="button"
                className="message-drafter-approve"
                onClick={handleApprove}
                disabled={decisionLoading || !editedBody.trim()}
              >
                {decisionLoading ? "Processing..." : "Approve draft"}
              </button>

              <button
                type="button"
                className="message-drafter-reject"
                onClick={handleReject}
                disabled={decisionLoading}
              >
                Reject draft
              </button>
            </div>
          )}

          {draft.status === "APPROVED" && approvedMessageId && !sent && (
            <div className="message-drafter-actions">
              <button
                type="button"
                className="message-drafter-approve"
                onClick={handleSend}
                disabled={sendLoading}
              >
                {sendLoading ? "Sending..." : "Send approved message"}
              </button>
            </div>
          )}

          {draft.status !== "PENDING" && (
            <button
              type="button"
              className="message-drafter-secondary"
              onClick={() => {
                setDraft(null);
                setEditedBody("");
                setApprovedMessageId(null);
                setSent(false);
                setNotice("");
                setError("");
              }}
            >
              Create another draft
            </button>
          )}
        </div>
      )}

      {error && <p className="message-drafter-error">{error}</p>}
      {notice && <p className="message-drafter-success">{notice}</p>}
    </section>
  );
}
