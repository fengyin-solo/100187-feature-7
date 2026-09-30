<template>
  <section class="page" data-module="defect">
    <header class="page-head">
      <div>
        <h2>缺陷登记管理</h2>
        <p class="page-desc">
          按定级口径（缺陷类别 × 影响范围）给出建议严重等级；口径可维护，调整后只对新登记记录生效，
          历史定级保持不变。同管段同类缺陷重复登记会提示合并。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记缺陷记录</button>
        <button class="btn" type="button" @click="openRules">定级口径管理</button>
        <button class="btn" type="button" @click="exportRows">导出缺陷登记清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value" :class="{ 'error-text': item.danger }">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field.key" class="filter-item">
        <span>{{ field.label }}</span>
        <input v-model="filters[field.key]" :placeholder="`按${field.label}检索`" />
      </label>
      <label class="filter-item">
        <span>状态</span>
        <select v-model="filters.status">
          <option value="">全部</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columnDefs" :key="column.key">
            <template v-if="column.badge">
              <span v-if="row[column.key]" :class="severityClass(row[column.key])">{{ row[column.key] }}</span>
              <span v-else class="badge badge-muted">未定级</span>
            </template>
            <template v-else>{{ displayCell(row, column.key) }}</template>
          </td>
          <td class="row-actions">
            <button
              v-for="action in availableActions(row)"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无缺陷登记数据，可先登记缺陷记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条缺陷登记记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 登记缺陷（含同管段同类重复时的合并提示） -->
    <div v-if="createOpen" class="modal-mask" @click.self="closeCreate">
      <div class="modal">
        <div class="modal-head">
          <h3>登记缺陷记录</h3>
          <button class="modal-close" type="button" @click="closeCreate">×</button>
        </div>

        <div v-if="createError" class="modal-tip error">{{ createError }}</div>
        <div v-if="duplicates.length" class="modal-tip warn">
          同一管段「{{ form.所在管段 }}」已存在 {{ duplicates.length }} 条同类（{{ form.缺陷类别 }}）未闭环缺陷，建议合并：
          <ul class="dup-list">
            <li v-for="dup in duplicates" :key="String(dup.id)">
              {{ dup.缺陷编号 }} · 当前状态 {{ dup.status }}
              <button class="link" type="button" @click="mergeInto(dup)">合并到这条</button>
            </li>
          </ul>
        </div>
        <div v-else-if="previewText" class="modal-tip info">
          当前口径：{{ previewText }}<template v-if="previewPlanRequired">；该等级为上限，定级时必须填写处置方案</template>
        </div>

        <div class="form-grid">
          <div class="form-item">
            <label>缺陷编号 <span class="req">*</span></label>
            <input v-model="form.缺陷编号" placeholder="如 DEFE-0101" />
          </div>
          <div class="form-item">
            <label>所在管段 <span class="req">*</span></label>
            <input v-model="form.所在管段" placeholder="如 WS-玉泉路干管" />
          </div>
          <div class="form-item">
            <label>缺陷类别 <span class="req">*</span></label>
            <input v-model="form.缺陷类别" list="defect-category-list" placeholder="破裂 / 变形 / 错口 / 渗漏 / 腐蚀 / 沉积" @change="schedulePreview" />
            <datalist id="defect-category-list">
              <option v-for="cat in categoryHints" :key="cat" :value="cat" />
            </datalist>
          </div>
          <div class="form-item">
            <label>影响范围 <span class="req">*</span></label>
            <select v-model="form.影响范围" @change="schedulePreview">
              <option value="" disabled>请选择影响范围</option>
              <option v-for="scope in scopeOptions" :key="scope" :value="scope">{{ scope }}</option>
            </select>
          </div>
          <div class="form-item">
            <label>缺陷位置</label>
            <input v-model="form.缺陷位置" placeholder="如 距3号井下游12米" />
          </div>
          <div class="form-item">
            <label>发现日期</label>
            <input v-model="form.发现日期" type="date" />
          </div>
          <div class="form-item">
            <label>登记人员</label>
            <input v-model="form.登记人员" />
          </div>
        </div>

        <div class="modal-foot">
          <button class="btn" type="button" @click="previewGrade(false)">按当前口径试算</button>
          <button class="btn ghost" type="button" @click="closeCreate">取消</button>
          <button class="btn primary" type="button" @click="submitCreate">保存登记</button>
        </div>
      </div>
    </div>

    <!-- 确认定级：等级默认取口径建议，可人工调整；到上限必须有处置方案 -->
    <div v-if="gradeTarget" class="modal-mask" @click.self="gradeTarget = null">
      <div class="modal">
        <div class="modal-head">
          <h3>确认定级 · {{ gradeTarget.缺陷编号 }}</h3>
          <button class="modal-close" type="button" @click="gradeTarget = null">×</button>
        </div>

        <div class="modal-tip info">
          口径建议：<span :class="severityClass(gradeTarget.建议严重等级)">{{ gradeTarget.建议严重等级 || '—' }}</span>
          （{{ gradeTarget.定级口径快照 || '无快照' }}）。确认后等级冻结，之后调整口径不影响本条。
        </div>
        <div v-if="gradeError" class="modal-tip error">{{ gradeError }}</div>

        <div class="form-grid">
          <div class="form-item">
            <label>严重等级 <span class="req">*</span></label>
            <select v-model="gradeForm.严重等级">
              <option v-for="lv in severityOptions" :key="lv" :value="lv">{{ lv }}</option>
            </select>
          </div>
          <div class="form-item full">
            <label>处置方案<span v-if="gradeForm.严重等级 === maxSeverity" class="req"> *（上限等级必填）</span></label>
            <textarea
              v-model="gradeForm.处置方案"
              :placeholder="gradeForm.严重等级 === maxSeverity ? '特大缺陷必须填写处置方案：封堵、导排、开挖更换、修复时限等' : '封堵、导排、开挖更换、修复时限等具体安排（一般等级可留空）'"
            />
          </div>
        </div>

        <div class="modal-foot">
          <button class="btn ghost" type="button" @click="gradeTarget = null">取消</button>
          <button class="btn primary" type="button" @click="submitGrade">确认定级并汇入安全台账</button>
        </div>
      </div>
    </div>

    <!-- 定级口径管理 -->
    <div v-if="rulesOpen" class="modal-mask" @click.self="rulesOpen = false">
      <div class="modal wide">
        <div class="modal-head">
          <h3>定级口径管理（缺陷类别 × 影响范围 → 严重等级）</h3>
          <button class="modal-close" type="button" @click="rulesOpen = false">×</button>
        </div>
        <p class="page-desc">调整口径后只影响之后新登记的缺陷；已定级历史记录保持原等级不变。「通用 / 通用」为兜底口径，不可删除。</p>
        <div v-if="rulesError" class="modal-tip error">{{ rulesError }}</div>

        <table class="rules-table">
          <thead>
            <tr><th>缺陷类别</th><th>影响范围</th><th>严重等级</th><th style="width: 90px">操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="rule in rules" :key="String(rule.id)">
              <td>{{ rule.缺陷类别 }}</td>
              <td>{{ rule.影响范围 }}</td>
              <td>
                <select :value="rule.严重等级" @change="updateRule(rule, ($event.target as HTMLSelectElement).value)">
                  <option v-for="lv in severityOptions" :key="lv" :value="lv">{{ lv }}</option>
                </select>
              </td>
              <td>
                <button v-if="!(rule.缺陷类别 === '通用' && rule.影响范围 === '通用')" class="link error-text" type="button" @click="deleteRule(rule)">删除</button>
                <span v-else class="badge badge-muted">兜底</span>
              </td>
            </tr>
          </tbody>
        </table>

        <h4 style="margin: 14px 0 6px">新增口径</h4>
        <div class="form-grid">
          <div class="form-item">
            <label>缺陷类别</label>
            <input v-model="newRule.缺陷类别" list="defect-category-list" placeholder="可填已有类别或新类别" />
          </div>
          <div class="form-item">
            <label>影响范围</label>
            <select v-model="newRule.影响范围">
              <option value="通用">通用（该类别下各范围兜底）</option>
              <option v-for="scope in scopeOptions" :key="scope" :value="scope">{{ scope }}</option>
            </select>
          </div>
          <div class="form-item">
            <label>严重等级</label>
            <select v-model="newRule.严重等级">
              <option v-for="lv in severityOptions" :key="lv" :value="lv">{{ lv }}</option>
            </select>
          </div>
          <div class="form-item">
            <label>&nbsp;</label>
            <button class="btn primary" type="button" @click="createRule">新增口径</button>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | string[] | null>
