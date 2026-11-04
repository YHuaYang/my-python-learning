"""
views.py 处理用户请求：查数据 → 选模板 → 返回 HTML。

每个视图函数接收一个 request（Django 传进来的请求对象），
必须返回一个 HttpResponse（render() 就是快捷方式之一）。

全局约定：所有对外展示文章的查询都必须加
    published_date__lte=timezone.now()
否则草稿（published_date 为 NULL）会被直接访问到。
筛选条件「列表里过滤了、详情里忘了过滤」是内容站最常见的越权漏洞。
"""
from datetime import date

from django.shortcuts import render,get_object_or_404
from .models import Post,Category,Tag,DailySong,Project,WeeklyProgress,Profile
from .forms import SearchForm
from .ranking import sort_by_hot
from django.db.models import F,Q
from django.core.paginator import Paginator


# 首页支持的排序方式与显示名。白名单制：
# 不直接把 request.GET 的值传给代码，避免 ?sort=任意值 导致意外行为
SORT_OPTIONS = {
    'latest': '最新',
    'hot': '热门',
}
DEFAULT_SORT = 'latest'


def post_list(request):
    """首页：文章列表 + 个人简介 / 今日歌曲 / 本周进度 / 项目精选。

    规划文档把首页定位为「聚合入口」而不是纯文章列表，
    所以这里要一次查多个模型。每个区块都用 first() 或切片取少量数据，
    不用全部取出来再截断。
    """
    posts = (
        Post.objects
        .filter(status='published')
        .select_related('category')
        .prefetch_related('tags')
        .order_by('-published_date')
    )
    categories = Category.objects.all()

    # 排序方式取自 URL 参数，非法值回退到默认值
    sort = request.GET.get('sort', DEFAULT_SORT)
    if sort not in SORT_OPTIONS:
        sort = DEFAULT_SORT

    # WIDGET_LIMIT：首页只展示少量内容，完整列表在各自的独立页面
    widget_limit = 5

    if sort == 'hot':
        # 热门排序必须在 Python 层算，所以先把全部结果取出来。
        # 这里有意不用 Paginator：热门排序需要先对整个集合排序才能
        # 知道前一页是哪几篇，若先分页再排，每页内部有序但页间无序。
        # 数据量上千后应改成 annotate + ExpressionWrapper 在数据库排序。
        posts = sort_by_hot(list(posts))
        page_obj = posts
    else:
        # 用 get_page 而不是 page：page() 在页码非法时抛异常导致 500，
        # get_page() 会把非法页码自动修正为第 1 页或最后一页
        paginator = Paginator(posts, widget_limit)
        page_obj = paginator.get_page(request.GET.get('page'))

    # 今日歌曲：按日期精确匹配。没有当天的就不显示这个区块，
    # 不拿旧歌凑数，否则「今日歌曲」会变成「上一首歌」
    today_song = DailySong.objects.filter(date=date.today()).first()

    # 本周进度：取最新一条（模型 Meta 已按 -year、-week 排序）
    latest_progress = WeeklyProgress.objects.first()

    # 项目精选：已经在后台用 sort_order 手控好了顺序，取前 3 个
    featured_projects = Project.objects.all()[:3]

    # 个人资料：Profile 是单例，还没填时返回空对象而不是 404
    profile, _ = Profile.objects.get_or_create(pk=1)

    return render(request, 'blog/post_list.html', {
        'posts': page_obj,
        'page_obj': page_obj,
        'categories': categories,
        'sort': sort,
        'sort_options': SORT_OPTIONS,
        'today_song': today_song,
        'latest_progress': latest_progress,
        'featured_projects': featured_projects,
        'profile': profile,
    })


def post_detail(request, slug):
    """文章详情页：按 slug 查单篇。"""
    # 用 get_object_or_404 而不是 Post.objects.get()：
    # get() 找不到会抛 DoesNotExist → 500 服务器错误；
    # get_object_or_404 会自动转成 404 页面。
    # 「文章不存在」是正常情况，不该表现为代码出错。
    post = get_object_or_404(
        Post.objects.select_related('category').prefetch_related('tags'),
        slug=slug,
        status='published',
    )
    Post.objects.filter(pk=post.pk).update(views=F('views') + 1)
    # 只在内存里 +1，不用 refresh_from_db() 再查一次数据库：
    # update() 已把新值写入库中，这里只需要让模板显示的数字对得上
    post.views += 1
    return render(request, 'blog/post_detail.html', {"post": post})


