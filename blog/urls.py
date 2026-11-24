"""
urls.py 是路由表，它决定了去views.py调用哪些函数去处理
"""
from django.contrib.sitemaps.views import sitemap
from django.urls import path

from . import views
from .feeds import LatestPostsFeed
from .sitemaps import PostSitemap, StaticViewSitemap

sitemaps={
    'posts': PostSitemap,
    'static': StaticViewSitemap,
}

urlpatterns = [
    # path('',...)的空字符串（''）代表根目录
    # <str:slug>可以转换中文，而 <slug:slug>会404
    # name 用来反向解析{% url 'post_list' %}，之后要改路径直接改模板就行
    path('', views.post_list, name='post_list'),
    # 归档页：首页只展示最新 N 篇，其余全在这里
    path('archive/', views.archive, name='archive'),
    path('about/', views.about, name='about'),
    path('posts/<str:slug>/', views.post_detail, name='post_detail'),
    path('tag/<str:slug>/', views.tag_posts, name='tag_posts'),
    path('category/<str:slug>/', views.category_posts, name='category_posts'),
    path('search/', views.search, name='search'),

    # 项目：固定路径与通配路径要注意顺序，固定路径必须在前，
    # 否则 projects/ 会被 projects/<str:slug>/ 抢走
    path('projects/', views.projects, name='projects'),
    path('projects/<str:slug>/', views.project_detail, name='project_detail'),

    # 进度：用「年 + 周」定位，比主键可读，且对 SEO 友好
    path('progress/', views.progress_list, name='progress_list'),
    path('progress/<int:year>-w<int:week>/', views.progress_detail, name='progress_detail'),

    path('rss/',LatestPostsFeed(),name='rss'),
    path('sitemap.xml',sitemap,{'sitemaps':sitemaps},name='sitemap'),

    # robots.txt 必须在根路径：爬虫只认域名下的 /robots.txt，
    # 放到子目录（如 /static/robots.txt）不会被读取
    path('robots.txt', views.robots_txt, name='robots_txt'),

    # 后台 Markdown 编辑器的图片上传接口。
    # 放在 /admin/ 之外的独立路径：编辑器直接 POST 到这里。
    # 权限由视图里的 @login_required + is_staff 双重把关。
    path(
        'admin-upload-image/',
        views.upload_editor_image,
        name='upload_editor_image',
    ),
]