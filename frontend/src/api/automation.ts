/** 自动化操作相关 API */
import client, { API_PREFIX } from './client';

const BASE = `${API_PREFIX}/automation`;

export interface AutomationResult {
  success: boolean;
  message: string;
  step: string;
  details: Record<string, any>;
}

/** 自动登录 Google */
export const autoLogin = (accountId: number) =>
  client.post<AutomationResult>(`${BASE}/login`, { account_id: accountId });

/** 创建家庭组 */
export const createFamilyGroup = (accountId: number) =>
  client.post<AutomationResult>(`${BASE}/family/create`, { account_id: accountId });

/** 发送家庭组邀请 */
export const sendFamilyInvite = (accountId: number, inviteEmail: string) =>
  client.post<AutomationResult>(`${BASE}/family/invite`, {
    account_id: accountId,
    invite_email: inviteEmail,
  });

/** 接受家庭组邀请 */
export const acceptFamilyInvite = (accountId: number) =>
  client.post<AutomationResult>(`${BASE}/family/accept`, { account_id: accountId });

/** 移除家庭组成员 */
export const removeFamilyMember = (accountId: number, memberEmail: string) =>
  client.post<AutomationResult>(`${BASE}/family/remove-member`, {
    account_id: accountId,
    member_email: memberEmail,
  });

/** 退出家庭组 */
export const leaveFamilyGroup = (accountId: number) =>
  client.post<AutomationResult>(`${BASE}/family/leave`, { account_id: accountId });

/** 同步家庭组状态 (纯 HTTP, 不需要浏览器) */
export interface DiscoverResult {
  success: boolean;
  has_group: boolean;
  role: string;
  members: { name: string; email: string; role: string }[];
  member_count: number;
  message: string;
  cookies_expired?: boolean;
}

export const discoverFamily = (accountId: number) =>
  client.post<DiscoverResult>(`${BASE}/family/discover`, { account_id: accountId });

/** 获取 OAuth 凭证 JSON */
export const getOAuthCredential = (accountId: number) =>
  client.get<Record<string, any>>(`${BASE}/oauth/credential/${accountId}`);

/** 下载 OAuth 凭证文件 */
export const downloadOAuthCredential = async (accountId: number) => {
  const res = await client.get<Blob>(`${BASE}/oauth/credential/${accountId}/download`, {
    responseType: 'blob',
  });
  const disposition = (res.headers['content-disposition'] as string) || '';
  const match = disposition.match(/filename="?(.+?)"?$/i);
  const filename = match ? decodeURIComponent(match[1]) : 'credential.json';
  return { blob: res.data, filename };
};
