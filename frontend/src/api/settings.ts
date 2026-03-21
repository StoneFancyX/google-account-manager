/** 系统设置 API */
import client, { API_PREFIX } from './client';

export interface Settings {
  debug_mode: boolean;
  headless_mode: boolean;
  default_sms_provider_id: string;
  card_number: string;
  card_expiry: string;
  card_cvv: string;
  card_zip: string;
}

/** 获取系统设置 */
export const getSettings = () =>
  client.get<Settings>(`${API_PREFIX}/settings`);

/** 更新系统设置 */
export const updateSettings = (data: Partial<Settings>) =>
  client.put<Settings>(`${API_PREFIX}/settings`, data);
