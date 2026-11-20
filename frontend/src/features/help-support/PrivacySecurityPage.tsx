
import {
  ArrowLeft,
  ShieldCheck,
  Users,
  Building2,
  ClipboardList,
  LockKeyhole,
  BrainCircuit,
  Link2,
} from "lucide-react";
import { Link } from "react-router-dom";
import "./privacy-security.css";

const securitySections = [
  {
    id: "access-control",
    title: "Role-based access control",
    icon: Users,
    content: [
      "Jusr AI uses role-based access to determine which parts of the platform staff members can access.",
      "The platform defines access for Patients, Coordinators, Referring Clinicians, Receiving Clinicians and Facility Administrators.",
      "Access should be denied by default unless the relevant permission has been granted.",
    ],
  },
  {
    id: "facility-access",
    title: "Facility-level data boundaries",
    icon: Building2,
    content: [
      "Staff access is restricted according to their authorised facility and role.",
      "Case visibility should follow facility-scoped access rules.",
      "Facility Administrators can manage staff profiles, access settings and facility connections, but must not have access to clinical case content.",
    ],
  },
  {
    id: "patient-information",
    title: "Patient information protection",
    icon: LockKeyhole,
    content: [
      "Patient information should only be accessible to authorised users for their permitted workflows.",
      "Patient-facing secure links provide access to the relevant response workflow.",
      "Sensitive patient information should not be included in unnecessary support requests or shared outside authorised workflows.",
    ],
  },
  {
    id: "audit-trails",
    title: "Audit trails and accountability",
    icon: ClipboardList,
    content: [
      "Important actions should generate an audit event.",
      "Audit records should capture the responsible staff identifier, role, event, timestamp and relevant changes.",
      "Audit events are intended to provide accountability and traceability across case management activities.",
    ],
  },
  {
    id: "ai-oversight",
    title: "AI assistance and human oversight",
    icon: BrainCircuit,
    content: [
      "Jusr AI uses AI to support workflows such as intake, urgency assessment, messaging drafts, clinical summaries and referral-target suggestions.",
      "AI-generated suggestions must be reviewed by an authorised human before they are acted upon.",
      "AI must not independently make final clinical decisions or close cases.",
    ],
  },
  {
    id: "secure-links",
    title: "Patient secure links",
    icon: Link2,
    content: [
      "Patient secure links provide access to designated patient response workflows.",
      "The backend design includes token-based links, expiry controls and birth-year verification.",
      "The backend also defines a limit on unsuccessful verification attempts. These controls should be enforced by the live service.",
    ],
  },
];

function PrivacySecurityPage() {
  return (
    <main className="page-container privacy-security-page">
      <Link to="/help-support" className="privacy-security-back">
        <ArrowLeft size={16} />
        Back to Help & Support
      </Link>

      <div className="page-heading">
        <div>
          <span className="help-support-eyebrow">HELP CENTRE</span>
          <h1>Privacy & Security</h1>
          <p>
            Understand how access, accountability and responsible use
            of information are addressed in Jusr AI.
          </p>
        </div>
      </div>

      <section className="privacy-security-banner">
        <div className="privacy-security-banner-icon">
          <ShieldCheck size={30} />
        </div>
        <div>
          <span>SECURITY AND ACCOUNTABILITY</span>
          <h2>Protecting information through controlled access</h2>
          <p>
            Jusr AI is designed around role-based access, facility
            boundaries, auditability and human oversight.
          </p>
        </div>
      </section>

      <div className="privacy-security-notice">
        <ShieldCheck size={19} />
        <p>
          This page describes the security requirements and intended
          safeguards in the Jusr AI Developer Guide. It is not an
          independent security certification or confirmation that
          every control is already operational.
        </p>
      </div>

      <div className="privacy-security-grid">
        {securitySections.map((section, index) => {
          const SectionIcon = section.icon;

          return (
            <section
              className="privacy-security-card"
              id={section.id}
              key={section.id}
            >
              <div className="privacy-security-card-heading">
                <div className="privacy-security-icon">
                  <SectionIcon size={20} />
                </div>
                <div>
                  <span>
                    SECURITY AREA {String(index + 1).padStart(2, "0")}
                  </span>
                  <h2>{section.title}</h2>
                </div>
              </div>

              <div className="privacy-security-card-content">
                {section.content.map((paragraph, paragraphIndex) => (
                  <p key={paragraphIndex}>{paragraph}</p>
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </main>
  );
}

export default PrivacySecurityPage;
