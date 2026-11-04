"""自定义模板过滤器：Markdown 渲染。

放在 blog/templatetags/ 下才能被 {% load %} 找到。
"""
import markdown
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(name='markdownify')
def markdownify(text):
    """把 Markdown 文本渲染成可直接插入页面的 HTML。

    安全说明：这里用了 mark_safe，输出的 HTML 不会被 Django 转义。
    当前可以接受，因为站内只有站主能在 Admin 里写文章。
    若以后开放访客输入（留言、评论），必须先用 bleach 或 nh3 清洗 HTML，
    否则 Markdown 里的 <script> 会真的执行。
    """
    if not text:
        return ''

    html = markdown.markdown(
        text,
        extensions=[
            'fenced_code',
            'codehilite',
            'tables',
            'toc',
        ],
        extension_configs={
            'codehilite': {
                'css_class': 'codehilite',
                # 不猜语言：写成 ```python 才高亮，避免误判成别的语法
                'guess_lang': False,
                'linenums': False,
            },
        },
    )
    return mark_safe(html)
