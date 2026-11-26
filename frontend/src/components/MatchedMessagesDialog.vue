<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../api'
import { dateTime, integer } from '../format'
import type { MatchedMessage } from '../types'

const props = withDefaults(
  defineProps<{
    batchId: string
    targetType: 'template' | 'candidate' | 'unmatched'
    targetId: string
    heading: string
    text: string
    operator?: string | null
    untriggeredOnly?: boolean
  }>(),
  { operator: null, untriggeredOnly: false },
)

const emit = defineEmits<{ close: [] }>()

const messages = ref<MatchedMessage[]>([])
const loading = ref(true)
const error = ref('')
const copied = ref(false)

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const response =
      props.targetType === 'template'
        ? await api.matchedTemplateMessages(props.batchId, props.targetId, {
            operator: props.operator,
            untriggered: props.untriggeredOnly,
          })
        : props.targetType === 'candidate'
          ? await api.matchedCandidateMessages(props.batchId, props.targetId)
          : await api.unmatchedTemplatedMessages(props.batchId)
    messages.value = response.messages
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : 'Не удалось загрузить сообщения'
  } finally {
    loading.value = false
  }
}

async function copyText(): Promise<void> {
  try {
    await navigator.clipboard.writeText(props.text)
    copied.value = true
    window.setTimeout(() => (copied.value = false), 1800)
  } catch {
    const area = document.createElement('textarea')
    area.value = props.text
    document.body.appendChild(area)
    area.select()
    document.execCommand('copy')
    document.body.removeChild(area)
    copied.value = true
    window.setTimeout(() => (copied.value = false), 1800)
  }
}

function onKey(event: KeyboardEvent): void {
  if (event.key === 'Escape') emit('close')
}

onMounted(() => {
  void load()
  window.addEventListener('keydown', onKey)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
})
</script>

<template>
  <div class="modal-backdrop" @click.self="emit('close')">
    <div class="modal" role="dialog" aria-modal="true" :aria-label="heading">
      <div class="modal-header">
        <div style="flex: 1; min-width: 0">
          <h3 class="card-title" style="font-size: 17px">{{ heading }}</h3>
          <div class="card-caption">
            Реальные сообщения загрузки · {{ integer(messages.length) }}
          </div>
        </div>
        <button class="btn" type="button" @click="copyText">
          {{ copied ? 'Скопировано' : 'Копировать' }}
        </button>
        <button class="btn btn-ghost" type="button" aria-label="Закрыть" @click="emit('close')">
          ✕
        </button>
      </div>
      <div class="modal-body">
        <div v-if="text" class="modal-text">{{ text }}</div>

        <div v-if="loading" class="empty">
          <div class="spinner" style="margin: 0 auto 10px"></div>
          Подбираем сообщения…
        </div>
        <div v-else-if="error" class="empty negative">{{ error }}</div>
        <div v-else-if="!messages.length" class="empty">Подходящих сообщений не найдено</div>
        <div v-else class="table-wrap">
          <table class="data">
            <thead>
              <tr>
                <th>Сообщение</th>
                <th class="num">Длина</th>
                <th>Номер</th>
                <th>Дата/Время отправки</th>
                <th>Оператор</th>
                <th>Статус доставки</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="message in messages" :key="message.message_id">
                <td>
                  <div class="cell-text" :title="message.text">{{ message.text }}</div>
                </td>
                <td class="num">{{ integer(message.segments) }}</td>
                <td class="mono">{{ message.masked_recipient }}</td>
                <td>{{ dateTime(message.sent_at) }}</td>
                <td>{{ message.operator || '—' }}</td>
                <td>{{ message.delivery_status }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>
