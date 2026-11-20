import "./patients.css";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Plus,
  Search,
  UserCheck,
  Users,
  X,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import Alert from "../../components/ui/Alert";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../../components/ui/StateViews";
import { useUser } from "../../context/UserContext";
import { createPatient, createSimulationCase, listPatients, type PatientListItem } from "../../services/api/patientsApi";
import { formatDateOnly, initialsOf } from "../../utils/format";

const PAGE_SIZE = 25;

type TreatmentStage =
  | "NOTIFYING"
  | "AWAITING_ACK"
  | "AWAITING_CONFIRMATION"
  | "REFERRAL_PENDING"
  | "AWAITING_APPOINTMENT"
  | "AWAITING_TREATMENT"
  | "READY_TO_CLOSE";

const TREATMENT_STAGES: Array<{ value: TreatmentStage | ""; label: string }> = [
  { value: "", label: "Default — result received, awaiting triage" },
  { value: "NOTIFYING", label: "Notification — informing the patient of the result" },
  { value: "AWAITING_ACK", label: "Awaiting patient acknowledgement" },
  { value: "AWAITING_CONFIRMATION", label: "Awaiting confirmatory test (e.g. colposcopy, biopsy)" },
  { value: "REFERRAL_PENDING", label: "Referral sent — awaiting acceptance" },
  { value: "AWAITING_APPOINTMENT", label: "Awaiting appointment — referral accepted, visit booked" },
  { value: "AWAITING_TREATMENT", label: "In treatment — under active care or monitoring" },
  { value: "READY_TO_CLOSE", label: "Discharge review — care complete, ready to close" },
];

