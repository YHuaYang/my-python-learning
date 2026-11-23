"""
admin.py 配置 Django 后台的显示方式。

@admin.register(Model) 装饰器等价于 admin.site.register(Model, XxxAdmin)。
ModelAdmin 里的每一项都是「展示层」配置，不影响数据存储和校验规则。
"""
import logging

from django.contrib import admin, messages
from django.templatetags.static import static
from django.utils.html import format_html
from unfold.admin import ModelAdmin as UnfoldModelAdmin

from .dashboard import dashboard_context
from .models import (
    Category,
    GuestbookMessage,
    Post,
    Profile,
    Project,
    Tag,
    VisitLog,
    WeeklyProgress,
)

logger = logging.getLogger(__name__)

# 为什么要有这一行别名：
#
# unfold 提供了自己的 ModelAdmin 基类，它在渲染表单时
# 会给输入框、下拉框、文件选择器加上 Tailwind 样式类。
# 如果继承 django.contrib.admin.ModelAdmin，虽然页面布局、
# 侧边栏、按钮会变成 unfold 外观（那些在模板与 CSS 里），
# 但表单控件拿不到样式类，表现为「输入框像纯文本、
# 看不出哪里能填、哪里是按钮」。
#
# 下面所有 Admin 类都必须继承 UnfoldModelAdmin 而不是 admin.ModelAdmin。


class MarkdownEditorMixin(UnfoldModelAdmin):
    """给指定字段挂上 Toast UI 的 Markdown 编辑器。

    为什么要抽成 mixin：
    文章正文、项目详情、周进度正文三处都要用，
    复制三份 Media 与 get_form 很容易改漏一处。

    子类只需声明 markdown_fields，其余自动完成。

    为什么直接继承 UnfoldModelAdmin 而不是纯 object：
    纯 mixin 的 super() 指向 object，没有 get_form，
    静态检查会报「Cannot access attribute get_form」。
    直接继承基类后 super() 有完整类型，子类只需再写
    (MarkdownEditorMixin) 就行，不用多重继承。
    """

    # 子类覆盖：要加编辑器的字段名
    markdown_fields: tuple[str, ...] = ()

    class Media:
        # admin-editor.js 539KB（gzip 167KB）。
        # 通过 ModelAdmin.Media 注入，只有声明了这个 mixin 的
        # 编辑页会加载，不是所有后台页面。
        #
        # Django 会自动去重：同一页多个 Admin 声明相同资源
        # 也只输出一次。
        css = {
            'all': (static('js/asset-admin-editor.css'),),
        }
        js = (static('js/admin-editor.js'),)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        for name in self.markdown_fields:
            if name not in form.base_fields:
                continue
            widget = form.base_fields[name].widget
            # 只打标记，不换 widget 类：
            # 保留 Admin 默认的 AdminTextareaWidget，样式才一致。
            # admin-editor.ts 只增强带这个属性的 textarea，
            # 不会误伤搜索框与帮助文本。
            widget.attrs['data-markdown-editor'] = ''
            widget.attrs['rows'] = 10
        return form


@admin.register(Post)
class PostAdmin(MarkdownEditorMixin):
       # 只给正文加编辑器，不给摘要：
       # 摘要是短文本（200 字左右），用 500px 高的编辑器反而碍事。
       markdown_fields = ('text',)

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
               'description': '想从前台藏起一篇文章，把状态改成草稿或归档。'
                              '清空发布时间没用，它不会从前台消失。',
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
class CategoryAdmin(UnfoldModelAdmin):
       list_display = ('name','slug','type')
       list_filter = ('type',)
       search_fields = ('name',)
       prepopulated_fields = {'slug':('name',)}


@admin.register(Tag)
class TagAdmin(UnfoldModelAdmin):
    list_display = ('name','slug')
    search_fields = ('name',)
    prepopulated_fields = {'slug':('name',)}


@admin.register(WeeklyProgress)
class WeeklyProgressAdmin(MarkdownEditorMixin):
    # 周进度正文也用 Markdown（支持小标题、列表）
    markdown_fields = ('content',)

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
            'description': '按 ISO 周算，所以年初年末可能和日历年不一致。'
                           '不确定时用 Python 查：date(2026,10,25).isocalendar()',
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
class ProjectAdmin(MarkdownEditorMixin):
    # 项目详细说明用 Markdown（表格、代码块都支持）
    markdown_fields = ('description',)

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
            'description': '横图更好看，建议 16:9。传了会在列表和详情页显示；不传就只有文字。',
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

    actions = ('renumber_sort_order',)

    @admin.action(description='按当前顺序重新编号（消除重复的排序值）')
    def renumber_sort_order(self, request, queryset):
        """把排序值重编号成 1, 2, 3…，**不改变当前显示顺序**。

        为什么需要：sort_order 没有唯一约束，可以多个项目都是 1。
        排序规则是 ['sort_order', '-created_date']，
        所以重复时靠创建时间倒序兜底（新建的在前）。
        结果是「填了数字但顺序不受控」，想精确调位置就无从入手。

        重排后：顺序完全不变，但每个项目拿到唯一编号，
        之后改任何一个数字就能确定地把它移到目标位置。

        两个细节：
        1. 用当前视图的排序结果作为编号依据，而不是按 pk。
           这样「重排后顺序不变」才成立。
        2. 用 bulk_update 一次写完，不逐条 save()：
           N 个项目就是 N 次 UPDATE 对比 1 次，且不触发信号。
        """
        ordering = queryset.model._meta.ordering
        # 必须对传入的 queryset 重新排序：
        # 用户在列表页勾选的可能只是部分项，且 queryset 的
        # 默认排序不一定是 Meta.ordering（比如刚搜索过）
        items = list(queryset.order_by(*ordering))

        if not items:
            self.message_user(request, '没有选中任何项目', messages.WARNING)
            return

        changed = 0
        for index, obj in enumerate(items, start=1):
            if obj.sort_order != index:
                obj.sort_order = index
                changed += 1

        if changed == 0:
            self.message_user(request, '排序值已经是 1 开始的连续编号，无需调整')
            return

        queryset.model.objects.bulk_update(items, ['sort_order'])
        self.message_user(
            request,
            f'已重编号 {len(items)} 个项目（其中 {changed} 个有变化），'
            '显示顺序保持不变',
        )


