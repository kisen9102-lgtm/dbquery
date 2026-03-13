from django.db import models


class Instance(models.Model):
    DB_TYPE_CHOICES = [
        ('mysql', 'MySQL'),
        ('tidb', 'TiDB'),
    ]
    ENV_CHOICES = [
        ('prod', 'prod'),
        ('test', 'test'),
        ('dev', 'dev'),
    ]

    remark     = models.CharField(max_length=128, blank=True, default='')
    ip         = models.GenericIPAddressField()
    port       = models.PositiveIntegerField()
    env        = models.CharField(max_length=16, choices=ENV_CHOICES, default='test')
    db_type    = models.CharField(max_length=16, choices=DB_TYPE_CHOICES, default='mysql')
    created_by = models.CharField(max_length=64, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'dbs_instances'
        unique_together = [('ip', 'port')]

    def __str__(self):
        return f'{self.remark or self.ip}:{self.port} [{self.db_type}]'
