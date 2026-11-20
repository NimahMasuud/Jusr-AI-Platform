const TOKEN_KEY = "jusr-access-token";

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || ""
).replace(/\/$/, "");

export interface ApiResponse<T> {
  success: boolean;
  data: T;
  meta?: Record<string, unknown>;
  error?: {
    code: string;
    message: string;
    details?: unknown;
  };
}

interface ApiRequestOptions extends RequestInit {
  authenticated?: boolean;
}

export class ApiRequestError extends Error {
  status: number;
  code: string | null;
  details: unknown;

  constructor(
    message: string,
    status: number,
    code: string | null = null,
    details: unknown = null
  ) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function saveAccessToken(token: string) {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function getAccessToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function clearAccessToken() {
  sessionStorage.removeItem(TOKEN_KEY);
}

export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {}
): Promise<T> {
  const response = await apiEnvelope<T>(path, options);
  return response.data;
}

export interface ApiEnvelopeResult<T> {
  success: boolean;
  data: T;
  meta: Record<string, unknown>;
}

export async function apiEnvelope<T>(
  path: string,
  options: ApiRequestOptions = {}
): Promise<ApiEnvelopeResult<T>> {
  const { authenticated = true, headers, ...requestOptions } = options;

  const requestHeaders = new Headers(headers);

  if (!(requestOptions.body instanceof URLSearchParams)) {
    if (requestOptions.body && !requestHeaders.has("Content-Type")) {
      requestHeaders.set("Content-Type", "application/json");
    }
  }

  if (authenticated) {
    const token = getAccessToken();

    if (!token) {
      throw new Error("You are not authenticated. Please log in.");
    }

    requestHeaders.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...requestOptions,
    headers: requestHeaders,
  });

  let result: any;
  try {
    result = await response.json();
  } catch {
    throw new ApiRequestError(
      `The server returned an unreadable response (${response.status}).`,
      response.status
    );
  }

  if (!response.ok || result.success === false) {
    const detail = result.detail;
    const detailMessage =
      typeof detail === "string"
        ? detail
        : detail && typeof detail === "object"
          ? detail.message
          : undefined;

    throw new ApiRequestError(
      result.error?.message ||
        detailMessage ||
        `Request failed: ${response.status}`,
      response.status,
      result.error?.code || (typeof detail === "object" ? detail.code : null),
      result.error?.details || detail || null
    );
  }

  const apiResult = result as ApiResponse<T>;
  return {
    success: true,
    data: apiResult.data,
    meta: apiResult.meta ?? {},
  };
}
