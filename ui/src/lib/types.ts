/**
 * Un produs din catalog.
 *
 * Structurat doar ce e faptic si des intrebat (pret, stoc, negociabil, TVA,
 * garantie) — pentru astea botul raspunde determinist, fara LLM. Restul e un
 * singur text liber, scris ca un anunt.
 */
export interface Product {
  id: string;
  /** contul OLX al carui catalog contine produsul (adnotare de la server) */
  account_id?: string;
  account_label?: string;
  title: string;
  price: number;
  currency: string;
  stock: number;
  condition: "nou" | "folosit";
  /** cea mai frecventa intrebare de pe OLX — ca bifa, raspunsul e exact */
  negotiable: boolean;
  /** ex. "12 luni", "fara" — gol inseamna "nespecificat" */
  warranty: string;
  vat: {
    /** pretul afisat include deja TVA? */
    included: boolean;
    /** se emite factura cu TVA deductibil? */
    deductible: boolean;
    /** cota, editabila (implicit cea curenta) */
    rate: number;
  };
  /** descrierea libera: tot ce nu e faptic (specificatii, culoare, stare) */
  about: string;
  faq: { question: string; answer: string }[];
}

export type FinanceTransactionKind = "purchase" | "sale" | "expense";

export interface FinanceTransaction {
  id: string;
  product_id: string;
  product_title: string;
  account_id?: string;
  account_label?: string;
  kind: FinanceTransactionKind;
  quantity: number;
  unit_price: number;
  currency: string;
  gross_total: number;
  net_total: number;
  vat_rate: number;
  vat_included: boolean;
  vat_deductible: boolean;
  vat_amount: number;
  occurred_at: string;
  note: string;
  created_at: string;
}

export interface FinanceTransactionInput {
  product_id: string;
  kind: FinanceTransactionKind;
  quantity: number;
  unit_price: number;
  vat_rate: number;
  vat_included: boolean;
  vat_deductible: boolean;
  occurred_at: string;
  note: string;
}

export interface ProductFinance {
  product_id: string;
  title: string;
  currency: string;
  sale_price: number;
  vat_rate: number;
  sale_vat_included: boolean;
  account_id?: string;
  account_label?: string;
  purchase_quantity: number;
  sold_quantity: number;
  stock_quantity: number;
  sell_through_rate: number;
  average_purchase_price: number;
  average_sale_price: number;
  purchase_cost: number;
  sales_revenue: number;
  additional_costs: number;
  invested: number;
  cash_balance: number;
  realized_profit: number;
  margin_rate: number;
  roi: number;
  inventory_value: number;
  projected_revenue: number;
  projected_profit: number;
  recoverable_vat: number;
  sales_vat: number;
  vat_balance: number;
  average_days_to_sale: number | null;
  transaction_count: number;
}

export interface FinanceCurrencySummary {
  currency: string;
  purchase_cost: number;
  sales_revenue: number;
  additional_costs: number;
  invested: number;
  cash_balance: number;
  realized_profit: number;
  inventory_value: number;
  projected_revenue: number;
  projected_profit: number;
  recoverable_vat: number;
  sales_vat: number;
  vat_balance: number;
  purchase_quantity: number;
  sold_quantity: number;
  stock_quantity: number;
  sell_through_rate: number;
  product_count: number;
  active_product_count: number;
}

export interface FinanceSummary {
  currency: string | null;
  mixed_currencies: boolean;
  purchase_cost: number | null;
  sales_revenue: number | null;
  additional_costs: number | null;
  invested: number | null;
  cash_balance: number | null;
  realized_profit: number | null;
  inventory_value: number | null;
  projected_revenue: number | null;
  projected_profit: number | null;
  recoverable_vat: number | null;
  sales_vat: number | null;
  vat_balance: number | null;
  purchase_quantity: number;
  sold_quantity: number;
  stock_quantity: number;
  sell_through_rate: number;
  product_count: number;
  active_product_count: number;
}

export interface FinanceReport {
  summary: FinanceSummary;
  currency_summaries: FinanceCurrencySummary[];
  products: ProductFinance[];
  transactions: FinanceTransaction[];
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

/** Locatie, livrare si plata — aceleasi pentru toate anunturile contului. */
export interface SellerInfo {
  city: string;
  pickup_available: boolean;
  delivery_available: boolean;
  courier: string;
  delivery_paid_by: "buyer" | "seller";
  payment_methods: string;
}

export interface Settings {
  poll_interval_seconds: number;
  /** completate o data per cont; botul le foloseste si cand niciun produs
   *  nu se potriveste cu anuntul */
  seller_info: SellerInfo;
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
