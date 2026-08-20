<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { memoriesApi } from '../api/memories'
import ForumHeader from '../components/ForumHeader.vue'
import type { Memory, MemoryType, UpdateMemoryRequest } from '../types/api'
import { getApiErrorMessage } from '../utils/apiError'

const memories = ref<Memory[]>([])
const loading = ref(false)
const savingId = ref<string | null>(null)
const errorMessage = ref('')
const editingId = ref<string | null>(null)
const editForm = reactive<UpdateMemoryRequest>({
  memoryType: 'FOOD_PREFERENCE',
  key: '',
  value: '',
})

const categories: Array<{ type: MemoryType; label: string; description: string }> = [
  { type: 'DIETARY_RESTRICTION', label: '饮食限制', description: '需要避开的过敏原和食物。' },
  { type: 'FOOD_PREFERENCE', label: '食物偏好', description: '你通常喜欢或不喜欢的食材与食物。' },
  { type: 'CUISINE_PREFERENCE', label: '菜系偏好', description: '你经常选择或喜欢的菜系。' },
  { type: 'COOKING_PREFERENCE', label: '烹饪偏好', description: '口味、用油、盐量和操作难度等偏好。' },
  { type: 'HOUSEHOLD_CONTEXT', label: '烹饪习惯', description: '常用份量、厨具和时间限制。' },
  { type: 'NUTRITION_GOAL', label: '营养目标', description: '推荐菜谱时会持续参考的营养目标。' },
]

const memoryKeyLabels: Record<string, string> = {
  available_appliances: '可用厨具',
  unavailable_appliances: '不可用厨具',
  cooking_time: '烹饪时长',
  usual_servings: '常用份量',
  cooking_complexity: '烹饪难度',
  less_oil: '少油偏好',
  low_oil: '少油偏好',
  sour_flavor: '酸味偏好',
  cilantro: '香菜',
  coriander: '香菜',
  peanut: '花生',
  peanuts: '花生',
  rice: '米饭',
}

const memoryValueLabels: Record<string, string> = {
  allergy: '过敏',
  avoid: '避免',
  dislike: '不喜欢',
  like: '喜欢',
  prefer: '偏好',
  preferred: '偏好',
  yes: '是',
  no: '否',
  true: '是',
  false: '否',
  rice_cooker: '电饭锅',
  wok: '炒锅',
  oven: '烤箱',
  microwave: '微波炉',
  air_fryer: '空气炸锅',
  pressure_cooker: '压力锅',
  simple: '简单',
  easy: '简单',
  low_oil: '少油',
  less_oil: '少油',
  home_style_chinese: '家常中餐',
  strongly_avoids_cilantro: '非常不喜欢香菜',
  strongly_avoid: '坚决避免',
  prefers_rice_as_main_staple: '偏好以米饭为主食',
  'prefers_simple,_easy_steps': '偏好简单、容易操作的步骤',
  prefers_less_oil_when_cooking: '烹饪时偏好少油',
  likes_sour_flavors: '喜欢酸味',
}

function normalizeMachineText(value: string): string {
  return value.trim().toLowerCase().replace(/[\s-]+/g, '_')
}

function displayMemoryKey(key: string): string {
  return memoryKeyLabels[normalizeMachineText(key)] ?? key.replaceAll('_', ' ')
}

function displayMemoryValue(value: string): string {
  const normalized = normalizeMachineText(value)
  const minuteMatch = normalized.match(/^(\d+)_minutes?$/)
  if (minuteMatch) return `${minuteMatch[1]} 分钟`
  const servingsMatch = normalized.match(/^(\d+)_servings?$/)
  if (servingsMatch) return `${servingsMatch[1]} 人份`
  const peopleMatch = normalized.match(/^(\d+)_people$/)
  if (peopleMatch) return `${peopleMatch[1]} 人份`
  if (memoryValueLabels[normalized]) return memoryValueLabels[normalized]

  return value
    .split(/[,，]/)
    .map((item) => memoryValueLabels[normalizeMachineText(item)] ?? item.trim().replaceAll('_', ' '))
    .filter(Boolean)
    .join('、')
}

