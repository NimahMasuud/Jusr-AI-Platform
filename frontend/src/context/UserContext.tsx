
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import {
  getCurrentUser,
  logout as authLogout,
  type AuthUser,
} from "../services/api/authService";
import { listFacilities } from "../services/api/adminApi";

export type UserRole =
  | "coordinator"
  | "referring_clinician"
  | "receiving_clinician"
  | "facility_administrator"
  | "national_admin";

export interface Facility {
  id: string;
  name: string;
}

export interface DemoUser {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  facility: Facility;
  specialty: string | null;
  authorisedToClose: boolean;
}

interface UserContextType {
  activeUser: DemoUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  loginUser: (user: AuthUser) => void;
  logoutUser: () => void;
}

const UserContext = createContext<UserContextType | undefined>(
  undefined
);

function mapRole(role: string): UserRole {
  const roles: Record<string, UserRole> = {
    COORDINATOR: "coordinator",
    REFERRING_CLINICIAN: "referring_clinician",
    RECEIVING_CLINICIAN: "receiving_clinician",
    FACILITY_ADMIN: "facility_administrator",
    NATIONAL_ADMIN: "national_admin",
  };

  const mappedRole = roles[role];

  if (!mappedRole) {
    throw new Error("This account does not have a supported staff role.");
  }

  return mappedRole;
}

function mapUser(user: AuthUser): DemoUser {
  return {
    id: user.id,
    name: user.displayName,
    email: user.email,
    role: mapRole(user.role),
    facility: {
      id: user.facilityId ?? "",
      name: "Your facility",
    },
    specialty: user.specialty ?? null,
    authorisedToClose: user.authorisedToClose,
  };
}

async function withFacilityName(user: DemoUser): Promise<DemoUser> {
  if (!user.facility.id) return user;

  try {
    const facilities = await listFacilities();
    const match = facilities.find((f) => f.id === user.facility.id);
    if (!match) return user;
    return { ...user, facility: { id: match.id, name: match.name } };
  } catch {
    return user;
  }
}

export function UserProvider({ children }: { children: ReactNode }) {
  const [activeUser, setActiveUser] = useState<DemoUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const adoptUser = useCallback(async (user: AuthUser) => {
    const mapped = mapUser(user);
    setActiveUser(mapped);
    const enriched = await withFacilityName(mapped);
    setActiveUser((current) =>
      current && current.id === enriched.id ? enriched : current
    );
  }, []);

  useEffect(() => {
    let mounted = true;

    async function restoreSession() {
      try {
        const user = await getCurrentUser();

        if (mounted) {
          await adoptUser(user);
        }
      } catch {
        authLogout();

        if (mounted) {
          setActiveUser(null);
        }
      } finally {
        if (mounted) {
          setIsLoading(false);
        }
      }
    }

    restoreSession();

    return () => {
      mounted = false;
    };
  }, [adoptUser]);

  function loginUser(user: AuthUser) {
    void adoptUser(user);
  }

  function logoutUser() {
    authLogout();
    setActiveUser(null);
  }

  return (
    <UserContext.Provider
      value={{
        activeUser,
        isLoading,
        isAuthenticated: !!activeUser,
        loginUser,
        logoutUser,
      }}
    >
      {children}
    </UserContext.Provider>
  );
}

export function useUser() {
  const context = useContext(UserContext);

  if (!context) {
    throw new Error("useUser must be used within a UserProvider");
  }

  return context;
}
