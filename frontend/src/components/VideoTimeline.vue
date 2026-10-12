<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{ src: string; duration: number; start: number; end: number }>()
const emit = defineEmits<{ pick: [number]; 'update:start': [number]; 'update:end': [number] }>()
const video = ref<HTMLVideoElement>()

function now() {
  return Math.round((video.value?.currentTime ?? 0) * 100) / 100
}

function format(seconds: number) {
  const minutes = Math.floor(seconds / 60)
  return `${minutes}:${(seconds % 60).toFixed(1).padStart(4, '0')}`
}
</script>

<template>
  <div class="space-y-2">
    <video ref="video" :src="src" controls preload="metadata" class="max-h-72 w-full rounded-lg bg-black" />
    <div class="flex flex-wrap gap-2">
      <button type="button" class="btn" data-testid="pick-frame" @click="emit('pick', now())">
        Détecter les visages sur cette image
      </button>
      <button type="button" class="btn" @click="emit('update:start', Math.min(now(), props.end))">Début ici</button>
      <button type="button" class="btn" @click="emit('update:end', Math.max(now(), props.start))">Fin ici</button>
    </div>
    <p class="text-xs text-zinc-400">
      Segment : {{ format(start) }} → {{ format(end) }} ({{ (end - start).toFixed(1) }} s sur {{ duration.toFixed(1) }} s)
    </p>
  </div>
</template>