def category_posts(request, slug):
    """某个分类下的已发布文章。"""
    # 先取分类，分类不存在则 404（而不是显示一个空列表）
    category = get_object_or_404(Category, slug=slug)
    # 用 Post.objects.filter(category=category) 而不是 category.posts：
    # 两者 SQL 完全相同，但后者是 related_name 动态生成的反向属性，
    # 静态类型检查器看不到它，写成正向查询能消除误报且意图更明确
    posts = (
        Post.objects
        .filter(category=category, status='published')
        .select_related('category')
        .prefetch_related('tags')
        .order_by('-published_date')
    )
    # title 传给模板做页面标题，这样 post_filter.html 不用判断
    # 「当前是分类页还是标签页」，两个视图共用同一个模板
    page_obj = _paginate(request, posts)
    return render(request, 'blog/post_filter.html', {
        'title': f'分类：{category.name}',
        'posts': page_obj,
        'page_obj': page_obj,
    })


def tag_posts(request, slug):
    """某个标签下的已发布文章。逻辑与 category_posts 相同，只是换模型。

    没有合并成一个函数，是因为合并需要把模型类当参数传进来，
    可读性反而不如两个各自 5 行的独立函数。
    """
    tag = get_object_or_404(Tag, slug=slug)
    # 同样改用正向查询：Post.objects.filter(tags=tag) 与 tag.posts 等价，
    # 但静态检查器能识别前者，避免 related_name 造成的类型报错
    posts = (
        Post.objects
        .filter(tags=tag, status='published')
        .select_related('category')
        .prefetch_related('tags')
        .order_by('-published_date')
    )
    page_obj = _paginate(request, posts)
    return render(request, 'blog/post_filter.html', {
        'title': f'标签：{tag.name}',
        'posts': page_obj,
        'page_obj': page_obj,
    })


def search(request):
    form = SearchForm(request.GET or None)
    posts = Post.objects.none()  # 默认空 QuerySet
    keyword = ''

    if form.is_valid():
        keyword = form.cleaned_data['q'].strip()
        if keyword:
            posts = Post.objects.filter(
                Q(title__icontains=keyword) | Q(text__icontains=keyword),
                status='published',
            ).order_by('-published_date')

    return render(request, 'blog/search.html', {
        'form': form,
        'posts': posts,
        'keyword': keyword,
    })


def _paginate(request, queryset, per_page=5):
    """对 queryset 分页，返回 page_obj。三个列表视图共用。"""
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(request.GET.get('page'))


def projects(request):
    """项目列表。按 sort_order 升序（手控排序），再按创建时间倒序作为次级排序。"""
    items = Project.objects.all()
    return render(request, 'blog/projects.html', {'projects': items})


def project_detail(request, slug):
    """项目详情。"""
    project = get_object_or_404(Project, slug=slug)
    return render(request, 'blog/project_detail.html', {'project': project})


def progress_list(request):
    """学习进度列表，按年、周倒序。"""
    items = WeeklyProgress.objects.all()
    return render(request, 'blog/progress_list.html', {
        'progresses': items,
        'page_obj': _paginate(request, items, per_page=12),
    })

def progress_detail(request, year, week):
    """某周的进度详情。用年+周定位，而不是主键：URL 可读且稳定。"""
    item = get_object_or_404(WeeklyProgress, year=year, week=week)
    return render(request, 'blog/progress_detail.html', {'progress': item})


def song_list(request):
    """每日歌曲列表，一天一首，按日期倒序。"""
    items = DailySong.objects.all()
    return render(request, 'blog/song_list.html', {
        'songs': items,
        'page_obj': _paginate(request, items, per_page=12),
    })


def about(request):
    """关于页：静态文字 + 可选的个人资料。"""
    # 用 get_or_create 而不是直接取：还没在后台填资料时不能报 404
    profile, _ = Profile.objects.get_or_create(pk=1)
    return render(request, 'blog/about.html', {'profile': profile})
