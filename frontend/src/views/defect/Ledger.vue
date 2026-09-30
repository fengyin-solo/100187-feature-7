<template>
  <section class="page" data-module="defect-ledger">
    <header class="page-head">
      <div>
        <h2>安全台账</h2>
        <p class="page-desc">汇总缺陷定级结果：仅已定级缺陷入台账；严重等级分布与运营概览取自同一口径，数字保持一致。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn ghost" to="/defect">返回缺陷登记</RouterLink>
        <button class="btn" type="button" @click="reload">刷新台账</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in distCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value" :class="item.danger ? 'danger-text' : ''">{{ item.value }}</strong>
      </article>
    </div>

    <p class="page-desc">
      台账合计 {{ graded }} 条已定级缺陷，另有 {{ distribution['待定级'] ?? 0 }} 条待定级未入台账，
      缺陷总数 {{ total }} 条（各等级数量之和等于总数）。
    </p>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, index) in items" :key="`${row['缺陷编号']}-${index}`">
          <td v-for="column in columns" :key="column">{{ row[column] || '—' }}</td>
        </tr>
        <tr v-if="!items.length">
          <td :colspan="columns.length" class="empty-state">暂无已定级缺陷，台账为空</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>数据口径：缺陷定级确认时锁定等级，历史定级不随后续口径调整变化</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

const ENDPOINT = '/api/defect/ledger'
const columns = ['缺陷编号', '所在管段', '缺陷类别', '影响范围', '严重等级', '处置方案', '缺陷状态', '定级日期', '定级规则版本']

type LedgerRow = Record<string, string | number | null>
type Distribution = Record<string, number>

const items = ref<LedgerRow[]>([])
const total = ref(0)
const graded = ref(0)
const distribution = ref<Distribution>({})
const errorMessage = ref('')

const distOrder = ['严重', '较重', '一般', '轻微', '待定级']
const distCards = computed(() =>
  distOrder.map((label) => ({
    label: label === '待定级' ? '待定级（未入台账）' : label,
    value: distribution.value[label] ?? 0,
    danger: label === '严重',
  })),
)

async function reload() {
  errorMessage.value = ''
  try {
    const response = await request(ENDPOINT)
    if (!response.ok) throw new Error('安全台账读取失败')
    const payload = await response.json()
    items.value = payload.items ?? []
    total.value = payload.total ?? 0
    graded.value = payload.graded ?? 0
    distribution.value = payload.distribution ?? {}
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '安全台账读取失败'
  }
}

onMounted(reload)
</script>
