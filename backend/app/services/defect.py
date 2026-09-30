"""缺陷登记业务规则。

口径都收在这一层：
- 定级口径是可维护的规则（缺陷类别 + 影响范围 → 建议严重等级），存在独立规则表里；
- 登记时按当前口径给出建议等级，规则调整只影响之后新登记的记录；
- 已定级记录的等级永久冻结，口径调整不回改历史；
- 同一管段同类未闭环缺陷重复登记时提示合并；
- 确认定级时等级与处置方案冲突（到上限却没有处置方案）直接拦下；
- 定级结果同步进安全台账，台账与概览共用同一份分布口径。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.store import store
# 安全台账服务反向依赖本模块的等级常量，这里延迟导入以避开循环引用；
# 实际在定级/流转方法里通过 _ledger() 取用。

MODULE = "defect"
RULE_MODULE = "defect_grade_rules"

REQUIRED_FIELDS = ["缺陷编号", "所在管段", "缺陷类别", "影响范围"]
EXTRA_FIELDS = ["缺陷位置", "发现日期", "登记人员"]

STATUS_ORDER = ["待定级", "已定级", "处置中", "已闭环", "已合并"]
OPEN_STATUSES = ["待定级", "已定级", "处置中"]
ACTION_RULES = {"确认定级": "已定级", "提交闭环": "处置中", "挂起缺陷": "已闭环"}

# 影响范围按影响面从小到大排列，规则匹配与下拉选项都用这份顺序。
SCOPES = ["单点局部", "支管接入", "干管交汇", "片区影响"]
SCOPE_WILDCARD = "通用"
SEVERITY_LEVELS = ["一般", "较大", "重大", "特大"]
MAX_SEVERITY = "特大"

DEFAULT_CATEGORY = "通用"
DEFAULT_RULE: dict[str, str] = {"缺陷类别": DEFAULT_CATEGORY, "影响范围": SCOPE_WILDCARD, "严重等级": "一般"}

OVERDUE_DAYS = 30


def _ledger():
    """延迟导入安全台账服务，避免 defect ↔ ledger 两个模块互相 import 形成循环。"""
    from app.services.ledger import LedgerService
    return LedgerService()


class DefectService:
    # ---------------------------------------------------------------- 列表/统计

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        pipe: str | None = None,
        category: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("缺陷编号", ""))]
        if pipe:
            rows = [row for row in rows if pipe in str(row.get("所在管段", ""))]
        if category:
            rows = [row for row in rows if category in str(row.get("缺陷类别", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def stats(self) -> dict[str, int]:
        """缺陷状态指标；超期未闭环按发现日期超过 30 天且仍未闭环判定。"""
        rows = store.rows(MODULE)
        result = {"待定级": 0, "已定级": 0, "处置中": 0, "已闭环": 0, "已合并": 0, "超期未闭环": 0}
        cutoff = date.today() - timedelta(days=OVERDUE_DAYS)
        for row in rows:
            status = str(row.get("status", ""))
            if status in result:
                result[status] += 1
            if status in OPEN_STATUSES:
                found = self._parse_date(row.get("发现日期"))
                if found is not None and found <= cutoff:
                    result["超期未闭环"] += 1
        return result

    # ---------------------------------------------------------------- 定级口径规则

    def list_rules(self) -> list[dict[str, Any]]:
        rows = store.rows(RULE_MODULE)
        return sorted(rows, key=lambda row: (str(row.get("缺陷类别", "")), self._scope_index(row.get("影响范围"))))

    def create_rule(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        category = str(values.get("缺陷类别") or "").strip()
        scope = str(values.get("影响范围") or "").strip()
        severity = str(values.get("严重等级") or "").strip()
        if not category or not scope or not severity:
            return None, "口径规则不完整：缺陷类别、影响范围、严重等级都必须填写"
        if scope != SCOPE_WILDCARD and scope not in SCOPES:
            return None, f"影响范围「{scope}」不在可选口径内：{'、'.join(SCOPES)}（或填写「{SCOPE_WILDCARD}」兜底）"
        if severity not in SEVERITY_LEVELS:
            return None, f"严重等级「{severity}」不在允许等级内：{'、'.join(SEVERITY_LEVELS)}"
        rows = store.rows(RULE_MODULE)
        if any(row.get("缺陷类别") == category and row.get("影响范围") == scope for row in rows):
            return None, f"口径已存在：{category} / {scope}，直接在列表里调整等级即可"
        rule = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
                "缺陷类别": category, "影响范围": scope, "严重等级": severity}
        rows.append(rule)
        return rule, ""

    def update_rule(self, rule_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        rule = store.find(RULE_MODULE, rule_id)
        if rule is None:
            return None, f"定级口径 {rule_id} 不存在"
        severity = str(values.get("严重等级") or "").strip()
        if severity not in SEVERITY_LEVELS:
            return None, f"严重等级「{severity}」不在允许等级内：{'、'.join(SEVERITY_LEVELS)}"
        rule["严重等级"] = severity
        return rule, ""

    def delete_rule(self, rule_id: int) -> str:
        rows = store.rows(RULE_MODULE)
        rule = next((row for row in rows if int(row.get("id", 0)) == rule_id), None)
        if rule is None:
            return f"定级口径 {rule_id} 不存在"
        if rule.get("缺陷类别") == DEFAULT_CATEGORY and rule.get("影响范围") == SCOPE_WILDCARD:
            return "通用兜底口径不能删除，只可调整其等级"
        rows.remove(rule)
        return ""

    def match_rule(self, category: str, scope: str) -> dict[str, str]:
        """按 精确类别+精确范围 → 类别+通用 → 通用+范围 → 通用/通用 的顺序找口径。"""
        rows = store.rows(RULE_MODULE)

        def find(cat: str, scp: str) -> dict[str, str] | None:
            return next((row for row in rows if row.get("缺陷类别") == cat and row.get("影响范围") == scp), None)

        return (find(category, scope)
                or find(category, SCOPE_WILDCARD)
                or find(DEFAULT_CATEGORY, scope)
                or find(DEFAULT_CATEGORY, SCOPE_WILDCARD)
                or dict(DEFAULT_RULE))

    def preview_grade(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        category = str(values.get("缺陷类别") or "").strip()
        scope = str(values.get("影响范围") or "").strip()
        missing = [name for name, value in (("缺陷类别", category), ("影响范围", scope)) if not value]
        if missing:
            return None, f"试算定级缺少字段：{'、'.join(missing)}"
        if scope != SCOPE_WILDCARD and scope not in SCOPES:
            return None, f"影响范围「{scope}」不在可选口径内：{'、'.join(SCOPES)}"
        rule = self.match_rule(category, scope)
        return {
            "缺陷类别": category,
            "影响范围": scope,
            "建议严重等级": rule["严重等级"],
            "口径说明": f"{rule['缺陷类别']} / {rule['影响范围']} → {rule['严重等级']}"
                        + ("（兜底口径）" if rule.get("缺陷类别") == DEFAULT_CATEGORY else ""),
            "处置方案必填": rule["严重等级"] == MAX_SEVERITY,
        }, ""

    # ---------------------------------------------------------------- 登记/合并/定级

    def create_entry(
        self,
        values: dict[str, Any],
        *,
        ignore_duplicates: bool = False,
    ) -> tuple[dict[str, Any] | None, str, list[dict[str, Any]]]:
        """登记缺陷。

        返回（记录, 错误说明, 重复记录）：有重复且未明确忽略时不写入，交由前端提示合并。
        """
        values = {key: value for key, value in values.items() if not str(key).startswith("_")}
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}", []
        category = str(values["缺陷类别"]).strip()
        scope = str(values["影响范围"]).strip()
        if scope not in SCOPES:
            return None, f"影响范围「{scope}」不在可选口径内：{'、'.join(SCOPES)}", []

        rows = store.rows(MODULE)
        code = str(values["缺陷编号"]).strip()
        if any(str(row.get("缺陷编号", "")).strip() == code for row in rows):
            return None, f"缺陷编号「{code}」已登记，请勿重复建档", []

        duplicates = self.find_duplicates(str(values["所在管段"]).strip(), category)
        if duplicates and not ignore_duplicates:
            return None, "同一管段已存在同类未闭环缺陷，请确认是否合并后再登记", duplicates

        rule = self.match_rule(category, scope)
        suggested = rule["严重等级"]
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in [*REQUIRED_FIELDS, *EXTRA_FIELDS]:
            entry[field] = str(values.get(field) or "").strip()
        entry["建议严重等级"] = suggested
        entry["定级口径快照"] = f"{rule['缺陷类别']} / {rule['影响范围']} → {suggested}"
        entry["严重等级"] = ""
        entry["处置方案"] = ""
        entry["status"] = "待定级"
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, "", []

    def merge_into(self, target_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """把重复登记的内容作为补登信息并到已有缺陷上，不新增记录。"""
        target = store.find(MODULE, target_id)
        if target is None:
            return None, f"合并目标缺陷 {target_id} 不存在或已归档"
        if target.get("status") not in OPEN_STATUSES:
            return None, f"目标缺陷「{target.get('缺陷编号')}」已{target.get('status')}，不能再合并"
        parts = [f"重复登记编号 {str(values.get('缺陷编号') or '').strip() or '（未编号）'}"]
        for field in ["缺陷位置", "发现日期", "登记人员"]:
            value = str(values.get(field) or "").strip()
            if value:
                parts.append(f"{field}：{value}")
        note = "；".join(parts)
        target.setdefault("合并补登", [])
        target["合并补登"].append(note)
        return target, ""

    def find_duplicates(self, pipe: str, category: str) -> list[dict[str, Any]]:
        if not pipe or not category:
            return []
        return [
            row for row in store.rows(MODULE)
            if str(row.get("所在管段", "")).strip() == pipe
            and str(row.get("缺陷类别", "")).strip() == category
            and row.get("status") in OPEN_STATUSES
        ]

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        values = values or {}
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"缺陷记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于缺陷登记可执行范围"

        if action == "确认定级":
            return self._confirm_grade(entry, values)

        status = str(entry.get("status", ""))
        if action == "提交闭环":
            if status == "处置中":
                return None, "缺陷已在处置中，无需重复提交"
            if status != "已定级":
                return None, f"缺陷当前为「{status}」，需先确认定级才能提交处置"
            entry["status"] = "处置中"
            entry["pending"] = False
            _ledger().sync_status(entry)
            return entry, "缺陷已提交闭环处置"

        if action == "挂起缺陷":
            if status == "已闭环":
                return None, "缺陷已闭环，无需重复操作"
            if status not in ("已定级", "处置中"):
                return None, f"缺陷当前为「{status}」，定级后才能闭环"
            entry["status"] = "已闭环"
            entry["pending"] = False
            _ledger().sync_status(entry)
            return entry, "缺陷已挂起闭环"

        return None, f"动作「{action}」当前不可执行"

    def _confirm_grade(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        status = str(entry.get("status", ""))
        if status != "待定级":
            return None, f"缺陷当前状态为「{status}」，历史定级保持不变，不能重复确认定级"

        severity = str(values.get("严重等级") or entry.get("建议严重等级") or "").strip()
        if not severity:
            return None, "定级缺少字段：严重等级"
        if severity not in SEVERITY_LEVELS:
            return None, f"严重等级「{severity}」不在允许等级内：{'、'.join(SEVERITY_LEVELS)}"

        plan = str(values.get("处置方案") or "").strip()
        if severity == MAX_SEVERITY and not plan:
            return None, f"严重等级为上限「{MAX_SEVERITY}」，必须填写处置方案后才能确认定级"

        # 定级即冻结：等级、口径快照、处置方案一起固化，之后改口径不影响这条记录。
        entry["严重等级"] = severity
        entry["处置方案"] = plan
        entry["定级时间"] = date.today().isoformat()
        entry["定级口径快照"] = str(entry.get("定级口径快照") or "")
        entry["status"] = "已定级"
        entry["pending"] = True
        entry["abnormal"] = severity == MAX_SEVERITY
        _ledger().upsert_from_defect(entry)
        message = "缺陷定级已确认并汇入安全台账"
        if severity != entry.get("建议严重等级"):
            message += f"（人工调整为{severity}，口径建议为{entry.get('建议严重等级')}）"
        return entry, message

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        try:
            return date.fromisoformat(str(value)[:10])
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _scope_index(scope: Any) -> int:
        scope = str(scope)
        return SCOPES.index(scope) if scope in SCOPES else len(SCOPES)
