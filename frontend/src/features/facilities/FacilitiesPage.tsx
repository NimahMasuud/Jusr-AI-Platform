import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Building2,
  FileDown,
  Pencil,
  Plus,
  Search,
  Trash2,
  Upload,
  Users,
  Wifi,
  WifiOff,
} from "lucide-react";
import Alert from "../../components/ui/Alert";
import ConfirmDialog from "../../components/ui/ConfirmDialog";
import Modal from "../../components/ui/Modal";
import Pagination from "../../components/ui/Pagination";
import { EmptyState, ErrorState, LoadingState } from "../../components/ui/StateViews";
import { useUser } from "../../context/UserContext";
import {
  createFacility,
  createStaff,
  deleteFacility,
  deleteStaff,
  importStaffCsv,
  listFacilities,
  listStaff,
  updateFacility,
  updateStaff,
  type StaffMember,
} from "../../services/api/adminApi";
import {
  getEventsCsvTemplate,
  getRejectedEvents,
  importEventsCsv,
  submitEvent,
  type RejectedEvent,
  type RejectedResult,
} from "../../services/api/eventsApi";
import type { FacilityRecord } from "../../services/api/v6.types";
import { formatDateTime, humanize } from "../../utils/format";
import "./facilities.css";

const STAFF_ROLES = [
  { value: "COORDINATOR", label: "Coordinator" },
  { value: "REFERRING_CLINICIAN", label: "Referring clinician" },
  { value: "RECEIVING_CLINICIAN", label: "Receiving clinician" },
  { value: "FACILITY_ADMIN", label: "Facility administrator" },
];

const WORKING_DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"];
const TIME_ZONES = [
  "Africa/Accra",
  "Africa/Abidjan",
  "Africa/Lagos",
  "Africa/Douala",
  "Africa/Nairobi",
  "Africa/Kampala",
  "Africa/Kigali",
  "Africa/Dar_es_Salaam",
  "Africa/Addis_Ababa",
  "Africa/Johannesburg",
  "Africa/Lusaka",
  "Africa/Harare",
  "Africa/Maputo",
  "Africa/Cairo",
  "Africa/Casablanca",
  "Asia/Dubai",
  "Asia/Kolkata",
  "Europe/London",
  "UTC",
];

const TIME_ZONE_LABELS: Record<string, string> = {
  "Africa/Accra": "Accra (GMT, UTC+0)",
  "Africa/Abidjan": "Abidjan (GMT, UTC+0)",
  "Africa/Lagos": "Lagos (WAT, UTC+1)",
  "Africa/Douala": "Douala (WAT, UTC+1)",
  "Africa/Nairobi": "Nairobi (EAT, UTC+3)",
  "Africa/Kampala": "Kampala (EAT, UTC+3)",
  "Africa/Kigali": "Kigali (CAT, UTC+2)",
  "Africa/Dar_es_Salaam": "Dar es Salaam (EAT, UTC+3)",
  "Africa/Addis_Ababa": "Addis Ababa (EAT, UTC+3)",
  "Africa/Johannesburg": "Johannesburg (SAST, UTC+2)",
  "Africa/Lusaka": "Lusaka (CAT, UTC+2)",
  "Africa/Harare": "Harare (CAT, UTC+2)",
  "Africa/Maputo": "Maputo (CAT, UTC+2)",
  "Africa/Cairo": "Cairo (EET, UTC+2)",
  "Africa/Casablanca": "Casablanca (WET, UTC+1)",
  "Asia/Dubai": "Abu Dhabi / Dubai (GST, UTC+4)",
  "Asia/Kolkata": "India (IST, UTC+5:30)",
  "Europe/London": "London (GMT/BST)",
  "UTC": "UTC",
};

function timeZoneLabel(zone: string): string {
  return TIME_ZONE_LABELS[zone] ?? zone;
}

type Tab = "facilities" | "staff" | "feed";

function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let value = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    if (quoted) {
      if (char === '"') {
        if (text[i + 1] === '"') {
          value += '"';
          i += 1;
        } else {
          quoted = false;
        }
      } else {
        value += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(value.trim());
      value = "";
    } else if (char === "\n") {
      row.push(value.trim());
      rows.push(row);
      row = [];
      value = "";
    } else if (char !== "\r") {
      value += char;
    }
  }
  if (value !== "" || row.length > 0) {
    row.push(value.trim());
    rows.push(row);
  }
  return rows.filter((cells) => cells.some((cell) => cell !== ""));
}

