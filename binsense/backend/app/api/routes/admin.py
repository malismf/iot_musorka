"""Администрирование: выдача устройств, пользователи, журнал действий."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status

from ...devices import log_action, provision_device
from ...mqtt import mqtt_admin
from ...schemas import AuditOut, ProvisionIn, ProvisionOut, RoleUpdateIn, UserOut
from ..deps import AdminDep, PoolDep, client_ip
from .auth import user_out

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/devices", response_model=ProvisionOut, status_code=status.HTTP_201_CREATED)
async def provision(
    body: ProvisionIn, pool: PoolDep, user: AdminDep, request: Request
) -> ProvisionOut:
    """«Заводская» подготовка устройства: учётка MQTT + код привязки.

    Вызывается скриптом tools/provision.py при подготовке партии устройств.
    """
    result = await provision_device(
        pool, body.device_id, hw=body.hw, fw=body.fw, reset_claim_code=body.reset_claim_code
    )
    await log_action(
        pool, user["id"], "provision", result.device_id,
        {"created": result.created}, ip=client_ip(request),
    )
    return result


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: str, pool: PoolDep, user: AdminDep, request: Request
) -> None:
    device_id = device_id.lower()
    exists = await pool.fetchval("SELECT 1 FROM devices WHERE id = $1", device_id)
    if not exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Устройство не найдено")
    try:
        await mqtt_admin.clear_config(device_id)
        await mqtt_admin.delete_device(device_id)
    except Exception as exc:  # noqa: BLE001 — брокер может быть недоступен
        await log_action(pool, user["id"], "mqtt_delete_failed", device_id, {"error": str(exc)})
    await pool.execute("DELETE FROM devices WHERE id = $1", device_id)
    await log_action(pool, user["id"], "delete_device", device_id, ip=client_ip(request))


@router.get("/users", response_model=list[UserOut])
async def list_users(pool: PoolDep, user: AdminDep) -> list[UserOut]:
    rows = await pool.fetch("SELECT * FROM users ORDER BY id")
    return [user_out(r) for r in rows]


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_role(
    user_id: int, body: RoleUpdateIn, pool: PoolDep, user: AdminDep, request: Request
) -> UserOut:
    if user_id == user["id"] and body.role != "admin":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нельзя снять роль администратора с себя")
    row = await pool.fetchrow(
        "UPDATE users SET role = $2 WHERE id = $1 RETURNING *", user_id, body.role
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")
    await log_action(
        pool, user["id"], "role_change", None,
        {"user_id": user_id, "role": body.role}, ip=client_ip(request),
    )
    return user_out(row)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, pool: PoolDep, user: AdminDep, request: Request) -> None:
    if user_id == user["id"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нельзя удалить самого себя")
    await pool.execute("DELETE FROM users WHERE id = $1", user_id)
    await log_action(pool, user["id"], "delete_user", None, {"user_id": user_id},
                     ip=client_ip(request))


@router.get("/audit", response_model=list[AuditOut])
async def audit(
    pool: PoolDep, user: AdminDep, limit: Annotated[int, Query(ge=1, le=1000)] = 200
) -> list[AuditOut]:
    rows = await pool.fetch(
        """
        SELECT a.*, u.email AS user_email
          FROM audit_log a
          LEFT JOIN users u ON u.id = a.user_id
         ORDER BY a.created_at DESC
         LIMIT $1
        """,
        limit,
    )
    return [AuditOut(**dict(r)) for r in rows]


@router.get("/mqtt-clients", response_model=list[str])
async def mqtt_clients(user: AdminDep) -> list[str]:
    """Список учётных записей в брокере — помогает при отладке доступа."""
    try:
        return await mqtt_admin.list_clients()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Брокер недоступен: {exc}")
