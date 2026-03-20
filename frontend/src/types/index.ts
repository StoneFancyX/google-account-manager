/** 数据类型定义 */

export interface Account {
  id: number;
  email: string;
  password: string;
  recovery_email?: string;
  totp_secret?: string;
  tags?: string;
  group_name?: string;
  group_id?: number;
  family_group_id?: number;
  is_family_owner?: boolean;
  is_family_pending?: boolean;
  family_member_count?: number;
  subscription_status?: string;
  subscription_expiry?: string;
  country?: string;
  country_cn?: string;
  has_oauth_credential?: boolean;
  validation_url?: string;
  notes?: string;
  created_at?: string;
  updated_at?: string;
}

export interface Group {
  id: number;
  name: string;
  main_account_id?: number;
  main_account_email?: string;
  notes?: string;
  accounts?: Account[];
  created_at?: string;
  updated_at?: string;
}

export interface TOTPResponse {
  code: string;
  remaining: number;
  formatted: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}
