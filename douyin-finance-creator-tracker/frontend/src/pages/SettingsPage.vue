<template>
  <div class="settings-page">
    <div class="page-header">
    <div>
      <p class="eyebrow">DATA CONNECTION</p>
      <h1>同步与合规说明</h1>
    </div>
  </div>
  <section class="guide-card glass">
    <h2>真实数据同步方式</h2>
    <ol>
      <li>
        添加由你提供的抖音主页链接或
        <code>sec_user_id</code>，并确认仅同步允许范围内的公开内容。
      </li>
      <li>
        点击“同步”，工作台会自动拉起可视
        Chrome/Edge，并在抖音登录页弹出二维码认证；扫码后同步会继续执行。
      </li>
      <li>
        同步仅导入作品元数据、原始链接、发布时间和描述；不下载视频，也不绕过付费、登录或访问控制。
      </li>
      <li>
        字幕需要另行配置具有授权的音频来源和转写服务；当前会明确显示“仅原视频可用”。
      </li>
    </ol>
    </section>
  </div>
</template>

<style scoped>
.guide-card {
  max-width: 780px;
  padding: 24px;
  border-radius: 20px;
}
.guide-card h2 {
  margin: 0 0 14px;
  font-size: 20px;
  font-weight: 500;
}
.guide-card ol {
  margin: 0;
  padding-left: 22px;
  color: var(--body);
  font-size: 13px;
  line-height: 1.85;
}
.guide-card code {
  color: var(--brand);
}
</style>
