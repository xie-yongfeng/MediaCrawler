<script setup>
import { computed } from "vue";
import { ExternalLink, FileText, Play } from "lucide-vue-next";
import { extractContentOverview } from "../utils/transcript";

const props = defineProps({ video: { type: Object, required: true } });
const emit = defineEmits(["detail", "source"]);
const transcriptOverview = computed(() =>
  extractContentOverview(props.video.transcript_markdown)
);

function avatarUrl(value) {
  return /^https?:\/\//i.test(value || "") ? value : "";
}
function avatarText(avatar, name) {
  return avatarUrl(avatar)
    ? (name || "").trim().slice(0, 1)
    : (avatar || name || "博").trim().slice(0, 1);
}
function time(value) {
  return value?.slice(11, 16) || value || "—";
}
function duration(value) {
  return value
    ? `时长 ${Math.floor(value / 60)}:${String(value % 60).padStart(2, "0")}`
    : "时长待同步";
}
function transcriptText(status, progress = 0) {
  const label =
    {
      completed: "字幕已保存",
      processing: "转写中",
      failed: "转写失败",
      unavailable: "暂未配置转写服务",
    }[status] || status;
  return status === "processing"
    ? `${label} ${Math.max(0, Math.min(100, Number(progress) || 0))}%`
    : label;
}
</script>

<template>
  <article class="video-card glass" :class="{ critical: video.is_critical }">
    <div class="video-top">
      <span v-if="video.is_critical" class="status-tag critical">临盘发布</span>
      <span class="avatar" :style="{ '--avatar': video.creator_color }">
        <img
          v-if="avatarUrl(video.creator_avatar)"
          :src="video.creator_avatar"
          :alt="video.creator_name"
        />
        <template v-else>{{
          avatarText(video.creator_avatar, video.creator_name)
        }}</template>
      </span>
      <div class="video-author">
        <b>{{ video.creator_name }}</b>
        <span v-if="video.topic" class="topic-label">{{ video.topic }}</span>
      </div>
      <span>{{ time(video.published_at) }} 发布 · {{ duration(video.duration_seconds) }}</span>
    </div>
    <div class="video-main">
      <button
        class="video-thumbnail"
        type="button"
        aria-label="查看作品"
        @click="emit('detail', video)"
      >
        <img
          v-if="video.cover_url"
          :src="video.cover_url"
          alt="视频封面"
        /><span v-else class="thumbnail-placeholder"><Play :size="20" /></span
        ><span class="thumbnail-play"
          ><Play :size="14" fill="currentColor"
        /></span>
      </button>
      <div class="video-copy">
        <h3 v-if="video.title">{{ video.title }}</h3>
        <p v-if="video.summary && video.summary !== video.title">
          {{ video.summary }}
        </p>
        <p v-if="transcriptOverview" class="video-overview">
          <b>内容综述：</b>{{ transcriptOverview }}
        </p>
        <small
          ><FileText :size="12" />{{
            transcriptText(video.transcript_status, video.transcript_progress)
          }}
          <!-- <span v-if="video.playback_url" class="playback-ready"
            >可播放</span
          > -->
          </small
        >
      </div>
      <div class="card-actions">
        <button
          class="icon-button"
          aria-label="打开原视频"
          @click="emit('source', video)"
        >
          <ExternalLink :size="17" /></button
        ><button
          class="button secondary compact"
          @click="emit('detail', video)"
        >
          详情
        </button>
      </div>
    </div>
  </article>
</template>

<style scoped>
.video-card {
  height: 100%;
  padding: 16px;
  border-radius: 20px;
  transition: background 0.2s, border-color 0.2s;
}
.video-card:hover {
  background: var(--glass-bg-hover);
}
.video-card.critical {
  border-left: 3px solid var(--brand);
}
.video-main {
  display: grid;
  grid-template-columns: 132px minmax(0, 1fr) auto;
  align-items: start;
  gap: 14px;
  margin-top: 12px;
}
.video-copy {
  min-width: 0;
  flex: 1;
}
.video-author {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
}
.video-thumbnail {
  position: relative;
  display: grid;
  width: 132px;
  height: 100%;
  aspect-ratio: 9/11;
  place-items: center;
  overflow: hidden;
  border: 1px solid var(--glass-border);
  border-radius: 12px;
  color: var(--brand);
  background: var(--glass-bg);
  cursor: pointer;
}
.video-thumbnail img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.thumbnail-placeholder {
  display: grid;
  width: 100%;
  height: 100%;
  place-items: center;
  background: var(--surface);
}
.thumbnail-play {
  position: absolute;
  display: grid;
  width: 30px;
  height: 30px;
  place-items: center;
  border: 1px solid var(--glass-border);
  border-radius: 9999px;
  color: var(--brand);
  background: var(--glass-bg);
  box-shadow: var(--shadow-xs);
  backdrop-filter: blur(20px) !important;
}
.video-thumbnail:hover .thumbnail-play {
  color: var(--heading);
  background: var(--brand);
}
.video-thumbnail:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 2px;
}
.video-top .video-author {
  gap: 7px;
}
.video-top .avatar {
  width: 24px;
  height: 24px;
  flex-basis: 24px;
  border-radius: 8px;
  font-size: 10px;
}
.video-copy h3 {
  margin-top: 0;
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  font-size: 15px;
  line-height: 1.45;
}
.video-copy p {
  display: -webkit-box;
  margin: 0 0 9px;
  overflow: hidden;
  color: var(--body);
  font-size: 12px;
  line-height: 1.65;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}
.video-copy .video-overview {
  margin-top: -3px;
  color: var(--body-subtle);
  -webkit-line-clamp: 8;
}
.video-overview b {
  color: var(--body);
}
.video-copy small {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--body-subtle);
  font-size: 10px;
}
.card-actions {
  display: flex;
  align-items: center;
  gap: 7px;
}
.playback-ready {
  margin-left: 6px;
  color: var(--brand);
}

@media (max-width: 860px) {
  .video-main {
    grid-template-columns: 104px minmax(0, 1fr);
    gap: 0 10px;
    align-items: flex-start;
  }
  .video-thumbnail {
    width: 104px;
  }
  .card-actions {
    grid-column: 2;
    grid-row: 2;
    justify-content: flex-end;
    flex-direction: row;
  }
  .video-copy h3 {
    font-size: 13px;
  }
}
</style>
