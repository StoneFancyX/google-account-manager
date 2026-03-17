/** 分组相关 API */
import client, { API_PREFIX } from './client';
import type { Group } from '@/types';

export const getGroupList = (search?: string) => {
  const params = new URLSearchParams();
  if (search) params.append('search', search);
  const qs = params.toString();
  return client.get<{ groups: Group[] }>(`${API_PREFIX}/groups${qs ? `?${qs}` : ''}`);
};

export const getGroup = (id: number) =>
  client.get<Group>(`${API_PREFIX}/groups/${id}`);

export const createGroup = (data: { name: string; notes?: string }) =>
  client.post<{ id: number; message: string }>(`${API_PREFIX}/groups`, data);

export const updateGroup = (id: number, data: { name: string; main_account_id?: number; notes?: string }) =>
  client.put<{ message: string }>(`${API_PREFIX}/groups/${id}`, data);

export const deleteGroup = (id: number) =>
  client.delete<{ message: string }>(`${API_PREFIX}/groups/${id}`);

export const addAccountToGroup = (groupId: number, accountId: number) =>
  client.post<{ message: string }>(`${API_PREFIX}/groups/${groupId}/accounts/${accountId}`);

export const removeAccountFromGroup = (accountId: number) =>
  client.delete<{ message: string }>(`${API_PREFIX}/groups/accounts/${accountId}`);

export const setMainAccount = (groupId: number, accountId: number) =>
  client.put<{ message: string }>(`${API_PREFIX}/groups/${groupId}/main-account/${accountId}`);
