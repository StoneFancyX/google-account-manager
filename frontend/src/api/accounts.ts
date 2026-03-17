/** 账号相关 API */
import client, { API_PREFIX } from './client';
import type { Account, TOTPResponse } from '@/types';

export const getAccounts = (search?: string, group?: string, tag?: string, page: number = 1, pageSize: number = 20, ownerOnly: boolean = false) => {
  const params = new URLSearchParams();
  if (search) params.append('search', search);
  if (group) params.append('group', group);
  if (tag) params.append('tag', tag);
  params.append('page', String(page));
  params.append('page_size', String(pageSize));
  if (ownerOnly) params.append('owner_only', 'true');
  return client.get<{ accounts: Account[]; total: number; page: number; page_size: number }>(`${API_PREFIX}/accounts?${params}`);
};

export const getAccount = (id: number) =>
  client.get<Account>(`${API_PREFIX}/accounts/${id}`);

export const createAccount = (data: Omit<Account, 'id'>) =>
  client.post<{ id: number; message: string }>(`${API_PREFIX}/accounts`, data);

export const updateAccount = (id: number, data: Omit<Account, 'id'>) =>
  client.put<{ message: string }>(`${API_PREFIX}/accounts/${id}`, data);

export const deleteAccount = (id: number) =>
  client.delete<{ message: string }>(`${API_PREFIX}/accounts/${id}`);

export const getGroups = () =>
  client.get<{ groups: string[] }>(`${API_PREFIX}/accounts/groups`);

export const getTags = () =>
  client.get<{ tags: string[] }>(`${API_PREFIX}/accounts/tags`);

export const getTOTP = (accountId: number) =>
  client.get<TOTPResponse>(`${API_PREFIX}/accounts/${accountId}/totp`);

export interface ImportResult {
  message: string;
  success: number;
  skipped: number;
  failed: number;
  details: { email?: string; line?: string; status: string; reason?: string; id?: number }[];
}

export const importAccounts = (text: string, tags?: string, group_name?: string, notes?: string) =>
  client.post<ImportResult>(`${API_PREFIX}/accounts/import`, { text, tags, group_name, notes });
