# 部署操作手册（照着敲）

服务器：腾讯云 4核4G / Ubuntu 24.04 LTS
项目路径：`/var/www/mysite`
本文档所有 `你的IP` 换成真实公网 IP。

---

## 〇、一个必须先知道的事实

项目里有**两类静态文件**，来源不同：

| 类型 | 例子 | 怎么到服务器 |
| --- | --- | --- |
| 进 git 的源码资源 | `bg-day.jpg`、`pygments.css` | `git clone` 自带 |
| **不进 git 的构建产物** | `tailwind.css`、`bundle.js`、`admin-editor.js` | **必须本地 build 后 scp** |

构建产物被 `.gitignore` 排除（它们是 `npm run build` 的产出，不该进版本库）。

所以**服务器 clone 下来是缺样式的**。这不是我配错了，是这类项目的正常做法。
下面的步骤里会处理。

---

## 一、本地：推送代码 + 打包产物

### 1.1 推送代码到 GitHub

```powershell
cd D:\learning\Django

# 确认工作区干净（有改动先提交）
git status

# 推送（本地有 56 个提交从未推送）
git push origin master
```

推送后会提示输入 GitHub 凭据。如果配了 `gh`，也可以：

```powershell
gh auth setup-git
git push origin master
```

### 1.2 构建前端并打包

```powershell
cd D:\learning\Django
npm run build
```

确认产物在：

```powershell
ls blog\static\css\tailwind.css
ls blog\static\js\bundle.js
ls blog\static\js\admin-editor.js
ls blog\static\js\asset-admin-editor.css
```

### 1.3 准备上传目录

```powershell
cd D:\learning\Django
Remove-Item upload -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory upload | Out-Null

Copy-Item blog\static\css\tailwind.css          upload\
Copy-Item blog\static\js\bundle.js              upload\
Copy-Item blog\static\js\admin-editor.js        upload\
Copy-Item blog\static\js\asset-admin-editor.css upload\

Get-ChildItem upload | Select-Object Name, Length
```

应该看到 4 个文件，合计约 1.09 MB。

---

## 二、服务器：系统初始化

先用 SSH 连上：

```powershell
ssh ubuntu@你的IP
```

### 2.1 更新系统

```bash
sudo apt update && sudo apt upgrade -y
```

### 2.2 装系统依赖

```bash
sudo apt install -y \
    python3-venv python3-pip \
    nginx \
    sqlite3 \
    certbot python3-certbot-nginx \
    git
```

### 2.3 确认 Python 版本

```bash
python3 --version
```

Ubuntu 24.04 应该是 **3.12.x**。项目要求 ≥3.10，兼容。

---

## 三、服务器：拉代码

```bash
# 建目录
sudo mkdir -p /var/www
cd /var/www

# clone（仓库是 public，不需要凭据）
sudo git clone https://github.com/YHuaYang/my-python-learning.git mysite

# 把所有权给自己，后面操作不用 sudo
sudo chown -R $USER:$USER /var/www/mysite
cd /var/www/mysite
```

**注意**：如果 `git clone` 报错说目录非空，说明 `/var/www/mysite` 已存在，先确认里面是什么再处理。

### 3.1 确认真的是你要的代码

```bash
ls
git log --oneline -1
```

应该看到 `blog/`、`mysite/`、`deploy/`、`manage.py` 等。

---

## 四、服务器：Python 环境

```bash
cd /var/www/mysite

# 建虚拟环境
python3 -m venv venv

# 升级 pip
venv/bin/pip install --upgrade pip

# 装依赖
venv/bin/pip install -r requirements.txt
```

耗时约 1-3 分钟。最后确认：

```bash
venv/bin/python -c "import django; print(django.get_version())"
```

应该输出 `5.2.x`。

---

## 五、服务器：配置 .env

```bash
cd /var/www/mysite

# 生成 SECRET_KEY（复制输出）
venv/bin/python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# 复制模板
cp .env.example .env

# 编辑
nano .env
```

`.env` 内容改成（把 `你的IP` 和密钥换成真实的）：

