"""安全台账：归集已定级缺陷，并对外提供唯一的严重等级分布口径。

台账记录由缺陷定级动作写入，不在台账页手工新建；缺陷状态流转时台账同步状态。
台账页和运营概览的严重等级分布都调用 severity_distribution()，避免两处各算各的。
"""
from __future__ import annotations

from typing import Any

from app.services.defect import SEVERITY_LEVELS
from app.store import store

MODULE = "ledger"
LEDGER_FIELDS = ["缺陷编号", "所在管段", "缺陷类别", "影响范围", "严重等级", "处置方案",
                 "定级时间", "发现日期", "登记人员", "台账状态"]


class LedgerService:
    def list_entries(
        self,
        *,
        severity: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if severity:
            rows = [row for row in rows if row.get("严重等级") == severity]
        if status:
            rows = [row for row in rows if row.get("台账状态") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def upsert_from_defect(self, defect: dict[str, Any]) -> dict[str, Any]:
        rows = store.rows(MODULE)
        entry = next((row for row in rows if row.get("缺陷编号") == defect.get("缺陷编号")), None)
        created = entry is None
        if entry is None:
            entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
            rows.append(entry)
        for field in LEDGER_FIELDS:
            if field in defect:
                entry[field] = defect[field]
        entry["台账状态"] = str(defect.get("status") or "")
        entry["来源缺陷id"] = defect.get("id")
        entry["pending"] = defect.get("status") != "已闭环"
        entry["abnormal"] = defect.get("严重等级") == "特大"
        entry["_created"] = created
        return entry

    def sync_status(self, defect: dict[str, Any]) -> None:
        """缺陷后续状态流转（处置中、闭环）时同步台账，不新增记录。"""
        for row in store.rows(MODULE):
            if row.get("来源缺陷id") == defect.get("id"):
                row["台账状态"] = str(defect.get("status") or "")
                row["pending"] = defect.get("status") != "已闭环"

    def severity_distribution(self) -> list[dict[str, str | int]]:
        """安全台账与运营概览共用：只统计台账内已定级缺陷的当前等级。"""
        rows = store.rows(MODULE)
        counts = {level: 0 for level in SEVERITY_LEVELS}
        for row in rows:
            level = str(row.get("严重等级", ""))
            if level in counts:
                counts[level] += 1
        return [{"severity": level, "label": level, "count": counts[level]} for level in SEVERITY_LEVELS]
