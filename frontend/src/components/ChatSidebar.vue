<script setup lang="ts">
import { nextTick, ref } from 'vue'

import type { Conversation } from '../types/api'
import AppLogo from './AppLogo.vue'

defineProps<{
  conversations: Conversation[]
  activeConversationId: string | null
  loading: boolean
  open: boolean
  busy: boolean
}>()

const emit = defineEmits<{
  newConversation: []
  select: [conversationId: string]
  rename: [conversationId: string, title: string]
  delete: [conversationId: string]
  logout: []
  close: []
}>()

const openMenuId = ref<string | null>(null)
const renameTarget = ref<Conversation | null>(null)
const deleteTarget = ref<Conversation | null>(null)
const titleDraft = ref('')
const renameInput = ref<HTMLInputElement | null>(null)

function selectConversation(conversationId: string): void {
  openMenuId.value = null
  emit('select', conversationId)
}

function toggleMenu(conversationId: string): void {
  openMenuId.value = openMenuId.value === conversationId ? null : conversationId
}

async function openRename(conversation: Conversation): Promise<void> {
  openMenuId.value = null
  renameTarget.value = conversation
  titleDraft.value = conversation.title
  await nextTick()
  renameInput.value?.focus()
  renameInput.value?.select()
}

function closeRename(): void {
  renameTarget.value = null
  titleDraft.value = ''
}

function submitRename(): void {
  const title = titleDraft.value.trim()
  if (!renameTarget.value || !title) return
  emit('rename', renameTarget.value.id, title)
  closeRename()
}

function openDelete(conversation: Conversation): void {
  openMenuId.value = null
  deleteTarget.value = conversation
}

function closeDelete(): void {
  deleteTarget.value = null
}

function confirmDelete(): void {
  if (!deleteTarget.value) return
  emit('delete', deleteTarget.value.id)
  closeDelete()
}

function formatDate(value: string): string {
  const date = new Date(value)
  const today = new Date()
  if (date.toDateString() === today.toDateString()) {
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}
</script>

<template>
  <div v-if="open" class="sidebar-backdrop" @click="emit('close')" />
  <aside class="sidebar" :class="{ 'sidebar--open': open }">
    <div class="sidebar__top">
      <AppLogo compact />
      <button class="icon-button sidebar__close" type="button" aria-label="关闭菜单" @click="emit('close')">
        <svg viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18" /></svg>
      </button>
    </div>

    <nav class="sidebar-nav" aria-label="主导航">
      <RouterLink to="/chat">对话</RouterLink>
      <RouterLink to="/forum">社区</RouterLink>
      <RouterLink to="/settings/memory">记忆</RouterLink>
    </nav>

    <button class="new-chat-button" type="button" :disabled="busy" @click="emit('newConversation')">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
      新建对话
    </button>

    <div class="sidebar__label">对话记录</div>
    <div class="conversation-list" aria-live="polite">
      <div v-if="loading" class="sidebar-state">正在加载对话…</div>
      <div v-else-if="conversations.length === 0" class="sidebar-state">
        你的菜谱对话会显示在这里。
      </div>
      <template v-else>
        <div
          v-for="conversation in conversations"
          :key="conversation.id"
          class="conversation-row"
          :class="{ 'conversation-row--active': conversation.id === activeConversationId }"
        >
          <button
            class="conversation-item"
            type="button"
            :disabled="busy"
            @click="selectConversation(conversation.id)"
          >
            <span class="conversation-item__title">{{ conversation.title }}</span>
            <span class="conversation-item__date">{{ formatDate(conversation.updatedAt) }}</span>
          </button>
          <button
            class="conversation-actions-button"
            type="button"
            :disabled="busy"
            :aria-label="`${conversation.title} 的操作菜单`"
            :aria-expanded="openMenuId === conversation.id"
            @click.stop="toggleMenu(conversation.id)"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <circle cx="5" cy="12" r="1.5" />
              <circle cx="12" cy="12" r="1.5" />
              <circle cx="19" cy="12" r="1.5" />
            </svg>
          </button>
          <div
            v-if="openMenuId === conversation.id"
            class="conversation-actions-menu"
            role="menu"
            @click.stop
          >
            <button type="button" role="menuitem" @click="openRename(conversation)">重命名</button>
            <button class="conversation-actions-menu__danger" type="button" role="menuitem" @click="openDelete(conversation)">删除</button>
          </div>
        </div>
      </template>
    </div>

    <button class="logout-button" type="button" @click="emit('logout')">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M10 5H5v14h5M14 8l4 4-4 4M8 12h10" />
      </svg>
      退出登录
    </button>
  </aside>

  <Teleport to="body">
    <div
      v-if="renameTarget"
      class="conversation-dialog-backdrop"
      role="presentation"
      @click.self="closeRename"
      @keydown.esc="closeRename"
    >
      <section class="conversation-dialog" role="dialog" aria-modal="true" aria-labelledby="rename-conversation-title">
        <span class="eyebrow">对话</span>
        <h2 id="rename-conversation-title">重命名对话</h2>
        <p>填写一个简短、方便以后查找的标题。</p>
        <label class="conversation-dialog__field">
          <span>标题</span>
          <input
            ref="renameInput"
            v-model="titleDraft"
            type="text"
            maxlength="160"
            autocomplete="off"
            @keydown.enter.prevent="submitRename"
          >
        </label>
        <div class="conversation-dialog__actions">
          <button class="dialog-button dialog-button--secondary" type="button" @click="closeRename">取消</button>
          <button class="dialog-button dialog-button--primary" type="button" :disabled="!titleDraft.trim() || busy" @click="submitRename">保存</button>
        </div>
      </section>
    </div>

    <div
      v-if="deleteTarget"
      class="conversation-dialog-backdrop"
      role="presentation"
      @click.self="closeDelete"
      @keydown.esc="closeDelete"
    >
      <section class="conversation-dialog" role="alertdialog" aria-modal="true" aria-labelledby="delete-conversation-title">
        <span class="eyebrow eyebrow--danger">永久操作</span>
        <h2 id="delete-conversation-title">删除这段对话？</h2>
        <p>
          “{{ deleteTarget.title }}”及其可见消息记录将被永久删除。
          已发布的社区帖子和上传过的图片会保留。
        </p>
        <div class="conversation-dialog__actions">
          <button class="dialog-button dialog-button--secondary" type="button" @click="closeDelete">取消</button>
          <button class="dialog-button dialog-button--danger" type="button" :disabled="busy" @click="confirmDelete">永久删除</button>
        </div>
      </section>
    </div>
  </Teleport>
</template>
