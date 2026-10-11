<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { api, ApiError, type FaceDetection, type Media } from '../api'
import { useJobs } from '../composables/useJobs'
import DropZone from './DropZone.vue'
import FacePicker from './FacePicker.vue'

const PHOTO_ACCEPT = '.jpg,.jpeg,.png,.webp'
const { upsert } = useJobs()

interface Side { media: Media | null; detection: FaceDetection | null; selected: string[]; busy: boolean }
const blank = (): Side => ({ media: null, detection: null, selected: [], busy: false })
const source = reactive<Side>(blank())
const target = reactive<Side>(blank())
const options = reactive({ allFaces: true, enhance: true, watermark: true })
const error = ref<string | null>(null)
const launching = ref(false)

watch(() => target.selected.length, (n) => { if (n) options.allFaces = false })

function fail(e: unknown) {
  error.value = e instanceof ApiError ? e.message : String(e)
}

async function upload(side: Side, file: File, multiple: boolean) {
  error.value = null
  Object.assign(side, blank(), { busy: true })
  try {
    side.media = await api.uploadMedia(file)
    side.detection = await api.detectFaces(side.media.id)
    if (!side.detection.faces.length) error.value = 'Aucun visage détecté sur cette image.'
    else if (!multiple && side.detection.faces.length === 1) side.selected = [side.detection.faces[0].id]
  } catch (e) {
    fail(e)
  } finally {
    side.busy = false
  }
}

const canRun = computed(
  () =>
    source.selected.length === 1 &&
    !!target.media &&
    !!target.detection?.faces.length &&
    (options.allFaces || target.selected.length > 0) &&
    !launching.value,
)

async function run() {
  launching.value = true
  error.value = null
  try {
    upsert(
      await api.createJob({
        type: 'photo',
        source_face_id: source.selected[0],
        target_media_id: target.media!.id,
        target_face_ids: options.allFaces ? 'all' : target.selected,
        enhance: options.enhance,
        watermark: options.watermark,
      }),
    )
  } catch (e) {
    fail(e)
  } finally {
    launching.value = false
  }
}
</script>

<template>
  <section class="space-y-6">
    <p v-if="error" data-testid="error" class="rounded-lg bg-red-500/10 p-3 text-sm text-red-300">{{ error }}</p>
    <div class="grid gap-6 md:grid-cols-2">
      <div class="space-y-3">
        <h2 class="font-semibold">1. Visage source</h2>
        <DropZone label="Photo du visage à poser" :accept="PHOTO_ACCEPT" :busy="source.busy" testid="source-input"
          @file="upload(source, $event, false)" />
        <template v-if="source.media && source.detection">
          <FacePicker v-model="source.selected" :src="source.media.url" :detection="source.detection"
            :multiple="false" testid="source" />
          <p v-if="source.detection.faces.length > 1 && !source.selected.length" class="text-xs text-amber-300">
            Plusieurs visages : cliquez sur celui à utiliser.
          </p>
        </template>
      </div>
      <div class="space-y-3">
        <h2 class="font-semibold">2. Photo cible</h2>
        <DropZone label="Photo à modifier" :accept="PHOTO_ACCEPT" :busy="target.busy" testid="target-input"
          @file="upload(target, $event, true)" />
        <template v-if="target.media && target.detection">
          <FacePicker v-model="target.selected" :src="target.media.url" :detection="target.detection"
            :multiple="true" testid="target" />
          <label class="flex items-center gap-2 text-sm">
            <input v-model="options.allFaces" type="checkbox" data-testid="all-faces" /> Remplacer tous les visages
          </label>
        </template>
      </div>
    </div>
    <div class="space-y-3 rounded-xl border border-zinc-800 p-4">
      <h2 class="font-semibold">3. Options</h2>
      <label class="flex items-center gap-2 text-sm">
        <input v-model="options.enhance" type="checkbox" /> Améliorer le visage (GFPGAN)
      </label>
      <label class="flex items-center gap-2 text-sm">
        <input v-model="options.watermark" type="checkbox" /> Filigrane visible « Jideo »
      </label>
      <button class="btn-primary" :disabled="!canRun" data-testid="launch" @click="run">Lancer le swap</button>
    </div>
  </section>
</template>
