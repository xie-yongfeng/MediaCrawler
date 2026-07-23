#!/usr/bin/env bash
# 启动 Fund Insight Desk 后端 (FastAPI + Uvicorn)
set -euo pipefail

# 切换到脚本所在目录，确保无论从哪里调用都能正确定位项目文件
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"
MEDIA_CRAWLER_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CDP_USER_DATA_DIR="${CDP_USER_DATA_DIR:-$MEDIA_CRAWLER_ROOT/browser_data/cdp_dy_user_data_dir}"
PYTHON_BIN="python"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

# 若不存在虚拟环境则创建
if [ ! -d "$VENV_DIR" ]; then
    echo "[run.sh] 未检测到虚拟环境，正在创建 $VENV_DIR ..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# 激活虚拟环境
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# 安装/更新依赖
echo "[run.sh] 正在安装依赖..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

cdp_ready() {
    curl --fail --silent --max-time 1 http://127.0.0.1:9222/json/version >/dev/null 2>&1
}

# Keep a dedicated Chrome instance available for all crawler subprocesses.
if ! cdp_ready; then
    CHROME_BIN="${CHROME_BIN:-}"
    if [ -z "$CHROME_BIN" ]; then
        for candidate in google-chrome google-chrome-stable chromium chromium-browser; do
            if command -v "$candidate" >/dev/null 2>&1; then
                CHROME_BIN="$(command -v "$candidate")"
                break
            fi
        done
    fi
    if [ -z "$CHROME_BIN" ] && [ -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]; then
        CHROME_BIN="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    fi
    if [ -z "$CHROME_BIN" ]; then
        echo "[run.sh] Chrome was not found. Set CHROME_BIN before starting the service." >&2
        exit 1
    fi
    mkdir -p "$CDP_USER_DATA_DIR"
    echo "[run.sh] Starting persistent CDP Chrome on port 9222..."
    nohup "$CHROME_BIN" --remote-debugging-port=9222 --user-data-dir="$CDP_USER_DATA_DIR" \
        >"$CDP_USER_DATA_DIR/cdp-chrome.log" 2>&1 &
    for _ in $(seq 1 30); do
        cdp_ready && break
        sleep 1
    done
    if ! cdp_ready; then
        echo "[run.sh] CDP Chrome did not become ready on port 9222." >&2
        exit 1
    fi
fi

# 启动服务（默认开启 --reload 便于开发调试；可通过 RELOAD=false 关闭）
RELOAD_FLAG="--reload"
if [ "${RELOAD:-true}" = "false" ]; then
    RELOAD_FLAG=""
fi

echo "[run.sh] 正在启动后端服务： http://$HOST:$PORT"
exec uvicorn app:app --host "$HOST" --port "$PORT" $RELOAD_FLAG
