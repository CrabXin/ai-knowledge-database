"""登录鉴权与角色权限模块。

实现需求"其他功能1：用户登录，区分普通用户和管理员，管理员才有权限采集数据"。
- 使用 CSV 存储用户表（用户名、密码哈希、角色）
- 登录成功后签发 JWT，前端在后续请求头携带 Bearer Token
- 提供依赖项 get_current_user / require_admin 供路由做权限校验
"""
import csv
import datetime
import hashlib
import os

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import config

bearer_scheme = HTTPBearer(auto_error=False)


def _hash_password(password: str) -> str:
    """对密码做 SHA-256 加盐哈希。"""
    salted = (password + config.JWT_SECRET).encode("utf-8")
    return hashlib.sha256(salted).hexdigest()


# 三级角色：超级用户 > 管理员 > 普通用户
ROLE_SUPERADMIN = "superadmin"
ROLE_ADMIN = "admin"
ROLE_USER = "user"
VALID_ROLES = {ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_USER}

# 默认内置账号（首次启动时若缺失则补齐）
_DEFAULT_USERS = [
    ("superadmin", "super123", ROLE_SUPERADMIN),  # 超级用户：可新增管理员
    ("admin", "admin123", ROLE_ADMIN),            # 管理员：可采集数据、新增普通用户
    ("user", "user123", ROLE_USER),               # 普通用户：仅查看与问答
]


def init_default_users() -> None:
    """初始化/补齐默认用户表（幂等）。

    若用户表不存在则创建；若已存在但缺少某个内置账号（如新引入的 superadmin），
    则补写该账号，不影响已有数据。
    """
    existing = _load_users()
    if not os.path.exists(config.USER_CSV):
        with open(config.USER_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["username", "password_hash", "role"])
        existing = {}
    # 补齐缺失的内置账号
    missing = [(u, p, r) for (u, p, r) in _DEFAULT_USERS if u not in existing]
    if missing:
        with open(config.USER_CSV, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for u, p, r in missing:
                writer.writerow([u, _hash_password(p), r])


def _load_users() -> dict:
    """读取用户表，返回 {username: {password_hash, role}}。"""
    users = {}
    if not os.path.exists(config.USER_CSV):
        return users
    with open(config.USER_CSV, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            users[row["username"]] = {
                "password_hash": row["password_hash"],
                "role": row["role"],
            }
    return users


def list_users() -> list:
    """返回所有用户（不含密码）：[{username, role}]，供用户管理页展示。"""
    users = _load_users()
    return [{"username": u, "role": info["role"]} for u, info in users.items()]


def create_user(username: str, password: str, role: str) -> dict:
    """新增用户，写入用户表。

    Raises:
        ValueError: 用户名为空/已存在、密码过短或角色非法。
    """
    username = (username or "").strip()
    if not username or not password:
        raise ValueError("用户名和密码不能为空")
    if len(password) < 5:
        raise ValueError("密码长度至少 5 位")
    if role not in VALID_ROLES:
        raise ValueError("非法的角色")
    if username in _load_users():
        raise ValueError("用户名已存在")
    with open(config.USER_CSV, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([username, _hash_password(password), role])
    return {"username": username, "role": role}


def authenticate(username: str, password: str) -> dict:
    """校验用户名密码，成功返回用户信息，失败返回 None。"""
    users = _load_users()
    user = users.get(username)
    if not user:
        return None
    if user["password_hash"] != _hash_password(password):
        return None
    return {"username": username, "role": user["role"]}


def create_token(username: str, role: str) -> str:
    """签发 JWT。"""
    payload = {
        "sub": username,
        "role": role,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=config.JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """FastAPI 依赖：解析并校验 Token，返回当前登录用户。"""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    try:
        payload = jwt.decode(
            credentials.credentials, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM]
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已过期，请重新登录")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的登录凭证")
    return {"username": payload["sub"], "role": payload["role"]}


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """FastAPI 依赖：要求管理员或超级用户（用于采集接口）。"""
    if user["role"] not in (ROLE_ADMIN, ROLE_SUPERADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅管理员可执行数据采集")
    return user


def require_user_manager(user: dict = Depends(get_current_user)) -> dict:
    """FastAPI 依赖：要求具备用户管理权限（管理员或超级用户）。"""
    if user["role"] not in (ROLE_ADMIN, ROLE_SUPERADMIN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权管理用户")
    return user


def can_create_role(actor_role: str, target_role: str) -> bool:
    """判断 actor_role 是否有权创建 target_role 账号。

    - 超级用户：可创建 管理员 / 普通用户
    - 管理员：  仅可创建 普通用户
    - 其他：    不可创建
    """
    if actor_role == ROLE_SUPERADMIN:
        return target_role in (ROLE_ADMIN, ROLE_USER)
    if actor_role == ROLE_ADMIN:
        return target_role == ROLE_USER
    return False
