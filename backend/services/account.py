"""账号服务 - 处理账号 CRUD"""
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional

from sqlalchemy.orm import Session
from models.orm import Account


class AccountService:
    """账号业务逻辑"""

    def __init__(self, db: Session, crypto=None):
        self.db = db

    def set_crypto(self, crypto):
        pass  # 不再需要加密管理器

    def _to_dict(self, account: Account) -> Dict:
        """ORM 对象转字典"""
        from models.orm import Group

        # 判断是否是家庭组管理员 + 成员数
        is_family_owner = False
        family_member_count = 0
        if account.family_group_id:
            group = self.db.query(Group).get(account.family_group_id)
            if group:
                family_member_count = group.member_count or 0
                if group.main_account_id == account.id:
                    is_family_owner = True

        return {
            "id": account.id,
            "email": account.email,
            "password": account.password or "",
            "recovery_email": account.recovery_email or "",
            "totp_secret": account.totp_secret or "",
            "tags": account.tags or "",
            "group_name": account.group_name or "",
            "family_group_id": account.family_group_id,
            "is_family_owner": is_family_owner,
            "is_family_pending": bool(account.is_family_pending),
            "family_member_count": family_member_count,
            "subscription_status": account.subscription_status or "",
            "subscription_expiry": account.subscription_expiry or "",
            "country": account.country or "",
            "country_cn": account.country_cn or "",
            "has_oauth_credential": bool(account.oauth_credential_json),
            "validation_url": self._get_validation_url(account.oauth_credential_json),
            "notes": account.notes or "",
            "created_at": account.created_at.isoformat() if account.created_at else None,
            "updated_at": account.updated_at.isoformat() if account.updated_at else None,
        }

    def _get_validation_url(self, oauth_json: str) -> str:
        """从 oauth_credential_json 中提取 validation_url"""
        if not oauth_json:
            return ""
        try:
            cred = json.loads(oauth_json)
            return cred.get("validation_url", "")
        except Exception:
            return ""

    def get_all(
        self, search: str = "", group_filter: str = "", tag_filter: str = "",
        page: int = 1, page_size: int = 20, owner_only: bool = False,
    ) -> tuple[List[Dict], int]:
        from models.orm import Group

        query = self.db.query(Account)

        if search:
            like = f"%{search}%"
            query = query.filter(Account.email.ilike(like) | Account.notes.ilike(like))
        if group_filter:
            query = query.filter(Account.group_name == group_filter)
        if tag_filter:
            query = query.filter(Account.tags.ilike(f"%{tag_filter}%"))
        if owner_only:
            # 仅显示家庭组创建者 (main_account_id 指向自己的账号)
            query = query.filter(
                Account.family_group_id.isnot(None),
                Account.id.in_(
                    self.db.query(Group.main_account_id).filter(Group.main_account_id.isnot(None))
                ),
            )

        query = query.order_by(Account.email)
        total = query.count()
        rows = query.offset((page - 1) * page_size).limit(page_size).all()
        return [self._to_dict(row) for row in rows], total

    def get_by_id(self, account_id: int) -> Optional[Dict]:
        row = self.db.query(Account).get(account_id)
        return self._to_dict(row) if row else None

    def find_by_email(self, email: str) -> Optional[Dict]:
        """通过邮箱查找账号（不区分大小写）"""
        row = self.db.query(Account).filter(Account.email.ilike(email)).first()
        return self._to_dict(row) if row else None

    def create(
        self,
        email: str,
        password: str = "",
        recovery_email: str = "",
        totp_secret: str = "",
        tags: str = "",
        group_name: str = "",
        family_group_id: int = None,
        notes: str = "",
    ) -> int:
        account = Account(
            email=email,
            password=password,
            recovery_email=recovery_email,
            totp_secret=totp_secret,
            tags=tags,
            group_name=group_name,
            family_group_id=family_group_id,
            notes=notes,
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return account.id

    def update(
        self,
        account_id: int,
        email: str,
        password: str = "",
        recovery_email: str = "",
        totp_secret: str = "",
        tags: str = "",
        group_name: str = "",
        family_group_id: int = None,
        notes: str = "",
    ):
        account = self.db.query(Account).get(account_id)
        if not account:
            return

        account.email = email
        account.password = password
        account.recovery_email = recovery_email
        account.totp_secret = totp_secret
        account.tags = tags
        account.group_name = group_name
        # 仅在显式传入时更新，避免编辑账号时意外清空分组关联
        if family_group_id is not None:
            account.family_group_id = family_group_id
        account.notes = notes
        account.updated_at = datetime.now(timezone.utc)

        self.db.commit()

    def delete(self, account_id: int):
        account = self.db.query(Account).get(account_id)
        if account:
            self.db.delete(account)
            self.db.commit()

    def get_all_groups(self) -> List[str]:
        rows = (
            self.db.query(Account.group_name)
            .filter(Account.group_name != "")
            .distinct()
            .order_by(Account.group_name)
            .all()
        )
        return [r[0] for r in rows]

    def get_all_tags(self) -> List[str]:
        rows = (
            self.db.query(Account.tags)
            .filter(Account.tags != "")
            .all()
        )
        all_tags = set()
        for (tags_str,) in rows:
            all_tags.update(t.strip() for t in tags_str.split(",") if t.strip())
        return sorted(all_tags)
