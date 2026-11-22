"""测试模块。

测试的价值不是「证明代码是对的」，而是「锁住已经确认过的行为」：
以后改动时，如果某条规则被无意破坏，测试会立刻失败告诉你。

跑测试：
    python manage.py test

测试会创建独立的 test_db.sqlite3，结束后销毁，不碰真实数据库。
"""
import io
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from .forms import GuestbookForm
from .models import Category, GuestbookMessage, Post, Profile, Tag


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
    """分页行为，重点是非法页码不能导致 500。

    首页已改为固定 6 篇、不分页，所以用例改用分类页：
    _paginate() 仍被分类/标签/搜索/进度页使用，分页逻辑照旧需要保护。
    """

    def setUp(self):
        self.user = make_user('pager')
        self.category = Category.objects.create(name='分页测试', type='教程')
        # 造 7 篇已发布文章，每页 5 条 → 2 页
        for i in range(7):
            Post.objects.create(
                author=self.user,
                title=f'文章{i}',
                text='x',
                status='published',
                category=self.category,
            )
        self.url = f'/category/{self.category.slug}/'

    def test_first_page_has_five(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['posts']), 5)
        self.assertTrue(response.context['page_obj'].has_next())

    def test_second_page_has_two(self):
        response = self.client.get(self.url, {'page': 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['posts']), 2)
        self.assertFalse(response.context['page_obj'].has_next())

    def test_out_of_range_page_falls_back_to_last(self):
        """?page=999 应回退到最后一页而不是报错。

        如果视图用 paginator.page() 而非 get_page()，这里会抛
        EmptyPage 变成 500。
        """
        response = self.client.get(self.url, {'page': 999})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['page_obj'].number, 2)

    def test_non_numeric_page_falls_back_to_first(self):
        """?page=abc 应回退到第 1 页"""
        response = self.client.get(self.url, {'page': 'abc'})
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


class HomePostLimitTest(TestCase):
    """首页只展示最新 6 篇，其余进归档。"""

    def setUp(self):
        self.user = make_user('lister')
        now = timezone.now()
        # 造 9 篇已发布文章。注意时间方向：
        # published_date = now - i 小时，所以 i 越小越新，
        # 文章0 最新、文章8 最旧。
        for i in range(9):
            post = Post.objects.create(
                author=self.user,
                title=f'文章{i}',
                text='x',
                status='published',
            )
            # 绕过 save() 精确控制发布时间（save() 会自动写成当前时间）
            Post.objects.filter(pk=post.pk).update(
                published_date=now - timedelta(hours=i)
            )

    def test_home_shows_at_most_six(self):
        """首页最多 6 篇，即使有 9 篇已发布"""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['posts']), 6)

    def test_home_shows_newest_first(self):
        """首页取最新的 6 篇（文章0-5），从新到旧"""
        response = self.client.get('/')
        titles = [p.title for p in response.context['posts']]
        self.assertEqual(titles, [f'文章{i}' for i in range(6)])

    def test_home_excludes_older_than_limit(self):
        """最旧的 3 篇（文章6-8）不出现在首页"""
        response = self.client.get('/')
        titles = [p.title for p in response.context['posts']]
        for i in range(6, 9):
            self.assertNotIn(f'文章{i}', titles)

    def test_home_has_no_pagination(self):
        """首页不再分页：带 page 参数也不报错，内容不变"""
        response = self.client.get('/', {'page': 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['posts']), 6)

    def test_home_with_fewer_than_limit(self):
        """文章不足 6 篇时全部展示，不出错"""
        Post.objects.all().delete()
        for i in range(3):
            Post.objects.create(
                author=self.user, title=f'少量{i}', text='x', status='published'
            )
        response = self.client.get('/')
        self.assertEqual(len(response.context['posts']), 3)


