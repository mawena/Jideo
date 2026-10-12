<script setup lang="ts">
import { ref } from 'vue'
import { api, ApiError } from '../api'

const emit = defineEmits<{ success: [] }>()
const password = ref('')
const error = ref<string | null>(null)
const busy = ref(false)

async function submit() {
  busy.value = true
  error.value = null
  try {
    await api.login(password.value)
    emit('success')
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : String(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <form class="mx-auto mt-24 max-w-sm space-y-4 rounded-xl border border-zinc-800 bg-zinc-900 p-6" @submit.prevent="submit">
    <h1 class="text-xl font-bold">Jideo</h1>
    <label class="block space-y-1 text-sm">
      <span>Mot de passe</span>
      <input v-model="password" type="password" autocomplete="current-password" required
        class="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2" />
    </label>
    <p v-if="error" class="text-sm text-red-300">{{ error }}</p>
    <button class="btn-primary w-full" :disabled="busy">Se connecter</button>
  </form>
</template>
