import {
  BookOpen,
  MessageCircle,
  FileQuestion,
  ShieldCheck,
  ChevronRight,
  Search,
} from "lucide-react";
import { useState } from "react";
import "./help-support.css";
import { Link } from "react-router-dom";

interface FAQItem {
  category: string;
  question: string;
  answer: string;
}

const faqItems: FAQItem[] = [
  {
    category: "Worklist",
    question: "What is the Worklist?",
    answer:
      "The Worklist helps authorised staff view and manage cases assigned to their facility. It provides case status, ownership, priority and the next required action.",
  },
  {
    category: "Referrals",
    question: "How do referrals work?",
    answer:
      "A referral is sent to a receiving facility for review. The receiving clinician can accept or decline it. A declined referral should include a reason so that the case can be followed up.",
  },
  {
    category: "Urgent cases",
    question: "How are urgent cases routed?",
    answer:
      "Urgent cases are routed according to the required specialty. A qualified receiving clinician must accept the case. If acceptance does not happen within the configured time limit, the case should be escalated.",
  },
  {
    category: "Consultations",
    question: "What happens after a consultation?",
    answer:
      "The consultation outcome should be recorded by the responsible clinician. The case remains open until the required care and closure evidence have been documented and an authorised person closes it.",
  },
  {
    category: "Patient links",
    question: "How do patients respond to secure links?",
    answer:
      "Patients can use their secure link to access the relevant response workflow. Depending on the workflow, they may acknowledge a message, confirm understanding and provide confidence or follow-up responses.",
  },
  {
    category: "Case management",
    question: "Can a case be closed without documented evidence?",
    answer:
      "No. A case must have the required documented evidence or an authorised clinical decision before it can be closed.",
  },
  {
    category: "Access and security",
    question: "Can every staff member view all cases?",
    answer:
      "No. Access is restricted by staff role and facility scope. Facility Administrators manage facility and staff access but must not have access to clinical case content.",
  },
];

function HelpSupportPage() {
  const [faqSearch, setFaqSearch] = useState("");
  const [expandedFAQ, setExpandedFAQ] = useState<number | null>(null);

  const filteredFAQs = faqItems.filter((item) =>
    `${item.category} ${item.question} ${item.answer}`
      .toLowerCase()
      .includes(faqSearch.toLowerCase().trim()),
  );
  return (
    <main className="page-container help-support-page">
      <div className="page-heading">
        <div>
          <span className="help-support-eyebrow">SUPPORT CENTRE</span>
          <h1>Help & Support</h1>
          <p>
            Find guidance on using Jusr AI and managing your care coordination
            workflows.
          </p>
        </div>
      </div>

      <section className="help-welcome">
        <div>
          <span>JUSR AI HELP CENTRE</span>
          <h2>How can we help you today?</h2>
          <p>
            Explore helpful resources and answers to common questions about your
            workspace.
          </p>
        </div>
        <BookOpen size={64} strokeWidth={1.2} />
      </section>

      <section className="help-search-section">
        <div className="help-search">
          <Search size={18} />
          <input
            type="search"
            placeholder="Search help articles and topics..."
            value={faqSearch}
            onChange={(event) => {
              setFaqSearch(event.target.value);
              setExpandedFAQ(null);
            }}
          />
        </div>
      </section>

      <section className="help-faq-section">
        <div className="help-faq-heading">
          <div>
            <span className="help-support-eyebrow">HELP CENTRE</span>
            <h2>Frequently asked questions</h2>
            <p>Quick answers to common questions about using Jusr AI.</p>
          </div>
          <span className="help-faq-count">{filteredFAQs.length} topics</span>
        </div>

        <div className="help-faq-list">
          {filteredFAQs.map((item, index) => (
            <article className="help-faq-item" key={item.question}>
              <button
                type="button"
                className="help-faq-question"
                onClick={() =>
                  setExpandedFAQ(expandedFAQ === index ? null : index)
                }
                aria-expanded={expandedFAQ === index}
              >
                <span>
                  <small>{item.category}</small>
                  <strong>{item.question}</strong>
                </span>

                <ChevronRight
                  size={19}
                  className={
                    expandedFAQ === index
                      ? "help-faq-chevron expanded"
                      : "help-faq-chevron"
                  }
                />
              </button>

              {expandedFAQ === index && (
                <div className="help-faq-answer">{item.answer}</div>
              )}
            </article>
          ))}

          {filteredFAQs.length === 0 && (
            <div className="help-faq-empty">
              <FileQuestion size={24} />
              <strong>No matching questions</strong>
              <p>Try another search term.</p>
            </div>
          )}
        </div>
      </section>

      <section className="help-resource-grid">
        <Link to="/help-support/user-guide" className="help-resource-card">
          <span className="help-resource-icon">
            <BookOpen size={22} />
          </span>
          <h3>User guide</h3>
          <p>Learn how to navigate your workspace and use the main features.</p>
          <span className="help-resource-link">
            Explore guide <ChevronRight size={16} />
          </span>
        </Link>

        <Link to="/help-support/contact" className="help-resource-card">
          <span className="help-resource-icon">
            <MessageCircle size={22} />
          </span>
          <h3>Contact support</h3>
          <p>
            Get assistance with technical issues or difficulties using the
            platform.
          </p>
          <span className="help-resource-link">
            Get assistance <ChevronRight size={16} />
          </span>
        </Link>

        <Link
          to="/help-support/privacy-security"
          className="help-resource-card"
        >
          <span className="help-resource-icon">
            <ShieldCheck size={22} />
          </span>
          <h3>Privacy and security</h3>
          <p>
            Understand account access, role permissions and responsible handling
            of information.
          </p>
          <span className="help-resource-link">
            Learn more <ChevronRight size={16} />
          </span>
        </Link>
      </section>

      <section className="help-contact-panel">
        <div>
          <h2>Need further assistance?</h2>
          <p>
            If you are experiencing a problem, use your organisation's
            designated support channel.
          </p>
        </div>
        <span className="help-contact-note">
          Support contact details to be configured
        </span>
      </section>
    </main>
  );
}

export default HelpSupportPage;
