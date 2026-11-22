"""访问统计中间件。

每个前台请求写一条 VisitLog。设计上的取舍都写在代码里。
"""

import logging
import re
from contextlib import suppress

from .models import VisitLog

logger = logging.getLogger(__name__)

# 不记录的路径前缀。
# 用元组而不是正则：前缀判断比正则快，且这些路径不含通配需求。
SKIP_PREFIXES = (
    '/admin/',      # 自己在后台操作，记进去只是噪音
    '/static/',     # 静态资源，一次页面加载会产生十几个请求
    '/media/',      # 上传的图片、音频
)

# 爬虫过滤。UA 里出现这些词的不记录。
# 不追求完整识别（那需要庞大的爬虫清单），
# 只挡最常见的几个，漏掉几个爬虫顶多让 PV 偏大，不影响趋势判断。
BOT_PATTERN = re.compile(
    r'bot|spider|crawler|slurp|curl|wget|python-requests|httpclient',
    re.IGNORECASE,
)


def _detect_device(user_agent: str) -> str:
    """从 UA 判断设备类型，只给四个粗粒度值。

    顺序重要：平板 UA 里常同时含 "Mobile" 和 "Android"，
    所以必须先判断平板，再判断手机，否则平板会被误判为手机。
    """
    ua = user_agent.lower()

    if 'ipad' in ua or 'tablet' in ua:
        return 'tablet'
    # Android 不含 Mobile 的一般是平板
    if 'android' in ua and 'mobile' not in ua:
        return 'tablet'
    if 'mobile' in ua or 'iphone' in ua or 'android' in ua:
        return 'mobile'
    if 'windows' in ua or 'macintosh' in ua or 'linux' in ua:
        return 'desktop'
    return 'unknown'


def _referer_host(referer: str, own_host: str) -> str:
    """从完整 Referer 里只取域名部分。

    只存 host 不存完整 URL：完整 URL 可能带搜索关键词等隐私信息，
    统计上也只需要知道「从哪个站来的」。

    同站跳转返回空串：内部导航不算「来源」，
    否则每篇站内互链都会被记成一次外部来路。
    """
    if not referer:
        return ''

    # 手写解析而不引 urllib.parse：
    # Referer 是浏览器给的，格式简单，且这里只需要 host 一个字段。
    # 用 urlparse 也可以，但为一行代码引一个模块不值。
    match = re.match(r'^https?://([^/]+)', referer)
    if not match:
        return ''
    host = match.group(1).lower()

    # 去掉端口
    host = host.split(':')[0]

    own = own_host.lower().split(':')[0]
    # 本站与 www 前缀都算同站
    if host in (own, f'www.{own}') or own in (host, f'www.{host}'):
        return ''
    return host[:100]


class VisitLoggingMiddleware:
    """记录前台访问。

    放在 MIDDLEWARE 最后：前面几个中间件（Session、Auth、Message）
    都可能早退（比如重定向），放最后能保证 process_request
    在所有前置检查之后才执行。
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 先拿响应，再决定记不记：
        # 只统计成功返回的页面，404 和 500 不该算进访问量
        response = self.get_response(request)

        if self._should_log(request, response):
            self._log(request)

        return response

    def _should_log(self, request, response) -> bool:
        # 只统计 GET：POST 是表单提交，不是「浏览」
        if request.method != 'GET':
            return False

        # 只统计 2xx：404 可能是扫描器在试探，500 是错误
        if not (200 <= response.status_code < 300):
            return False

        path = request.path
        if path.startswith(SKIP_PREFIXES):
            return False

        # 已登录用户（就是站主自己）不记录。
        # 否则每次检查页面都会污染数据，趋势图会变成「我自己的访问日志」
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            return False

        ua = request.META.get('HTTP_USER_AGENT', '')
        return bool(ua) and not BOT_PATTERN.search(ua)

    def _log(self, request) -> None:
        ua = request.META.get('HTTP_USER_AGENT', '')
        # 统计失败绝不能影响页面返回：磁盘满、表锁、字段超长都可能发生。
        # 但完全吞掉会让问题无从排查，所以用 suppress 包住后补一条日志。
        with suppress(Exception):
            VisitLog.objects.create(
                # 去掉 query string：/posts/x/?from=xx 应归到同一页
                path=request.path[:255],
                device=_detect_device(ua),
                referer_host=_referer_host(
                    request.META.get('HTTP_REFERER', ''),
                    request.get_host(),
                ),
            )
