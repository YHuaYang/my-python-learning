"""测试模块。

测试的价值不是「证明代码是对的」，而是「锁住已经确认过的行为」：
以后改动时，如果某条规则被无意破坏，测试会立刻失败告诉你。

跑测试：
    python manage.py test

测试会创建独立的 test_db.sqlite3，结束后销毁，不碰真实数据库。
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Category, Post, Tag


class DraftIsolationTest(TestCase):
    """草稿 / 下架文章绝不能出现在前台。

    这是内容站最严重的越权风险：列表过滤了但详情没过滤，
    别人猜到 slug 就能读到未发布内容。
    """

    def setUp(self):
        # setUp 在每个 test_ 方法前执行；每个方法结束后事务回滚，
        # 所以测试之间互不影响，可以放心造数据
        User = get_user_model()
        self.user = User.objects.create_user(username='tester', password='x')

        self.category = Category.objects.create(name='教程', type='教程')
        self.tag = Tag.objects.create(name='Django')

        self.published = Post.objects.create(
            author=self.user,
            title='已发布文章',
            text='正文内容',
            status='published',
            category=self.category,
        )
        self.published.tags.set([self.tag])

        # status='draft' 不满足 save() 里「published 才补时间」的条件，
        # 所以 published_date 保持 None，正合预期
        self.draft = Post.objects.create(
            author=self.user,
            title='草稿文章',
            text='草稿正文',
            status='draft',
        )
        self.draft.tags.set([self.tag])

        self.archived = Post.objects.create(
            author=self.user,
            title='已下架文章',
            text='下架正文',
            status='archived',
            category=self.category,
        )

    def test_list_shows_only_published(self):
        """首页只显示已发布文章"""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '已发布文章')
        self.assertNotContains(response, '草稿文章')
        self.assertNotContains(response, '已下架文章')

    def test_draft_detail_returns_404(self):
        """草稿详情页 404，不能靠猜 slug 访问"""
        response = self.client.get(f'/posts/{self.draft.slug}/')
        self.assertEqual(response.status_code, 404)

    def test_archived_detail_returns_404(self):
        """已下架文章详情页也 404"""
        response = self.client.get(f'/posts/{self.archived.slug}/')
        self.assertEqual(response.status_code, 404)

    def test_published_detail_returns_200(self):
        """已发布文章正常显示，作为对照组"""
        response = self.client.get(f'/posts/{self.published.slug}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '已发布文章')

    def test_search_excludes_draft(self):
        """搜索结果不含草稿"""
        response = self.client.get('/search/', {'q': '草稿'})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '草稿文章')

    def test_category_page_excludes_archived(self):
        """分类页不含已下架文章"""
        response = self.client.get(f'/category/{self.category.slug}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '已发布文章')
        self.assertNotContains(response, '已下架文章')

    def test_tag_page_excludes_draft_and_archived(self):
        """标签页：草稿与下架文章都打了同一标签，但都不该出现"""
        response = self.client.get(f'/tag/{self.tag.slug}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '已发布文章')
        self.assertNotContains(response, '草稿文章')
        self.assertNotContains(response, '已下架文章')


class PaginationTest(TestCase):
    """分页行为，重点是非法页码不能导致 500。"""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='pager', password='x')
        # 造 7 篇已发布文章，每页 5 条 → 2 页
        for i in range(7):
            Post.objects.create(
                author=self.user,
                title=f'文章{i}',
                text='x',
                status='published',
            )

    def test_first_page_has_five(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['posts']), 5)
        self.assertTrue(response.context['page_obj'].has_next())

    def test_second_page_has_two(self):
        response = self.client.get('/', {'page': 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['posts']), 2)
        self.assertFalse(response.context['page_obj'].has_next())

    def test_out_of_range_page_falls_back_to_last(self):
        """?page=999 应回退到最后一页而不是报错。

        如果视图用 paginator.page() 而非 get_page()，这里会抛
        EmptyPage 变成 500。
        """
        response = self.client.get('/', {'page': 999})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['page_obj'].number, 2)

    def test_non_numeric_page_falls_back_to_first(self):
        """?page=abc 应回退到第 1 页"""
        response = self.client.get('/', {'page': 'abc'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['page_obj'].number, 1)


class PostModelTest(TestCase):
    """模型层的两个关键逻辑：中文 slug 生成、状态与时间的一致性。"""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='modeluser', password='x')

    def test_slug_generated_from_chinese_title(self):
        """中文标题能生成非空 slug（依赖 allow_unicode=True）"""
        post = Post.objects.create(
            author=self.user, title='测试中文标题', text='x', status='draft'
        )
        self.assertTrue(post.slug)
        self.assertEqual(post.slug, '测试中文标题')

    def test_duplicate_title_gets_numeric_suffix(self):
        """重复标题追加 -2，避免撞 unique 约束"""
        first = Post.objects.create(
            author=self.user, title='重名文章', text='x', status='draft'
        )
        second = Post.objects.create(
            author=self.user, title='重名文章', text='y', status='draft'
        )
        self.assertEqual(first.slug, '重名文章')
        self.assertEqual(second.slug, '重名文章-2')

    def test_published_post_gets_date_automatically(self):
        """状态为 published 但没填时间时，save() 自动补当前时间"""
        post = Post.objects.create(
            author=self.user, title='自动补时间', text='x', status='published'
        )
        self.assertIsNotNone(post.published_date)

    def test_draft_keeps_null_date(self):
        """草稿不自动补发布时间"""
        post = Post.objects.create(
            author=self.user, title='草稿不补时间', text='x', status='draft'
        )
        self.assertIsNone(post.published_date)

    def test_editing_does_not_change_slug(self):
        """编辑已有文章时 slug 不变（exclude(pk=self.pk) 的作用）"""
        post = Post.objects.create(
            author=self.user, title='slug稳定性', text='x', status='draft'
        )
        original_slug = post.slug
        post.text = '改过的正文'
        post.save()
        post.refresh_from_db()
        self.assertEqual(post.slug, original_slug)


class FeedAndSitemapTest(TestCase):
    """RSS 与 sitemap 的结构正确性。"""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='feeduser', password='x')
        Post.objects.create(
            author=self.user, title='订阅里的文章', text='x', status='published'
        )
        Post.objects.create(
            author=self.user, title='不该出现的草稿', text='x', status='draft'
        )

    def test_rss_returns_xml(self):
        response = self.client.get('/rss/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('xml', response['Content-Type'])

    def test_rss_contains_published_only(self):
        response = self.client.get('/rss/')
        content = response.content.decode()
        self.assertIn('订阅里的文章', content)
        self.assertNotIn('不该出现的草稿', content)

    def test_sitemap_returns_xml(self):
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        self.assertIn('xml', response['Content-Type'])

    def test_sitemap_contains_static_pages(self):
        response = self.client.get('/sitemap.xml')
        content = response.content.decode()
        # 用 Site 的 domain 拼出的绝对地址，末尾是站点根和关于页
        self.assertIn('/about/', content)
