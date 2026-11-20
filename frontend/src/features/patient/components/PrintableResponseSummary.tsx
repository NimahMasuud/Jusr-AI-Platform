
import { Printer, CheckCircle2, Clock } from "lucide-react";
import type { AssistedResponse } from "./AssistedResponseForm";
import "../assisted-response.css";

interface PrintableResponseSummaryProps {
  response: AssistedResponse;
  patientLabel: string;
  caseId: string;
}

function PrintableResponseSummary({
  response,
  patientLabel,
  caseId,
}: PrintableResponseSummaryProps) {
  const handlePrint = () => {
    window.print();
  };

  const recordedDate = response.recordedAt
    ? new Date(response.recordedAt)
    : null;

  const validRecordedDate =
    recordedDate && !Number.isNaN(recordedDate.getTime());

  const formattedDate = validRecordedDate
    ? recordedDate.toLocaleDateString("en-GB", {
        day: "2-digit",
        month: "long",
        year: "numeric",
      })
    : "Not available";

  const formattedTime = validRecordedDate
    ? recordedDate.toLocaleTimeString("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
      })
    : "Not available";

  const ResponseRow = ({
    label,
    value,
  }: {
    label: string;
    value: string;
  }) => (
    <div className="print-summary-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );

  return (
    <section className="print-summary-container">
      <div className="print-summary-toolbar">
        <div>
          <span className="assisted-eyebrow">RESPONSE RECORD</span>
          <h2>Patient response summary</h2>
          <p>Review the recorded information before printing.</p>
        </div>

        <button type="button" onClick={handlePrint}>
          <Printer size={17} />
          Print summary
        </button>
      </div>

      <div className="print-summary-document">
        <header className="print-summary-header">
          <div>
            <span className="print-summary-brand">JUSR AI</span>
            <p>Patient care response record</p>
          </div>

          <span className="print-summary-status">
            <CheckCircle2 size={15} />
            Recorded
          </span>
        </header>

        <div className="print-summary-patient">
          <div>
            <span>Patient reference</span>
            <strong>{patientLabel}</strong>
          </div>

          <div>
            <span>Case reference</span>
            <strong>{caseId}</strong>
          </div>
        </div>

        <div className="print-summary-section">
          <h3>Recorded responses</h3>

          <ResponseRow
            label="Information received"
            value={response.acknowledged ? "Yes" : "No"}
          />

          <ResponseRow
            label="Understanding"
            value={response.understanding || "Not recorded"}
          />

          <ResponseRow
            label="Confidence rating"
            value={
              response.confidence !== null
                ? `${response.confidence} / 5`
                : "Not recorded"
            }
          />

          <ResponseRow
            label="Result explained"
            value={response.resultExplained ? "Yes" : "No"}
          />

          <ResponseRow
            label="Call-back requested"
            value={response.callbackRequested ? "Yes" : "No"}
          />
        </div>

        <div className="print-summary-section">
          <h3>Recording information</h3>

          <ResponseRow
            label="Recorded by"
            value={response.recordedBy || "Not available"}
          />

          <ResponseRow
            label="Staff role"
            value={response.staffRole || "Not available"}
          />

          <ResponseRow
            label="Date recorded"
            value={formattedDate}
          />

          <ResponseRow
            label="Time recorded"
            value={formattedTime}
          />
        </div>

        <div className="print-summary-attribution">
          <Clock size={17} />

          <div>
            <strong>Recorded by staff on behalf of patient</strong>
            <p>
              These responses were entered by a staff member during an
              assisted interaction. They are not a direct digital
              submission by the patient.
            </p>
          </div>
        </div>

        <footer className="print-summary-footer">
          <p>Jusr AI · Helping you stay informed about your care.</p>
          <span>
            Demonstration record — synthetic data. Not a live hospital record.
          </span>
        </footer>
      </div>
    </section>
  );
}

export default PrintableResponseSummary;
