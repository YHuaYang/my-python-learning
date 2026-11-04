"""
views.py 处理用户请求：查数据 → 选模板 → 返回 HTML。

每个视图函数接收一个 request（Django 传进来的请求对象），
必须返回一个 HttpResponse（render() 就是快捷方式之一）。

全局约定：所有对外展示文章的查询都必须加
    published_date__lte=timezone.now()
否则草稿（published_date 为 NULL）会被直接访问到。
筛选条件「列表里过滤了、详情里忘了过滤」是内容站最常见的越权漏洞。
"""
from django.shortcuts import render,get_object_or_404
from .models import Post,Category,Tag
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
    """首页：已发布文章列表，支持「最新 / 热门」切换。"""
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
        paginator = Paginator(posts, 5)
        page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'blog/post_list.html', {
        'posts': page_obj,
        'page_obj': page_obj,
        'categories': categories,
        'sort': sort,
        'sort_options': SORT_OPTIONS,
    })


def about(request):
    """关于页：纯静态内容，不需要查数据库，所以不传上下文。"""
    # request 参数虽然没用到，但签名里必须有，Django 会按位置传入
    return render(request, 'blog/about.html')


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
