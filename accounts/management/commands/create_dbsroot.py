"""
用法: python manage.py create_dbsroot [--password PASSWORD]
若 dbsroot 已存在则不做任何操作。
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = '创建 dbsroot 超级用户（已存在时跳过）'

    def add_arguments(self, parser):
        parser.add_argument('--password', default='Dbs@Root2026',
                            help='dbsroot 的初始密码（默认 Dbs@Root2026）')

    def handle(self, *args, **options):
        username = 'dbsroot'
        password = options['password']
        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(f'用户 {username} 已存在，跳过。'))
            return
        User.objects.create_superuser(username=username, password=password, email='')
        self.stdout.write(self.style.SUCCESS(f'超级用户 {username} 创建成功，密码: {password}'))
