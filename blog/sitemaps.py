from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from .models import Post


class PostSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.8

    def items(self):
        return Post.objects.filter(status='published')

    def lastmod(self, obj):
        return obj.published_date

    # 不写 location()：Post 有 get_absolute_url()，Sitemap 会自动调用它


class StaticViewSitemap(Sitemap):
    # 静态页的更新频率低，优先级也略低于文章
    changefreq = 'monthly'
    priority = 0.5

    def items(self):
        # 返回的是 URL name 列表
        return ['post_list', 'about']

    def location(self, item):
        # items() 返回的是 name，这里反向解析成路径
        return reverse(item)