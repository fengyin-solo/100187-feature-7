<template>
  <section class="page" data-module="defect">
    <header class="page-head">
      <div>
        <h2>缺陷登记管理</h2>
        <p class="page-desc">定级口径按缺陷类别与影响范围维护：登记时给出建议严重等级，到上限「{{ topSeverity }}」的缺陷必须填写处置方案才能确认定级。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记缺陷记录</button>
        <button class="btn" type="button" @click="openRules">维护定级口径</button>
        <RouterLink class="btn ghost" to="/defect-ledger">查看安全台账</RouterLink>
        <button class="btn ghost" type="button" @click="exportRows">导出清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value" :class="item.danger ? 'danger-text' : ''">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>缺陷编号</span>
        <input v-model="keyword" placeholder="按缺陷编号检索" />
      </label>
      <label class="filter-item">
        <span>缺陷状态</span>
        <select v-model="statusFilter">
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
          <td v-for="column in columns" :key="column">
            <template v-if="column === '严重等级'">
              <span v-if="row[column]">{{ row[column] }}</span>
              <span v-else-if="row['建议严重等级']" class="hint-text">建议 {{ row['建议严重等级'] }}</span>
              <span v-else>—</span>
            </template>
            <template v-else-if="column === '缺陷状态'">
              {{ row[column] }}
              <span v-if="mergedCount(row)" class="merge-badge">含合并 {{ mergedCount(row) }}</span>
            </template>
            <template v-else>{{ row[column] || '—' }}</template>
          </td>
          <td class="row-actions">
            <button v-if="row.status === '待定级'" class="link" type="button" @click="openGrade(row)">确认定级</button>
            <button v-if="row.status === '已定级'" class="link" type="button" @click="runAction('提交闭环', row)">提交闭环</button>
            <button v-if="row.status !== '已闭环'" class="link danger" type="button" @click="runAction('挂起缺陷', row)">挂起缺陷</button>
            <span v-if="row.status === '已闭环'" class="hint-text">已闭环</span>
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

    <!-- 登记缺陷 -->
    <div v-if="createVisible" class="modal-mask" @click.self="closeCreate">
      <div class="modal">
        <h3>登记缺陷记录</h3>
        <div class="form-grid">
          <label v-for="field in createFields" :key="field.key" class="form-item">
            <span>{{ field.label }}<em v-if="field.required" class="required">*</em></span>
            <select v-if="field.type === 'select'" v-model="createForm[field.key]">
              <option value="">请选择</option>
              <option v-for="opt in field.options" :key="opt" :value="opt">{{ opt }}</option>
            </select>
            <input v-else v-model="createForm[field.key]" :type="field.type === 'date' ? 'date' : 'text'" />
          </label>
        </div>
        <div class="suggest-box">
          <template v-if="createPreview">
            <strong>当前口径建议等级：{{ createPreview['建议等级'] || '无匹配规则' }}</strong>
            <span v-if="createPreview['需处置方案']" class="danger-text">（到上限，定级时必须填写处置方案）</span>
            <span class="hint-text">规则版本 v{{ createPreview['规则版本'] }}</span>
          </template>
          <span v-else class="hint-text">选择缺陷类别与影响范围后自动试算建议等级</span>
        </div>
        <p v-if="duplicates.length" class="dup-box">
          同一管段已有 {{ duplicates.length }} 条同类未闭环缺陷：
          <span v-for="d in duplicates" :key="String(d.id)" class="dup-item">
            {{ d['缺陷编号'] }}（{{ d['缺陷位置'] || '位置未填' }}，{{ d.status }}）
          </span>
          建议合并，不要重复登记。
        </p>
        <p v-if="createError" class="error-text">{{ createError }}</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="closeCreate">取消</button>
          <button v-if="duplicates.length" class="btn" type="button" @click="mergeDuplicate">合并到已有记录</button>
          <button v-if="duplicates.length" class="btn" type="button" @click="submitCreate(true)">仍要独立登记</button>
          <button v-else class="btn primary" type="button" @click="submitCreate(false)">提交登记</button>
        </div>
      </div>
    </div>

    <!-- 确认定级 -->
    <div v-if="gradeVisible" class="modal-mask" @click.self="closeGrade">
      <div class="modal">
        <h3>确认定级 · {{ gradeTarget?.['缺陷编号'] }}</h3>
        <p class="hint-text">
          {{ gradeTarget?.['所在管段'] }} · {{ gradeTarget?.['缺陷类别'] }} · {{ gradeTarget?.['影响范围'] }}，
          登记时口径建议：<strong>{{ gradeTarget?.['建议严重等级'] }}</strong>（v{{ gradeTarget?.['建议规则版本'] }}）
        </p>
        <div class="form-grid">
          <label class="form-item">
            <span>严重等级<em class="required">*</em></span>
            <select v-model="gradeForm['严重等级']">
              <option value="">请选择</option>
              <option v-for="level in severityLevels" :key="level" :value="level">{{ level }}</option>
            </select>
          </label>
          <label class="form-item">
            <span>定级日期</span>
            <input v-model="gradeForm['定级日期']" type="date" />
          </label>
          <label class="form-item">
            <span>定级人员</span>
            <input v-model="gradeForm['定级人员']" type="text" />
          </label>
          <label class="form-item full">
            <span>处置方案<em v-if="gradeForm['严重等级'] === topSeverity" class="required">*</em></span>
            <textarea v-model="gradeForm['处置方案']" rows="3" placeholder="严重等级为上限时必填，其他等级不填"></textarea>
          </label>
        </div>
        <p class="hint-text">确认后等级按定级时口径锁定；之后口径调整只影响新登记记录，历史等级不变。</p>
        <p v-if="gradeError" class="error-text">{{ gradeError }}</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="closeGrade">取消</button>
          <button class="btn primary" type="button" @click="submitGrade">确认定级</button>
        </div>
      </div>
    </div>

    <!-- 定级口径规则 -->
    <div v-if="rulesVisible" class="modal-mask wide" @click.self="closeRules">
      <div class="modal">
        <h3>定级口径维护 <span class="hint-text">（当前版本 v{{ ruleVersion }}，调整后只对新登记记录生效）</span></h3>
        <table class="data-table rule-table">
          <thead>
            <tr><th>规则号</th><th>缺陷类别</th><th>影响范围</th><th>建议等级</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="rule in rules" :key="String(rule.id)">
              <td>{{ rule.id }}</td>
              <td>{{ rule['缺陷类别'] }}</td>
              <td>{{ rule['影响范围'] }}</td>
              <td>{{ rule['建议等级'] }}</td>
              <td><button class="link danger" type="button" @click="deleteRule(rule.id)">删除</button></td>
            </tr>
          </tbody>
        </table>
        <h4>新增 / 调整规则（同「类别 × 范围」重复提交即调整）</h4>
        <div class="form-grid">
          <label class="form-item">
            <span>缺陷类别（可填「不限」）</span>
            <input v-model="ruleForm['缺陷类别']" list="category-options" placeholder="如 破裂 / 不限" />
            <datalist id="category-options">
              <option v-for="c in categoryOptions" :key="c" :value="c" />
              <option value="不限" />
            </datalist>
          </label>
          <label class="form-item">
            <span>影响范围（可填「不限」）</span>
            <select v-model="ruleForm['影响范围']">
              <option value="">请选择</option>
              <option v-for="s in scopeOptions.concat(['不限'])" :key="s" :value="s">{{ s }}</option>
            </select>
          </label>
          <label class="form-item">
            <span>建议等级</span>
            <select v-model="ruleForm['建议等级']">
              <option value="">请选择</option>
              <option v-for="level in severityLevels" :key="level" :value="level">{{ level }}</option>
            </select>
          </label>
        </div>
        <p v-if="rulesError" class="error-text">{{ rulesError }}</p>
        <p v-if="rulesMessage" class="ok-text">{{ rulesMessage }}</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="closeRules">关闭</button>
          <button class="btn primary" type="button" @click="submitRule">保存规则</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { request } from '@/api/client'

