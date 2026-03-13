import logging
import time
import pymysql
import pymysql.cursors
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated

from common.config import QUERY_DEFAULT_ACCOUNT, QUERY_DEFAULT_PASSWORD, DBS_DB_CONFIG

logger = logging.getLogger('dbs')


_READONLY_PREFIXES = ('select', 'show', 'describe', 'desc', 'explain', 'use')


def _is_readonly_sql(sql):
    """检查 SQL 语句是否为只读语句（用于 query 角色限制）"""
    statements = [s.strip() for s in sql.split(';') if s.strip()]
    for stmt in statements:
        first_word = stmt.split()[0].lower() if stmt.split() else ''
        if first_word not in _READONLY_PREFIXES:
            return False, stmt
    return True, None


def _is_query_role(user):
    if user.is_superuser:
        return False
    profile = getattr(user, 'profile', None)
    if profile and profile.role == 'admin':
        return False
    return True


def _can_access_instance(user, ip, port):
    """检查用户是否有权访问指定实例：root/admin 全部放行，query 用户需在实例组中"""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    if profile and profile.role == 'admin':
        return True
    # query 角色：检查所属实例组
    from accounts.models import InstanceGroup
    for group in InstanceGroup.objects.filter(members=user):
        if group.has_instance(ip, int(port)):
            return True
    return False


def _resolve_credentials(account, passwd):
    """未传账号时使用默认查询账号 dbs_admin"""
    if not account:
        return QUERY_DEFAULT_ACCOUNT, QUERY_DEFAULT_PASSWORD
    return account, passwd

FILTER_DB_NAMES = {
    'information_schema', 'performance_schema', 'mysql', 'sys', 'test',
    'checksum', 'dba_backup', 'backup_dba', 'percona',
    '#mysql50#lost found', '#mysql50#lost+found',
}
_FILTER_DB_TUPLE = tuple(FILTER_DB_NAMES)


def _connect(ip, port, account, passwd, db=None):
    kwargs = dict(host=ip, port=port, user=account, password=passwd,
                  charset='utf8mb4', connect_timeout=5)
    if db:
        kwargs['db'] = db
    return pymysql.connect(**kwargs)


