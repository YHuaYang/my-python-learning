from django import forms
from .models import Post


class SearchForm(forms.Form):
    # 用普通 Form 而不是 ModelForm：搜索不保存数据，不需要模型绑定。
    # required=False 让空白提交也能通过校验（不填关键词 = 显示全部或空结果）
    q = forms.CharField(
        label='关键词',
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={
            'placeholder': '搜索文章标题或正文',
            'class': 'w-full rounded border border-neutral-300 px-3 py-2 text-sm '
                     'focus:border-brand focus:outline-none '
                     'dark:border-neutral-600 dark:bg-neutral-800 dark:text-neutral-100 '
                     'dark:placeholder-neutral-500',
        }),
    )