```ini
SECRET_KEY=刚才生成的那一长串

DEBUG=False

ALLOWED_HOSTS=你的IP,localhost,127.0.0.1

USE_HTTPS=False
```

`nano` 保存：`Ctrl+O` 回车，`Ctrl+X` 退出。

**为什么 `USE_HTTPS=False`**：现在还没证书。有证书后再改 `True` 并重启。

**为什么 `ALLOWED_HOSTS` 要含 IP**：未备案期间用 IP 访问，不填会返回 400。

### 5.1 验证配置能读

```bash
venv/bin/python manage.py check
```

应该输出 `System check identified no issues`。

如果报 `ModuleNotFoundError`，说明依赖没装全，回第四步。

---

## 六、服务器：安装构建产物

这一步补上 git 里没有的 4 个文件。

### 6.1 从本地传上去

**回到本地 PowerShell**（新开一个窗口，别关 SSH）：

```powershell
cd D:\learning\Django
ssh ubuntu@你的IP "mkdir -p /tmp/assets"
scp upload\* ubuntu@你的IP:/tmp/assets/
```

### 6.2 回到服务器，安装

```bash
cd /var/www/mysite
chmod +x deploy/install-assets.sh
sudo ./deploy/install-assets.sh /tmp/assets
```

脚本会把这 4 个文件放到正确位置：

```
blog/static/css/tailwind.css
blog/static/js/bundle.js
blog/static/js/admin-editor.js
blog/static/js/asset-admin-editor.css
```

### 6.3 验证文件到位

```bash
ls -lh blog/static/css/tailwind.css
ls -lh blog/static/js/
```

`blog/static/js/` 下应该有 `bundle.js`（约 357KB）和 `admin-editor.js`（约 543KB）。

---

## 七、服务器：数据库与静态文件

### 7.1 迁移数据库

```bash
cd /var/www/mysite
venv/bin/python manage.py migrate
```

会创建 `db.sqlite3`，输出一串 `Applying blog.0001_initial... OK` 等。

### 7.2 创建管理员账号

```bash
venv/bin/python manage.py createsuperuser
```

会问用户名、邮箱（可空）、密码。**密码最少 8 位**，别用太简单的。

### 7.3 收集静态文件

```bash
venv/bin/python manage.py collectstatic --noinput
```

**关键**：这一步必须在 `DEBUG=False` 下跑。项目里 `.env` 已设 `DEBUG=False`，所以直接跑就对。

输出类似 `441 static files copied`。这些会被复制到项目根的 `static/` 目录，
Nginx 从那里读。

### 7.4 验证没报错

```bash
venv/bin/python manage.py check --deploy
```

现在应该有几条 HTTPS 警告（因为 `USE_HTTPS=False`），这是**正常的**：
等装了证书改 `True` 后就消失。

---

## 八、服务器：systemd 服务

```bash
cd /var/www/mysite

# 复制服务文件
sudo cp deploy/mysite.service /etc/systemd/system/mysite.service

# 重载 systemd
sudo systemctl daemon-reload

# 开机自启
sudo systemctl enable mysite

# 启动
sudo systemctl start mysite
```

### 8.1 检查是否跑起来

```bash
sudo systemctl status mysite
```

应该看到 `active (running)`（绿色）。

按 `q` 退出。

### 8.2 如果失败了

```bash
sudo journalctl -u mysite -n 50 --no-pager
```

常见错误：

| 报错 | 原因 |
| --- | --- |
| `No module named 'mysite'` | `WorkingDirectory` 路径不对 |
| `Permission denied: db.sqlite3` | 文件属主不是 `www-data` |
| `Address already in use` | 8000 端口被占 |

### 8.3 设文件权限

这一步弄错会报 `attempt to write a readonly database`，原因不直观：

**SQLite 不只是写 `db.sqlite3`，它还在同一目录下创建临时文件**
（`-journal`、`-wal`、`-shm`）。所以 `www-data` 必须能**在项目目录里新建文件**，
仅仅能给数据库文件写权限是不够的。

