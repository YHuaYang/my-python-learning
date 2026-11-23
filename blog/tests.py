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
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from .dashboard import dashboard_context
from .forms import GuestbookForm
from .models import Category, GuestbookMessage, Post, Profile, Project, Tag, VisitLog


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

    def test_robots_txt_is_plain_text(self):
        """robots.txt 必须是 text/plain，否则严格的爬虫会解析失败"""
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/plain', response['Content-Type'])

    def test_robots_txt_disallows_private_paths(self):
        """后台、搜索结果、RSS 不应被索引

        三个路径各有原因：
        /admin/ —— 登录页被收录既不必要也不安全
        /search/ —— 同关键词可生成无数 URL，重复内容稀释权重
        /rss/    —— 与文章页内容重复，不应两种形式都被索引
        """
        content = self.client.get('/robots.txt').content.decode()
        for path in ('/admin/', '/search/', '/rss/'):
            self.assertIn(f'Disallow: {path}', content, msg=path)

    def test_robots_txt_points_to_sitemap(self):
        """必须包含 Sitemap 行，爬虫靠它发现站点地图"""
        content = self.client.get('/robots.txt').content.decode()
        self.assertIn('Sitemap: http', content)
        self.assertIn('/sitemap.xml', content)

    def test_footer_has_no_sitemap_link(self):
        """页脚不再链到 sitemap.xml：人点开是一屏 XML，没意义

        它仍可通过 /robots.txt 被爬虫发现，这一点由上一个测试保证。
        """
        html = self.client.get('/').content.decode()
        i, j = html.find('<footer'), html.find('</footer>')
        footer = html[i:j]
        self.assertNotIn('Sitemap', footer)
        # RSS 要保留：技术读者会用它订阅
        self.assertIn('RSS', footer)


class AdminLocalizationTest(TestCase):
    """后台界面全中文，且不泄漏模板注释。

    两类问题的根源不同：
    1. 模型与字段名默认取 Python 标识符，需要显式 verbose_name
    2. unfold 不自带 locale，它的 {% trans %} 在中文环境下
       找不到翻译，原样输出英文。靠项目级 LOCALE_PATHS 解决
    """

    def setUp(self):
        self.user = make_user('adminviewer')
        # 必须同时是 staff 与 superuser：
        # is_staff 只决定「能不能登录后台」，
        # 具体模型页还需要 has_perm 检查，缺权限会返回 403 而不是登录页。
        # 测试关心的是文案与模板，为权限专门去配 Permission 对象不值得
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save(update_fields=['is_staff', 'is_superuser'])
        self.client.force_login(self.user)
        self.post = Post.objects.create(
            author=self.user, title='后台测试文章', text='x', status='published',
        )

    def test_no_template_comment_leak(self):
        """多行 {# ... #} 会被原样输出到 HTML，必须用 {% comment %}

        这是本项目的已知坑：AGENTS.md 记过 {# #} 只支持单行。
        """
        for path in ('/admin/', '/admin/blog/post/'):
            html = self.client.get(path).content.decode()
            self.assertNotIn('{#', html, msg=path)
            self.assertNotIn('#}', html, msg=path)

    def test_unfold_strings_translated(self):
        """unfold 的界面文案应被我们的语言包翻成中文"""
        from django.utils import translation
        from django.utils.translation import gettext

        with translation.override('zh-hans'):
            for msgid, expected in (
                ('Type to search', '输入以搜索'),
                ('Select', '选择'),
                ('Apply Filters', '应用筛选'),
                ('Recent actions', '最近操作'),
            ):
                self.assertEqual(gettext(msgid), expected, msgid)

    def test_search_placeholder_is_chinese(self):
        """搜索栏 placeholder 不能是英文"""
        html = self.client.get('/admin/blog/post/').content.decode()
        self.assertIn('输入以搜索', html)
        self.assertNotIn('Type to search', html)

    def test_model_labels_are_chinese(self):
        """模型与字段的 verbose_name 应全部中文

        判据：非 'ID' 且是纯 ASCII 且有字母 = 没设 verbose_name，
        Django 用了字段名本身。
        """
        from django.apps import apps

        english = []
        for model in apps.get_app_config('blog').get_models():
            for f in model._meta.fields:
                vn = str(f.verbose_name)
                if vn != 'ID' and vn.isascii() and any(c.isalpha() for c in vn):
                    english.append(f'{model.__name__}.{f.name}={vn!r}')
        self.assertEqual(english, [], f'仍有英文字段标签: {english}')

    def test_admin_uses_unfold_base_class(self):
        """所有 Admin 必须继承 unfold 的 ModelAdmin。

        漏了会怎样：页面布局、侧边栏、按钮仍是 unfold 外观
       （那些在模板与 CSS 里），但表单控件拿不到样式类，
        表现为「输入框无边框、与纯文本难区分、看不出哪里能填」。
        这个 bug 不易从代码看出来，只能靠测试或看页面发现。
        """
        from django.contrib import admin

        bad = []
        for model, obj in admin.site._registry.items():
            # Site 已换成 UnfoldSiteAdmin；User 是有意保留原生基类
            # （UserAdmin 带密码与权限穿梭框的自定义布局，
            #   多继承容易产生 MRO 冲突，而本站只有一个用户）
            if model._meta.label == 'auth.User':
                continue
            if not any('unfold' in b.__module__ for b in type(obj).__mro__):
                bad.append(model._meta.label)

        self.assertEqual(bad, [], f'这些 Admin 未使用 unfold 基类: {bad}')

    def test_admin_form_inputs_have_styles(self):
        """编辑页的文本输入框应带 unfold 的 Tailwind 样式类

        之前的 bug：继承了 django.contrib.admin.ModelAdmin，
        输入框只有 Django 原生的 vTextField（无边框），
        截图上看就像一段普通文字。
        """
        html = self.client.get(
            f'/admin/blog/post/{self.post.pk}/change/'
        ).content.decode()
        # unfold 给输入框加的样式类里一定有这个组合
        self.assertIn('border border-base-200', html)
        # 标题字段不能只剩原生 class
        self.assertNotRegex(html, r'name="title"[^>]*class="vTextField"')


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


