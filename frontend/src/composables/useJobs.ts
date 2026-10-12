import { reactive, ref } from 'vue'
import { api, type Job, type ProgressEvent } from '../api'

const jobs = ref<Job[]>([])
const progress = reactive<Record<string, ProgressEvent>>({})
let source: EventSource | null = null

// Un statut ne régresse jamais : la réponse du POST (en attente) peut arriver après l'événement SSE « started ».
const RANK: Record<Job['status'], number> = { queued: 0, running: 1, done: 2, failed: 2, cancelled: 2 }

function upsert(job: Job) {
  const index = jobs.value.findIndex((j) => j.id === job.id)
  if (index === -1) jobs.value.unshift(job)
  else if (RANK[job.status] >= RANK[jobs.value[index].status]) jobs.value[index] = job
}

function remove(id: string) {
  jobs.value = jobs.value.filter((j) => j.id !== id)
  delete progress[id]
}

async function refresh() {
  jobs.value = (await api.listJobs()).items
}

function connect() {
  if (source) return
  source = new EventSource('/api/events')
  source.onmessage = (message) => {
    const event = JSON.parse(message.data)
    if (event.type === 'progress') {
      progress[event.job_id] = event
    } else if (event.job) {
      upsert(event.job)
      if (event.type !== 'started') delete progress[event.job.id]
    }
  }
  // EventSource se reconnecte seul ; on resynchronise la liste après une coupure.
  source.onerror = () => setTimeout(() => refresh().catch(() => {}), 2000)
}

export function useJobs() {
  return { jobs, progress, refresh, connect, upsert, remove }
}
