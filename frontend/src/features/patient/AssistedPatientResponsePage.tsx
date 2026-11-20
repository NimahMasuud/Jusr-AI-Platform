import { useSearchParams, useNavigate } from "react-router-dom";
import { useState } from "react";
import { ArrowLeft, ClipboardList, UserRound } from "lucide-react";

import AssistedResponseForm, {
  type AssistedResponse,
} from "./components/AssistedResponseForm";

import PrintableResponseSummary from "./components/PrintableResponseSummary";
import { recordAssistedPatientResponse } from "./patientAccessService";

import "./assisted-response.css";

function AssistedPatientResponsePage() {
  const [response, setResponse] = useState<AssistedResponse | null>(null);
  const [error, setError] = useState("");

  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const patientLabel = searchParams.get("patient") || "Patient";
  const caseId = searchParams.get("caseId") || "";

  const handleResponseSubmit = async (submittedResponse: AssistedResponse) => {
    setError("");

    if (!caseId) {
      setError("A valid case reference is required to record this response.");
      return;
    }

    try {
      const result = await recordAssistedPatientResponse(caseId, {
        acknowledged: submittedResponse.acknowledged,
        understood_level:
          submittedResponse.understanding === "Yes"
            ? "YES"
            : submittedResponse.understanding === "Partly"
              ? "PARTLY"
              : "NO",
        confidence: submittedResponse.confidence ?? 1,
        explanationStatus: submittedResponse.resultExplained
          ? "EXPLAINED"
          : "NOT_EXPLAINED",
        callbackRequested: submittedResponse.callbackRequested,
      });

      setResponse({
        ...submittedResponse,
        recordedBy: result.recordedBy.displayName,
        staffRole: result.recordedBy.role,
        recordedAt: result.recordedAt,
      });
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to save the patient response. Please try again.",
      );

      throw err;
    }
  };

  return (
    <main className="assisted-page">
      <header className="assisted-page-header">
        <div>
          <span className="assisted-eyebrow">JUSR AI · CARE COORDINATION</span>

          <h1>Assisted patient response</h1>

          <p>
            Record patient feedback when a patient cannot use the digital
            patient access page.
          </p>
        </div>
      </header>

      <div className="assisted-page-content">
        <button
          type="button"
          className="assisted-back-button"
          onClick={() => window.history.back()}
        >
          <ArrowLeft size={17} />
          Back
        </button>

        <section className="assisted-patient-context">
          <div className="assisted-patient-avatar">
            <UserRound size={22} />
          </div>

          <div className="assisted-patient-details">
            <span>Patient reference</span>
            <h2>{patientLabel}</h2>

            <p>
              <ClipboardList size={14} />
              {caseId || "No case reference"}
            </p>
          </div>

          <span className="assisted-demo-badge">Synthetic demo record</span>
        </section>

        {error && (
          <div className="assisted-page-error" role="alert">
            <strong>Response not saved</strong>
            <p>{error}</p>
          </div>
        )}

        {!response ? (
          <AssistedResponseForm onSubmit={handleResponseSubmit} />
        ) : (
          <>
            <div className="assisted-page-success" role="status">
              <strong>Response recorded</strong>
              <p>
                The patient's responses have been saved successfully. The
                recording is attributed to the authenticated staff member.
              </p>
            </div>

            <PrintableResponseSummary
              response={response}
              patientLabel={patientLabel}
              caseId={caseId}
            />

            <button
              type="button"
              className="assisted-back-button"
              onClick={() =>
                navigate("/worklist", {
                  state: {
                    assistedResponseRecorded: true,
                    caseId,
                    recordedAt: response.recordedAt,
                    recordedBy: response.recordedBy,
                    staffRole: response.staffRole,
                  },
                })
              }
            >
              <ArrowLeft size={17} />
              Return to worklist
            </button>
          </>
        )}

        <div className="assisted-page-disclaimer">
          <strong>Demonstration only</strong>
          <p>
            This application uses synthetic patient records and simulated
            workflows. Staff-assisted responses are saved to the demonstration
            backend. It is not connected to live hospital systems.
          </p>
        </div>
      </div>
    </main>
  );
}

export default AssistedPatientResponsePage;
