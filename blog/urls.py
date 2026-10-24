"""
urls.py 是路由表，它决定了去views.py调用哪些函数去处理
"""
from django.urls import path
from . import views

urlpatterns = [
    # path('',...)的空字符串（''）代表根目录
    # <str:slug>可以转换中文，而 <slug:slug>会404
    # name 用来反向解析{% url 'post_list' %}，之后要改路径直接改模板就行
    path('', views.post_list, name='post_list'),
    path('about/', views.about, name='about'),
    path('posts/<str:slug>/', views.post_detail, name='post_detail'),
    path('tag/<str:slug>/', views.tag_posts, name='tag_posts'),
    path('category/<str:slug>/', views.category_posts, name='category_posts'),
]