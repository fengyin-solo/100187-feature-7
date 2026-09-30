"""缺陷登记接口：缺陷登记、定级口径维护、试算定级、合并与定级动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.defect import SCOPES, SEVERITY_LEVELS, DefectService

router = APIRouter(prefix="/api/defect", tags=["缺陷登记"])

service = DefectService()

LIST_FIELDS = ["缺陷编号", "所在管段", "缺陷类别", "影响范围", "缺陷位置",
               "严重等级", "建议严重等级", "处置方案", "发现日期", "登记人员", "缺陷状态"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按缺陷编号检索"),
    pipe: str | None = Query(default=None, description="按所在管段检索"),
    category: str | None = Query(default=None, description="按缺陷类别检索"),
    status: str | None = Query(default=None, description="待定级、已定级、处置中、已闭环、已合并"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按编号、管段、类别与状态过滤缺陷登记列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword, pipe=pipe, category=category, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/options")
def grade_options() -> dict[str, Any]:
    """定级相关的下拉口径：影响范围、严重等级；前端表单与口径管理共用。"""
    return {"影响范围": SCOPES, "严重等级": SEVERITY_LEVELS}


@router.get("/rules")
def list_rules() -> dict[str, Any]:
    """读取定级口径规则全量表（缺陷类别 + 影响范围 → 严重等级）。"""
    return {"items": service.list_rules()}


@router.post("/rules", response_model=ActionResult)
def create_rule(payload: EntryPayload) -> ActionResult:
    """新增一条定级口径；重复口径或等级非法时拒绝并说明。"""
    rule, message = service.create_rule(payload.values)
    if rule is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="定级口径已新增", entry=rule)


@router.put("/rules/{rule_id}", response_model=ActionResult)
def update_rule(rule_id: int, payload: EntryPayload) -> ActionResult:
    """调整一条口径的严重等级；只对调整后新登记的记录生效，历史记录不动。"""
    rule, message = service.update_rule(rule_id, payload.values)
    if rule is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="定级口径已调整，仅影响之后新登记的记录", entry=rule)


@router.delete("/rules/{rule_id}", response_model=ActionResult)
def delete_rule(rule_id: int) -> ActionResult:
    """删除一条口径；通用兜底口径不允许删除。"""
    message = service.delete_rule(rule_id)
    if message:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="定级口径已删除")


@router.post("/grade-preview", response_model=ActionResult)
def preview_grade(payload: EntryPayload) -> ActionResult:
    """按当前口径试算建议严重等级，供登记表单在提交前提示。"""
    preview, message = service.preview_grade(payload.values)
    if preview is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=str(preview["口径说明"]), entry=preview)


@router.get("/stats")
def stats() -> dict[str, Any]:
    """缺陷状态计数与超期未闭环数，供页面顶部指标卡使用。"""
    return service.stats()


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出缺陷登记清单：返回全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "defect", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条缺陷记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"缺陷记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条缺陷记录。

    字段不全时说明缺哪一项；同一管段同类未闭环缺陷重复登记时返回重复清单提示合并；
    明确带上 ignore_duplicates=true 表示已知晓重复仍要建档。
    """
    ignore = str(payload.values.pop("ignore_duplicates", "")).strip().lower() in ("true", "1", "yes")
    entry, message, duplicates = service.create_entry(payload.values, ignore_duplicates=ignore)
    if entry is None:
        return ActionResult(
            ok=False,
            message=message,
            duplicates=[{"id": row.get("id"), "缺陷编号": row.get("缺陷编号"),
                         "所在管段": row.get("所在管段"), "缺陷类别": row.get("缺陷类别"),
                         "status": row.get("status")} for row in duplicates],
        )
    result = ActionResult(ok=True, message="缺陷记录已登记，建议严重等级已按当前口径给出", entry=entry)
    return result


@router.post("/{entry_id}/merge", response_model=ActionResult)
def merge_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """把重复登记内容合并进已有缺陷（{entry_id} 为合并目标），不新增记录。"""
    target, message = service.merge_into(entry_id, payload.values)
    if target is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=f"已合并到缺陷「{target.get('缺陷编号')}」", entry=target)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条缺陷执行确认定级、提交闭环、挂起缺陷。

    确认定级时等级到上限（特大）却没有处置方案，或字段不完整，直接拒绝保存；
    已定级的历史记录不能重复定级，保持原等级不变。
    """
    action = str(payload.values.pop("action", "")).strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