type Duplicate = { id: number; 缺陷编号: string; 所在管段: string; 缺陷类别: string; status: string }
type Rule = { id: number; 缺陷类别: string; 影响范围: string; 严重等级: string }

const ENDPOINT = '/api/defect'
const maxSeverity = '特大'
const statuses = ['待定级', '已定级', '处置中', '已闭环', '已合并']
const scopeOptions = ['单点局部', '支管接入', '干管交汇', '片区影响']
const severityOptions = ['一般', '较大', '重大', '特大']
const categoryHints = ['破裂', '变形', '错口', '渗漏', '腐蚀', '沉积']

const columnDefs = [
  { key: '缺陷编号' },
  { key: '所在管段' },
  { key: '缺陷类别' },
  { key: '影响范围' },
  { key: '缺陷位置' },
  { key: '严重等级', badge: true },
  { key: '处置方案' },
  { key: '发现日期' },
  { key: '登记人员' },
  { key: 'status', label: '缺陷状态' },
]
const columns = columnDefs.map((c) => c.label ?? c.key)

const emptyForm = () => ({
  缺陷编号: '', 所在管段: '', 缺陷类别: '', 影响范围: '',
  缺陷位置: '', 发现日期: '', 登记人员: '',
})

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({ 缺陷编号: '', 所在管段: '', 缺陷类别: '', status: '' })
const filterFields = [
  { key: '缺陷编号', label: '缺陷编号' },
  { key: '所在管段', label: '所在管段' },
  { key: '缺陷类别', label: '缺陷类别' },
]
const stats = ref([
  { label: '待定级缺陷', value: 0, danger: false },
  { label: '处置中缺陷', value: 0, danger: false },
  { label: '已闭环', value: 0, danger: false },
  { label: '超期未闭环', value: 0, danger: true },
])

