<script setup>
import { RefreshCw } from "lucide-vue-next";
import VideoCard from "../components/VideoCard.vue";

defineProps({
  dashboard: { type: Object, default: null },
  criticalBrief: { type: Array, default: () => [] },
  regularBrief: { type: Array, default: () => [] },
});

const emit = defineEmits(["refresh", "detail", "source"]);
</script>

<template>
  <div class="brief-page">
    <div class="page-header">
    <div>
      <p class="eyebrow">TODAY'S BRIEF</p>
      <h1>今日收盘前简报</h1>
      <p>仅显示今日发布的作品；临盘发布内容单独归类。</p>
    </div>
    <button class="button secondary" @click="emit('refresh')">
      <RefreshCw :size="15" />刷新工作台
    </button>
  </div>
  <template v-if="dashboard">
    <section v-if="criticalBrief.length" class="brief-section">
      <div class="section-title">
        <div>
          <h2>临盘发布</h2>
          <p>今天 14:00 至 15:00 发布的作品。</p>
        </div>
      </div>
      <div class="feed brief-grid">
        <VideoCard
          v-for="video in criticalBrief"
          :key="video.id"
          :video="video"
          @detail="emit('detail', $event)"
          @source="emit('source', $event)"
        />
      </div>
    </section>
    <section class="brief-section">
      <div class="section-title">
        <div>
          <h2>今日发布</h2>
          <p>
            {{
              regularBrief.length
                ? "今天已发布的其他作品。"
                : "暂无其他今日发布作品。"
            }}
          </p>
        </div>
      </div>
      <div v-if="regularBrief.length" class="feed brief-grid">
        <VideoCard
          v-for="video in regularBrief"
          :key="video.id"
          :video="video"
          @detail="emit('detail', $event)"
          @source="emit('source', $event)"
        />
      </div>
      <div v-else class="empty glass">
        同步完成后，今日发布的真实内容会显示在这里。
      </div>
    </section>
  </template>
  </div>
</template>

<style scoped>
.brief-section {
  margin-bottom: 28px;
}
.brief-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
@media (max-width: 760px) {
  .brief-grid {
    grid-template-columns: 1fr;
  }
}
</style>
