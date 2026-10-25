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
from django.db.models import F


def post_list(request):
    """首页：已发布文章列表（新→旧）+ 分类导航。"""
    # 首页要看两样东西，所以查两次不同的表：
    # posts 用于正文列表，categories 用于底部的分类入口
    posts=Post.objects.filter(status='published').order_by('-published_date')
    categories = Category.objects.all()
    return render(request,'blog/post_list.html',{"posts":posts,"categories":categories,})


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
    post = get_object_or_404(Post, slug=slug, status='published')
    Post.objects.filter(pk=post.pk).update(views=F('views') + 1)
    post.refresh_from_db()
    return render(request, 'blog/post_detail.html', {"post": post})


def category_posts(request, slug):
    """某个分类下的已发布文章。"""
    # 先取分类，分类不存在则 404（而不是显示一个空列表）
    category = get_object_or_404(Category, slug=slug)
    # category.posts 是 related_name='posts' 定义的反向查询，
    # 等价于 Post.objects.filter(category=category)，生成的 SQL 相同。
    # 注意仍然要自己加发布时间过滤，反向查询不会自动带上去。
    posts = category.posts.filter(
        status='published'
    ).order_by('-published_date')
    # title 传给模板做页面标题，这样 post_filter.html 不用判断
    # 「当前是分类页还是标签页」，两个视图共用同一个模板
    return render(request, 'blog/post_filter.html', {
        'title': f'分类：{category.name}',
        'posts': posts,
    })


def tag_posts(request, slug):
    """某个标签下的已发布文章。逻辑与 category_posts 相同，只是换模型。

    没有合并成一个函数，是因为合并需要把模型类当参数传进来，
    可读性反而不如两个各自 5 行的独立函数。
    """
    tag = get_object_or_404(Tag, slug=slug)
    posts = tag.posts.filter(
        status='published'
    ).order_by('-published_date')
    return render(request, 'blog/post_filter.html', {
        'title': f'标签：{tag.name}',
        'posts': posts,
    })
