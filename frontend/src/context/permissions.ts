
import type { UserRole } from "./UserContext";

// Application sections
export type AppPermission =
  | "dashboard"
  | "worklist"
  | "urgent_inbox"
  | "patients"
  | "referrals"
  | "consultations"
  | "ai_review"
  | "measures"
  | "facilities"
  | "settings";

const ALL: AppPermission[] = [
  "dashboard",
  "worklist",
  "urgent_inbox",
  "patients",
  "referrals",
  "consultations",
  "ai_review",
  "measures",
  "facilities",
  "settings",
];

// Navigation and page access by staff role (Developer Guide section 2).
export const rolePermissions: Record<UserRole, AppPermission[]> = {
  coordinator: [
    "dashboard",
    "worklist",
    "patients",
    "referrals",
    "consultations",
    "ai_review",
    "measures",
  ],

  referring_clinician: [
    "dashboard",
    "worklist",
    "referrals",
    "consultations",
    "ai_review",
    "measures",
  ],

  receiving_clinician: [
    "dashboard",
    "urgent_inbox",
    "worklist",
    "referrals",
    "consultations",
    "ai_review",
    "measures",
  ],

  facility_administrator: [
    "dashboard",
    "measures",
    "facilities",
    "settings",
  ],

  national_admin: ALL,
};

// Check whether a role has access to an application section
export function hasPermission(
  role: UserRole,
  permission: AppPermission
): boolean {
  return rolePermissions[role].includes(permission);
}

export const roleLabels: Record<UserRole, string> = {
  coordinator: "Coordinator",
  referring_clinician: "Referring clinician",
  receiving_clinician: "Receiving clinician",
  facility_administrator: "Facility administrator",
  national_admin: "National administrator",
};
