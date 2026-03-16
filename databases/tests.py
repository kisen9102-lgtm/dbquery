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


class DatabaseListViewTest(TestCase):

    def setUp(self):
        self.root = User.objects.create_superuser('root3', password='root3')
        self.quser = User.objects.create_user('quser3', password='quser3')
        self.inst = Instance.objects.create(
            remark='pg', ip='10.0.0.1', port=5432, env='test', db_type='postgresql'
        )
        self.client = APIClient()

    def test_instance_id_returns_db_list(self):
        self.client.force_authenticate(self.root)
        with patch('databases.views.get_connector') as mock_gc:
            mock_gc.return_value.get_databases.return_value = ['mydb']
            with patch('databases.views._can_access_instance', return_value=True):
                resp = self.client.get(
                    '/databases/', {'instance_id': self.inst.pk}
                )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['db_names'], ['mydb'])

    def test_ip_port_forbidden_for_query_user(self):
        self.client.force_authenticate(self.quser)
        resp = self.client.get('/databases/', {'ip': '10.0.0.1', 'port': 5432})
        self.assertEqual(resp.status_code, 403)

    def test_missing_params_returns_400(self):
        self.client.force_authenticate(self.root)
        resp = self.client.get('/databases/')
        self.assertEqual(resp.status_code, 400)


class ExecuteSqlViewTest(TestCase):

    def setUp(self):
        self.root = User.objects.create_superuser('root4', password='root4')
        self.quser = User.objects.create_user('quser4', password='quser4')
        self.inst = Instance.objects.create(
            remark='pg', ip='10.0.0.1', port=5432, env='test', db_type='postgresql'
        )
        self.client = APIClient()

    def test_execute_sql_with_instance_id(self):
        self.client.force_authenticate(self.root)
        mock_results = [{'type': 'resultset', 'columns': ['v'], 'rows': [['16']], 'row_count': 1, 'limited': False, 'sql': 'SELECT version()'}]
        with patch('databases.views.get_connector') as mock_gc:
            mock_gc.return_value.execute_sql.return_value = (mock_results, 5.0)
            with patch('databases.views._can_access_instance', return_value=True):
                resp = self.client.post('/databases/execute_sql/', {
                    'instance_id': self.inst.pk,
                    'sql': 'SELECT version()',
                }, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data['error'])

    def test_query_role_blocked_from_dml(self):
        self.client.force_authenticate(self.quser)
        with patch('databases.views._resolve_instance',
                   return_value=('10.0.0.1', 5432, 'postgresql', self.inst)):
            resp = self.client.post('/databases/execute_sql/', {
                'instance_id': self.inst.pk,
                'sql': 'DELETE FROM users',
            }, format='json')
        self.assertEqual(resp.status_code, 403)