export default function PatientsPage() {
  const navigate = useNavigate();
  const { activeUser } = useUser();
  const [items, setItems] = useState<PatientListItem[]>([]);
  const [skip, setSkip] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [sex, setSex] = useState<"all" | "F" | "M" | "OTHER">("all");
  const [registerOpen, setRegisterOpen] = useState(false);
  const [simulateOpen, setSimulateOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await listPatients({ skip, limit: PAGE_SIZE });
      setItems(result.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load patients.");
    } finally {
      setLoading(false);
    }
  }, [skip]);

  useEffect(() => {
    void load();
  }, [load]);

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return items.filter((patient) => {
      if (sex !== "all" && patient.sex !== sex) return false;
      if (!term) return true;
      return [patient.displayLabel, patient.facility, patient.latestScreening]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(term));
    });
  }, [items, search, sex]);

  const withCases = items.filter((patient) => patient.activeCases > 0).length;
  const canRegister =
    activeUser &&
    ["coordinator", "referring_clinician", "national_admin"].includes(activeUser.role);
  const canSimulate =
    activeUser && ["coordinator", "national_admin"].includes(activeUser.role);

  return (
    <div className="patients-page">
      <header className="patients-page-heading">
        <div>
          <span className="patients-eyebrow">PATIENTS</span>
          <h1>Patients</h1>
          <p>People with a record at your facility, and their cases.</p>
        </div>
        {canRegister && (
          <div className="patients-heading-actions">
            {canSimulate && (
              <button
                type="button"
                className="ui-btn ui-btn-secondary"
                onClick={() => setSimulateOpen(true)}
              >
                <Plus size={15} /> Add simulation case
              </button>
            )}
            <button
              type="button"
              className="ui-btn ui-btn-primary"
              onClick={() => setRegisterOpen(true)}
            >
              <Plus size={15} /> Register patient
            </button>
          </div>
        )}
      </header>

      <section className="patients-stats">
        <article className="patients-stat-card">
          <span className="patients-stat-icon">
            <Users size={20} />
          </span>
          <div>
            <span>On this page</span>
            <strong>{items.length}</strong>
          </div>
        </article>
        <article className="patients-stat-card">
          <span className="patients-stat-icon active">
            <UserCheck size={20} />
          </span>
          <div>
            <span>With an active case</span>
            <strong>{withCases}</strong>
          </div>
        </article>
      </section>

      <section className="patients-directory">
        <div className="patients-directory-heading">
          <div>
            <h2>Patient directory</h2>
            <p>Select a patient to see their details, cases and messages.</p>
          </div>
          <span className="patients-result-count">{visible.length} shown</span>
        </div>

        <div className="patients-filters">
          <label className="patients-search">
            <Search size={15} />
            <input
              type="search"
              placeholder="Search this page by name, facility or screening"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <label className="patients-filter-select">
            <select
              value={sex}
              onChange={(event) =>
                setSex(event.target.value as "all" | "F" | "M" | "OTHER")
              }
              aria-label="Filter by sex"
            >
              <option value="all">All sexes</option>
              <option value="F">Female</option>
              <option value="M">Male</option>
              <option value="OTHER">Other</option>
            </select>
          </label>
        </div>

        {error ? (
          <ErrorState message={error} onRetry={() => void load()} />
        ) : loading ? (
          <LoadingState message="Loading patients…" />
        ) : visible.length === 0 ? (
          <EmptyState
            title="No patients found"
            message="Register a patient or adjust the search."
          />
        ) : (
          <>
            <div className="patients-table-wrapper">
              <table className="patients-table">
                <thead>
                  <tr>
                    <th>Patient</th>
                    <th>Facility</th>
                    <th>Latest screening</th>
                    <th>Active cases</th>
                    <th>Last updated</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {visible.map((patient) => (
                    <tr key={patient.id}>
                      <td>
                        <div className="patients-table-person">
                          <span className="patients-avatar">
                            {initialsOf(patient.displayLabel)}
                          </span>
                          <div>
                            <strong>{patient.displayLabel}</strong>
                            <span>
                              {patient.ageYears ? `${patient.ageYears}y` : "Age unknown"}
                              {patient.sex ? ` · ${patient.sex}` : ""}
                            </span>
                          </div>
                        </div>
                      </td>
                      <td>{patient.facility}</td>
                      <td>{patient.latestScreening}</td>
                      <td>
                        <span
                          className={`patients-case-count ${
                            patient.activeCases > 0 ? "has-cases" : "no-cases"
                          }`}
                        >
                          {patient.activeCases}
                        </span>
                      </td>
                      <td>{formatDateOnly(patient.lastUpdated)}</td>
                      <td>
                        <button
                          type="button"
                          className="patients-view-button"
                          onClick={() => navigate(`/patients/${patient.id}`)}
                        >
                          View
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="ui-pagination">
              <span>
                Showing {skip + 1}–{skip + items.length}
              </span>
              <div className="ui-pagination-controls">
                <button
                  type="button"
                  className="ui-btn ui-btn-secondary ui-btn-sm"
                  disabled={skip === 0}
                  onClick={() => setSkip(Math.max(0, skip - PAGE_SIZE))}
                >
                  <ChevronLeft size={14} /> Previous
                </button>
                <button
                  type="button"
                  className="ui-btn ui-btn-secondary ui-btn-sm"
                  disabled={items.length < PAGE_SIZE}
                  onClick={() => setSkip(skip + PAGE_SIZE)}
                >
                  Next <ChevronRight size={14} />
                </button>
              </div>
            </div>
          </>
        )}
      </section>

      {registerOpen && (
        <RegisterPatientDialog
          onClose={() => setRegisterOpen(false)}
          onCreated={(patientId) => {
            setRegisterOpen(false);
            navigate(`/patients/${patientId}`);
          }}
        />
      )}

      {simulateOpen && (
        <SimulationCaseDialog
          onClose={() => setSimulateOpen(false)}
          onCreated={(caseId) => {
            setSimulateOpen(false);
            navigate(`/worklist?caseId=${encodeURIComponent(caseId)}`);
          }}
        />
      )}
    </div>
  );
}

function RegisterPatientDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (patientId: string) => void;
}) {
  const [displayLabel, setDisplayLabel] = useState("");
  const [age, setAge] = useState("");
  const [sex, setSex] = useState("F");
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit() {
    setBusy(true);
    setError("");
    try {
      const created = await createPatient({
        displayLabel: displayLabel.trim(),
        ageYears: age ? Number(age) : null,
        sex: sex || null,
        phone: phone.trim() || null,
      });
      onCreated(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to register the patient.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ui-modal-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="ui-modal" role="dialog" aria-modal="true" aria-label="Register patient">
        <div className="ui-modal-header">
          <h3>Register a patient</h3>
          <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        <div className="ui-modal-body">
          {error && <Alert tone="danger">{error}</Alert>}
          <div className="ui-field">
            <label>Patient name or label</label>
            <input
              value={displayLabel}
              onChange={(event) => setDisplayLabel(event.target.value)}
              placeholder="Use a synthetic label, never real identifiable data"
            />
          </div>
          <div className="ui-field">
            <label>Age (years)</label>
            <input
              type="number"
              min={0}
              max={130}
              value={age}
              onChange={(event) => setAge(event.target.value)}
            />
          </div>
          <div className="ui-field">
            <label>Sex</label>
            <select value={sex} onChange={(event) => setSex(event.target.value)}>
              <option value="F">Female</option>
              <option value="M">Male</option>
              <option value="OTHER">Other</option>
            </select>
          </div>
          <div className="ui-field">
            <label>Mobile phone (for the SMS patient link)</label>
            <input
              value={phone}
              onChange={(event) => setPhone(event.target.value)}
              placeholder="e.g. +233 20 000 0000"
              inputMode="tel"
            />
          </div>
          <div className="ui-field">
            <span className="ui-hint">
              This demo stores synthetic patients only. The phone number is used
              only for simulated SMS delivery of secure links.
            </span>
          </div>
        </div>
        <div className="ui-modal-footer">
          <button type="button" className="ui-btn ui-btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="ui-btn ui-btn-primary"
            disabled={busy || !displayLabel.trim()}
            onClick={() => void submit()}
          >
            Register patient
          </button>
        </div>
      </div>
    </div>
  );
}

function SimulationCaseDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (caseId: string) => void;
}) {
  const [displayLabel, setDisplayLabel] = useState("");
  const [age, setAge] = useState("");
  const [sex, setSex] = useState("F");
  const [phone, setPhone] = useState("");
  const [screeningType, setScreeningType] = useState("Cervical screening");
  const [outcome, setOutcome] = useState("Abnormal");
  const [priority, setPriority] = useState<"NORMAL" | "URGENT">("URGENT");
  const [nextAction, setNextAction] = useState(
    "Review the screening result with the patient"
  );
  const [confirmatory, setConfirmatory] = useState(true);
  const [stage, setStage] = useState<TreatmentStage | "">("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit() {
    setBusy(true);
    setError("");
    try {
      const created = await createSimulationCase({
        displayLabel: displayLabel.trim(),
        ageYears: age ? Number(age) : null,
        sex: sex || null,
        phone: phone.trim() || null,
        screeningType: screeningType.trim(),
        outcome: outcome.trim(),
        priority,
        confirmatoryRequired: confirmatory,
        nextActionLabel: nextAction.trim() || undefined,
        initialStatus: stage || undefined,
      });
      onCreated(created.caseNumber || created.caseId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to add the simulation case.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ui-modal-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="ui-modal" role="dialog" aria-modal="true" aria-label="Add simulation case">
        <div className="ui-modal-header">
          <h3>Add a simulation case</h3>
          <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        <div className="ui-modal-body">
          {error && <Alert tone="danger">{error}</Alert>}
          <p className="ui-hint" style={{ marginTop: 0 }}>
            Coordinator onboarding: registers a synthetic patient, records a
            screening result and opens a case with a generated case ID.
          </p>
          <div className="ui-field">
            <label>Patient name or label</label>
            <input
              value={displayLabel}
              onChange={(event) => setDisplayLabel(event.target.value)}
              placeholder="e.g. Demo Patient 12"
            />
          </div>
          <div className="ui-field">
            <label>Age (years)</label>
            <input
              type="number"
              min={0}
              max={130}
              value={age}
              onChange={(event) => setAge(event.target.value)}
            />
          </div>
          <div className="ui-field">
            <label>Sex</label>
            <select value={sex} onChange={(event) => setSex(event.target.value)}>
              <option value="F">Female</option>
              <option value="M">Male</option>
              <option value="OTHER">Other</option>
            </select>
          </div>
          <div className="ui-field">
            <label>Mobile phone (SMS patient link)</label>
            <input
              value={phone}
              onChange={(event) => setPhone(event.target.value)}
              placeholder="e.g. +233 20 000 0000"
              inputMode="tel"
            />
          </div>
          <div className="ui-field">
            <label>Screening type</label>
            <input
              value={screeningType}
              onChange={(event) => setScreeningType(event.target.value)}
            />
          </div>
          <div className="ui-field">
            <label>Outcome</label>
            <select value={outcome} onChange={(event) => setOutcome(event.target.value)}>
              <option value="Abnormal">Abnormal / positive</option>
              <option value="Normal">Normal</option>
              <option value="Inconclusive">Inconclusive</option>
            </select>
          </div>
          <div className="ui-field">
            <label>Priority</label>
            <select
              value={priority}
              onChange={(event) => setPriority(event.target.value as "NORMAL" | "URGENT")}
            >
              <option value="URGENT">Urgent</option>
              <option value="NORMAL">Routine</option>
            </select>
          </div>
          <div className="ui-field">
            <label>Next action</label>
            <input value={nextAction} onChange={(event) => setNextAction(event.target.value)} />
          </div>
          <div className="ui-field">
            <label>Treatment stage</label>
            <select
              value={stage}
              onChange={(event) => setStage(event.target.value as TreatmentStage | "")}
            >
              {TREATMENT_STAGES.map((option) => (
                <option key={option.value || "default"} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <span className="ui-hint">
              Starts the simulated case at a later care-pathway stage, e.g.
              “Awaiting appointment” (referral accepted, visit booked) or
              “Confirmatory testing” (colposcopy, biopsy), so the patient view can
              be previewed at that stage.
            </span>
          </div>
          <label className="ui-checkbox">
            <input
              type="checkbox"
              checked={confirmatory}
              onChange={(event) => setConfirmatory(event.target.checked)}
            />
            <span>Confirmatory test required</span>
          </label>
        </div>
        <div className="ui-modal-footer">
          <button type="button" className="ui-btn ui-btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="ui-btn ui-btn-primary"
            disabled={busy || !displayLabel.trim()}
            onClick={() => void submit()}
          >
            {busy ? "Creating…" : "Create case"}
          </button>
        </div>
      </div>
    </div>
  );
}
