"""
models.py 描述数据长什么样。

每个 class 代表数据库里的一张表：
- 类属性 = 表的列（字段）
- 字段类型与参数 = 列的类型和约束
- ForeignKey / ManyToManyField = 表与表之间的关系

Django 的其他部分都从这里派生：makemigrations 读它生成迁移，
Admin 读它生成表单，ORM 读它生成 SQL。改模型等于改数据库结构。
"""
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class Category(models.Model):
    # 双值结构：(存入数据库的值, 界面中显示的值)
    # 目前两者相同所以看不出区别；若写成 ('tutorial', '教程')，
    # 数据库存 tutorial，后台下拉框显示「教程」。
    TYPE_CHOICES = [
        ('教程', '教程'),
        ('日报', '日报'),
        ('周报', '周报'),
    ]

    name = models.CharField(max_length=50, unique=True, verbose_name='名称')
    slug = models.SlugField(
        max_length=50, unique=True, allow_unicode=True, verbose_name='URL 标识',
        help_text='不填会自动生成，一般不用管',
    )
    type = models.CharField(
        max_length=20, choices=TYPE_CHOICES, default='日报', verbose_name='分类类型',
    )

    class Meta:
        # 中文单复数相同，不用写 s。
        # 不指定的话后台会显示类名「Category」而不是「分类」
        verbose_name = '分类'
        verbose_name_plural = '分类'
        # 查询和后台默认按名称排序，不用每次写 order_by
        ordering = ['name']

    def __str__(self):
        # 决定「用文字表示这个对象」时显示什么：Admin 列表、下拉框选项、print()
        return self.name

    def save(self, *args, **kwargs):
        # slug 为空时才自动生成；手动填过的值优先，不被覆盖
        if not self.slug:
            # allow_unicode=True 不能省：默认只保留 ASCII，
            # 中文标题会被清成空字符串，随后撞 unique 约束
            self.slug = slugify(self.name, allow_unicode=True)
        # 必须调用父类：重写 save() 会完全覆盖 Django 的实现，
        # 漏掉这行代码看起来能跑，但数据根本不会写进数据库
        super().save(*args, **kwargs)


class Tag(models.Model):
    name = models.CharField(max_length=30, unique=True, verbose_name='名称')
    slug = models.SlugField(
        max_length=30, unique=True, allow_unicode=True, verbose_name='URL 标识',
        help_text='不填会自动生成，一般不用管',
    )

    class Meta:
        verbose_name = '标签'
        verbose_name_plural = '标签'
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # 与 Category 相同的逻辑：slug 为空时从 name 生成中文 slug。
        # 这里 slug 没写 default=''，但 CharField/SlugField 未赋值时就是空字符串，
        # 所以 if not self.slug 依然成立（显式写 default 可读性更好）。
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)


