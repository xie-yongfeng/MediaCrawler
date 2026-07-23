<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { RouterView, useRoute, useRouter } from "vue-router";
import {
  Bell,
  Check,
  CircleAlert,
  CircleCheck,
  Clock3,
  LayoutDashboard,
  LoaderCircle,
  Pencil,
  Plus,
  RefreshCw,
  Settings2,
  ShieldAlert,
  Trash2,
  UserRound,
} from "lucide-vue-next";
import CreatorDeleteDialog from "./components/CreatorDeleteDialog.vue";
import CreatorFormDialog from "./components/CreatorFormDialog.vue";
import VideoDetailDialog from "./components/VideoDetailDialog.vue";
import { request } from "./utils/request";

const dashboard = ref(null);
const creators = ref([]);
const timeline = ref([]);
const route = useRoute();
const router = useRouter();
const selectedCreatorId = ref(null);
const timelineFilter = ref("all");
const search = ref("");
const activeDetail = ref(null);
const syncState = ref({ status: "idle", message: "尚未同步真实内容。" });
const loading = ref(true);
const error = ref("");
const secondsLeft = ref(0);
const currentTime = ref(Date.now());
const showCreatorForm = ref(false);
const creatorSaving = ref(false);
const editingCreator = ref(null);
const deletingCreator = ref(null);
const creatorDeleting = ref(false);
const workarea = ref(null);
let ticker;
let polling;
let searchDebounce;

const navigation = [
  { id: "brief", label: "今日简报", icon: LayoutDashboard },
  { id: "watchlist", label: "观察清单", icon: UserRound },
  { id: "settings", label: "同步说明", icon: Settings2 },
];
const activeNav = computed(() => route.name || "brief");
const selectedCreator = computed(
  () =>
    creators.value.find((item) => item.id === selectedCreatorId.value) ||
    creators.value[0]
);
const visibleBrief = computed(() => dashboard.value?.videos || []);
const criticalBrief = computed(() =>
  visibleBrief.value.filter((video) => video.is_critical)
);
const regularBrief = computed(() =>
  visibleBrief.value.filter((video) => !video.is_critical)
);
const cutoff = computed(() => {
  if (secondsLeft.value <= 0) return "交易已结束";
  const minutes = Math.floor(secondsLeft.value / 60)
    .toString()
    .padStart(2, "0");
  const seconds = (secondsLeft.value % 60).toString().padStart(2, "0");
  return `00:${minutes}:${seconds}`;
});
const autoSyncCountdown = computed(() => {
  const scheduledAt = syncState.value.next_auto_sync_at;
  if (!scheduledAt || syncState.value.status === "running") return "";
  const remaining = Math.max(
    0,
    Math.ceil((new Date(scheduledAt).getTime() - currentTime.value) / 1000)
  );
  if (remaining === 0) return "即将开始";
  const hours = Math.floor(remaining / 3600)
    .toString()
    .padStart(2, "0");
  const minutes = Math.floor((remaining % 3600) / 60)
    .toString()
    .padStart(2, "0");
  const seconds = (remaining % 60).toString().padStart(2, "0");
  return `${hours}:${minutes}:${seconds}`;
});

function nextCutoffSeconds() {
  const now = new Date();
  const deadline = new Date(now);
  deadline.setHours(15, 0, 0, 0);
  return Math.max(0, Math.floor((deadline - now) / 1000));
}
function time(value) {
  return value?.slice(11, 16) || value || "—";
}
function avatarUrl(value) {
  return /^https?:\/\//i.test(value || "") ? value : "";
}
function avatarText(avatar, name) {
  return avatarUrl(avatar)
    ? (name || "").trim().slice(0, 1)
    : (avatar || name || "博").trim().slice(0, 1);
}
function isCreatorSyncing(creatorId) {
  return (
    syncState.value.status === "running" &&
    syncState.value.active_creator_id === creatorId
  );
}
function goTo(name, query = {}) {
  router.push({ name, query });
}
function openTimeline(creatorId) {
  selectedCreatorId.value = creatorId;
  goTo("timeline", { creator: creatorId });
}
function selectCreatorFromRoute() {
  const creatorId = Number(route.query.creator);
  if (
    Number.isInteger(creatorId) &&
    creators.value.some((item) => item.id === creatorId)
  )
    selectedCreatorId.value = creatorId;
}
function pageProps(name) {
  if (name === "brief") {
    return {
      dashboard: dashboard.value,
      criticalBrief: criticalBrief.value,
      regularBrief: regularBrief.value,
    };
  }
  if (name === "timeline") {
    return {
      creator: selectedCreator.value,
      timeline: timeline.value,
      filter: timelineFilter.value,
      search: search.value,
      syncState: syncState.value,
      isCreatorSyncing,
    };
  }
  if (name === "watchlist") {
    return {
      creators: creators.value,
      syncState: syncState.value,
      isCreatorSyncing,
    };
  }
  return {};
}

