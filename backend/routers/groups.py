"""分组路由 - 分组 CRUD、成员管理"""
from fastapi import APIRouter, HTTPException, Depends

from deps import verify_token, get_group_service
from models.schemas import GroupCreate, GroupUpdate
from services.group import GroupService

router = APIRouter(
    prefix="/groups", tags=["分组"], dependencies=[Depends(verify_token)]
)


@router.get("")
async def list_groups(
    search: str = "",
    svc: GroupService = Depends(get_group_service),
):
    """获取所有分组 (支持按子号邮箱搜索)"""
    return {"groups": svc.get_all(search=search)}


@router.get("/{group_id}")
async def get_group(group_id: int, svc: GroupService = Depends(get_group_service)):
    """获取分组详情（含成员）"""
    group = svc.get_with_accounts(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="分组不存在")
    return group


@router.post("", status_code=201)
async def create_group(
    data: GroupCreate,
    svc: GroupService = Depends(get_group_service),
):
    """创建分组"""
    group_id = svc.create(name=data.name, notes=data.notes)
    return {"id": group_id, "message": "分组创建成功"}


@router.put("/{group_id}")
async def update_group(
    group_id: int,
    data: GroupUpdate,
    svc: GroupService = Depends(get_group_service),
):
    """更新分组"""
    svc.update(
        group_id=group_id,
        name=data.name,
        main_account_id=data.main_account_id,
        notes=data.notes,
    )
    return {"message": "分组更新成功"}


@router.delete("/{group_id}")
async def delete_group(
    group_id: int, svc: GroupService = Depends(get_group_service)
):
    """删除分组"""
    svc.delete(group_id)
    return {"message": "分组删除成功"}


@router.post("/{group_id}/accounts/{account_id}")
async def add_account(
    group_id: int,
    account_id: int,
    svc: GroupService = Depends(get_group_service),
):
    """将账号添加到分组"""
    try:
        svc.add_account(group_id, account_id)
        return {"message": "账号已添加到分组"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/accounts/{account_id}")
async def remove_account(
    account_id: int,
    svc: GroupService = Depends(get_group_service),
):
    """将账号从分组移除"""
    svc.remove_account(account_id)
    return {"message": "账号已从分组移除"}


@router.put("/{group_id}/main-account/{account_id}")
async def set_main_account(
    group_id: int,
    account_id: int,
    svc: GroupService = Depends(get_group_service),
):
    """设置分组主号"""
    try:
        svc.set_main_account(group_id, account_id)
        return {"message": "主号设置成功"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
