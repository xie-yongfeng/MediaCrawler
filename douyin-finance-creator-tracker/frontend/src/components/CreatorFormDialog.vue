<script setup>
import { computed, ref, watch } from "vue";
import { LoaderCircle, X } from "lucide-vue-next";

const props = defineProps({
  creator: { type: Object, default: null },
  visible: { type: Boolean, default: false },
  saving: { type: Boolean, default: false },
});
const emit = defineEmits(["close", "save"]);

const form = ref({
  name: "",
  platform_creator_id: "",
  tags: "",
  priority: false,
  consent: false,
});
const isEditing = computed(() => Boolean(props.creator));

watch(
  () => [props.visible, props.creator],
  () => {
    if (!props.visible) return;
    form.value = props.creator
      ? {
          name: props.creator.name,
          platform_creator_id:
            props.creator.profile_url || props.creator.platform_creator_id,
          tags: props.creator.tags.join("、"),
          priority: props.creator.priority,
          consent: true,
        }
      : {
          name: "",
          platform_creator_id: "",
          tags: "",
          priority: false,
          consent: false,
        };
  },
  { immediate: true }
);

function submit() {
  emit("save", {
    ...form.value,
    tags: form.value.tags
      .split(/[，,、]/)
      .map((item) => item.trim())
      .filter(Boolean),
  });
}
</script>

<template>
  <div
    v-if="visible"
    class="modal-scrim"
    @click.self="!saving && emit('close')"
  >
    <section
      class="form-modal glass"
      role="dialog"
      aria-modal="true"
      aria-label="编辑观察来源"
    >
      <button
        class="icon-button close-detail"
        aria-label="关闭"
        :disabled="saving"
        @click="emit('close')"
      >
        <X :size="18" />
      </button>
      <p class="eyebrow">WATCHLIST SOURCE</p>
      <h2>{{ isEditing ? "编辑博主" : "添加博主" }}</h2>
      <p class="form-help">
        支持完整抖音主页链接或 <code>sec_user_id</code>。不会绕过平台访问控制。
      </p>
      <form @submit.prevent="submit">
        <label v-if="isEditing"
          >显示名称<input
            v-model.trim="form.name"
            maxlength="80"
            placeholder="例如：趋势观察站" /></label
        ><label
          >主页链接或 sec_user_id<input
            v-model.trim="form.platform_creator_id"
            required
            placeholder="https://www.douyin.com/user/..." /></label
        ><label
          >关注主题（用逗号分隔）<input
            v-model="form.tags"
            placeholder="半导体，AI，医药" /></label
        ><label class="check-label"
          ><input v-model="form.priority" type="checkbox" />设为重点博主</label
        ><label class="check-label consent"
          ><input
            v-model="form.consent"
            type="checkbox"
            required
          />我确认此来源由我提供，仅用于允许范围内的公开内容同步。</label
        >
        <footer>
          <button
            type="button"
            class="button secondary"
            :disabled="saving"
            @click="emit('close')"
          >
            取消</button
          ><button class="button primary" type="submit" :disabled="saving">
            <LoaderCircle v-if="saving" class="spin" :size="15" />{{
              saving ? "正在读取抖音昵称…" : "保存来源"
            }}
          </button>
        </footer>
      </form>
    </section>
  </div>
</template>