const ENDPOINT = '/api/defect'
const columns = ['缺陷编号', '所在管段', '缺陷类别', '影响范围', '缺陷位置', '严重等级', '发现日期', '登记人员', '缺陷状态']
const statuses = ['待定级', '已定级', '处置中', '已闭环']

type Row = Record<string, any>
type ActionResponse = {
  ok: boolean
  message: string
  entry?: Row | null
  code?: string | null
  candidates?: Row[] | null
  version?: number | null
  preview?: Record<string, any> | null
}

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')

const severityLevels = ref<string[]>([])
const scopeOptions = ref<string[]>([])
const categoryOptions = ref<string[]>([])
const topSeverity = computed(() => severityLevels.value[severityLevels.value.length - 1] ?? '严重')

const stats = computed(() => [
  { label: '待定级缺陷', value: rows.value.filter((r) => r.status === '待定级').length },
  { label: '处置中缺陷', value: rows.value.filter((r) => r.status === '处置中').length },
  { label: '已闭环缺陷', value: rows.value.filter((r) => r.status === '已闭环').length, danger: false },
  { label: '上限等级缺陷', value: rows.value.filter((r) => r['定级严重等级'] === topSeverity.value).length, danger: true },
])

function mergedCount(row: Row): number {
  return Array.isArray(row['合并记录']) ? row['合并记录'].length : 0
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value) query.set('keyword', keyword.value)
  if (statusFilter.value) query.set('status', statusFilter.value)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) throw new Error('缺陷记录列表读取失败')
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '缺陷登记列表读取失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload: ActionResponse = await response.json()
    if (!payload.ok) {
      errorMessage.value = payload.message
      return
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '缺陷登记操作失败'
  }
}

