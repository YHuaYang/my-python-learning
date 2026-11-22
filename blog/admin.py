"""
admin.py 配置 Django 后台的显示方式。

@admin.register(Model) 装饰器等价于 admin.site.register(Model, XxxAdmin)。
ModelAdmin 里的每一项都是「展示层」配置，不影响数据存储和校验规则。
"""
from django.contrib import admin, messages
from django.utils.html import format_html

from .models import Category, GuestbookMessage, Post, Profile, Project, Tag, WeeklyProgress


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
       # 列表页显示的列。写字段名时 Django 会显示该值的 __str__，
       # 所以 'author' 显示的是用户名（User.__str__ 返回 username）
       list_display = ('title', 'slug', 'status', 'author', 'category', 'published_date', 'views')
       # 右侧筛选栏。多对多和多对一字段会自动展开成可选值
       list_filter = ('status', 'category', 'published_date', 'author')
       # 顶部搜索框搜哪些字段。只能搜文本类字段，不能搜外键本身
       search_fields = ('title', 'text')
       # 标题输入时用 JS 实时填充 slug。注意 urlify.js 只处理 ASCII，
       # 中文标题会被清空，最终靠 Post.save() 里的 Python 逻辑补上
       prepopulated_fields = {'slug': ('title',)}
       # 列表页顶部的时间钻取条（2026 › 十月 › 21）
       date_hierarchy = 'published_date'
       # 默认排序，新文章在上；published_date 为 NULL 的草稿排最后
       ordering = ('-published_date',)
       list_per_page = 20

       # fieldsets 完全覆盖编辑页的字段显示：没写进来的字段在后台看不见。
       # 漏掉必填字段会导致保存失败；漏掉可选字段只是看不见，数据照常保存。
       fieldsets = (
           ('状态', {
               'fields': ('status',),
               'description': '下架或隐藏文章请改这里：选「草稿」或「已下架」。'
                              '不要用清空发布时间的方式，那样不会从前台消失。',
           }),
           ('内容', {
               'fields': ('title', 'slug', 'category', 'tags', 'author', 'excerpt', 'text')
           }),
           ('发布', {
               'fields': ('published_date', 'created_date'),
               'classes': ('collapse',),   # 这一组默认折叠，减少视觉干扰
           }),
       )


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
       list_display = ('name','slug','type')
       list_filter = ('type',)
       search_fields = ('name',)
       prepopulated_fields = {'slug':('name',)}


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name','slug')
    search_fields = ('name',)
    prepopulated_fields = {'slug':('name',)}


