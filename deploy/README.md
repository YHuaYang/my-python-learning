# 部署指南（腾讯云 Ubuntu 24.04）

适用：4 核 4G / Ubuntu 24.04 LTS / SQLite / 单域名 / 一年期。

---

## 一、部署前必须知道的三件事

### 1. 不备案只能用 IP 访问

腾讯云国内节点**必须 ICP 备案**才能用域名访问 80/443 端口。

| 情况 | 结果 |
| --- | --- |
| 已备案 | 域名 + HTTPS 正常 |
| **未备案** | 只能用 `http://服务器IP:8000`（无 HTTPS、搜索引擎不收录） |

备案周期 1-3 周，需要：身份证、域名、服务器订单。

**未备案期间的临时方案**：把 Nginx 改成监听 8080 或直接用 Gunicorn 的 8000 端口，
用 `浏览器 → http://IP:端口` 访问。配置见文末「未备案临时方案」。

### 2. `media/` 必须由 Nginx 托管

Django 的 `static()` 只在 `DEBUG=True` 时生效，生产环境不配 Nginx，
**所有上传的图片都会 404**。`deploy/nginx.conf` 里已经配好了。

### 3. `DEBUG=False` 之后的行为变化

| 项 | 影响 |
| --- | --- |
| 报错页 | 不再显示详细堆栈，改为 500 页面 |
| 静态文件 | 必须 `collectstatic`，否则全 404 |
| `ALLOWED_HOSTS` | 必须填域名，否则 400 Bad Request |

---

## 二、服务器准备

### 2.1 登录服务器

```bash
ssh root@你的服务器IP
```

### 2.2 创建部署用户（可选但推荐）

```bash
adduser deploy
usermod -aG sudo deploy
```

之后用 `deploy` 用户操作，不要一直用 root。

### 2.3 安全组开放端口

腾讯云控制台 → 安全组 → 入站规则：

| 端口 | 用途 | 是否必须 |
| --- | --- | --- |
| 22 | SSH | ✅ 必须 |
| 80 | HTTP（证书验证 + 重定向） | 备案后必须 |
| 443 | HTTPS | 备案后必须 |
| 8000 | 备用（未备案时临时访问） | 视情况 |

---

## 三、上传代码

### 方式 A：git clone（推荐）

```bash
sudo mkdir -p /var/www
cd /var/www
sudo git clone 你的仓库地址 mysite
sudo chown -R $USER:$USER mysite
```

### 方式 B：本地打包上传

```powershell
# 本地（Windows）
cd D:\learning\Django
tar -czf mysite.tar.gz --exclude=node_modules --exclude=yangvenv --exclude=.git --exclude=media --exclude=static --exclude=db.sqlite3 .
scp mysite.tar.gz deploy@服务器IP:/tmp/
```

```bash
# 服务器
sudo mkdir -p /var/www/mysite
cd /var/www/mysite
sudo tar -xzf /tmp/mysite.tar.gz
sudo chown -R $USER:$USER /var/www/mysite
```

**注意**：`db.sqlite3` 和 `media/` 要不要带看你自己。
如果想让服务器从空库开始，不要带 `db.sqlite3`。

---

## 四、配置环境变量

```bash
cd /var/www/mysite

# 生成 SECRET_KEY
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# 复制模板
cp .env.example .env
nano .env
```

`.env` 内容：

```ini
SECRET_KEY=刚才生成的那串

# 生产环境必须 False
DEBUG=False

# 填你的域名；未备案阶段可以先填 IP
ALLOWED_HOSTS=example.com,www.example.com,你的服务器IP

# 有 HTTPS 证书后改成 True
USE_HTTPS=False
```

---

## 五、首次部署

```bash
cd /var/www/mysite
chmod +x deploy/deploy.sh deploy/update.sh

# 先改脚本里的 DOMAIN
nano deploy/deploy.sh    # 把 example.com 改成你的域名

sudo ./deploy/deploy.sh
```

脚本会依次做：装系统依赖 → 建虚拟环境 → 装 Python 包 →
collectstatic → migrate → 配权限 → 装 systemd → 配 Nginx → 申请证书。

---

## 六、配置 DNS

腾讯云控制台 → DNS 解析：

| 记录类型 | 主机记录 | 记录值 |
| --- | --- | --- |
| A | @ | 服务器 IP |
| A | www | 服务器 IP |

DNS 生效通常几分钟到几小时。验证：

```bash
dig example.com +short
# 应该返回你的服务器 IP
```

---

## 七、申请 HTTPS 证书

**必须先完成 DNS 解析**，否则 certbot 验证失败。

```bash
sudo certbot --nginx -d example.com -d www.example.com \
    --agree-tos --register-unsafely-without-email --redirect
```

