"""测试模块。

测试的价值不是「证明代码是对的」，而是「锁住已经确认过的行为」：
以后改动时，如果某条规则被无意破坏，测试会立刻失败告诉你。

跑测试：
    python manage.py test

测试会创建独立的 test_db.sqlite3，结束后销毁，不碰真实数据库。
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from .models import Category, Post, Tag, GuestbookMessage
from .forms import GuestbookForm
from .ranking import hot_score, sort_by_hot


def make_user(username):
    """建一个测试用户。

    为什么要单独封一个函数：django-stubs 把 get_user_model() 推导为
    type[AbstractBaseUser]，而 create_user 定义在 UserManager 上，
    静态检查器因此报错。运行时完全正常（20 个测试全过），
    这里集中屏蔽一次，避免四处重复。
    """
    User = get_user_model()
    return User.objects.create_user(username=username, password='x')  # type: ignore[attr-defined]


class DraftIsolationTest(TestCase):
    """草稿 / 下架文章绝不能出现在前台。

    这是内容站最严重的越权风险：列表过滤了但详情没过滤，
    别人猜到 slug 就能读到未发布内容。
    """

    def setUp(self):
        # setUp 在每个 test_ 方法前执行；每个方法结束后事务回滚，
        # 所以测试之间互不影响，可以放心造数据
        self.user = make_user('tester')

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
        self.user = make_user('pager')
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
        self.user = make_user('modeluser')

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
        self.user = make_user('feeduser')
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


class HotRankingTest(TestCase):
    """热度排序算法（Hacker News 公式）。

    公式：score = views / (age_hours + 2) ** 1.5
    这些测试固定住了参数与边界行为，改动公式时会立刻暴露。
    """

    def setUp(self):
        self.user = make_user('hotuser')
        self.now = timezone.now()

    def _make(self, title, views, hours_ago):
        post = Post.objects.create(
            author=self.user,
            title=title,
            text='x',
            status='published',
        )
        # 直接写库绕过 save()，以便精确控制发布时间
        Post.objects.filter(pk=post.pk).update(
            views=views,
            published_date=self.now - timedelta(hours=hours_ago),
        )
        post.refresh_from_db()
        return post

    def test_formula_matches_manual_calculation(self):
        """分数必须严格等于 views / (hours + 2) ** 1.5"""
        post = self._make('公式验证', views=10, hours_ago=22)
        expected = 10 / (22 + 2) ** 1.5
        self.assertAlmostEqual(hot_score(post, now=self.now), expected, places=10)

    def test_fresh_post_is_damped_by_offset(self):
        """刚发布的文章分母是 2 而非 0，分数不会爆炸"""
        post = self._make('刚发布', views=1, hours_ago=0)
        # 1 / 2^1.5 而不是 1 / 0
        self.assertAlmostEqual(hot_score(post, now=self.now), 1 / 2 ** 1.5, places=6)

    def test_more_views_ranks_higher_at_same_age(self):
        """同年龄时，阅读量高的排前面"""
        low = self._make('低阅读', views=1, hours_ago=10)
        high = self._make('高阅读', views=100, hours_ago=10)
        self.assertGreater(hot_score(high, now=self.now), hot_score(low, now=self.now))

    def test_newer_ranks_higher_at_same_views(self):
        """同阅读量时，更新的排前面"""
        old = self._make('旧文章', views=5, hours_ago=100)
        new = self._make('新文章', views=5, hours_ago=1)
        self.assertGreater(hot_score(new, now=self.now), hot_score(old, now=self.now))

    def test_zero_views_scores_zero(self):
        post = self._make('零阅读', views=0, hours_ago=1)
        self.assertEqual(hot_score(post, now=self.now), 0.0)

    def test_future_date_does_not_produce_negative_age(self):
        """时钟回拨导致未来时间时，年龄兜底为 0，不出现负数或无穷大"""
        post = self._make('未来时间', views=5, hours_ago=-10)
        self.assertAlmostEqual(hot_score(post, now=self.now), 5 / 2 ** 1.5, places=6)

    def test_sort_by_hot_orders_descending(self):
        self._make('A阅读少', views=1, hours_ago=10)
        self._make('B阅读多', views=50, hours_ago=10)
        self._make('C很旧', views=50, hours_ago=1000)

        posts = list(Post.objects.filter(status='published'))
        ordered = sort_by_hot(posts, now=self.now)
        self.assertEqual(ordered[0].title, 'B阅读多')


class HomeSortSwitchTest(TestCase):
    """首页「最新 / 热门」切换。"""

    def setUp(self):
        self.user = make_user('sorter')
        now = timezone.now()
        # 稍旧但阅读量很高（10000/(50+2)^1.5 ≈ 26.6）
        old_hot = Post.objects.create(
            author=self.user, title='旧的爆款', text='x', status='published'
        )
        Post.objects.filter(pk=old_hot.pk).update(
            views=10000, published_date=now - timedelta(hours=50)
        )
        # 最新但完全没人看（0 阅读，分数恒为 0）
        new_cold = Post.objects.create(
            author=self.user, title='新的冷门', text='x', status='published'
        )
        Post.objects.filter(pk=new_cold.pk).update(
            views=0, published_date=now - timedelta(hours=0)
        )

    def test_default_is_latest(self):
        """不带参数时按时间倒序，新的在前"""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        titles = [p.title for p in response.context['posts']]
        self.assertEqual(titles[0], '新的冷门')

    def test_sort_hot_puts_high_views_first(self):
        """sort=hot 时阅读量高的在前

        选题参数在说明一点：公式并非「阅读量高就一定第一」。
        views=100 / 500 小时 算出来是 0.0089，反而输给
        views=1 / 1 小时的 0.1925（新文章权重优势）。
        所以这里用 10000 阅读对 50 小时，差距足够大才能压过时间因素。
        """
        response = self.client.get('/', {'sort': 'hot'})
        self.assertEqual(response.status_code, 200)
        titles = [p.title for p in response.context['posts']]
        self.assertEqual(titles[0], '旧的爆款')

    def test_invalid_sort_falls_back_to_latest(self):
        """非法排序值回退到最新，不报错"""
        response = self.client.get('/', {'sort': 'hacker'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['sort'], 'latest')

    def test_hot_mode_ignores_page_param(self):
        """热门模式不分页，传 page 也不应报错"""
        response = self.client.get('/', {'sort': 'hot', 'page': 999})
        self.assertEqual(response.status_code, 200)


class GuestbookTest(TestCase):
    """留言板：审核过滤、XSS 防护、限流。

    这是项目里第一个「访客写数据」的链路，最该测的三类风险：
      1. 未审核的留言被公开（过滤条件漏写）
      2. 访客输入被当成 HTML 执行（没转义）
      3. 无限提交把库塞满（没限流）
    """

    def setUp(self):
        # 每个测试都从空的限流计数开始，否则前一个测试用掉的额度
        # 会让后一个测试莫名被判超限。LocMemCache 是进程级单例，
        # 不清理就会跨测试残留
        cache.clear()
        self.addCleanup(cache.clear)

        self.user = make_user('guestbooker')
        self.post = Post.objects.create(
            author=self.user,
            title='留言测试文章',
            text='正文',
            status='published',
        )
        self.url = f'/posts/{self.post.slug}/'

    def _post_message(self, **kwargs):
        """发一条留言。默认值合法，传参可覆盖任意字段。"""
        data = {'nickname': '访客', 'content': '留言内容'}
        data.update(kwargs)
        return self.client.post(self.url, data)

    def test_get_shows_empty_form(self):
        """GET 请求给一个空表单，不报错"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.context['form'], GuestbookForm)
        self.assertEqual(response.context['guestbook_messages'].count(), 0)

    def test_valid_post_creates_unapproved_message(self):
        """合法提交：入库、关联到文章、默认未审核、记 IP"""
        response = self._post_message(nickname='小明', content='写得好')

        # 302 而不是 200：PRG 模式，重定向防 F5 重复提交
        self.assertEqual(response.status_code, 302)

        msg = GuestbookMessage.objects.get()
        self.assertEqual(msg.nickname, '小明')
        self.assertEqual(msg.content, '写得好')
        self.assertEqual(msg.post, self.post)
        # 默认不通过，必须后台点通过才公开
        self.assertFalse(msg.is_approved)
        self.assertIsNotNone(msg.ip_address)

    def test_unapproved_message_not_visible(self):
        """未审核的留言即使已入库，前台也看不到"""
        GuestbookMessage.objects.create(
            post=self.post, nickname='待审', content='这句话不该被看到',
        )
        response = self.client.get(self.url)
        self.assertNotContains(response, '这句话不该被看到')

    def test_approved_message_is_visible(self):
        """审核通过后前台可见（对照组）"""
        GuestbookMessage.objects.create(
            post=self.post, nickname='通过', content='这句话应该出现',
            is_approved=True,
        )
        response = self.client.get(self.url)
        self.assertContains(response, '这句话应该出现')

    def test_global_message_not_on_post_page(self):
        """post 为空的全局留言不该出现在文章页（三态外键的坑）"""
        GuestbookMessage.objects.create(
            post=None, nickname='全局', content='这条属于全局留言板',
            is_approved=True,
        )
        response = self.client.get(self.url)
        self.assertNotContains(response, '这条属于全局留言板')

    def test_message_stored_raw_but_rendered_escaped(self):
        """XSS：内容原样存库，但渲染时必须转义

        两件事都要测。只测「页面里没有 <script>」，也可能是因为
        内容压根没存进去；只测「库里存了原样」，又不知道渲染安不安全。
        """
        payload = '<script>alert(1)</script>'
        GuestbookMessage.objects.create(
            post=self.post, nickname='坏人', content=payload, is_approved=True,
        )

        msg = GuestbookMessage.objects.get()
        self.assertEqual(msg.content, payload)   # 存的是原样

        response = self.client.get(self.url)
        # 原始的 <script> 不能出现在 HTML 里（否则浏览器会执行）
        self.assertNotContains(response, payload)
        # 转义后的版本应该出现，证明内容确实渲染了
        self.assertContains(response, '&lt;script&gt;')

    def test_empty_content_rejected(self):
        """空内容不写库"""
        response = self._post_message(content='')
        self.assertEqual(response.status_code, 200)   # 重新渲染带错误
        self.assertEqual(GuestbookMessage.objects.count(), 0)

    def test_too_long_content_rejected(self):
        """超过 200 字不写库"""
        response = self._post_message(content='x' * 201)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(GuestbookMessage.objects.count(), 0)

    def test_empty_nickname_rejected(self):
        """昵称必填"""
        response = self._post_message(nickname='')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(GuestbookMessage.objects.count(), 0)

    def test_rate_limit_blocks_fourth_message(self):
        """限流：同一 IP 一小时只能发 3 条"""
        for i in range(3):
            response = self._post_message(content=f'第 {i} 条')
            self.assertEqual(response.status_code, 302, f'第 {i + 1} 条应成功')

        self.assertEqual(GuestbookMessage.objects.count(), 3)

        # 第 4 条被挡：不写库，重新渲染页面并带表单级错误
        response = self._post_message(content='第 4 条')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(GuestbookMessage.objects.count(), 3)
        self.assertTrue(response.context['form'].non_field_errors())

    def test_rate_limit_not_charged_on_invalid_form(self):
        """校验失败不消耗额度：否则乱提交三次就被锁了"""
        for _ in range(5):
            self._post_message(content='')      # 全部非法

        # 额度应该还是满的，合法提交仍能成功
        response = self._post_message(content='终于合法了')
        self.assertEqual(response.status_code, 302)

    def test_csrf_token_present_in_form(self):
        """表单必须带 CSRF token，否则提交会被 403"""
        response = self.client.get(self.url)
        self.assertContains(response, 'csrfmiddlewaretoken')