// ---------- 登记 ----------
const createVisible = ref(false)
const createError = ref('')
const duplicates = ref<Row[]>([])
const createPreview = ref<Record<string, any> | null>(null)

const createFields = computed(() => [
  { key: '缺陷编号', label: '缺陷编号', required: true },
  { key: '所在管段', label: '所在管段', required: true },
  { key: '缺陷类别', label: '缺陷类别', required: true, type: 'select', options: categoryOptions.value },
  { key: '影响范围', label: '影响范围', required: true, type: 'select', options: scopeOptions.value },
  { key: '缺陷位置', label: '缺陷位置' },
  { key: '发现日期', label: '发现日期', type: 'date' },
  { key: '登记人员', label: '登记人员' },
])

const emptyCreateForm = (): Row => ({
  缺陷编号: '', 所在管段: '', 缺陷类别: '', 影响范围: '', 缺陷位置: '', 发现日期: '', 登记人员: '',
})
const createForm = ref<Row>(emptyCreateForm())

function openCreate() {
  createForm.value = emptyCreateForm()
  createError.value = ''
  duplicates.value = []
  createPreview.value = null
  createVisible.value = true
}
function closeCreate() {
  createVisible.value = false
}

async function refreshPreview() {
  const { 缺陷类别: category, 影响范围: scope } = createForm.value
  if (!category || !scope) {
    createPreview.value = null
    return
  }
  try {
    const response = await request(`${ENDPOINT}/rules/preview`, {
      method: 'POST',
      body: JSON.stringify({ values: { 缺陷类别: category, 影响范围: scope } }),
    })
    const payload: ActionResponse = await response.json()
    createPreview.value = payload.preview ?? null
  } catch {
    createPreview.value = null
  }
}

async function submitCreate(force: boolean) {
  createError.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: createForm.value, force }),
    })
    const payload: ActionResponse = await response.json()
    if (payload.ok) {
      createVisible.value = false
      await reload()
      return
    }
    if (payload.code === 'DUPLICATE') {
      duplicates.value = payload.candidates ?? []
      createError.value = payload.message
      return
    }
    createError.value = payload.message
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '缺陷登记失败'
  }
}

