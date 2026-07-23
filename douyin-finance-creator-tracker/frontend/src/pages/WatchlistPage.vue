<script setup>
import { Clock3, Pencil, Plus, RefreshCw, Trash2 } from "lucide-vue-next";

defineProps({
  creators: { type: Array, default: () => [] },
  syncState: { type: Object, required: true },
  isCreatorSyncing: { type: Function, required: true },
});

const emit = defineEmits(["add", "sync", "timeline", "edit", "delete"]);

function avatarUrl(value) {
  return /^https?:\/\//i.test(value || "") ? value : "";
}
function avatarText(avatar, name) {
  return avatarUrl(avatar)
    ? (name || "").trim().slice(0, 1)
    : (avatar || name || "博").trim().slice(0, 1);
}
function syncTime(value) {
  return value
    ? `最近同步 ${value.replace("T", " ").slice(0, 16)}`
    : "待首次同步";
}
</script>

<template>
  <div class="watchlist-page">
    <div class="page-header">
    <div>
      <p class="eyebrow">WATCHLIST</p>
      <h1>创作者观察清单</h1>
      <p>
        仅添加你提供的主页链接或 ID；重点标记只影响信息排序，不表示内容更可靠。
      </p>
    </div>
    <button class="button primary" @click="emit('add')">
      <Plus :size="16" />添加博主
    </button>
  </div>
  <section class="watchlist-grid">
    <article
      v-for="creator in creators"
      :key="creator.id"
      class="watch-card glass"
      :class="{ syncing: isCreatorSyncing(creator.id) }"
    >
      <div class="watch-card-top">
        <span class="avatar large" :style="{ '--avatar': creator.color }"
          ><img
            v-if="avatarUrl(creator.avatar)"
            :src="creator.avatar"
            :alt="creator.name"
          /><template v-else>{{
            avatarText(creator.avatar, creator.name)
          }}</template></span
        >
        <div>
          <h2>{{ creator.name }}</h2>
          <p>
            {{ creator.platform }} ·
            {{ creator.priority ? "重点监测" : "常规监测" }}
          </p>
        </div>
        <div class="watch-status">
          <span
            class="source-chip"
            :class="creator.source_status === '已同步' ? 'success' : ''"
            >{{ creator.source_status }}</span
          ><span class="watch-last-sync">{{
            syncTime(creator.last_synced)
          }}</span>
        </div>
      </div>
      <p class="id-line">{{ creator.profile_url }}</p>
      <div v-if="creator.tags.length" class="tag-list">
        <span v-for="tag in creator.tags" :key="tag" class="topic-label">{{
          tag
        }}</span>
      </div>
      <div class="watch-metrics">
        <span
          >总作品数 <b>{{ creator.video_count || 0 }}</b></span
        >
      </div>
      <p class="sync-note">{{ creator.source_message || "等待同步。" }}</p>
      <div class="watch-actions">
        <button
          class="button secondary compact sync-button"
          :class="{
            queued:
              syncState.status === 'running' && !isCreatorSyncing(creator.id),
          }"
          :disabled="syncState.status === 'running'"
          @click="emit('sync', creator.id)"
        >
          <RefreshCw
            :size="14"
            :class="{ spin: isCreatorSyncing(creator.id) }"
          />同步</button
        ><button
          class="button secondary compact"
          @click="emit('timeline', creator.id)"
        >
          <Clock3 :size="14" />时间线</button
        ><button
          class="icon-button"
          aria-label="编辑博主"
          @click="emit('edit', creator)"
        >
          <Pencil :size="15" /></button
        ><button
          class="icon-button danger"
          aria-label="删除博主"
          @click="emit('delete', creator)"
        >
          <Trash2 :size="15" />
        </button>
      </div>
    </article>
    <div v-if="!creators.length" class="empty-panel glass">
      <p>尚未添加观察来源。</p>
    </div>
    </section>
  </div>
</template>

<style scoped>
.watchlist-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.watch-card {
  padding: 18px;
  border-radius: 20px;
}
.watch-card.syncing {
  animation: sync-card-border 1.4s ease-in-out infinite;
  border-color: rgba(138, 255, 196, 0.82);
}
.watch-card-top {
  justify-content: space-between;
}
.watch-card h2 {
  margin: 0 0 4px;
  font-size: 16px;
  font-weight: 500;
}
.watch-card p {
  margin: 0;
  color: var(--body);
  font-size: 11px;
}
.source-chip {
  color: var(--warning);
  background: rgba(251, 191, 36, 0.12);
  border-color: rgba(251, 191, 36, 0.15);
}
.source-chip.success {
  color: var(--brand);
  background: rgba(138, 255, 196, 0.12);
  border-color: rgba(138, 255, 196, 0.15);
}
.id-line {
  overflow: hidden;
  margin: 16px 0 !important;
  color: var(--body-subtle) !important;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tag-list {
  min-height: 22px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.sync-note {
  min-height: 36px;
  margin: 13px 0 !important;
  line-height: 1.55;
}
.watch-actions {
  margin-top: 0;
  padding-top: 12px;
  display: flex;
  align-items: center;
  gap: 7px;
  border-top: 1px solid var(--glass-border-subtle);
}
.watch-status { margin-left: auto; display: flex; align-items: center; justify-content: flex-end; flex-wrap: wrap; gap: 6px; }
.watch-last-sync, .watch-metrics { color: var(--body-subtle); font-size: 10px; font-variant-numeric: tabular-nums; }
.watch-metrics { margin-top: 12px; }
.watch-metrics b { margin-left: 4px; color: var(--heading); font-size: 13px; }
@keyframes sync-card-border {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(138, 255, 196, 0.08);
  }
  50% {
    box-shadow: 0 0 0 4px rgba(138, 255, 196, 0.2);
  }
}
@media (max-width: 960px) {
  .watchlist-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 650px) {
  .watchlist-grid {
    gap: 12px;
  }
  .watch-card-top { align-items: flex-start; }
  .watch-status { max-width: 140px; }
  .watch-last-sync { width: 100%; text-align: right; }
}
</style>
