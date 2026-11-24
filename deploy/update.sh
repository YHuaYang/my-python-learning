#!/usr/bin/env bash
#
# 日常更新脚本。代码改动后跑这个。
#
# 用法：sudo ./deploy/update.sh

set -euo pipefail

PROJECT_DIR="/var/www/mysite"
VENV_DIR="$PROJECT_DIR/venv"
SERVICE_NAME="mysite"

if [ "$EUID" -ne 0 ]; then
    echo "请用 sudo 运行：sudo ./deploy/update.sh"
    exit 1
fi

cd "$PROJECT_DIR"

echo "==> 1. 拉取最新代码"
# 如果服务器上是 git clone 的，用这个；
# 如果是手动 scp 上传的，注释掉这行
git pull --ff-only || echo "  跳过 git pull（可能不是 git 仓库）"

echo "==> 2. 更新依赖"
"$VENV_DIR/bin/pip" install -r requirements.txt

echo "==> 3. 数据库迁移"
"$VENV_DIR/bin/python" manage.py migrate --noinput

echo "==> 4. 收集静态文件"
# 这一步不能省：前端改过类名或换过 JS，不 collectstatic 会 404
"$VENV_DIR/bin/python" manage.py collectstatic --noinput

echo "==> 5. 重启服务"
systemctl restart "$SERVICE_NAME"

echo "==> 6. 检查状态"
sleep 2
systemctl is-active "$SERVICE_NAME" && echo "  服务运行中" || echo "  ❌ 服务未启动，查日志"

echo
echo "更新完成。查看日志：journalctl -u $SERVICE_NAME -n 50"
