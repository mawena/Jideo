<script setup lang="ts">
import { computed } from 'vue'
import type { Job } from '../api'
import BeforeAfter from './BeforeAfter.vue'

const props = defineProps<{ job: Job }>()
const emit = defineEmits<{ close: [] }>()

const before = computed(() => {
  const media = props.job.params.target_media_id
  if (props.job.type === 'photo') return `/api/media/${media}/file`
  if (props.job.type === 'preview') return `/api/media/${media}/frame?t=${props.job.params.t ?? 0}`
  return null
})
</script>

<template>
  <div class="fixed inset-0 z-10 flex items-center justify-center bg-black/80 p-4" @click.self="emit('close')">
    <div class="max-h-full w-full max-w-5xl space-y-3 overflow-auto rounded-xl bg-zinc-900 p-4">
      <div class="flex items-center justify-between">
        <h2 class="font-semibold">Résultat</h2>
        <button class="btn" @click="emit('close')">Fermer</button>
      </div>
      <video v-if="job.type === 'video' && job.result_url" :src="job.result_url" controls class="max-h-[70vh] w-full" />
      <BeforeAfter v-else-if="before && job.result_url" :before="before" :after="job.result_url" />
      <p v-if="job.message" class="text-sm text-amber-300">{{ job.message }}</p>
      <a v-if="job.result_url" :href="job.result_url" download class="btn inline-block">Télécharger</a>
    </div>
  </div>
</template>
