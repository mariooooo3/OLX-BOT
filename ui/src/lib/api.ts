import type {
  Product,
  ConversationThread,
  BotStatus,
  BotError,
  Settings,
  LlmModelsResponse,
  PullJob,
} from "./types";

// Backend-ul FastAPI al botului (server.py). Configurabil prin VITE_API_URL.
const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    // FastAPI intoarce erorile ca {"detail": "..."} — afisam mesajul curat
    let detail = body;
    try {
      detail = JSON.parse(body).detail ?? body;
    } catch {
      /* corpul nu e JSON — il folosim ca atare */
    }
    throw new Error(`API ${res.status}: ${detail || res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export async function getHealth(): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/api/health");
}

export async function getProducts(): Promise<Product[]> {
  return request<Product[]>("/api/products");
}

export async function getProduct(id: string): Promise<Product | null> {
  try {
    return await request<Product>(`/api/products/${encodeURIComponent(id)}`);
  } catch (e) {
    if (e instanceof Error && e.message.startsWith("API 404")) return null;
    throw e;
  }
}

export async function saveProduct(product: Product): Promise<Product> {
  return request<Product>("/api/products", {
    method: "POST",
    body: JSON.stringify(product),
  });
}

export async function deleteProduct(id: string): Promise<void> {
  await request(`/api/products/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function getConversations(): Promise<ConversationThread[]> {
  return request<ConversationThread[]>("/api/conversations");
}

export async function getBotStatus(): Promise<BotStatus> {
  return request<BotStatus>("/api/bot/status");
}

export async function startBot(): Promise<BotStatus> {
  return request<BotStatus>("/api/bot/start", { method: "POST" });
}

export async function stopBot(): Promise<BotStatus> {
  return request<BotStatus>("/api/bot/stop", { method: "POST" });
}

export async function getBotErrors(): Promise<BotError[]> {
  return request<BotError[]>("/api/bot/errors");
}

export async function clearBotErrors(): Promise<{ cleared: number }> {
  return request<{ cleared: number }>("/api/bot/errors", { method: "DELETE" });
}

export async function getSettings(): Promise<Settings> {
  return request<Settings>("/api/settings");
}

export async function saveSettings(next: Settings): Promise<Settings> {
  return request<Settings>("/api/settings", {
    method: "PUT",
    body: JSON.stringify(next),
  });
}

export async function getLlmModels(refresh = false): Promise<LlmModelsResponse> {
  return request<LlmModelsResponse>(`/api/llm/models${refresh ? "?refresh=true" : ""}`);
}

export async function pullOllamaModel(
  model: string,
): Promise<{ started: boolean; already_running?: boolean }> {
  return request<{ started: boolean; already_running?: boolean }>("/api/ollama/pull", {
    method: "POST",
    body: JSON.stringify({ model }),
  });
}

export async function getOllamaPullStatus(): Promise<Record<string, PullJob>> {
  return request<Record<string, PullJob>>("/api/ollama/pull/status");
}

export async function getMessagesPerDay(): Promise<{ date: string; count: number }[]> {
  return request<{ date: string; count: number }[]>("/api/stats/messages-per-day");
}

export interface OlxAccount {
  id: string;
  label: string;
  /** emailul contului OLX, detectat la login; null pana la primul login reusit */
  username: string | null;
  /** numele afisat pe OLX (ex. "Mario"); null pana la primul login reusit */
  name: string | null;
  connected: boolean;
  active: boolean;
}

export interface OlxSession {
  connected: boolean;
  login_running: boolean;
  last_result: "success" | "failed" | null;
  account: OlxAccount | null;
  accounts: OlxAccount[];
}

export async function getOlxSession(): Promise<OlxSession> {
  return request<OlxSession>("/api/olx/session");
}

export async function startOlxLogin(): Promise<{ started: boolean }> {
  return request<{ started: boolean }>("/api/olx/login", { method: "POST" });
}

export async function addOlxAccount(label?: string): Promise<{ id: string; label: string }> {
  return request<{ id: string; label: string }>("/api/olx/accounts", {
    method: "POST",
    body: JSON.stringify({ label: label ?? "" }),
  });
}

export async function activateOlxAccount(
  id: string,
): Promise<{ active: string; bot_stopped: boolean }> {
  return request<{ active: string; bot_stopped: boolean }>(
    `/api/olx/accounts/${encodeURIComponent(id)}/activate`,
    { method: "POST" },
  );
}

/**
 * Deconectare cont. Implicit (purge=false) sterge doar sesiunea de browser —
 * produsele, conversatiile si setarile contului raman salvate si le regasesti
 * la re-login. Cu purge=true sterge definitiv contul cu toate datele lui.
 */
export async function signOutOlxAccount(
  id: string,
  purge = false,
): Promise<{ ok: boolean; active: string | null; purged: boolean }> {
  return request<{ ok: boolean; active: string | null; purged: boolean }>(
    `/api/olx/accounts/${encodeURIComponent(id)}${purge ? "?purge=true" : ""}`,
    { method: "DELETE" },
  );
}
