import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CalendarClock,
  Info,
  ListTree,
  Pencil,
  Plus,
  RotateCcw,
  Settings as SettingsIcon,
  ShieldCheck,
  Trash2,
  Users,
  Zap,
} from "lucide-react";
import Alert from "../../components/ui/Alert";
import ConfirmDialog from "../../components/ui/ConfirmDialog";
import Modal from "../../components/ui/Modal";
import { ErrorState, LoadingState } from "../../components/ui/StateViews";
import { useUser } from "../../context/UserContext";
import { normalizeSpecialty } from "../case/useStaff";
import { listFacilities, listStaff, type StaffMember } from "../../services/api/adminApi";
import {
  advanceDemoClock,
  getDemoClock,
  resetDemoClock,
  type DemoClockState,
} from "../../services/api/demoApi";
import {
  createRoutingRule,
  createSpecialtyEntry,
  deleteRoutingRule,
  deleteSetting,
  deleteSpecialtyBackup,
  deleteSpecialtyEntry,
  getSettings,
  listRoutingRules,
  listSpecialtyBackups,
  listSpecialtyCatalog,
  putSetting,
  putSpecialtyBackup,
  updateRoutingRule,
  updateSpecialtyEntry,
  type RoutingRule,
  type RoutingRuleInput,
  type SettingsResponse,
  type SpecialtyBackupRecord,
  type SpecialtyCatalogEntry,
} from "../../services/api/settingsApi";
import type { FacilityRecord } from "../../services/api/v6.types";
import { formatDateTime, humanize } from "../../utils/format";
import "./settings.css";

const LIMIT_UNITS = ["minutes", "hours", "days", "working_days"];
const URGENCY_OPTIONS = ["", "NORMAL", "HIGH", "URGENT"];

type LimitValue = { value: number; unit: string };

const GROUPS = [
  { id: "limits", title: "Workflow time limits", description: "Overdue threshold for each case status. Working-day limits skip weekends.", prefixes: ["limit."] },
  { id: "urgent", title: "Urgent routing", description: "Acceptance limits and escalation before the backup clinician takes over.", prefixes: ["urgent."] },
  { id: "referrals", title: "Referrals", description: "Second acceptance limit before a referral is marked not accepted in time.", prefixes: ["referral."] },
  { id: "consultations", title: "Consultations", description: "Reply limits for consultations, standard and urgent.", prefixes: ["consultation."] },
  { id: "messages", title: "Messages", description: "Delivery attempts and the delay before each retry.", prefixes: ["message."] },
  { id: "closure", title: "Closure", description: "Minimum attempts, routes and window before an UNREACHABLE closure is allowed.", prefixes: ["closure."] },
  { id: "reminders", title: "Acknowledgement reminders", description: "Reminder schedule approval for cases waiting for a patient acknowledgement (50% and 100% of the limit).", prefixes: ["reminder."] },
  { id: "feed", title: "Feed monitoring", description: "Expected interval before a facility feed is treated as missing. Unset ignores the facility.", prefixes: ["feed."] },
  { id: "baseline", title: "Baseline assumptions", description: "Assumed baseline values used by the measures comparison.", prefixes: ["baseline."] },
];

function isLimitValue(value: unknown): value is LimitValue {
  return (
    typeof value === "object" &&
    value !== null &&
    "value" in value &&
    "unit" in value &&
    !Array.isArray(value)
  );
}

function kindOf(value: unknown) {
  if (isLimitValue(value)) return "limit" as const;
  if (Array.isArray(value)) return "list" as const;
  if (typeof value === "boolean") return "boolean" as const;
  if (typeof value === "number") return "number" as const;
  if (value === null || value === undefined) return "optional-number" as const;
  return "text" as const;
}

function displayValue(value: unknown) {
  if (value === null || value === undefined) return "Not set";
  if (isLimitValue(value)) return `${value.value} ${value.unit.replaceAll("_", " ")}`;
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "boolean") return value ? "On" : "Off";
  return String(value);
}

function labelFor(key: string) {
  const dot = key.indexOf(".");
  return humanize(dot >= 0 ? key.slice(dot + 1) : key);
}

