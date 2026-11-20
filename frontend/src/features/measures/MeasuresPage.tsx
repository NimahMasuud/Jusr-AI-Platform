import { useCallback, useEffect, useState, type ReactNode } from "react";
import Alert from "../../components/ui/Alert";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../../components/ui/StateViews";
import { listFacilities } from "../../services/api/adminApi";
import {
  getMeasures,
  type MeasuresResponse,
  type Ratio,
} from "../../services/api/measuresApi";
import type { FacilityRecord } from "../../services/api/v6.types";
import { formatDateTime, formatHours, humanize } from "../../utils/format";
import "./measures.css";

const PATHWAY_OPTIONS = [
  { value: "", label: "All pathways" },
  { value: "Cervical", label: "Cervical screening" },
  { value: "Breast", label: "Breast screening" },
  { value: "Colorectal", label: "Colorectal screening" },
];

function pct(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  return `${Math.round(value * 100)}%`;
}

function ratioText(ratio: Ratio) {
  if (ratio.value === null) return "—";
  return `${pct(ratio.value)} · ${ratio.numerator}/${ratio.denominator}`;
}

function hoursText(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  return formatHours(value);
}

function MeasureCard({
  id,
  title,
  display,
  definition,
  children,
}: {
  id: string;
  title: string;
  display: string;
  definition: string;
  children: ReactNode;
}) {
  return (
    <article className="measure-card">
      <div className="measure-card-top">
        <span className="measure-id">{id}</span>
        <span className="measure-display">{display}</span>
      </div>
      <h3>{title}</h3>
      <div className="measure-values">{children}</div>
      <p className="measure-definition">{definition}</p>
    </article>
  );
}

function MeasureValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="measure-value">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export default function MeasuresPage() {
  const [facilities, setFacilities] = useState<FacilityRecord[]>([]);
  const [facilityId, setFacilityId] = useState("");
  const [pathway, setPathway] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [applied, setApplied] = useState({ facilityId: "", pathway: "", since: "", until: "" });
  const [data, setData] = useState<MeasuresResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    listFacilities()
      .then(setFacilities)
      .catch(() => setFacilities([]));
  }, []);

  const load = useCallback(async (params: typeof applied) => {
    setLoading(true);
    setError("");
    try {
      const result = await getMeasures({
        facilityId: params.facilityId || undefined,
        pathway: params.pathway || undefined,
        since: params.since || undefined,
        until: params.until || undefined,
      });
      setData(result);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load the measures."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(applied);
  }, [applied, load]);

  function applyFilters() {
    setApplied({ facilityId, pathway, since, until });
  }

  function resetFilters() {
    setFacilityId("");
    setPathway("");
    setSince("");
    setUntil("");
    setApplied({ facilityId: "", pathway: "", since: "", until: "" });
  }

  const baseline = data?.baseline;

  return (
    <div className="page-container measures-page">
      <div className="page-heading measures-heading">
        <div>
          <span className="measures-eyebrow">INSIGHTS & ANALYTICS</span>
          <h1>Measures</h1>
          <p>
            M1 to M6 calculated from the case event log. Only aggregates are
            returned; case content is never shown here.
          </p>
        </div>
      </div>

      <section className="measures-filter-panel">
        <div className="measures-section-heading">
          <div>
            <h2>Performance overview</h2>
            <p>Filter the measures by facility, pathway and date range.</p>
          </div>
          <span className="filter-label">FILTERS</span>
        </div>

        <div className="measures-filters">
          <label>
            <span>Facility</span>
            <select
              value={facilityId}
              onChange={(event) => setFacilityId(event.target.value)}
            >
              <option value="">All facilities</option>
              {facilities.map((facility) => (
                <option key={facility.id} value={facility.id}>
                  {facility.name}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span>Pathway</span>
            <select
              value={pathway}
              onChange={(event) => setPathway(event.target.value)}
            >
              {PATHWAY_OPTIONS.map((option) => (
                <option key={option.label} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span>From date</span>
            <input
              type="date"
              value={since}
              onChange={(event) => setSince(event.target.value)}
            />
          </label>

          <label>
            <span>To date</span>
            <input
              type="date"
              value={until}
              onChange={(event) => setUntil(event.target.value)}
            />
          </label>
        </div>

        <div className="measures-filter-actions">
          <button type="button" className="ui-btn ui-btn-secondary" onClick={resetFilters}>
            Reset
          </button>
          <button type="button" className="ui-btn ui-btn-primary" onClick={applyFilters}>
            Apply filters
          </button>
        </div>
      </section>

      {error && <Alert tone="danger">{error}</Alert>}

      {loading ? (
        <LoadingState message="Calculating measures…" />
      ) : !data ? (
        <ErrorState message={error || "No measures returned."} onRetry={() => void load(applied)} />
      ) : data.scope.caseCount === 0 ? (
        <EmptyState
          title="No cases in this scope"
          message="Adjust the filters, or handle cases so the event log has something to measure."
        />
      ) : (
        <>
          <div className="measures-scope">
            <span>
              <strong>{data.scope.caseCount}</strong> cases in scope
            </span>
            {data.scope.pathway && <span>Pathway: {data.scope.pathway}</span>}
            <span>Calculated {formatDateTime(data.scope.calculatedAt)}</span>
            <span>Source: {humanize(data.scope.source)}</span>
          </div>

          <section className="measures-section">
            <div className="measures-section-heading">
              <div>
                <h2>Six core measures</h2>
                <p>
                  Each measure is derived from recorded events, not stored
                  counters. Hover a value to read its definition.
                </p>
              </div>
              <span className="measure-count">06 MEASURES</span>
            </div>

            <div className="measures-grid">
              <MeasureCard
                id="M1"
                title="Time to notification"
                display="Comparison view"
                definition={data.definitions.M1 ?? "Result received to message delivered."}
              >
                <MeasureValue label="Cases" value={String(data.m1.resultToNotified.n)} />
                <MeasureValue label="Median" value={hoursText(data.m1.resultToNotified.medianHours)} />
                <MeasureValue label="90th percentile" value={hoursText(data.m1.resultToNotified.p90Hours)} />
              </MeasureCard>

              <MeasureCard
                id="M2"
                title="Acknowledgement and understanding"
                display="Percentage view"
                definition={data.definitions.M2 ?? "Share acknowledged within the limit and share answering yes to understanding."}
              >
                <MeasureValue label="Acknowledged within limit" value={ratioText(data.m2.acknowledgedWithinLimit)} />
                <MeasureValue label="Understood (yes)" value={ratioText(data.m2.understood)} />
              </MeasureCard>

              <MeasureCard
                id="M3"
                title="Referral acceptance and attendance"
                display="Percentage view"
                definition={data.definitions.M3 ?? "Share of referrals accepted within the limit and share of appointments attended."}
              >
                <MeasureValue label="Accepted within limit" value={ratioText(data.m3.referralAcceptedWithinLimit)} />
                <MeasureValue label="Appointments attended" value={ratioText(data.m3.attended)} />
              </MeasureCard>

              <MeasureCard
                id="M4"
                title="Time to care"
                display="Comparison view"
                definition={data.definitions.M4 ?? "Time from result received to each step of care."}
              >
                <MeasureValue label={`Confirmatory result (n=${data.m4.toConfirmatoryResult.n})`} value={hoursText(data.m4.toConfirmatoryResult.medianHours)} />
                <MeasureValue label={`Consultation outcome (n=${data.m4.toConsultationOutcome.n})`} value={hoursText(data.m4.toConsultationOutcome.medianHours)} />
                <MeasureValue label={`Attendance (n=${data.m4.toAttendance.n})`} value={hoursText(data.m4.toAttendance.medianHours)} />
                <MeasureValue label={`Treatment start (n=${data.m4.toTreatmentStart.n})`} value={hoursText(data.m4.toTreatmentStart.medianHours)} />
              </MeasureCard>

              <MeasureCard
                id="M5"
                title="Unresolved results and closure"
                display="Count and age view"
                definition={data.definitions.M5 ?? "Open cases, documented closure, delay reasons and drop-off."}
              >
                <MeasureValue label="Open cases" value={String(data.m5.openTotal)} />
                <MeasureValue label="Documented closure" value={ratioText(data.m5.documentedClosure)} />
                <MeasureValue label="Drop-off" value={ratioText(data.m5.dropOff)} />
              </MeasureCard>

              <MeasureCard
                id="M6"
                title="Understanding, reassurance and confidence"
                display="Measure cards"
                definition={data.definitions.M6 ?? "Patient-reported understanding, confidence and reassurance."}
              >
                <MeasureValue label="Understood (yes)" value={ratioText(data.m6.understood)} />
                <MeasureValue label={`Mean confidence (n=${data.m6.meanConfidence.n})`} value={data.m6.meanConfidence.mean === null ? "—" : data.m6.meanConfidence.mean.toFixed(1)} />
                <MeasureValue label={`Mean reassurance (n=${data.m6.meanReassurance.n})`} value={data.m6.meanReassurance.mean === null ? "—" : data.m6.meanReassurance.mean.toFixed(1)} />
              </MeasureCard>
            </div>
          </section>

          <section className="measures-section comparison-section">
            <div className="measures-section-heading">
              <div>
                <h2>Baseline vs tracker</h2>
                <p>{data.baseline.note}</p>
              </div>
              <span className="comparison-tag">
                {data.baseline.assumed ? "ASSUMED BASELINE" : "CONFIGURED BASELINE"}
              </span>
            </div>

            <div className="comparison-grid">
              <div className="comparison-panel">
                <div className="comparison-panel-heading">
                  <span className="comparison-dot baseline-dot" />
                  <div>
                    <h3>Baseline</h3>
                    <p>Without a shared tracker</p>
                  </div>
                </div>
                <table className="baseline-table">
                  <tbody>
                    <tr><td>M1 median time to notification</td><td>{hoursText(baseline?.m1.medianHours)}</td></tr>
                    <tr><td>M1 90th percentile</td><td>{hoursText(baseline?.m1.p90Hours)}</td></tr>
                    <tr><td>M2 acknowledged</td><td>{pct(baseline?.m2.acknowledgedShare)}</td></tr>
                    <tr><td>M2 understood</td><td>{pct(baseline?.m2.understoodShare)}</td></tr>
                    <tr><td>M3 referral accepted</td><td>{pct(baseline?.m3.referralAcceptedShare)}</td></tr>
                    <tr><td>M3 attended</td><td>{pct(baseline?.m3.attendedShare)}</td></tr>
                    <tr><td>M4 treatment start (median)</td><td>{hoursText(baseline?.m4.toTreatmentStartMedianHours)}</td></tr>
                    <tr><td>M5 drop-off</td><td>{pct(baseline?.m5.dropOffShare)}</td></tr>
                  </tbody>
                </table>
              </div>

              <div className="comparison-panel">
                <div className="comparison-panel-heading">
                  <span className="comparison-dot tracker-dot" />
                  <div>
                    <h3>Jusr AI tracker</h3>
                    <p>Cases handled through the tracker</p>
                  </div>
                </div>
                <table className="baseline-table">
                  <tbody>
                    <tr><td>M1 median time to notification</td><td>{hoursText(data.m1.resultToNotified.medianHours)}</td></tr>
                    <tr><td>M1 90th percentile</td><td>{hoursText(data.m1.resultToNotified.p90Hours)}</td></tr>
                    <tr><td>M2 acknowledged</td><td>{pct(data.m2.acknowledgedWithinLimit.value)}</td></tr>
                    <tr><td>M2 understood</td><td>{pct(data.m2.understood.value)}</td></tr>
                    <tr><td>M3 referral accepted</td><td>{pct(data.m3.referralAcceptedWithinLimit.value)}</td></tr>
                    <tr><td>M3 attended</td><td>{pct(data.m3.attended.value)}</td></tr>
                    <tr><td>M4 treatment start (median)</td><td>{hoursText(data.m4.toTreatmentStart.medianHours)}</td></tr>
                    <tr><td>M5 drop-off</td><td>{pct(data.m5.dropOff.value)}</td></tr>
                  </tbody>
                </table>
              </div>
            </div>
          </section>

          <section className="measures-section">
            <div className="measures-section-heading">
              <div>
                <h2>Open cases and delay reasons</h2>
                <p>M5: open cases by status and age, with recorded reasons for delay.</p>
              </div>
            </div>

            <div className="measures-detail-grid">
              <div className="comparison-panel">
                <h3 className="measures-detail-title">Open by status and age</h3>
                <div className="open-age-table-wrap">
                  <table className="ui-table open-age-table">
                    <thead>
                      <tr>
                        <th>Status</th>
                        <th>0–2d</th>
                        <th>3–7d</th>
                        <th>8–14d</th>
                        <th>15d+</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(data.m5.openByStatusAndAge).map(([status, buckets]) => (
                        <tr key={status}>
                          <td>{humanize(status)}</td>
                          <td>{buckets["0-2"] ?? 0}</td>
                          <td>{buckets["3-7"] ?? 0}</td>
                          <td>{buckets["8-14"] ?? 0}</td>
                          <td>{buckets["15+"] ?? 0}</td>
                        </tr>
                      ))}
                      {Object.keys(data.m5.openByStatusAndAge).length === 0 && (
                        <tr>
                          <td colSpan={5}>No open cases.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="comparison-panel">
                <h3 className="measures-detail-title">Reasons for delay</h3>
                {Object.keys(data.m5.delayReasons).length === 0 ? (
                  <p className="measures-muted">No delay reasons recorded.</p>
                ) : (
                  <ul className="delay-list">
                    {Object.entries(data.m5.delayReasons)
                      .sort((a, b) => b[1] - a[1])
                      .map(([reason, count]) => (
                        <li key={reason}>
                          <span>{humanize(reason)}</span>
                          <strong>{count}</strong>
                        </li>
                      ))}
                  </ul>
                )}
                {Object.keys(data.m5.closedByType).length > 0 && (
                  <>
                    <h3 className="measures-detail-title">Closed by type</h3>
                    <ul className="delay-list">
                      {Object.entries(data.m5.closedByType).map(([type, count]) => (
                        <li key={type}>
                          <span>{humanize(type)}</span>
                          <strong>{count}</strong>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
