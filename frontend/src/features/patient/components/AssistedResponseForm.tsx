
import { useState } from "react";
import { CheckCircle2, Circle, Phone, UserRound } from "lucide-react";
import "../assisted-response.css";

export interface AssistedResponse {
  acknowledged: boolean;
  understanding: "Yes" | "Partly" | "No" | "";
  confidence: number | null;
  resultExplained: boolean;
  callbackRequested: boolean;
  recordedBy: string;
  staffRole: string;
  recordedAt: string;
}

interface AssistedResponseFormProps {
  onSubmit: (response: AssistedResponse) => Promise<void> | void;
}

function AssistedResponseForm({ onSubmit }: AssistedResponseFormProps) {
  const [acknowledged, setAcknowledged] = useState(false);
  const [understanding, setUnderstanding] =
    useState<AssistedResponse["understanding"]>("");
  const [confidence, setConfidence] = useState<number | null>(null);
  const [resultExplained, setResultExplained] = useState(false);
  const [callbackRequested, setCallbackRequested] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [saving, setSaving] = useState(false);

  const canSubmit =
    acknowledged && understanding !== "" && confidence !== null;

  const handleSubmit = async () => {
    if (!canSubmit || submitted || saving) return;

    const response: AssistedResponse = {
      acknowledged,
      understanding,
      confidence,
      resultExplained,
      callbackRequested,
      recordedBy: "",
      staffRole: "",
      recordedAt: "",
    };

    setSaving(true);

    try {
      await onSubmit(response);
      setSubmitted(true);
    } catch {
      // Keep the form available so the staff member can retry.
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="assisted-response-form">
      <div className="assisted-form-header">
        <div className="assisted-form-icon">
          <Phone size={20} />
        </div>

        <div>
          <span className="assisted-eyebrow">STAFF-ASSISTED RESPONSE</span>
          <h2>Record patient response</h2>
          <p>
            Record the patient's answers on their behalf during a phone call or
            in-person interaction.
          </p>
        </div>
      </div>

      <div className="assisted-question">
        <h3>1. Has the patient received this information?</h3>

        <button
          type="button"
          className={`assisted-option ${acknowledged ? "selected" : ""}`}
          disabled={submitted || saving}
          onClick={() => setAcknowledged(!acknowledged)}
          aria-pressed={acknowledged}
        >
          {acknowledged ? <CheckCircle2 size={19} /> : <Circle size={19} />}
          Yes, the patient has received the information
        </button>
      </div>

      <div className="assisted-question">
        <h3>2. Does the patient understand what the result means?</h3>

        <div className="assisted-choice-list">
          {(["Yes", "Partly", "No"] as const).map((option) => (
            <button
              key={option}
              type="button"
              disabled={submitted || saving}
              className={`assisted-choice ${
                understanding === option ? "selected" : ""
              }`}
              onClick={() => setUnderstanding(option)}
              aria-pressed={understanding === option}
            >
              {option}
            </button>
          ))}
        </div>
      </div>

      <div className="assisted-question">
        <h3>3. How confident is the patient about the next step?</h3>
        <p>1 means not confident; 5 means very confident.</p>

        <div className="assisted-confidence-list">
          {[1, 2, 3, 4, 5].map((rating) => (
            <button
              key={rating}
              type="button"
              disabled={submitted || saving}
              className={`assisted-confidence ${
                confidence === rating ? "selected" : ""
              }`}
              onClick={() => setConfidence(rating)}
              aria-pressed={confidence === rating}
            >
              {rating}
            </button>
          ))}
        </div>
      </div>

      <div className="assisted-question">
        <h3>4. Was the result explained to the patient?</h3>

        <button
          type="button"
          className={`assisted-option ${resultExplained ? "selected" : ""}`}
          disabled={submitted || saving}
          onClick={() => setResultExplained(!resultExplained)}
          aria-pressed={resultExplained}
        >
          {resultExplained ? <CheckCircle2 size={19} /> : <Circle size={19} />}
          Yes, the result was explained
        </button>
      </div>

      <div className="assisted-question">
        <h3>5. Does the patient want someone to call them again?</h3>

        <button
          type="button"
          disabled={submitted || saving}
          className={`assisted-option ${callbackRequested ? "selected" : ""}`}
          onClick={() => setCallbackRequested(!callbackRequested)}
          aria-pressed={callbackRequested}
        >
          <Phone size={18} />
          {callbackRequested ? "Call-back requested" : "Request a call-back"}
        </button>
      </div>

      {submitted && (
        <div className="assisted-staff-notice" role="status">
          <UserRound size={18} />
          <div>
            <strong>Recorded by staff on behalf of patient</strong>
            <span>Authenticated staff recording</span>
          </div>
        </div>
      )}

      <div className="assisted-form-submit">
        {!submitted ? (
          <>
            <button
              type="button"
              disabled={!canSubmit || saving}
              onClick={handleSubmit}
            >
              <CheckCircle2 size={17} />
              {saving ? "Saving response..." : "Save patient response"}
            </button>

            <p>
              Acknowledgement, understanding and confidence are required.
            </p>
          </>
        ) : (
          <div className="assisted-saved-message" role="status">
            <CheckCircle2 size={19} />
            Patient response recorded successfully.
          </div>
        )}
      </div>
    </section>
  );
}

export default AssistedResponseForm;
