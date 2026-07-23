<script setup>
import { computed, ref, watch } from "vue";
import { ExternalLink, Play } from "lucide-vue-next";

const props = defineProps({
  src: { type: String, default: "" },
  poster: { type: String, default: "" },
  sourceUrl: { type: String, required: true },
  title: { type: String, default: "原视频" },
});
const emit = defineEmits(["playback-error"]);
const failed = ref(false);
const playable = computed(() => Boolean(props.src) && !failed.value);

watch(
  () => props.src,
  () => {
    failed.value = false;
  }
);
function handleError() {
  failed.value = true;
  emit("playback-error");
}
function openSource() {
  window.open(props.sourceUrl, "_blank", "noopener,noreferrer");
}
</script>

<template>
  <section class="video-player" :aria-label="`${title} 播放器`">
    <video
      v-if="playable"
      :src="src"
      :poster="poster || undefined"
      controls
      playsinline
      preload="metadata"
      @error="handleError"
    >
      此浏览器不支持视频播放。
    </video>
    <div
      v-else
      class="video-fallback"
      :style="
        poster
          ? {
              backgroundImage: `linear-gradient(rgba(3,10,12,.3), rgba(3,10,12,.78)), url(${poster})`,
            }
          : undefined
      "
    >
      <span class="fallback-icon"><Play :size="22" fill="currentColor" /></span>
      <div>
        <b>原视频受平台限制</b>
        <p>请在原平台继续观看与核对。</p>
      </div>
      <button class="player-source" type="button" @click="openSource">
        在原平台打开 <ExternalLink :size="15" />
      </button>
    </div>
  </section>
</template>

<style scoped>
.video-player {
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--glass-border-subtle);
  border-radius: 20px;
  background: var(--bg);
  aspect-ratio: 16/9;
}
.video-player video {
  display: block;
  width: 100%;
  height: 100%;
  background: var(--bg);
  object-fit: contain;
}
.video-fallback {
  width: 100%;
  height: 100%;
  padding: 24px;
  display: grid;
  align-content: center;
  justify-items: center;
  gap: 12px;
  color: var(--heading);
  background-color: var(--surface);
  background-position: center;
  background-size: contain;
  background-repeat: no-repeat;
  text-align: center;
}
.fallback-icon {
  display: grid;
  width: 48px;
  height: 48px;
  place-items: center;
  border-radius: 9999px;
  color: #062116;
  background: var(--brand);
  box-shadow: var(--shadow-xs);
}
.video-fallback b {
  font-size: 14px;
  font-weight: 500;
}
.video-fallback p {
  max-width: 260px;
  margin: 5px 0 0;
  color: var(--body);
  font-size: 11px;
  line-height: 1.6;
}
.player-source {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--glass-border);
  border-radius: 20px;
  padding: 8px 12px;
  color: var(--heading);
  background: var(--glass-bg);
  font: 500 12px "Google Sans", sans-serif;
  backdrop-filter: blur(20px) !important;
}
.player-source:hover {
  color: var(--brand);
  background: var(--glass-bg-hover);
}
.player-source:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 2px;
}
@media (max-width: 760px) {
  .fallback-icon {
    display: none;
  }
}
</style>