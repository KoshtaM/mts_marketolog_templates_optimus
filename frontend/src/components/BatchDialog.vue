<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  title: string
  label: string
  placeholder?: string
  initial?: string | null
}>()

const emit = defineEmits<{
  save: [value: string | null]
  cancel: []
}>()

const value = ref(props.initial ?? '')
const visible = ref(true)

function save(): void {
  emit('save', value.value.trim() || null)
  visible.value = false
}

function cancel(): void {
  emit('cancel')
  visible.value = false
}
</script>

<template>
  <div v-if="visible" class="modal-backdrop" @click.self="cancel">
    <div class="modal" role="dialog" aria-modal="true" :aria-label="title">
      <div class="modal-header">
        <div style="flex: 1; min-width: 0">
          <h3 class="card-title" style="font-size: 17px">{{ title }}</h3>
        </div>
        <button class="btn btn-ghost" type="button" aria-label="Закрыть" @click="cancel">
          ✕
        </button>
      </div>
      <div class="modal-body">
        <label class="field-label" :for="`batch-dialog-value`">{{ label }}</label>
        <div class="field">
          <input
            id="`batch-dialog-value`"
            class="input"
            :value="value"
            :placeholder="placeholder"
            @input="(event: Event) => (value = (event.target as HTMLInputElement).value)"
          />
        </div>
        <div class="row" style="margin-top: 16px; justify-content: flex-end">
          <button class="btn" type="button" @click="cancel">Отмена</button>
          <button class="btn btn-primary" type="button" @click="save">Сохранить</button>
        </div>
      </div>
    </div>
  </div>
</template>
