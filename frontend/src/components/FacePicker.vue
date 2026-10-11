<script setup lang="ts">
import type { FaceDetection } from '../api'

const props = defineProps<{
  src: string
  detection: FaceDetection
  modelValue: string[]
  multiple: boolean
  testid: string
}>()
const emit = defineEmits<{ 'update:modelValue': [string[]] }>()

function toggle(id: string) {
  if (!props.multiple) return emit('update:modelValue', [id])
  const selected = new Set(props.modelValue)
  if (selected.has(id)) selected.delete(id)
  else selected.add(id)
  emit('update:modelValue', [...selected])
}

function box(bbox: [number, number, number, number]) {
  const { width: w, height: h } = props.detection
  const x1 = Math.max(0, bbox[0]), y1 = Math.max(0, bbox[1])
  const x2 = Math.min(w, bbox[2]), y2 = Math.min(h, bbox[3])
  return {
    left: `${(x1 / w) * 100}%`,
    top: `${(y1 / h) * 100}%`,
    width: `${((x2 - x1) / w) * 100}%`,
    height: `${((y2 - y1) / h) * 100}%`,
  }
}
</script>

<template>
  <div class="relative inline-block max-w-full">
    <img :src="src" class="block max-h-80 max-w-full rounded-lg" alt="" />
    <button
      v-for="face in detection.faces"
      :key="face.id"
      type="button"
      :data-testid="`${testid}-face-${face.index}`"
      :aria-pressed="modelValue.includes(face.id)"
      class="absolute rounded border-2 transition"
      :class="modelValue.includes(face.id) ? 'border-violet-400 bg-violet-400/25' : 'border-white/70 hover:border-violet-300'"
      :style="box(face.bbox)"
      @click="toggle(face.id)"
    >
      <span class="absolute -top-5 left-0 rounded bg-black/70 px-1 text-xs text-white">{{ face.index + 1 }}</span>
    </button>
  </div>
</template>
