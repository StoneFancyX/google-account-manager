"""Pydantic 请求/响应模型 (Schemas)"""
from pydantic import BaseModel
from typing import Optional, List


# ---- 认证 ----

class LoginRequest(BaseModel):
    password: str


class SetPasswordRequest(BaseModel):
    password: str
    confirm_password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


# ---- 账号 ----

class AccountBase(BaseModel):
    email: str
    password: Optional[str] = ""
    recovery_email: Optional[str] = ""
    totp_secret: Optional[str] = ""
    tags: Optional[str] = ""
    group_name: Optional[str] = ""
    group_id: Optional[int] = None
    notes: Optional[str] = ""


class AccountCreate(AccountBase):
    pass


class AccountUpdate(AccountBase):
    pass


class AccountImportRequest(BaseModel):
    """批量导入账号请求

    格式: 邮箱----密码----辅助邮箱----2FA密钥----短信验证链接(可选)
    每行一个账号, 用 ---- 分隔字段
    """
    text: str
    tags: Optional[str] = ""
    group_name: Optional[str] = ""
    notes: Optional[str] = ""


# ---- 分组 ----

class GroupCreate(BaseModel):
    name: str
    notes: Optional[str] = ""


class GroupUpdate(BaseModel):
    name: str
    main_account_id: Optional[int] = None
    notes: Optional[str] = ""


# ---- 浏览器配置 ----

class BrowserProfileBase(BaseModel):
    name: str
    account_id: Optional[int] = None
    proxy_type: Optional[str] = ""
    proxy_host: Optional[str] = ""
    proxy_port: Optional[int] = None
    proxy_username: Optional[str] = ""
    proxy_password: Optional[str] = ""
    user_agent: Optional[str] = ""
    os_type: Optional[str] = "macos"
    timezone: Optional[str] = ""
    language: Optional[str] = "en-US"
    screen_width: Optional[int] = 1920
    screen_height: Optional[int] = 1080
    webrtc_disabled: Optional[bool] = True
    notes: Optional[str] = ""


class BrowserProfileCreate(BrowserProfileBase):
    pass


class BrowserProfileUpdate(BrowserProfileBase):
    pass