class Post(models.Model):

    STATUS_CHOICES = [
        ('draft', '草稿'),
        ('published', '已发布'),
        ('archived', '归档'),
    ]
    # 决定前台是否可见的唯一字段：只有 published 会被查询出来
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='draft',
        verbose_name='状态',
        help_text='只有「已发布」会出现在前台',
    )
    # settings.AUTH_USER_MODEL 是字符串形式的用户模型引用（默认 'auth.User'）。
    # 不直接 import User，是为了以后换成自定义用户模型时不用改代码。
    # CASCADE：作者被删除时，他名下的文章一并删除。
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name='作者',
    )
    title = models.CharField(max_length=200, verbose_name='标题')
    text = models.TextField(verbose_name='正文', help_text='可以用 Markdown')
    # 摘要：用空字符串而不是 NULL。字符串字段一律不写 null=True，
    # 否则「NULL」和「''」两种空值并存，查询时要同时判断两种情况。
    excerpt = models.TextField(
        blank=True, default='', verbose_name='摘要',
        help_text='不填会自动截取正文开头，一般不用管',
    )
    # SET_NULL 与 null=True 必须配对：删除分类时把文章的 category_id 置 NULL，
    # 文章本身保留（若写 CASCADE，删分类会连同文章一起消失）。
    # related_name='posts' 让反向查询写成 category.posts.all()
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='posts', verbose_name='分类',
    )
    # 多对多：一篇可有多个标签，一个标签属于多篇文章。
    # 多对多不需要 on_delete —— 关联数据存在自动生成的中间表 blog_post_tags，
    # 删除标签只是断开关联行，两边的实体表都不受影响。
    tags = models.ManyToManyField(Tag, blank=True, related_name='posts', verbose_name='标签')
    # 四个参数各管一件事：
    #   unique        —— 保证 URL 唯一，两篇文章不能共用同一个 slug
    #   allow_unicode —— 允许中文 slug（默认只保留 ASCII）
    #   blank         —— 表单校验允许留空，后台可以不填
    #   default=''    —— 初始值为空字符串，让 save() 里能判断「未填写」
    slug = models.SlugField(
        max_length=200, unique=True, allow_unicode=True, blank=True, default='',
        verbose_name='URL 标识',
        help_text='不填会自动生成，一般不用管',
    )
    created_date = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    # published_date 只记录发布时刻，用于显示和排序；
    # 前台是否可见由上面的 status 决定。
    published_date = models.DateTimeField(
        blank=True, null=True, verbose_name='发布时间',
        help_text='不填，改为已发布会自动填上当前时间',
    )
    views = models.PositiveIntegerField(default=0, editable=False, verbose_name='阅读数')

    class Meta:
        verbose_name = '文章'
        verbose_name_plural = '文章'

    def publish(self):
        # 把草稿转成已发布：改状态、补发布时间（有就不覆盖），再保存
        self.status = 'published'
        if not self.published_date:
            self.published_date = timezone.now()
        self.save()

    def save(self, *args, **kwargs):
        # 强制 status 与 published_date 一致：状态是 published 却没发布时间时
        # 自动补当前时间。否则前台会渲染出 "None"（曾出现过这种数据不一致）
        if self.status == 'published' and not self.published_date:
            self.published_date = timezone.now()
        if not self.slug:
            base = slugify(self.title, allow_unicode=True)
            slug = base
            n = 2
            # 标题重复时依次尝试 base-2、base-3……
            # 不加这段会撞 unique 约束，抛 IntegrityError（500 错误页）
            #
            # exclude(pk=self.pk) 排除自己：编辑已有文章时不算「和自己重名」。
            # 否则每保存一次 slug 就会变一次，旧链接全部 404。
            while Post.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{n}'
                n += 1
            self.slug = slug
        # 必须调用父类，否则数据不会写进数据库（和 Category.save 同理）
        super().save(*args, **kwargs)
    def get_absolute_url(self):
        # name 必须和 blog/urls.py 里完全一致（下划线，不是连字符），
        # 否则抛 NoReverseMatch，sitemap 与 Admin 的「查看」按钮都会挂
        return reverse('post_detail', kwargs={'slug': self.slug})

    def __str__(self):
        return self.title


class WeeklyProgress(models.Model):
    # ISO 年。不是日历年：2026-12-31 可能属于 2027 年第 1 周，
    # 所以录入时用 date.isocalendar()[0]，不要用 date.year
    year = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(2000), MaxValueValidator(2100)],
        verbose_name='年份',
        help_text='按 ISO 年算，年初年末可能和日历年不一致',
    )
    # ISO 周，1-53，用 date.isocalendar()[1] 获取
    week = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(53)],
        verbose_name='第几周',
        help_text='1-53',
    )
    # 一句话摘要，首页卡片用。正文截断不好控制，所以单独存一列短文本
    summary = models.CharField(
        max_length=120, blank=True, default='', verbose_name='摘要',
    )
    # 详情页正文：小标题自己写（本周目标/完成项/总结/下周计划），
    # 模型不强制四段都存在，否则每周会被逼着填满四个框
    content = models.TextField(
        blank=True, default='', verbose_name='正文',
        help_text='可以用 Markdown，小标题自拟',
    )
    published_date = models.DateTimeField(default=timezone.now, verbose_name='发布时间')

    class Meta:
        # 同一组 (年, 周) 只能有一条，避免重复记录同一周
        unique_together = [('year', 'week')]
        ordering = ['-year', '-week']
        verbose_name = '周进度'
        verbose_name_plural = '周进度'

    def __str__(self):
        return f'{self.year} 年第 {self.week} 周'


