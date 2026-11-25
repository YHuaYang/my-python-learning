"""Gunicorn 配置。

为什么用 .py 而不是命令行参数：
参数一多命令行就难读，配置文件还能写注释。

为什么只监听 127.0.0.1 而不是 0.0.0.0：
Gunicorn 前面有 Nginx 做反向代理，外部请求经 Nginx 转发。
直接监听 0.0.0.0 会让 8000 端口暴露在公网，绕过 Nginx 的
HTTPS 与访问控制。
"""

# 监听地址：只接受本机连接
bind = '127.0.0.1:8000'

# worker 数量。
# 常用公式：(CPU 核数 * 2) + 1。
# 服务器是 4 核，按公式是 9，但个人博客流量很小，
# 3 个足够，还能给系统留资源。
workers = 3

# worker 类型：同步模式。
# 不选 gevent/eventlet：那需要额外依赖，
# 而且博客是 IO 轻负载，同步模型完全够用。
worker_class = 'sync'

# 每个 worker 处理多少个请求后重启，防止内存泄漏累积。
# 加随机抖动避免所有 worker 同时重启。
max_requests = 1000
max_requests_jitter = 100

# 超时：worker 超过这个秒数没响应就被杀掉重启。
# 30 秒对博客够用，太长会让卡死的请求占住 worker。
timeout = 30

# 优雅重启：收到重启信号后给正在处理的请求留时间完成
graceful_timeout = 30

# 把请求交给 worker 前等待多久（防止慢连接攻击）
keepalive = 5

# 日志输出到 stdout/stderr，由 systemd 收集（journalctl 查看）。
# 不写到文件：日志轮转要额外配 logrotate，交给 systemd 更省事。
accesslog = '-'
errorlog = '-'

# 日志级别。info 能看到每个请求，warning 只看异常。
# 生产环境用 info，出问题时好排查；嫌吵可以改 warning。
loglevel = 'info'

# 不在日志里记录请求耗时行（access log 已含足够信息）
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(L)s'

# 进程名，方便 ps / htop 里认出来
proc_name = 'mysite'

# 启动前切换到这个目录（保证相对路径正确）
chdir = '/var/www/mysite'


# Gunicorn 27 新增的 ControlSocket 功能（可用 gunicornc 命令行
# 连到运行中的实例查状态/改 worker 数）。默认路径是 $HOME/.gunicorn/，
# 而 www-data 的 home 是 /var/www，该目录不可写，于是每次启动都
# 刷一条 "Control server error: Permission denied"。
# 我们不用这个功能，直接关掉，日志就干净了。
control_socket_disable = True
