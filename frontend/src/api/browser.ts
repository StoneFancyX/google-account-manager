/** 浏览器配置相关 API */
import client, { API_PREFIX } from './client';

export interface BrowserProfile {
  id: number;
  name: string;
  account_id: number | null;
  account_email: string;
  proxy_type: string;
  proxy_host: string;
  proxy_port: number | null;
  proxy_username: string;
  proxy_password: string;
  user_agent: string;
  os_type: string;
  timezone: string;
  language: string;
  screen_width: number;
  screen_height: number;
  webrtc_disabled: boolean;
  notes: string;
  status: 'running' | 'stopped';
  created_at: string;
  updated_at: string;
}

export type BrowserProfileForm = Omit<BrowserProfile, 'id' | 'account_email' | 'status' | 'created_at' | 'updated_at'>;

const BASE = `${API_PREFIX}/browser-profiles`;

export const getBrowserProfiles = () =>
  client.get<{ profiles: BrowserProfile[] }>(BASE);

export const getBrowserProfile = (id: number) =>
  client.get<BrowserProfile>(`${BASE}/${id}`);

export const createBrowserProfile = (data: BrowserProfileForm) =>
  client.post(BASE, data);

export const updateBrowserProfile = (id: number, data: BrowserProfileForm) =>
  client.put(`${BASE}/${id}`, data);

export const deleteBrowserProfile = (id: number) =>
  client.delete(`${BASE}/${id}`);

export const launchBrowser = (id: number) =>
  client.post(`${BASE}/${id}/launch`);

export const stopBrowser = (id: number) =>
  client.post(`${BASE}/${id}/stop`);

export const getBrowserStatus = (id: number) =>
  client.get(`${BASE}/${id}/status`);

export const clearBrowserData = (id: number) =>
  client.delete(`${BASE}/${id}/data`);