// 登记弹窗
const createOpen = ref(false)
const form = ref(emptyForm())
const createError = ref('')
const duplicates = ref<Duplicate[]>([])
const previewText = ref('')
const previewPlanRequired = ref(false)
let previewTimer: ReturnType<typeof setTimeout> | undefined

// 定级弹窗
const gradeTarget = ref<Row | null>(null)
const gradeForm = ref({ 严重等级: '', 处置方案: '' })
const gradeError = ref('')

// 口径弹窗
const rulesOpen = ref(false)
const rules = ref<Rule[]>([])
const rulesError = ref('')
const newRule = ref({ 缺陷类别: '', 影响范围: '通用', 严重等级: '一般' })

function severityClass(value: unknown): string {
  const index = severityOptions.indexOf(String(value))
  return index >= 0 ? `badge badge-lv${index + 1}` : 'badge badge-muted'
}

function displayCell(row: Row, key: string): string {
  const value = row[key]
  if (key === '处置方案') {
    const text = String(value ?? '')
    return text || '—'
  }
  if (Array.isArray(value)) {
    return `含 ${value.length} 条合并补登`
  }
  return value === null || value === undefined || value === '' ? '—' : String(value)
}

function availableActions(row: Row): string[] {
  switch (row.status) {
    case '待定级':
      return ['确认定级']
    case '已定级':
      return ['提交闭环', '挂起缺陷']
    case '处置中':
      return ['挂起缺陷']
    default:
      return []
  }
}

