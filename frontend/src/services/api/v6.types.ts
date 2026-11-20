// Types for the v6 backend contract (Developer Guide workflows).

export interface PagedResult<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

export type Priority = "NORMAL" | "HIGH" | "URGENT";

export type CaseStatus =
  | "NEW"
  | "AWAITING_CLASSIFICATION"
  | "URGENT_ROUTING"
  | "NOTIFYING"
  | "AWAITING_ACK"
  | "AWAITING_CONFIRMATION"
  | "REFERRAL_PENDING"
  | "AWAITING_APPOINTMENT"
  | "AWAITING_TREATMENT"
  | "READY_TO_CLOSE"
  | "CLOSED";

export type CaseFlag =
  | "URGENT"
  | "OVERDUE"
  | "EXCEPTION"
  | "UNASSIGNED"
  | "DATA_MISSING"
  | "MESSAGE_FAILED"
  | "NOT_EXPLAINED";

export type WorklistTab =
  | "ALL"
  | "URGENT"
  | "OVERDUE"
  | "EXCEPTIONS"
  | "UNASSIGNED"
  | "MESSAGE_FAILED"
  | "NOT_EXPLAINED"
  | "DATA_MISSING";

export type DelayReasonCode =
  | "PATIENT_UNREACHABLE"
  | "PATIENT_DID_NOT_UNDERSTAND"
  | "REFERRAL_DECLINED"
  | "NO_SLOT_AVAILABLE"
  | "RESULT_OR_DATA_MISSING"
  | "PATIENT_MOVED"
  | "OTHER";

export type ClosureType =
  | "CARE_CONFIRMED"
  | "NOT_ACTIONABLE"
  | "NO_FURTHER_CARE"
  | "PATIENT_DECLINED"
  | "UNREACHABLE"
  | "MOVED_OR_TRANSFERRED"
  | "OTHER";

export type ReferralStatus =
  | "SENT"
  | "ACCEPTED"
  | "DECLINED"
  | "NOT_ACCEPTED_IN_TIME";

export type DeclineCode =
  | "WRONG_SPECIALTY"
  | "NO_CAPACITY"
  | "INFORMATION_MISSING"
  | "NOT_ELIGIBLE"
  | "OTHER";

export type ConsultationType =
  | "CLINICIAN_TO_CLINICIAN"
  | "PATIENT_CALLBACK";

export type ConsultationState =
  | "REQUESTED"
  | "ACCEPTED"
  | "ESCALATED"
  | "OUTCOME_RECORDED";

export type ConsultationOutcomeType =
  | "ADVICE_GIVEN"
  | "TEST_ORDERED"
  | "REFERRAL_MADE"
  | "NO_ACTION";

export type RoutingStatus =
  | "AWAITING_ACCEPTANCE"
  | "ACCEPTED"
  | "EXCEPTION";

export type ContactRoute = "PHONE" | "SMS" | "EMAIL" | "VISIT" | "OTHER";
export type Attendance = "BOOKED" | "ATTENDED" | "MISSED";
export type UnderstandingLevel = "YES" | "PARTLY" | "NO";

export interface PersonRef {
  id: string;
  displayName: string;
  role?: string;
  specialty?: string | null;
}

export interface FacilityRef {
  id: string;
  name: string;
}

export interface FacilityRecord extends FacilityRef {
  code: string;
  type: string | null;
  connectorType: string | null;
  connectionStatus: string;
  timeZone: string | null;
  workingDays: string[] | null;
  lastEventAt: string | null;
}

export interface ScreeningRef {
  id?: string;
  type: string;
  outcome: string;
  displayLabel: string;
}

export interface RoutingSummary {
  status: string;
  stage: number;
  escalatedToCoordinator: boolean;
  requiredSpecialty: string | null;
  routedClinician: PersonRef | null;
  startedAt: string | null;
  dueAt: string | null;
  acceptedAt: string | null;
  exceptionReason: string | null;
  firstLimitMinutes: number | null;
  secondLimitMinutes: number | null;
}

export interface WorklistPatient {
  id: string;
  recordNumber?: string | null;
  displayLabel: string;
  ageYears: number | null;
  sex: string | null;
}

export interface ClosureSummary {
  id: string;
  status: string;
  closureType: string;
  reason: string;
  closedById: string | null;
  closedByName?: string | null;
  secondApproverId: string | null;
  secondApproverName?: string | null;
  secondSignOffById: string | null;
  requestedAt: string;
  closedAt: string | null;
}

