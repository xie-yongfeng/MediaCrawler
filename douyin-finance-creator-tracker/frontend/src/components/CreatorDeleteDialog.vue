<script setup>
import { AlertTriangle, Trash2, X } from "lucide-vue-next";

defineProps({
  creator: { type: Object, default: null },
  deleting: { type: Boolean, default: false },
});

const emit = defineEmits(["close", "confirm"]);
</script>

<template>
  <div
    v-if="creator"
    class="modal-scrim"
    @click.self="!deleting && emit('close')"
  >
    <section
      class="delete-dialog glass"
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-creator-title"
    >
      <button
        class="icon-button close-detail"
        aria-label="关闭"
        :disabled="deleting"
        @click="emit('close')"
      >
        <X :size="18" />
      </button>
      <div class="delete-dialog-icon"><AlertTriangle :size="22" /></div>
      <p class="eyebrow">REMOVE WATCHLIST SOURCE</p>
      <h2 id="delete-creator-title">删除 {{ creator.name }}？</h2>
      <p>将删除该博主及其已入库作品，此操作无法撤销。</p>
      <footer>
        <button
          class="button secondary"
          :disabled="deleting"
          @click="emit('close')"
        >
          取消
        </button>
        <button
          class="button danger-action"
          :disabled="deleting"
          @click="emit('confirm')"
        >
          <Trash2 :size="15" />{{ deleting ? "正在删除…" : "删除博主" }}
        </button>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.delete-dialog {
  position: relative;
  width: min(100%, 420px);
  padding: 24px;
  border-radius: 20px;
}
.delete-dialog-icon {
  width: 42px;
  height: 42px;
  display: grid;
  place-items: center;
  border: 1px solid rgba(251, 113, 133, 0.25);
  border-radius: 12px;
  color: #fb7185;
  background: rgba(251, 113, 133, 0.12);
}
.delete-dialog h2 {
  margin: 14px 34px 6px 0;
  font-size: 20px;
  font-weight: 500;
}
.delete-dialog p:not(.eyebrow) {
  margin: 0;
  color: var(--body);
  font-size: 13px;
  line-height: 1.6;
}
.delete-dialog footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 22px;
}
.danger-action {
  border: 1px solid rgba(251, 113, 133, 0.4);
  border-radius: 20px;
  padding: 10px 14px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #fff1f2;
  background: rgba(225, 29, 72, 0.78);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}
.danger-action:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
</style>
