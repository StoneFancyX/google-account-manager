/** 仪表盘 API */
import client, { API_PREFIX } from './client';

export interface DashboardStats {
  total_accounts: number;
  total_groups: number;
  with_2fa: number;
  without_2fa: number;
  with_group: number;
  top_tags: { tag: string; count: number }[];
  recent_accounts: { id: number; email: string; updated_at: string | null }[];
}

export const getDashboardStats = () => client.get<DashboardStats>(`${API_PREFIX}/dashboard`);