class Project(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='项目名称')
    slug = models.SlugField(
        max_length=100, unique=True, allow_unicode=True, blank=True, default='',
        verbose_name='URL 标识',
        help_text='不填会自动生成，一般不用管',
    )
    summary = models.CharField(
        max_length=200, blank=True, default='', verbose_name='简介',
        help_text='显示在列表卡片上，短一点更好',
    )
    description = models.TextField(
        blank=True, default='', verbose_name='详细说明', help_text='可以用 Markdown',
    )
    # 技术栈用逗号分隔的纯文本，不单独建表：
    # 它只用于展示，没有筛选/统计需求，JSON 字段或关系表都属过度设计
    tech_stack = models.CharField(
        max_length=200, blank=True, default='', verbose_name='技术栈',
        help_text='用逗号隔开',
    )

    # 项目封面图。可选：没传时前台用技术栈文字占位，不阻断展示。
    # 用 ImageField 而非 FileField，让 Pillow 真的验证是图片。
    # blank=True 与 default='' 配对：没传时存空串而不是 NULL，
    # 模板里 {% if project.cover %} 能直接判断
    cover = models.ImageField(
        upload_to='projects/covers/',
        blank=True,
        default='',
        verbose_name='封面图',
        # 不写尺寸提示：分组说明里已经写了，重复会显示两遍
    )

    github_url = models.URLField(
        blank=True, default='', verbose_name='GitHub 地址',
    )
    demo_url = models.URLField(
        blank=True, default='', verbose_name='在线演示地址',
    )
    # 手控排序：数字小的在前面。没有这个字段就只好按创建时间排，不受控
    sort_order = models.IntegerField(
        default=0, verbose_name='排序', help_text='数字越小越靠前',
    )
    created_date = models.DateTimeField(default=timezone.now, verbose_name='创建时间')

    class Meta:
        ordering = ['sort_order', '-created_date']
        verbose_name = '项目'
        verbose_name_plural = '项目'

    def __str__(self):
        return self.name

    @property
    def cover_src(self):
        """模板里统一用这个取封面地址。

        没传图时返回空串，模板靠 {% if project.cover_src %} 判断
        是否渲染 <img>，否则会显示一个破图框。

        用属性而不是模板里直接写 {{ project.cover.url }}：
        空文件访问 .url 会抛 ValueError，导致页面 500。
        """
        if self.cover:
            return self.cover.url
        return ''

    def save(self, *args, **kwargs):
        # 与 Post 相同的重名处理，但这里 name 已 unique，
        # 所以重名会在校验阶段被拦，不用再加 -2 后缀逻辑
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)


class Profile(models.Model):
    # 单例模型：全局只应该有一条记录。用 OneToOneField 指向用户 +
    # save() 里强制 pk=1 双保险，避免后台误建第二条
    nickname = models.CharField(max_length=50, verbose_name='昵称')

    # 头像两种来源，优先用上传的文件：
    # avatar 是本地图（推荐），avatar_url 留着兼容外链头像。
    # 用 ImageField 而不是 FileField：前者会校验确实是图片，
    # 避免有人传个 .jpg 后缀的脚本上去。
    # blank=True 与 default='' 配对：没传时存空字符串而不是 NULL，
    # 模板里 {% if profile.avatar %} 能直接判断
    avatar = models.ImageField(
        upload_to='avatars/',
        blank=True,
        default='',
        verbose_name='头像（上传）',
        # 不写优先级说明：分组说明里已经写了，重复会显示两遍
    )
    avatar_url = models.URLField(
        blank=True,
        default='',
        verbose_name='头像（外链）',
        help_text='上传了头像就不用填这个',
    )

    tagline = models.CharField(
        max_length=120, blank=True, default='', verbose_name='一句话介绍',
    )
    # 「关于我」页的正文。用 TextField + Markdown 而不是 CharField：
    # 简介通常要分段、加列表、放链接，纯文本表达不了。
    # 存源文本、渲染时再转换，这样后台能编辑，不用改模板重新部署
    bio = models.TextField(
        blank=True,
        default='',
        verbose_name='个人简介',
        help_text='支持 Markdown，显示在「关于我」页面',
    )
    email = models.EmailField(blank=True, default='', verbose_name='邮箱')
    github_url = models.URLField(
        blank=True, default='', verbose_name='GitHub 地址',
    )
    social_links = models.TextField(
        blank=True, default='', verbose_name='其他链接',
        help_text='一行一个',
    )
    updated_date = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '个人资料'
        verbose_name_plural = '个人资料'

    def __str__(self):
        return self.nickname

    @property
    def avatar_src(self):
        """模板里统一用这个取头像地址。

        上传的图优先，其次外链，都没有则返回空字符串，
        模板靠 {% if profile.avatar_src %} 判断是否渲染 <img>，
        否则会显示一个破图框。

        用属性而不是模板里写 if/else 两层：
        头像在两个模板（首页侧栏、关于页）都要用，
        逻辑写一处才不会两处走偏。
        """
        if self.avatar:
            return self.avatar.url
        return self.avatar_url

    def save(self, *args, **kwargs):
        # 强制主键为 1：无论新建多少次，都只会覆盖同一条记录
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        # 模板里用 Profile.load() 拿资料；不存在时返回未保存的空实例，
        # 避免首页因为还没填资料就报错
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class GuestbookMessage(models.Model):
    # 留言板。本项目第一个「访客写数据」的模型，所以安全相关字段较多。
    #
    # post 为空 = 全局留言（留给以后的 /guestbook/ 页）；有值 = 属于某篇文章。
    # 用 null=True 而不是 default=0：没有「第 0 篇文章」，空就是空。
    # 代价是查询时必须显式区分 post=post 和 post__isnull=True，
    # 漏写就会把两种留言混在一起。
    post = models.ForeignKey(
        Post,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='guestbook_messages',
        verbose_name='所属文章',
    )
    nickname = models.CharField(max_length=50, verbose_name='昵称')
    # 限 200 字：留言是「给几个意见」，不是写长文。
    # 限长同时对刷屏和超长输入做了硬性约束，不靠前端 maxlength
    content = models.TextField(max_length=200, verbose_name='留言内容')

    # 默认不通过：访客提交后前台查不到，必须在 Admin 里点通过才显示。
    # 个人博客没有审核就等于对公众开放，垃圾留言会直接上首页
    is_approved = models.BooleanField(default=False, verbose_name='已审核')

    # 只用于限流，不展示。存在库里而不是纯缓存里，
    # 是为了出问题时能查「哪个 IP 发了什么」
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name='IP 地址')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='提交时间')

    class Meta:
        # 评论区惯例：从旧到新读下来，新留言出现在最下面
        ordering = ['created_at']
        verbose_name = '留言'
        verbose_name_plural = '留言'

    def __str__(self):
        target = self.post.title if self.post else '全局'
        return f'{self.nickname} @ {target}'


