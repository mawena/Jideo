<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { api, ApiError, type FaceDetection, type JobType, type Media } from '../api'
import { useJobs } from '../composables/useJobs'
import DropZone from './DropZone.vue'
import FacePicker from './FacePicker.vue'
import VideoTimeline from './VideoTimeline.vue'

const PHOTO_ACCEPT = '.jpg,.jpeg,.png,.webp'
const VIDEO_ACCEPT = '.mp4,.mov,.webm,.mkv'
const { upsert } = useJobs()

interface Side { media: Media | null; detection: FaceDetection | null; selected: string[]; busy: boolean; t: number }
const blank = (): Side => ({ media: null, detection: null, selected: [], busy: false, t: 0 })
const source = reactive<Side>(blank())
const target = reactive<Side>(blank())
const trim = reactive({ start: 0, end: 0 })
const options = reactive({ allFaces: true, enhance: true, watermark: true, downscale: false, threshold: 0.35 })
const error = ref<string | null>(null)
const launching = ref(false)

// Jeton de requête par côté : une réponse tardive d'une requête dépassée est ignorée.
const tokens = { source: 0, target: 0 }
const nextToken = (side: Side) => ++tokens[side === source ? 'source' : 'target']
const isCurrent = (side: Side, token: number) => tokens[side === source ? 'source' : 'target'] === token

const isVideo = computed(() => target.media?.kind === 'video')
const targetImage = computed(() => {
  if (!target.media || !target.detection) return ''
  return isVideo.value ? api.frameUrl(target.media.id, target.detection.t) : target.media.url
})

watch(() => target.selected.length, (n) => { if (n) options.allFaces = false })

function fail(e: unknown) {
  error.value = e instanceof ApiError ? e.message : String(e)
}

async function detect(side: Side, multiple: boolean) {
  const token = nextToken(side)
  side.busy = true
  side.detection = null
  side.selected = []
  try {
    const detection = await api.detectFaces(side.media!.id, side.t)
    if (!isCurrent(side, token)) return
    side.detection = detection
    if (!detection.faces.length) error.value = 'Aucun visage détecté sur cette image.'
    else if (!multiple && detection.faces.length === 1) side.selected = [detection.faces[0].id]
  } catch (e) {
    if (isCurrent(side, token)) fail(e)
  } finally {
    if (isCurrent(side, token)) side.busy = false
  }
}

async function upload(side: Side, file: File, multiple: boolean) {
  const token = nextToken(side)
  error.value = null
  Object.assign(side, blank(), { busy: true })
  let media: Media
  try {
    media = await api.uploadMedia(file)
  } catch (e) {
    if (isCurrent(side, token)) {
      side.busy = false
      fail(e)
    }
    return
  }
  if (!isCurrent(side, token)) return
  side.media = media
  if (side === target) {
    const video = media.kind === 'video'
    trim.start = 0
    trim.end = video ? media.duration ?? 0 : 0
    options.enhance = !video // GFPGAN est très lent en vidéo sur CPU
    options.allFaces = true
  }
  await detect(side, multiple)
}

function pickFrame(t: number) {
  error.value = null
  target.t = t
  detect(target, true)
}

const canRun = computed(
  () =>
    source.selected.length === 1 &&
    !!target.media &&
    !!target.detection?.faces.length &&
    (options.allFaces || target.selected.length > 0) &&
    !launching.value,
)

async function run(type: JobType) {
  launching.value = true
  error.value = null
  try {
    upsert(
      await api.createJob({
        type,
        source_face_id: source.selected[0],
        target_media_id: target.media!.id,
        target_face_ids: options.allFaces ? 'all' : target.selected,
        enhance: options.enhance,
        watermark: options.watermark,
        similarity_threshold: options.threshold,
        t: target.detection?.t ?? 0,
        trim: type === 'video' ? { start: trim.start, end: trim.end } : undefined,
        downscale_720p: options.downscale,
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
        <h2 class="font-semibold">2. Photo ou vidéo cible</h2>
        <DropZone label="Photo ou vidéo à modifier" :accept="`${PHOTO_ACCEPT},${VIDEO_ACCEPT}`" :busy="target.busy"
          testid="target-input" @file="upload(target, $event, true)" />
        <VideoTimeline v-if="target.media && isVideo" v-model:start="trim.start" v-model:end="trim.end"
          :src="target.media.url" :media-id="target.media.id" :duration="target.media.duration ?? 0" @pick="pickFrame" />
        <template v-if="target.media && target.detection">
          <p v-if="isVideo" class="text-xs text-zinc-400">
            Visages détectés à {{ target.detection.t.toFixed(1) }} s — les visages choisis seront suivis dans toute la vidéo.
          </p>
          <FacePicker v-model="target.selected" :src="targetImage" :detection="target.detection"
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
        <span v-if="isVideo" class="text-zinc-500">— environ 2 à 2,5 fois plus lent</span>
      </label>
      <label class="flex items-center gap-2 text-sm">
        <input v-model="options.watermark" type="checkbox" /> Filigrane visible « Jideo »
      </label>
      <label v-if="isVideo" class="flex items-center gap-2 text-sm">
        <input v-model="options.downscale" type="checkbox" /> Réduire à 720p (plus rapide)
      </label>
      <details class="text-sm">
        <summary class="cursor-pointer text-zinc-400">Avancé</summary>
        <label class="mt-2 block">
          Seuil de ressemblance pour retrouver les visages : {{ options.threshold.toFixed(2) }}
          <input v-model.number="options.threshold" type="range" min="0.1" max="0.8" step="0.05" class="block w-full" />
        </label>
      </details>
      <div class="flex flex-wrap gap-3">
        <template v-if="isVideo">
          <button class="btn" :disabled="!canRun" data-testid="preview" @click="run('preview')">Aperçu de cette image</button>
          <button class="btn-primary" :disabled="!canRun" data-testid="launch" @click="run('video')">Lancer le rendu vidéo</button>
        </template>
        <button v-else class="btn-primary" :disabled="!canRun" data-testid="launch" @click="run('photo')">Lancer le swap</button>
      </div>
    </div>
  </section>
</template>
