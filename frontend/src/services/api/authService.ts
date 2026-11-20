
import {
  apiRequest,
  saveAccessToken,
  clearAccessToken,
} from "./apiClient";

export interface AuthUser {
  id: string;
  email: string;
  displayName: string;
  role: string;
  facilityId: string | null;
  specialty?: string | null;
  authorisedToClose: boolean;
}

interface LoginResponse {
  accessToken: string;
  tokenType: string;
}

export async function login(
  email: string,
  password: string
): Promise<AuthUser> {
  const formData = new URLSearchParams();
  formData.set("username", email);
  formData.set("password", password);

  const result = await apiRequest<LoginResponse>(
    "/api/auth/login",
    {
      method: "POST",
      body: formData,
      authenticated: false,
    }
  );

  saveAccessToken(result.accessToken);

  try {
    return await getCurrentUser();
  } catch (error) {
    clearAccessToken();
    throw error;
  }
}

export async function getCurrentUser(): Promise<AuthUser> {
  return apiRequest<AuthUser>("/api/auth/me");
}

export function logout() {
  clearAccessToken();
}
