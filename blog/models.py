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
from django.utils import timezone
from django.utils.text import slugify
from django.urls import reverse


class Category(models.Model):
    # 双值结构：(存入数据库的值, 界面中显示的值)
    # 目前两者相同所以看不出区别；若写成 ('tutorial', '教程')，
    # 数据库存 tutorial，后台下拉框显示「教程」。
    TYPE_CHOICES = [
        ('教程', '教程'),
        ('日报', '日报'),
        ('周报', '周报'),
    ]

    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True, allow_unicode=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='日报')

    class Meta:
        # Django 默认把类名加 s 作为复数名，Category 会变成 "Categorys"（拼错），
        # 后台显示的模型名就是这个复数形式，所以必须手动指定
        verbose_name_plural = 'categories'
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
    name = models.CharField(max_length=30, unique=True)
    slug = models.SlugField(max_length=30, unique=True, allow_unicode=True)

    class Meta:
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
    )
    # settings.AUTH_USER_MODEL 是字符串形式的用户模型引用（默认 'auth.User'）。
    # 不直接 import User，是为了以后换成自定义用户模型时不用改代码。
    # CASCADE：作者被删除时，他名下的文章一并删除。
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    text = models.TextField()
    # 摘要：用空字符串而不是 NULL。字符串字段一律不写 null=True，
    # 否则「NULL」和「''」两种空值并存，查询时要同时判断两种情况。
    excerpt= models.TextField(blank=True,default='')
    # SET_NULL 与 null=True 必须配对：删除分类时把文章的 category_id 置 NULL，
    # 文章本身保留（若写 CASCADE，删分类会连同文章一起消失）。
    # related_name='posts' 让反向查询写成 category.posts.all()
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True,blank=True,related_name='posts')
    # 多对多：一篇可有多个标签，一个标签属于多篇文章。
    # 多对多不需要 on_delete —— 关联数据存在自动生成的中间表 blog_post_tags，
    # 删除标签只是断开关联行，两边的实体表都不受影响。
    tags = models.ManyToManyField(Tag, blank=True,related_name='posts')
    # 四个参数各管一件事：
    #   unique        —— 保证 URL 唯一，两篇文章不能共用同一个 slug
    #   allow_unicode —— 允许中文 slug（默认只保留 ASCII）
    #   blank         —— 表单校验允许留空，后台可以不填
    #   default=''    —— 初始值为空字符串，让 save() 里能判断「未填写」
    slug = models.SlugField(max_length=200, unique=True,allow_unicode=True,blank=True,default='')
    created_date = models.DateTimeField(default=timezone.now)
    # published_date 只记录发布时刻，用于显示和排序；
    # 前台是否可见由上面的 status 决定。
    published_date = models.DateTimeField(blank=True, null=True)
    views = models.PositiveIntegerField(default=0, editable=False)

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
        validators=[MinValueValidator(2000), MaxValueValidator(2100)]
    )
    # ISO 周，1-53，用 date.isocalendar()[1] 获取
    week = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(53)]
    )
    # 一句话摘要，首页卡片用。正文截断不好控制，所以单独存一列短文本
    summary = models.CharField(max_length=120, blank=True, default='')
    # 详情页正文：小标题自己写（本周目标/完成项/总结/下周计划），
    # 模型不强制四段都存在，否则每周会被逼着填满四个框
    content = models.TextField(blank=True, default='')
    published_date = models.DateTimeField(default=timezone.now)

    class Meta:
        # 同一组 (年, 周) 只能有一条，避免重复记录同一周
        unique_together = [('year', 'week')]
        ordering = ['-year', '-week']
        # 默认会变成 "weekly progresss"（拼错），必须手动指定
        verbose_name_plural = 'weekly progresses'

    def __str__(self):
        return f'{self.year} 年第 {self.week} 周'


class Project(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, allow_unicode=True, blank=True, default='')
    summary = models.CharField(max_length=200, blank=True, default='')
    description = models.TextField(blank=True, default='')
    # 技术栈用逗号分隔的纯文本，不单独建表：
    # 它只用于展示，没有筛选/统计需求，JSON 字段或关系表都属过度设计
    tech_stack = models.CharField(max_length=200, blank=True, default='')
    github_url = models.URLField(blank=True, default='')
    demo_url = models.URLField(blank=True, default='')
    # 手控排序：数字小的在前面。没有这个字段就只好按创建时间排，不受控
    sort_order = models.IntegerField(default=0)
    created_date = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['sort_order', '-created_date']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # 与 Post 相同的重名处理，但这里 name 已 unique，
        # 所以重名会在校验阶段被拦，不用再加 -2 后缀逻辑
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)


class DailySong(models.Model):
    # 一天一首，所以日期唯一。用 DateField 而非 DateTimeField：
    # 「哪一天的歌」不需要精确到秒
    date = models.DateField(unique=True)
    title = models.CharField(max_length=200)
    artist = models.CharField(max_length=100)
    cover_url = models.URLField(blank=True, default='')
    comment = models.TextField(blank=True, default='')
    # 平台官方播放器外链（网易云/QQ音乐等），不存音频文件
    song_url = models.URLField(blank=True, default='')
    # 官方 embed iframe 的 src，直接塞进模板的 iframe 里
    embed_url = models.URLField(blank=True, default='')

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f'{self.date} {self.title} - {self.artist}'


class Profile(models.Model):
    # 单例模型：全局只应该有一条记录。用 OneToOneField 指向用户 +
    # save() 里强制 pk=1 双保险，避免后台误建第二条
    nickname = models.CharField(max_length=50)
    avatar_url = models.URLField(blank=True, default='')
    tagline = models.CharField(max_length=120, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    github_url = models.URLField(blank=True, default='')
    social_links = models.TextField(
        blank=True, default='',
        help_text='一行一个，格式：平台名 URL',
    )
    updated_date = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'profiles'

    def __str__(self):
        return self.nickname

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
