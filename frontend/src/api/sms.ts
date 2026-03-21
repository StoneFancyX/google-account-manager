/** 接码管理 API */
import client, { API_PREFIX } from './client';

// ── 提供商类型 ──────────────────────────────────────

export interface SmsProviderConfig {
  id: number;
  name: string;
  provider_type: string;
  api_key: string;
  default_country: number;
  default_service: string;
  balance: string;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface SmsActivationRecord {
  id: number;
  activation_id: string;
  provider_id: number | null;
  phone_number: string;
  service: string;
  country: number;
  country_name: string;
  operator: string;
  cost: string;
  sms_code: string;
  sms_text: string;
  status: string;
  account_id: number | null;
  account_email: string;
  notes: string;
  created_at: string;
  updated_at: string;
}

// ── 提供商 CRUD ─────────────────────────────────────

export const getSmsProviders = () =>
  client.get<SmsProviderConfig[]>(`${API_PREFIX}/sms/providers`);

export const createSmsProvider = (data: Partial<SmsProviderConfig>) =>
  client.post<SmsProviderConfig>(`${API_PREFIX}/sms/providers`, data);

export const updateSmsProvider = (id: number, data: Partial<SmsProviderConfig>) =>
  client.put<SmsProviderConfig>(`${API_PREFIX}/sms/providers/${id}`, data);

export const deleteSmsProvider = (id: number) =>
  client.delete(`${API_PREFIX}/sms/providers/${id}`);

// ── 余额 ────────────────────────────────────────────

export const getSmsBalance = (providerId?: number) =>
  client.get<{ balance: string }>(`${API_PREFIX}/sms/balance`, { params: { provider_id: providerId } });

// ── 接码操作 ────────────────────────────────────────

export const requestNumber = (data: {
  provider_id?: number; service: string; country: number;
  operator?: string; max_price?: number; account_id?: number; account_email?: string;
}) =>
  client.post<{ id: number; activation_id: string; phone_number: string; cost: string }>(
    `${API_PREFIX}/sms/request-number`, data
  );

export const checkSmsStatus = (activationId: string, providerId?: number) =>
  client.get<{ status: string; info: string; code: string; sms_text?: string }>(
    `${API_PREFIX}/sms/status/${activationId}`, { params: { provider_id: providerId } }
  );

export const finishSmsActivation = (activationId: string, providerId?: number) =>
  client.post<{ result: string }>(`${API_PREFIX}/sms/finish/${activationId}`, null, { params: { provider_id: providerId } });

export const cancelSmsActivation = (activationId: string, providerId?: number) =>
  client.post<{ result: string }>(`${API_PREFIX}/sms/cancel/${activationId}`, null, { params: { provider_id: providerId } });

// ── 历史 / 列表 ─────────────────────────────────────

export const getSmsHistory = (page = 1, pageSize = 20, status?: string) =>
  client.get<{ total: number; records: SmsActivationRecord[] }>(
    `${API_PREFIX}/sms/history`, { params: { page, page_size: pageSize, status } }
  );

export const getSmsCountries = (providerId?: number) =>
  client.get<{ id: number; name: string }[]>(`${API_PREFIX}/sms/countries`, { params: { provider_id: providerId } });

export const getSmsServices = (providerId?: number) =>
  client.get<{ code: string; name: string }[]>(`${API_PREFIX}/sms/services`, { params: { provider_id: providerId } });

export const getSmsPricesByService = (service: string, providerId?: number) =>
  client.get<{ country_id: number; country_name: string; count: number; price: string }[]>(
    `${API_PREFIX}/sms/prices-by-service/${service}`, { params: { provider_id: providerId } }
  );
