<script setup>
import { computed, ref } from "vue";
import { ExternalLink, FileText, X } from "lucide-vue-next";
import VideoPlayer from "./video/VideoPlayer.vue";
import { extractContentOverview } from "../utils/transcript";

const props = defineProps({ detail: { type: Object, default: null } });
const emit = defineEmits(["close", "source", "transcript"]);
const transcriptView = ref("text");
const transcriptOverview = computed(() =>
  extractContentOverview(props.detail?.video?.transcript_markdown)
);

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
function renderMarkdown(value) {
  const escaped = String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return escaped
    .split("\n")
    .map((line) => {
      if (/^###\s+/.test(line)) return `<h3>${line.slice(4)}</h3>`;
      if (/^##\s+/.test(line)) return `<h2>${line.slice(3)}</h2>`;
      if (/^#\s+/.test(line)) return `<h1>${line.slice(2)}</h1>`;
      if (/^-\s+/.test(line)) return `<li>${line.slice(2)}</li>`;
      return `<p>${line
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/`(.+?)`/g, "<code>$1</code>")}</p>`;
    })
    .join("");
}
</script>

<template>
  <div v-if="detail" class="modal-scrim" @click.self="emit('close')">
    <section
      class="detail-modal media-detail-modal glass"
      role="dialog"
      aria-modal="true"
      aria-label="视频详情"
    >
      <button
        class="icon-button close-detail"
        aria-label="关闭详情"
        @click="emit('close')"
      >
        <X :size="18" />
      </button>
      <span v-if="detail.video.is_critical" class="status-tag critical"
        >临盘发布</span
      >
      <h2>{{ detail.video.title }}</h2>
      <!-- <p class="detail-meta">
        时长 {{ duration(detail.video.duration_seconds) }}
      </p> -->
      <p class="detail-meta">
        {{ detail.video.creator_name }} · {{ detail.video.published_at }} 发布 · {{ duration(detail.video.duration_seconds) }}
      </p>
      <div class="detail-grid media-detail-grid">
        <section class="source-panel player-panel">
          <VideoPlayer
            :src="detail.video.playback_url"
            :poster="detail.video.cover_url"
            :source-url="detail.video.source_url"
            :title="detail.video.title"
          />
          <div class="player-actions">
            <button
              class="button secondary compact"
              @click="emit('source', detail.video)"
            >
              原平台打开 <ExternalLink :size="15" /></button
            ><span class="source-label">{{
              detail.video.playback_url ? "原始流媒体地址" : "仅原平台可播放"
            }}</span>
          </div>
          <div v-if="transcriptOverview" class="structured-reading">
            <h3>内容综述</h3>
            <p>{{ transcriptOverview }}</p>
          </div>
          <div class="structured-reading">
            <h3>风险与不确定性</h3>
            <p>{{ detail.video.risk_note }}</p>
          </div>
        </section>
        <section class="transcript-panel">
          <div class="transcript-heading">
            <div>
              <h3>{{ transcriptView === "text" ? "字幕" : "AI 总结" }}</h3>
            </div>
            <div class="filter-tabs">
              <button
                :class="{ active: transcriptView === 'text' }"
                @click="transcriptView = 'text'"
              >
                字幕</button
              ><button
                :class="{ active: transcriptView === 'markdown' }"
                @click="transcriptView = 'markdown'"
              >
                总结
              </button>
            </div>
          </div>
          <p
            v-if="transcriptView === 'text' && detail.video.transcript_text"
            class="transcript-text"
          >
            {{ detail.video.transcript_text }}
          </p>
          <article
            v-else-if="
              transcriptView === 'markdown' && detail.video.transcript_markdown
            "
            class="transcript-text markdown-text"
            v-html="renderMarkdown(detail.video.transcript_markdown)"
          ></article>
          <div v-else class="transcript-empty">
            <FileText :size="25" /><b>{{
              transcriptView === "text"
                ? transcriptText(
                    detail.video.transcript_status,
                    detail.video.transcript_progress
                  )
                : "未生成 AI 总结"
            }}</b>
            <p>字幕完成后将仅保存文字内容。</p>
            <button
              v-if="transcriptView === 'text'"
              class="button secondary compact"
              :disabled="detail.video.transcript_status === 'processing'"
              @click="emit('transcript', detail.video)"
            >
              {{
                detail.video.transcript_status === "processing"
                  ? `识别中 ${detail.video.transcript_progress || 0}%`
                  : "识别"
              }}
            </button>
          </div>
        </section>
      </div>
    </section>
  </div>
</template>
