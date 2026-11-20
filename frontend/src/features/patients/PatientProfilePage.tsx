import "./patient-profile.css";
import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  ArrowLeft,
  ArrowUpRight,
  CalendarDays,
  ClipboardList,
  Link2,
  MessageSquare,
  Plus,
  UserRound,
  X,
} from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import Alert from "../../components/ui/Alert";
import StatusBadge from "../../components/ui/StatusBadge";
import { PriorityBadge } from "../../components/ui/FlagBadges";
import { LoadingState } from "../../components/ui/StateViews";
import { useUser } from "../../context/UserContext";
import type { CaseStatus, Priority } from "../../services/api/v6.types";
import { getPatientProfile, type PatientProfile } from "../../services/api/patientsApi";
import { createCase } from "../../services/api/casesApi";
import { formatDateOnly, formatDateTime, humanize, initialsOf } from "../../utils/format";

function linkStatusClass(status: string) {
  const value = status.toLowerCase().replaceAll(" ", "-");
  return `patient-profile-status status-${value}`;
}

export default function PatientProfilePage() {
  const { patientId } = useParams<{ patientId: string }>();
  const navigate = useNavigate();
  const { activeUser } = useUser();
  const [profile, setProfile] = useState<PatientProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [caseDialogOpen, setCaseDialogOpen] = useState(false);

  const load = useCallback(async () => {
    if (!patientId) return;
    setLoading(true);
    setError("");
    try {
      setProfile(await getPatientProfile(patientId));
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load this patient."
      );
    } finally {
      setLoading(false);
    }
  }, [patientId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!patientId) {
    return null;
  }

  if (loading) {
    return (
      <div className="patient-profile-page">
        <LoadingState message="Loading patient…" />
      </div>
    );
  }

  if (error || !profile) {
    return (
      <div className="patient-profile-page">
        <button type="button" className="patient-profile-back" onClick={() => navigate("/patients")}>
          <ArrowLeft size={14} /> Back to patients
        </button>
        <div className="patients-empty">
          <AlertCircle size={22} />
          <strong>Unable to load patient</strong>
          <p>{error || "Patient not found."}</p>
        </div>
      </div>
    );
  }

  const { patient } = profile;
  const activeCases = profile.cases.filter((item) => item.status !== "CLOSED").length;
  const latestScreening = profile.screenings[0];
  const latestCase = profile.cases[0];
  const canCreateCase =
    activeUser &&
    ["coordinator", "national_admin"].includes(activeUser.role);

  return (
    <div className="patient-profile-page">
      <button type="button" className="patient-profile-back" onClick={() => navigate("/patients")}>
        <ArrowLeft size={14} /> Back to patients
      </button>

      <header className="patient-profile-heading">
        <span className="patient-profile-avatar">
          {initialsOf(patient.displayLabel)}
        </span>
        <div>
          <span className="patients-eyebrow">PATIENT RECORD</span>
          <h1>{patient.displayLabel}</h1>
          <p>
            {patient.ageYears ? `${patient.ageYears} years` : "Age not recorded"}
            {patient.sex ? ` · ${patient.sex}` : ""}
            {patient.isSynthetic ? " · Synthetic record" : ""}
          </p>
        </div>
        {canCreateCase && (
          <button
            type="button"
            className="ui-btn ui-btn-primary"
            style={{ marginLeft: "auto" }}
            onClick={() => setCaseDialogOpen(true)}
          >
            <Plus size={15} /> Open a case
          </button>
        )}
      </header>

      <section className="patient-profile-overview">
        <div className="patient-profile-section-heading">
          <UserRound size={17} />
          <h2>At a glance</h2>
        </div>
        <div className="patient-profile-grid">
          <div>
            <span>Active cases</span>
            <strong>{activeCases}</strong>
          </div>
          <div>
            <span>Latest screening</span>
            <strong>{latestScreening ? latestScreening.screeningType : "Not recorded"}</strong>
          </div>
          <div>
            <span>Latest result</span>
            <strong>{latestScreening ? latestScreening.result : "Not recorded"}</strong>
          </div>
          <div>
            <span>Patient link</span>
            <strong>{profile.patientLink.status}</strong>
          </div>
        </div>
        {profile.patientLink.expiresAt && (
          <p className="patient-profile-muted">
            Latest patient link expires {formatDateTime(profile.patientLink.expiresAt)}.
            Link tokens are never shown to staff.
          </p>
        )}
      </section>

      <section className="patient-profile-overview">
        <div className="patient-profile-section-heading">
          <ClipboardList size={17} />
          <h2>Cases</h2>
        </div>
        {profile.cases.length === 0 ? (
          <p className="patient-profile-muted">No cases visible for this patient.</p>
        ) : (
          <div className="patient-profile-cases">
            {profile.cases.map((item) => (
              <button
                key={item.id}
                type="button"
                className="patient-profile-case patient-profile-case-button"
                onClick={() => navigate(`/worklist?caseId=${encodeURIComponent(item.id)}`)}
              >
                <div>
                  <strong>{item.caseNumber}</strong>
                  <span>
                    {item.screeningType} — {item.screeningResult}
                  </span>
                </div>
                <div>
                  <span>Status</span>
                  <StatusBadge status={item.status as CaseStatus} />
                </div>
                <div>
                  <span>Priority</span>
                  <PriorityBadge priority={item.priority.toUpperCase() as Priority} />
                </div>
                <div>
                  <span>Owner</span>
                  <strong>{item.assignedTo ?? "Unassigned"}</strong>
                </div>
                <div>
                  <span>Facility</span>
                  <strong>{item.facility}</strong>
                </div>
                <div>
                  <span>Next action</span>
                  <strong>{item.nextAction ?? "—"}</strong>
                </div>
                <div>
                  <span>Updated</span>
                  <strong>{formatDateOnly(item.lastUpdated ?? item.createdAt)}</strong>
                </div>
                <span className="patient-profile-case-action">
                  Open <ArrowUpRight size={14} />
                </span>
              </button>
            ))}
          </div>
        )}
      </section>

      <section className="patient-profile-overview">
        <div className="patient-profile-section-heading">
          <CalendarDays size={17} />
          <h2>Screening history</h2>
        </div>
        {profile.screenings.length === 0 ? (
          <p className="patient-profile-muted">No screenings recorded.</p>
        ) : (
          <div className="patient-profile-history">
            {profile.screenings.map((item) => (
              <div className="patient-profile-history-item" key={item.id}>
                <div className="patient-profile-history-main">
                  <strong>{item.screeningType}</strong>
                  <span>
                    {item.result} · {item.facility}
                  </span>
                </div>
                <span>{formatDateOnly(item.date)}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="patient-profile-overview">
        <div className="patient-profile-section-heading">
          <MessageSquare size={17} />
          <h2>Communications</h2>
        </div>
        {profile.communications.length === 0 ? (
          <p className="patient-profile-muted">No messages have been drafted for this patient.</p>
        ) : (
          <div className="patient-profile-history">
            {profile.communications.map((item) => (
              <div className="patient-profile-history-item" key={item.id}>
                <div className="patient-profile-history-main">
                  <strong>{humanize(item.channel)}</strong>
                  <span>{item.description}</span>
                </div>
                <span className={linkStatusClass(item.status)}>{item.status}</span>
                <span>{formatDateOnly(item.date)}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="patient-profile-overview">
        <div className="patient-profile-section-heading">
          <Link2 size={17} />
          <h2>Patient links</h2>
        </div>
        {profile.patientLinks.length === 0 ? (
          <p className="patient-profile-muted">
            No patient link has been generated. Generate one from the case once the
            message is approved.
          </p>
        ) : (
          <div className="patient-profile-history">
            {profile.patientLinks.map((link) => (
              <div className="patient-profile-history-item" key={link.id}>
                <div className="patient-profile-history-main">
                  <strong>Case {link.caseId.slice(0, 8)}…</strong>
                  <span>Created {formatDateTime(link.createdAt)}</span>
                </div>
                <span className={linkStatusClass(link.status)}>{humanize(link.status)}</span>
                <span>Expires {formatDateOnly(link.expiresAt)}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      {latestCase && (
        <p className="patient-profile-muted">
          Latest case created {formatDateOnly(latestCase.createdAt)} at {latestCase.facility}.
        </p>
      )}

      {caseDialogOpen && (
        <OpenCaseDialog
          patientId={patient.id}
          patientLabel={patient.displayLabel}
          onClose={() => setCaseDialogOpen(false)}
          onCreated={(caseRecordId) => {
            setCaseDialogOpen(false);
            navigate(`/worklist?caseId=${encodeURIComponent(caseRecordId)}`);
          }}
        />
      )}
    </div>
  );
}

function OpenCaseDialog({
  patientId,
  patientLabel,
  onClose,
  onCreated,
}: {
  patientId: string;
  patientLabel: string;
  onClose: () => void;
  onCreated: (caseRecordId: string) => void;
}) {
  const [caseNumber, setCaseNumber] = useState("");
  const [priority, setPriority] = useState<Priority>("NORMAL");
  const [nextActionLabel, setNextActionLabel] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [confirmatory, setConfirmatory] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit() {
    setBusy(true);
    setError("");
    try {
      const created = await createCase({
        patientId,
        caseId: caseNumber.trim(),
        priority,
        nextActionLabel: nextActionLabel.trim() || undefined,
        nextActionCode: nextActionLabel ? "MANUAL_ENTRY" : undefined,
        requiredSpecialty: specialty.trim().toUpperCase() || undefined,
        confirmatoryRequired: confirmatory,
      });
      onCreated(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create the case.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ui-modal-overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="ui-modal" role="dialog" aria-modal="true" aria-label="Open a case">
        <div className="ui-modal-header">
          <div>
            <h3>Open a case for {patientLabel}</h3>
            <p>Manual entry starts at T1, then T2 because a person matched the patient.</p>
          </div>
          <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>
        <div className="ui-modal-body">
          {error && <Alert tone="danger">{error}</Alert>}
          <div className="ui-field">
            <label>Case number</label>
            <input
              value={caseNumber}
              onChange={(event) => setCaseNumber(event.target.value)}
              placeholder="e.g. JC-2026-0101"
            />
          </div>
          <div className="ui-field">
            <label>Priority</label>
            <select
              value={priority}
              onChange={(event) => setPriority(event.target.value as Priority)}
            >
              <option value="NORMAL">Normal</option>
              <option value="HIGH">High</option>
              <option value="URGENT">Urgent</option>
            </select>
          </div>
          <div className="ui-field">
            <label>Next action (optional)</label>
            <input
              value={nextActionLabel}
              onChange={(event) => setNextActionLabel(event.target.value)}
              placeholder="e.g. Review screening result"
            />
          </div>
          <div className="ui-field">
            <label>Required specialty (optional)</label>
            <input
              value={specialty}
              onChange={(event) => setSpecialty(event.target.value)}
              placeholder="e.g. CARDIOLOGY"
            />
          </div>
          <label className="ui-checkbox">
            <input
              type="checkbox"
              checked={confirmatory}
              onChange={(event) => setConfirmatory(event.target.checked)}
            />
            Confirmatory result required
          </label>
        </div>
        <div className="ui-modal-footer">
          <button type="button" className="ui-btn ui-btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="ui-btn ui-btn-primary"
            disabled={busy || !caseNumber.trim()}
            onClick={() => void submit()}
          >
            Create case
          </button>
        </div>
      </div>
    </div>
  );
}