```bash
cd /var/www/mysite

# 数据库文件与 media 归 www-data
sudo chown www-data:www-data db.sqlite3
sudo chown -R www-data:www-data media

# 目录本身也要可写（创建 journal 文件用）
# 775 = 属主 rwx，同组 rwx，其他 r-x
sudo chown www-data:www-data /var/www/mysite
sudo chmod 775 /var/www/mysite
```

**注意后续影响**：目录属主变成 `www-data` 后，`ubuntu` 用户就改不了它了，
`git pull` 会报权限错误。两个解法：

```bash
# 解法一：git 操作以 www-data 身份执行
sudo -u www-data git pull

# 解法二：把 ubuntu 加进 www-data 组（需重新登录才生效）
sudo usermod -aG www-data ubuntu
```

验证权限是否够：

```bash
ls -ld /var/www/mysite
# 应该看到 drwxrwxr-x www-data www-data

# 直接测能不能写
sudo -u www-data touch /var/www/mysite/_writetest && sudo rm /var/www/mysite/_writetest && echo "可写"
```

### 8.4 测试 Gunicorn 能响应

```bash
curl -I http://127.0.0.1:8000/
```

应该返回 `HTTP/1.1 200 OK`。

如果返回 `400 Bad Request`，检查 `.env` 里的 `ALLOWED_HOSTS`。

---

## 九、服务器：Nginx

### 9.1 改配置里的域名/IP

```bash
cd /var/www/mysite
nano deploy/nginx-ip.conf
```

这个文件是**未备案版本**（只用 IP，无 HTTPS），内容见下一步。

### 9.2 先验证最小可用

如果域名还没备案，用这个简化配置。

```bash
sudo nano /etc/nginx/sites-available/mysite
```

