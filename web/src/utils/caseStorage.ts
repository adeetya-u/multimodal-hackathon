import { apiFetch } from "../lib/apiBase";

export const ACTIVE_CASE_KEY = "activeCaseId";

export function readActiveCaseId(): string | null {
  return localStorage.getItem(ACTIVE_CASE_KEY);
}

export function setActiveCaseId(id: string): void {
  localStorage.setItem(ACTIVE_CASE_KEY, id);
}

export function clearActiveCaseId(): void {
  localStorage.removeItem(ACTIVE_CASE_KEY);
}

/** Returns a valid case id, or null if the stored/url id no longer exists. */
export async function resolveCaseId(urlCaseId: string | null): Promise<string | null> {
  const candidate = urlCaseId || readActiveCaseId();
  if (!candidate) return null;

  const res = await apiFetch(`/api/cases/${candidate}`);
  if (res.status === 404) {
    clearActiveCaseId();
    return null;
  }
  return candidate;
}

export function isCaseNotFound(res: Response): boolean {
  return res.status === 404;
}
