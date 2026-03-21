import requests


class ApiClient:

    def __init__(self, url, cookies=None):
        self.url = url.rstrip('/')
        self.session = requests.Session()
        if cookies:
            self.session.cookies.update(cookies)

    def _csrf(self):
        return self.session.cookies.get('csrftoken', '')

    def _post(self, path, data):
        return self.session.post(
            self.url + path,
            json=data,
            headers={'X-CSRFToken': self._csrf()},
        )

    def _delete(self, path):
        return self.session.delete(
            self.url + path,
            headers={'X-CSRFToken': self._csrf()},
        )

    def login(self, username, password):
        self.session.get(self.url + '/accounts/login/')
        resp = self.session.post(
            self.url + '/accounts/login/',
            data={'username': username, 'password': password},
            headers={'X-CSRFToken': self._csrf()},
            allow_redirects=False,
        )
        return resp.status_code in (301, 302)

    def get_cookies(self):
        return dict(self.session.cookies)

    def list_instances(self):
        resp = self.session.get(self.url + '/databases/instances/')
        resp.raise_for_status()
        return resp.json()

    def create_instance(self, ip, port, db_type, env,
                        remark='', auth_username='', auth_password='', auth_source=''):
        resp = self._post('/databases/instances/', {
            'ip': ip, 'port': int(port), 'db_type': db_type, 'env': env,
            'remark': remark, 'auth_username': auth_username,
            'auth_password': auth_password, 'auth_source': auth_source,
        })
        resp.raise_for_status()
        data = resp.json()
        if data.get('error'):
            raise RuntimeError(str(data.get('error', data)))
        return data

    def delete_instance(self, instance_id):
        resp = self._delete(f'/databases/instances/{instance_id}/')
        resp.raise_for_status()

    def get_databases(self, instance_id):
        resp = self.session.get(
            self.url + '/databases/',
            params={'instance_id': instance_id},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get('error'):
            raise RuntimeError(data.get('message', '查询失败'))
        return data['db_names']

    def get_tables(self, instance_id, db):
        resp = self.session.get(
            self.url + '/databases/tables/',
            params={'instance_id': instance_id, 'db': db},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get('error'):
            raise RuntimeError(data.get('message', '查询失败'))
        return data['tables']

    def execute_sql(self, instance_id, db, sql):
        resp = self._post('/databases/execute_sql/', {
            'instance_id': instance_id, 'db': db, 'sql': sql,
        })
        resp.raise_for_status()
        data = resp.json()
        if data.get('error'):
            raise RuntimeError(data.get('message', '执行失败'))
        return data['results'], data['elapsed_ms']