class ArchiveTest(TestCase):
    """归档页：首页之外的剩余文章，按月份分组。"""

    def setUp(self):
        self.user = make_user('archiver')

    def _make(self, title, days_ago):
        post = Post.objects.create(
            author=self.user,
            title=title,
            text='x',
            status='published',
        )
        Post.objects.filter(pk=post.pk).update(
            published_date=timezone.now() - timedelta(days=days_ago)
        )
        return post

    def test_archive_page_renders(self):
        self._make('旧文', days_ago=10)
        response = self.client.get('/archive/')
        self.assertEqual(response.status_code, 200)

    def test_archive_excludes_home_posts(self):
        """首页那 6 篇不出现在归档页"""
        for i in range(9):
            self._make(f'文章{i}', days_ago=i)
        response = self.client.get('/archive/')
        archived = []
        for _key, posts in response.context['groups']:
            archived.extend(p.title for p in posts)
        # days_ago = i 所以文章0 最新。首页占 0-5，归档剩 6-8
        self.assertEqual(sorted(archived), ['文章6', '文章7', '文章8'])

    def test_archive_is_complement_of_home(self):
        """首页 + 归档 = 全部已发布文章，不重不漏"""
        for i in range(9):
            self._make(f'文章{i}', days_ago=i)

        home = {p.pk for p in self.client.get('/').context['posts']}
        archived = set()
        for _key, posts in self.client.get('/archive/').context['groups']:
            archived.update(p.pk for p in posts)

        all_ids = set(Post.objects.filter(status='published').values_list('pk', flat=True))
        self.assertEqual(home & archived, set())        # 不重
        self.assertEqual(home | archived, all_ids)      # 不漏

    def test_archive_empty_when_few_posts(self):
        """不足 6 篇时归档页为空，且给出提示"""
        for i in range(3):
            self._make(f'少量{i}', days_ago=i)
        response = self.client.get('/archive/')
        self.assertEqual(response.context['groups'], [])
        self.assertContains(response, '没有更早的文章')

    def test_archive_excludes_draft(self):
        """草稿不进归档"""
        for i in range(7):
            self._make(f'已发布{i}', days_ago=i)
        Post.objects.create(
            author=self.user, title='这是草稿', text='x', status='draft'
        )
        response = self.client.get('/archive/')
        archived = []
        for _key, posts in response.context['groups']:
            archived.extend(p.title for p in posts)
        self.assertNotIn('这是草稿', archived)

    def test_archive_groups_by_month(self):
        """按月份分组，同月归在一起"""
        # 先占满首页 6 个位置
        for i in range(6):
            self._make(f'首页{i}', days_ago=i)
        # 再放两篇同日期的旧文，应归到同一组
        self._make('旧文A', days_ago=100)
        self._make('旧文B', days_ago=100)

        response = self.client.get('/archive/')
        groups = response.context['groups']
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0][1]), 2)



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


class ProfileAvatarTest(TestCase):
    """头像：上传优先于外链，都没设时不出破图。"""

    def setUp(self):
        self.profile, _ = Profile.objects.get_or_create(pk=1)
        self.profile.nickname = '测试用户'
        self.profile.avatar = ''
        self.profile.avatar_url = ''
        self.profile.save()

    def _png(self, name='avatar.png', color=(194, 81, 0)):
        """造一张最小合法 PNG。不能手写字节，
        因为 ImageField 会真的解码校验，伪造的字节会验证失败。"""
        from PIL import Image
        buf = io.BytesIO()
        Image.new('RGB', (32, 32), color).save(buf, format='PNG')
        buf.seek(0)
        return SimpleUploadedFile(name, buf.read(), content_type='image/png')

    def test_avatar_src_empty_when_nothing_set(self):
        """两个都空时 avatar_src 返回空字符串，模板据此不渲染 img"""
        self.assertEqual(self.profile.avatar_src, '')

    def test_avatar_src_falls_back_to_url(self):
        """没上传时用外链"""
        self.profile.avatar_url = 'https://example.com/a.png'
        self.profile.save()
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.avatar_src, 'https://example.com/a.png')

    def test_uploaded_avatar_takes_priority(self):
        """两个都有时上传的图优先

        这是最容易写错的地方：如果用 `if avatar else avatar_url` 的反向逻辑，
        外链会盖住刚上传的图，用户会以为上传没生效。
        """
        self.profile.avatar_url = 'https://example.com/old.png'
        self.profile.avatar = self._png()
        self.profile.save()
        self.profile.refresh_from_db()

        self.assertTrue(self.profile.avatar_src.startswith('/media/'))
        self.assertNotIn('example.com', self.profile.avatar_src)

    def test_uploaded_avatar_renders_on_frontend(self):
        """上传后首页与关于页都显示这个头像"""
        self.profile.avatar = self._png()
        self.profile.save()
        self.profile.refresh_from_db()

        for path in ['/', '/about/']:
            response = self.client.get(path)
            self.assertContains(response, self.profile.avatar.url, msg_prefix=path)

    def tearDown(self):
        # 测试产生的上传文件不会随测试数据库回滚，要手动删
        self.profile.refresh_from_db()
        if self.profile.avatar:
            self.profile.avatar.delete(save=False)

