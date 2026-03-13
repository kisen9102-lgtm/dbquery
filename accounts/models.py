from django.contrib.auth.models import User
from django.db import models

ROLE_ADMIN = 'admin'
ROLE_QUERY = 'query'
ROLE_CHOICES = [(ROLE_ADMIN, '管理员'), (ROLE_QUERY, '查询用户')]


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_QUERY)

    def __str__(self):
        return f"{self.user.username} ({self.role})"

    @property
    def effective_role(self):
        if self.user.is_superuser:
            return 'root'
        return self.role

    @property
    def is_admin_or_root(self):
        return self.user.is_superuser or self.role == ROLE_ADMIN


class InstanceGroup(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='组名')
    description = models.TextField(blank=True, verbose_name='描述')
    # 格式: [{"ip": "127.0.0.1", "port": 3306}, ...]
    instances = models.JSONField(default=list, verbose_name='实例列表')
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='created_groups'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    members = models.ManyToManyField(
        User, through='GroupMembership', through_fields=('group', 'user'),
        related_name='instance_groups', blank=True
    )

    def __str__(self):
        return self.name

    def has_instance(self, ip, port):
        return any(
            str(item.get('ip')) == str(ip) and int(item.get('port', 0)) == int(port)
            for item in (self.instances or [])
        )


class GroupMembership(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='group_memberships')
    group = models.ForeignKey(
        InstanceGroup, on_delete=models.CASCADE, related_name='memberships'
    )
    added_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='added_memberships'
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'group')
