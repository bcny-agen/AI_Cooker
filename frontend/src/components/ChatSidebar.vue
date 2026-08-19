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
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' })
}
</script>

<template>
  <div v-if="open" class="sidebar-backdrop" @click="emit('close')" />
  <aside class="sidebar" :class="{ 'sidebar--open': open }">
    <div class="sidebar__top">
      <AppLogo compact />
      <button class="icon-button sidebar__close" type="button" aria-label="Close menu" @click="emit('close')">
        <svg viewBox="0 0 24 24"><path d="m6 6 12 12M18 6 6 18" /></svg>
      </button>
    </div>

    <nav class="sidebar-nav" aria-label="Main navigation">
      <RouterLink to="/chat">Chat</RouterLink>
      <RouterLink to="/forum">Forum</RouterLink>
      <RouterLink to="/settings/memory">Memory</RouterLink>
    </nav>

    <button class="new-chat-button" type="button" :disabled="busy" @click="emit('newConversation')">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
      New conversation
    </button>

    <div class="sidebar__label">Conversations</div>
    <div class="conversation-list" aria-live="polite">
      <div v-if="loading" class="sidebar-state">Loading conversations…</div>
      <div v-else-if="conversations.length === 0" class="sidebar-state">
        Your recipe conversations will appear here.
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
            :aria-label="`Actions for ${conversation.title}`"
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
            <button type="button" role="menuitem" @click="openRename(conversation)">Rename</button>
            <button class="conversation-actions-menu__danger" type="button" role="menuitem" @click="openDelete(conversation)">Delete</button>
          </div>
        </div>
      </template>
    </div>

    <button class="logout-button" type="button" @click="emit('logout')">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M10 5H5v14h5M14 8l4 4-4 4M8 12h10" />
      </svg>
      Log out
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
        <span class="eyebrow">Conversation</span>
        <h2 id="rename-conversation-title">Rename conversation</h2>
        <p>Choose a short title that will be easy to find later.</p>
        <label class="conversation-dialog__field">
          <span>Title</span>
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
          <button class="dialog-button dialog-button--secondary" type="button" @click="closeRename">Cancel</button>
          <button class="dialog-button dialog-button--primary" type="button" :disabled="!titleDraft.trim() || busy" @click="submitRename">Save</button>
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
        <span class="eyebrow eyebrow--danger">Permanent action</span>
        <h2 id="delete-conversation-title">Delete conversation?</h2>
        <p>
          “{{ deleteTarget.title }}” and its visible message history will be permanently deleted.
          Published forum posts and uploaded images will remain.
        </p>
        <div class="conversation-dialog__actions">
          <button class="dialog-button dialog-button--secondary" type="button" @click="closeDelete">Cancel</button>
          <button class="dialog-button dialog-button--danger" type="button" :disabled="busy" @click="confirmDelete">Delete permanently</button>
        </div>
      </section>
    </div>
  </Teleport>
</template>
