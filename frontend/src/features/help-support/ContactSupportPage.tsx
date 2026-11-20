
import { useState } from "react";
import {
  ArrowLeft,
  Send,
  MessageCircle,
  AlertCircle,
  CheckCircle2,
} from "lucide-react";
import { Link } from "react-router-dom";
import "./contact-support.css";

function ContactSupportPage() {
  const [form, setForm] = useState({
    category: "",
    severity: "",
    summary: "",
    description: "",
    email: "",
    caseReference: "",
  });

  const [submitted, setSubmitted] = useState(false);
  const [reference, setReference] = useState("");

  const updateField = (
    field: keyof typeof form,
    value: string
  ) => {
    setForm((previous) => ({ ...previous, [field]: value }));
  };

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const demoReference = `DEMO-${Date.now().toString().slice(-6)}`;

    setReference(demoReference);
    setSubmitted(true);
  };

  const handleNewReport = () => {
    setForm({
      category: "",
      severity: "",
      summary: "",
      description: "",
      email: "",
      caseReference: "",
    });
    setReference("");
    setSubmitted(false);
  };

  return (
    <main className="page-container contact-support-page">
      <Link to="/help-support" className="contact-support-back">
        <ArrowLeft size={16} />
        Back to Help & Support
      </Link>

      <div className="page-heading">
        <div>
          <span className="help-support-eyebrow">SUPPORT CENTRE</span>
          <h1>Contact Support</h1>
          <p>
            Tell us what you need help with. Provide as much detail as
            possible so the issue can be understood.
          </p>
        </div>
      </div>

      {submitted ? (
        <section className="support-success">
          <CheckCircle2 size={42} />
          <h2>Report recorded in demo mode</h2>
          <p>
            Your form has been processed locally for demonstration.
            No support ticket has been sent to a support team.
          </p>
          <div className="support-reference">
            <span>DEMO REFERENCE</span>
            <strong>{reference}</strong>
          </div>
          <button type="button" onClick={handleNewReport}>
            Submit another report
          </button>
        </section>
      ) : (
        <div className="support-form-layout">
          <form className="support-form" onSubmit={handleSubmit}>
            <div className="support-form-heading">
              <MessageCircle size={22} />
              <div>
                <h2>Report an issue</h2>
                <p>Fields marked with * are required.</p>
              </div>
            </div>

            <div className="support-demo-notice">
              <AlertCircle size={17} />
              <span>
                Demo mode: submissions are not transmitted to a
                support team.
              </span>
            </div>

            <div className="support-form-grid">
              <label>
                Issue category *
                <select
                  required
                  value={form.category}
                  onChange={(event) =>
                    updateField("category", event.target.value)
                  }
                >
                  <option value="">Select a category</option>
                  <option value="Technical issue">Technical issue</option>
                  <option value="Account and access">Account and access</option>
                  <option value="Case management">Case management</option>
                  <option value="Referrals">Referrals</option>
                  <option value="Patient links">Patient links</option>
                  <option value="Data or reporting">Data or reporting</option>
                  <option value="Other">Other</option>
                </select>
              </label>

              <label>
                Severity *
                <select
                  required
                  value={form.severity}
                  onChange={(event) =>
                    updateField("severity", event.target.value)
                  }
                >
                  <option value="">Select severity</option>
                  <option value="Low">Low - Minor inconvenience</option>
                  <option value="Medium">Medium - Work affected</option>
                  <option value="High">High - Major disruption</option>
                  <option value="Critical">
                    Critical - Platform unavailable
                  </option>
                </select>
              </label>

              <label className="support-full-width">
                Issue summary *
                <input
                  required
                  maxLength={120}
                  value={form.summary}
                  onChange={(event) =>
                    updateField("summary", event.target.value)
                  }
                  placeholder="Briefly describe the issue"
                />
              </label>

              <label className="support-full-width">
                Detailed description *
                <textarea
                  required
                  minLength={10}
                  rows={6}
                  maxLength={2000}
                  value={form.description}
                  onChange={(event) =>
                    updateField("description", event.target.value)
                  }
                  placeholder="What happened? What were you trying to do? Include any error message."
                />
              </label>

              <label>
                Contact email *
                <input
                  required
                  type="email"
                  value={form.email}
                  onChange={(event) =>
                    updateField("email", event.target.value)
                  }
                  placeholder="you@organisation.org"
                />
              </label>

              <label>
                Case reference (optional)
                <input
                  value={form.caseReference}
                  onChange={(event) =>
                    updateField("caseReference", event.target.value)
                  }
                  placeholder="e.g. CASE-001"
                />
              </label>
            </div>

            <div className="support-form-footer">
              <p>
                Do not include patient names, medical records or other
                sensitive clinical information in this demo form.
              </p>
              <button type="submit">
                <Send size={16} />
                Submit report
              </button>
            </div>
          </form>
        </div>
      )}
    </main>
  );
}

export default ContactSupportPage;
