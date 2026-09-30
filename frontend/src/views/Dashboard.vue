<template>
  <section class="page">
    <header class="page-head">
      <div>
        <h2>运营概览</h2>
        <p class="page-desc">汇总各业务模块的关键指标，先看总量再看异常。</p>
      </div>
    </header>
    <div class="stat-row">
      <article v-for="card in cards" :key="card.label" class="stat-card">
        <span class="stat-label">{{ card.label }}</span>
        <strong class="stat-value">{{ card.value }}</strong>
      </article>
    </div>

    <h3 style="margin: 18px 0 4px">缺陷严重等级分布（与安全台账同口径）</h3>
    <div class="dist-row">
      <div v-for="item in severityDistribution" :key="item.label" class="dist-chip">
        <span :class="severityClass(item.label)">{{ item.label }}</span>
        <strong>{{ item.count }}</strong>
        <span class="page-desc">条</span>
      </div>
      <div class="dist-chip">
        <span>合计</span>
        <strong>{{ severityTotal }}</strong>
        <span class="page-desc">条已定级</span>
      </div>
    </div>

    <table class="data-table">
      <thead>
        <tr><th>业务模块</th><th>今日新增</th><th>待处理</th><th>异常量</th></tr>
      </thead>
      <tbody>
        <tr v-for="row in moduleRows" :key="row.name">
          <td>{{ row.name }}</td>
          <td>{{ row.created }}</td>
          <td>{{ row.pending }}</td>
          <td>{{ row.abnormal }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { fetchJson } from '@/api/client'

type Overview = {
  cards: { label: string; value: number }[]
  modules: { name: string; created: number; pending: number; abnormal: number }[]
  severity_distribution: { severity: string; label: string; count: number }[]
}

const severityOptions = ['一般', '较大', '重大', '特大']

function severityClass(value: string): string {
  const index = severityOptions.indexOf(value)
  return index >= 0 ? `badge badge-lv${index + 1}` : 'badge badge-muted'
}

const cards = ref<Overview['cards']>([])
const moduleRows = ref<Overview['modules']>([])
const severityDistribution = ref<Overview['severity_distribution']>([])
const severityTotal = computed(() =>
  severityDistribution.value.reduce((sum, item) => sum + item.count, 0),
)

onMounted(async () => {
  try {
    const payload = await fetchJson<Overview>('/api/overview')
    cards.value = payload.cards
    moduleRows.value = payload.modules
    severityDistribution.value = payload.severity_distribution ?? []
  } catch {
    cards.value = [{"label": "业务模块", "value": 0}, {"label": "今日新增", "value": 0}]
    moduleRows.value = [{"name": "管段档案", "created": 0, "pending": 0, "abnormal": 0}, {"name": "检查井", "created": 0, "pending": 0, "abnormal": 0}, {"name": "阀门井室", "created": 0, "pending": 0, "abnormal": 0}, {"name": "泵站设施", "created": 0, "pending": 0, "abnormal": 0}, {"name": "巡查任务", "created": 0, "pending": 0, "abnormal": 0}, {"name": "缺陷登记", "created": 0, "pending": 0, "abnormal": 0}, {"name": "内窥检测", "created": 0, "pending": 0, "abnormal": 0}, {"name": "修复施工", "created": 0, "pending": 0, "abnormal": 0}, {"name": "压力监测", "created": 0, "pending": 0, "abnormal": 0}, {"name": "流量监测", "created": 0, "pending": 0, "abnormal": 0}, {"name": "泄漏排查", "created": 0, "pending": 0, "abnormal": 0}, {"name": "清淤疏浚", "created": 0, "pending": 0, "abnormal": 0}, {"name": "养护材料", "created": 0, "pending": 0, "abnormal": 0}, {"name": "养护机械", "created": 0, "pending": 0, "abnormal": 0}, {"name": "占道许可", "created": 0, "pending": 0, "abnormal": 0}, {"name": "公众诉求", "created": 0, "pending": 0, "abnormal": 0}, {"name": "养护资金", "created": 0, "pending": 0, "abnormal": 0}, {"name": "管网档案", "created": 0, "pending": 0, "abnormal": 0}]
    severityDistribution.value = []
  }
})
</script>
