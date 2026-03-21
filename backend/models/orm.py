"""SQLAlchemy ORM 模型定义"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import relationship, DeclarativeBase


class Base(DeclarativeBase):
    pass


class Config(Base):
    __tablename__ = "config"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)


class Group(Base):
    __tablename__ = "family_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    main_account_id = Column(Integer, ForeignKey("accounts.id", use_alter=True), nullable=True)
    member_count = Column(Integer, default=0)  # 家庭组实际成员数 (含系统外成员)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # 关系
    accounts = relationship("Account", back_populates="group", foreign_keys="Account.family_group_id")
    main_account = relationship("Account", foreign_keys=[main_account_id], post_update=True)


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, nullable=False)
    password = Column(Text, default="")
    recovery_email = Column(Text, default="")
    totp_secret = Column(Text, default="")
    tags = Column(Text, default="")
    group_name = Column(String, default="")
    family_group_id = Column(Integer, ForeignKey("family_groups.id", ondelete="SET NULL"), nullable=True)
    is_family_pending = Column(Boolean, default=False)  # 家庭组邀请待接受
    subscription_status = Column(String, default="")  # 订阅状态: free / ultra
    subscription_expiry = Column(String, default="")  # 订阅到期日, 如 "Mar 23, 2026"
    country = Column(String, default="")  # 账号所属国家/地区, 如 "United States"
    country_cn = Column(String, default="")  # 中文国家名, 如 "美国"
    cookies_json = Column(Text, default="")  # 登录后保存的 cookies (JSON), 用于纯 HTTP 操作
    oauth_credential_json = Column(Text, default="")  # OAuth 认证 JSON (antigravity 格式)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # 关系
    group = relationship("Group", back_populates="accounts", foreign_keys=[family_group_id])
    browser_profiles = relationship("BrowserProfile", back_populates="account", cascade="all, delete-orphan")


class BrowserProfile(Base):
    __tablename__ = "browser_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)

    # 代理
    proxy_type = Column(String, default="")        # http / socks5 / 空=不使用
    proxy_host = Column(String, default="")
    proxy_port = Column(Integer, nullable=True)
    proxy_username = Column(String, default="")
    proxy_password = Column(String, default="")

    # 指纹
    user_agent = Column(Text, default="")
    os_type = Column(String, default="macos")        # windows / macos / linux
    timezone = Column(String, default="")            # e.g. America/New_York
    language = Column(String, default="en-US")
    screen_width = Column(Integer, default=1920)
    screen_height = Column(Integer, default=1080)
    webrtc_disabled = Column(Boolean, default=True)

    notes = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # 关系
    account = relationship("Account", back_populates="browser_profiles")


class SmsProvider(Base):
    """接码提供商配置"""
    __tablename__ = "sms_providers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)  # 显示名称, 如 "HeroSMS 主号"
    provider_type = Column(String, nullable=False, default="herosms")  # herosms / smsbus
    api_key = Column(Text, default="")
    default_country = Column(Integer, default=2)  # 该提供商的默认国家
    default_service = Column(String, default="go")  # 该提供商的默认服务
    balance = Column(String, default="")  # 缓存余额
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class SmsActivation(Base):
    """接码记录"""
    __tablename__ = "sms_activations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    activation_id = Column(String, nullable=False, index=True)  # HeroSMS 返回的激活 ID
    provider_id = Column(Integer, ForeignKey("sms_providers.id", ondelete="SET NULL"), nullable=True)  # 关联的提供商
    phone_number = Column(String, default="")  # 手机号码
    service = Column(String, default="")  # 服务代码, 如 "go" (Google)
    country = Column(Integer, default=0)  # 国家 ID
    country_name = Column(String, default="")  # 国家名称
    operator = Column(String, default="")  # 运营商
    cost = Column(String, default="")  # 费用
    sms_code = Column(String, default="")  # 收到的验证码
    sms_text = Column(String, default="")  # 完整短信内容
    status = Column(String, default="pending")  # pending / code_received / finished / cancelled / error
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)  # 关联的账号
    account_email = Column(String, default="")  # 冗余存储邮箱, 方便查询
    notes = Column(Text, default="")  # 备注
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
