"""缺陷登记业务规则：定级口径维护、查重合并、定级校验与安全台账汇总。

口径调整的生效边界在这里收敛：
- 规则按「缺陷类别 × 影响范围」匹配，带版本号；登记时把当时的建议等级与规则版本
  快照到记录上，规则再怎么改，新规则只作用于之后登记的记录。
- 已定级记录的等级在确认定级时锁定，后续口径调整不再回改历史记录。
"""
from __future__ import annotations

import copy
from typing import Any

from app.store import store

MODULE = "defect"
RULE_MODULE = "_defect_grading_rule"

# 登记必填：影响范围是定级口径的输入，缺了无法给出建议等级。
REQUIRED_FIELDS = ["缺陷编号", "所在管段", "缺陷类别", "影响范围"]
OPTIONAL_FIELDS = ["缺陷位置", "发现日期", "登记人员"]
STATUS_ORDER = ["待定级", "已定级", "处置中", "已闭环"]
ACTION_RULES = {"确认定级": "已定级", "提交闭环": "处置中", "挂起缺陷": "已闭环"}
NEGATIVE_ACTIONS = ["挂起缺陷"]

# 等级由低到高，末位即等级上限；到上限的缺陷必须填处置方案才能定级。
SEVERITY_LEVELS = ["轻微", "一般", "较重", "严重"]
TOP_SEVERITY = SEVERITY_LEVELS[-1]
SCOPE_OPTIONS = ["局部", "管段", "片区"]
CATEGORY_OPTIONS = ["破裂", "变形", "错口", "脱节", "渗漏", "腐蚀", "沉积", "障碍物"]

# 默认定级口径。类别与范围都支持填「不限」作为通配：
# 精确匹配优先，其次类别通配，再次兜底（类别、范围都不限）。
DEFAULT_RULES: list[dict[str, Any]] = [
    {"id": 1, "缺陷类别": "破裂", "影响范围": "片区", "建议等级": "严重"},
    {"id": 2, "缺陷类别": "破裂", "影响范围": "管段", "建议等级": "较重"},
    {"id": 3, "缺陷类别": "破裂", "影响范围": "局部", "建议等级": "一般"},
    {"id": 4, "缺陷类别": "变形", "影响范围": "片区", "建议等级": "严重"},
    {"id": 5, "缺陷类别": "变形", "影响范围": "管段", "建议等级": "较重"},
    {"id": 6, "缺陷类别": "变形", "影响范围": "局部", "建议等级": "一般"},
    {"id": 7, "缺陷类别": "渗漏", "影响范围": "片区", "建议等级": "较重"},
    {"id": 8, "缺陷类别": "渗漏", "影响范围": "管段", "建议等级": "一般"},
    {"id": 9, "缺陷类别": "渗漏", "影响范围": "局部", "建议等级": "轻微"},
    {"id": 10, "缺陷类别": "沉积", "影响范围": "不限", "建议等级": "一般"},
    {"id": 11, "缺陷类别": "不限", "影响范围": "不限", "建议等级": "一般"},
]


def _norm(value: Any) -> str:
    return str(value or "").strip()


def severity_distribution() -> dict[str, int]:
    """安全台账与运营概览共用的严重等级分布口径。

    已定级（含处置中、已闭环）按定级时锁定的等级统计；待定级记录单列「待定级」，
    两者总数等于缺陷记录总数，台账和概览永远从这同一份函数取数。
    """
    dist = {level: 0 for level in SEVERITY_LEVELS}
    pending = 0
    for row in store.rows(MODULE):
        level = _norm(row.get("定级严重等级") or row.get("严重等级"))
        if row.get("status") == STATUS_ORDER[0] or level not in SEVERITY_LEVELS:
            pending += 1
            continue
        dist[level] += 1
    dist["待定级"] = pending
    return dist


