"""缺陷登记接口：缺陷记录、定级口径维护、查重合并、确认定级与安全台账。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.defect import (
    CATEGORY_OPTIONS,
    SCOPE_OPTIONS,
    SEVERITY_LEVELS,
    DefectService,
)

router = APIRouter(prefix="/api/defect", tags=["缺陷登记"])

service = DefectService()

LIST_FIELDS = ["缺陷编号", "所在管段", "缺陷类别", "影响范围", "缺陷位置", "严重等级", "发现日期", "登记人员", "缺陷状态"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按缺陷编号检索"),
    status: str | None = Query(default=None, description="待定级、已定级、处置中、已闭环"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按缺陷编号与状态过滤缺陷登记列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/options")
def list_options() -> dict[str, object]:
    """定级相关的枚举口径，供前端下拉框与校验使用。"""
    return {
        "severity": SEVERITY_LEVELS,
        "scope": SCOPE_OPTIONS,
        "category": CATEGORY_OPTIONS,
        "topSeverity": SEVERITY_LEVELS[-1],
    }


@router.get("/rules")
def list_rules() -> dict[str, object]:
    """查看当前定级口径及规则版本。"""
    return {"version": service.rule_version(), "items": service.list_rules()}


@router.post("/rules/preview")
def preview_rule(payload: EntryPayload) -> ActionResult:
    """试算某类别 × 范围按当前口径会得到的建议等级，不改动任何数据。"""
    preview = service.preview_rule(
        payload.values.get("缺陷类别", ""), payload.values.get("影响范围", "")
    )
    if not preview["建议等级"]:
        return ActionResult(ok=False, message="当前口径没有可命中的规则，请先维护定级口径", preview=preview)
    return ActionResult(ok=True, message=f"建议严重等级：{preview['建议等级']}", preview=preview)


@router.post("/rules")
def upsert_rule(payload: EntryPayload) -> ActionResult:
    """新增或调整一条定级规则；版本递增，新口径只对之后登记的记录生效。"""
    rule, message = service.upsert_rule(payload.values)
    if rule is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=rule, version=service.rule_version())


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int) -> ActionResult:
    """删除一条定级规则；已定级的历史记录等级不受影响。"""
    return ActionResult(ok=True, message=service.delete_rule(rule_id), version=service.rule_version())


@router.get("/ledger")
def get_ledger() -> dict[str, object]:
    """安全台账：定级结果汇总，严重等级分布与运营概览取同一口径。"""
    return service.ledger()


@router.get("/export")
def export_entries() -> dict[str, object]:
    """导出缺陷登记清单：返回全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "defect", "total": total, "items": items}


@router.post("/merge", response_model=ActionResult)
def merge_entry(payload: EntryPayload) -> ActionResult:
    """查重提示后选择合并：把本次登记并进一条已有的同管段同类缺陷。"""
    try:
        target_id = int(payload.values.get("targetId") or 0)
    except (TypeError, ValueError):
        return ActionResult(ok=False, message="缺少合并目标缺陷编号")
    if not target_id:
        return ActionResult(ok=False, message="缺少合并目标缺陷编号")
    entry, message = service.merge_entry(target_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条缺陷记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"缺陷记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条缺陷记录：缺字段说明缺哪项；同管段同类未闭环缺陷提示合并。"""
    entry, message, extra = service.create_entry(payload.values, force=payload.force)
    if entry is not None:
        return ActionResult(ok=True, message="缺陷记录已登记，建议严重等级已按当前口径给出", entry=entry)
    candidates = extra.get("candidates")
    if candidates:
        return ActionResult(
            ok=False,
            code="DUPLICATE",
            message=message,
            candidates=candidates,
        )
    return ActionResult(ok=False, message=message)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """确认定级、提交闭环、挂起缺陷；等级与处置方案冲突或字段缺失时拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    action_values = {k: v for k, v in payload.values.items() if k != "action"}
    entry, message = service.run_action(entry_id, action, action_values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
