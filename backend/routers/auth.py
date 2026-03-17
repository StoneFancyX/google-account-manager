"""认证路由 - 密码设置、登录"""
from fastapi import APIRouter, HTTPException, Depends

from deps import (
    get_auth_service,
    create_access_token, state,
)
from models.schemas import LoginRequest, SetPasswordRequest, TokenResponse
from services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["认证"])


@router.get("/check-setup")
async def check_setup(auth: AuthService = Depends(get_auth_service)):
    """检查是否已设置主密码"""
    return {"has_password": auth.has_master_password()}


@router.post("/setup", response_model=TokenResponse)
async def setup_password(
    request: SetPasswordRequest,
    auth: AuthService = Depends(get_auth_service),
):
    """首次设置主密码"""
    if auth.has_master_password():
        raise HTTPException(status_code=400, detail="主密码已设置")
    if request.password != request.confirm_password:
        raise HTTPException(status_code=400, detail="两次密码不一致")
    if len(request.password) < 6:
        raise HTTPException(status_code=400, detail="密码长度至少6位")

    auth.set_master_password(request.password)
    state.logged_in = True

    return {"access_token": create_access_token({"sub": "user"}), "token_type": "bearer"}


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    auth: AuthService = Depends(get_auth_service),
):
    """登录验证"""
    if not auth.verify_master_password(request.password):
        raise HTTPException(status_code=401, detail="密码错误")

    state.logged_in = True

    return {"access_token": create_access_token({"sub": "user"}), "token_type": "bearer"}
