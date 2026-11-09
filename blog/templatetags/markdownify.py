"""自定义模板过滤器：Markdown 渲染。

放在 blog/templatetags/ 下才能被 {% load %} 找到。
"""
import markdown
import nh3
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# nh3 的白名单：只放行 Markdown 渲染可能产生的标签。
# 漏掉的标签会被删掉（连同内容），不会漏出到页面上。
ALLOWED_TAGS = {
    'p', 'br', 'hr',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'strong', 'b', 'em', 'i', 'del', 's', 'sup', 'sub',
    'ul', 'ol', 'li',
    'blockquote',
    'code', 'pre', 'span',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
    'a', 'img',
    'div',
}

# 属性也必须逐个放行。
# href/src 不放行 javascript: 协议 —— nh3 默认会拦掉，这是它的默认安全行为，
# 不用自己写判断。codehilite 需要 class 才能上色，所以 span/code/pre/div
# 都要给 class。
ALLOWED_ATTRIBUTES = {
    'a': {'href', 'title'},
    'img': {'src', 'alt', 'title'},
    'code': {'class'},
    'pre': {'class'},
    'span': {'class'},
    'div': {'class'},
    'th': {'align'},
    'td': {'align'},
}


@register.filter(name='markdownify')
def markdownify(text):
    """把 Markdown 文本渲染成可直接插入页面的 HTML。

    安全说明：这里用了 mark_safe，输出的 HTML 不会被 Django 转义，
    所以渲染后必须过一道 nh3 白名单清洗。
    文章是站主在 Admin 写的，可信度较高，但「可信」不等于「不会出错」：
    粘贴进来的外链、以后开放的访客输入，都可能带 <script>。
    漏了这一步就是存储型 XSS。
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

    # link_rel：给所有外链自动补上 rel，避免 window.opener 反向操作本页。
    # 这一项 nh3 默认就是 'noopener noreferrer'，写出来是为了明确意图。
    clean_html = nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        link_rel='noopener noreferrer',
    )
    return mark_safe(clean_html)
