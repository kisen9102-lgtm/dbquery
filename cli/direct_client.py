from common.connector import get_connector

_READONLY_PREFIXES = ('select', 'show', 'desc', 'describe', 'explain', 'keys')


class DirectClient:

    def __init__(self, host, port, db_type, user='', password='', auth_source=''):
        self.db_type = db_type
        self.connector = get_connector(db_type, host, int(port), user, password, auth_source)

    def _check_readonly(self, sql):
        tokens = sql.strip().split()
        if not tokens:
            return False
        return tokens[0].lower() in _READONLY_PREFIXES

    def get_databases(self):
        return self.connector.get_databases()

    def get_tables(self, db):
        if self.db_type == 'redis':
            results, _ = self.connector.execute_sql('KEYS *', db)
            tables = []
            if results and results[0]['type'] == 'resultset':
                for row in results[0]['rows']:
                    tables.append({'TABLE_NAME': row[1], 'TABLE_TYPE': 'key',
                                   'TABLE_ROWS': None, 'size_mb': None})
            return tables
        return self.connector.get_tables(db)

    def execute_sql(self, sql, db=''):
        if not self._check_readonly(sql):
            raise PermissionError(
                f'直连模式仅允许只读操作，不支持: {sql.strip().split()[0] if sql.strip() else sql}'
            )
        return self.connector.execute_sql(sql, db)
