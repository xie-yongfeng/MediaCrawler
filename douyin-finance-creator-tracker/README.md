# Fund Insight Desk

基金收盘前信息助手的本地原型：Vue 3 桌面工作台 + FastAPI + SQLite。它把用户明确提供、且允许同步的公开内容元数据整理为收盘前信息流，不提供投资建议或交易执行。

## 当前能力

- 维护抖音创作者观察清单：支持完整主页链接和 `sec_user_id`，主题标签、重点标记、编辑与删除。
- 从根目录的 MediaCrawler 发起单博主 `dy --type creator` 同步，使用本机浏览器登录会话处理平台登录要求。
- 按抖音 `aweme_id` 去重导入真实作品标题、描述、原始链接、发布时间和入库时间；不会下载视频。
- 显示今日简报、临盘发布标记、未处理队列、博主时间线、原视频入口和来源状态。
- 未配置获授权的音频来源与转写服务时，会明确显示“仅原视频可用”，不会伪造字幕。

## 边界

只能添加由使用者提供的主页链接或 ID，并且仅同步平台规则、授权范围内的公开内容。应用不绕过登录、付费墙或访问控制，也不将创作者内容转化为买卖建议。请以基金销售平台的实际确认规则为准。

## 启动

先确保根目录 MediaCrawler 的 Python 环境可用，并按其说明完成浏览器/CDP 登录配置。工作台会在同步时复用该项目，不需要复制采集代码。

```powershell
# 终端 1：工作台后端
cd E:\work\MediaCrawler\fund-insight-desk\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app:app --reload --port 8000

# 终端 2：工作台前端
cd E:\work\MediaCrawler\fund-insight-desk\frontend
npm install
npm run dev
```

打开 Vite 显示的地址，通常是 `http://localhost:5173`。

## 使用真实博主数据

1. 在“观察清单”中点击“添加博主”。
2. 输入显示名称，以及抖音完整主页链接，例如 `https://www.douyin.com/user/<sec_user_id>`；也可直接输入 `sec_user_id`。
3. 选择关注主题，确认来源由你提供且仅用于允许范围内的公开内容同步。
4. 点击“同步”。后端将在根目录运行：

```powershell
uv run python main.py --platform dy --lt qrcode --type creator --headless false --cdp_connect_existing false --creator_id <sec_user_id> --save_data_option sqlite --get_comment false --get_sub_comment false --crawler_max_notes_count 5
```

工作台会自动检测并拉起可视 Chrome/Edge，抖音登录页会自动弹出；首次使用时请在该浏览器中扫码认证。登录状态保存在 MediaCrawler 的专用浏览器资料目录，后续同步会复用。任务结束后，工作台从 `E:\work\MediaCrawler\database\sqlite_tables.db` 导入本次更新的公开作品元数据。

同步失败时，先检查博主 ID/主页链接、浏览器登录状态、平台可见性和 MediaCrawler 依赖。不会为失败任务编造演示内容。
## 字幕转写

设置 `AUDIOCONVERT_TOKEN` 后，同步完成会通过 AudioConvert 自动转写最近 5 条作品；手动“识别”与自动转写使用相同服务。本地 SQLite 仅保存字幕文本与 Markdown 总结。
