<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { api } from '../api'

const props = defineProps<{ src: string; mediaId: string; duration: number; start: number; end: number }>()
const emit = defineEmits<{ pick: [number]; 'update:start': [number]; 'update:end': [number] }>()
const video = ref<HTMLVideoElement>()
const unplayable = ref(false)
const current = ref(0) // le curseur est la référence : il marche même si le navigateur ne lit pas le codec
const previewAt = ref(0)
let timer: ReturnType<typeof setTimeout> | undefined

const round = (t: number) => Math.round(t * 100) / 100

// Aperçu serveur débouncé pour ne pas inonder /frame pendant qu'on glisse le curseur.
watch(current, (t) => {
  clearTimeout(timer)
  timer = setTimeout(() => { previewAt.value = t }, 250)
})
onBeforeUnmount(() => clearTimeout(timer))

function onTimeUpdate() {
  if (video.value) current.value = round(video.value.currentTime)
}

function onSlide(event: Event) {
  current.value = Number((event.target as HTMLInputElement).value)
  if (video.value && !unplayable.value) video.value.currentTime = current.value
}

function format(seconds: number) {
  const minutes = Math.floor(seconds / 60)
  return `${minutes}:${(seconds % 60).toFixed(1).padStart(4, '0')}`
}
</script>

<template>
  <div class="space-y-2">
    <video v-show="!unplayable" ref="video" :src="src" controls preload="metadata"
      class="max-h-72 w-full rounded-lg bg-black" @timeupdate="onTimeUpdate" @error="unplayable = true" />
    <p v-if="unplayable" class="text-sm text-amber-300" data-testid="unplayable">
      Le navigateur ne peut pas lire cette vidéo : utilisez le curseur ci-dessous.
    </p>
    <img :src="api.frameUrl(mediaId, previewAt)" alt="Image de la vidéo à l'instant choisi"
      class="max-h-72 w-full rounded-lg bg-black object-contain" data-testid="frame-preview" />
    <div class="flex items-center gap-3">
      <input type="range" min="0" :max="duration" step="0.1" :value="current" class="w-full"
        aria-label="Instant dans la vidéo" data-testid="frame-slider" @input="onSlide" />
      <span class="w-14 shrink-0 text-right text-xs tabular-nums text-zinc-400">{{ format(current) }}</span>
    </div>
    <div class="flex flex-wrap gap-2">
      <button type="button" class="btn" data-testid="pick-frame" @click="emit('pick', current)">
        Détecter les visages sur cette image
      </button>
      <button type="button" class="btn" @click="emit('update:start', Math.min(current, props.end))">Début ici</button>
      <button type="button" class="btn" @click="emit('update:end', Math.max(current, props.start))">Fin ici</button>
    </div>
    <p class="text-xs text-zinc-400">
      Segment : {{ format(start) }} → {{ format(end) }} ({{ (end - start).toFixed(1) }} s sur {{ duration.toFixed(1) }} s)
    </p>
  </div>
</template>
