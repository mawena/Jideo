<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, type Health, type Job } from './api'
import HistoryList from './components/HistoryList.vue'
import ResultView from './components/ResultView.vue'
import Workshop from './components/Workshop.vue'
import { useJobs } from './composables/useJobs'

const health = ref<Health | null>(null)
const opened = ref<Job | null>(null)
const { refresh, connect } = useJobs()

onMounted(async () => {
  health.value = await api.health()
  await refresh()
  connect()
})
</script>

<template>
  <div class="min-h-screen">
    <header class="flex items-baseline gap-3 border-b border-zinc-800 px-4 py-3">
      <h1 class="text-xl font-bold tracking-tight">Jideo</h1>
      <span class="text-sm text-zinc-500">Face swap local</span>
    </header>
    <div v-if="health && !health.models_ready" class="bg-amber-500/10 px-4 py-2 text-sm text-amber-200">
      Modèles absents : lancez <code>./jideo install</code>.
    </div>
    <main class="mx-auto grid max-w-7xl gap-6 p-4 lg:grid-cols-[1fr_380px]">
      <Workshop />
      <HistoryList @open="opened = $event" />
    </main>
    <ResultView v-if="opened" :job="opened" @close="opened = null" />
  </div>
</template>
