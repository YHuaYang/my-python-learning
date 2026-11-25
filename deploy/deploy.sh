#!/usr/bin/env bash
#
# 一键部署脚本（首次部署用）
#
# 用法：
#   1. 把项目传到服务器：/var/www/mysite
#   2. chmod +x deploy/deploy.sh
#   3. sudo ./deploy/deploy.sh
#
# 这个脚本做的是「首次部署」。日常更新代码用 deploy/update.sh。

set -euo pipefail

# ===== 配置（按需改这几行）=====
PROJECT_DIR="/var/www/mysite"
VENV_DIR="$PROJECT_DIR/venv"
SERVICE_NAME="mysite"
DOMAIN="example.com"          # ← 改成你的域名

echo "==> 1. 检查是否以 root 运行"
if [ "$EUID" -ne 0 ]; then
    echo "请用 sudo 运行：sudo ./deploy/deploy.sh"
    exit 1
fi

echo "==> 2. 安装系统依赖"
apt update
apt install -y \
    python3-venv python3-pip \
    nginx \
    certbot python3-certbot-nginx \
    git

echo "==> 3. 创建虚拟环境并装依赖"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$PROJECT_DIR/requirements.txt"

echo "==> 4. 检查 .env 是否存在"
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "缺少 .env 文件。请先："
    echo "  cp $PROJECT_DIR/.env.example $PROJECT_DIR/.env"
    echo "  然后填入 SECRET_KEY / DEBUG=False / ALLOWED_HOSTS=$DOMAIN"
    exit 1
fi

echo "==> 5. 收集静态文件"
cd "$PROJECT_DIR"
"$VENV_DIR/bin/python" manage.py collectstatic --noinput

echo "==> 6. 数据库迁移"
"$VENV_DIR/bin/python" manage.py migrate --noinput

echo "==> 7. 设置文件权限"
# 有两个用户都要写，需求不同：
#   www-data —— SQLite 要在项目目录建 -journal 临时文件，
#              还要写 media/（否则报 readonly database）
#   ubuntu   —— collectstatic 要建 static/，还要 git pull 与改代码
#
# 关键是不要独占：属主给 ubuntu，属组给 www-data，
# 组权限带 w。两者都靠组权限获得写权。
DEPLOY_USER="${SUDO_USER:-ubuntu}"
chown -R "$DEPLOY_USER":www-data "$PROJECT_DIR"
# g+w 只给组加写权限，保留原有执行位。
# 不用 chmod -R 777（太宽），也不用 -R 755（会抹掉已有权限）
chmod -R g+w "$PROJECT_DIR"

# media 必须可写（用户上传图片的落地处）
chown -R www-data:www-data "$PROJECT_DIR/media" 2>/dev/null || true
chmod -R g+w "$PROJECT_DIR/media" 2>/dev/null || true

echo "==> 8. 安装 systemd 服务"
cp "$PROJECT_DIR/deploy/mysite.service" "/etc/systemd/system/$SERVICE_NAME.service"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

echo "==> 9. 安装 Nginx 配置"
cp "$PROJECT_DIR/deploy/nginx.conf" "/etc/nginx/sites-available/$SERVICE_NAME"
ln -sf "/etc/nginx/sites-available/$SERVICE_NAME" "/etc/nginx/sites-enabled/$SERVICE_NAME"
# 删掉默认站点，否则它会抢 80 端口的 default_server
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo "==> 10. 申请 HTTPS 证书"
echo "  如果域名还没备案或 DNS 未生效，这一步会失败。"
echo "  可以先跳过，用 IP 访问（但没 HTTPS）。"
read -rp "现在申请证书吗？需要 DNS 已指向本机 [y/N] " answer
if [[ "$answer" == "y" ]]; then
    certbot --nginx -d "$DOMAIN" -d "www.$DOMAIN" \
        --non-interactive --agree-tos --register-unsafely-without-email \
        --redirect
    echo "  证书已申请，certbot 会自动配置续期"
else
    echo "  跳过。之后可以手动跑：certbot --nginx -d $DOMAIN"
fi

echo "==> 11. 检查部署状态"
"$VENV_DIR/bin/python" manage.py check --deploy || true

echo
echo "=========================================="
echo "部署完成"
echo "=========================================="
echo "服务状态：systemctl status $SERVICE_NAME"
echo "查看日志：journalctl -u $SERVICE_NAME -f"
echo "Nginx 日志：tail -f /var/log/nginx/mysite.error.log"
echo
echo "重要提醒："
echo "  1. .env 里必须设 DEBUG=False"
echo "  2. ALLOWED_HOSTS 要含 $DOMAIN"
echo "  3. 有 HTTPS 后设 USE_HTTPS=True 并重启服务"
echo "  4. 去后台把 Site 的 domain 改成 $DOMAIN"
