import "./dashboard.css";
import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Building2,
  Clock,
  FileWarning,
  HelpCircle,
  MessageSquareWarning,
  Plug,
  ShieldCheck,
  UserX,
  Users,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import StatusBadge from "../../components/ui/StatusBadge";
import { PriorityBadge } from "../../components/ui/FlagBadges";
import {
  ErrorState,
  LoadingState,
} from "../../components/ui/StateViews";
import { useUser } from "../../context/UserContext";
import {
  getDashboardSummary,
  type DashboardSummary,
} from "../../services/api/dashboardApi";
import { formatDateTime, formatTimeLeft, humanize, initialsOf } from "../../utils/format";

const ROLE_TITLES: Record<string, string> = {
  coordinator: "Coordinator Dashboard",
  referring_clinician: "Referring Clinician Dashboard",
  receiving_clinician: "Receiving Clinician Dashboard",
  facility_administrator: "Facility Administrator Dashboard",
  national_admin: "National Administrator Dashboard",
};

const ROLE_HINTS: Record<string, string> = {
  coordinator: "Own the pathway: classify, notify, refer and close.",
  referring_clinician: "Your assigned cases and the closures waiting for your sign-off.",
  receiving_clinician: "Urgent cases routed to you and referrals waiting for a decision.",
  facility_administrator: "Staff access and the facility connection only — no patient data.",
  national_admin: "Cross-facility oversight, settings and the demo clock.",
};

export default function DashboardPage() {
  const { activeUser } = useUser();
  const navigate = useNavigate();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setSummary(await getDashboardSummary());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load the dashboard.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (!activeUser) return null;

  if (loading) {
    return (
      <main className="dashboard-page">
        <LoadingState message="Loading your dashboard…" />
      </main>
    );
  }

  if (error || !summary) {
    return (
      <main className="dashboard-page">
        <ErrorState message={error || "The dashboard could not be loaded."} onRetry={() => void load()} />
      </main>
    );
  }

  const role = activeUser.role;
  const stats = summary.stats ?? {};
  const refs = summary.referrals ?? {};
  const demoClock = summary.demoClock;

  return (
    <main className="dashboard-page">
      <div className="dashboard-heading">
        <div>
          <span className="dashboard-eyebrow">OVERVIEW</span>
          <h1>{ROLE_TITLES[role] ?? "Dashboard"}</h1>
          <p>
            Welcome, {activeUser.name}. {ROLE_HINTS[role] ?? ""}
          </p>
        </div>
        <div className="dashboard-date">
          <Clock size={15} />
          <span>
            Updated {formatDateTime(summary.generatedAt)}
            {demoClock?.active ? ` · Demo clock +${demoClock.offsetMinutes} min` : ""}
          </span>
        </div>
      </div>

      {role === "coordinator" || role === "national_admin" ? (
        <CoordinatorView summary={summary} stats={stats} refs={refs} navigate={navigate} />
      ) : role === "referring_clinician" ? (
        <ReferringView summary={summary} stats={stats} refs={refs} navigate={navigate} />
      ) : role === "receiving_clinician" ? (
        <ReceivingView summary={summary} refs={refs} navigate={navigate} />
      ) : (
        <FacilityView summary={summary} />
      )}
    </main>
  );
}

type Navigate = ReturnType<typeof useNavigate>;

function StatCard({
  label,
  value,
  icon: Icon,
  tone,
  hint,
  onClick,
}: {
  label: string;
  value: number;
  icon: typeof Activity;
  tone: "navy" | "teal" | "coral" | "amber";
  hint?: string;
  onClick?: () => void;
}) {
  return (
    <article
      className={`stat-card stat-${tone}`}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={(event) => {
        if (onClick && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault();
          onClick();
        }
      }}
      style={onClick ? { cursor: "pointer" } : undefined}
    >
      <div className="stat-card-top">
        <span>{label}</span>
        <span className="stat-icon">
          <Icon size={17} />
        </span>
      </div>
      <div className="stat-value">{value}</div>
      {hint && <p>{hint}</p>}
    </article>
  );
}

