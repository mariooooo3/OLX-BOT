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

export async function getProducts(accountId?: string): Promise<Product[]> {
  return request<Product[]>(`/api/products${accountScope(accountId)}`);
}

export async function getProduct(id: string): Promise<Product | null> {
  try {
    return await request<Product>(`/api/products/${encodeURIComponent(id)}`);
  } catch (e) {
    if (e instanceof Error && e.message.startsWith("API 404")) return null;
    throw e;
  }
}

/** Salveaza produsul. `accountId` alege contul tinta la creare; la editare,
 *  serverul pastreaza contul care detine deja produsul. */
export async function saveProduct(product: Product, accountId?: string): Promise<Product> {
  return request<Product>(`/api/products${accountScope(accountId)}`, {
    method: "POST",
    body: JSON.stringify(product),
  });
}

/** Copiaza un produs pe alte conturi. Copiile sunt independente. */
export async function copyProduct(
  productId: string,
  targetAccountIds: string[],
): Promise<{ count: number }> {
  return request<{ count: number }>(`/api/products/${encodeURIComponent(productId)}/copy`, {
    method: "POST",
    body: JSON.stringify({ target_account_ids: targetAccountIds }),
  });
}

export async function deleteProduct(id: string, accountId?: string): Promise<void> {
  await request(`/api/products/${encodeURIComponent(id)}${accountScope(accountId)}`, {
    method: "DELETE",
  });
}

/**
 * Firele de conversatie. Implicit aduna toate conturile (botul raspunde pe
 * toate deodata); `accountId` filtreaza pe unul singur.
 */
export async function getConversations(accountId?: string): Promise<ConversationThread[]> {
  return request<ConversationThread[]>(`/api/conversations${accountScope(accountId)}`);
}

/** "?account_id=<id>" pentru filtrare, sau "" pentru toate conturile. */
function accountScope(accountId?: string): string {
  return accountId && accountId !== "all" ? `?account_id=${encodeURIComponent(accountId)}` : "";
}

export async function getBotStatus(accountId?: string): Promise<BotStatus> {
  return request<BotStatus>(`/api/bot/status${accountScope(accountId)}`);
}

/** Porneste botul pe toate conturile conectate. */
export async function startBot(): Promise<BotStatus> {
  return request<BotStatus>("/api/bot/start", { method: "POST" });
}

/** Opreste botul pe toate conturile. */
export async function stopBot(): Promise<BotStatus> {
  return request<BotStatus>("/api/bot/stop", { method: "POST" });
}

export async function restartBot(): Promise<BotStatus> {
  return request<BotStatus>("/api/bot/restart", { method: "POST" });
}

/** Porneste botul pe un singur cont (comutatorul individual). */
export async function startBotAccount(accountId: string): Promise<BotStatus> {
  return request<BotStatus>(`/api/bot/accounts/${encodeURIComponent(accountId)}/start`, {
    method: "POST",
  });
}

/** Opreste botul pe un singur cont. */
export async function stopBotAccount(accountId: string): Promise<BotStatus> {
  return request<BotStatus>(`/api/bot/accounts/${encodeURIComponent(accountId)}/stop`, {
    method: "POST",
  });
}

export async function restartBotAccount(accountId: string): Promise<BotStatus> {
  return request<BotStatus>(`/api/bot/accounts/${encodeURIComponent(accountId)}/restart`, {
    method: "POST",
  });
}

export async function getBotErrors(): Promise<BotError[]> {
  return request<BotError[]>("/api/bot/errors");
}

export async function clearBotErrors(): Promise<{ cleared: number }> {
  return request<{ cleared: number }>("/api/bot/errors", { method: "DELETE" });
}

export async function getSettings(accountId?: string): Promise<Settings> {
  return request<Settings>(`/api/settings${accountScope(accountId)}`);
}

/**
 * Scrie setarile. Trimite DOAR campurile schimbate: in modul "toate conturile"
 * cele netrimise raman diferite de la un cont la altul (fiecare cont isi
 * pastreaza, de exemplu, modelul LLM propriu).
 *
 * `accountId` lipsa = contul selectat; "all" = toate conturile.
 */
export async function saveSettings(
  changes: Partial<Settings>,
  accountId?: string,
): Promise<Settings> {
  const query = accountId ? `?account_id=${encodeURIComponent(accountId)}` : "";
  return request<Settings>(`/api/settings${query}`, {
    method: "PUT",
    body: JSON.stringify(changes),
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

export async function getMessagesPerDay(
  accountId?: string,
): Promise<{ date: string; count: number }[]> {
  return request<{ date: string; count: number }[]>(
    `/api/stats/messages-per-day${accountScope(accountId)}`,
  );
}

export interface OlxAccount {
  id: string;
  label: string;
  /** numele afisat peste tot in UI (numele OLX, altfel eticheta locala) */
  display_name: string;
  /** indexul de culoare din paleta, stabil per cont (vezi lib/accounts.ts) */
  color: number;
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

/** Deschide fereastra de login pentru UN cont anume (reconectare). */
export async function startOlxLoginForAccount(
  accountId: string,
): Promise<{ started: boolean; account_id: string }> {
  return request<{ started: boolean; account_id: string }>(
    `/api/olx/accounts/${encodeURIComponent(accountId)}/login`,
    { method: "POST" },
  );
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