export interface WorklistCase {
  id: string;
  caseId: string;
  trackerId: string;
  patient: WorklistPatient;
  patientInitials: string;
  screening: ScreeningRef | null;
  priority: Priority;
  status: CaseStatus;
  flags: CaseFlag[];
  closure: ClosureSummary | null;
  assignedCoordinator: PersonRef | null;
  owner: PersonRef | null;
  facility: FacilityRef;
  nextAction: { code: string | null; label: string | null } | null;
  dueAt: string | null;
  updatedAt: string;
  timeInStatusHours: number | null;
  timeLeftHours: number | null;
  delayReason: {
    code: string;
    note: string | null;
    recordedAt: string;
  } | null;
  delayReasonRequired: boolean;
  specialty: string | null;
  routingStatus: string | null;
  routing: RoutingSummary | null;
  patientLabel: string;
  age: number | null;
  sex: string | null;
  screeningType: string | null;
  assignedTo: string | null;
}

export interface WorklistSummary {
  totalCases: number;
  urgentCases: number;
  overdueCases: number;
  unassignedCases: number;
  exceptionCases?: number;
  messageFailedCases?: number;
  notExplainedCases?: number;
  dataMissingCases?: number;
}

export interface WorklistResponse {
  summary: WorklistSummary;
  tab: WorklistTab;
  cases: WorklistCase[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

export interface WorklistQuery {
  page?: number;
  pageSize?: number;
  search?: string;
  tab?: WorklistTab;
  priority?: Priority;
  status?: CaseStatus;
  includeClosed?: boolean;
  facilityId?: string;
  ownerId?: string;
  screeningType?: string;
  routingStatus?: RoutingStatus;
  sortBy?: "default" | "dueAt" | "updatedAt" | "createdAt" | "priority";
  sortOrder?: "asc" | "desc";
}

export interface CaseDetail extends WorklistCase {
  patient: WorklistPatient & { preferredLanguage: string | null };
  matchConfidence: number | null;
  confirmatoryRequired: boolean;
  requiredSpecialty: string | null;
  statusEnteredAt: string | null;
  createdAt: string;
  closedAt: string | null;
  closureType: string | null;
  linkedCaseId: string | null;
  referral: {
    id: string;
    status: string;
    receivingFacilityId: string | null;
    receivingClinicianId: string | null;
  } | null;
  counts: {
    appointments: number;
    results: number;
    consultations: number;
    treatmentStarts: number;
  };
  validClosureTypes: string[];
}

export interface CaseEvent {
  id: number;
  eventType: string;
  description: string;
  occurredAt: string;
  actorId: string | null;
  actorRole: string | null;
  transition: string | null;
  oldValues: Record<string, unknown> | null;
  newValues: Record<string, unknown> | null;
}

export interface SuggestedRouting {
  pathway: string;
  resultCategory: string;
  suggestedUrgency: string | null;
  confirmatoryRequired: boolean;
  specialty: string | null;
  timeToAcceptMinutes: number | null;
}

export interface ResultRecord {
  id: string;
  kind: "ORIGINAL" | "CONFIRMATORY";
  testCode: string;
  testName: string | null;
  value: string;
  abnormal: boolean;
  issuedAt: string | null;
  source: string;
  receivedAt: string;
}

export interface AppointmentRecord {
  id: string;
  caseId: string;
  facilityId: string;
  scheduledAt: string;
  attendance: Attendance;
  recordedById: string | null;
  recordedAt: string | null;
}

export interface TreatmentStartRecord {
  id: string;
  kind: "TREATMENT" | "MONITORING";
  startDate: string;
  note: string | null;
  attachmentRef: string | null;
  recordedById: string | null;
  recordedAt: string;
}

export interface ContactAttemptRecord {
  id: string;
  route: ContactRoute;
  outcome: "REACHED" | "NOT_REACHED";
  note: string | null;
  recordedById: string | null;
  recordedAt: string;
}

export interface ClosureChecklist {
  closureType: string;
  validClosureTypes: string[];
  items: { item: string; present: boolean; ref: Record<string, unknown> | null }[];
  dataMissing: boolean;
  canClose: boolean;
  complete: boolean;
  needsSecondSignOff: boolean;
}

export interface ReferralRecord {
  id: string;
  status: ReferralStatus;
  case: {
    id: string;
    caseId: string;
    trackerId: string;
    priority: Priority;
    status: CaseStatus;
    flags: CaseFlag[];
    patient: { id: string; displayLabel: string };
    screening: { type: string; outcome: string; displayLabel: string } | null;
  };
  referringFacility: FacilityRef;
  receivingFacility: FacilityRef | null;
  receivingClinician: PersonRef | null;
  referredById: string | null;
  referredBy: PersonRef | null;
  reason: string | null;
  rejectionReason: string | null;
  declineReason: string | null;
  declineCode: string | null;
  targetSpecialty: string | null;
  packet: Record<string, unknown> | null;
  acceptedById: string | null;
  escalated: boolean;
  escalationReason: string | null;
  escalatedAt: string | null;
  decidedAt: string | null;
  createdAt: string;
  updatedAt: string;
  consultation: {
    id: string;
    outcome: string | null;
    outcomeType: string | null;
    recordedById: string | null;
    recordedAt: string;
  } | null;
}

export interface ConsultationRecord {
  id: string;
  caseId: string;
  trackerId: string;
  type: ConsultationType;
  state: ConsultationState;
  source: string;
  requester: PersonRef | null;
  recipient: PersonRef | null;
  recipientSpecialty: string | null;
  copiedToCoordinator: boolean;
  question: string | null;
  preferredTime: string | null;
  thread: {
    byId: string;
    byName: string;
    role: string;
    text: string;
    at: string;
  }[];
  urgent: boolean;
  dueAt: string | null;
  escalationStage: number;
  acceptedBy: PersonRef | null;
  acceptedAt: string | null;
  outcome: {
    type: string;
    note: string;
    recordedBy: PersonRef | null;
    recordedAt: string;
  } | null;
  escalatedAt: string | null;
  referralId: string | null;
  createdAt: string;
  prompt?: string | null;
}

export interface MessageRecord {
  id: string;
  caseId: string;
  channel: "SMS" | "EMAIL";
  kind: string;
  language: string;
  templateVersion: string;
  body: string;
  status: string;
  source: string;
  suggestionId: string | null;
  createdById: string | null;
  approvedById: string | null;
  approvedAt: string | null;
  rejectionReason: string | null;
  attempts: number;
  nextRetryAt: string | null;
  lastError: string | null;
  sentAt: string | null;
  createdAt: string;
}

export interface AISuggestionRecord {
  id: string;
  kind: string;
  status: "PENDING" | "APPROVED" | "REJECTED";
  caseId: string | null;
  facilityId: string;
  payload: Record<string, unknown>;
  model: string | null;
  confidence: number | null;
  createdAt: string;
  decidedById: string | null;
  decidedAt: string | null;
  decisionNote: string | null;
  applied: Record<string, unknown> | null;
  requiresStaffApproval: boolean;
}

export interface PatientLinkRecord {
  id: string;
  status: string;
  createdAt: string;
  expiresAt: string;
  failedAttempts: number;
  lockedAt: string | null;
  verifiedAt: string | null;
  lastAccessedAt: string | null;
  createdById: string | null;
  deliveryChannel: string | null;
  deliveryStatus: string | null;
  deliveredTo: string | null;
  deliveredAt: string | null;
}

export interface GeneratedPatientLink {
  linkId: string;
  token: string;
  url: string;
  expiresAt: string;
  verificationRequired: boolean;
  resent: boolean;
  note: string;
  sms: {
    to: string;
    status: string;
    channel: string;
    simulated: boolean;
    sentAt: string;
    body: string;
  } | null;
}

export interface PatientResponseRecord {
  id: string;
  kind: string;
  value: Record<string, unknown> | null;
  source: "PATIENT_LINK" | "STAFF_ASSISTED";
  submissionId: string | null;
  note: string | null;
  recordedAt: string;
  recordedBy: PersonRef | null;
}

export interface PatientPortalContext {
  patient: { displayLabel: string };
  facility: { name: string };
  screening: { displayLabel: string } | null;
  nextAction: { label: string } | null;
  dueAt: string | null;
  expiresAt: string;
  status: CaseStatus;
  priority: Priority;
  urgencyText: string;
  contact: { name: string | null; facility: string; phone: string | null };
  language: "en" | "ar";
  reassuranceAvailable: boolean;
  progress: {
    steps: { key: string; label: string; done: boolean }[];
    currentStep: number;
  };
  responses: {
    acknowledged: boolean;
    understood: string | null;
    confidence: number | null;
    explanationStatus: string | null;
    callbackRequested: boolean;
  };
}

export interface TransitionRow {
  id: string;
  from: string[];
  to: string;
  who: string[];
  refusedUnless: string;
}
