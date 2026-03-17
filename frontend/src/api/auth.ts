/** 认证相关 API */
import client, { API_PREFIX } from './client';
import type { TokenResponse } from '@/types';

export const checkSetup = () =>
  client.get<{ has_password: boolean }>(`${API_PREFIX}/auth/check-setup`);

export const setupPassword = (password: string, confirmPassword: string) =>
  client.post<TokenResponse>(`${API_PREFIX}/auth/setup`, {
    password,
    confirm_password: confirmPassword,
  });

export const login = (password: string) =>
  client.post<TokenResponse>(`${API_PREFIX}/auth/login`, { password });
