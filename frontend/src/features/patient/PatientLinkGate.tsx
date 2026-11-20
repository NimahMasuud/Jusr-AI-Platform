import "./patient-link.css";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useParams } from "react-router-dom";
import {
  ShieldAlert,
  Clock,
  Link2Off,
  AlertCircle,
  RefreshCw,
  LockKeyhole,
  CalendarDays,
  CheckCircle2,
  LoaderCircle,
} from "lucide-react";
import PatientPage from "./PatientPage";
import jusrLogo from "../../assets/jusr-logo-cropped.png";
import {
  getPatientPortalContext,
  verifyPatientLink,
} from "./patientAccessService";
import { ApiRequestError } from "../../services/api/apiClient";

type GateStatus =
  | "loading"
  | "verification"
  | "ready"
  | "expired"
  | "replaced"
  | "locked"
  | "invalid"
  | "error";

const linkMessages = {
  expired: {
    title: "This link has expired",
    description:
      "For your security, this patient access link is no longer available. Please contact your healthcare team for a new link.",
    icon: Clock,
  },
  replaced: {
    title: "This link is no longer active",
    description:
      "A newer patient access link has been issued. Please use the latest link you received.",
    icon: Link2Off,
  },
  locked: {
    title: "Access temporarily locked",
    description:
      "For your security, this link has been locked after unsuccessful identity checks. Please contact your healthcare team for assistance.",
    icon: LockKeyhole,
  },
  invalid: {
    title: "Unable to access this page",
    description:
      "This link is invalid or cannot be recognised. Please check the link or contact your healthcare team.",
    icon: ShieldAlert,
  },
  error: {
    title: "Unable to load your page",
    description:
      "We could not connect to the patient service. Please try again in a moment.",
    icon: AlertCircle,
  },
};

function getApiError(error: unknown) {
  if (error instanceof ApiRequestError) return error;
  return null;
}

