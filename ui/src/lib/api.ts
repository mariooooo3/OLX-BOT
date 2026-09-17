import type {
  Product,
  ConversationThread,
  BotStatus,
  BotError,
  Settings,
  LlmModelsResponse,
  PullJob,
  FinanceReport,
  FinanceTransaction,
  FinanceTransactionInput,
  Proxy,
  ProxyFullTestResult,
  ProxyTestResult,
  ListingSearchResponse,
  ActiveListingsResponse,
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

export async function getFinance(accountId?: string): Promise<FinanceReport> {
  return request<FinanceReport>(`/api/finance${accountScope(accountId)}`);
}

export async function saveFinanceTransaction(
  transaction: FinanceTransactionInput,
  accountId?: string,
): Promise<FinanceTransaction> {
  return request<FinanceTransaction>(`/api/finance/transactions${accountScope(accountId)}`, {
    method: "POST",
    body: JSON.stringify(transaction),
  });
}

export async function deleteFinanceTransaction(id: string, accountId?: string): Promise<void> {
  await request(`/api/finance/transactions/${encodeURIComponent(id)}${accountScope(accountId)}`, {
    method: "DELETE",
  });
}

/**
 * Cauta pe OLX.ro anunturi al caror titlu contine `query`, excluzand cele
 * ale conturilor tale conectate (vezi server.py:search_listings). Public,
 * fara nicio sesiune — poate dura cateva zeci de secunde (deschide pagina
 * de detaliu a fiecarui candidat ca sa afle vanzatorul), de-asta `limit`
 * plafoneaza cate verificam.
 */
export async function searchListings(
  query: string,
  limit = 20,
): Promise<ListingSearchResponse> {
  return request<ListingSearchResponse>(
    `/api/listing-search?q=${encodeURIComponent(query)}&limit=${limit}`,
  );
}

/**
 * Extrage anunturile ACTIVE ale unui cont, direct de pe profilul lui public
 * OLX (vezi server.py:get_active_listings) — nu creeaza produse, doar le
 * intoarce ca sa alegi ce imporți (creare efectiva prin saveProduct()).
 * Contul trebuie sa fie conectat; poate dura cateva zeci de secunde.
 */
export async function getActiveListings(accountId: string): Promise<ActiveListingsResponse> {
  return request<ActiveListingsResponse>(
    `/api/olx/accounts/${encodeURIComponent(accountId)}/active-listings`,
  );
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
  /** are proxy de iesire configurat (conturi diferite, IP-uri diferite) */
  has_proxy: boolean;
  /** proxy-ul asignat, din registrul central — vezi getProxies() */
  proxy_id: string | null;
  /** adresa proxy-ului, fara credentiale — doar de afisat */
  proxy_server: string | null;
  proxy_username: string | null;
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

export interface AssignProxyResult {
  ok: boolean;
  has_proxy: boolean;
  restarted: "thread" | null;
  /** proxy-ul era deja alocat altui cont — a fost mutat aici, iar contul
   *  vechi a ramas fara proxy (repornit automat daca rula) */
  moved_from: { account_id: string; account_label: string } | null;
}

/**
 * Asigneaza (sau, cu `proxyId` null, dezasigneaza) un proxy din registrul
 * central (vezi getProxies()) contului dat. Daca botul acestui cont ruleaza
 * deja, serverul il repornește automat.
 */
export async function setAccountProxy(
  accountId: string,
  proxyId: string | null,
): Promise<AssignProxyResult> {
  return request<AssignProxyResult>(`/api/olx/accounts/${encodeURIComponent(accountId)}/proxy`, {
    method: "PUT",
    body: JSON.stringify({ proxy_id: proxyId }),
  });
}

// --------------------------------------------------------------------- //
// registru de proxy-uri — un singur loc de adevar, ca acelasi proxy sa nu
// ajunga din greseala pe doua conturi (vezi core/proxies.py)
// --------------------------------------------------------------------- //

export interface ProxyInput {
  label?: string;
  server: string;
  /** goale la editare = neschimbate (parola nu se intoarce niciodata catre UI) */
  username?: string;
  password?: string;
  /** salveaza chiar daca testul de conectivitate esueaza */
  skip_validation?: boolean;
}

export async function getProxies(): Promise<Proxy[]> {
  return request<Proxy[]>("/api/proxies");
}

export async function createProxy(
  input: ProxyInput,
): Promise<{ proxy: Proxy; test: ProxyTestResult | null }> {
  return request(`/api/proxies`, { method: "POST", body: JSON.stringify(input) });
}

export async function updateProxy(
  proxyId: string,
  input: Partial<ProxyInput>,
): Promise<{ proxy: Proxy; test: ProxyTestResult | null }> {
  return request(`/api/proxies/${encodeURIComponent(proxyId)}`, {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

/** Reruleaza testul de conectivitate al unui proxy deja salvat. */
export async function testProxy(proxyId: string): Promise<ProxyTestResult> {
  return request(`/api/proxies/${encodeURIComponent(proxyId)}/test`, { method: "POST" });
}

/**
 * Verificare completa, cu Chromium real — mai lenta (~5-15s) decat
 * testProxy(), dar prinde discrepante intre `requests` si browserul real
 * (vezi core/proxies.py:test_proxy_full()).
 */
export async function testProxyFull(proxyId: string): Promise<ProxyFullTestResult> {
  return request(`/api/proxies/${encodeURIComponent(proxyId)}/test-full`, { method: "POST" });
}

/** `force`: sterge chiar daca proxy-ul e alocat unui cont (il dezasigneaza intai). */
export async function deleteProxy(proxyId: string, force = false): Promise<void> {
  await request(`/api/proxies/${encodeURIComponent(proxyId)}${force ? "?force=true" : ""}`, {
    method: "DELETE",
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
