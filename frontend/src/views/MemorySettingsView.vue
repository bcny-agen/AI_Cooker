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
  { type: 'DIETARY_RESTRICTION', label: 'Dietary restrictions', description: 'Allergies and foods you need to avoid.' },
  { type: 'FOOD_PREFERENCE', label: 'Food preferences', description: 'Ingredients and foods you usually like or avoid.' },
  { type: 'CUISINE_PREFERENCE', label: 'Cuisine preferences', description: 'Cuisines you tend to enjoy.' },
  { type: 'COOKING_PREFERENCE', label: 'Cooking preferences', description: 'Spice, oil, salt, and difficulty preferences.' },
  { type: 'HOUSEHOLD_CONTEXT', label: 'Cooking habits', description: 'Usual servings, appliances, and time constraints.' },
  { type: 'NUTRITION_GOAL', label: 'Nutrition goals', description: 'Ongoing nutrition goals used for recipe suggestions.' },
]

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
    errorMessage.value = getApiErrorMessage(error, 'Your saved memories could not be loaded.')
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
    errorMessage.value = getApiErrorMessage(error, 'This memory could not be updated.')
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
    errorMessage.value = getApiErrorMessage(error, 'This memory could not be deleted.')
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
        <span class="eyebrow">Privacy and personalization</span>
        <h1>What AI Cooker remembers</h1>
        <p>
          These are stable cooking preferences shared across your conversations.
          Temporary ingredients and one-off meal plans should not appear here.
        </p>
      </div>

      <div v-if="errorMessage" class="notice notice--error" role="alert">{{ errorMessage }}</div>
      <div v-if="loading" class="memory-state"><span class="spinner" /> Loading memories…</div>
      <div v-else-if="memories.length === 0" class="memory-state memory-state--empty">
        <span aria-hidden="true">🧠</span>
        <h2>Nothing saved yet</h2>
        <p>Stable preferences you explicitly share in chat will appear here.</p>
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
                Category
                <select v-model="editForm.memoryType">
                  <option v-for="item in categories" :key="item.type" :value="item.type">{{ item.label }}</option>
                </select>
              </label>
              <label>
                Subject
                <input v-model="editForm.key" maxlength="80" required />
              </label>
              <label>
                What to remember
                <input v-model="editForm.value" maxlength="255" required />
              </label>
              <div class="memory-actions">
                <button class="text-button" type="button" :disabled="savingId === memory.id" @click="cancelEdit">Cancel</button>
                <button class="primary-link" type="submit" :disabled="savingId === memory.id">
                  {{ savingId === memory.id ? 'Saving…' : 'Save' }}
                </button>
              </div>
            </form>
            <template v-else>
              <div class="memory-card__text">
                <strong>{{ memory.key }}</strong>
                <span>{{ memory.value }}</span>
              </div>
              <div class="memory-actions">
                <button class="text-button" type="button" @click="startEdit(memory)">Edit</button>
                <button class="danger-button" type="button" :disabled="savingId === memory.id" @click="remove(memory.id)">
                  {{ savingId === memory.id ? 'Deleting…' : 'Delete' }}
                </button>
              </div>
            </template>
          </article>
        </section>
      </div>
    </section>
  </main>
</template>