function CoordinatorView({
  summary,
  stats,
  refs,
  navigate,
}: {
  summary: DashboardSummary;
  stats: NonNullable<DashboardSummary["stats"]>;
  refs: Record<string, number>;
  navigate: Navigate;
}) {
  const totalActive = stats.activeCases ?? 0;
  return (
    <>
      <section className="stats-grid">
        <StatCard
          label="Active cases"
          value={totalActive}
          icon={Activity}
          tone="navy"
          hint="All open cases you can see"
          onClick={() => navigate("/worklist")}
        />
        <StatCard
          label="Urgent"
          value={stats.urgentCases ?? 0}
          icon={AlertTriangle}
          tone="coral"
          hint="Need a person now"
          onClick={() => navigate("/worklist")}
        />
        <StatCard
          label="Overdue"
          value={stats.overdueCases ?? 0}
          icon={Clock}
          tone="amber"
          hint="Past their due time"
          onClick={() => navigate("/worklist")}
        />
        <StatCard
          label="Unassigned"
          value={stats.unassignedCases ?? 0}
          icon={UserX}
          tone="teal"
          hint="No owner yet"
          onClick={() => navigate("/worklist")}
        />
      </section>

      <section className="stats-grid">
        <StatCard label="Exceptions" value={stats.exceptionCases ?? 0} icon={FileWarning} tone="coral" hint="Referral or routing exception" />
        <StatCard label="Message failed" value={stats.messageFailedCases ?? 0} icon={MessageSquareWarning} tone="amber" hint="Patient not reached by message" />
        <StatCard label="Not explained" value={stats.notExplainedCases ?? 0} icon={HelpCircle} tone="amber" hint="Patient did not understand" />
        <StatCard label="Data missing" value={stats.dataMissingCases ?? 0} icon={FileWarning} tone="navy" hint="Information needed to proceed" />
      </section>

      <div className="dashboard-main-grid">
        <section className="dashboard-panel">
          <div className="panel-heading">
            <div>
              <h2>Cases needing attention</h2>
              <p>Urgent, overdue and flagged cases first.</p>
            </div>
            <span className="panel-count">{summary.priorityCases?.length ?? 0}</span>
          </div>
          {(summary.priorityCases?.length ?? 0) === 0 ? (
            <div className="empty-state">
              <p>Nothing urgent right now.</p>
            </div>
          ) : (
            <div className="priority-list">
              {summary.priorityCases?.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className="priority-item"
                  style={{ textAlign: "left", width: "100%", background: "none", border: 0, font: "inherit", cursor: "pointer" }}
                  onClick={() => navigate(`/worklist?caseId=${encodeURIComponent(item.id)}`)}
                >
                  <span className={`priority-indicator priority-${item.priority.toLowerCase()}`} />
                  <div className="priority-details">
                    <div className="priority-title-row">
                      <h3>{item.patientLabel}</h3>
                      <PriorityBadge priority={item.priority} />
                      <StatusBadge status={item.status} />
                    </div>
                    <p>
                      {item.screeningType ?? "No screening"} — {item.screeningResult ?? "No result"}
                    </p>
                    <div className="priority-meta">
                      <span>{item.caseId}</span>
                      <span>Owner: {item.owner}</span>
                      <span className={item.overdue ? "wl-time-overdue" : undefined}>
                        {formatTimeLeft(
                          item.dueAt
                            ? (new Date(item.dueAt).getTime() - Date.now()) / 3600000
                            : null
                        )}
                      </span>
                    </div>
                  </div>
                  <span className="priority-footer">
                    <ArrowRight size={14} />
                  </span>
                </button>
              ))}
            </div>
          )}
        </section>

        <section className="dashboard-panel">
          <div className="panel-heading">
            <div>
              <h2>Where cases are</h2>
              <p>Cases by workflow status.</p>
            </div>
          </div>
          {(summary.careProgress?.length ?? 0) === 0 ? (
            <div className="empty-state">
              <p>No active cases yet.</p>
            </div>
          ) : (
            <div className="progress-list">
              {[...(summary.careProgress ?? [])]
                .sort((a, b) => b.count - a.count)
                .map((item) => (
                  <div className="progress-item" key={item.label}>
                    <div className="progress-label">
                      <span>{item.label}</span>
                      <strong>{item.count}</strong>
                    </div>
                    <div className="progress-track">
                      <div className="progress-fill" style={{ width: `${item.percentage}%` }} />
                    </div>
                    <span className="progress-percentage">{item.percentage}%</span>
                  </div>
                ))}
            </div>
          )}
        </section>
      </div>

      <div className="dashboard-bottom-grid">
        <ReferralPanel refs={refs} navigate={navigate} />
        <ActivityPanel items={summary.recentActivity ?? []} />
      </div>
    </>
  );
}