function resetFilters() {
  filters.value = { 缺陷编号: '', 所在管段: '', 缺陷类别: '', status: '' }
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

// --------------------------------------------------------------- 登记/试算/合并

function openCreate() {
  form.value = emptyForm()
  createError.value = ''
  duplicates.value = []
  previewText.value = ''
  previewPlanRequired.value = false
  createOpen.value = true
}

function closeCreate() {
  createOpen.value = false
}

function schedulePreview() {
  clearTimeout(previewTimer)
  previewTimer = setTimeout(() => void previewGrade(true), 250)
}

async function previewGrade(silent = false) {
  if (!form.value.缺陷类别 || !form.value.影响范围) {
    if (!silent) createError.value = '试算缺少字段：缺陷类别、影响范围'
    return
  }
  const response = await request(`${ENDPOINT}/grade-preview`, {
    method: 'POST',
    body: JSON.stringify({ values: { 缺陷类别: form.value.缺陷类别, 影响范围: form.value.影响范围 } }),
  })
  const payload = await response.json()
  if (!response.ok || !payload.ok) {
    createError.value = payload.message ?? '试算失败'
    previewText.value = ''
    return
  }
  createError.value = ''
  previewText.value = payload.message
  previewPlanRequired.value = Boolean(payload.entry?.处置方案必填)
}

async function submitCreate() {
  createError.value = ''
  const response = await request(ENDPOINT, {
    method: 'POST',
    body: JSON.stringify({ values: { ...form.value } }),
  })
  const payload = await response.json()
  if (payload.ok) {
    createOpen.value = false
    await Promise.all([reload(), reloadStats()])
    return
  }
  duplicates.value = payload.duplicates ?? []
  createError.value = duplicates.value.length
    ? payload.message
    : payload.message ?? '缺陷记录未保存'
}

async function mergeInto(target: Duplicate) {
  createError.value = ''
  const response = await request(`${ENDPOINT}/${target.id}/merge`, {
    method: 'POST',
    body: JSON.stringify({ values: { ...form.value } }),
  })
  const payload = await response.json()
  if (!payload.ok) {
    createError.value = payload.message ?? '合并失败'
    return
  }
  createOpen.value = false
  errorMessage.value = payload.message
  await Promise.all([reload(), reloadStats()])
}

// --------------------------------------------------------------- 定级

function runAction(action: string, row: Row) {
  errorMessage.value = ''
  if (action === '确认定级') {
    gradeTarget.value = row
    gradeForm.value = {
      严重等级: String(row.建议严重等级 ?? ''),
      处置方案: '',
    }
    gradeError.value = ''
    return
  }
  void simpleAction(action, row)
}

async function simpleAction(action: string, row: Row) {
  const response = await request(`${ENDPOINT}/${row.id}/actions`, {
    method: 'POST',
    body: JSON.stringify({ values: { action } }),
  })
  const payload = await response.json()
  if (!payload.ok) {
    errorMessage.value = payload.message ?? '操作未生效'
    return
  }
  errorMessage.value = payload.message
  await Promise.all([reload(), reloadStats()])
}

async function submitGrade() {
  gradeError.value = ''
  if (gradeForm.value.严重等级 === maxSeverity && !gradeForm.value.处置方案.trim()) {
    gradeError.value = '严重等级为上限「特大」，必须填写处置方案后才能确认定级'
    return
  }
  const target = gradeTarget.value
  if (!target) return
  const response = await request(`${ENDPOINT}/${target.id}/actions`, {
    method: 'POST',
    body: JSON.stringify({ values: { action: '确认定级', ...gradeForm.value } }),
  })
  const payload = await response.json()
  if (!payload.ok) {
    gradeError.value = payload.message ?? '定级未保存'
    return
  }
  gradeTarget.value = null
  errorMessage.value = payload.message
  await Promise.all([reload(), reloadStats()])
}

// --------------------------------------------------------------- 口径维护

async function openRules() {
  rulesOpen.value = true
  rulesError.value = ''
  await loadRules()
}

async function loadRules() {
  const response = await request(`${ENDPOINT}/rules`)
  const payload = await response.json()
  rules.value = payload.items ?? []
}

async function updateRule(rule: Rule, severity: string) {
  rulesError.value = ''
  const response = await request(`${ENDPOINT}/rules/${rule.id}`, {
    method: 'PUT',
    body: JSON.stringify({ values: { 严重等级: severity } }),
  })
  const payload = await response.json()
  if (!payload.ok) {
    rulesError.value = payload.message ?? '口径调整失败'
    await loadRules()
    return
  }
  rulesError.value = payload.message
  await loadRules()
}

async function deleteRule(rule: Rule) {
  rulesError.value = ''
  const response = await request(`${ENDPOINT}/rules/${rule.id}`, { method: 'DELETE' })
  const payload = await response.json()
  if (!payload.ok) {
    rulesError.value = payload.message ?? '口径删除失败'
    return
  }
  await loadRules()
}

async function createRule() {
  rulesError.value = ''
  if (!newRule.value.缺陷类别.trim()) {
    rulesError.value = '新增口径缺少字段：缺陷类别'
    return
  }
  const response = await request(`${ENDPOINT}/rules`, {
    method: 'POST',
    body: JSON.stringify({ values: { ...newRule.value } }),
  })
  const payload = await response.json()
  if (!payload.ok) {
    rulesError.value = payload.message
    return
  }
  newRule.value = { 缺陷类别: '', 影响范围: '通用', 严重等级: '一般' }
  await loadRules()
}

// --------------------------------------------------------------- 列表/指标

async function reloadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    const payload = await response.json()
    stats.value[0].value = payload.待定级 ?? 0
    stats.value[1].value = payload.处置中 ?? 0
    stats.value[2].value = payload.已闭环 ?? 0
    stats.value[3].value = payload.超期未闭环 ?? 0
  } catch {
    // 指标读不出来不阻塞列表，卡片保持 0
  }
}

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  const paramMap: Record<string, string> = {
    缺陷编号: 'keyword',
    所在管段: 'pipe',
    缺陷类别: 'category',
    status: 'status',
  }
  for (const [key, value] of Object.entries(filters.value)) {
    if (value && paramMap[key]) params.set(paramMap[key], value)
  }
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) {
      throw new Error('缺陷记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '缺陷登记列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void reloadStats()
})
</script>
