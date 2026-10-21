from django.shortcuts import render,get_object_or_404
from django.utils import timezone
from .models import Post

# 添加这个函数
def post_list(request):
    posts=Post.objects.filter(published_date__lte=timezone.now()).order_by('published_date')
    return render(request, 'blog/post_list.html', {"posts":posts})
def about(request):
    return render(request, 'blog/about.html')
def post_detail(request, slug):
    post=get_object_or_404(
        Post,
        slug=slug,
        published_date__lte=timezone.now()
    )
    return render(request, 'blog/post_detail.html', {"post":post})