class DatabaseListView(APIView):
    """查询目标 MySQL 实例的数据库列表"""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        account = request.GET.get('account', '')
        passwd = request.GET.get('passwd', '')
        ip = request.GET.get('ip', '')
        try:
            port = int(request.GET.get('port', 0))
        except (TypeError, ValueError):
            port = 0

        if not ip or not port:
            return Response(
                {'error': True, 'message': 'ip、port 不能为空', 'db_names': []},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not _can_access_instance(request.user, ip, port):
            return Response(
                {'error': True, 'message': '无权限访问该实例，请联系管理员将实例加入您的用户组', 'db_names': []},
                status=status.HTTP_403_FORBIDDEN,
            )

        account, passwd = _resolve_credentials(account, passwd)

        try:
            conn = pymysql.connect(host=ip, port=port, user=account, password=passwd)
            with conn.cursor() as cursor:
                cursor.execute('SHOW DATABASES')
                rows = cursor.fetchall()
            conn.close()
            db_names = [row[0] for row in rows if row[0] not in FILTER_DB_NAMES]
            return Response({'error': False, 'message': '', 'db_names': db_names})
        except Exception as exc:
            logger.error('查询数据库列表失败 %s:%d %s', ip, port, exc)
            err_msg = str(exc)
            if 'Access denied' in err_msg:
                err_msg = f'连接失败：请在目标实例上创建 dbs_admin 账号并授权。（原始错误：{err_msg}）'
            return Response(
                {'error': True, 'message': err_msg, 'db_names': []},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TableListView(APIView):
    """查询指定数据库的表和视图列表"""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        ip = request.GET.get('ip', '')
        account = request.GET.get('account', '')
        passwd = request.GET.get('passwd', '')
        db = request.GET.get('db', '')
        try:
            port = int(request.GET.get('port', 0))
        except (TypeError, ValueError):
            port = 0

        if not ip or not port or not db:
            return Response({'error': True, 'message': '参数不完整', 'tables': []},
                            status=status.HTTP_400_BAD_REQUEST)
        if not _can_access_instance(request.user, ip, port):
            return Response(
                {'error': True, 'message': '无权限访问该实例', 'tables': []},
                status=status.HTTP_403_FORBIDDEN,
            )
        account, passwd = _resolve_credentials(account, passwd)
        try:
            conn = _connect(ip, port, account, passwd, db)
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(
                    "SELECT TABLE_NAME, TABLE_TYPE, TABLE_ROWS, "
                    "ROUND(DATA_LENGTH/1024/1024, 2) AS size_mb "
                    "FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = %s ORDER BY TABLE_TYPE, TABLE_NAME",
                    (db,)
                )
                tables = cursor.fetchall()
            conn.close()
            return Response({'error': False, 'tables': tables})
        except Exception as exc:
            logger.error('查询表列表失败 %s:%d/%s %s', ip, port, db, exc)
            err_msg = str(exc)
            if 'Access denied' in err_msg:
                err_msg = f'连接失败：请在目标实例上创建 dbs_admin 账号并授权。（原始错误：{err_msg}）'
            return Response({'error': True, 'message': err_msg, 'tables': []},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ExecuteSqlView(APIView):
    """执行 SQL 语句并返回结果"""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    MAX_ROWS = 1000  # 最多返回行数

    def post(self, request):
        data = request.data
        ip = data.get('ip', '')
        account = data.get('account', '')
        passwd = data.get('passwd', '')
        db = data.get('db', '')
        sql = data.get('sql', '').strip()
        try:
            port = int(data.get('port', 0))
        except (TypeError, ValueError):
            port = 0

        if not ip or not port or not sql:
            return Response({'error': True, 'message': '参数不完整'},
                            status=status.HTTP_400_BAD_REQUEST)
        if not _can_access_instance(request.user, ip, port):
            return Response(
                {'error': True, 'message': '无权限访问该实例，请联系管理员将实例加入您的用户组'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if _is_query_role(request.user):
            ok, bad_stmt = _is_readonly_sql(sql)
            if not ok:
                return Response(
                    {'error': True, 'message': f'query 角色仅允许执行查询语句（SELECT/SHOW/DESCRIBE/EXPLAIN），'
                                               f'禁止执行：{bad_stmt[:60]}'},
                    status=status.HTTP_403_FORBIDDEN,
                )
        account, passwd = _resolve_credentials(account, passwd)
        try:
            conn = _connect(ip, port, account, passwd, db or None)
            results = []
            t0 = time.time()
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # 支持多语句（分号分割），逐条执行
                statements = [s.strip() for s in sql.split(';') if s.strip()]
                for stmt in statements:
                    cursor.execute(stmt)
                    if cursor.description:
                        columns = [d[0] for d in cursor.description]
                        rows = cursor.fetchmany(self.MAX_ROWS)
                        limited = cursor.fetchone() is not None  # 是否被截断
                        results.append({
                            'type': 'resultset',
                            'columns': columns,
                            'rows': [list(r.values()) for r in rows],
                            'row_count': len(rows),
                            'limited': limited,
                            'sql': stmt,
                        })
                    else:
                        conn.commit()
                        results.append({
                            'type': 'affected',
                            'affected_rows': cursor.rowcount,
                            'sql': stmt,
                        })
            elapsed = round((time.time() - t0) * 1000, 1)
            conn.close()
            return Response({'error': False, 'results': results, 'elapsed_ms': elapsed})
        except Exception as exc:
            logger.error('执行 SQL 失败 %s:%d %s', ip, port, exc)
            err_msg = str(exc)
            if 'Access denied' in err_msg:
                err_msg = f'连接失败：请在目标实例上创建 dbs_admin 账号并授权。（原始错误：{err_msg}）'
            return Response({'error': True, 'message': err_msg},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _is_admin_or_root(user):
    if user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    return profile and profile.role == 'admin'


def _ops_conn():
    """返回 ops_db 连接"""
    return pymysql.connect(**DBS_DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)


class InstanceListView(APIView):
    """实例注册表：GET 列出所有实例，POST 新增（admin/root）"""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            conn = _ops_conn()
            with conn.cursor() as cur:
                cur.execute("SELECT id, remark, ip, port, env FROM dbs_instances ORDER BY id")
                rows = cur.fetchall()
            conn.close()

            # query 角色只返回其所在用户组内的实例
            if _is_query_role(request.user):
                from accounts.models import InstanceGroup
                allowed = set()
                for group in InstanceGroup.objects.filter(members=request.user):
                    for item in (group.instances or []):
                        allowed.add((str(item.get('ip')), int(item.get('port', 0))))
                rows = [r for r in rows if (str(r['ip']), int(r['port'])) in allowed]

            return Response(rows)
        except Exception as exc:
            logger.error('查询实例列表失败: %s', exc)
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        if not _is_admin_or_root(request.user):
            return Response({'error': '无权限'}, status=status.HTTP_403_FORBIDDEN)
        remark = request.data.get('remark', '').strip()
        ip     = request.data.get('ip', '').strip()
        port   = request.data.get('port')
        env    = request.data.get('env', 'test')

        if not ip or not port:
            return Response({'error': 'ip 和 port 为必填项'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            port = int(port)
        except (TypeError, ValueError):
            return Response({'error': 'port 必须为整数'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            conn = _ops_conn()
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM dbs_instances WHERE ip=%s AND port=%s", (ip, port))
                if cur.fetchone():
                    conn.close()
                    return Response({'error': f'{ip}:{port} 已存在'}, status=status.HTTP_400_BAD_REQUEST)
                cur.execute(
                    "INSERT INTO dbs_instances (remark, ip, port, env, created_by) VALUES (%s,%s,%s,%s,%s)",
                    (remark or ip, ip, port, env, request.user.username)
                )
                new_id = cur.lastrowid
            conn.commit()
            conn.close()
            return Response({'id': new_id, 'remark': remark or ip, 'ip': ip, 'port': port, 'env': env},
                            status=status.HTTP_201_CREATED)
        except Exception as exc:
            logger.error('新增实例失败: %s', exc)
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class InstanceDetailView(APIView):
    """实例注册表：PUT 修改、DELETE 删除（admin/root）"""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def _fetch(self, cur, pk):
        cur.execute("SELECT id, remark, ip, port, env FROM dbs_instances WHERE id=%s", (pk,))
        return cur.fetchone()

    def put(self, request, pk):
        if not _is_admin_or_root(request.user):
            return Response({'error': '无权限'}, status=status.HTTP_403_FORBIDDEN)
        try:
            conn = _ops_conn()
            with conn.cursor() as cur:
                inst = self._fetch(cur, pk)
                if not inst:
                    conn.close()
                    return Response({'error': '实例不存在'}, status=status.HTTP_404_NOT_FOUND)

                remark = (request.data.get('remark', inst['remark']) or '').strip() or inst['ip']
                env    = request.data.get('env', inst['env'])
                ip     = (request.data.get('ip', inst['ip']) or '').strip()
                port   = request.data.get('port', inst['port'])
                try:
                    port = int(port)
                except (TypeError, ValueError):
                    conn.close()
                    return Response({'error': 'port 必须为整数'}, status=status.HTTP_400_BAD_REQUEST)

                if (ip != inst['ip'] or port != inst['port']):
                    cur.execute("SELECT id FROM dbs_instances WHERE ip=%s AND port=%s AND id!=%s", (ip, port, pk))
                    if cur.fetchone():
                        conn.close()
                        return Response({'error': f'{ip}:{port} 已被其他实例占用'},
                                        status=status.HTTP_400_BAD_REQUEST)

                cur.execute(
                    "UPDATE dbs_instances SET remark=%s, ip=%s, port=%s, env=%s WHERE id=%s",
                    (remark, ip, port, env, pk)
                )
            conn.commit()
            conn.close()
            return Response({'id': pk, 'remark': remark, 'ip': ip, 'port': port, 'env': env})
        except Exception as exc:
            logger.error('更新实例失败: %s', exc)
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, pk):
        if not _is_admin_or_root(request.user):
            return Response({'error': '无权限'}, status=status.HTTP_403_FORBIDDEN)
        try:
            conn = _ops_conn()
            with conn.cursor() as cur:
                if not self._fetch(cur, pk):
                    conn.close()
                    return Response({'error': '实例不存在'}, status=status.HTTP_404_NOT_FOUND)
                cur.execute("DELETE FROM dbs_instances WHERE id=%s", (pk,))
            conn.commit()
            conn.close()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as exc:
            logger.error('删除实例失败: %s', exc)
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DatabaseSearchView(APIView):
    """按数据库名或 IP+端口 跨实例查询数据库信息，所有角色可用"""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        db_name = request.GET.get('db_name', '').strip()
        ip_filter = request.GET.get('ip', '').strip()
        port_str = request.GET.get('port', '').strip()

        if not db_name and not (ip_filter and port_str) and _is_query_role(request.user):
            return Response(
                {'error': True, 'message': '请输入数据库名称，或同时输入 IP 和端口', 'results': []},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if db_name and _is_query_role(request.user) and db_name.lower() in FILTER_DB_NAMES:
            return Response(
                {'error': True, 'message': f'禁止查询系统库：{db_name}', 'results': []},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 查询可访问实例列表
        try:
            conn = _ops_conn()
            with conn.cursor() as cur:
                if ip_filter and port_str:
                    cur.execute(
                        "SELECT id, remark, ip, port, env FROM dbs_instances WHERE ip=%s AND port=%s",
                        (ip_filter, int(port_str))
                    )
                else:
                    cur.execute("SELECT id, remark, ip, port, env FROM dbs_instances ORDER BY id")
                instances = cur.fetchall()
            conn.close()
        except Exception as exc:
            logger.error('获取实例列表失败: %s', exc)
            return Response({'error': True, 'message': str(exc), 'results': []},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 按 IP+端口 查询仅限 root/admin
        if ip_filter and port_str and _is_query_role(request.user):
            return Response(
                {'error': True, 'message': '无权限通过 IP+端口 方式查询，请使用数据库名称查询', 'results': []},
                status=status.HTTP_403_FORBIDDEN,
            )

        results = []
        for inst in instances:
            try:
                conn = _connect(inst['ip'], inst['port'], QUERY_DEFAULT_ACCOUNT, QUERY_DEFAULT_PASSWORD)
                with conn.cursor(pymysql.cursors.DictCursor) as cur:
                    if db_name:
                        # 检查该实例是否存在该数据库
                        cur.execute(
                            "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s",
                            (db_name,)
                        )
                        if not cur.fetchone():
                            conn.close()
                            continue
                        cur.execute(
                            "SELECT COUNT(*) AS table_count, "
                            "ROUND(SUM(DATA_LENGTH + INDEX_LENGTH)/1024/1024, 2) AS size_mb "
                            "FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s",
                            (db_name,)
                        )
                        stats = cur.fetchone() or {}
                        results.append({
                            'id': inst['id'],
                            'ip': inst['ip'],
                            'port': inst['port'],
                            'remark': inst['remark'],
                            'env': inst['env'],
                            'db_name': db_name,
                            'table_count': int(stats.get('table_count') or 0),
                            'size_mb': float(stats.get('size_mb') or 0),
                        })
                    else:
                        # 列出该实例所有业务数据库
                        cur.execute(
                            "SELECT TABLE_SCHEMA AS db_name, COUNT(*) AS table_count, "
                            "ROUND(SUM(DATA_LENGTH + INDEX_LENGTH)/1024/1024, 2) AS size_mb "
                            "FROM information_schema.TABLES "
                            "WHERE TABLE_SCHEMA NOT IN %s "
                            "GROUP BY TABLE_SCHEMA ORDER BY TABLE_SCHEMA",
                            (_FILTER_DB_TUPLE,)
                        )
                        for db in cur.fetchall():
                            results.append({
                                'id': inst['id'],
                                'ip': inst['ip'],
                                'port': inst['port'],
                                'remark': inst['remark'],
                                'env': inst['env'],
                                'db_name': db['db_name'],
                                'table_count': int(db.get('table_count') or 0),
                                'size_mb': float(db.get('size_mb') or 0),
                            })
                conn.close()
            except Exception as exc:
                logger.warning('搜索实例 %s:%s 失败: %s', inst['ip'], inst['port'], exc)
                results.append({
                    'id': inst['id'],
                    'ip': inst['ip'],
                    'port': inst['port'],
                    'remark': inst['remark'],
                    'env': inst['env'],
                    'db_name': '-',
                    'table_count': '-',
                    'size_mb': '-',
                    'error': str(exc),
                })

        return Response({'error': False, 'results': results})
