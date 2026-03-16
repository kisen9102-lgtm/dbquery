from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('databases', '0002_instance_add_postgresql'),
    ]

    operations = [
        migrations.AddField(
            model_name='instance',
            name='auth_username',
            field=models.CharField(blank=True, default='', max_length=128),
        ),
        migrations.AddField(
            model_name='instance',
            name='auth_password',
            field=models.CharField(blank=True, default='', max_length=256),
        ),
        migrations.AddField(
            model_name='instance',
            name='auth_source',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AlterField(
            model_name='instance',
            name='db_type',
            field=models.CharField(
                choices=[
                    ('mysql', 'MySQL'), ('tidb', 'TiDB'),
                    ('postgresql', 'PostgreSQL'),
                    ('redis', 'Redis'), ('mongodb', 'MongoDB'),
                ],
                default='mysql', max_length=16,
            ),
        ),
    ]