class ProjectCoverTest(TestCase):
    """项目封面图：上传、展示、没传时不渲染 <img>。"""

    def setUp(self):
        self.user = make_user('projector')
        self.project = Project.objects.create(
            name='测试项目',
            summary='简介',
            tech_stack='Django',
        )

    def _png(self, name='cover.png', size=(800, 450)):
        """造一张 16:9 的合法 PNG。"""
        from PIL import Image
        buf = io.BytesIO()
        Image.new('RGB', size, (60, 90, 140)).save(buf, format='PNG')
        buf.seek(0)
        return SimpleUploadedFile(name, buf.read(), content_type='image/png')

    def test_cover_src_empty_when_not_uploaded(self):
        """没传封面时 cover_src 返回空串，模板据此不渲染 img"""
        self.assertEqual(self.project.cover_src, '')

    def test_no_img_tag_without_cover(self):
        """没传封面时列表页不出破图：不应有指向 media 的 img"""
        response = self.client.get('/projects/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '/media/projects/covers/')

    def test_uploaded_cover_renders_on_list_and_detail(self):
        """上传后列表页与详情页都显示封面"""
        self.project.cover = self._png()
        self.project.save()
        self.project.refresh_from_db()

        self.assertTrue(self.project.cover_src.startswith('/media/projects/covers/'))

        for path in ['/projects/', f'/projects/{self.project.slug}/']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertContains(response, self.project.cover_src, msg_prefix=path)
            # 16:9 裁切靠这个类，漏了会让不同尺寸的图把卡片撑变形
            self.assertContains(response, 'aspect-video', msg_prefix=path)

    def test_cover_is_optional(self):
        """封面是可选字段，不填也能正常保存与展示"""
        self.project.cover = ''
        self.project.save()
        response = self.client.get(f'/projects/{self.project.slug}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '测试项目')

    def tearDown(self):
        self.project.refresh_from_db()
        if self.project.cover:
            self.project.cover.delete(save=False)


class VisitLoggingTest(TestCase):
    """访问统计：记录什么、不记录什么。

    中间件的过滤规则是这张表的生命线。漏记只是数据少，
    多记会让统计完全失真（自己看页面、爬虫扫描都会算进访客）。
    """

    DESKTOP_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
    MOBILE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile'

    def setUp(self):
        self.user = make_user('visitor')

    def test_records_anonymous_get(self):
        """匿名访问前台会写入一条记录"""
        self.client.get('/', HTTP_USER_AGENT=self.DESKTOP_UA)
        self.assertEqual(VisitLog.objects.count(), 1)
        log = VisitLog.objects.get()
        self.assertEqual(log.path, '/')
        self.assertEqual(log.device, 'desktop')

    def test_detects_mobile(self):
        self.client.get('/', HTTP_USER_AGENT=self.MOBILE_UA)
        self.assertEqual(VisitLog.objects.get().device, 'mobile')

    def test_ignores_logged_in_user(self):
        """已登录用户（站主自己）不记录，否则趋势图变成自己的访问日志"""
        self.client.force_login(self.user)
        self.client.get('/', HTTP_USER_AGENT=self.DESKTOP_UA)
        self.assertEqual(VisitLog.objects.count(), 0)

    def test_ignores_bots(self):
        """爬虫 UA 不记录"""
        self.client.get('/', HTTP_USER_AGENT='Googlebot/2.1 (+http://www.google.com/bot.html)')
        self.assertEqual(VisitLog.objects.count(), 0)

    def test_ignores_admin_path(self):
        self.client.get('/admin/', HTTP_USER_AGENT=self.DESKTOP_UA)
        self.assertEqual(VisitLog.objects.count(), 0)

    def test_ignores_static_and_media(self):
        self.client.get('/static/css/tailwind.css', HTTP_USER_AGENT=self.DESKTOP_UA)
        self.client.get('/media/x.png', HTTP_USER_AGENT=self.DESKTOP_UA)
        self.assertEqual(VisitLog.objects.count(), 0)

    def test_ignores_non_2xx(self):
        """404 不记录：扫描器试探不该算进访问量"""
        self.client.get('/no-such-page/', HTTP_USER_AGENT=self.DESKTOP_UA)
        self.assertEqual(VisitLog.objects.count(), 0)

    def test_ignores_post(self):
        """只统计 GET；POST 是表单提交，不是浏览"""
        post = Post.objects.create(
            author=self.user, title='留言测试', text='x', status='published',
        )
        self.client.post(
            f'/posts/{post.slug}/',
            {'nickname': 'a', 'content': 'b'},
            HTTP_USER_AGENT=self.DESKTOP_UA,
        )
        # 重定向后客户端不会再自动发 GET，所以只应有 0 条
        self.assertEqual(VisitLog.objects.count(), 0)

    def test_strips_query_string(self):
        """query string 不计入 path，/x/?a=1 与 /x/?b=2 归为同一页"""
        self.client.get('/?sort=hot', HTTP_USER_AGENT=self.DESKTOP_UA)
        self.assertEqual(VisitLog.objects.get().path, '/')

    def test_external_referer_recorded(self):
        self.client.get(
            '/',
            HTTP_USER_AGENT=self.DESKTOP_UA,
            HTTP_REFERER='https://www.google.com/search?q=django',
        )
        self.assertEqual(VisitLog.objects.get().referer_host, 'www.google.com')

    def test_same_site_referer_ignored(self):
        """同站跳转不算外部来路"""
        self.client.get(
            '/',
            HTTP_USER_AGENT=self.DESKTOP_UA,
            HTTP_REFERER='http://testserver/projects/',
        )
        self.assertEqual(VisitLog.objects.get().referer_host, '')


class ProjectReorderTest(TestCase):
    """Project 排序重排 action。

    背景：sort_order 没有唯一约束，可以多个项目都是 1。
    排序规则是 ['sort_order', '-created_date']，
    所以重复时靠创建时间倒序兜底，顺序不受手动控制。
    重排后每个项目拿到唯一编号，之后改数字就能精确定位。
    """

    def setUp(self):
        self.user = make_user('sorter')
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save(update_fields=['is_staff', 'is_superuser'])
        self.client.force_login(self.user)

        # 三个项目：前两个 sort_order 都是 1（制造重复）
        self.a = Project.objects.create(name='项目A', sort_order=1)
        self.b = Project.objects.create(name='项目B', sort_order=1)
        self.c = Project.objects.create(name='项目C', sort_order=5)

    def _run_action(self):
        """通过 Admin 的 changelist POST 触发 action。"""
        return self.client.post(
            '/admin/blog/project/',
            {
                'action': 'renumber_sort_order',
                '_selected_action': [p.pk for p in Project.objects.all()],
            },
            follow=True,
        )

    def test_action_renumbers_to_consecutive(self):
        """重排后 sort_order 变成 1,2,3 连续且唯一"""
        self._run_action()
        values = sorted(Project.objects.values_list('sort_order', flat=True))
        self.assertEqual(values, [1, 2, 3])

    def test_action_keeps_display_order(self):
        """重排不改变当前显示顺序——这是这个 action 的核心承诺"""
        before = [p.name for p in Project.objects.all()]
        self._run_action()
        after = [p.name for p in Project.objects.all()]
        self.assertEqual(before, after)

    def test_action_is_idempotent(self):
        """再跑一次不再改动（已连续编号）"""
        self._run_action()
        snapshot = list(Project.objects.values_list('pk', 'sort_order'))
        self._run_action()
        self.assertEqual(list(Project.objects.values_list('pk', 'sort_order')), snapshot)

    def test_action_only_touches_selected(self):
        """只对勾选的项目编号；没勾选的保持原值"""
        self.client.post(
            '/admin/blog/project/',
            {
                'action': 'renumber_sort_order',
                '_selected_action': [self.a.pk],
            },
            follow=True,
        )
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertEqual(self.a.sort_order, 1)
        # b 没被勾选，仍是 1
        self.assertEqual(self.b.sort_order, 1)


class DashboardTest(TestCase):
    """后台仪表盘的统计逻辑与渲染。"""

    def setUp(self):
        self.user = make_user('dashboarder')
        # Admin 只允许 is_staff 用户访问。
        # make_user 用 create_user 建的是普通用户，
        # 不升级的话 /admin/ 会 302 到登录页（测试里表现为断言失败）
        self.user.is_staff = True
        self.user.save(update_fields=['is_staff'])
        self.client.force_login(self.user)

    def test_dashboard_renders(self):
        self.assertContains(self.client.get('/admin/'), '近 7 天访问趋势')

    def test_dashboard_shows_real_counts(self):
        """卡片数字来自真实数据，不是估算或占位"""
        Post.objects.create(
            author=self.user, title='A', text='x', status='published',
        )
        ctx = dashboard_context()
        self.assertEqual(ctx['overview']['posts_total'], 1)
        self.assertEqual(ctx['overview']['posts_published'], 1)

    def test_trend_has_seven_days_even_without_visits(self):
        """没访问也要补齐 7 天，否则折线图会缺日连成直线"""
        ctx = dashboard_context()
        self.assertEqual(len(ctx['trend']['days']), 7)
        self.assertEqual(ctx['trend']['total_visits'], 0)
        # 分母为 0 时峰值为 1，避免柱高算成 0/0
        self.assertEqual(ctx['trend']['max_count'], 1)

    def test_trend_counts_visits(self):
        VisitLog.objects.create(path='/', device='desktop')
        VisitLog.objects.create(path='/about/', device='mobile')
        ctx = dashboard_context()
        self.assertEqual(ctx['trend']['total_visits'], 2)
        self.assertEqual(ctx['top_pages'][0]['count'], 1)

    def test_device_distribution(self):
        VisitLog.objects.create(path='/', device='mobile')
        VisitLog.objects.create(path='/', device='mobile')
        VisitLog.objects.create(path='/', device='desktop')
        devices = {d['key']: d for d in dashboard_context()['trend']['devices']}
        self.assertEqual(devices['mobile']['count'], 2)
        self.assertEqual(devices['desktop']['count'], 1)

    def test_old_visits_excluded_from_trend(self):
        """超出 7 天窗口的记录不进趋势图"""
        old = VisitLog.objects.create(path='/', device='desktop')
        VisitLog.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=30)
        )
        self.assertEqual(dashboard_context()['trend']['total_visits'], 0)


class PruneVisitsCommandTest(TestCase):
    """清理命令：只删超期的，不碰近期数据。"""

    def setUp(self):
        self.fresh = VisitLog.objects.create(path='/new', device='desktop')
        self.stale = VisitLog.objects.create(path='/old', device='desktop')
        VisitLog.objects.filter(pk=self.stale.pk).update(
            created_at=timezone.now() - timedelta(days=200)
        )

    def test_deletes_only_expired(self):
        call_command('prune_visits', '--days', '90', verbosity=0)
        self.assertEqual(VisitLog.objects.count(), 1)
        self.assertTrue(VisitLog.objects.filter(pk=self.fresh.pk).exists())

    def test_dry_run_deletes_nothing(self):
        call_command('prune_visits', '--days', '90', '--dry-run', verbosity=0)
        self.assertEqual(VisitLog.objects.count(), 2)

    def test_keeps_everything_when_all_fresh(self):
        VisitLog.objects.filter(pk=self.stale.pk).update(created_at=timezone.now())
        call_command('prune_visits', '--days', '90', verbosity=0)
        self.assertEqual(VisitLog.objects.count(), 2)


