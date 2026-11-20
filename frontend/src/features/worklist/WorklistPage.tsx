import "./worklist.css";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ChevronRight,
  Clock,
  Layers,
  RotateCcw,
  Search,
  SlidersHorizontal,
  UserX,
} from "lucide-react";
import { useSearchParams } from "react-router-dom";
import StatusBadge, { statusLabel } from "../../components/ui/StatusBadge";
import FlagBadges, { PriorityBadge } from "../../components/ui/FlagBadges";
import Pagination from "../../components/ui/Pagination";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "../../components/ui/StateViews";
import { getWorklist } from "../../services/api/casesApi";
import type {
  CaseStatus,
  Priority,
  WorklistCase,
  WorklistQuery,
  WorklistResponse,
  WorklistTab,
} from "../../services/api/v6.types";
import { formatDateTime, formatTimeLeft, initialsOf } from "../../utils/format";
import CaseDrawer from "../case/CaseDrawer";

const TABS: { id: WorklistTab; label: string }[] = [
  { id: "ALL", label: "All" },
  { id: "URGENT", label: "Urgent" },
  { id: "OVERDUE", label: "Overdue" },
  { id: "EXCEPTIONS", label: "Exceptions" },
  { id: "UNASSIGNED", label: "Unassigned" },
  { id: "MESSAGE_FAILED", label: "Message failed" },
  { id: "NOT_EXPLAINED", label: "Not explained" },
  { id: "DATA_MISSING", label: "Data missing" },
];

const STATUSES: CaseStatus[] = [
  "NEW",
  "AWAITING_CLASSIFICATION",
  "URGENT_ROUTING",
  "NOTIFYING",
  "AWAITING_ACK",
  "AWAITING_CONFIRMATION",
  "REFERRAL_PENDING",
  "AWAITING_APPOINTMENT",
  "AWAITING_TREATMENT",
  "READY_TO_CLOSE",
  "CLOSED",
];

const PRIORITIES: Priority[] = ["URGENT", "HIGH", "NORMAL"];

function tabCount(summary: WorklistResponse["summary"], tab: WorklistTab): number | null {
  switch (tab) {
    case "URGENT":
      return summary.urgentCases;
    case "OVERDUE":
      return summary.overdueCases;
    case "UNASSIGNED":
      return summary.unassignedCases;
    case "EXCEPTIONS":
      return summary.exceptionCases ?? 0;
    case "MESSAGE_FAILED":
      return summary.messageFailedCases ?? 0;
    case "NOT_EXPLAINED":
      return summary.notExplainedCases ?? 0;
    case "DATA_MISSING":
      return summary.dataMissingCases ?? 0;
    default:
      return null;
  }
}

function PatientCell({ item }: { item: WorklistCase }) {
  return (
    <div className="worklist-patient">
      <div className="wl-patient-line">
        <span className="wl-avatar">{initialsOf(item.patient.displayLabel)}</span>
        <strong>{item.patient.displayLabel}</strong>
      </div>
      <span>
        {item.patient.ageYears ? `${item.patient.ageYears}y` : "Age not recorded"}
        {item.patient.sex ? ` · ${item.patient.sex}` : ""}
      </span>
    </div>
  );
}

function CaseCell({ item }: { item: WorklistCase }) {
  return (
    <div className="worklist-screening">
      <strong className="wl-mono">{item.caseId}</strong>
      <span>{item.trackerId}</span>
    </div>
  );
}

function ScreeningCell({ item }: { item: WorklistCase }) {
  return (
    <div className="worklist-screening">
      <strong>{item.screening?.type ?? "No screening"}</strong>
      <span>{item.screening?.outcome ?? "—"}</span>
    </div>
  );
}

function OwnerCell({ item }: { item: WorklistCase }) {
  return (
    <div className="worklist-patient">
      <strong>{item.owner?.displayName ?? "Unassigned"}</strong>
      <span>{item.owner?.role ? item.owner.role.replaceAll("_", " ").toLowerCase() : "No owner"}</span>
    </div>
  );
}

function TimeCell({ item }: { item: WorklistCase }) {
  const overdue = item.timeLeftHours !== null && item.timeLeftHours < 0;
  return (
    <div className="worklist-patient">
      <strong className={overdue ? "wl-time-overdue" : undefined}>
        {formatTimeLeft(item.timeLeftHours)}
      </strong>
      <span>{item.dueAt ? formatDateTime(item.dueAt) : "No due date"}</span>
    </div>
  );
}

function WorklistPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [tab, setTab] = useState<WorklistTab>("ALL");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [priority, setPriority] = useState<Priority | "">("");
  const [status, setStatus] = useState<CaseStatus | "">("");
  const [sortBy, setSortBy] = useState<WorklistQuery["sortBy"]>("default");
  const [includeClosed, setIncludeClosed] = useState(
    () => searchParams.get("includeClosed") === "true"
  );
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [data, setData] = useState<WorklistResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [openCaseId, setOpenCaseId] = useState<string | null>(
    searchParams.get("caseId")
  );

  useEffect(() => {
    setOpenCaseId(searchParams.get("caseId"));
  }, [searchParams]);

  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(searchInput.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    setPage(1);
  }, [tab, search, priority, status, sortBy, includeClosed]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await getWorklist({
        page,
        pageSize,
        tab,
        search: search || undefined,
        priority: priority || undefined,
        status: status || undefined,
        includeClosed,
        sortBy,
      });
      setData(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load the worklist.");
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, tab, search, priority, status, includeClosed, sortBy]);

  useEffect(() => {
    void load();
  }, [load]);

  const summary = data?.summary;
  const cases = data?.cases ?? [];
  const hasFilters = Boolean(search || priority || status || tab !== "ALL" || includeClosed);

  const stats = useMemo(
    () => [
      {
        label: "Cases in view",
        value: summary?.totalCases ?? 0,
        hint: "Current filter",
        icon: Layers,
        tone: "neutral",
      },
      {
        label: "Urgent",
        value: summary?.urgentCases ?? 0,
        hint: "Needs a person now",
        icon: AlertTriangle,
        tone: "danger",
      },
      {
        label: "Overdue",
        value: summary?.overdueCases ?? 0,
        hint: "Past the due time",
        icon: Clock,
        tone: "warning",
      },
      {
        label: "Unassigned",
        value: summary?.unassignedCases ?? 0,
        hint: "No owner yet",
        icon: UserX,
        tone: "info",
      },
    ],
    [summary]
  );

  const openCase = useCallback(
    (caseId: string) => {
      setOpenCaseId(caseId);
      const next = new URLSearchParams(searchParams);
      next.set("caseId", caseId);
      setSearchParams(next);
    },
    [searchParams, setSearchParams]
  );

  const closeCase = useCallback(() => {
    setOpenCaseId(null);
    const next = new URLSearchParams(searchParams);
    next.delete("caseId");
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  const handleCaseChanged = useCallback(() => {
    void load();
  }, [load]);

  function clearFilters() {
    setSearchInput("");
    setSearch("");
    setPriority("");
    setStatus("");
    setTab("ALL");
    setSortBy("default");
    setIncludeClosed(false);
  }

  return (
    <div className="worklist-page">
      <header className="worklist-page-heading">
        <div>
          <span className="worklist-eyebrow">CASES</span>
          <h1>Worklist</h1>
          <p>
            Every case you can see, across the whole pathway. Urgent cases come
            first, then the longest overdue.
          </p>
        </div>
      </header>

      <section className="worklist-stats" aria-label="Worklist summary">
        {stats.map((stat) => (
          <article className="worklist-stat-card" key={stat.label}>
            <div className="worklist-stat-top">
              <span>{stat.label}</span>
              <span className={`wl-stat-icon wl-stat-${stat.tone}`}>
                <stat.icon size={16} />
              </span>
            </div>
            <div className="worklist-stat-value">{stat.value}</div>
            <p>{stat.hint}</p>
          </article>
        ))}
      </section>

      <section className="worklist-filters" aria-label="Worklist filters">
        <div className="worklist-filter-heading">
          <div>
            <h2>
              <SlidersHorizontal size={15} />
              Find a case
            </h2>
            <p>Search by patient, case number or tracker ID.</p>
          </div>
          {hasFilters && (
            <button type="button" className="clear-filters" onClick={clearFilters}>
              <RotateCcw size={13} />
              Clear filters
            </button>
          )}
        </div>

        <div className="worklist-filter-controls">
          <label className="worklist-search">
            <Search size={15} />
            <input
              type="search"
              value={searchInput}
              placeholder="Patient name, case number, tracker ID"
              onChange={(event) => setSearchInput(event.target.value)}
              aria-label="Search cases"
            />
          </label>
          <select
            value={priority}
            onChange={(event) => setPriority(event.target.value as Priority | "")}
            aria-label="Filter by priority"
          >
            <option value="">All priorities</option>
            {PRIORITIES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value as CaseStatus | "")}
            aria-label="Filter by status"
          >
            <option value="">All statuses</option>
            {STATUSES.map((value) => (
              <option key={value} value={value}>
                {statusLabel(value)}
              </option>
            ))}
          </select>
          <select
            value={sortBy}
            onChange={(event) =>
              setSortBy(event.target.value as WorklistQuery["sortBy"])
            }
            aria-label="Sort cases"
          >
            <option value="default">Urgent, then overdue</option>
            <option value="dueAt">By due time</option>
            <option value="updatedAt">Recently updated</option>
            <option value="createdAt">Newest first</option>
            <option value="priority">By priority</option>
          </select>
          <label className="wl-checkbox">
            <input
              type="checkbox"
              checked={includeClosed}
              onChange={(event) => {
                setIncludeClosed(event.target.checked);
                const next = new URLSearchParams(searchParams);
                if (event.target.checked) next.set("includeClosed", "true");
                else next.delete("includeClosed");
                setSearchParams(next, { replace: true });
              }}
            />
            Include closed
          </label>
        </div>
      </section>

      <section className="worklist-table-panel">
        <div className="worklist-table-heading">
          <div>
            <h2>Cases</h2>
            <p>Select a case to open it and act on the next step.</p>
          </div>
          <span className="worklist-result-count">
            {summary?.totalCases ?? 0} result{(summary?.totalCases ?? 0) === 1 ? "" : "s"}
          </span>
        </div>

        <div className="wl-tabs" role="tablist" aria-label="Case tabs">
          {TABS.map((item) => {
            const count = summary ? tabCount(summary, item.id) : null;
            return (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={tab === item.id}
                className={`wl-tab${tab === item.id ? " is-active" : ""}`}
                onClick={() => setTab(item.id)}
              >
                {item.label}
                {count !== null && <span className="wl-tab-count">{count}</span>}
              </button>
            );
          })}
        </div>

        {error ? (
          <ErrorState message={error} onRetry={() => void load()} />
        ) : loading ? (
          <LoadingState message="Loading cases…" />
        ) : cases.length === 0 ? (
          <EmptyState
            title="No cases match this view"
            message={
              hasFilters
                ? "Try clearing the filters or choosing another tab."
                : "Cases appear here as soon as screening results arrive."
            }
            action={
              hasFilters ? (
                <button type="button" className="ui-btn ui-btn-secondary" onClick={clearFilters}>
                  Clear filters
                </button>
              ) : undefined
            }
          />
        ) : (
          <>
            <div className="worklist-table-scroll worklist-desktop-table">
              <table className="worklist-table">
                <thead>
                  <tr>
                    <th>Patient</th>
                    <th>Case</th>
                    <th>Screening</th>
                    <th>Priority</th>
                    <th>Status &amp; flags</th>
                    <th>Owner</th>
                    <th>Next action</th>
                    <th>Time left</th>
                  </tr>
                </thead>
                <tbody>
                  {cases.map((item) => (
                    <tr
                      key={item.id}
                      className="worklist-clickable-row"
                      onClick={() => openCase(item.id)}
                      tabIndex={0}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          openCase(item.id);
                        }
                      }}
                    >
                      <td>
                        <PatientCell item={item} />
                      </td>
                      <td>
                        <CaseCell item={item} />
                      </td>
                      <td>
                        <ScreeningCell item={item} />
                      </td>
                      <td>
                        <PriorityBadge priority={item.priority} />
                      </td>
                      <td>
                        <div className="wl-status-cell">
                          <StatusBadge status={item.status} />
                          <FlagBadges flags={item.flags} />
                        </div>
                      </td>
                      <td>
                        <OwnerCell item={item} />
                      </td>
                      <td className="worklist-next-action">
                        {item.nextAction?.label ?? item.nextAction?.code ?? "—"}
                      </td>
                      <td>
                        <TimeCell item={item} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="worklist-mobile-cards">
              {cases.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className="worklist-mobile-card"
                  onClick={() => openCase(item.id)}
                >
                  <div className="worklist-mobile-card-top">
                    <PatientCell item={item} />
                    <PriorityBadge priority={item.priority} />
                  </div>
                  <div className="worklist-mobile-screening">
                    <strong>
                      {item.screening?.type ?? "Screening"} · {item.screening?.outcome ?? "—"}
                    </strong>
                    <span>
                      {item.caseId} · {statusLabel(item.status)}
                    </span>
                  </div>
                  <div className="wl-status-cell" style={{ marginTop: 10 }}>
                    <FlagBadges flags={item.flags} />
                  </div>
                  <div className="worklist-mobile-details">
                    <div>
                      <span>Owner</span>
                      <strong>{item.owner?.displayName ?? "Unassigned"}</strong>
                    </div>
                    <div>
                      <span>Time left</span>
                      <strong>{formatTimeLeft(item.timeLeftHours)}</strong>
                    </div>
                    <div>
                      <span>Next action</span>
                      <strong>{item.nextAction?.label ?? "—"}</strong>
                    </div>
                    <div>
                      <span>Facility</span>
                      <strong>{item.facility.name}</strong>
                    </div>
                  </div>
                  <div className="worklist-mobile-card-footer">
                    Open case <ChevronRight size={14} />
                  </div>
                </button>
              ))}
            </div>

            <Pagination
              page={page}
              pageSize={pageSize}
              total={data?.total ?? 0}
              onChange={setPage}
            />
          </>
        )}
      </section>

      {openCaseId && (
        <CaseDrawer
          caseId={openCaseId}
          onClose={closeCase}
          onChanged={handleCaseChanged}
        />
      )}
    </div>
  );
}

export default WorklistPage;