@admin.register(Profile)
class ProfileAdmin(UnfoldModelAdmin):
    list_display = ('nickname', 'avatar_preview', 'tagline', 'email', 'updated_date')
    # 单例模型，只有一条记录，不需要搜索和筛选
    fieldsets = (
        ('基本信息', {
            'fields': ('nickname', 'tagline'),
        }),
        ('头像', {
            'fields': ('avatar', 'avatar_preview_large', 'avatar_url'),
            'description': '两个都填时用上传的图。上传后保存就能看到预览。',
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
class GuestbookMessageAdmin(UnfoldModelAdmin):
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


@admin.register(VisitLog)
class VisitLogAdmin(UnfoldModelAdmin):
    """只读的访问记录。

    不提供新增/修改：数据由中间件自动产生，
    手动改记录只会让统计失真。
    但允许删除：清理扒虫扫出来的垃圾记录时有用。
    """

    list_display = ('created_at', 'path', 'device', 'referer_host')
    list_filter = ('device', 'created_at')
    search_fields = ('path', 'referer_host')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    list_per_page = 50

    # 全字段只读：数据由中间件写入，后台不给改
    readonly_fields = ('path', 'device', 'referer_host', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # 不允许修改，但 allow 查看视图
        return False

    def has_view_permission(self, request, obj=None):
        return True

    # 保留删除权限：清理异常数据时用
    def has_delete_permission(self, request, obj=None):
        return True


# 后台首页仪表盘。
#
# 为什么去改编 admin.site.index 而不是写一个独立视图：
# 这样不用改 URL（仍是 /admin/），也不用改动项目的路由配置。
# 保留原方法作为兜底：一旦取数据失败，后台仍能正常打开。
_original_index = admin.site.index


def custom_index(request, extra_context=None):
    ctx = dict(extra_context or {})
    # ruff 的 BLE001 建议不要捕裸 Exception，这里是故意的：
    # 仪表盘只是附加信息，任何统计查询出错（索引缺失、字段改名、
    # 数据库锁）都不该让整个后台变成 500——那样连修数据都进不去。
    # 捕大例外并记日志，是这里唯一正确的选择。
    try:
        ctx['dashboard'] = dashboard_context()
    except Exception:
        logger.exception('仪表盘统计失败，退回默认首页')
        ctx['dashboard'] = None
    return _original_index(request, ctx)


admin.site.index = custom_index


# ===== 给 django.contrib 自带的 Admin 换 unfold 基类 =====
#
# User / Group / Site 的 Admin 写在 django.contrib 包内部，
# 继承的是原生 admin.ModelAdmin，所以它们的编辑页输入框
# 拿不到 unfold 的样式类（表现为无边框、与纯文本难区分）。
#
# 做法：先 unregister，再用「原 Admin + Unfold ModelAdmin」多继承重新注册。
# 多继承顺序很重要：原 Admin 在前，它的 fieldsets / 表单布局优先；
# UnfoldModelAdmin 在后，只贡献样式与模板钩子。
#
# User 不一起改：UserAdmin 带密码修改、权限穿梭框等大量自定义布局，
# 多继承容易产生 MRO 冲突。而本站只有一个用户（站主自己），
# 改用户频率极低，不值得为它承担后台坏掉的风险。
from django.contrib.auth.admin import GroupAdmin  # noqa: E402
from django.contrib.auth.models import Group  # noqa: E402
from django.contrib.sites.admin import SiteAdmin  # noqa: E402
from django.contrib.sites.models import Site  # noqa: E402

admin.site.unregister(Group)
admin.site.unregister(Site)


@admin.register(Group)
class UnfoldGroupAdmin(GroupAdmin, UnfoldModelAdmin):
    """用户组。继承原 GroupAdmin 保留其布局，再加 unfold 样式。"""


@admin.register(Site)
class UnfoldSiteAdmin(SiteAdmin, UnfoldModelAdmin):
    """站点。domain 决定 sitemap 与 robots.txt 里的绝对地址，
    上线后要在这里改成真实域名。"""