成功后：

1. 改 `.env`：`USE_HTTPS=True`
2. 改后台的 `Site.domain` 为真实域名
3. 重启服务

```bash
sudo systemctl restart mysite
```

**验证 HTTPS**：

```bash
curl -I https://example.com
# 应该返回 200 且有 Strict-Transport-Security 头
```

**自动续期**：certbot 会装 systemd timer，验证：

```bash
sudo systemctl list-timers | grep certbot
sudo certbot renew --dry-run
```

---

## 八、后台必做的三件事

部署完成、能打开后台后：

### 8.1 改 Site 域名

```
/admin/sites/site/1/change/
```

`domain` 从 `127.0.0.1:8001` 改成 `example.com`。

**为什么重要**：sitemap.xml 和 robots.txt 里的绝对地址靠它拼。
不改的话 SEO 全指向 127.0.0.1。

### 8.2 填个人资料

```
/admin/blog/profile/1/change/
```

注意 `邮箱` 字段会在前台公开显示。

### 8.3 改管理员密码

```bash
cd /var/www/mysite
venv/bin/python manage.py changepassword yang
```

---

## 九、常用运维命令

```bash
# 服务控制
sudo systemctl status mysite
sudo systemctl restart mysite
sudo systemctl stop mysite

# 日志
sudo journalctl -u mysite -f              # 实时日志
sudo journalctl -u mysite -n 100          # 最近 100 行
sudo tail -f /var/log/nginx/mysite.error.log

# 检查配置
cd /var/www/mysite
venv/bin/python manage.py check --deploy

# 数据库备份
sudo -u www-data sqlite3 /var/www/mysite/db.sqlite3 ".backup /var/backups/mysite-$(date +%F).sqlite3"

# 清理 90 天前的访问记录（可以加到 cron）
venv/bin/python manage.py prune_visits --days 90
```

---

## 十、日常更新流程

本地改完代码提交后：

```bash
# 服务器上
cd /var/www/mysite
sudo ./deploy/update.sh
```

如果改了前端（TSX / CSS），**本地必须先 build**：

```powershell
cd D:\learning\Django
npm run build
git add -A
git commit -m "..."
git push
```

服务器的 `collectstatic` 只是把已有产物复制到 `static/`，
不会运行 `npm run build`（服务器没有 Node 环境）。

---

## 十一、未备案临时方案

如果暂时用 IP 访问，把 Nginx 配置简化：

```nginx
server {
    listen 80;
    server_name _;

    client_max_body_size 20M;

    location /static/ {
        alias /var/www/mysite/static/;
        expires 1y;
    }

    location /media/ {
        alias /var/www/mysite/media/;
        expires 7d;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

`.env` 里 `ALLOWED_HOSTS` 填服务器 IP，`USE_HTTPS=False`。

---

## 十二、故障排查

| 现象 | 排查 |
| --- | --- |
| **502 Bad Gateway** | Gunicorn 没起来：`journalctl -u mysite -n 50` |
| **400 Bad Request** | `ALLOWED_HOSTS` 缺当前访问的域名/IP |
| **静态文件 404** | 没跑 `collectstatic`，或 Nginx 的 `alias` 路径错 |
| **图片 404** | Nginx 缺 `location /media/` 配置 |
| **无限重定向** | `USE_HTTPS=True` 但 Nginx 没传 `X-Forwarded-Proto` |
| **后台样式全乱** | `collectstatic` 后没重启，或 Nginx 没配 `/static/` |
| **上传图片失败** | Nginx 的 `client_max_body_size` 太小 |
| **CSRF 验证失败** | `.env` 的 `ALLOWED_HOSTS` 与访问域名不一致 |

### 快速诊断命令

```bash
# Gunicorn 是否在监听
sudo ss -tlnp | grep 8000

# Nginx 配置语法
sudo nginx -t

# Django 能否启动
cd /var/www/mysite
sudo -u www-data venv/bin/python manage.py check --deploy

# 模拟请求
curl -I http://127.0.0.1:8000/          # 直连 Gunicorn
curl -I http://localhost/               # 经 Nginx
```

---

## 十三、一年后的注意事项

服务器到期不续费，数据会被腾讯云释放。到期前记住：

```bash
# 备份数据库
sudo -u www-data sqlite3 /var/www/mysite/db.sqlite3 ".backup /root/mysite-backup.sqlite3"

# 备份媒体文件
sudo tar -czf /root/media-backup.tar.gz -C /var/www/mysite media/

# 下载到本地
scp root@服务器IP:/root/mysite-backup.sqlite3 ./
scp root@服务器IP:/root/media-backup.tar.gz ./
```

代码在 git 仓库里，不用单独备份。
