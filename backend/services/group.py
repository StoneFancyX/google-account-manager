"""分组服务 - 处理分组 CRUD 和成员管理"""
from datetime import datetime, timezone
from typing import List, Dict, Optional

from sqlalchemy.orm import Session
from models.orm import Group, Account
from services.account import AccountService


class GroupService:
    """分组业务逻辑"""

    MAX_MEMBERS = 6  # 1 个主号 + 5 个子号

    def __init__(self, db: Session, account_service: AccountService):
        self.db = db
        self.account_service = account_service

    def _to_dict(self, group: Group, main_email: str = None) -> Dict:
        return {
            "id": group.id,
            "name": group.name,
            "main_account_id": group.main_account_id,
            "main_account_email": main_email or "",
            "notes": group.notes or "",
            "created_at": group.created_at.isoformat() if group.created_at else None,
            "updated_at": group.updated_at.isoformat() if group.updated_at else None,
        }

    def _ensure_main_account(self, accounts: List[Dict], main_id: int, group_id: int) -> List[Dict]:
        """主号的 family_group_id 意外丢失时，自动修复并补入列表"""
        if not main_id or any(a["id"] == main_id for a in accounts):
            return accounts
        main_acc = self.db.query(Account).get(main_id)
        if main_acc:
            main_acc.family_group_id = group_id
            self.db.commit()
            accounts.insert(0, self.account_service._to_dict(main_acc))
        return accounts

    def get_all(self, search: str = "") -> List[Dict]:
        rows = (
            self.db.query(Group, Account.email)
            .outerjoin(Account, Group.main_account_id == Account.id)
            .order_by(Group.name)
            .all()
        )
        result = []
        keyword = search.strip().lower()
        for group, email in rows:
            d = self._to_dict(group, email)
            accounts = self.get_accounts(group.id)
            d["accounts"] = self._ensure_main_account(accounts, group.main_account_id, group.id)
            # 搜索过滤: 匹配分组名、主号邮箱或任意子号邮箱
            if keyword:
                match = (
                    keyword in (group.name or "").lower()
                    or keyword in (email or "").lower()
                    or any(keyword in (a.get("email", "")).lower() for a in d["accounts"])
                )
                if not match:
                    continue
            result.append(d)
        return result

    def get_by_id(self, group_id: int) -> Optional[Dict]:
        result = (
            self.db.query(Group, Account.email)
            .outerjoin(Account, Group.main_account_id == Account.id)
            .filter(Group.id == group_id)
            .first()
        )
        if not result:
            return None
        group, email = result
        return self._to_dict(group, email)

    def get_with_accounts(self, group_id: int) -> Optional[Dict]:
        """获取分组详情（含成员列表）"""
        group_dict = self.get_by_id(group_id)
        if group_dict:
            accounts = self.get_accounts(group_id)
            group_dict["accounts"] = self._ensure_main_account(
                accounts, group_dict.get("main_account_id"), group_id
            )
        return group_dict

    def get_accounts(self, group_id: int) -> List[Dict]:
        """获取分组内所有账号"""
        rows = (
            self.db.query(Account)
            .filter(Account.family_group_id == group_id)
            .order_by(Account.email)
            .all()
        )
        return [self.account_service._to_dict(row) for row in rows]

    def create(self, name: str, notes: str = "") -> int:
        group = Group(name=name, notes=notes)
        self.db.add(group)
        self.db.commit()
        self.db.refresh(group)
        return group.id

    def update(self, group_id: int, name: str, main_account_id: int = None, notes: str = ""):
        group = self.db.query(Group).get(group_id)
        if not group:
            return
        group.name = name
        group.main_account_id = main_account_id
        group.notes = notes
        group.updated_at = datetime.now(timezone.utc)
        self.db.commit()

    def delete(self, group_id: int):
        group = self.db.query(Group).get(group_id)
        if group:
            # 先清除关联账号的 family_group_id
            self.db.query(Account).filter(Account.family_group_id == group_id).update(
                {"family_group_id": None}
            )
            self.db.delete(group)
            self.db.commit()

    def add_account(self, group_id: int, account_id: int):
        count = self.db.query(Account).filter(Account.family_group_id == group_id).count()
        if count >= self.MAX_MEMBERS:
            raise ValueError(f"分组最多只能有{self.MAX_MEMBERS}个账号（1个主号+5个子号）")

        account = self.db.query(Account).get(account_id)
        if account:
            account.family_group_id = group_id
            account.updated_at = datetime.now(timezone.utc)
            self.db.commit()

    def remove_account(self, account_id: int):
        account = self.db.query(Account).get(account_id)
        if account:
            account.family_group_id = None
            account.updated_at = datetime.now(timezone.utc)
            self.db.commit()

    def set_main_account(self, group_id: int, account_id: int):
        account = self.db.query(Account).get(account_id)
        if not account or account.family_group_id != group_id:
            raise ValueError("该账号不在指定的分组内")

        group = self.db.query(Group).get(group_id)
        if group:
            group.main_account_id = account_id
            group.updated_at = datetime.now(timezone.utc)
            self.db.commit()
