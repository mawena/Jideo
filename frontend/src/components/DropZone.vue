<script setup lang="ts">
import { ref } from 'vue'

defineProps<{ label: string; accept: string; busy?: boolean; testid?: string }>()
const emit = defineEmits<{ file: [File] }>()
const over = ref(false)

function onDrop(event: DragEvent) {
  over.value = false
  const file = event.dataTransfer?.files[0]
  if (file) emit('file', file)
}

function onChange(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) emit('file', file)
  input.value = ''
}
</script>

<template>
  <label
    class="flex cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed p-6 text-center text-sm transition"
    :class="over ? 'border-violet-400 bg-violet-500/10' : 'border-zinc-700 hover:border-zinc-500'"
    @dragover.prevent="over = true"
    @dragleave="over = false"
    @drop.prevent="onDrop"
  >
    <span class="font-medium text-zinc-200">{{ busy ? 'Traitement…' : label }}</span>
    <span class="text-zinc-500">Glisser-déposer ou cliquer</span>
    <input type="file" class="hidden" :accept="accept" :data-testid="testid" :disabled="busy" @change="onChange" />
  </label>
</template>