function ReferringView({
  summary,
  stats,
  refs,
  navigate,
}: {
  summary: DashboardSummary;
  stats: NonNullable<DashboardSummary["stats"]>;
  refs: Record<string, number>;
  navigate: Navigate;
}) {
  const approvals = summary.closureApprovals ?? [];
  return (
    <>
      <section className="stats-grid">
        <StatCard
          label="My active cases"
          value={stats.assignedCases ?? 0}
          icon={Users}
          tone="navy"
          hint="Cases where you are the owner"
          onClick={() => navigate("/worklist")}
        />
        <StatCard label="Urgent" value={stats.urgentCases ?? 0} icon={AlertTriangle} tone="coral" hint="Urgent and still open" onClick={() => navigate("/worklist")} />
        <StatCard label="Overdue" value={stats.overdueCases ?? 0} icon={Clock} tone="amber" hint="Past their due time" onClick={() => navigate("/worklist")} />
        <StatCard
          label="Closures to sign off"
          value={stats.closuresAwaitingSignOff ?? 0}
          icon={ShieldCheck}
          tone="teal"
          hint="You are the named second approver"
        />
      </section>

      <div className="dashboard-main-grid">
        <section className="dashboard-panel">
          <div className="panel-heading">
            <div>
              <h2>Closures waiting for your sign-off</h2>
              <p>An 'other' closure needs a second person before it takes effect.</p>
            </div>
            <span className="panel-count">{approvals.length}</span>
          </div>
          {approvals.length === 0 ? (
            <div className="empty-state">
              <p>No closures are waiting for you.</p>
            </div>
          ) : (
            <div className="priority-list">
              {approvals.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className="priority-item"
                  style={{ textAlign: "left", width: "100%", background: "none", border: 0, font: "inherit", cursor: "pointer" }}
                  onClick={() => navigate(`/worklist?caseId=${encodeURIComponent(item.id)}`)}
                >
                  <span className="priority-indicator priority-high" />
                  <div className="priority-details">
                    <div className="priority-title-row">
                      <h3>{item.patientLabel}</h3>
                      <span className="ui-badge ui-badge-warning">{humanize(item.closureType)}</span>
                    </div>
                    <p>{item.reason}</p>
                    <div className="priority-meta">
                      <span>{item.caseNumber}</span>
                      <span>Requested by {item.requestedBy}</span>
                      <span>{formatDateTime(item.requestedAt)}</span>
                    </div>
                  </div>
                  <span className="priority-footer">
                    <ArrowRight size={14} />
                  </span>
                </button>
              ))}
            </div>
          )}
        </section>

        <ReferralPanel refs={refs} navigate={navigate} />
      </div>
    </>
  );
}

function ReceivingView({
  summary,
  refs,
  navigate,
}: {
  summary: DashboardSummary;
  refs: Record<string, number>;
  navigate: Navigate;
}) {
  const routing = summary.urgentRouting ?? { awaitingAcceptance: 0, accepted: 0 };
  return (
    <>
      <section className="stats-grid">
        <StatCard
          label="Urgent routed to me"
          value={routing.awaitingAcceptance}
          icon={AlertTriangle}
          tone="coral"
          hint="Accept before the time limit"
          onClick={() => navigate("/urgent-inbox")}
        />
        <StatCard
          label="Urgent accepted"
          value={routing.accepted}
          icon={Activity}
          tone="teal"
          hint="You own these cases"
          onClick={() => navigate("/worklist")}
        />
        <StatCard
          label="Referrals assigned to me"
          value={refs.assignedToMe ?? 0}
          icon={Users}
          tone="navy"
          hint="Sent or accepted"
          onClick={() => navigate("/referrals")}
        />
        <StatCard
          label="Outstanding decisions"
          value={refs.outstandingDecisions ?? 0}
          icon={Clock}
          tone="amber"
          hint="Referrals waiting for you"
          onClick={() => navigate("/referrals")}
        />
      </section>

      <div className="dashboard-main-grid">
        <ReferralPanel refs={refs} navigate={navigate} />
        <section className="dashboard-panel">
          <div className="panel-heading">
            <div>
              <h2>Urgent routing</h2>
              <p>Two stages, then the coordinator handles the exception.</p>
            </div>
          </div>
          <div className="progress-list">
            <div className="progress-item">
              <div className="progress-label">
                <span>Awaiting acceptance</span>
                <strong>{routing.awaitingAcceptance}</strong>
              </div>
            </div>
            <div className="progress-item">
              <div className="progress-label">
                <span>Accepted</span>
                <strong>{routing.accepted}</strong>
              </div>
            </div>
          </div>
          <div className="priority-footer" style={{ padding: 16 }}>
            <a href="/urgent-inbox">Open the urgent inbox</a>
          </div>
        </section>
      </div>
    </>
  );
}

