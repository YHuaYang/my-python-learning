"""模板全局上下文。

导航链接要出现在 base.html 里（每个页面都有），所以不能靠单个视图传。
用 context processor 注入，比在每个视图里重复一遍更不容易漏。

这里只生成「标签 + href」，用 reverse() 而不是硬编码路径：
以后改 URL 配置，这里自动跟着变。
"""

from django.urls import reverse

# 顺序即导航栏的显示顺序。
# 不用 reverse_lazy：context processor 在每次请求时执行，
# URL 配置那时早已加载完毕，直接 reverse 就行。
NAV_ITEMS = [
    ('首页', 'post_list'),
    ('项目', 'projects'),
    ('进度', 'progress_list'),
    ('搜索', 'search'),
    ('关于', 'about'),
]


def nav(request):
    """把导航项和当前路径交给模板。

    request.path 给 React 的 GooeyNav 用：
    孤岛组件拿不到 Django 的 request，只能通过 data-* 传进去。
    """
    return {
        'nav_items': [
            {'label': label, 'href': reverse(url_name)}
            for label, url_name in NAV_ITEMS
        ],
        'current_path': request.path,
    }