function SettingEditor({
  settingKey,
  defaultValue,
  currentValue,
  scope,
  onClose,
  onSaved,
}: {
  settingKey: string;
  defaultValue: unknown;
  currentValue: unknown;
  scope: string;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const kind = kindOf(defaultValue);
  const start = kindOf(currentValue) === kind ? currentValue : defaultValue;

  const [limitValue, setLimitValue] = useState(
    isLimitValue(start) ? String(start.value) : ""
  );
  const [limitUnit, setLimitUnit] = useState(
    isLimitValue(start) ? start.unit : "hours"
  );
  const [listText, setListText] = useState(
    Array.isArray(start) ? start.join(", ") : ""
  );
  const [boolText, setBoolText] = useState(String(Boolean(start)));
  const [numberText, setNumberText] = useState(
    typeof start === "number" ? String(start) : ""
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function save() {
    setError("");
    let value: unknown;
    if (kind === "limit") {
      const numeric = Number(limitValue);
      if (!Number.isFinite(numeric) || numeric <= 0) {
        setError("Enter a positive number with a unit.");
        return;
      }
      value = { value: numeric, unit: limitUnit };
    } else if (kind === "list") {
      const parts = listText.split(",").map((part) => part.trim()).filter(Boolean);
      const numbers = parts.map(Number);
      if (numbers.length === 0 || numbers.some((n) => !Number.isFinite(n) || n <= 0)) {
        setError("Enter comma-separated positive numbers, for example 60, 300, 1080.");
        return;
      }
      value = numbers;
    } else if (kind === "boolean") {
      value = boolText === "true";
    } else if (kind === "number") {
      const numeric = Number(numberText);
      if (!Number.isFinite(numeric)) {
        setError("Enter a number.");
        return;
      }
      value = numeric;
    } else if (kind === "optional-number") {
      value = numberText.trim() === "" ? null : Number(numberText);
      if (value !== null && !Number.isFinite(value as number)) {
        setError("Enter a number, or leave it empty to unset.");
        return;
      }
    } else {
      setError("This setting cannot be edited here.");
      return;
    }

    setBusy(true);
    try {
      await putSetting(settingKey, scope, value);
      onSaved(`${labelFor(settingKey)} saved for ${scope}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save this setting.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      title={`Edit ${labelFor(settingKey)}`}
      subtitle={`${settingKey} · scope ${scope}`}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="ui-btn ui-btn-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="button" className="ui-btn ui-btn-primary" onClick={() => void save()} disabled={busy}>
            {busy ? "Saving…" : "Save value"}
          </button>
        </>
      }
    >
      {error && <Alert tone="danger">{error}</Alert>}

      {kind === "limit" && (
        <>
          <div className="ui-field">
            <label>Value</label>
            <input
              type="number"
              min={1}
              value={limitValue}
              onChange={(event) => setLimitValue(event.target.value)}
            />
          </div>
          <div className="ui-field">
            <label>Unit</label>
            <select value={limitUnit} onChange={(event) => setLimitUnit(event.target.value)}>
              {LIMIT_UNITS.map((unit) => (
                <option key={unit} value={unit}>{humanize(unit)}</option>
              ))}
            </select>
          </div>
        </>
      )}

      {kind === "list" && (
        <div className="ui-field">
          <label>Delays (minutes, comma separated)</label>
          <input value={listText} onChange={(event) => setListText(event.target.value)} />
          <span className="ui-hint">Each entry is the delay before the next retry, in minutes.</span>
        </div>
      )}

      {kind === "boolean" && (
        <div className="ui-field">
          <label>Value</label>
          <select value={boolText} onChange={(event) => setBoolText(event.target.value)}>
            <option value="true">On</option>
            <option value="false">Off</option>
          </select>
        </div>
      )}

      {(kind === "number" || kind === "optional-number") && (
        <div className="ui-field">
          <label>Value</label>
          <input
            type="number"
            min={kind === "optional-number" ? undefined : 0}
            value={numberText}
            placeholder={kind === "optional-number" ? "Leave empty to unset" : undefined}
            onChange={(event) => setNumberText(event.target.value)}
          />
          {kind === "optional-number" && (
            <span className="ui-hint">Leave empty to remove the value (null).</span>
          )}
        </div>
      )}

      {kind === "text" && (
        <div className="ui-field">
          <label>Value</label>
          <input value={numberText} onChange={(event) => setNumberText(event.target.value)} />
        </div>
      )}
    </Modal>
  );
}

function emptyRule(): RoutingRuleInput {
  return {
    pathway: "",
    resultCategory: "",
    suggestedUrgency: "",
    confirmatoryRequired: false,
    specialty: "",
    primaryPool: "",
    backupPool: "",
    timeToAcceptMinutes: null,
    timeToAppointmentDays: null,
    notes: "",
  };
}

function RuleEditor({
  rule,
  onClose,
  onSaved,
}: {
  rule: RoutingRule | null;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const [form, setForm] = useState<RoutingRuleInput>(() =>
    rule
      ? {
          pathway: rule.pathway,
          resultCategory: rule.resultCategory,
          suggestedUrgency: rule.suggestedUrgency ?? "",
          confirmatoryRequired: rule.confirmatoryRequired,
          specialty: rule.specialty ?? "",
          primaryPool: rule.primaryPool ?? "",
          backupPool: rule.backupPool ?? "",
          timeToAcceptMinutes: rule.timeToAcceptMinutes,
          timeToAppointmentDays: rule.timeToAppointmentDays,
          notes: rule.notes ?? "",
        }
      : emptyRule()
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function set<K extends keyof RoutingRuleInput>(key: K, value: RoutingRuleInput[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function save() {
    if (!form.pathway.trim() || !form.resultCategory.trim()) {
      setError("Pathway and result category are required.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const payload: RoutingRuleInput = {
        pathway: form.pathway.trim(),
        resultCategory: form.resultCategory.trim(),
        suggestedUrgency: form.suggestedUrgency || null,
        confirmatoryRequired: form.confirmatoryRequired,
        specialty: form.specialty?.trim() || null,
        primaryPool: form.primaryPool?.trim() || null,
        backupPool: form.backupPool?.trim() || null,
        timeToAcceptMinutes: form.timeToAcceptMinutes || null,
        timeToAppointmentDays: form.timeToAppointmentDays || null,
        notes: form.notes?.trim() || null,
      };
      if (rule) {
        await updateRoutingRule(rule.id, payload);
        onSaved(`Routing rule updated: ${payload.pathway}.`);
      } else {
        await createRoutingRule(payload);
        onSaved(`Routing rule added: ${payload.pathway}.`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save this routing rule.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      title={rule ? "Edit routing rule" : "Add routing rule"}
      subtitle="Rules suggest urgency and the receiving specialty from the screening pathway and result."
      onClose={onClose}
      footer={
        <>
          <button type="button" className="ui-btn ui-btn-secondary" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="button" className="ui-btn ui-btn-primary" onClick={() => void save()} disabled={busy}>
            {busy ? "Saving…" : "Save rule"}
          </button>
        </>
      }
    >
      {error && <Alert tone="danger">{error}</Alert>}
      <div className="routing-form-grid">
        <div className="ui-field">
          <label>Pathway *</label>
          <input value={form.pathway} onChange={(event) => set("pathway", event.target.value)} />
        </div>
        <div className="ui-field">
          <label>Result category *</label>
          <input value={form.resultCategory} onChange={(event) => set("resultCategory", event.target.value)} />
        </div>
        <div className="ui-field">
          <label>Suggested urgency</label>
          <select
            value={form.suggestedUrgency ?? ""}
            onChange={(event) => set("suggestedUrgency", event.target.value)}
          >
            {URGENCY_OPTIONS.map((option) => (
              <option key={option || "none"} value={option}>
                {option ? humanize(option) : "No suggestion"}
              </option>
            ))}
          </select>
        </div>
        <div className="ui-field">
          <label>Specialty</label>
          <input value={form.specialty ?? ""} onChange={(event) => set("specialty", event.target.value)} />
        </div>
        <div className="ui-field">
          <label>Primary pool</label>
          <input value={form.primaryPool ?? ""} onChange={(event) => set("primaryPool", event.target.value)} />
        </div>
        <div className="ui-field">
          <label>Backup pool</label>
          <input value={form.backupPool ?? ""} onChange={(event) => set("backupPool", event.target.value)} />
        </div>
        <div className="ui-field">
          <label>Accept within (minutes)</label>
          <input
            type="number"
            min={1}
            value={form.timeToAcceptMinutes ?? ""}
            onChange={(event) =>
              set("timeToAcceptMinutes", event.target.value ? Number(event.target.value) : null)
            }
          />
        </div>
        <div className="ui-field">
          <label>Appointment within (days)</label>
          <input
            type="number"
            min={1}
            value={form.timeToAppointmentDays ?? ""}
            onChange={(event) =>
              set("timeToAppointmentDays", event.target.value ? Number(event.target.value) : null)
            }
          />
        </div>
      </div>
      <label className="ui-checkbox">
        <input
          type="checkbox"
          checked={form.confirmatoryRequired}
          onChange={(event) => set("confirmatoryRequired", event.target.checked)}
        />
        A confirmatory result is required before referral
      </label>
      <div className="ui-field">
        <label>Notes</label>
        <textarea value={form.notes ?? ""} onChange={(event) => set("notes", event.target.value)} />
      </div>
    </Modal>
  );
}

export default function SettingsPage() {
  const { activeUser } = useUser();
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [facilities, setFacilities] = useState<FacilityRecord[]>([]);
  const [rules, setRules] = useState<RoutingRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [scope, setScope] = useState("");
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [removingKey, setRemovingKey] = useState<string | null>(null);
  const [removingBusy, setRemovingBusy] = useState(false);
  const [ruleEditor, setRuleEditor] = useState<RoutingRule | "new" | null>(null);
  const [ruleRemoving, setRuleRemoving] = useState<RoutingRule | null>(null);
  const [ruleRemovingBusy, setRuleRemovingBusy] = useState(false);
  const [clock, setClock] = useState<DemoClockState | null>(null);
  const [clockMinutes, setClockMinutes] = useState("60");
  const [clockBusy, setClockBusy] = useState(false);
  const [clockJobs, setClockJobs] = useState("");
  const [backups, setBackups] = useState<SpecialtyBackupRecord[]>([]);
  const [backupStaff, setBackupStaff] = useState<StaffMember[]>([]);
  const [backupSpecialty, setBackupSpecialty] = useState("");
  const [backupClinician, setBackupClinician] = useState("");
  const [backupBusy, setBackupBusy] = useState(false);
  const [backupLoading, setBackupLoading] = useState(false);
  const [backupLoadError, setBackupLoadError] = useState("");

  const [catalog, setCatalog] = useState<SpecialtyCatalogEntry[]>([]);
  const [catalogBusy, setCatalogBusy] = useState(false);
  const [catalogError, setCatalogError] = useState("");
  const [catalogEditor, setCatalogEditor] = useState<SpecialtyCatalogEntry | "new" | null>(null);
  const [catalogName, setCatalogName] = useState("");
  const [catalogLabel, setCatalogLabel] = useState("");
  const [catalogRemoving, setCatalogRemoving] = useState<SpecialtyCatalogEntry | null>(null);

  const isNational = activeUser?.role === "national_admin";
  const canEdit =
    activeUser?.role === "national_admin" ||
    activeUser?.role === "facility_administrator";

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [settingsResult, rulesResult, facilitiesResult] = await Promise.all([
        getSettings(),
        listRoutingRules(),
        listFacilities(),
      ]);
      setSettings(settingsResult);
      setRules(rulesResult);
      setFacilities(facilitiesResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load settings.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!activeUser) return;
    if (activeUser.role === "national_admin") {
      setScope("global");
    } else if (activeUser.facility?.id) {
      setScope(`facility:${activeUser.facility.id}`);
    }
  }, [activeUser]);

  useEffect(() => {
    if (!isNational) return;
    getDemoClock()
      .then(setClock)
      .catch(() => setClock(null));
  }, [isNational]);

  useEffect(() => {
    if (!canEdit) return;
    let cancelled = false;
    setBackupLoading(true);
    setBackupLoadError("");
    listSpecialtyCatalog()
      .then((rows) => {
        if (!cancelled) setCatalog(rows);
      })
      .catch((err) => {
        if (cancelled) return;
        setCatalog([]);
        setBackupLoadError(
          err instanceof Error ? err.message : "Unable to load the specialty list."
        );
      });
    listSpecialtyBackups()
      .then((rows) => {
        if (!cancelled) setBackups(rows);
      })
      .catch((err) => {
        if (cancelled) return;
        setBackups([]);
        setBackupLoadError(
          err instanceof Error ? err.message : "Unable to load named backups."
        );
      });
    listStaff({ role: "RECEIVING_CLINICIAN" })
      .then((rows) => {
        if (!cancelled) setBackupStaff(rows.filter((person) => person.isActive));
      })
      .catch((err) => {
        if (cancelled) return;
        setBackupStaff([]);
        setBackupLoadError(
          err instanceof Error ? err.message : "Unable to load receiving clinicians."
        );
      })
      .finally(() => {
        if (!cancelled) setBackupLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [canEdit]);

  const backupSpecialties = useMemo(() => {
    const names = new Set<string>();
    catalog.forEach((entry) => names.add(entry.name));
    backupStaff.forEach((person) => {
      const name = normalizeSpecialty(person.specialty);
      if (name) names.add(name);
    });
    backups.forEach((row) => names.add(row.specialty));
    return Array.from(names).sort();
  }, [catalog, backupStaff, backups]);

  const specialtyLabels = useMemo(() => {
    const map = new Map<string, string>();
    catalog.forEach((entry) => map.set(entry.name, entry.label));
    return map;
  }, [catalog]);

  const labelForSpecialty = (name: string) =>
    specialtyLabels.get(name) ?? humanize(name);

  const backupCandidates = useMemo(() => {
    const selected = normalizeSpecialty(backupSpecialty);
    if (!selected) return [];
    return backupStaff.filter(
      (person) => normalizeSpecialty(person.specialty) === selected
    );
  }, [backupStaff, backupSpecialty]);

  const facilityNames = useMemo(() => {
    const map = new Map<string, string>();
    facilities.forEach((facility) => map.set(facility.id, facility.name));
    return map;
  }, [facilities]);

  async function saveBackup() {
    if (!backupSpecialty || !backupClinician) {
      setError("Choose a specialty and a clinician.");
      return;
    }
    setBackupBusy(true);
    setError("");
    try {
      await putSpecialtyBackup(normalizeSpecialty(backupSpecialty), backupClinician);
      setNotice(`Named backup saved for ${humanize(backupSpecialty)}.`);
      setBackups(await listSpecialtyBackups());
      setBackupClinician("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save this backup.");
    } finally {
      setBackupBusy(false);
    }
  }

  async function removeBackup(specialty: string) {
    setBackupBusy(true);
    setError("");
    try {
      await deleteSpecialtyBackup(specialty);
      setNotice(`Named backup removed for ${humanize(specialty)}.`);
      setBackups(await listSpecialtyBackups());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to remove this backup.");
    } finally {
      setBackupBusy(false);
    }
  }

  function openCatalogEditor(entry: SpecialtyCatalogEntry | "new") {
    setCatalogError("");
    setCatalogEditor(entry);
    setCatalogName(entry === "new" ? "" : entry.name);
    setCatalogLabel(entry === "new" ? "" : entry.label);
  }

  async function saveCatalogEntry() {
    if (!catalogEditor) return;
    if (!catalogName.trim()) {
      setCatalogError("Give the specialty a name.");
      return;
    }
    setCatalogBusy(true);
    setCatalogError("");
    try {
      const payload = {
        name: catalogName.trim(),
        label: catalogLabel.trim() || undefined,
      };
      if (catalogEditor === "new") {
        await createSpecialtyEntry(payload);
        setNotice(`Specialty ${catalogName.trim()} added.`);
      } else {
        await updateSpecialtyEntry(catalogEditor.name, payload);
        setNotice("Specialty updated.");
      }
      setCatalogEditor(null);
      setCatalog(await listSpecialtyCatalog());
    } catch (err) {
      setCatalogError(
        err instanceof Error ? err.message : "Unable to save this specialty."
      );
    } finally {
      setCatalogBusy(false);
    }
  }

  async function removeCatalogEntry() {
    if (!catalogRemoving) return;
    setCatalogBusy(true);
    setCatalogError("");
    try {
      await deleteSpecialtyEntry(catalogRemoving.name);
      setNotice(`Specialty ${catalogRemoving.label} removed.`);
      setCatalogRemoving(null);
      setCatalog(await listSpecialtyCatalog());
    } catch (err) {
      setCatalogError(
        err instanceof Error ? err.message : "Unable to remove this specialty."
      );
    } finally {
      setCatalogBusy(false);
    }
  }

  const grouped = useMemo(() => {
    if (!settings) return [];
    const keys = Object.keys(settings.defaults).sort();
    const buckets = GROUPS.map((group) => ({
      ...group,
      entries: keys.filter((key) => group.prefixes.some((prefix) => key.startsWith(prefix))),
    }));
    const known = new Set(buckets.flatMap((bucket) => bucket.entries));
    const rest = keys.filter((key) => !known.has(key));
    if (rest.length > 0) {
      buckets.push({
        id: "other",
        title: "Other settings",
        description: "Additional configuration values.",
        prefixes: [],
        entries: rest,
      });
    }
    return buckets.filter((bucket) => bucket.entries.length > 0);
  }, [settings]);

  function effectiveFor(key: string) {
    if (!settings) return { value: undefined, source: "" };
    const scoped = settings.overrides.find((o) => o.key === key && o.scope === scope);
    const global = settings.overrides.find((o) => o.key === key && o.scope === "global");
    if (scoped) return { value: scoped.value, source: `override · ${scope}` };
    if (global && scope !== "global") return { value: global.value, source: "global override" };
    return { value: settings.defaults[key], source: "built-in default" };
  }

  const editing =
    settings && editingKey
      ? {
          key: editingKey,
          defaultValue: settings.defaults[editingKey],
          currentValue: effectiveFor(editingKey).value,
        }
      : null;
  const scopedOverride = removingKey
    ? settings?.overrides.find((o) => o.key === removingKey && o.scope === scope)
    : undefined;

  async function removeOverride() {
    if (!removingKey) return;
    setRemovingBusy(true);
    try {
      await deleteSetting(removingKey, scope);
      setNotice(`Override removed for ${labelFor(removingKey)}.`);
      setRemovingKey(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to remove this override.");
      setRemovingKey(null);
    } finally {
      setRemovingBusy(false);
    }
  }

  async function removeRule() {
    if (!ruleRemoving) return;
    setRuleRemovingBusy(true);
    try {
      await deleteRoutingRule(ruleRemoving.id);
      setNotice(`Routing rule removed: ${ruleRemoving.pathway}.`);
      setRuleRemoving(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to remove this routing rule.");
      setRuleRemoving(null);
    } finally {
      setRuleRemovingBusy(false);
    }
  }

  async function advanceClock() {
    const minutes = Number(clockMinutes);
    if (!Number.isFinite(minutes) || minutes <= 0) return;
    setClockBusy(true);
    setError("");
    try {
      const result = await advanceDemoClock(minutes);
      setClock({
        active: result.active,
        offsetMinutes: result.offsetMinutes,
        now: result.now,
        banner: result.banner,
      });
      setClockJobs(
        Object.entries(result.jobs)
          .map(([job, value]) => `${humanize(job)}: ${JSON.stringify(value)}`)
          .join(" · ")
      );
      setNotice(`Demo clock advanced by ${minutes} minutes. Scheduled jobs ran once.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to advance the demo clock.");
    } finally {
      setClockBusy(false);
    }
  }

  async function resetClock() {
    setClockBusy(true);
    setError("");
    try {
      const result = await resetDemoClock();
      setClock(result);
      setClockJobs("");
      setNotice("Demo clock reset to real time.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to reset the demo clock.");
    } finally {
      setClockBusy(false);
    }
  }

  const scopeOptions = [
    ...(isNational ? [{ value: "global", label: "Global (all facilities)" }] : []),
    ...facilities.map((facility) => ({
      value: `facility:${facility.id}`,
      label: facility.name,
    })),
  ];

  return (
    <main className="page-container settings-page">
      <div className="page-heading">
        <div>
          <span className="settings-eyebrow">CONFIGURATION</span>
          <h1>Settings</h1>
          <p>
            Time limits, routing and message rules live in one settings store.
            Changes are logged and take effect on the next check.
          </p>
        </div>
      </div>

      {notice && <Alert tone="success">{notice}</Alert>}
      {error && <Alert tone="danger">{error}</Alert>}

      {loading ? (
        <LoadingState message="Loading settings…" />
      ) : !settings ? (
        <ErrorState message={error || "No settings returned."} onRetry={() => void load()} />
      ) : (
        <div className="settings-content">
          <section className="settings-section settings-scope-section">
            <div className="settings-section-heading">
              <SettingsIcon size={19} />
              <div>
                <h2>Editing scope</h2>
                <p>
                  Overrides are most specific first: specialty, then facility,
                  then global, then the built-in default.
                </p>
              </div>
            </div>

            {canEdit ? (
              isNational ? (
                <div className="settings-field">
                  <label htmlFor="scope-select">Apply changes at</label>
                  <select
                    id="scope-select"
                    value={scope}
                    onChange={(event) => setScope(event.target.value)}
                  >
                    {scopeOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>
              ) : (
                <div className="settings-field">
                  <label>Apply changes at</label>
                  <input
                    readOnly
                    value={
                      scope.startsWith("facility:")
                        ? facilities.find((f) => `facility:${f.id}` === scope)?.name ?? scope
                        : "No facility linked to this account"
                    }
                  />
                  <small>Facility administrators change settings for their own facility only.</small>
                </div>
              )
            ) : (
              <div className="settings-notice">
                <ShieldCheck size={18} />
                <p>
                  You can view settings, but only facility administrators and
                  national administrators can change them.
                </p>
              </div>
            )}
          </section>

          {grouped.map((group) => (
            <section className="settings-section" key={group.id}>
              <div className="settings-section-heading">
                <ListTree size={19} />
                <div>
                  <h2>{group.title}</h2>
                  <p>{group.description}</p>
                </div>
              </div>

              <div className="settings-rows">
                {group.entries.map((key) => {
                  const entry = effectiveFor(key);
                  const override = settings.overrides.find(
                    (o) => o.key === key && o.scope === scope
                  );
                  return (
                    <div className="settings-row" key={key}>
                      <div className="settings-row-main">
                        <strong>{labelFor(key)}</strong>
                        <span className="settings-row-key">{key}</span>
                      </div>
                      <div className="settings-row-value">
                        <strong>{displayValue(entry.value)}</strong>
                        <span>{entry.source}</span>
                      </div>
                      {canEdit && scope && (
                        <div className="settings-row-actions">
                          <button
                            type="button"
                            className="ui-btn ui-btn-secondary ui-btn-sm"
                            onClick={() => setEditingKey(key)}
                          >
                            <Pencil size={13} /> Edit
                          </button>
                          {override && (
                            <button
                              type="button"
                              className="ui-btn ui-btn-ghost ui-btn-sm"
                              onClick={() => setRemovingKey(key)}
                            >
                              <RotateCcw size={13} /> Reset
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </section>
          ))}

          <section className="settings-section">
            <div className="settings-section-heading">
              <Info size={19} />
              <div>
                <h2>Routing table</h2>
                <p>
                  Rules map a screening pathway and result to a suggested
                  urgency, receiving specialty and acceptance limits.
                </p>
              </div>
              {canEdit && (
                <button
                  type="button"
                  className="ui-btn ui-btn-primary ui-btn-sm settings-section-action"
                  onClick={() => setRuleEditor("new")}
                >
                  <Plus size={14} /> Add rule
                </button>
              )}
            </div>

            {rules.length === 0 ? (
              <div className="settings-empty-state">No routing rules configured yet.</div>
            ) : (
              <div className="settings-table-wrap">
                <table className="ui-table">
                  <thead>
                    <tr>
                      <th>Pathway / category</th>
                      <th>Urgency</th>
                      <th>Specialty</th>
                      <th>Pools</th>
                      <th>Limits</th>
                      <th>Changed</th>
                      {canEdit && <th />}
                    </tr>
                  </thead>
                  <tbody>
                    {rules.map((rule) => (
                      <tr key={rule.id}>
                        <td>
                          <strong>{rule.pathway}</strong>
                          <div className="settings-row-key">{rule.resultCategory}</div>
                        </td>
                        <td>
                          {rule.suggestedUrgency ? humanize(rule.suggestedUrgency) : "—"}
                          {rule.confirmatoryRequired ? " · confirmatory" : ""}
                        </td>
                        <td>{rule.specialty ? humanize(rule.specialty) : "—"}</td>
                        <td>
                          {rule.primaryPool ?? "—"}
                          {rule.backupPool ? ` / ${rule.backupPool}` : ""}
                        </td>
                        <td>
                          {rule.timeToAcceptMinutes ? `${rule.timeToAcceptMinutes} min` : "—"}
                          {rule.timeToAppointmentDays ? ` · ${rule.timeToAppointmentDays} d` : ""}
                        </td>
                        <td>{formatDateTime(rule.changedAt)}</td>
                        {canEdit && (
                          <td>
                            <div className="settings-row-actions">
                              <button
                                type="button"
                                className="ui-btn ui-btn-secondary ui-btn-sm"
                                onClick={() => setRuleEditor(rule)}
                              >
                                <Pencil size={13} /> Edit
                              </button>
                              <button
                                type="button"
                                className="ui-btn ui-btn-ghost ui-btn-sm"
                                onClick={() => setRuleRemoving(rule)}
                              >
                                <Trash2 size={13} />
                              </button>
                            </div>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {canEdit && (
            <section className="settings-section">
              <div className="settings-section-heading">
                <ListTree size={19} />
                <div>
                  <h2>Named specialties</h2>
                  <p>
                    The specialty list used for routing and named backups. Add,
                    rename or remove a specialty here.
                  </p>
                </div>
                <button
                  type="button"
                  className="ui-btn ui-btn-secondary ui-btn-sm settings-section-action"
                  onClick={() => openCatalogEditor("new")}
                >
                  <Plus size={14} /> Add specialty
                </button>
              </div>

              {catalogError && !catalogEditor && !catalogRemoving && (
                <Alert tone="danger">{catalogError}</Alert>
              )}

              <div className="settings-rows">
                {catalog.map((entry) => (
                  <div className="settings-row" key={entry.name}>
                    <div className="settings-row-main">
                      <strong>{entry.label}</strong>
                      <span className="settings-row-key">{entry.name}</span>
                    </div>
                    <span className="settings-row-value">
                      <span className="ui-badge ui-badge-neutral">
                        {entry.scope === "global" ? "Global" : "This facility"}
                      </span>
                    </span>
                    {entry.editable ? (
                      <div className="settings-row-actions">
                        <button
                          type="button"
                          className="ui-btn ui-btn-secondary ui-btn-sm"
                          onClick={() => openCatalogEditor(entry)}
                          disabled={catalogBusy}
                        >
                          <Pencil size={13} /> Edit
                        </button>
                        <button
                          type="button"
                          className="ui-btn ui-btn-ghost ui-btn-sm"
                          onClick={() => setCatalogRemoving(entry)}
                          disabled={catalogBusy}
                        >
                          <Trash2 size={13} /> Delete
                        </button>
                      </div>
                    ) : (
                      <div className="settings-row-actions">
                        <span className="settings-row-key">Managed nationally</span>
                      </div>
                    )}
                  </div>
                ))}
                {catalog.length === 0 && (
                  <div className="settings-empty-state">
                    No named specialties yet. Add one to make it available in the
                    backup dropdown below.
                  </div>
                )}
              </div>
            </section>
          )}

          {canEdit && (
            <section className="settings-section">
              <div className="settings-section-heading">
                <Users size={19} />
                <div>
                  <h2>Named specialty backups</h2>
                  <p>
                    If the first clinician does not accept an urgent case in
                    time, the second escalation goes to the backup named here
                    (R-29).
                  </p>
                </div>
              </div>

              <div className="settings-rows">
                {backups.map((row) => (
                  <div className="settings-row" key={row.specialty}>
                    <div className="settings-row-main">
                      <strong>{labelForSpecialty(row.specialty)}</strong>
                      <span className="settings-row-key">{row.clinicianName ?? row.clinicianId}</span>
                    </div>
                    <div className="settings-row-actions">
                      <button
                        type="button"
                        className="ui-btn ui-btn-ghost ui-btn-sm"
                        onClick={() => void removeBackup(row.specialty)}
                        disabled={backupBusy}
                      >
                        <Trash2 size={13} /> Remove
                      </button>
                    </div>
                  </div>
                ))}
                {backups.length === 0 && (
                  <div className="settings-empty-state">No named backups yet; the second escalation picks any qualified clinician.</div>
                )}
              </div>

              <div className="routing-form-grid" style={{ marginTop: 16 }}>
                <div className="ui-field">
                  <label>Specialty</label>
                  <select
                    value={backupSpecialty}
                    onChange={(event) => {
                      setBackupSpecialty(event.target.value);
                      setBackupClinician("");
                    }}
                    disabled={backupSpecialties.length === 0}
                  >
                    <option value="">
                      {backupSpecialties.length === 0
                        ? "No specialties available yet"
                        : "Choose a specialty"}
                    </option>
                    {backupSpecialties.map((name) => (
                      <option key={name} value={name}>{labelForSpecialty(name)}</option>
                    ))}
                  </select>
                </div>
                <div className="ui-field">
                  <label>Backup clinician</label>
                  <select
                    value={backupClinician}
                    onChange={(event) => setBackupClinician(event.target.value)}
                    disabled={!backupSpecialty || backupCandidates.length === 0}
                  >
                    <option value="">
                      {backupCandidates.length === 0
                        ? "No clinician matches this specialty"
                        : "Choose a clinician"}
                    </option>
                    {backupCandidates.map((person) => {
                      const facilityName = person.facilityId
                        ? facilityNames.get(person.facilityId)
                        : undefined;
                      return (
                        <option key={person.id} value={person.id}>
                          {person.displayName}
                          {facilityName ? ` — ${facilityName}` : ""}
                        </option>
                      );
                    })}
                  </select>
                </div>
                <div className="ui-field">
                  <label>&nbsp;</label>
                  <button
                    type="button"
                    className="ui-btn ui-btn-primary"
                    onClick={() => void saveBackup()}
                    disabled={backupBusy || !backupSpecialty || !backupClinician}
                  >
                    Save backup
                  </button>
                </div>
              </div>

              {backupLoading && (
                <p className="settings-hint">Loading specialties and clinicians…</p>
              )}
              {backupLoadError && (
                <p className="settings-hint settings-hint-error">{backupLoadError}</p>
              )}
              {!backupLoading && backupStaff.length === 0 && !backupLoadError && (
                <p className="settings-hint">
                  No active receiving clinicians are registered at the facilities
                  you manage. Add a receiving clinician under Facilities → Staff,
                  then name them here.
                </p>
              )}
              {backupSpecialty && backupCandidates.length === 0 && backupStaff.length > 0 && (
                <p className="settings-hint">
                  No active receiving clinician has this specialty. Choose another
                  specialty or update a clinician's specialty under Facilities → Staff.
                </p>
              )}
            </section>
          )}

          {isNational && (
            <section className="settings-section">
              <div className="settings-section-heading">
                <CalendarClock size={19} />
                <div>
                  <h2>Demo clock</h2>
                  <p>
                    Move demo time forward to trigger overdue flags, timeouts
                    and escalations. Scheduled jobs run once on each advance.
                  </p>
                </div>
              </div>

              <div className="settings-system-row">
                <span>Current time</span>
                <strong>{clock ? formatDateTime(clock.now) : "Not loaded"}</strong>
              </div>
              <div className="settings-system-row">
                <span>Offset</span>
                <strong>
                  {clock ? `${clock.offsetMinutes} minutes ${clock.active ? "ahead" : "(real time)"}` : "—"}
                </strong>
              </div>
              {clock?.banner && <Alert tone="warning">{clock.banner}</Alert>}

              <div className="settings-input-suffix" style={{ marginTop: 16 }}>
                <input
                  type="number"
                  min={1}
                  value={clockMinutes}
                  onChange={(event) => setClockMinutes(event.target.value)}
                />
                <span>minutes</span>
                <button
                  type="button"
                  className="ui-btn ui-btn-primary ui-btn-sm"
                  onClick={() => void advanceClock()}
                  disabled={clockBusy}
                >
                  <Zap size={14} /> Advance
                </button>
                <button
                  type="button"
                  className="ui-btn ui-btn-secondary ui-btn-sm"
                  onClick={() => void resetClock()}
                  disabled={clockBusy}
                >
                  <RotateCcw size={14} /> Reset
                </button>
              </div>

              {clockJobs && <p className="settings-helper">Jobs: {clockJobs}</p>}
            </section>
          )}
        </div>
      )}

      {editing && (
        <SettingEditor
          settingKey={editing.key}
          defaultValue={editing.defaultValue}
          currentValue={editing.currentValue}
          scope={scope}
          onClose={() => setEditingKey(null)}
          onSaved={(message) => {
            setEditingKey(null);
            setNotice(message);
            void load();
          }}
        />
      )}

      <ConfirmDialog
        open={removingKey !== null}
        title="Remove this override?"
        message={
          scopedOverride
            ? `The value will fall back to the inherited setting. ${
                typeof scopedOverride.value === "object"
                  ? JSON.stringify(scopedOverride.value)
                  : String(scopedOverride.value)
              }`
            : undefined
        }
        confirmLabel="Remove override"
        tone="danger"
        busy={removingBusy}
        onConfirm={() => void removeOverride()}
        onCancel={() => setRemovingKey(null)}
      />

      {ruleEditor && (
        <RuleEditor
          rule={ruleEditor === "new" ? null : ruleEditor}
          onClose={() => setRuleEditor(null)}
          onSaved={(message) => {
            setRuleEditor(null);
            setNotice(message);
            void load();
          }}
        />
      )}

      <ConfirmDialog
        open={ruleRemoving !== null}
        title="Remove this routing rule?"
        message={ruleRemoving ? `${ruleRemoving.pathway} · ${ruleRemoving.resultCategory}` : undefined}
        confirmLabel="Remove rule"
        tone="danger"
        busy={ruleRemovingBusy}
        onConfirm={() => void removeRule()}
        onCancel={() => setRuleRemoving(null)}
      />

      {catalogEditor && (
        <Modal
          open
          title={catalogEditor === "new" ? "Add specialty" : "Edit specialty"}
          subtitle="The name is stored in upper case with underscores; the label is what staff see."
          onClose={() => setCatalogEditor(null)}
          footer={
            <>
              <button
                type="button"
                className="ui-btn ui-btn-secondary"
                onClick={() => setCatalogEditor(null)}
                disabled={catalogBusy}
              >
                Cancel
              </button>
              <button
                type="button"
                className="ui-btn ui-btn-primary"
                onClick={() => void saveCatalogEntry()}
                disabled={catalogBusy}
              >
                {catalogBusy ? "Saving…" : "Save specialty"}
              </button>
            </>
          }
        >
          {catalogError && <Alert tone="danger">{catalogError}</Alert>}
          <div className="routing-form-grid">
            <div className="ui-field">
              <label>Specialty name *</label>
              <input
                value={catalogName}
                placeholder="e.g. Colposcopy"
                onChange={(event) => setCatalogName(event.target.value)}
              />
            </div>
            <div className="ui-field">
              <label>Display label</label>
              <input
                value={catalogLabel}
                placeholder="e.g. Colposcopy"
                onChange={(event) => setCatalogLabel(event.target.value)}
              />
            </div>
          </div>
        </Modal>
      )}

      <ConfirmDialog
        open={catalogRemoving !== null}
        title="Delete this specialty?"
        message={
          catalogRemoving
            ? `${catalogRemoving.label} will be removed from the specialty list. Existing staff and backups keep their specialty value.`
            : undefined
        }
        confirmLabel="Delete specialty"
        tone="danger"
        busy={catalogBusy}
        onConfirm={() => void removeCatalogEntry()}
        onCancel={() => setCatalogRemoving(null)}
      />
    </main>
  );
}
