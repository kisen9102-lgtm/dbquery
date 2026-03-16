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


from unittest.mock import patch, MagicMock
from django.contrib.auth.models import User
from rest_framework.test import APIClient


class ResolveInstanceTest(TestCase):

    def setUp(self):
        self.root = User.objects.create_superuser('root', password='root')
        self.query_user = User.objects.create_user('quser', password='quser')
        self.inst = Instance.objects.create(
            remark='pg-test', ip='127.0.0.1', port=15432,
            env='test', db_type='postgresql',
        )

    def _call(self, user, ip='', port=0, instance_id=''):
        from databases.views import _resolve_instance
        request = MagicMock()
        request.user = user
        return _resolve_instance(request, ip, port, instance_id)

    def test_instance_id_resolves_correctly(self):
        with patch('databases.views._can_access_instance', return_value=True):
            ip, port, db_type, inst = self._call(
                self.root, instance_id=str(self.inst.pk)
            )
        self.assertEqual(ip, '127.0.0.1')
        self.assertEqual(port, 15432)
        self.assertEqual(db_type, 'postgresql')

    def test_instance_id_not_found_raises(self):
        from databases.views import _resolve_instance
        request = MagicMock(); request.user = self.root
        with self.assertRaises(ValueError):
            _resolve_instance(request, '', 0, '999999')

    def test_ip_port_allowed_for_root(self):
        ip, port, db_type, _ = self._call(
            self.root, ip='127.0.0.1', port=15432
        )
        self.assertEqual(ip, '127.0.0.1')
        self.assertEqual(port, 15432)

    def test_ip_port_forbidden_for_non_root(self):
        with self.assertRaises(PermissionError):
            self._call(self.query_user, ip='127.0.0.1', port=15432)

    def test_no_params_raises_value_error(self):
        with self.assertRaises(ValueError):
            self._call(self.root)


class InstToDictTest(TestCase):

    def setUp(self):
        self.root = User.objects.create_superuser('root2', password='root2')
        self.admin = User.objects.create_user('admin2', password='admin2')
        from accounts.models import UserProfile
        UserProfile.objects.create(user=self.admin, role='admin')
        self.query_user = User.objects.create_user('quser2', password='quser2')
        self.inst = Instance.objects.create(
            remark='pg', ip='10.0.0.1', port=5432, env='prod', db_type='postgresql'
        )

    def test_full_dict_contains_ip_port(self):
        from databases.views import _inst_to_dict_full
        d = _inst_to_dict_full(self.inst)
        self.assertIn('ip', d)
        self.assertIn('port', d)

    def test_safe_dict_excludes_ip_port(self):
        from databases.views import _inst_to_dict_safe
        d = _inst_to_dict_safe(self.inst)
        self.assertNotIn('ip', d)
        self.assertNotIn('port', d)
        self.assertIn('id', d)
        self.assertIn('remark', d)
