import { useEffect, useState } from "react";
import { listStaff, listClosureAuthorisedStaff, type StaffMember } from "../../services/api/adminApi";
import type { PersonRef } from "../../services/api/v6.types";

export function useStaff(params: { role?: string; facilityId?: string } = {}) {
  const [staff, setStaff] = useState<StaffMember[]>([]);
  const [loading, setLoading] = useState(true);
  const { role, facilityId } = params;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listStaff({ role, facilityId })
      .then((rows) => {
        if (!cancelled) setStaff(rows.filter((person) => person.isActive));
      })
      .catch(() => {
        if (!cancelled) setStaff([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [role, facilityId]);

  return { staff, loading };
}

export function useClosureApprovers() {
  const [staff, setStaff] = useState<PersonRef[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listClosureAuthorisedStaff()
      .then((rows) => {
        if (!cancelled) setStaff(rows);
      })
      .catch((err) => {
        if (!cancelled) {
          setStaff([]);
          setError(err instanceof Error ? err.message : "Unable to load approvers.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { staff, error };
}

export function normalizeSpecialty(value: string | null | undefined): string {
  return (value ?? "").trim().toUpperCase().replaceAll(" ", "_");
}
