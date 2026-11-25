#!/usr/bin/env bash
#
# 服务器端：从本地推送的产物恢复静态文件
#
# 为什么需要这个脚本：
# 项目有两个静态文件来源，
#   1. 进 git 的源码资源（bg-day.jpg、pygments.css）
#   2. 不进 git 的构建产物（tailwind.css、bundle.js、admin-editor.js）
# 服务器 clone 后只有第 1 类，第 2 类必须 scp 上去。
#
# 用法（在服务器上）：
#   sudo ./deploy/install-assets.sh /tmp/assets
#
# 参数是本地 scp 上来的目录，应该包含：
#   tailwind.css  bundle.js  admin-editor.js  asset-admin-editor.css

set -euo pipefail

PROJECT_DIR="/var/www/mysite"
SRC="${1:-/tmp/assets}"

if [ "$EUID" -ne 0 ]; then
    echo "请用 sudo 运行"
    exit 1
fi

if [ ! -d "$SRC" ]; then
    echo "找不到源目录：$SRC"
    echo "本地应该先执行：npm run build && scp -r assets-to-upload/* 服务器:/tmp/assets/"
    exit 1
fi

echo "==> 从 $SRC 安装构建产物"

# CSS 进 blog/static/css/
if [ -f "$SRC/tailwind.css" ]; then
    cp "$SRC/tailwind.css" "$PROJECT_DIR/blog/static/css/tailwind.css"
    echo "  ✓ tailwind.css"
else
    echo "  ✗ 缺少 tailwind.css"
    exit 1
fi

# JS 进 blog/static/js/
mkdir -p "$PROJECT_DIR/blog/static/js"
for f in bundle.js admin-editor.js asset-admin-editor.css; do
    if [ -f "$SRC/$f" ]; then
        cp "$SRC/$f" "$PROJECT_DIR/blog/static/js/$f"
        echo "  ✓ $f"
    else
        echo "  ✗ 缺少 $f"
        exit 1
    fi
done

chown -R www-data:www-data "$PROJECT_DIR/blog/static"

echo
echo "完成。别忘了重新 collectstatic："
echo "  cd $PROJECT_DIR && sudo -u www-data venv/bin/python manage.py collectstatic --noinput"