粘贴：

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name _;

    client_max_body_size 20M;

    # 静态文件：collectstatic 的产物
    location /static/ {
        alias /var/www/mysite/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # 媒体文件：用户上传的图片
    # 不配这段，所有上传图片都会 404
    location /media/ {
        alias /var/www/mysite/media/;
        expires 7d;
        add_header Cache-Control "public";
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

保存后：

```bash
# 启用
sudo ln -s /etc/nginx/sites-available/mysite /etc/nginx/sites-enabled/mysite

# 删掉默认站点（它会抢 80 端口）
sudo rm -f /etc/nginx/sites-enabled/default

# 测试语法
sudo nginx -t

# 重载
sudo systemctl reload nginx
```

---

## 十、开放端口

### 10.1 服务器防火墙

```bash
sudo ufw status
```

如果是 `inactive`，可以不启用（腾讯云安全组已经拦了）。

如果要启用：

```bash
sudo ufw allow 22
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
```

**小心**：`ufw enable` 前必须已放行 22，否则会被锁在外面。

### 10.2 腾讯云安全组

控制台 → 云服务器 → 安全组 → 入站规则：

| 端口 | 协议 | 来源 | 说明 |
| --- | --- | --- | --- |
| 22 | TCP | 0.0.0.0/0 | SSH |
| 80 | TCP | 0.0.0.0/0 | HTTP |
| 443 | TCP | 0.0.0.0/0 | HTTPS（有证书后） |

腾讯云默认可能只开了 22。**80 需要手动加**。

---

## 十一、验证

本地浏览器打开：

```
http://你的IP/
```

### 检查清单

| 检查项 | 预期 |
| --- | --- |
| 首页能打开 | 有背景图、有样式 |
| 导航能点 | 链接正常跳转 |
| `http://你的IP/admin/` | 后台登录页有样式 |
| 登录后台 | 仪表盘正常 |
| `http://你的IP/robots.txt` | 返回文本，`Sitemap:` 行 |
| `http://你的IP/static/css/tailwind.css` | 返回 CSS，不是 404 |

### 如果样式没生效

```bash
# 1. 确认文件在
ls -lh /var/www/mysite/static/css/tailwind.css

# 2. 确认 Nginx 路径对
sudo nginx -T | grep -A3 "location /static/"

# 3. 直接 curl
curl -I http://127.0.0.1/static/css/tailwind.css
```

---

## 十二、后台必做三件事

登录 `http://你的IP/admin/` 后：

### 12.1 改 Site 域名

访问 `/admin/sites/site/1/change/`

`domain` 从 `127.0.0.1:8001` 改成 `你的IP`（或以后的域名）。

**为什么**：sitemap.xml 和 robots.txt 里的绝对地址靠它拼。

### 12.2 填个人资料

访问 `/admin/blog/profile/1/change/`

注意 `邮箱` 字段会**在前台公开显示**。

### 12.3 改管理员密码

```bash
cd /var/www/mysite
venv/bin/python manage.py changepassword 你的用户名
```

---

## 十三、日后更新代码

### 只改了后端 Python

```bash
cd /var/www/mysite
git pull
sudo systemctl restart mysite
```

### 改了前端（TSX / CSS）

**本地**：

```powershell
cd D:\learning\Django
npm run build

# 重新打包
Remove-Item upload -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory upload | Out-Null
Copy-Item blog\static\css\tailwind.css          upload\
Copy-Item blog\static\js\bundle.js              upload\
Copy-Item blog\static\js\admin-editor.js        upload\
Copy-Item blog\static\js\asset-admin-editor.css upload\

# 推送代码
git add -A; git commit -m "..."; git push

# 传产物
ssh ubuntu@你的IP "mkdir -p /tmp/assets"
scp upload\* ubuntu@你的IP:/tmp/assets/
```

**服务器**：

```bash
cd /var/www/mysite
git pull
sudo ./deploy/install-assets.sh /tmp/assets
venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart mysite
```

### 改了模型（新增迁移）

```bash
cd /var/www/mysite
git pull
venv/bin/python manage.py migrate
sudo systemctl restart mysite
```

---

## 十四、故障排查速查

```bash
# 服务状态
sudo systemctl status mysite

# 应用日志（最重要）
sudo journalctl -u mysite -n 100 --no-pager
sudo journalctl -u mysite -f          # 实时

# Nginx 日志
sudo tail -50 /var/log/nginx/error.log

# 分层测试
curl -I http://127.0.0.1:8000/        # 直连 Gunicorn
curl -I http://127.0.0.1/             # 经 Nginx
curl -I http://你的IP/                 # 从外部

# 端口检查
sudo ss -tlnp | grep -E '8000|80'
```

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 浏览器连不上 | 安全组没开 80 | 腾讯云控制台加规则 |
| 502 Bad Gateway | Gunicorn 没起来 | `journalctl -u mysite` |
| 400 Bad Request | `ALLOWED_HOSTS` 缺当前 IP | 改 `.env` 重启 |
| 样式全丢 | 没 scp 构建产物 | 走第六步 |
| 图片 404 | Nginx 缺 `/media/` | 走第九步 |
| 后台 500 | 没 `collectstatic` | 在 `DEBUG=False` 下重跑 |
| 上传失败 | Nginx `client_max_body_size` 太小 | 改 20M |

---

## 十五、部署完成后的待办

- [ ] 改 `Site.domain`
- [ ] 填个人资料
- [ ] 改管理员密码
- [ ] 开始写第一篇正式文章

## 关于备案（后续）

未备案期间只能用 IP 访问，缺点：

- 没有 HTTPS（浏览器会标“不安全”）
- 搜索引擎不收录
- 部分网络环境可能访问慢

备案下来后：

```bash
# 1. 改 DNS 解析到服务器 IP
# 2. 等等待生效
dig 你的域名 +short

# 3. 申请证书
sudo certbot --nginx -d 你的域名 -d www.你的域名 \
    --agree-tos --register-unsafely-without-email --redirect

# 4. 改 .env
nano /var/www/mysite/.env
#   ALLOWED_HOSTS=你的域名,www.你的域名,你的IP
#   USE_HTTPS=True

# 5. 换回完整 Nginx 配置
sudo cp /var/www/mysite/deploy/nginx.conf /etc/nginx/sites-available/mysite
#    并改里面的 example.com 为真实域名
sudo nginx -t && sudo systemctl reload nginx

# 6. 重启应用
sudo systemctl restart mysite
```
