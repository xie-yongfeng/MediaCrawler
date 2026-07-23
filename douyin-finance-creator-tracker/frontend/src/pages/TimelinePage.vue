<script setup>
import { computed } from "vue";
import { FileText, RefreshCw } from "lucide-vue-next";
import VideoPlayer from "../components/video/VideoPlayer.vue";
import { extractContentOverview } from "../utils/transcript";

const props = defineProps({
  creator: { type: Object, default: null },
  timeline: { type: Array, default: () => [] },
  filter: { type: String, default: "all" },
  search: { type: String, default: "" },
  syncState: { type: Object, required: true },
  isCreatorSyncing: { type: Function, required: true },
});
const emit = defineEmits([
  "sync",
  "add",
  "detail",
  "transcript",
  "update:filter",
  "update:search",
]);

const timelineGroups = computed(() => {
  const groups = new Map();
  for (const video of props.timeline) {
    const date = video.published_at?.slice(0, 10) || "";
    if (!groups.has(date)) groups.set(date, []);
    groups.get(date).push(video);
  }
  return [...groups].map(([date, videos]) => ({
    date,
    label: timelineDateLabel(date),
    videos,
  }));
});

function timelineDateLabel(dateText) {
  const value = new Date(`${dateText}T00:00:00`);
  const now = new Date();
  if (Number.isNaN(value.getTime())) return dateText;
  const weekday = [
    "星期日",
    "星期一",
    "星期二",
    "星期三",
    "星期四",
    "星期五",
    "星期六",
  ][value.getDay()];
  if (
    value.getFullYear() === now.getFullYear() &&
    value.getMonth() === now.getMonth()
  )
    return `${value.getDate()}日 ${weekday}`;
  if (value.getFullYear() === now.getFullYear())
    return `${value.getMonth() + 1}月${value.getDate()}日 ${weekday}`;
  return `${value.getFullYear()}年${
    value.getMonth() + 1
  }月${value.getDate()}日 ${weekday}`;
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
  <div class="timeline-page">
    <div class="page-header">
      <div>
        <p class="eyebrow">CREATOR TIMELINE</p>
        <h1>{{ creator ? `${creator.name} 的视频时间线` : "选择一个博主" }}</h1>
        <p v-if="creator">
          {{ creator.platform }} ·
          {{
            creator.last_synced ? `最近同步 ${creator.last_synced}` : "尚未同步"
          }}
        </p>
      </div>
      <button
        v-if="creator"
        class="button secondary sync-button"
        :class="{
          queued:
            syncState.status === 'running' && !isCreatorSyncing(creator.id),
        }"
        :disabled="syncState.status === 'running'"
        @click="emit('sync', creator.id)"
      >
        <RefreshCw
          :size="15"
          :class="{ spin: isCreatorSyncing(creator.id) }"
        />同步
      </button>
    </div>
    <template v-if="creator"
      ><div class="timeline-toolbar glass">
        <div class="filter-tabs">
          <button
            v-for="item in [
              { id: 'all', label: '全部' },
              { id: 'critical', label: '临盘' },
            ]"
            :key="item.id"
            :class="{ active: filter === item.id }"
            @click="emit('update:filter', item.id)"
          >
            {{ item.label }}
          </button>
        </div>
        <label class="search-box"
          ><FileText :size="16" /><input
            :value="search"
            placeholder="搜索标题或字幕"
            @input="emit('update:search', $event.target.value)"
        /></label>
      </div>
      <section class="timeline-list glass">
        <section
          v-for="group in timelineGroups"
          :key="group.date"
          class="timeline-day"
        >
          <header class="timeline-day-heading">
            <span>{{ group.label }}</span
            ><i></i>
          </header>
          <article
            v-for="video in group.videos"
            :key="video.id"
            class="timeline-row"
          >
            <div class="rail">
              <span
                class="timeline-node"
                :class="{ hot: video.is_critical }"
              ></span>
            </div>
            <div class="timeline-content">
              <div class="video-top">
                <span v-if="video.is_critical" class="status-tag critical"
                  >临盘发布</span
                ><b>{{ video.published_at }} 发布 · {{ duration(video.duration_seconds) }}</b>
              </div>
              <div class="timeline-work">
                <section class="timeline-source">
                  <div class="timeline-media">
                    <VideoPlayer
                      :src="video.playback_url"
                      :poster="video.cover_url"
                      :source-url="video.source_url"
                      :title="video.title"
                    />
                  </div>
                  <h3>{{ video.title }}</h3>
                  <p v-if="video.summary && video.summary !== video.title">
                    {{ video.summary }}
                  </p>
                  <p
                    v-if="extractContentOverview(video.transcript_markdown)"
                    class="timeline-overview"
                  >
                    <b>内容综述：</b>{{
                      extractContentOverview(video.transcript_markdown)
                    }}
                  </p>
                </section>
                <aside class="timeline-transcript transcript-panel">
                  <div class="transcript-heading">
                    <div><h3>字幕</h3></div>
                  </div>
                  <p v-if="video.transcript_text" class="transcript-text">
                    {{ video.transcript_text }}
                  </p>
                  <div v-else class="transcript-empty">
                    <FileText :size="25" /><b>{{
                      transcriptText(
                        video.transcript_status,
                        video.transcript_progress
                      )
                    }}</b>
                    <p>字幕完成后将仅保存文字内容。</p>
                    <button
                      class="button secondary compact"
                      :disabled="video.transcript_status === 'processing'"
                      @click="emit('transcript', video)"
                    >
                      {{
                        video.transcript_status === "processing"
                          ? `识别中 ${video.transcript_progress || 0}%`
                          : "识别"
                      }}
                    </button>
                  </div>
                </aside>
              </div>
              <div class="timeline-bottom">
                <button class="button secondary compact" @click="emit('detail', video)">
                  详情
                </button>
              </div>
            </div>
          </article>
        </section>
        <div v-if="!timelineGroups.length" class="empty">
          没有符合筛选条件的已入库内容。
        </div>
      </section></template
    >
    <section v-else class="empty-panel glass">
      <p>从观察清单添加博主后即可查看时间线。</p>
      <button class="button primary" @click="emit('add')">添加博主</button>
    </section>
  </div>