function PatientLinkGate() {
  const { linkToken } = useParams<{ linkToken: string }>();
  const [status, setStatus] = useState<GateStatus>("loading");
  const [birthYear, setBirthYear] = useState("");
  const [sessionToken, setSessionToken] = useState<string | null>(null);

  const [verificationError, setVerificationError] = useState("");
  const [attemptsRemaining, setAttemptsRemaining] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  async function loadPortal(token: string, patientSession: string | null) {
    try {
      await getPatientPortalContext(token, patientSession);
      setStatus("ready");
    } catch (error) {
      const apiError = getApiError(error);
      if (apiError?.code === "VERIFICATION_REQUIRED") {
        setStatus("verification");
        return;
      }
      if (apiError?.code === "LINK_EXPIRED" || apiError?.status === 410) {
        setStatus(apiError.code === "LINK_SUPERSEDED" ? "replaced" : "expired");
        return;
      }
      if (apiError?.code === "LINK_SUPERSEDED") {
        setStatus("replaced");
        return;
      }
      if (apiError?.code === "LINK_LOCKED" || apiError?.status === 423) {
        setStatus("locked");
        return;
      }
      if (apiError?.status === 404) {
        setStatus("invalid");
        return;
      }
      setStatus("error");
    }
  }

  useEffect(() => {
    if (!linkToken) {
      setStatus("invalid");
      return;
    }
    void loadPortal(linkToken, null);
    // A token identifies one public patient link; load once when it changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [linkToken]);

  async function handleVerification(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!linkToken || !/^\d{4}$/.test(birthYear) || busy) return;

    setBusy(true);
    setVerificationError("");
    try {
      const result = await verifyPatientLink(linkToken, Number(birthYear));
      const patientSession = result.sessionToken;
      setSessionToken(patientSession);
      await loadPortal(linkToken, patientSession);
    } catch (error) {
      const apiError = getApiError(error);
      const details = apiError?.details as
        | { attemptsRemaining?: number }
        | null
        | undefined;

      if (apiError?.code === "LINK_LOCKED" || apiError?.status === 423) {
        setStatus("locked");
      } else if (apiError?.code === "LINK_EXPIRED" || apiError?.status === 410) {
        setStatus(apiError.code === "LINK_SUPERSEDED" ? "replaced" : "expired");
      } else if (apiError?.code === "LINK_SUPERSEDED") {
        setStatus("replaced");
      } else if (apiError?.code === "VERIFICATION_FAILED") {
        const remaining = details?.attemptsRemaining;
        setAttemptsRemaining(typeof remaining === "number" ? remaining : null);
        setVerificationError(
          remaining === 1
            ? "That birth year does not match. You have 1 attempt remaining."
            : typeof remaining === "number"
              ? `That birth year does not match. You have ${remaining} attempts remaining.`
              : "That birth year does not match. Please try again."
        );
      } else {
        setVerificationError(
          error instanceof Error ? error.message : "Unable to verify your identity. Please try again."
        );
      }
      setBirthYear("");
    } finally {
      setBusy(false);
    }
  }

  if (status === "ready" && linkToken) {
    return (
      <PatientPage
        linkToken={linkToken}
        sessionToken={sessionToken}
      />
    );
  }

  const messageKey =
    status === "expired" || status === "replaced" || status === "locked" || status === "invalid"
      ? status
      : "error";
  const message = linkMessages[messageKey];
  const MessageIcon = message.icon;

  return (
    <main className="patient-link-page" lang="en" dir="ltr">
      <header className="patient-link-header">
        <img src={jusrLogo} alt="Jusr AI" />
        <span>
          <ShieldAlert size={15} />
          Secure patient access
        </span>
      </header>

      <div className="patient-link-content">
        <div className="patient-link-card">
          {status === "loading" ? (
            <>
              <div className="patient-link-icon"><LoaderCircle size={30} /></div>
              <span className="patient-link-eyebrow">JUSR AI PATIENT ACCESS</span>
              <h1>Opening your secure page</h1>
              <p>Please wait while we verify your patient access link.</p>
            </>
          ) : status === "verification" ? (
            <>
              <div className="patient-link-icon"><ShieldAlert size={30} /></div>
              <span className="patient-link-eyebrow">JUSR AI PATIENT ACCESS</span>
              <h1>Verify your identity</h1>
              <p>
                To protect your personal health information, please confirm your year of birth before continuing.
              </p>
              <form className="patient-verification-form" onSubmit={handleVerification}>
                <label htmlFor="birth-year">
                  <CalendarDays size={17} />
                  Year of birth
                </label>
                <input
                  id="birth-year"
                  type="number"
                  inputMode="numeric"
                  placeholder="e.g. 1990"
                  min="1900"
                  max={new Date().getFullYear()}
                  value={birthYear}
                  onChange={(event) => setBirthYear(event.target.value)}
                  required
                />
                {verificationError && (
                  <p className="patient-verification-error" role="alert">
                    <AlertCircle size={16} />
                    {verificationError}
                  </p>
                )}
                <button
                  type="submit"
                  className="patient-link-button"
                  disabled={!/^\d{4}$/.test(birthYear) || busy}
                >
                  {busy ? <LoaderCircle size={17} /> : null}
                  {busy ? "Verifying…" : "Verify and continue"}
                </button>
                <p className="patient-verification-hint">
                  This identity check helps protect your health information.
                  {attemptsRemaining !== null ? ` ${attemptsRemaining} attempt(s) remaining.` : ""}
                </p>
              </form>
            </>
          ) : (
            <>
              <div className="patient-link-icon"><MessageIcon size={30} /></div>
              <span className="patient-link-eyebrow">JUSR AI PATIENT ACCESS</span>
              <h1>{message.title}</h1>
              <p>{message.description}</p>
              {status === "error" && (
                <button
                  type="button"
                  className="patient-link-button"
                  onClick={() => linkToken && void loadPortal(linkToken, sessionToken)}
                >
                  <RefreshCw size={17} />
                  Try again
                </button>
              )}
              {status === "locked" && (
                <div className="patient-link-confirmation" role="alert">
                  <LockKeyhole size={18} />
                  <p>Please contact your healthcare team to request assistance or a new secure link.</p>
                </div>
              )}
              <p className="patient-link-help">
                If you need assistance, please contact your healthcare team.
              </p>
            </>
          )}
        </div>
      </div>

      <footer className="patient-link-footer">
        <CheckCircle2 size={14} /> Jusr AI · Helping you stay informed about your care.
      </footer>
    </main>
  );
}

export default PatientLinkGate;
