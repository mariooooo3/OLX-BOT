export interface Product {
  id: string;
  /** contul OLX al carui catalog contine produsul (adnotare de la server) */
  account_id?: string;
  account_label?: string;
  title: string;
  category: string;
  subcategory: string;
  price: number;
  currency: string;
  stock: number;
  condition: "nou" | "folosit";
  description: string;
  attributes: Record<string, string>;
  faq: { question: string; answer: string }[];
  shipping: {
    available: boolean;
    courier: string | null;
    cost_paid_by: "buyer" | "seller" | null;
    estimated_days: number | null;
  };
  keywords: string[];
}

export interface ConversationMessage {
  id: string;
  timestamp: string;
  buyer_message: string;
  bot_response: string;
  status: "sent" | "failed" | "pending";
}

/** Un fir de conversatie OLX: toate schimburile cu acelasi cumparator
 *  despre acelasi anunt, in ordine cronologica. */
export interface ConversationThread {
  olx_conversation_id: string;
  /** contul OLX pe care a venit conversatia */
  account_id: string;
  account_label: string;
  /** numele interlocutorului (null pentru intrarile vechi, dinainte sa-l salvam) */
  buyer_name: string | null;
  /** titlul anuntului OLX la care se refera conversatia */
  ad_title: string | null;
  product_id: string | null;
  last_timestamp: string;
  messages: ConversationMessage[];
}

/** Starea botului pe un singur cont OLX. Fiecare cont ruleaza independent,
 *  cu browserul si setarile lui. */
export interface BotAccountStatus {
  account_id: string;
  account_label: string;
  connected: boolean;
  running: boolean;
  stopping: boolean;
  last_poll: string | null;
  active_llm: string | null;
  errors_today: number;
  last_error: string | null;
}

export interface BotStatus {
  /** true daca botul ruleaza pe cel putin un cont */
  running: boolean;
  accounts_running: number;
  accounts_connected: number;
  /** oprire ceruta, botul termina ciclul curent si inchide browserul */
  stopping: boolean;
  last_poll: string | null;
  /** modelul cu care ruleaza botul acum ("groq:llama-3.1-8b-instant");
   *  null cand botul e oprit */
  active_llm: string | null;
  poll_interval_seconds: number;
  messages_today: number;
  errors_today: number;
  last_error: string | null;
  /** starea fiecarui cont, pentru comutatoarele individuale */
  accounts: BotAccountStatus[];
}

export interface BotError {
  id: string;
  timestamp: string;
  message: string;
  /** contul pe care a aparut eroarea */
  account_id: string;
  account_label: string;
}

export interface Settings {
  poll_interval_seconds: number;
  /** backend-ul LLM activ: modele locale (ollama) sau online (groq) */
  llm_backend: "groq" | "ollama";
  groq_model: string;
  ollama_model: string;
  log_level: "INFO" | "DEBUG";
  /** campurile care difera intre conturile din scope-ul curent — in modul
   *  "toate conturile" se afiseaza ca "valori diferite" in loc sa arate
   *  tacit valoarea unui singur cont */
  mixed?: (keyof Omit<Settings, "mixed">)[];
}

export interface LlmModelsResponse {
  ollama: {
    available: boolean;
    models: { name: string; size_gb: number }[];
    host: string;
  };
  groq: {
    available: boolean;
    models: { name: string; note?: string }[];
  };
}

export interface PullJob {
  status: string;
  percent: number;
  done: boolean;
  error: string | null;
}