async function mergeDuplicate() {
  if (!duplicates.value.length) return
  createError.value = ''
  try {
    const target = duplicates.value[0]
    const response = await request(`${ENDPOINT}/merge`, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm.value, targetId: target.id } }),
    })
    const payload: ActionResponse = await response.json()
    if (!payload.ok) {
      createError.value = payload.message
      return
    }
    createVisible.value = false
    errorMessage.value = payload.message
    await reload()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '合并失败'
  }
}

// ---------- 定级 ----------
const gradeVisible = ref(false)
const gradeError = ref('')
const gradeTarget = ref<Row | null>(null)
const gradeForm = ref<Row>({})

function openGrade(row: Row) {
  gradeTarget.value = row
  gradeError.value = ''
  gradeForm.value = {
    严重等级: row['建议严重等级'] ?? '',
    处置方案: '',
    定级日期: new Date().toISOString().slice(0, 10),
    定级人员: '',
  }
  gradeVisible.value = true
}
function closeGrade() {
  gradeVisible.value = false
  gradeTarget.value = null
}

async function submitGrade() {
  if (!gradeTarget.value) return
  gradeError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${gradeTarget.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action: '确认定级', ...gradeForm.value } }),
    })
    const payload: ActionResponse = await response.json()
    if (!payload.ok) {
      gradeError.value = payload.message
      return
    }
    gradeVisible.value = false
    await reload()
  } catch (error) {
    gradeError.value = error instanceof Error ? error.message : '确认定级失败'
  }
}

// ---------- 规则 ----------
const rulesVisible = ref(false)
const rules = ref<Row[]>([])
const ruleVersion = ref(1)
const rulesError = ref('')
const rulesMessage = ref('')
const ruleForm = ref<Row>({ 缺陷类别: '', 影响范围: '', 建议等级: '' })

async function openRules() {
  rulesVisible.value = true
  rulesError.value = ''
  rulesMessage.value = ''
  await loadRules()
}
function closeRules() {
  rulesVisible.value = false
}

async function loadRules() {
  try {
    const response = await request(`${ENDPOINT}/rules`)
    const payload = await response.json()
    rules.value = payload.items ?? []
    ruleVersion.value = payload.version ?? 1
  } catch (error) {
    rulesError.value = error instanceof Error ? error.message : '定级口径读取失败'
  }
}

async function submitRule() {
  rulesError.value = ''
  rulesMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/rules`, {
      method: 'POST',
      body: JSON.stringify({ values: ruleForm.value }),
    })
    const payload: ActionResponse = await response.json()
    if (!payload.ok) {
      rulesError.value = payload.message
      return
    }
    rulesMessage.value = payload.message
    ruleForm.value = { 缺陷类别: '', 影响范围: '', 建议等级: '' }
    await loadRules()
  } catch (error) {
    rulesError.value = error instanceof Error ? error.message : '规则保存失败'
  }
}

async function deleteRule(id: number) {
  rulesError.value = ''
  rulesMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/rules/${id}`, { method: 'DELETE' })
    const payload: ActionResponse = await response.json()
    rulesMessage.value = payload.message
    await loadRules()
  } catch (error) {
    rulesError.value = error instanceof Error ? error.message : '规则删除失败'
  }
}

onMounted(async () => {
  try {
    const response = await request(`${ENDPOINT}/options`)
    const payload = await response.json()
    severityLevels.value = payload.severity ?? []
    scopeOptions.value = payload.scope ?? []
    categoryOptions.value = payload.category ?? []
  } catch {
    // 枚举取用时页面仍可渲染，列表不受影响
  }
  await reload()
})

// 类别或范围变化时重新试算建议等级
watch(() => [createForm.value['缺陷类别'], createForm.value['影响范围']], refreshPreview)
</script>
