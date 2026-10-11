<script setup lang="ts">
import { ref } from 'vue'

defineProps<{ before: string; after: string }>()
const position = ref(50)
</script>

<template>
  <div class="relative inline-block max-w-full select-none overflow-hidden rounded-lg" data-testid="before-after">
    <img :src="after" class="block max-h-[70vh] max-w-full" alt="Après" />
    <img
      :src="before"
      class="absolute inset-0 h-full w-full"
      :style="{ clipPath: `inset(0 ${100 - position}% 0 0)` }"
      alt="Avant"
    />
    <div class="pointer-events-none absolute inset-y-0 w-0.5 bg-white/80" :style="{ left: `${position}%` }" />
    <input
      v-model.number="position"
      type="range"
      min="0"
      max="100"
      class="absolute inset-x-0 bottom-3 mx-auto w-2/3"
      aria-label="Comparer avant et après"
    />
  </div>
</template>
