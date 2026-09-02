import axios from "axios";
import type { AxiosInstance } from "axios";
import { useContext, useMemo } from "react";
import AuthContext from "./contexts/AuthContext";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export type InvestigationResult = {
  investigation_id: string;
  case_id: string;
  model_provider: string;
  model_name: string;
  model_available: boolean;
  risk_assessment: string;
  confidence: number;
  recommendation: string;
  reasoning_summary: string;
  findings: Array<{ finding_id: string; description: string; evidence_ids: string[]; confidence: number; source: string } | string>;
  evidence_references: string[];
  missing_evidence: string[];
  tool_calls?: unknown;
  tool_calls_count?: number;
  duration_ms?: number;
  status: string;
  failure_reason?: string;
  failure_details?: unknown;
  started_at: string;
  completed_at?: string;
};

export type CaseItem = {
  id: string;
  transaction_id: string;
  status: string;
  assignee: string | null;
  created_at: string;
  updated_at: string;
};

export type CaseDetail = {
  id: string;
  transaction_id: string;
  status: string;
  assignee: string | null;
  created_at: string;
  updated_at: string;
  transaction?: {
    id: string;
    provider_event_id: string;
    amount: string;
    currency: string;
    status: string;
    customer_id?: string;
    device_id?: string;
    merchant_id?: string;
    raw_payload?: Record<string, unknown>;
    created_at?: string;
  } | null;
  evidence_count: number;
  evidence?: Array<{ id: string; source_type: string; source_id: string; payload: unknown }>;
};