async function loadTimeline() {
  if (!selectedCreatorId.value) {
    timeline.value = [];
    return;
  }
  timeline.value = await request(
    `/api/creators/${selectedCreatorId.value}/videos?filter=${
      timelineFilter.value
    }&search=${encodeURIComponent(search.value)}`
  );
}
async function loadData({ keepLoading = false } = {}) {
  if (!keepLoading) loading.value = true;
  try {
    const [summary, creatorItems, task] = await Promise.all([
      request("/api/dashboard"),
      request("/api/creators"),
      request("/api/sync/status"),
    ]);
    dashboard.value = summary;
    creators.value = creatorItems;
    syncState.value = task;
    selectCreatorFromRoute();
    if (!creatorItems.some((item) => item.id === selectedCreatorId.value))
      selectedCreatorId.value = creatorItems[0]?.id || null;
    await loadTimeline();
    error.value = "";
  } catch (issue) {
    error.value = issue.message;
  } finally {
    loading.value = false;
  }
}
function hasProcessingTranscript() {
  return [
    ...(dashboard.value?.videos || []),
    ...timeline.value,
    activeDetail.value?.video,
  ].some((video) => video?.transcript_status === "processing");
}
async function refreshTask() {
  try {
    syncState.value = await request("/api/sync/status");
    if (syncState.value.status !== "running" || hasProcessingTranscript())
      await loadData({ keepLoading: true });
    if (activeDetail.value?.video?.transcript_status === "processing") {
      activeDetail.value = await request(
        `/api/videos/${activeDetail.value.video.id}`
      );
    }
  } catch {
    /* retain the last visible state while the API is restarting */
  }
}
async function triggerSync(creatorId = null) {
  try {
    await request("/api/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ creator_ids: creatorId ? [creatorId] : [] }),
    });
    await refreshTask();
  } catch (issue) {
    error.value = issue.message;
  }
}
async function openDetail(video) {
  try {
    activeDetail.value = await request(`/api/videos/${video.id}`);
  } catch (issue) {
    error.value = issue.message;
  }
}
async function requestTranscript(video) {
  try {
    await request("/api/videos/" + video.id + "/transcription/audioconvert", {
      method: "POST",
    });
    video.transcript_status = "processing";
    video.transcript_progress = 5;
  } catch (issue) {
    error.value = issue.message;
  }
}
function openSource(video) {
  window.open(video.source_url, "_blank", "noopener,noreferrer");
}
function openCreatorForm(creator = null) {
  editingCreator.value = creator;
  showCreatorForm.value = true;
}
async function saveCreator(payload) {
  creatorSaving.value = true;
  try {
    const path = editingCreator.value
      ? `/api/creators/${editingCreator.value.id}`
      : "/api/creators";
    const method = editingCreator.value ? "PUT" : "POST";
    const creator = await request(path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    selectedCreatorId.value = creator.id;
    showCreatorForm.value = false;
    await loadData({ keepLoading: true });
  } catch (issue) {
    error.value = issue.message;
  } finally {
    creatorSaving.value = false;
  }
}
function openDeleteCreator(creator) {
  deletingCreator.value = creator;
}
async function removeCreator() {
  if (!deletingCreator.value) return;
  creatorDeleting.value = true;
  try {
    await request(`/api/creators/${deletingCreator.value.id}`, {
      method: "DELETE",
    });
    deletingCreator.value = null;
    await loadData({ keepLoading: true });
  } catch (issue) {
    error.value = issue.message;
  } finally {
    creatorDeleting.value = false;
  }
}

watch([selectedCreatorId, timelineFilter], () =>
  loadTimeline().catch((issue) => {
    error.value = issue.message;
  })
);
watch(search, () => {
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(
    () =>
      loadTimeline().catch((issue) => {
        error.value = issue.message;
      }),
    250
  );
});
watch(
  () => route.query.creator,
  () => selectCreatorFromRoute(),
  { immediate: true }
);
watch(
  () => route.fullPath,
  async () => {
    await nextTick();
    workarea.value?.scrollTo({ top: 0, behavior: "smooth" });
  }
);
onMounted(() => {
  secondsLeft.value = nextCutoffSeconds();
  loadData();
  ticker = window.setInterval(() => {
    secondsLeft.value = nextCutoffSeconds();
    currentTime.value = Date.now();
  }, 1000);
  polling = window.setInterval(refreshTask, 3000);
});
onUnmounted(() => {
  window.clearInterval(ticker);
  window.clearInterval(polling);
  clearTimeout(searchDebounce);
});
</script>

<template>
  <main class="app-shell">
    <header class="topbar glass">
      <div class="cutoff-header">
        <span class="cutoff-header-meta"
          ><span>参考截止时间</span><small>15:00</small></span
        ><strong>{{ cutoff }}</strong>
      </div>
      <div class="header-sync">
        <div class="header-sync-copy">
          <span
            ><i
              class="live-dot"
              :class="{ quiet: syncState.status !== 'running' }"
            ></i
            >{{ syncState.message }}</span
          ><small v-if="autoSyncCountdown"
            >下次自动同步 {{ autoSyncCountdown }}</small
          >
        </div>
        <button
          class="button secondary compact"
          :disabled="syncState.status === 'running'"
          @click="triggerSync()"
        >
          <RefreshCw
            :size="15"
            :class="{ spin: syncState.status === 'running' }"
          />同步全部
        </button>
      </div>
    </header>

    <aside class="sidebar glass">
      <nav class="nav-list" aria-label="主导航">
        <button
          v-for="item in navigation"
          :key="item.id"
          class="nav-item"
          :class="{ active: activeNav === item.id }"
          @click="goTo(item.id)"
        >
          <component :is="item.icon" :size="18" /><span>{{ item.label }}</span>
        </button>
      </nav>
      <div class="sidebar-divider"></div>
      <section class="creator-list" aria-label="观察清单">
        <div class="section-label">
          <span>观察清单</span
          ><button
            class="icon-button mini"
            aria-label="添加博主"
            @click="openCreatorForm()"
          >
            <Plus :size="15" />
          </button>
        </div>
        <button
          v-for="creator in creators"
          :key="creator.id"
          class="creator-row"
          :class="{ selected: selectedCreatorId === creator.id }"
          @click="
            selectedCreatorId = creator.id;
            openTimeline(creator.id);
          "
        >
          <span class="avatar" :style="{ '--avatar': creator.color }"
            ><img
              v-if="avatarUrl(creator.avatar)"
              :src="creator.avatar"
              :alt="creator.name"
            /><template v-else>{{
              avatarText(creator.avatar, creator.name)
            }}</template></span
          >
          <span class="creator-copy"
            ><b>{{ creator.name }}</b
            ><small>{{
              creator.last_synced
                ? `${time(creator.last_synced)} 已同步`
                : "待首次同步"
            }}</small></span
          >
          <span class="creator-count">{{ creator.video_count || 0 }}</span>
        </button>
        <button
          v-if="!creators.length"
          class="empty-side"
          @click="openCreatorForm()"
        >
          <Plus :size="15" />添加第一位博主
        </button>
      </section>
      <div class="sidebar-footer">
        <ShieldAlert :size="15" /><span>不提供投资建议</span>
      </div>
    </aside>

    <section ref="workarea" class="workarea">
      <div v-if="loading" class="loading-state glass">
        <LoaderCircle class="spin" :size="23" />正在载入本地工作台…
      </div>
      <div v-else-if="error" class="error-state glass">
        <CircleAlert :size="20" /><span>{{ error }}</span
        ><button class="button secondary compact" @click="loadData">
          重试
        </button>
      </div>

      <RouterView v-else v-slot="{ Component, route: currentRoute }">
        <component
          :is="Component"
          v-bind="pageProps(currentRoute.name)"
          @refresh="loadData"
          @detail="openDetail"
          @source="openSource"
          @sync="triggerSync"
          @add="openCreatorForm()"
          @transcript="requestTranscript"
          @update:filter="timelineFilter = $event"
          @update:search="search = $event"
          @timeline="openTimeline"
          @edit="openCreatorForm"
          @delete="openDeleteCreator"
        />
      </RouterView>
    </section>

    <VideoDetailDialog :detail="activeDetail" @close="activeDetail = null" @source="openSource" @transcript="requestTranscript" />
    <CreatorFormDialog :visible="showCreatorForm" :creator="editingCreator" :saving="creatorSaving" @close="showCreatorForm = false" @save="saveCreator" />
    <CreatorDeleteDialog
      :creator="deletingCreator"
      :deleting="creatorDeleting"
      @close="deletingCreator = null"
      @confirm="removeCreator"
    />
  </main>
</template>
