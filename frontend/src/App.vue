<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, ApiError, setUnauthorizedHandler, type Health, type Job } from './api'
import HistoryList from './components/HistoryList.vue'
import LoginView from './components/LoginView.vue'
import ResultView from './components/ResultView.vue'
import Workshop from './components/Workshop.vue'
import { useJobs } from './composables/useJobs'

const health = ref<Health | null>(null)
const opened = ref<Job | null>(null)
const bootError = ref<string | null>(null)
const { refresh, connect, disconnect } = useJobs()

const locked = computed(() => !!health.value?.auth_required && !health.value.authenticated)

setUnauthorizedHandler(() => {
  if (health.value) health.value.authenticated = false
  disconnect()
})

async function boot() {
  bootError.value = null
  try {
    health.value = await api.health()
    if (locked.value) return
    await refresh()
    connect()
  } catch (e) {
    bootError.value = `Jideo ne répond pas : ${e instanceof ApiError ? e.message : 'erreur inattendue'}`
  }
}

async function logout() {
  try {
    await api.logout()
  } finally {
    location.reload()
  }
}

onMounted(boot)
</script>

<template>
  <div class="min-h-screen">
    <LoginView v-if="locked" @success="boot" />
    <template v-else>
      <header class="flex items-baseline gap-3 border-b border-zinc-800 px-4 py-3">
        <h1 class="text-xl font-bold tracking-tight">Jideo</h1>
        <span class="text-sm text-zinc-500">Face swap local</span>
        <button v-if="health?.auth_required" class="btn ml-auto" @click="logout">Se déconnecter</button>
      </header>
      <div v-if="bootError" class="bg-red-500/10 px-4 py-2 text-sm text-red-300">{{ bootError }}</div>
      <div v-if="health && !health.models_ready" class="bg-amber-500/10 px-4 py-2 text-sm text-amber-200">
        Modèles absents : lancez <code>./jideo install</code>.
      </div>
      <main class="mx-auto grid max-w-7xl gap-6 p-4 lg:grid-cols-[1fr_380px]">
        <Workshop />
        <HistoryList @open="opened = $event" />
      </main>
      <ResultView v-if="opened" :job="opened" @close="opened = null" />
    </template>
  </div>
</template>
