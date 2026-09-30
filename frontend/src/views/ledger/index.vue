<template>
  <section class="page" data-module="ledger">
    <header class="page-head">
      <div>
        <h2>安全台账</h2>
        <p class="page-desc">
          归集已定级缺陷，记录严重等级、处置方案与处置状态。
          台账与运营概览的严重等级分布取自同一份后端口径（/api/ledger/distribution）。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="exportRows">导出安全台账</button>
      </div>
    </header>

    <div class="dist-row">
      <div v-for="item in distribution" :key="item.label" class="dist-chip">
        <span :class="severityClass(item.label)">{{ item.label }}</span>
        <strong>{{ item.count }}</strong>
        <span class="page-desc">条</span>
      </div>
      <div class="dist-chip">
        <span>合计</span>
        <strong>{{ totalGraded }}</strong>
        <span class="page-desc">条已定级</span>
      </div>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>严重等级</span>
        <select v-model="filters.severity">
          <option value="">全部</option>
          <option v-for="lv in severityOptions" :key="lv" :value="lv">{{ lv }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>台账状态</span>
        <select v-model="filters.status">
          <option value="">全部</option>
          <option value="已定级">已定级</option>
          <option value="处置中">处置中</option>
          <option value="已闭环">已闭环</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columnDefs" :key="column.key">
            <template v-if="column.badge">
              <span :class="severityClass(row[column.key])">{{ row[column.key] ?? '—' }}</span>
            </template>
            <template v-else>{{ cellText(row[column.key]) }}</template>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length" class="empty-state">暂无台账记录，缺陷确认定级后自动汇入</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条台账记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type DistributionItem = { severity: string; label: string; count: number }

const ENDPOINT = '/api/ledger'
const severityOptions = ['一般', '较大', '重大', '特大']

const columnDefs = [
  { key: '缺陷编号' },
  { key: '所在管段' },
  { key: '缺陷类别' },
  { key: '影响范围' },
  { key: '严重等级', badge: true },
  { key: '处置方案' },
  { key: '定级时间' },
  { key: '发现日期' },
  { key: '登记人员' },
  { key: '台账状态' },
]
const columns = columnDefs.map((c) => c.key)

const rows = ref<Row[]>([])
const total = ref(0)
const totalGraded = ref(0)
const distribution = ref<DistributionItem[]>([])
const errorMessage = ref('')
const filters = ref<Record<string, string>>({ severity: '', status: '' })

function severityClass(value: unknown): string {
  const index = severityOptions.indexOf(String(value))
  return index >= 0 ? `badge badge-lv${index + 1}` : 'badge badge-muted'
}

function cellText(value: unknown): string {
  return value === null || value === undefined || value === '' ? '—' : String(value)
}

function resetFilters() {
  filters.value = { severity: '', status: '' }
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function reloadDistribution() {
  const response = await request(`${ENDPOINT}/distribution`)
  if (!response.ok) return
  const payload = await response.json()
  distribution.value = payload.items ?? []
  totalGraded.value = payload.total ?? 0
}

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters.value)) {
    if (value) params.set(key, value)
  }
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) {
      throw new Error('安全台账读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '安全台账读取失败'
  }
  // 分布始终取全量口径，不受当前筛选影响，保证与运营概览一致
  await reloadDistribution()
}

onMounted(reload)
</script>
