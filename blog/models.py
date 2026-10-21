from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Category(models.Model):
    TYPE_CHOICES = [
        ('教程', '教程'),
        ('日报', '日报'),
        ('周报',"周报"),
    ]
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True, allow_unicode=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='日报')
    class Meta:
        verbose_name_plural='categories'
        ordering = ['name',]
    def __str__(self):
        return self.name
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)

class Tag(models.Model):
    name = models.CharField(max_length=30, unique=True)
    slug = models.SlugField(max_length=30, unique=True, allow_unicode=True)

    class Meta:
        ordering = ['name',]
    def __str__(self):
        return self.name
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)



class Post(models.Model):
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    text = models.TextField()
    excerpt= models.TextField(blank=True,default='')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True,blank=True,related_name='posts')
    tags = models.ManyToManyField(Tag, blank=True,related_name='posts')
    slug = models.SlugField(max_length=200, unique=True,allow_unicode=True,blank=True,default='')
    created_date = models.DateTimeField(default=timezone.now)
    published_date = models.DateTimeField(blank=True, null=True)

    def publish(self):
        self.published_date = timezone.now()
        self.save()
    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title, allow_unicode=True)
            slug = base
            n = 2
            # 标题重复时依次尝试 base-2、base-3……避免撞唯一约束
            while Post.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{n}'
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)
    def __str__(self):
        return self.title
