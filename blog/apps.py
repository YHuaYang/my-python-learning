from django.apps import AppConfig


class BlogConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'blog'
    # 后台侧边栏与面包屑显示的应用名。
    # 不设的话后台会直接显示 app 的技术名「Blog」，
    # 与周围已中文化的模型名混在一起。
    verbose_name = '博客内容'