function FacilityView({
  summary,
}: {
  summary: DashboardSummary;
}) {
  const staff = summary.staffAccess;
  const connection = summary.connection;
  return (
    <>
      <section className="stats-grid">
        <StatCard label="Total staff" value={staff?.totalStaff ?? 0} icon={Users} tone="navy" hint="At this facility" />
        <StatCard label="Active staff" value={staff?.activeStaff ?? 0} icon={ShieldCheck} tone="teal" hint="Can sign in" />
        <StatCard label="Inactive" value={staff?.inactiveStaff ?? 0} icon={UserX} tone="amber" hint="Access disabled" />
        <StatCard
          label="Connection"
          value={connection?.status === "CONNECTED" ? 1 : 0}
          icon={Plug}
          tone={connection?.status === "CONNECTED" ? "teal" : "coral"}
          hint={connection?.status ?? "Unknown"}
        />
      </section>

      <div className="dashboard-main-grid">
        <section className="dashboard-panel">
          <div className="panel-heading">
            <div>
              <h2>Staff by role</h2>
              <p>No patient or clinical case data is shown at this level (R-09).</p>
            </div>
          </div>
          {staff && Object.keys(staff.byRole).length > 0 ? (
            <div className="progress-list">
              {Object.entries(staff.byRole).map(([role, count]) => (
                <div className="progress-item" key={role}>
                  <div className="progress-label">
                    <span>{humanize(role)}</span>
                    <strong>{count}</strong>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state">
              <p>No staff records at this facility.</p>
            </div>
          )}
          <div className="priority-footer" style={{ padding: 16 }}>
            <a href="/settings">Open settings</a>
          </div>
        </section>

        <section className="dashboard-panel">
          <div className="panel-heading">
            <div>
              <h2>Facility</h2>
              <p>Connection and staff management.</p>
            </div>
          </div>
          <div className="priority-list">
            <div className="priority-item">
              <span className="priority-indicator priority-normal" />
              <div className="priority-details">
                <div className="priority-title-row">
                  <h3>
                    <Building2 size={14} /> {summary.facility?.name ?? "Facility"}
                  </h3>
                </div>
                <div className="priority-meta">
                  <span>Code: {summary.facility?.code ?? "—"}</span>
                  <span>Connector: {connection?.connectorType ?? "—"}</span>
                  <span>Last event: {formatDateTime(connection?.lastEventAt)}</span>
                </div>
              </div>
            </div>
          </div>
          <div className="priority-footer" style={{ padding: 16 }}>
            <a href="/facilities">Manage facilities and staff</a>
          </div>
        </section>
      </div>
    </>
  );
}

function ReferralPanel({
  refs,
  navigate,
}: {
  refs: Record<string, number>;
  navigate: Navigate;
}) {
  const pending = refs.pending ?? refs.sent ?? 0;
  const accepted = refs.accepted ?? 0;
  const declined = refs.declined ?? refs.rejected ?? 0;
  const total = refs.total ?? pending + accepted + declined;
  const share = (value: number) => (total ? Math.round((value / total) * 100) : 0);
  return (
    <section className="dashboard-panel">
      <div className="panel-heading">
        <div>
          <h2>Referrals</h2>
          <p>Where referrals stand right now.</p>
        </div>
        <span className="panel-count">{total}</span>
      </div>
      <div className="referral-total">
        <h3>{total}</h3>
        <span>referrals in view</span>
      </div>
      <div className="referral-progress">
        <span className="referral-segment referral-accepted" style={{ width: `${share(accepted)}%` }} />
        <span className="referral-segment referral-pending" style={{ width: `${share(pending)}%` }} />
        <span className="referral-segment referral-rejected" style={{ width: `${share(declined)}%` }} />
      </div>
      <div className="referral-legend">
        <div className="referral-legend-item">
          <span className="referral-label">Accepted</span>
          <strong>{accepted}</strong>
        </div>
        <div className="referral-legend-item">
          <span className="referral-label">Awaiting</span>
          <strong>{pending}</strong>
        </div>
        <div className="referral-legend-item">
          <span className="referral-label">Declined</span>
          <strong>{declined}</strong>
        </div>
      </div>
      <div className="referral-footer">
        <span>Reassign or escalate from the referrals page.</span>
        <button
          type="button"
          className="ui-btn ui-btn-secondary ui-btn-sm"
          onClick={() => navigate("/referrals")}
        >
          Open referrals
        </button>
      </div>
    </section>
  );
}

function ActivityPanel({
  items,
}: {
  items: NonNullable<DashboardSummary["recentActivity"]>;
}) {
  return (
    <section className="dashboard-panel">
      <div className="panel-heading">
        <div>
          <h2>Recent activity</h2>
          <p>The append-only audit trail.</p>
        </div>
      </div>
      {items.length === 0 ? (
        <div className="empty-state">
          <p>No activity recorded yet.</p>
        </div>
      ) : (
        <div className="activity-list">
          {items.map((item) => (
            <div className="activity-item" key={item.id}>
              <span className="activity-marker">{initialsOf(item.actor)}</span>
              <div className="activity-content">
                <p>{item.description}</p>
                <div className="activity-meta">
                  <span>{item.actor}</span>
                  {item.actorRole && <span>{humanize(item.actorRole)}</span>}
                  <span>{formatDateTime(item.timestamp)}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
