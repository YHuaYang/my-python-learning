"""后台仪表盘的统计逻辑。

抽成独立模块而不是写在 admin.py 里：
- 这些查询只被仪表盘用，和 Admin 的模型配置无关
- 单独放便于测试（不启动 Admin 就能验算）
"""

from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from .models import GuestbookMessage, Post, Project, VisitLog, WeeklyProgress

# 图表展示的天数
CHART_DAYS = 7

# 热门页面取前几名
TOP_PATHS = 5


def _days_ago(n: int):
    """N 天前的零点（本地时区）。

    用零点而不是「现在减 N×24 小时」：
    按天聚合时要让每天的桶边界对齐自然日，
    否则凌晨跑和晚上跑出来的第一桶宽度不一样。
    """
    now = timezone.localtime()
    return (now - timedelta(days=n - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )


def content_overview() -> dict:
    """顶部数字卡片。全部是真实数据，没有估算值。"""
    published = Post.objects.filter(status='published')

    # 用 values_list + sum 而不是 Python 端 sum(Post.objects.all())：
    # 前者只取一列，后者要把整行实例化，字段多时浪费明显
    views_total = sum(Post.objects.values_list('views', flat=True))

    return {
        'posts_total': Post.objects.count(),
        'posts_published': published.count(),
        'views_total': views_total,
        'guestbook_pending': GuestbookMessage.objects.filter(
            is_approved=False,
        ).count(),
        'guestbook_total': GuestbookMessage.objects.count(),
        'projects_total': Project.objects.count(),
        'progress_total': WeeklyProgress.objects.count(),
    }


def visit_trend() -> dict:
    """近 7 天的访问量与设备分布。

    返回结构直接给模板用，模板里不写任何数据加工逻辑。
    """
    since = _days_ago(CHART_DAYS)

    # 按天聚合。TruncDate 在 SQLite 上能用，且会按 settings.TIME_ZONE 切日
    rows = (
        VisitLog.objects
        .filter(created_at__gte=since)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(count=Count('pk'))
        .order_by('day')
    )
    counted = {r['day']: r['count'] for r in rows}

    # 补全没有访问的日期：折线图缺日会连成直线，看起来像数据连续
    days = []
    for i in range(CHART_DAYS):
        d = (_days_ago(CHART_DAYS) + timedelta(days=i)).date()
        days.append({'date': d.strftime('%m-%d'), 'count': counted.get(d, 0)})

    total_visits = sum(d['count'] for d in days)

    # 无访问时给一个非零分母，否则柱状图高度会算成 0/0
    max_count = max([d['count'] for d in days] + [1])

    # 把计数映射成 0-10 的档位类名（bar-0 ~ bar-10）。
    # 不用内联 style：
    # 1. HTML 模板里的模板标签会让 CSS 静态检查器报「非法 CSS」
    # 2. Admin 用的是 unfold 自带的 Tailwind 产物，
    #    算出来的任意值类名（如 h-[45%]）根本不在那份 CSS 里
    # 所以档位类写在模板内的 <style> 里，不依赖任何构建。
    for d in days:
        d['bar_class'] = 'bar-' + str(round(d['count'] / max_count * 10))

    # 设备分布
    device_rows = (
        VisitLog.objects
        .filter(created_at__gte=since)
        .values('device')
        .annotate(count=Count('pk'))
        .order_by('-count')
    )
    device_labels = dict(VisitLog.DEVICE_CHOICES)
    # 分母用总量而不是最大项：这里要的是「占总量的比例」
    device_total = total_visits or 1
    devices = [
        {
            'key': r['device'],
            'label': device_labels.get(r['device'], '未知'),
            'count': r['count'],
            'pct': round(r['count'] / device_total * 100, 1),
            # 同样用档位类名代替内联 style
            'bar_class': 'dev-' + str(round(r['count'] / device_total * 10)),
        }
        for r in device_rows
    ]

    return {
        'days': days,
        'devices': devices,
        'total_visits': total_visits,
        'max_count': max_count,
    }


def top_pages() -> list:
    """近 7 天访问最多的页面。"""
    since = _days_ago(CHART_DAYS)
    return list(
        VisitLog.objects
        .filter(created_at__gte=since)
        .values('path')
        .annotate(count=Count('pk'))
        .order_by('-count')[:TOP_PATHS]
    )


def top_referers() -> list:
    """近 7 天的外部来路。空串是同站跳转与直接访问，已排除。"""
    since = _days_ago(CHART_DAYS)
    return list(
        VisitLog.objects
        .filter(created_at__gte=since)
        .exclude(referer_host='')
        .values('referer_host')
        .annotate(count=Count('pk'))
        .order_by('-count')[:TOP_PATHS]
    )


def dashboard_context() -> dict:
    """一次性拿出仪表盘需要的全部数据。

    显式标注 dict[str, Any]：否则空 dict 会被推断成
    dict[Unknown, Unknown]，后续赋值 list 时类型检查报错。
    """
    ctx: dict = {'overview': content_overview()}
    ctx['trend'] = visit_trend()
    ctx['top_pages'] = top_pages()
    ctx['top_referers'] = top_referers()
    return ctx
