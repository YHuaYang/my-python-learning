"""
urls.py 是路由表，它决定了去views.py调用哪些函数去处理
"""
from django.urls import path
from django.contrib.sitemaps.views import sitemap
from .feeds import LatestPostsFeed
from .sitemaps import PostSitemap,StaticViewSitemap
from . import views

sitemaps={
    'posts': PostSitemap,
    'static': StaticViewSitemap,
}

urlpatterns = [
    # path('',...)的空字符串（''）代表根目录
    # <str:slug>可以转换中文，而 <slug:slug>会404
    # name 用来反向解析{% url 'post_list' %}，之后要改路径直接改模板就行
    path('', views.post_list, name='post_list'),
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
]