export type CaseListResponse = {
  items: CaseItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export type TransactionListItem = {
  id: string;
  provider_event_id: string;
  amount: string;
  currency: string;
  status: string;
  customer_id: string;
  device_id: string | null;
  merchant_id: string;
  raw_payload: Record<string, unknown>;
  created_at: string;
  risk_score: number;
  risk_level: string;
  decision: string;
  triggered_rules: Array<{ rule_id: string; rule_name: string; action: string; priority: number; dsl_expression: string }>;
  has_case: boolean;
  case_id: string | null;
  case_status: string | null;
  customer_external_id: string | null;
  merchant_name: string | null;
  merchant_category_code: string | null;
};

export type TransactionListResponse = {
  items: TransactionListItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export type TransactionListParams = {
  page?: number;
  page_size?: number;
  sort_by?: "created_at" | "amount" | "risk_score" | "provider_event_id" | "status";
  sort_order?: "asc" | "desc";
  risk?: "low" | "medium" | "high" | "critical";
  min_amount?: number;
  max_amount?: number;
  customer_id?: string;
  merchant_id?: string;
  device_id?: string;
  status?: string;
  provider_event_id?: string;
  search?: string;
  from_date?: string;
  to_date?: string;
};

export type CustomerListItem = {
  customer_id: string;
  external_id: string;
  risk_tier: string;
  kyc_status: string;
  created_at: string;
  total_transactions: number;
  total_amount: string;
  average_risk_score: number;
  risk_level: string;
  unique_merchants: number;
  unique_devices: number;
  total_cases: number;
};
export type CustomerListResponse = { items: CustomerListItem[]; total: number; page: number; page_size: number; total_pages: number };
export type CustomerProfile = {
  customer_id: string;
  external_id: string;
  risk_tier: string;
  kyc_status: string;
  created_at: string;
  total_transactions: number;
  total_amount: string;
  average_amount: string;
  min_amount: string | null;
  max_amount: string | null;
  first_transaction_at: string | null;
  last_transaction_at: string | null;
  average_risk_score: number;
  max_risk_score: number;
  risk_level: string;
  blocked_count: number;
  review_count: number;
  allowed_count: number;
  flagged_count: number;
  failed_count: number;
  triggered_rule_frequency: Record<string, number>;
  top_triggered_rules: Array<{ rule_name: string; count: number; action: string; example_transaction_id: string | null }>;
  unique_merchants: number;
  unique_devices: number;
  recent_merchants: Array<{ merchant_id: string; name: string; category_code: string; last_used: string }>;
  recent_devices: Array<{ device_id: string; fingerprint_hash: string; ip: string | null; last_used: string }>;
  cases: { total: number; open: number; in_progress: number; escalated: number; closed_approved: number; closed_denied: number };
  recent_transactions: Array<{ id: string; provider_event_id: string; amount: string; currency: string; status: string; merchant_name: string | null; merchant_id: string; device_id: string | null; risk_score: number; risk_level: string; decision: string; triggered_rules: string[]; created_at: string; has_case: boolean; case_id: string | null }>;
  risk_explanation: string;
  supporting_transaction_ids: string[];
};

export type MerchantListItem = {
  merchant_id: string;
  name: string;
  category_code: string;
  risk_level: string;
  created_at: string;
  total_transactions: number;
  total_volume: string;
  average_risk_score: number;
  risk_level_computed: string;
  unique_customers: number;
  unique_devices: number;
  total_cases: number;
};
export type MerchantListResponse = { items: MerchantListItem[]; total: number; page: number; page_size: number; total_pages: number };
export type MerchantProfile = {
  merchant_id: string;
  name: string;
  category_code: string;
  risk_level_merchant: string;
  created_at: string;
  total_transactions: number;
  total_volume: string;
  average_amount: string;
  min_amount: string | null;
  max_amount: string | null;
  first_activity: string | null;
  last_activity: string | null;
  average_risk_score: number;
  max_risk_score: number;
  risk_level: string;
  allowed_count: number;
  review_count: number;
  blocked_count: number;
  flagged_count: number;
  failed_count: number;
  triggered_rule_frequency: Record<string, number>;
  top_triggered_rules: Array<{ rule_name: string; count: number; action: string; example_transaction_id: string | null }>;
  unique_customers: number;
  unique_devices: number;
  recent_customers: Array<{ customer_id: string; external_id: string; risk_tier: string; last_used: string }>;
  recent_devices: Array<{ device_id: string; fingerprint_hash: string; ip: string | null; last_used: string }>;
  cases: { total: number; open: number; in_progress: number; escalated: number; closed_approved: number; closed_denied: number };
  recent_transactions: Array<{ id: string; provider_event_id: string; amount: string; currency: string; status: string; merchant_name: string | null; merchant_id: string; device_id: string | null; risk_score: number; risk_level: string; decision: string; triggered_rules: string[]; created_at: string; has_case: boolean; case_id: string | null }>;
  risk_explanation: string;
  supporting_transaction_ids: string[];
};

export type DeviceListItem = {
  device_id: string;
  fingerprint_hash: string;
  ip: string | null;
  user_agent: string | null;
  risk_score_device: number | null;
  created_at: string;
  total_transactions: number;
  total_volume: string;
  average_risk_score: number;
  risk_level: string;
  unique_customers: number;
  unique_merchants: number;
  total_cases: number;
};
export type DeviceListResponse = { items: DeviceListItem[]; total: number; page: number; page_size: number; total_pages: number };
export type DeviceProfile = {
  device_id: string;
  fingerprint_hash: string;
  ip: string | null;
  user_agent: string | null;
  risk_score_device: number | null;
  created_at: string;
  total_transactions: number;
  total_volume: string;
  average_amount: string;
  min_amount: string | null;
  max_amount: string | null;
  first_seen: string | null;
  last_seen: string | null;
  average_risk_score: number;
  max_risk_score: number;
  risk_level: string;
  allowed_count: number;
  review_count: number;
  blocked_count: number;
  flagged_count: number;
  failed_count: number;
  triggered_rule_frequency: Record<string, number>;
  top_triggered_rules: Array<{ rule_name: string; count: number; action: string; example_transaction_id: string | null }>;
  unique_customers: number;
  unique_merchants: number;
  recent_customers: Array<{ customer_id: string; external_id: string; risk_tier: string; last_used: string }>;
  recent_merchants: Array<{ merchant_id: string; name: string; category_code: string; last_used: string }>;
  cases: { total: number; open: number; in_progress: number; escalated: number; closed_approved: number; closed_denied: number };
  recent_transactions: Array<{ id: string; provider_event_id: string; amount: string; currency: string; status: string; merchant_name: string | null; merchant_id: string; device_id: string | null; risk_score: number; risk_level: string; decision: string; triggered_rules: string[]; created_at: string; has_case: boolean; case_id: string | null }>;
  risk_explanation: string;
  supporting_transaction_ids: string[];
  concentration_signal: string;
};

export type NetworkNode = {
  id: string;
  type: string;
  label: string;
  risk_score: number | null;
  risk_level: string;
  hop: number;
  external_id?: string | null;
  provider_event_id?: string | null;
};
export type NetworkEdge = {
  source: string;
  target: string;
  relationship: string;
  label: string;
  supporting_transaction_ids: string[];
  supporting_case_ids: string[];
};
export type NetworkStats = {
  node_count: number;
  edge_count: number;
  customer_count: number;
  merchant_count: number;
  device_count: number;
  transaction_count: number;
  case_count: number;
  max_hop: number;
};
export type NetworkGraphResponse = {
  root: NetworkNode;
  nodes: NetworkNode[];
  edges: NetworkEdge[];
  stats: NetworkStats;
};
export type NetworkGraphParams = {
  entity_type: "customer" | "merchant" | "device" | "transaction" | "case";
  entity_id: string;
  hops: number;
};

export type OverviewMetrics = {
  total_transactions: number;
  total_cases: number;
  open_cases: number;
  in_progress_cases: number;
  escalated_cases: number;
  high_risk_transactions: number;
  critical_risk_transactions: number;
  blocked_transactions: number;
  review_transactions: number;
  allowed_transactions: number;
  total_transaction_value: string;
  average_transaction_value: string;
};
export type RiskDistributionItem = { risk_level: string; count: number; percentage: number };
export type DecisionDistributionItem = { decision: string; count: number; percentage: number };
export type TransactionTrendItem = { date: string; transaction_count: number; transaction_value: string; high_risk_count: number; blocked_count: number };
export type CaseTrendItem = { date: string; opened: number; in_progress: number; resolved: number; confirmed_fraud: number };
export type RuleTriggerStats = { rule: string; count: number; action: string };
export type RiskConcentrationItem = { id: string; label: string; type: string; transaction_count: number; high_risk_count: number; blocked_count: number; total_value: string; average_risk_score: number; risk_level: string };
export type RiskConcentration = { customers: RiskConcentrationItem[]; merchants: RiskConcentrationItem[]; devices: RiskConcentrationItem[] };
export type DashboardAnalytics = {
  overview: OverviewMetrics;
  risk_distribution: RiskDistributionItem[];
  decision_distribution: DecisionDistributionItem[];
  transaction_trend: TransactionTrendItem[];
  case_trend: CaseTrendItem[];
  top_triggered_rules: RuleTriggerStats[];
  risk_concentration: RiskConcentration;
  generated_at: string;
  days: number;
};

export type RuleDetail = {
  id: string;
  name: string;
  description: string | null;
  enabled: boolean;
  priority: number;
  action: string;
  condition: string;
  dsl_expression: string;
  created_at: string | null;
  updated_at: string | null;
  version: number;
};
export type RuleListResponse = {
  items: RuleDetail[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};
export type RiskExplainResponse = {
  transaction_id: string;
  provider_event_id: string;
  amount: string;
  currency: string;
  risk_score: number;
  risk_level: string;
  decision: string;
  triggered_rules: Array<{ rule_id: string; rule_name: string; action: string; priority: number; matched: boolean; explanation: string; dsl_expression: string; condition: string }>;
  evaluated_rules: Array<{ rule_id: string; rule_name: string; action: string; priority: number; matched: boolean; explanation: string; dsl_expression: string; condition: string }>;
  decision_reason: string;
  score_breakdown: Record<string, unknown>;
  factors: Record<string, unknown>;
};

export type AlertItem = {
  id: string;
  transaction_id: string | null;
  case_id: string | null;
  rule_id: string | null;
  alert_type: string;
  title: string;
  description: string;
  severity: string;
  risk_score: number | null;
  decision: string;
  status: string;
  priority: number;
  assigned_to: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  resolution_reason: string | null;
  provider_event_id: string | null;
  customer_label: string | null;
  merchant_name: string | null;
  rule_name: string | null;
};
export type AlertListResponse = { items: AlertItem[]; total: number; page: number; page_size: number; total_pages: number };
export type AlertDetail = AlertItem & {
  merchant_category_code?: string | null;
};
export type OperationsSummary = {
  open_alerts: number;
  critical_alerts: number;
  high_alerts: number;
  acknowledged_alerts: number;
  in_progress_alerts: number;
  unresolved_alerts: number;
  alerts_last_24h: number;
  blocked_transactions: number;
  review_transactions: number;
  open_cases: number;
  escalated_cases: number;
  average_alert_risk: number;
  highest_priority_alert: { id: string; priority: number; title: string } | null;
  oldest_open_alert_age_hours: number | null;
  generated_at: string;
};

export class ApiService {
  public client: AxiosInstance;
  private _token: string | null;
  constructor(token: string | null) {
    this._token = token;
    this.client = axios.create({
      baseURL: API_BASE_URL,
      timeout: 30000,
    });
    if (token) this.setToken(token);
    // attach request id passthrough — always read latest token at request time
    this.client.interceptors.request.use((config) => {
      const current = this._token || localStorage.getItem("risk_era_token");
      if (current) (config.headers as any).Authorization = `Bearer ${current}`;
      const rid = localStorage.getItem("risk_era_request_id") || `req-${Date.now()}`;
      (config.headers as any)["X-Request-ID"] = rid;
      return config;
    });
  }
  setToken(token: string | null) {
    this._token = token;
    if (token) this.client.defaults.headers.common["Authorization"] = `Bearer ${token}`;
    else delete this.client.defaults.headers.common["Authorization"];
  }
  async health() {
    const r = await this.client.get("/health");
    return r.data;
  }
  async ready() {
    const r = await this.client.get("/ready");
    return r.data;
  }
  async toolsStatus() {
    const r = await this.client.get("/api/v1/tools/status");
    return r.data;
  }
  async getCases(page = 1, pageSize = 20, filters: Record<string, string | number | undefined> = {}) {
    const params: Record<string, unknown> = { page, page_size: pageSize, ...filters };
    // strip undefined
    Object.keys(params).forEach((k) => params[k] === undefined && delete params[k]);
    const r = await this.client.get("/api/v1/cases", { params });
    return r.data as CaseListResponse;
  }
  async getCase(caseId: string) {
    const r = await this.client.get(`/api/v1/cases/${caseId}`);
    return r.data as CaseDetail;
  }
  async getCaseEvidence(caseId: string) {
    const r = await this.client.get(`/api/v1/cases/${caseId}/evidence`);
    return r.data;
  }
  async getTransaction(transactionId: string) {
    const r = await this.client.get(`/api/v1/transactions/${transactionId}`);
    return r.data;
  }
  async getTransactions(params: TransactionListParams = {}) {
    const r = await this.client.get("/api/v1/transactions", { params });
    return r.data as TransactionListResponse;
  }
  async runInvestigation(caseId: string) {
    const r = await this.client.post(`/api/v1/investigation/${caseId}/run`);
    return r.data;
  }
  async getInvestigationResult(caseId: string) {
    const r = await this.client.get(`/api/v1/investigation/${caseId}/result`);
    return r.data;
  }
  async getInvestigationHistory(caseId: string) {
    const r = await this.client.get(`/api/v1/investigation/${caseId}/history`);
    return r.data;
  }
  async getWorkbench(caseId: string) {
    const r = await this.client.get(`/api/v1/investigation/${caseId}/workbench`);
    return r.data;
  }
  async submitFeedbackByInvestigation(investigationId: string, decision: string, corrected: string | null, reason: string) {
    const r = await this.client.post(`/api/v1/feedback/investigation/${investigationId}`, {
      decision: decision.toLowerCase(),
      corrected_recommendation: corrected,
      reason,
    });
    return r.data;
  }
  async getFeedbackByCase(caseId: string) {
    const r = await this.client.get(`/api/v1/feedback/case/${caseId}`);
    return r.data;
  }
  async getAuditEvents(params: Record<string, unknown> = {}) {
    const r = await this.client.get("/api/v1/audit/", { params });
    return r.data;
  }
  async getAuditSummary(params: Record<string, unknown> = {}) {
    const r = await this.client.get("/api/v1/audit/summary", { params });
    return r.data as { total: number; unique_actors: number; case_actions: number; investigation_actions: number; evidence_actions: number; alert_actions: number; status_changes: number; assignment_changes: number; latest_event_at: string | null; first_event_at: string | null };
  }
  async verifyAuditChain(limit = 1000) {
    const r = await this.client.get("/api/v1/audit/verify-chain", { params: { limit } });
    return r.data as { valid: boolean; error: string | null; checked_count?: number; total?: number; first_checked_at?: string | null; last_checked_at?: string | null };
  }
  async ingestTransaction(payload: Record<string, unknown>) {
    const r = await this.client.post("/api/v1/transactions", payload);
    return r.data;
  }
  async listCustomers(params: Record<string, unknown> = {}) {
    const r = await this.client.get("/api/v1/customers", { params });
    return r.data as CustomerListResponse;
  }
  async getCustomerProfile(customerId: string) {
    const r = await this.client.get(`/api/v1/customers/${customerId}/profile`);
    return r.data as CustomerProfile;
  }
  async listMerchants(params: Record<string, unknown> = {}) {
    const r = await this.client.get("/api/v1/merchants", { params });
    return r.data as MerchantListResponse;
  }
  async getMerchantProfile(merchantId: string) {
    const r = await this.client.get(`/api/v1/merchants/${merchantId}/profile`);
    return r.data as MerchantProfile;
  }
  async listDevices(params: Record<string, unknown> = {}) {
    const r = await this.client.get("/api/v1/devices", { params });
    return r.data as DeviceListResponse;
  }
  async getDeviceActivity(deviceId: string) {
    const r = await this.client.get(`/api/v1/devices/${deviceId}/activity`);
    return r.data as DeviceProfile;
  }
  async getNetworkGraph(params: NetworkGraphParams) {
    const r = await this.client.get("/api/v1/network/graph", { params });
    return r.data as NetworkGraphResponse;
  }
  async getDashboardAnalytics(days: number = 30) {
    const r = await this.client.get("/api/v1/analytics/dashboard", { params: { days } });
    return r.data as DashboardAnalytics;
  }
  async getRules(params: Record<string, unknown> = {}) {
    const r = await this.client.get("/api/v1/rules", { params });
    return r.data as RuleListResponse;
  }
  async getRule(ruleId: string) {
    const r = await this.client.get(`/api/v1/rules/${ruleId}`);
    return r.data as RuleDetail;
  }
  async getTransactionRiskExplanation(transactionId: string) {
    const r = await this.client.get(`/api/v1/transactions/${transactionId}/risk-explain`);
    return r.data as RiskExplainResponse;
  }
  async listAlerts(params: Record<string, unknown> = {}) {
    const r = await this.client.get("/api/v1/alerts", { params });
    return r.data as AlertListResponse;
  }
  async getAlert(alertId: string) {
    const r = await this.client.get(`/api/v1/alerts/${alertId}`);
    return r.data as AlertDetail;
  }
  async updateAlertStatus(alertId: string, status: string, reason?: string) {
    const r = await this.client.patch(`/api/v1/alerts/${alertId}/status`, { status, reason });
    return r.data as AlertDetail;
  }
  async assignAlert(alertId: string, assigned_to: string) {
    const r = await this.client.patch(`/api/v1/alerts/${alertId}/assign`, { assigned_to });
    return r.data as AlertDetail;
  }
  async resolveAlert(alertId: string, reason?: string) {
    const r = await this.client.post(`/api/v1/alerts/${alertId}/resolve`, { reason });
    return r.data as AlertDetail;
  }
  async dismissAlert(alertId: string, reason?: string) {
    const r = await this.client.post(`/api/v1/alerts/${alertId}/dismiss`, { reason });
    return r.data as AlertDetail;
  }
  async createCaseFromAlert(alertId: string) {
    const r = await this.client.post(`/api/v1/alerts/${alertId}/case`);
    return r.data as { alert_id: string; case_id: string; transaction_id: string };
  }
  async getOperationsSummary() {
    const r = await this.client.get("/api/v1/operations/summary");
    return r.data as OperationsSummary;
  }
  async assistantChat(payload: { message: string; context?: Record<string, unknown> }) {
    const r = await this.client.post("/api/v1/assistant/chat", payload);
    return r.data as { answer: string; grounded: boolean; sources: string[]; context_used?: Record<string, unknown> };
  }
}

export const useApi = (): ApiService => {
  const { token } = useContext(AuthContext)!;
  return useMemo(() => new ApiService(token), [token]);
};

export default ApiService;
