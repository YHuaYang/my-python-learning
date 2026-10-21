from django.contrib import admin
from .models import Post,Category


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
       list_display = ('title', 'slug', 'author', 'category','published_date',)
       list_filter = ('category','published_date', 'author')
       search_fields = ('title', 'text')
       prepopulated_fields = {'slug': ('title',)}
       date_hierarchy = 'published_date'
       ordering = ('-published_date',)
       list_per_page = 20

       fieldsets = (
           ('内容', {
               'fields': ('title', 'slug', 'category','author', 'excerpt', 'text')
           }),
           ('发布', {
               'fields': ('published_date', 'created_date'),
               'classes': ('collapse',),
           }),
       )
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
       list_display = ('name','slug','type')
       list_filter = ('type',)
       search_fields = ('name',)
       prepopulated_fields = {'slug':('name',)}

