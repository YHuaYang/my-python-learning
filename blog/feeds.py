from django.contrib.syndication.views import Feed
from django.urls import reverse

from .models import Post


class LatestPostsFeed(Feed):
    title = '多于点线圈-blog'
    link = '/'
    description = '最新发布的文章'

    def items(self):
        return Post.objects.filter(status='published').order_by('-published_date')[:20]
    def item_title(self,item):
        return item.title
    def item_description(self, item):
        return item.excerpt or item.text[:200]
    def item_link(self, item):
        return reverse('post_detail', kwargs={'slug':item.slug})
    def item_pubdate(self, item):
        return item.published_date
