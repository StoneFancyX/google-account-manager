"""仪表盘路由 - 统计概览"""
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from deps import verify_token
from models.database import get_db
from models.orm import Account, Group

router = APIRouter(prefix="/dashboard", tags=["仪表盘"], dependencies=[Depends(verify_token)])


@router.get("")
async def get_stats(db: Session = Depends(get_db)):
    """获取仪表盘统计数据"""
    total_accounts = db.query(func.count(Account.id)).scalar() or 0
    total_groups = db.query(func.count(Group.id)).scalar() or 0

    with_2fa = db.query(func.count(Account.id)).filter(
        Account.totp_secret != "", Account.totp_secret.isnot(None)
    ).scalar() or 0

    without_2fa = total_accounts - with_2fa

    with_group = db.query(func.count(Account.id)).filter(
        Account.family_group_id.isnot(None)
    ).scalar() or 0

    # 标签统计
    tag_rows = db.query(Account.tags).filter(Account.tags != "", Account.tags.isnot(None)).all()
    tag_counts: dict[str, int] = {}
    for (tags_str,) in tag_rows:
        for tag in tags_str.split(","):
            tag = tag.strip()
            if tag:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
    top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    # 最近更新的账号
    recent = (
        db.query(Account.id, Account.email, Account.updated_at)
        .order_by(Account.updated_at.desc())
        .limit(5)
        .all()
    )
    recent_accounts = [
        {"id": r.id, "email": r.email, "updated_at": r.updated_at.isoformat() if r.updated_at else None}
        for r in recent
    ]

    return {
        "total_accounts": total_accounts,
        "total_groups": total_groups,
        "with_2fa": with_2fa,
        "without_2fa": without_2fa,
        "with_group": with_group,
        "top_tags": [{"tag": t, "count": c} for t, c in top_tags],
        "recent_accounts": recent_accounts,
    }
