"""
views.py 处理用户请求：查数据 → 选模板 → 返回 HTML。

每个视图函数接收一个 request（Django 传进来的请求对象），
必须返回一个 HttpResponse（render() 就是快捷方式之一）。

全局约定：所有对外展示文章的查询都必须加
    published_date__lte=timezone.now()
否则草稿（published_date 为 NULL）会被直接访问到。
筛选条件「列表里过滤了、详情里忘了过滤」是内容站最常见的越权漏洞。
"""
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, redirect, render

from .forms import GuestbookForm, SearchForm
from .models import (
    Category,
    GuestbookMessage,
    Post,
    Profile,
    Project,
    Tag,
    WeeklyProgress,
)


# 首页只展示最新 N 篇，超出部分进归档页。
# 用篇数而不是天数：写作频率不稳时，天数窗口会让首页时而有内容、
# 时而空白；篇数上限保证首页始终是一个固定的矩，
# 且“第 N+1 篇出现时最早的一篇自动移出”是个可预期的行为。
HOME_POST_LIMIT = 6


def post_list(request):
    """首页：最新文章 + 个人简介 / 本周进度 / 项目精选。"""
    posts = (
        Post.objects
        .filter(status='published')
        .select_related('category')
        .prefetch_related('tags')
        .order_by('-published_date')[:HOME_POST_LIMIT]
    )
    categories = Category.objects.all()

    # 本周进度：取最新一条（模型 Meta 已按 -year、-week 排序）
    latest_progress = WeeklyProgress.objects.first()

    # 项目精选：已经在后台用 sort_order 手控好了顺序，取前 3 个
    featured_projects = Project.objects.all()[:3]

    # 个人资料：Profile 是单例，还没填时返回空对象而不是 404
    profile, _ = Profile.objects.get_or_create(pk=1)

    return render(request, 'blog/post_list.html', {
        'posts': posts,
        'categories': categories,
        'latest_progress': latest_progress,
        'featured_projects': featured_projects,
        'profile': profile,
    })


def archive(request):
    """归档页：首页之外的其余已发布文章，按月份分组。

    与首页是整体与补集的关系：首页取最新 N 篇，这里取剩下的。
    用同一个 HOME_POST_LIMIT 切片口径，两页加起来恰好是全部，
    不会重复也不会漏。
    """
    all_posts = (
        Post.objects
        .filter(status='published')
        .select_related('category')
        .order_by('-published_date')
    )

    # 切成首页之外的部分。先取 N 篇切片的长度而不是硬写 HOME_POST_LIMIT：
    # 文章不足 N 篇时，首页已经全部展示，归档页应为空而不是负数切片。
    home_ids = list(all_posts[:HOME_POST_LIMIT].values_list('pk', flat=True))
    older_posts = all_posts.exclude(pk__in=home_ids)

    # 按月份分组。在 Python 层分组而不是数据库 GROUP BY：
    # 需要在模板里直接遍历嵌套结构，且还要分页，
    # 数据库聚合之后还要二次查询取具体文章，反而更繁。
    groups = []
    for post in older_posts:
        if post.published_date is None:
            continue
        key = (post.published_date.year, post.published_date.month)
        if not groups or groups[-1][0] != key:
            groups.append((key, []))
        groups[-1][1].append(post)

    return render(request, 'blog/archive.html', {
        'groups': groups,
        'total': older_posts.count(),
    })


def post_detail(request, slug):
    """文章详情页：按 slug 查单篇。"""
    post = get_object_or_404(
        Post.objects.select_related('category').prefetch_related('tags'),
        slug=slug,
        status='published',
    )
    Post.objects.filter(pk=post.pk).update(views=F('views') + 1)
    post.views += 1

    ip = request.META.get('REMOTE_ADDR', '')

    if request.method == 'POST':
        form = GuestbookForm(request.POST)

        # 限流先于校验：被限流的人不该再看到字段错误，否则提示混乱
        rate_key = f'guestbook:{ip}'
        if cache.get(rate_key, 0) >= 3:
            # 用表单级错误而不是返回 429：
            # 直接 429 会让页面变成白屏错误页，用户看不到已有留言
            form.add_error(None, '发送太频繁了，请一小时后再试')
        elif form.is_valid():
            # commit=False 拿到对象但不入库，用来补两个表单里没有的字段。
            # post 不补就会是 NULL，留言会变成全局留言，文章页看不到；
            # ip_address 不补就无法追溯到具体来源
            obj = form.save(commit=False)
            obj.post = post
            obj.ip_address = ip
            obj.save()
            # 计数放在 save() 之后：校验失败不该消耗额度，
            # 否则用户空提交三次就被锁了
            cache.set(rate_key, cache.get(rate_key, 0) + 1, 3600)
            # PRG（Post/Redirect/Get）：成功后必须重定向，
            # 否则用户按 F5 会重复提交同一份表单
            return redirect('post_detail', slug=post.slug)
        # 校验失败时什么都不做：form 带着错误往下流到 render
    else:
        form = GuestbookForm()

    # post 与 is_approved 两个条件缺一不可：
    # 漏 post 会把所有文章的留言混在一起；
    # 漏 is_approved 会让未审核的留言直接公开。
    # 不能用 post.guestbook_messages.all()：那是 related_name 反查，
    # 拿到的是全部留言，包含未审核的
    guestbook_messages = GuestbookMessage.objects.filter(
        post=post,
        is_approved=True,
    )

    return render(request, 'blog/post_detail.html', {
        "post": post,
        "form": form,
        "guestbook_messages": guestbook_messages,
    })



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


def about(request):
    """关于页：静态文字 + 可选的个人资料。"""
    # 用 get_or_create 而不是直接取：还没在后台填资料时不能报 404
    profile, _ = Profile.objects.get_or_create(pk=1)
    return render(request, 'blog/about.html', {'profile': profile})