const groupedMemories = computed(() => categories
  .map((category) => ({
    ...category,
    items: memories.value.filter((memory) => memory.memoryType === category.type),
  }))
  .filter((category) => category.items.length > 0))

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    memories.value = await memoriesApi.list()
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error, '已保存的长期记忆加载失败。')
  } finally {
    loading.value = false
  }
}

function startEdit(memory: Memory): void {
  editingId.value = memory.id
  editForm.memoryType = memory.memoryType
  editForm.key = memory.key
  editForm.value = memory.value
  errorMessage.value = ''
}

function cancelEdit(): void {
  editingId.value = null
}

async function save(memoryId: string): Promise<void> {
  if (!editForm.key.trim() || !editForm.value.trim()) return
  savingId.value = memoryId
  errorMessage.value = ''
  try {
    const updated = await memoriesApi.update(memoryId, {
      memoryType: editForm.memoryType,
      key: editForm.key.trim(),
      value: editForm.value.trim(),
    })
    memories.value = memories.value.map((memory) => memory.id === memoryId ? updated : memory)
    editingId.value = null
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error, '这条记忆更新失败。')
  } finally {
    savingId.value = null
  }
}

async function remove(memoryId: string): Promise<void> {
  savingId.value = memoryId
  errorMessage.value = ''
  try {
    await memoriesApi.remove(memoryId)
    memories.value = memories.value.filter((memory) => memory.id !== memoryId)
    if (editingId.value === memoryId) editingId.value = null
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error, '这条记忆删除失败。')
  } finally {
    savingId.value = null
  }
}

onMounted(load)
</script>

<template>
  <main class="forum-shell">
    <ForumHeader />
    <section class="memory-page">
      <div class="memory-heading">
        <span class="eyebrow">隐私与个性化</span>
        <h1>AI Cooker 记住了什么</h1>
        <p>
          这里保存的是会在不同对话间持续使用的稳定烹饪偏好。
          临时食材和一次性的用餐计划不会出现在这里。
        </p>
      </div>

      <div v-if="errorMessage" class="notice notice--error" role="alert">{{ errorMessage }}</div>
      <div v-if="loading" class="memory-state"><span class="spinner" /> 正在加载记忆…</div>
      <div v-else-if="memories.length === 0" class="memory-state memory-state--empty">
        <span aria-hidden="true">🧠</span>
        <h2>暂时没有已保存的记忆</h2>
        <p>你在对话中明确表达的稳定偏好会显示在这里。</p>
      </div>

      <div v-else class="memory-groups">
        <section v-for="category in groupedMemories" :key="category.type" class="memory-group">
          <header>
            <div>
              <h2>{{ category.label }}</h2>
              <p>{{ category.description }}</p>
            </div>
            <span>{{ category.items.length }}</span>
          </header>

          <article v-for="memory in category.items" :key="memory.id" class="memory-card">
            <form v-if="editingId === memory.id" class="memory-edit" @submit.prevent="save(memory.id)">
              <label>
                分类
                <select v-model="editForm.memoryType">
                  <option v-for="item in categories" :key="item.type" :value="item.type">{{ item.label }}</option>
                </select>
              </label>
              <label>
                主题
                <input v-model="editForm.key" maxlength="80" required />
              </label>
              <label>
                记忆内容
                <input v-model="editForm.value" maxlength="255" required />
              </label>
              <div class="memory-actions">
                <button class="text-button" type="button" :disabled="savingId === memory.id" @click="cancelEdit">取消</button>
                <button class="primary-link" type="submit" :disabled="savingId === memory.id">
                  {{ savingId === memory.id ? '正在保存…' : '保存' }}
                </button>
              </div>
            </form>
            <template v-else>
              <div class="memory-card__text">
                <strong>{{ displayMemoryKey(memory.key) }}</strong>
                <span>{{ displayMemoryValue(memory.value) }}</span>
              </div>
              <div class="memory-actions">
                <button class="text-button" type="button" @click="startEdit(memory)">编辑</button>
                <button class="danger-button" type="button" :disabled="savingId === memory.id" @click="remove(memory.id)">
                  {{ savingId === memory.id ? '正在删除…' : '删除' }}
                </button>
              </div>
            </template>
          </article>
        </section>
      </div>
    </section>
  </main>
</template>
