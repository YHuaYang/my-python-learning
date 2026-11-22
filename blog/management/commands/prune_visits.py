"""清理过期的访问记录。

用法：
    python manage.py prune_visits              # 默认保留 90 天
    python manage.py prune_visits --days 30    # 只留 30 天
    python manage.py prune_visits --dry-run    # 只看要删多少，不真删

为什么要单独一个命令而不是中间件里顺手删：
中间件在每个请求上跑，在里面做批量删除会让某个访客莫名承担一次
大范围 DELETE。清理是运维动作，该由人（或 cron）在合适的时间触发。
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from blog.models import VisitLog

DEFAULT_RETENTION_DAYS = 90


class Command(BaseCommand):
    help = '删除超过保留期的访问记录'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=DEFAULT_RETENTION_DAYS,
            help=f'保留天数，默认 {DEFAULT_RETENTION_DAYS}',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='只统计将要删除的条数，不实际删除',
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']

        if days <= 0:
            self.stderr.write(self.style.ERROR('--days 必须是正整数'))
            return

        cutoff = timezone.now() - timedelta(days=days)
        stale = VisitLog.objects.filter(created_at__lt=cutoff)
        count = stale.count()

        if count == 0:
            self.stdout.write(f'没有超过 {days} 天的记录，无需清理')
            return

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'[dry-run] 将删除 {count} 条（早于 {cutoff:%Y-%m-%d %H:%M}）'
                )
            )
            return

        # delete() 返回 (总删除数, {模型: 数量})，取第一个值即可
        deleted, _ = stale.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f'已删除 {deleted} 条，早于 {cutoff:%Y-%m-%d %H:%M}'
            )
        )
        self.stdout.write(f'剩余记录：{VisitLog.objects.count()} 条')
