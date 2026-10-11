<script setup lang="ts">
import { ref } from 'vue'
import { api, ApiError, type Job, type JobStatus, type JobType } from '../api'
import { useJobs } from '../composables/useJobs'

const emit = defineEmits<{ open: [Job] }>()
const { jobs, progress, upsert, remove } = useJobs()
const error = ref<string | null>(null)

const STATUS: Record<JobStatus, { label: string; css: string }> = {
  queued: { label: 'En attente', css: 'bg-zinc-700 text-zinc-200' },
  running: { label: 'En cours', css: 'bg-violet-600/30 text-violet-200' },
  done: { label: 'Terminé', css: 'bg-emerald-600/30 text-emerald-200' },
  failed: { label: 'Échec', css: 'bg-red-600/30 text-red-200' },
  cancelled: { label: 'Annulé', css: 'bg-zinc-700 text-zinc-400' },
}
const TYPES: Record<JobType, string> = { photo: 'Photo', preview: 'Aperçu', video: 'Vidéo' }

function percent(job: Job) {
  return Math.round(100 * (progress[job.id]?.progress ?? job.progress))
}

function duration(seconds: number) {
  const minutes = Math.floor(seconds / 60)
  return minutes ? `${minutes} min ${Math.round(seconds % 60)} s` : `${Math.round(seconds)} s`
}

function detail(job: Job) {
  const p = progress[job.id]
  if (!p) return ''
  const parts: string[] = []
  if (p.eta_s != null) parts.push(`reste ${duration(p.eta_s)}`)
  if (p.fps) parts.push(`${p.fps.toFixed(1)} img/s`)
  return parts.join(' · ')
}

async function act(fn: () => Promise<unknown>) {
  error.value = null
  try {
    await fn()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : String(e)
  }
}
</script>

<template>
  <section class="space-y-3">
    <h2 class="text-lg font-semibold">Historique</h2>
    <p v-if="error" class="rounded-lg bg-red-500/10 p-2 text-sm text-red-300">{{ error }}</p>
    <p v-if="!jobs.length" class="text-sm text-zinc-500">Aucun traitement pour l'instant.</p>
    <article
      v-for="job in jobs"
      :key="job.id"
      data-testid="job"
      class="rounded-xl border border-zinc-800 bg-zinc-900 p-3 text-sm"
    >
      <div class="flex items-center justify-between gap-2">
        <span class="font-medium">{{ TYPES[job.type] }}</span>
        <span class="rounded-full px-2 py-0.5 text-xs" :class="STATUS[job.status].css">{{ STATUS[job.status].label }}</span>
      </div>
      <p class="mt-1 text-xs text-zinc-500">{{ new Date(job.created_at * 1000).toLocaleString('fr-FR') }}</p>
      <div v-if="job.status === 'running'" class="mt-2">
        <div class="h-1.5 overflow-hidden rounded bg-zinc-800">
          <div class="h-full bg-violet-500 transition-all" :style="{ width: `${percent(job)}%` }" />
        </div>
        <p class="mt-1 text-xs text-zinc-400">{{ percent(job) }} %<span v-if="detail(job)"> · {{ detail(job) }}</span></p>
      </div>
      <p v-if="job.message" class="mt-2 text-xs" :class="job.status === 'failed' ? 'text-red-300' : 'text-amber-300'">
        {{ job.message }}
      </p>
      <div class="mt-2 flex flex-wrap gap-2">
        <button v-if="job.status === 'done'" class="btn" @click="emit('open', job)">Voir</button>
        <a v-if="job.result_url" class="btn" :href="job.result_url" download>Télécharger</a>
        <button
          v-if="job.status === 'queued' || job.status === 'running'"
          class="btn"
          @click="act(async () => upsert(await api.cancelJob(job.id)))"
        >Annuler</button>
        <button
          v-if="job.status === 'failed' || job.status === 'cancelled'"
          class="btn"
          @click="act(async () => upsert(await api.retryJob(job.id)))"
        >Relancer</button>
        <button
          v-if="job.status !== 'running' && job.status !== 'queued'"
          class="btn"
          @click="act(async () => { await api.deleteJob(job.id); remove(job.id) })"
        >Supprimer</button>
      </div>
    </article>
  </section>
</template>