</template>

<style scoped>
.timeline-toolbar {
  margin: 0 4px 14px;
  padding: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-radius: 20px;
}
.timeline-list {
  padding: 18px;
  border-radius: 20px;
}
.timeline-row {
  display: grid;
  grid-template-columns: 24px 1fr;
}
.rail {
  position: relative;
}
.rail::after {
  content: "";
  position: absolute;
  top: 24px;
  bottom: -4px;
  left: 6px;
  width: 1px;
  background: var(--glass-border);
}
.timeline-row:last-of-type .rail::after {
  display: none;
}
.timeline-node {
  position: relative;
  z-index: 1;
  display: block;
  width: 14px;
  height: 14px;
  margin-top: 8px;
  border: 3px solid #a5b6b0;
  border-radius: 9999px;
  background: #5a6965;
}
.timeline-node.hot {
  border-color: #c5ffdd;
  background: var(--brand);
  box-shadow: 0 0 14px rgba(138, 255, 196, 0.48);
}
.timeline-content {
  padding: 4px 0 22px;
}
.timeline-content h3 {
  margin: 7px 0;
  color: var(--heading);
  font-size: 15px;
  line-height: 1.45;
  font-weight: 500;
}
.timeline-content p {
  margin: 0 0 9px;
  color: var(--body);
  font-size: 12px;
  line-height: 1.65;
}
.timeline-content .timeline-overview {
  color: var(--body-subtle);
}
.timeline-overview b {
  color: var(--body);
}
.timeline-bottom {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 18px;
}
.timeline-day { display: grid; gap: 2px; }
.timeline-day-heading { display: flex; align-items: center; gap: 12px; padding: 16px 0 10px; color: var(--brand); font-size: 19px; font-weight: 700; letter-spacing: 0.01em; }
.timeline-day-heading i { height: 1px; flex: 1; background: var(--glass-border); }
.timeline-media { width: min(100%, 360px); margin: 12px 0; }
.timeline-media .video-player { border-radius: 12px; }
.timeline-work { display: grid; grid-template-columns: minmax(280px, 42%) minmax(0, 1fr); gap: 18px; align-items: stretch; }
.timeline-source { min-width: 0; }
.timeline-source h3 { margin: 8px 0; }
.timeline-source .timeline-media { width: 100%; margin: 12px 0; }
.timeline-transcript { display: flex; flex-direction: column; justify-content: flex-start; margin-top: 12px; min-height: 150px; padding: 12px; border: 1px solid var(--glass-border); overflow: auto; }
.timeline-transcript .transcript-text { margin: 0 !important; }
@media (max-width: 650px) {
  .timeline-toolbar {
    align-items: stretch;
    flex-direction: column;
  }
  .filter-tabs {
    overflow: auto;
  }
  .search-box input {
    width: 100%;
  }
  .timeline-transcript {
    display: none;
    margin-top: 0;
  }
}
@media (max-width: 860px) {
  .timeline-work {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .timeline-media {
    width: 100%;
  }

  .timeline-content {
    min-width: 0;
  }

  .timeline-bottom {
    margin-top: 0;
  }
}
</style>