class DefectService:
    def __init__(self) -> None:
        table = store.rows(RULE_MODULE)
        if not table:
            table.extend(copy.deepcopy(DEFAULT_RULES))

    # ---------- 定级规则 ----------
    def list_rules(self) -> list[dict[str, Any]]:
        return store.rows(RULE_MODULE)

    def rule_version(self) -> int:
        return int(store.meta(RULE_MODULE, "version", default=1))

    def _bump_version(self) -> None:
        store.set_meta(RULE_MODULE, "version", self.rule_version() + 1)

    def suggest(self, category: str, scope: str) -> tuple[str, int | None]:
        """按当前口径给出建议等级；没有匹配规则时返回空等级，由调用方提示。"""
        category, scope = _norm(category), _norm(scope)
        wildcard = None
        for rule in self.list_rules():
            rule_category, rule_scope = _norm(rule.get("缺陷类别")), _norm(rule.get("影响范围"))
            level = _norm(rule.get("建议等级"))
            if rule_category == category and rule_scope == scope:
                return level, rule.get("id")
            if rule_category == category and rule_scope == "不限":
                wildcard = (level, rule.get("id"))
            if rule_category == "不限" and rule_scope == "不限" and wildcard is None:
                wildcard = (level, rule.get("id"))
        if wildcard is not None:
            return wildcard
        return "", None

    def preview_rule(self, category: str, scope: str) -> dict[str, Any]:
        level, rule_id = self.suggest(category, scope)
        return {
            "缺陷类别": _norm(category),
            "影响范围": _norm(scope),
            "建议等级": level,
            "命中规则": rule_id,
            "规则版本": self.rule_version(),
            "需处置方案": level == TOP_SEVERITY,
        }

    def upsert_rule(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        category, scope, level = (
            _norm(values.get("缺陷类别")),
            _norm(values.get("影响范围")),
            _norm(values.get("建议等级")),
        )
        if not category:
            return None, "规则缺少缺陷类别（可填具体类别或「不限」）"
        if not scope:
            return None, "规则缺少影响范围（可填具体范围或「不限」）"
        if level not in SEVERITY_LEVELS:
            return None, f"建议等级须为：{'、'.join(SEVERITY_LEVELS)}"
        rows = self.list_rules()
        for rule in rows:  # 同一组类别 × 范围只保留一条，重复维护视为修改
            if _norm(rule.get("缺陷类别")) == category and _norm(rule.get("影响范围")) == scope:
                rule["建议等级"] = level
                self._bump_version()
                return rule, f"定级规则已更新（版本 {self.rule_version()}，仅对新登记记录生效）"
        rule = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "缺陷类别": category,
            "影响范围": scope,
            "建议等级": level,
        }
        rows.append(rule)
        self._bump_version()
        return rule, f"定级规则已新增（版本 {self.rule_version()}，仅对新登记记录生效）"

    def delete_rule(self, rule_id: int) -> str:
        rows = self.list_rules()
        for index, rule in enumerate(rows):
            if int(rule.get("id", 0)) == rule_id:
                rows.pop(index)
                self._bump_version()
                return f"定级规则 {rule_id} 已删除（版本 {self.rule_version()}，已锁定的历史等级不变）"
        return f"定级规则 {rule_id} 不存在"

    # ---------- 缺陷记录 ----------
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("缺陷编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def _find_duplicates(self, pipe: str, category: str) -> list[dict[str, Any]]:
        """同管段、同类别且尚未闭环的记录视为可合并的重复登记。"""
        return [
            row
            for row in store.rows(MODULE)
            if _norm(row.get("所在管段")) == pipe
            and _norm(row.get("缺陷类别")) == category
            and row.get("status") != STATUS_ORDER[-1]
        ]

    def create_entry(
        self, values: dict[str, Any], *, force: bool = False
    ) -> tuple[dict[str, Any] | None, str, dict[str, Any]]:
        """登记缺陷。

        返回 (记录, 错误信息, 附加数据)；查重命中且未强制登记时，附加数据里带候选记录。
        """
        missing = [field for field in REQUIRED_FIELDS if not _norm(values.get(field))]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}", {"missing": missing}

        category, scope = _norm(values.get("缺陷类别")), _norm(values.get("影响范围"))
        pipe = _norm(values.get("所在管段"))

        if scope not in SCOPE_OPTIONS:
            return None, f"影响范围须为：{'、'.join(SCOPE_OPTIONS)}", {}
        suggested, rule_id = self.suggest(category, scope)
        if not suggested:
            return None, f"当前定级口径缺少「{category} × {scope}」可命中的规则，请先维护定级口径", {}

        duplicates = self._find_duplicates(pipe, category)
        if duplicates and not force:
            return (
                None,
                f"管段「{pipe}」已有 {len(duplicates)} 条同类（{category}）未闭环缺陷，请确认是否合并到已有记录",
                {"candidates": duplicates},
            )

        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: _norm(values.get(field)) for field in REQUIRED_FIELDS})
        for field in OPTIONAL_FIELDS:
            entry[field] = _norm(values.get(field))
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        # 登记时刻的口径快照；之后规则调整不影响这条记录。
        entry["建议严重等级"] = suggested
        entry["建议规则版本"] = self.rule_version()
        entry["命中规则"] = rule_id
        entry["定级严重等级"] = ""
        entry["处置方案"] = ""
        entry["定级规则版本"] = None
        entry["合并记录"] = []
        entry["严重等级"] = ""
        entry["缺陷状态"] = STATUS_ORDER[0]
        rows.append(entry)
        return entry, "", {}

    def merge_entry(
        self, target_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        """放弃新登记，把本次发现合并进同管段同类的已有缺陷。"""
        target = store.find(MODULE, target_id)
        if target is None:
            return None, f"合并目标缺陷 {target_id} 不存在或已归档"
        if target.get("status") == STATUS_ORDER[-1]:
            return None, f"缺陷 {target_id} 已闭环，不能再合并登记，请直接新登记"
        merged: dict[str, Any] = {
            "缺陷编号": _norm(values.get("缺陷编号")),
            "缺陷位置": _norm(values.get("缺陷位置")),
            "发现日期": _norm(values.get("发现日期")),
            "登记人员": _norm(values.get("登记人员")),
        }
        target.setdefault("合并记录", []).append(merged)
        if merged["发现日期"] and not _norm(target.get("发现日期")):
            target["发现日期"] = merged["发现日期"]
        return target, f"已合并到缺陷 {target.get('缺陷编号')}（累计合并 {len(target['合并记录'])} 次）"

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"缺陷记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于缺陷登记可执行范围"
        values = values or {}

        if action == "确认定级":
            if entry.get("status") != STATUS_ORDER[0]:
                return None, f"缺陷已按历史口径定级为「{entry.get('定级严重等级')}」，等级保持不变，不能重复定级"
            level = _norm(values.get("严重等级") or entry.get("建议严重等级"))
            if level not in SEVERITY_LEVELS:
                return None, f"严重等级须为：{'、'.join(SEVERITY_LEVELS)}"
            plan = _norm(values.get("处置方案"))
            # 等级与处置方案冲突：到上限却没方案、没到上限却填了方案，都不允许保存。
            if level == TOP_SEVERITY and not plan:
                return None, f"严重等级已到上限「{TOP_SEVERITY}」，必须填写处置方案后才能确认定级"
            if level != TOP_SEVERITY and plan:
                return None, f"严重等级为「{level}」（未到上限）时不需填写处置方案，请清空方案或调整等级"
            entry["定级严重等级"] = level
            entry["严重等级"] = level
            entry["处置方案"] = plan
            entry["定级规则版本"] = self.rule_version()
            entry["定级日期"] = _norm(values.get("定级日期"))
            entry["定级人员"] = _norm(values.get("定级人员"))

        target = ACTION_RULES[action]
        entry["status"] = target
        entry["缺陷状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"缺陷记录已{action}"

    # ---------- 安全台账 ----------
    def ledger_entries(self) -> list[dict[str, Any]]:
        """只有定级后的缺陷进入安全台账，按严重等级由高到低排列。"""
        items = []
        for row in store.rows(MODULE):
            level = _norm(row.get("定级严重等级") or row.get("严重等级"))
            if row.get("status") == STATUS_ORDER[0] or level not in SEVERITY_LEVELS:
                continue
            items.append({
                "缺陷编号": row.get("缺陷编号"),
                "所在管段": row.get("所在管段"),
                "缺陷类别": row.get("缺陷类别"),
                "影响范围": row.get("影响范围"),
                "严重等级": level,
                "处置方案": row.get("处置方案", ""),
                "缺陷状态": row.get("status"),
                "定级日期": row.get("定级日期", ""),
                "定级规则版本": row.get("定级规则版本"),
            })
        items.sort(key=lambda item: SEVERITY_LEVELS.index(item["严重等级"]))
        return items

    def ledger(self) -> dict[str, Any]:
        dist = severity_distribution()
        items = self.ledger_entries()
        return {
            "items": items,
            "total": len(store.rows(MODULE)),
            "graded": len(items),
            "distribution": dist,
        }
