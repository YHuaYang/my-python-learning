"""文章热度排序。

算法来源：Hacker News 的 ranking 公式

    score = (views) / (age_hours + 2) ** 1.5

设计意图：
- 分子是阅读量，代表「受欢迎程度」
- 分母是文章年龄，代表「新鲜度」，年龄越大分数衰减越快
- 指数 1.5 让衰减比线性更陡，保证新文章有机会上榜

关于常数 2：
    单纯用 age 做分母时，刚发布的文章 age≈0 会让分数趋近无穷大，
    瞬间霸占榜首。加 2 小时作为缓冲量，使最小分母为 2，
    把「刚发布」与「1 小时前」的差距从 2 倍收敛到 1.5 倍。

关于指数 1.5：
    1.0（线性衰减）太温和，一年前的文章仍有可观分数；
    2.0 太激进，一周前的文章分数就趋近 0；
    1.5 是 HN 长期实践出来的折中值。

为什么写在 Python 层而不是数据库：
    当前数据量是两位数，性能差异无法测量，而 Python 实现
    让公式本身一目了然。文章数上千时再改成
    annotate + ExpressionWrapper（SQLite 已支持 POWER 和 julianday）。
"""
from django.utils import timezone

# 分母缓冲量，单位小时
AGE_OFFSET_HOURS = 2

# 衰减指数，越大老文章掉得越快
GRAVITY = 1.5


def hot_score(post, now=None):
    """计算单篇文章的热度分数。分数越大越靠前。

    post: Post 实例，需要 views 和 published_date
    now:  可注入当前时间，便于测试；不传则用 timezone.now()
    """
    if now is None:
        now = timezone.now()

    # 没有发布时间就不参与热门排序（理论上不会出现：
    # status='published' 时 save() 会强制补上时间）
    if post.published_date is None:
        return 0.0

    age_hours = (now - post.published_date).total_seconds() / 3600

    # 用 max 兜底：系统时钟回拨等情况可能算出负数年龄
    age_hours = max(age_hours, 0)

    return post.views / (age_hours + AGE_OFFSET_HOURS) ** GRAVITY


def sort_by_hot(posts, now=None):
    """按热度排序文章列表。

    返回新列表，不修改传入的对象，也不额外查数据库。
    调用方需自行保证 posts 已经 select_related / prefetch_related，
    否则模板渲染时仍会触发 N+1。
    """
    if now is None:
        now = timezone.now()

    # 显式固定当前时间，避免排序过程中每次调用 now() 得到不同值，
    # 导致同一篇文章前后两次打分不一致
    return sorted(posts, key=lambda p: hot_score(p, now=now), reverse=True)