@admin.register(WeeklyProgress)
class WeeklyProgressAdmin(admin.ModelAdmin):
    # __str__ 会渲染成「2026 年第 43 周」
    list_display = ('__str__', 'summary_preview', 'published_date')
    list_filter = ('year',)
    search_fields = ('summary', 'content')
    ordering = ('-year', '-week')
    date_hierarchy = 'published_date'
    fieldsets = (
        ('周期', {
            'fields': ('year', 'week'),
            # 组顶部的说明文字，提醒自己 ISO 周的两个坑
            'description': 'ISO 标准：用 date(2026,10,25).isocalendar() 确认，'
                           '注意 ISO 年不等于日历年',
        }),
        ('内容', {
            'fields': ('summary', 'content'),
        }),
        ('发布', {
            'fields': ('published_date',),
        }),
    )

    @admin.display(description='摘要')
    def summary_preview(self, obj):
        return obj.summary[:30] or '（无摘要）'


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'cover_preview', 'slug', 'summary_preview', 'sort_order', 'created_date')
    search_fields = ('name', 'summary', 'description')
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('sort_order', '-created_date')
    # 预览图不能在保存后手动改，否则会误导
    readonly_fields = ('cover_preview_large',)
    fieldsets = (
        ('基本信息', {
            'fields': ('name', 'slug', 'summary', 'tech_stack', 'sort_order'),
        }),
        ('封面图', {
            'fields': ('cover', 'cover_preview_large'),
            'description': '建议 16:9 横向图，宽度 800px 以上。'
                           '留空时前台只显示文字，不会出破图。',
        }),
        ('详细内容', {
            'fields': ('description',),
        }),
        ('链接', {
            'fields': ('github_url', 'demo_url'),
        }),
    )

    @admin.display(description='封面')
    def cover_preview(self, obj):
        """列表页的小缩略图，一眼看出哪些项目还没传封面。"""
        src = obj.cover_src if obj else ''
        if not src:
            return '（未上传）'
        return format_html(
            '<img src="{}" style="height:40px;width:71px;'
            'object-fit:cover;border-radius:4px;">',
            src,
        )

    @admin.display(description='当前封面')
    def cover_preview_large(self, obj):
        """编辑页的大预览，上传后保存就能确认结果。"""
        src = obj.cover_src if obj else ''
        if not src:
            return '（还没上传封面）'
        return format_html(
            '<img src="{}" style="max-width:320px;'
            'border-radius:6px;border:1px solid #ddd;">',
            src,
        )

    @admin.display(description='简介')
    def summary_preview(self, obj):
        return obj.summary[:30] or '（无简介）'


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('nickname', 'avatar_preview', 'tagline', 'email', 'updated_date')
    # 单例模型，只有一条记录，不需要搜索和筛选
    fieldsets = (
        ('基本信息', {
            'fields': ('nickname', 'tagline'),
        }),
        ('头像', {
            'fields': ('avatar', 'avatar_preview_large', 'avatar_url'),
            'description': '两个都填时，上传的图片优先生效。'
                           '上传后保存即可看到预览，不需要先去前台确认。',
        }),
        ('联系方式', {
            'fields': ('email', 'github_url', 'social_links'),
        }),
    )
    # 预览图不能在保存后手动改，否则会误导
    readonly_fields = ('avatar_preview_large',)

    @admin.display(description='头像')
    def avatar_preview(self, obj):
        """列表页的小缩略图。"""
        src = obj.avatar_src if obj else ''
        if not src:
            return '（未设置）'
        return format_html(
            '<img src="{}" style="height:32px;width:32px;border-radius:50%;object-fit:cover;">',
            src,
        )

    @admin.display(description='当前头像')
    def avatar_preview_large(self, obj):
        """编辑页的大预览，方便确认上传结果。"""
        src = obj.avatar_src if obj else ''
        if not src:
            return '（还没上传头像）'
        return format_html(
            '<img src="{}" style="height:96px;width:96px;border-radius:50%;'
            'object-fit:cover;border:1px solid #ddd;">',
            src,
        )

    def has_add_permission(self, request):
        # 单例模型：已经存在一条时不再允许「新增」，
        # 否则后台会出现两个入口指向同一条记录，容易误解
        if Profile.objects.exists():
            return False
        return super().has_add_permission(request)


@admin.register(GuestbookMessage)
class GuestbookMessageAdmin(admin.ModelAdmin):
    # 昵称和内容放前面：审核时的判断依据就是这两列
    list_display = ('nickname', 'content_preview', 'target', 'is_approved', 'created_at')
    # 默认筛「待审核」：打开页面就是想处理待审的，
    # 不默认筛的话已通过的会混在里面，得自己点
    list_filter = ('is_approved', 'created_at')
    search_fields = ('nickname', 'content')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    list_per_page = 30
    # 列表页直接勾选审核状态，比进详情页快得多
    list_editable = ('is_approved',)
    # IP 不展示在列表页（列太多），但编辑页要能查
    readonly_fields = ('ip_address', 'created_at')
    fieldsets = (
        ('留言内容', {
            'fields': ('nickname', 'content', 'post'),
        }),
        ('审核', {
            'fields': ('is_approved',),
        }),
        ('系统信息', {
            'fields': ('ip_address', 'created_at'),
            'classes': ('collapse',),
        }),
    )
    actions = ('approve_selected', 'reject_selected')

    @admin.display(description='内容')
    def content_preview(self, obj):
        # 列表页不展示全文：200 字会把表格撑变形
        return obj.content[:40] + ('…' if len(obj.content) > 40 else '')

    @admin.display(description='所属文章')
    def target(self, obj):
        # post 可空，直接写 obj.post 会显示 None
        return obj.post.title if obj.post else '（全局）'

    @admin.action(description='通过选中留言')
    def approve_selected(self, request, queryset):
        # update() 不触发 save()，一次 SQL 搞定，比逐条 save() 快
        count = queryset.update(is_approved=True)
        self.message_user(request, f'已通过 {count} 条留言')

    @admin.action(description='驳回选中留言')
    def reject_selected(self, request, queryset):
        count = queryset.update(is_approved=False)
        self.message_user(request, f'已驳回 {count} 条留言', messages.WARNING)
