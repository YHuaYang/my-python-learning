#!/usr/bin/env bash
#
# 静态文件诊断。样式丢失时跑这个，一次看全链路。
#
# 用法（在服务器上）：
#   bash /var/www/mysite/deploy/diagnose-static.sh

PROJECT_DIR="/var/www/mysite"

echo "============================================================"
echo " 静态文件链路诊断"
echo "============================================================"
echo

# ---------- 1. 两个关键目录 ----------
echo "【1】目录结构"
echo "  blog/static/   ← 源文件（install-assets.sh 往这放）"
echo "  static/        ← collectstatic 的产物（Nginx 读这里）"
echo
for d in "$PROJECT_DIR/blog/static" "$PROJECT_DIR/static"; do
    if [ -d "$d" ]; then
        echo "  $d"
        echo "    属主: $(stat -c '%U:%G' "$d")  权限: $(stat -c '%a' "$d")"
    else
        echo "  ❌ 不存在: $d"
    fi
done
echo

# ---------- 2. 源文件（第 6 步的产物）----------
echo "【2】blog/static/ 里的构建产物（第 6 步 install-assets 的结果）"
check_src() {
    f="$PROJECT_DIR/blog/static/$1"
    if [ -f "$f" ]; then
        echo "  ✓ $1  $(du -h "$f" | cut -f1)"
    else
        echo "  ✗ 缺失 $1   ← 第六步没做或失败"
    fi
}
check_src "css/tailwind.css"
check_src "js/bundle.js"
check_src "js/admin-editor.js"
check_src "js/asset-admin-editor.css"
check_src "css/pygments.css"
check_src "css/blog.css"
echo

# ---------- 3. collectstatic 的产物 ----------
echo "【3】static/ 里的文件（Nginx 实际读这里）"
check_root() {
    f="$PROJECT_DIR/static/$1"
    if [ -f "$f" ]; then
        echo "  ✓ $1  $(du -h "$f" | cut -f1)  属主 $(stat -c '%U:%G' "$f")"
    else
        echo "  ✗ 缺失 $1   ← collectstatic 没跑，或跑的时候第 6 步还没做"
    fi
}
check_root "css/tailwind.css"
check_root "js/bundle.js"
check_root "css/pygments.css"
check_root "css/blog.css"
echo

# ---------- 4. manifest ----------
echo "【4】staticfiles.json（DEBUG=False 时必需）"
MF="$PROJECT_DIR/static/staticfiles.json"
if [ -f "$MF" ]; then
    echo "  ✓ 存在，$(du -h "$MF" | cut -f1)"
elif [ -d "$PROJECT_DIR/static" ]; then
    echo "  ✗ 没有 staticfiles.json"
    echo "    生产模式下所有 {% static %} 会抛 ValueError"
else
    echo "  - static/ 目录都不存在，更没 manifest"
fi
echo

# ---------- 5. 权限（www-data 能否读）----------
echo "【5】权限检查（Nginx 以 www-data 运行，必须能读）"
for f in "$PROJECT_DIR/static/css/tailwind.css" "$PROJECT_DIR/static/js/bundle.js"; do
    if [ -f "$f" ]; then
        # 用 www-data 身份实测
        if sudo -u www-data test -r "$f" 2>/dev/null; then
            echo "  ✓ www-data 可读: $(basename "$f")"
        else
            echo "  ✗ www-data 读不了: $f"
        fi
    fi
done
echo

# ---------- 6. Nginx 配置 ----------
echo "【6】Nginx 的 /static/ 配置"
if grep -q "location /static/" /etc/nginx/sites-enabled/mysite 2>/dev/null; then
    grep -A3 "location /static/" /etc/nginx/sites-enabled/mysite | sed 's/^/  /'
else
    echo "  ❌ /etc/nginx/sites-enabled/mysite 里没有 location /static/"
    echo "     样式一定会 404"
fi
echo

# ---------- 7. 实际 HTTP 测试 ----------
echo "【7】实际 HTTP 响应"
for u in "http://127.0.0.1/static/css/tailwind.css" \
         "http://127.0.0.1/static/js/bundle.js" \
         "http://127.0.0.1/"; do
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$u" 2>/dev/null)
    case "$code" in
        200) mark="✓" ;;
        404) mark="✗ 文件不存在（Nginx 找不到）" ;;
        403) mark="✗ 权限不足（www-data 读不了）" ;;
        502) mark="✗ Gunicorn 没起来" ;;
        *)   mark="?" ;;
    esac
    echo "  $code  $mark"
    echo "        $u"
done
echo

# ---------- 8. 页面 HTML 里的实际引用 ----------
echo "【8】首页 HTML 里的样式引用"
curl -s --max-time 5 "http://127.0.0.1/" 2>/dev/null \
    | grep -oE '(href|src)="[^"]*\.(css|js)"' | head -6 | sed 's/^/  /'
echo

echo "============================================================"
echo " 按上面【2】【3】的顺序判断："
echo "============================================================"
echo "  情况 A：【2】缺文件  → 回第六步，本地 scp 上去后跑 install-assets.sh"
echo "  情况 B：【2】有但【3】缺 → 跑 collectstatic（必须 DEBUG=False）"
echo "  情况 C：【3】有但【7】404 → Nginx 配置或 alias 路径问题"
echo "  情况 D：【3】有但【7】403 → chown -R www-data:www-data static/"