class VisitLog(models.Model):
    """一条访问记录，每次前台请求写一行。

    为什么不用外部统计（Umami / GA）：
    那些数据存在别人的服务器上，而本项目想在自己的 Admin 里看。

    为什么不存 IP：用户明确要求不记录。代价是没有 UV
    （无法区分「一人访五次」和「五人各访一次」），
    但 PV、设备占比、热门页面、来路这些都不需要 IP 也能统计。

    为什么不用单独的汇总表：
    先把原始记录存下来，图表靠聚合查询算。
    数据量小（个人博客，存 90 天），没必要提前汇总；
    等真的慢了再加缓存或汇总表。
    """

    # 不含 query string：统计热门页面时 /posts/x/?from=xx 应归到同一页。
    # 长度 255 足够容纳本项目最长路径（slug 允许中文）
    path = models.CharField(max_length=255, verbose_name='路径')

    # 只存「手机 / 电脑 / 平板 / 未知」四个值，不存完整 UA。
    # 完整 UA 动辄 150 字节且对统计无用；分类信息在中间件里就解析完。
    # 用 choices 而不是自由文本，避免以后手写值不一致
    DEVICE_CHOICES = [
        ('mobile', '手机'),
        ('tablet', '平板'),
        ('desktop', '电脑'),
        ('unknown', '未知'),
    ]
    device = models.CharField(
        max_length=10,
        choices=DEVICE_CHOICES,
        default='unknown',
        verbose_name='设备类型',
    )

    # 来源域名。只存 host 不存完整 URL：
    # 完整 URL 可能带搜索关键词等隐私信息，且统计只需要知道「从哪来」。
    # 空串 = 直接访问（无 Referer 或同站跳转）
    referer_host = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name='来源域名',
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name='访问时间',
    )

    class Meta:
        verbose_name = '访问记录'
        verbose_name_plural = '访问记录'
        # 默认按时间倒序：Admin 里看最新访问
        ordering = ['-created_at']
        # 图表按天聚合时全靠这个索引；不加的话
        # 存了几个月后每天查询都要全表扫描
        indexes = [
            models.Index(fields=['created_at', 'path'], name='visit_time_path_idx'),
            models.Index(fields=['created_at', 'device'], name='visit_time_device_idx'),
        ]

    def __str__(self):
        return f'{self.path} @ {self.created_at:%Y-%m-%d %H:%M}'


