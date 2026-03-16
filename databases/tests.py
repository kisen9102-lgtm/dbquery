# databases/tests.py
from django.test import TestCase
from databases.models import Instance


class InstanceModelTest(TestCase):
    def test_db_type_choices_include_postgresql(self):
        choices = dict(Instance.DB_TYPE_CHOICES)
        self.assertIn('postgresql', choices)
        self.assertEqual(choices['postgresql'], 'PostgreSQL')

    def test_create_postgresql_instance(self):
        inst = Instance.objects.create(
            remark='test-pg', ip='127.0.0.1', port=15432,
            env='test', db_type='postgresql',
        )
        self.assertEqual(inst.db_type, 'postgresql')
        self.assertIn('postgresql', str(inst))