function downloadTextFile(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function withFacilityId(csv: string, facilityId: string): string {
  const rows = parseCsv(csv);
  if (rows.length === 0) return csv;
  const header = rows[0].map((cell) => cell.trim().toLowerCase());
  const facilityIndex = header.indexOf("facilityid");
  const quote = (value: string) =>
    /[",\n\r]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
  const output = rows.map((cells, rowIndex) => {
    if (rowIndex === 0) {
      return facilityIndex >= 0 ? cells : [...cells, "facilityId"];
    }
    if (facilityIndex >= 0) {
      return cells.map((cell, index) => (index === facilityIndex ? facilityId : cell));
    }
    return [...cells, facilityId];
  });
  return output.map((cells) => cells.map(quote).join(",")).join("\n");
}

function statusClass(status: string | null | undefined) {
  if (status === "CONNECTED") return "status-connected";
  if (status === "MISSING") return "status-pending";
  return "status-disconnected";
}

function FacilityEditorModal({
  facility,
  onClose,
  onSaved,
}: {
  facility: FacilityRecord | null;
  onClose: () => void;
  onSaved: (facility: FacilityRecord, connectionSummary?: string) => void;
}) {
  const editing = facility !== null;
  const [name, setName] = useState(facility?.name ?? "");
  const [type, setType] = useState(facility?.type ?? "");
  const [timeZone, setTimeZone] = useState(facility?.timeZone ?? "Africa/Lagos");
  const [days, setDays] = useState<string[]>(
    facility?.workingDays ?? ["MON", "TUE", "WED", "THU", "FRI"]
  );
  const [connectorType, setConnectorType] = useState<"FEED_SIMULATOR" | "CSV">(
    facility?.connectorType === "CSV" ? "CSV" : "FEED_SIMULATOR"
  );
  const [csvText, setCsvText] = useState("");
  const [csvFileName, setCsvFileName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const zoneOptions = useMemo(() => {
    const current = facility?.timeZone;
    return current && !TIME_ZONES.includes(current) ? [current, ...TIME_ZONES] : TIME_ZONES;
  }, [facility?.timeZone]);

  function toggleDay(day: string) {
    setDays((current) =>
      current.includes(day) ? current.filter((d) => d !== day) : [...current, day]
    );
  }

  async function connect(saved: FacilityRecord): Promise<string> {
    if (connectorType === "FEED_SIMULATOR") {
      const alreadyConnected =
        editing &&
        facility.connectionStatus === "CONNECTED" &&
        facility.connectorType === "FEED_SIMULATOR";
      if (alreadyConnected) return "";
      try {
        await submitEvent({
          eventId: `TEST-${crypto.randomUUID()}`,
          type: "TEST_EVENT",
          facilityId: saved.id,
          payload: { note: "Connection handshake from the facility directory" },
        });
        return "Simulated feed connected — the facility is live.";
      } catch (err) {
        return `Facility saved, but the feed handshake failed: ${
          err instanceof Error ? err.message : "unknown error"
        }`;
      }
    }

    if (!csvText.trim()) return "";
    try {
      const result = await importEventsCsv(withFacilityId(csvText, saved.id));
      const counts = result.counts ?? {};
      const rejectedRows = (result.results ?? []).filter((row) => row.status === "REJECTED");
      const firstMessage =
        rejectedRows.length > 0 && typeof rejectedRows[0].message === "string"
          ? ` First: ${rejectedRows[0].message}.`
          : "";
      return `CSV imported: ${counts.ACCEPTED ?? 0} accepted, ${counts.REJECTED ?? 0} rejected${
        counts.DUPLICATE ? `, ${counts.DUPLICATE} duplicate` : ""
      }.${firstMessage}`;
    } catch (err) {
      return `Facility saved, but the CSV import failed: ${
        err instanceof Error ? err.message : "unknown error"
      }`;
    }
  }

  async function save() {
    if (!name.trim()) {
      setError("Give the facility a name.");
      return;
    }
    if (connectorType === "CSV" && csvText.trim()) {
      const header = parseCsv(csvText)[0]?.map((cell) => cell.trim().toLowerCase()) ?? [];
      const missing = ["eventid", "type"].filter((column) => !header.includes(column));
      if (missing.length > 0) {
        setError(`The CSV header needs the ${missing.join(" and ")} column${missing.length > 1 ? "s" : ""}.`);
        return;
      }
    }
    setBusy(true);
    setError("");
    try {
      const saved =
        editing && facility
          ? await updateFacility(facility.id, {
              name: name.trim(),
              type: type.trim() || null,
              timeZone,
              workingDays: days,
              connectorType,
            })
          : await createFacility({
              name: name.trim(),
              type: type.trim() || undefined,
              timeZone,
              workingDays: days,
              connectorType,
            });
      const summary = await connect(saved);
      onSaved(saved, summary);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : editing
            ? "Unable to update this facility."
            : "Unable to add this facility."
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      title={editing ? "Edit facility" : "Add a facility"}
      subtitle={
        editing
          ? "Changes apply to filters and routing immediately."
          : "A new facility appears in filters and routing immediately."
      }
      onClose={onClose}
      footer={
        <>
          <button type="button" className="ui-btn ui-btn-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="button" className="ui-btn ui-btn-primary" onClick={() => void save()} disabled={busy}>
            {busy ? "Saving…" : editing ? "Save changes" : "Add facility"}
          </button>
        </>
      }
    >
      {error && <Alert tone="danger">{error}</Alert>}
      <div className="ui-field">
        <label>Name *</label>
        <input value={name} onChange={(event) => setName(event.target.value)} />
      </div>
      <div className="ui-field">
        <label>Type</label>
        <input
          value={type}
          placeholder="e.g. Specialist centre"
          onChange={(event) => setType(event.target.value)}
        />
      </div>
      <div className="ui-field">
        <label>Time zone</label>
        <select value={timeZone} onChange={(event) => setTimeZone(event.target.value)}>
          {zoneOptions.map((zone) => (
            <option key={zone} value={zone}>{timeZoneLabel(zone)}</option>
          ))}
        </select>
      </div>
      <div className="ui-field">
        <label>Working days</label>
        <div className="facility-day-row">
          {WORKING_DAYS.map((day) => (
            <label key={day} className="facility-day">
              <input
                type="checkbox"
                checked={days.includes(day)}
                onChange={() => toggleDay(day)}
              />
              {day}
            </label>
          ))}
        </div>
      </div>
      <div className="ui-field">
        <label>Connector</label>
        <select
          value={connectorType}
          onChange={(event) => setConnectorType(event.target.value as "FEED_SIMULATOR" | "CSV")}
        >
          <option value="FEED_SIMULATOR">Simulated feed (OpenMRS handshake)</option>
          <option value="CSV">CSV upload</option>
        </select>
        {connectorType === "FEED_SIMULATOR" ? (
          <span className="ui-hint">
            Saving sends a connection handshake, so the facility shows CONNECTED
            straight away. Screening results can then arrive from the EMR feed.
          </span>
        ) : (
          <span className="ui-hint">
            Upload a CSV of screening events now. The facility id is added
            automatically; each RESULT_RECEIVED row creates a case for a patient
            already registered at this facility.
          </span>
        )}
      </div>
      {connectorType === "CSV" && (
        <div className="ui-field">
          <label>Connection CSV</label>
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={async (event) => {
              const file = event.target.files?.[0];
              if (file) {
                setCsvFileName(file.name);
                setCsvText(await file.text());
              }
            }}
          />
          <textarea
            rows={5}
            value={csvText}
            onChange={(event) => {
              setCsvText(event.target.value);
              setCsvFileName("");
            }}
            placeholder={
              "eventId,type,patientId,testCode,testName,testValue,screeningType,outcome\nEMR-001,RESULT_RECEIVED,<patient id>,VIA,VIA,Positive,Cervical screening,Abnormal"
            }
            aria-label="Connection CSV"
          />
          {csvFileName && <span className="ui-hint">Loaded {csvFileName}</span>}
        </div>
      )}
    </Modal>
  );
}

function StaffEditorModal({
  member,
  facilities,
  fixedFacilityId,
  onClose,
  onSaved,
}: {
  member: StaffMember | null;
  facilities: FacilityRecord[];
  fixedFacilityId?: string;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const editing = member !== null;
  const [email, setEmail] = useState(member?.email ?? "");
  const [displayName, setDisplayName] = useState(member?.displayName ?? "");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState(member?.role ?? "COORDINATOR");
  const [facilityId, setFacilityId] = useState(member?.facilityId ?? fixedFacilityId ?? "");
  const [specialty, setSpecialty] = useState(member?.specialty ?? "");
  const [authorisedToClose, setAuthorisedToClose] = useState(member?.authorisedToClose ?? false);
  const [isActive, setIsActive] = useState(member?.isActive ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function save() {
    setBusy(true);
    setError("");
    try {
      if (editing && member) {
        if (!email.trim()) {
          setError("Email is required.");
          setBusy(false);
          return;
        }
        await updateStaff(member.id, {
          email: email.trim(),
          displayName: displayName.trim(),
          role,
          facilityId: facilityId || undefined,
          specialty: specialty.trim() || null,
          authorisedToClose,
          isActive,
        });
        onSaved(`Staff profile updated: ${displayName.trim()}.`);
      } else {
        if (!email.trim() || !displayName.trim() || password.length < 8) {
          setError("Email, name and a password of at least 8 characters are required.");
          setBusy(false);
          return;
        }
        if (!facilityId) {
          setError("Choose the facility this staff member belongs to.");
          setBusy(false);
          return;
        }
        await createStaff({
          email: email.trim(),
          displayName: displayName.trim(),
          password,
          role,
          facilityId,
          specialty: specialty.trim() || undefined,
          authorisedToClose,
        });
        onSaved(`Staff profile created: ${displayName.trim()}.`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save this staff profile.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      title={editing ? "Edit staff profile" : "Add a staff profile"}
      subtitle="Staff profiles control access. Clinical content stays within the facility."
      onClose={onClose}
      footer={
        <>
          <button type="button" className="ui-btn ui-btn-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="button" className="ui-btn ui-btn-primary" onClick={() => void save()} disabled={busy}>
            {busy ? "Saving…" : editing ? "Save changes" : "Create profile"}
          </button>
        </>
      }
    >
      {error && <Alert tone="danger">{error}</Alert>}
      <div className="ui-field">
        <label>Email *</label>
        <input
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </div>
      {!editing && (
        <div className="ui-field">
          <label>Temporary password *</label>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          <span className="ui-hint">At least 8 characters. The person should change it after signing in.</span>
        </div>
      )}
      <div className="ui-field">
        <label>Display name *</label>
        <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
      </div>
      <div className="ui-field">
        <label>Role</label>
        <select value={role} onChange={(event) => setRole(event.target.value)}>
          {STAFF_ROLES.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </div>
      {!fixedFacilityId && (
        <div className="ui-field">
          <label>Facility *</label>
          <select value={facilityId} onChange={(event) => setFacilityId(event.target.value)}>
            <option value="">Choose a facility</option>
            {facilities.map((facility) => (
              <option key={facility.id} value={facility.id}>{facility.name}</option>
            ))}
          </select>
        </div>
      )}
      <div className="ui-field">
        <label>Specialty</label>
        <input
          value={specialty}
          placeholder="e.g. Gynaecology"
          onChange={(event) => setSpecialty(event.target.value)}
        />
      </div>
      <label className="ui-checkbox">
        <input
          type="checkbox"
          checked={authorisedToClose}
          onChange={(event) => setAuthorisedToClose(event.target.checked)}
        />
        Authorised to sign off closures
      </label>
      {editing && (
        <label className="ui-checkbox">
          <input
            type="checkbox"
            checked={isActive}
            onChange={(event) => setIsActive(event.target.checked)}
          />
          Active (can sign in)
        </label>
      )}
    </Modal>
  );
}

export default function FacilitiesPage() {
  const { activeUser } = useUser();
  const isNational = activeUser?.role === "national_admin";
  const canAdmin = isNational || activeUser?.role === "facility_administrator";

  const [tab, setTab] = useState<Tab>("facilities");
  const [facilities, setFacilities] = useState<FacilityRecord[]>([]);
  const [staff, setStaff] = useState<StaffMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [staffSearch, setStaffSearch] = useState("");
  const [staffRoleFilter, setStaffRoleFilter] = useState("");
  const [staffFacilityFilter, setStaffFacilityFilter] = useState("");
  const [facilityEditor, setFacilityEditor] = useState<FacilityRecord | "new" | null>(null);
  const [staffEditor, setStaffEditor] = useState<StaffMember | "new" | null>(null);
  const [rejected, setRejected] = useState<RejectedResult | null>(null);
  const [rejectedPage, setRejectedPage] = useState(1);
  const [rejectedError, setRejectedError] = useState("");
  const [rejectedBusy, setRejectedBusy] = useState(false);
  const [rejectedUpdatedAt, setRejectedUpdatedAt] = useState<Date | null>(null);
  const [facilityRemoving, setFacilityRemoving] = useState<FacilityRecord | null>(null);
  const [staffRemoving, setStaffRemoving] = useState<StaffMember | null>(null);
  const [removingBusy, setRemovingBusy] = useState(false);
  const [feedFacilityFilter, setFeedFacilityFilter] = useState("");
  const [csvText, setCsvText] = useState("");
  const [csvBusy, setCsvBusy] = useState(false);
  const [csvSummary, setCsvSummary] = useState<string>("");
  const [csvRows, setCsvRows] = useState<Array<Record<string, unknown>>>([]);
  const [facilitiesCsvOpen, setFacilitiesCsvOpen] = useState(false);
  const [facilitiesCsvText, setFacilitiesCsvText] = useState("");
  const [facilitiesCsvBusy, setFacilitiesCsvBusy] = useState(false);
  const [facilitiesCsvSummary, setFacilitiesCsvSummary] = useState("");
  const [facilitiesCsvErrors, setFacilitiesCsvErrors] = useState<string[]>([]);
  const [staffCsvOpen, setStaffCsvOpen] = useState(false);
  const [staffCsvText, setStaffCsvText] = useState("");
  const [staffCsvBusy, setStaffCsvBusy] = useState(false);
  const [staffCsvSummary, setStaffCsvSummary] = useState("");
  const [staffCsvRejected, setStaffCsvRejected] = useState<
    Array<{ row: number; email: string | null; message: string }>
  >([]);

  const loadDirectory = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [facilityRows, staffRows] = await Promise.all([
        listFacilities(),
        listStaff({
          facilityId: staffFacilityFilter || undefined,
          role: staffRoleFilter || undefined,
        }),
      ]);
      setFacilities(facilityRows);
      setStaff(staffRows.filter((member) => member.isActive));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load facilities.");
    } finally {
      setLoading(false);
    }
  }, [staffFacilityFilter, staffRoleFilter]);

  useEffect(() => {
    void loadDirectory();
  }, [loadDirectory]);

  const loadRejected = useCallback(async () => {
    setRejectedBusy(true);
    setRejectedError("");
    try {
      const result = await getRejectedEvents({
        facilityId: (isNational ? feedFacilityFilter : undefined) || undefined,
        page: rejectedPage,
        pageSize: 20,
      });
      setRejected(result);
      setRejectedUpdatedAt(new Date());
    } catch (err) {
      setRejectedError(
        err instanceof Error ? err.message : "Unable to load rejected items."
      );
    } finally {
      setRejectedBusy(false);
    }
  }, [isNational, feedFacilityFilter, rejectedPage]);

  useEffect(() => {
    void loadRejected();
  }, [loadRejected]);

  // The feed must never look frozen: poll while the page is open and refresh
  // whenever the tab regains focus.
  useEffect(() => {
    const interval = window.setInterval(() => void loadRejected(), 20000);
    const onFocus = () => void loadRejected();
    const onVisible = () => {
      if (document.visibilityState === "visible") void loadRejected();
    };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [loadRejected]);

  async function removeFacility() {
    if (!facilityRemoving) return;
    setRemovingBusy(true);
    setError("");
    try {
      await deleteFacility(facilityRemoving.id);
      setNotice(`Facility ${facilityRemoving.name} removed.`);
      setFacilityRemoving(null);
      await loadDirectory();
      await loadRejected();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to remove this facility."
      );
      setFacilityRemoving(null);
    } finally {
      setRemovingBusy(false);
    }
  }

  async function removeStaffMember() {
    if (!staffRemoving) return;
    setRemovingBusy(true);
    setError("");
    try {
      await deleteStaff(staffRemoving.id);
      setNotice(`${staffRemoving.displayName} removed from the staff directory.`);
      setStaffRemoving(null);
      await loadDirectory();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to remove this staff member."
      );
      setStaffRemoving(null);
    } finally {
      setRemovingBusy(false);
    }
  }

  const filteredFacilities = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return facilities;
    return facilities.filter((facility) =>
      `${facility.name} ${facility.code} ${facility.type ?? ""}`.toLowerCase().includes(term)
    );
  }, [facilities, search]);

  const filteredStaff = useMemo(() => {
    const term = staffSearch.trim().toLowerCase();
    if (!term) return staff;
    return staff.filter((member) =>
      `${member.displayName} ${member.email} ${member.specialty ?? ""}`.toLowerCase().includes(term)
    );
  }, [staff, staffSearch]);

  const facilityName = (id: string | null) =>
    facilities.find((facility) => facility.id === id)?.name ?? "—";

  const connectedCount = facilities.filter((f) => f.connectionStatus === "CONNECTED").length;

  async function handleCsvFile(file: File | null) {
    if (!file) return;
    const text = await file.text();
    setCsvText(text);
  }

  async function loadCsvTemplate(download: boolean) {
    setError("");
    try {
      const template = await getEventsCsvTemplate();
      setCsvText(template.csv);
      if (download) downloadTextFile("jusr-events-sample.csv", template.csv);
      setNotice(
        `Sample row loaded for ${template.facility} (patient ${template.patient}). Import it to create a case with a new case ID.`
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load the CSV template."
      );
    }
  }

  async function importCsv() {
    if (!csvText.trim()) return;
    setCsvBusy(true);
    setError("");
    setCsvSummary("");
    setCsvRows([]);
    try {
      const result = await importEventsCsv(csvText);
      const accepted = result.counts.ACCEPTED ?? 0;
      setCsvSummary(
        Object.entries(result.counts)
          .map(([status, count]) => `${humanize(status)}: ${count}`)
          .join(" · ")
      );
      setCsvRows(result.results);
      setNotice(
        accepted > 0
          ? `${accepted} event(s) imported. ${
              result.results
                .filter((row) => row.caseId)
                .map((row) => `Case ${row.caseId}`)
                .join(", ") || "Check the case list."
            }`
          : "No events were imported — review the row messages below."
      );
      await loadRejected();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to import this CSV.");
    } finally {
      setCsvBusy(false);
    }
  }

  async function importFacilitiesCsv() {
    if (!facilitiesCsvText.trim()) return;
    setFacilitiesCsvBusy(true);
    setError("");
    setFacilitiesCsvSummary("");
    setFacilitiesCsvErrors([]);
    try {
      const [header, ...rows] = parseCsv(facilitiesCsvText);
      const columns = header.map((cell) => cell.toLowerCase());
      const nameIndex = columns.indexOf("name");
      if (nameIndex === -1) {
        throw new Error("The CSV needs a 'name' column.");
      }
      let created = 0;
      const errors: string[] = [];
      for (const [offset, row] of rows.entries()) {
        const get = (key: string) => {
          const index = columns.indexOf(key.toLowerCase());
          return index === -1 ? "" : (row[index] ?? "").trim();
        };
        const name = row[nameIndex]?.trim();
        if (!name) {
          errors.push(`Row ${offset + 2}: missing name.`);
          continue;
        }
        try {
          const connector = get("connectorType").toUpperCase();
          await createFacility({
            name,
            type: get("type") || undefined,
            timeZone: get("timezone") || TIME_ZONES[0],
            workingDays: get("workingDays")
              ? get("workingDays")
                  .split("|")
                  .map((day) => day.trim().toUpperCase())
                  .filter(Boolean)
              : ["MON", "TUE", "WED", "THU", "FRI"],
            connectorType: connector === "CSV" ? "CSV" : "FEED_SIMULATOR",
          });
          created += 1;
        } catch (err) {
          errors.push(
            `Row ${offset + 2} (${name}): ${
              err instanceof Error ? err.message : "Unable to add this facility."
            }`
          );
        }
      }
      setFacilitiesCsvSummary(
        `${created} facility profile(s) added, ${errors.length} rejected.`
      );
      setFacilitiesCsvErrors(errors);
      if (created > 0) {
        setNotice(`${created} facility profile(s) imported.`);
        await loadDirectory();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to import this CSV.");
    } finally {
      setFacilitiesCsvBusy(false);
    }
  }

  async function importStaff() {
    if (!staffCsvText.trim()) return;
    setStaffCsvBusy(true);
    setError("");
    setStaffCsvSummary("");
    setStaffCsvRejected([]);
    try {
      const result = await importStaffCsv(staffCsvText);
      setStaffCsvSummary(
        `${result.counts.created} created, ${result.counts.rejected} rejected.`
      );
      setStaffCsvRejected(result.rejected);
      if (result.counts.created > 0) {
        setNotice(`${result.counts.created} staff profile(s) imported.`);
        await loadDirectory();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to import this CSV.");
    } finally {
      setStaffCsvBusy(false);
    }
  }

  return (
    <div className="page-container facilities-page">
      <div className="page-heading facilities-heading">
        <div>
          <span className="facilities-eyebrow">FACILITY ADMINISTRATION</span>
          <h1>Facilities</h1>
          <p>Manage facility profiles, staff access and connection status.</p>
        </div>

        {canAdmin && tab === "facilities" && (
          <div className="facility-heading-actions">
            <button className="add-facility-button" onClick={() => setFacilityEditor("new")}>
              <Plus size={17} />
              Add facility
            </button>
            <button
              className="ui-btn ui-btn-secondary"
              onClick={() => {
                setFacilitiesCsvOpen(true);
                setFacilitiesCsvSummary("");
                setFacilitiesCsvErrors([]);
              }}
            >
              <Upload size={15} /> Import CSV
            </button>
          </div>
        )}
        {canAdmin && tab === "staff" && (
          <div className="facility-heading-actions">
            <button className="add-facility-button" onClick={() => setStaffEditor("new")}>
              <Plus size={17} />
              Add staff
            </button>
            <button
              className="ui-btn ui-btn-secondary"
              onClick={() => {
                setStaffCsvOpen(true);
                setStaffCsvSummary("");
                setStaffCsvRejected([]);
              }}
            >
              <Upload size={15} /> Import CSV
            </button>
          </div>
        )}
      </div>

      <div className="wl-tabs" role="tablist" style={{ background: "transparent", padding: 0, border: 0 }}>
        {[
          { id: "facilities" as Tab, label: "Facilities" },
          { id: "staff" as Tab, label: "Staff profiles" },
          { id: "feed" as Tab, label: "Data feed" },
        ].map((option) => (
          <button
            key={option.id}
            type="button"
            role="tab"
            aria-selected={tab === option.id}
            className={`wl-tab${tab === option.id ? " is-active" : ""}`}
            onClick={() => setTab(option.id)}
          >
            {option.label}
          </button>
        ))}
      </div>

      {notice && <Alert tone="success">{notice}</Alert>}
      {error && <Alert tone="danger">{error}</Alert>}

      {loading ? (
        <LoadingState message="Loading facility administration…" />
      ) : !facilities.length && error ? (
        <ErrorState message={error} onRetry={() => void loadDirectory()} />
      ) : tab === "facilities" ? (
        <>
          <section className="facility-summary-grid">
            <div className="facility-summary-card">
              <span className="facility-summary-icon"><Building2 size={19} /></span>
              <div><p>Total facilities</p><h2>{facilities.length}</h2></div>
            </div>
            <div className="facility-summary-card">
              <span className="facility-summary-icon connected-icon"><Wifi size={19} /></span>
              <div><p>Connected</p><h2>{connectedCount}</h2></div>
            </div>
            <div className="facility-summary-card">
              <span className="facility-summary-icon staff-icon"><Users size={19} /></span>
              <div><p>Staff profiles</p><h2>{staff.length}</h2></div>
            </div>
            <div className="facility-summary-card">
              <span className="facility-summary-icon rejected-icon"><AlertCircle size={19} /></span>
              <div><p>Rejected items</p><h2>{rejected?.total ?? "—"}</h2></div>
            </div>
          </section>

          <section className="facilities-content">
            <div className="facilities-content-heading">
              <div>
                <h2>Registered facilities</h2>
                <p>Facility connection and integration overview.</p>
              </div>
              <div className="facility-search">
                <Search size={16} />
                <input
                  type="search"
                  placeholder="Search facilities..."
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </div>
            </div>

            <div className="facility-list">
              {filteredFacilities.map((facility) => (
                <div className="facility-row" key={facility.id}>
                  <span className="facility-row-icon"><Building2 size={20} /></span>
                  <span className="facility-row-main">
                    <strong>{facility.name}</strong>
                    <small>
                      {facility.type ?? "Facility"} · {facility.code} · {facility.connectorType ?? "—"}
                    </small>
                  </span>
                  <span className="facility-rejected-count">
                    {facility.workingDays?.length
                      ? `${facility.workingDays.length} working days`
                      : "No working days set"}
                  </span>
                  <span className={`facility-status ${statusClass(facility.connectionStatus)}`}>
                    {facility.connectionStatus === "CONNECTED" ? <Wifi size={14} /> : <WifiOff size={14} />}
                    {humanize(facility.connectionStatus)}
                  </span>
                  <span className="facility-rejected-count">
                    {facility.lastEventAt ? formatDateTime(facility.lastEventAt) : "No events yet"}
                  </span>
                  {canAdmin && (
                    <div className="facility-row-actions">
                      <button
                        type="button"
                        className="ui-btn ui-btn-secondary ui-btn-sm"
                        onClick={() => setFacilityEditor(facility)}
                      >
                        <Pencil size={13} /> Edit
                      </button>
                      <button
                        type="button"
                        className="ui-btn ui-btn-ghost ui-btn-sm"
                        onClick={() => setFacilityRemoving(facility)}
                      >
                        <Trash2 size={13} /> Delete
                      </button>
                    </div>
                  )}
                </div>
              ))}
              {filteredFacilities.length === 0 && (
                <div className="facility-empty-state">
                  <Building2 size={25} />
                  <strong>No facilities found</strong>
                  <p>Try a different search term.</p>
                </div>
              )}
            </div>
          </section>

          <section className="facilities-content access-settings-content">
            <div className="facilities-content-heading">
              <div>
                <h2>Access settings</h2>
                <p>Role-level access boundaries. Permissions are enforced by the backend.</p>
              </div>
            </div>

            <div className="access-settings-grid">
              <div className="access-role-card">
                <h3>Coordinator</h3>
                <p>Coordinates patient follow-up and case tracking.</p>
                <span>Facility-scoped access</span>
              </div>
              <div className="access-role-card">
                <h3>Referring clinician</h3>
                <p>Reviews cases and makes clinical decisions.</p>
                <span>Facility-scoped clinical access</span>
              </div>
              <div className="access-role-card">
                <h3>Receiving clinician</h3>
                <p>Manages incoming referrals and consultation outcomes.</p>
                <span>Facility-scoped clinical access</span>
              </div>
              <div className="access-role-card">
                <h3>Facility administrator</h3>
                <p>Manages facility connections, staff profiles and access.</p>
                <span>No clinical case content</span>
              </div>
            </div>
          </section>
        </>
      ) : tab === "staff" ? (
        <section className="facilities-content staff-content">
          <div className="facilities-content-heading">
            <div>
              <h2>Staff profiles</h2>
              <p>Manage staff profiles and facility assignments.</p>
            </div>
            <div className="facility-search">
              <Search size={16} />
              <input
                type="search"
                placeholder="Search staff..."
                value={staffSearch}
                onChange={(event) => setStaffSearch(event.target.value)}
              />
            </div>
          </div>

          <div className="facility-filter-row">
            {isNational && (
              <label>
                <span>Facility</span>
                <select
                  value={staffFacilityFilter}
                  onChange={(event) => setStaffFacilityFilter(event.target.value)}
                >
                  <option value="">All facilities</option>
                  {facilities.map((facility) => (
                    <option key={facility.id} value={facility.id}>{facility.name}</option>
                  ))}
                </select>
              </label>
            )}
            <label>
              <span>Role</span>
              <select
                value={staffRoleFilter}
                onChange={(event) => setStaffRoleFilter(event.target.value)}
              >
                <option value="">All roles</option>
                {STAFF_ROLES.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
          </div>

          <div className="facility-list">
            {filteredStaff.map((member) => (
              <div className="facility-row" key={member.id}>
                <span className="facility-row-icon"><Users size={20} /></span>
                <span className="facility-row-main">
                  <strong>{member.displayName}</strong>
                  <small>
                    {member.email} · {humanize(member.role)}
                    {member.specialty ? ` · ${member.specialty}` : ""}
                  </small>
                </span>
                <span className="facility-rejected-count">{facilityName(member.facilityId)}</span>
                <span className="facility-rejected-count">
                  {member.authorisedToClose ? "Closure sign-off" : "No closure sign-off"}
                </span>
                <span className={`facility-status ${member.isActive ? "status-connected" : "status-disconnected"}`}>
                  {member.isActive ? "Active" : "Inactive"}
                </span>
                {canAdmin && (
                  <div className="facility-row-actions">
                    <button
                      type="button"
                      className="ui-btn ui-btn-secondary ui-btn-sm"
                      onClick={() => setStaffEditor(member)}
                    >
                      <Pencil size={13} /> Edit
                    </button>
                    <button
                      type="button"
                      className="ui-btn ui-btn-ghost ui-btn-sm"
                      onClick={() => setStaffRemoving(member)}
                      disabled={member.id === activeUser?.id}
                      title={
                        member.id === activeUser?.id
                          ? "You cannot remove your own account"
                          : undefined
                      }
                    >
                      <Trash2 size={13} /> Delete
                    </button>
                  </div>
                )}
              </div>
            ))}
            {filteredStaff.length === 0 && (
              <div className="facility-empty-state">
                <Users size={25} />
                <strong>No staff profiles found</strong>
                <p>Try a different search term or filter.</p>
              </div>
            )}
          </div>
        </section>
      ) : (
        <>
          <section className="facilities-content">
            <div className="facilities-content-heading">
              <div>
                <h2>Rejected items</h2>
                <p>
                  Events that failed validation are listed here with their error
                  code. Nothing is silently dropped.
                </p>
                <p className="facility-feed-status">
                  {rejectedBusy
                    ? "Refreshing feed…"
                    : rejectedUpdatedAt
                      ? `Auto-updating · last checked ${formatDateTime(rejectedUpdatedAt.toISOString())}`
                      : "Auto-updates every 20 seconds."}
                </p>
              </div>
              <div className="facility-feed-actions">
                <button
                  type="button"
                  className="ui-btn ui-btn-secondary ui-btn-sm"
                  onClick={() => void loadRejected()}
                  disabled={rejectedBusy}
                >
                  Refresh now
                </button>
                {isNational && (
                  <label className="facility-inline-filter">
                    <span>Facility</span>
                    <select
                      value={feedFacilityFilter}
                      onChange={(event) => {
                        setFeedFacilityFilter(event.target.value);
                        setRejectedPage(1);
                      }}
                    >
                      <option value="">All facilities</option>
                      {facilities.map((facility) => (
                        <option key={facility.id} value={facility.id}>{facility.name}</option>
                      ))}
                    </select>
                  </label>
                )}
              </div>
            </div>

            {rejectedError && <Alert tone="danger">{rejectedError}</Alert>}

            {rejected?.byErrorCode ? (
              <div className="settings-rows">
                {Object.entries(rejected.byErrorCode).map(([code, count]) => (
                  <div className="settings-row" key={code}>
                    <div className="settings-row-main">
                      <strong>{humanize(code)}</strong>
                      <span className="settings-row-key">{code}</span>
                    </div>
                    <div className="settings-row-value">
                      <strong>{count}</strong>
                      <span>items</span>
                    </div>
                  </div>
                ))}
                {Object.keys(rejected.byErrorCode).length === 0 && (
                  <EmptyState title="No rejected items" message="Every recent event was accepted." />
                )}
              </div>
            ) : (rejected?.items.length ?? 0) === 0 ? (
              <EmptyState title="No rejected items" message="Every recent event was accepted." />
            ) : (
              <>
                <div className="settings-table-wrap">
                  <table className="ui-table">
                    <thead>
                      <tr>
                        <th>Received</th>
                        <th>Event</th>
                        <th>Facility</th>
                        <th>Error</th>
                        <th>Message</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rejected?.items.map((item: RejectedEvent) => (
                        <tr key={item.id}>
                          <td>{formatDateTime(item.receivedAt)}</td>
                          <td>
                            <strong>{item.type}</strong>
                            <div className="settings-row-key">{item.eventId}</div>
                          </td>
                          <td>{item.facilityId ?? "—"}</td>
                          <td>{humanize(item.errorCode)}</td>
                          <td>{item.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <Pagination
                  page={rejectedPage}
                  pageSize={20}
                  total={rejected?.total ?? 0}
                  onChange={setRejectedPage}
                />
              </>
            )}
          </section>

          {isNational && (
            <section className="facilities-content">
              <div className="facilities-content-heading">
                <div>
                  <h2>Import events by CSV</h2>
                  <p>
                    Upload a CSV of inbound events. Each row is processed on its
                    own; one refusal does not stop the rest.
                  </p>
                </div>
              </div>

              <div className="csv-import">
                <input
                  type="file"
                  accept=".csv,text/csv"
                  onChange={(event) => void handleCsvFile(event.target.files?.[0] ?? null)}
                />
                <textarea
                  value={csvText}
                  placeholder="eventId,type,facilityId,payload..."
                  onChange={(event) => setCsvText(event.target.value)}
                  rows={6}
                />
                <div className="csv-import-actions">
                  <button
                    type="button"
                    className="ui-btn ui-btn-secondary"
                    onClick={() => void loadCsvTemplate(false)}
                  >
                    <FileDown size={15} /> Load sample row
                  </button>
                  <button
                    type="button"
                    className="ui-btn ui-btn-secondary"
                    onClick={() => void loadCsvTemplate(true)}
                  >
                    <FileDown size={15} /> Download sample CSV
                  </button>
                  <button
                    type="button"
                    className="ui-btn ui-btn-primary"
                    onClick={() => void importCsv()}
                    disabled={csvBusy || !csvText.trim()}
                  >
                    <Upload size={15} />
                    {csvBusy ? "Importing…" : "Import CSV"}
                  </button>
                  {csvSummary && <span className="settings-helper">{csvSummary}</span>}
                </div>
                {csvRows.length > 0 && (
                  <ul className="csv-rejected">
                    {csvRows.map((row, index) => (
                      <li key={index}>
                        Row {String(row.row ?? index + 2)}:{" "}
                        <strong>{String(row.status ?? "UNKNOWN")}</strong>
                        {row.caseId ? ` · case ${String(row.caseId)}` : ""}
                        {row.trackerId ? ` · tracker ${String(row.trackerId)}` : ""}
                        {row.message ? ` · ${String(row.message)}` : ""}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </section>
          )}
        </>
      )}

      {facilityEditor && (
        <FacilityEditorModal
          facility={facilityEditor === "new" ? null : facilityEditor}
          onClose={() => setFacilityEditor(null)}
          onSaved={(facility, connectionSummary) => {
            const wasEditing = facilityEditor !== "new";
            setFacilityEditor(null);
            setNotice(
              `${
                wasEditing
                  ? `Facility updated: ${facility.name}.`
                  : `Facility added: ${facility.name}.`
              }${connectionSummary ? ` ${connectionSummary}` : ""}`
            );
            void loadDirectory();
          }}
        />
      )}

      {facilitiesCsvOpen && (
        <Modal
          open
          title="Import facility profiles by CSV"
          subtitle="Columns: name, type (optional), timeZone (optional), workingDays (optional, e.g. MON|TUE|WED), connectorType (optional: FEED_SIMULATOR or CSV)"
          onClose={() => setFacilitiesCsvOpen(false)}
          footer={
            <>
              <button
                type="button"
                className="ui-btn ui-btn-secondary"
                onClick={() => setFacilitiesCsvOpen(false)}
              >
                Close
              </button>
              <button
                type="button"
                className="ui-btn ui-btn-primary"
                onClick={() => void importFacilitiesCsv()}
                disabled={facilitiesCsvBusy || !facilitiesCsvText.trim()}
              >
                {facilitiesCsvBusy ? "Importing…" : "Import CSV"}
              </button>
            </>
          }
        >
          {error && <Alert tone="danger">{error}</Alert>}
          <div className="csv-import">
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={async (event) => {
                const file = event.target.files?.[0];
                if (file) setFacilitiesCsvText(await file.text());
              }}
            />
            <textarea
              rows={8}
              value={facilitiesCsvText}
              onChange={(event) => setFacilitiesCsvText(event.target.value)}
              placeholder={"name,type,timeZone,workingDays,connectorType\nHope Clinic,District Hospital,Africa/Lagos,MON|TUE|WED|THU|FRI,FEED_SIMULATOR"}
            />
            {facilitiesCsvSummary && (
              <p className="settings-helper">{facilitiesCsvSummary}</p>
            )}
            {facilitiesCsvErrors.length > 0 && (
              <ul className="csv-rejected">
                {facilitiesCsvErrors.map((message) => (
                  <li key={message}>{message}</li>
                ))}
              </ul>
            )}
          </div>
        </Modal>
      )}

      {staffCsvOpen && (
        <Modal
          open
          title="Import staff profiles by CSV"
          subtitle="Columns: email, displayName, password, role, facilityId (optional), specialty (optional), authorisedToClose (optional)"
          onClose={() => setStaffCsvOpen(false)}
          footer={
            <>
              <button
                type="button"
                className="ui-btn ui-btn-secondary"
                onClick={() => setStaffCsvOpen(false)}
              >
                Close
              </button>
              <button
                type="button"
                className="ui-btn ui-btn-primary"
                onClick={() => void importStaff()}
                disabled={staffCsvBusy || !staffCsvText.trim()}
              >
                {staffCsvBusy ? "Importing…" : "Import CSV"}
              </button>
            </>
          }
        >
          {error && <Alert tone="danger">{error}</Alert>}
          <div className="csv-import">
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={async (event) => {
                const file = event.target.files?.[0];
                if (file) setStaffCsvText(await file.text());
              }}
            />
            <textarea
              rows={8}
              value={staffCsvText}
              onChange={(event) => setStaffCsvText(event.target.value)}
              placeholder="email,displayName,password,role,specialty,authorisedToClose"
            />
            {staffCsvSummary && <p className="settings-helper">{staffCsvSummary}</p>}
            {staffCsvRejected.length > 0 && (
              <ul className="csv-rejected">
                {staffCsvRejected.map((row) => (
                  <li key={row.row}>
                    Row {row.row}
                    {row.email ? ` (${row.email})` : ""}: {row.message}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Modal>
      )}

      {staffEditor && (
        <StaffEditorModal
          member={staffEditor === "new" ? null : staffEditor}
          facilities={facilities}
          fixedFacilityId={
            activeUser?.role === "facility_administrator"
              ? activeUser.facility?.id || undefined
              : undefined
          }
          onClose={() => setStaffEditor(null)}
          onSaved={(message) => {
            setStaffEditor(null);
            setNotice(message);
            void loadDirectory();
          }}
        />
      )}

      <ConfirmDialog
        open={facilityRemoving !== null}
        title="Delete this facility?"
        message={
          facilityRemoving
            ? `${facilityRemoving.name} (${facilityRemoving.code}) will be removed from the directory, along with its feed events. Facilities with patients, staff or cases cannot be deleted.`
            : undefined
        }
        confirmLabel="Delete facility"
        tone="danger"
        busy={removingBusy}
        onConfirm={() => void removeFacility()}
        onCancel={() => setFacilityRemoving(null)}
      />

      <ConfirmDialog
        open={staffRemoving !== null}
        title="Delete this staff member?"
        message={
          staffRemoving
            ? `${staffRemoving.displayName} will be removed from the staff directory and can no longer sign in. Their past cases and audit history are kept.`
            : undefined
        }
        confirmLabel="Delete staff member"
        tone="danger"
        busy={removingBusy}
        onConfirm={() => void removeStaffMember()}
        onCancel={() => setStaffRemoving(null)}
      />
    </div>
  );
}
