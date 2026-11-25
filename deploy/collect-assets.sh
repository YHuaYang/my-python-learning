#!/usr/bin/env bash
# 本地（Windows Git Bash / WSL）打包要上传的构建产物。
#
# 用法：
#   bash deploy/collect-assets.sh
#
# 产出 upload/ 目录，用 scp 整个传上去。

set -euo pipefail

cd "$(dirname "$0")/.."

OUT="upload"

echo "==> 1. 构建前端"
npm run build

echo "==> 2. 收集产物"
rm -rf "$OUT"
mkdir -p "$OUT"

cp blog/static/css/tailwind.css "$OUT/"
cp blog/static/js/bundle.js "$OUT/"
cp blog/static/js/admin-editor.js "$OUT/"
cp blog/static/js/asset-admin-editor.css "$OUT/"

echo "==> 3. 清单"
ls -lh "$OUT"

echo
echo "上传命令："
echo "  scp -r $OUT/* 你的服务器:/tmp/assets/"
