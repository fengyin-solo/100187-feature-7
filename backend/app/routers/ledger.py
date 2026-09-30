"""安全台账接口：查看已定级缺陷的台账归集与严重等级分布。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import PageResult
from app.services.ledger import LedgerService

router = APIRouter(prefix="/api/ledger", tags=["安全台账"])

service = LedgerService()

LIST_FIELDS = ["缺陷编号", "所在管段", "缺陷类别", "影响范围", "严重等级", "处置方案",
               "定级时间", "发现日期", "登记人员", "台账状态"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    severity: str | None = Query(default=None, description="按严重等级筛选：一般、较大、重大、特大"),
    status: str | None = Query(default=None, description="按台账状态筛选：已定级、处置中、已闭环"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """分页读取安全台账；台账只收已定级缺陷，空结果返回空页。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(severity=severity, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/distribution")
def severity_distribution() -> dict[str, Any]:
    """严重等级分布：台账页与运营概览都取这一份结果，保证口径一致。"""
    rows = service.severity_distribution()
    return {"items": rows, "total": sum(int(row["count"]) for row in rows)}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出安全台账全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "ledger", "total": total, "items": items}
