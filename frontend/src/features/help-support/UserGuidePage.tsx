
import {
  ArrowLeft,
  LayoutDashboard,
  ClipboardList,
  AlertTriangle,
  ArrowLeftRight,
  Stethoscope,
  Link2,
  ShieldCheck,
  Building2,
  BookOpen,
} from "lucide-react";
import { Link } from "react-router-dom";
import "./user-guide.css";

const guideSections = [
  {
    id: "workspace",
    title: "Navigating your workspace",
    icon: LayoutDashboard,
    content: [
      "The Jusr AI workspace provides access to the tools and information available to your assigned role.",
      "Use the sidebar to navigate between Overview, Incoming Urgent Cases, Referrals, Consultations and Help & Support, where those options are available to your role.",
      "The workspace header displays your current facility and user profile.",
    ],
  },
  {
    id: "worklist",
    title: "Managing cases and worklists",
    icon: ClipboardList,
    content: [
      "The Worklist helps authorised staff view and manage cases assigned within their facility.",
      "Review the case status, priority, assigned owner, next action and due date before taking action.",
      "Open a case to review its available details and timeline. Keep ownership and follow-up information up to date.",
    ],
  },
  {
    id: "urgent-cases",
    title: "Handling urgent cases",
    icon: AlertTriangle,
    content: [
      "Urgent cases require prompt attention and should be routed according to the required specialty.",
      "A qualified receiving clinician must accept an urgent case before taking responsibility for it.",
      "If acceptance does not happen within the configured time limit, the case should be escalated according to the applicable workflow.",
    ],
  },
  {
    id: "referrals",
    title: "Managing referrals",
    icon: ArrowLeftRight,
    content: [
      "Referrals connect a referring facility with a receiving facility for further review and care.",
      "Receiving clinicians can review incoming referrals and accept or decline them.",
      "A declined referral should include a reason so the referring team can understand what happened and arrange appropriate follow-up.",
    ],
  },
  {
    id: "consultations",
    title: "Recording consultation outcomes",
    icon: Stethoscope,
    content: [
      "Consultations move through the stages REQUESTED, ACCEPTED, OUTCOME_RECORDED and ESCALATED.",
      "The responsible clinician should record the consultation outcome and relevant notes.",
      "Recording an outcome does not automatically mean the case is ready for closure. Required care and closure evidence must still be documented.",
    ],
  },
  {
    id: "patient-links",
    title: "Using patient secure links",
    icon: Link2,
    content: [
      "Patient secure links provide access to the relevant patient response workflow.",
      "Depending on the workflow, patients may acknowledge a message, confirm understanding, provide confidence feedback or request follow-up.",
      "Staff may also record a patient response through the staff-assisted workflow where available.",
    ],
  },
  {
    id: "closure",
    title: "Case closure requirements",
    icon: ShieldCheck,
    content: [
      "A case must not be closed without the required documented evidence or an authorised clinical decision.",
      "Where required information is missing, the case should remain open until the outstanding information is addressed.",
      "Case closure must be performed by an authorised human decision-maker. AI suggestions do not replace clinical or administrative approval.",
    ],
  },
  {
    id: "facilities",
    title: "Facility and staff administration",
    icon: Building2,
    content: [
      "Facility administration covers facility records, staff profiles, access settings and connection status.",
      "Access is restricted according to staff role and facility scope.",
      "Facility Administrators can manage facility and staff access but must not have access to clinical case content.",
    ],
  },
];

function UserGuidePage() {
  return (
    <div className="user-guide-page">
      <div className="user-guide-header">
        <Link to="/help-support" className="user-guide-back">
          <ArrowLeft size={16} />
          Back to Help & Support
        </Link>

        <span className="page-eyebrow">HELP CENTRE</span>
        <h1>Jusr AI User Guide</h1>
        <p>
          A practical guide to navigating the workspace and managing
          case coordination workflows.
        </p>
      </div>

      <div className="user-guide-intro">
        <BookOpen size={28} />
        <div>
          <h2>Getting started with Jusr AI</h2>
          <p>
            Use this guide to understand the main workspace features,
            role responsibilities and important case management steps.
          </p>
        </div>
      </div>

      <div className="user-guide-layout">
        <aside className="user-guide-contents">
          <h3>IN THIS GUIDE</h3>
          <nav>
            {guideSections.map((section, index) => (
              <a key={section.id} href={`#${section.id}`}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                {section.title}
              </a>
            ))}
          </nav>
        </aside>

        <main className="user-guide-sections">
          {guideSections.map((section, index) => {
            const SectionIcon = section.icon;

            return (
              <section
                key={section.id}
                id={section.id}
                className="user-guide-section"
              >
                <div className="user-guide-section-heading">
                  <div className="user-guide-section-icon">
                    <SectionIcon size={19} />
                  </div>
                  <div>
                    <span>SECTION {String(index + 1).padStart(2, "0")}</span>
                    <h2>{section.title}</h2>
                  </div>
                </div>

                <div className="user-guide-section-content">
                  {section.content.map((paragraph, paragraphIndex) => (
                    <p key={paragraphIndex}>{paragraph}</p>
                  ))}
                </div>
              </section>
            );
          })}
        </main>
      </div>
    </div>
  );
}

export default UserGuidePage;
