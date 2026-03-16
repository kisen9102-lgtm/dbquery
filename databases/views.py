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
from common.connector import get_connector, MYSQL_SYSTEM_DBS
from .models import Instance

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


def _resolve_instance(request, ip, port, instance_id):
    """
    从请求参数解析目标实例，返回 (ip, port, db_type, inst_or_None)。
    优先使用 instance_id；无则用 ip+port（仅 root）。
    失败时抛 ValueError（参数错误）或 PermissionError（权限不足）。
    """
    if instance_id:
        try:
            inst = Instance.objects.get(pk=instance_id)
        except (Instance.DoesNotExist, ValueError):
            raise ValueError(f'实例 {instance_id} 不存在')
        if not _can_access_instance(request.user, inst.ip, inst.port):
            raise PermissionError('无权限访问该实例，请联系管理员')
        return inst.ip, inst.port, inst.db_type, inst

    if ip and port:
        if not request.user.is_superuser:
            raise PermissionError('ip/port 方式仅 root 角色可用，请使用 instance_id')
        try:
            inst = Instance.objects.filter(ip=ip, port=int(port)).first()
        except (TypeError, ValueError):
            inst = None
        db_type = inst.db_type if inst else 'mysql'
        return ip, int(port), db_type, inst

    raise ValueError('instance_id 或 ip+port 不能同时为空')


def _resolve_credentials(account, passwd):
    """未传账号时使用默认查询账号 dbs_admin"""
    if not account:
        return QUERY_DEFAULT_ACCOUNT, QUERY_DEFAULT_PASSWORD
    return account, passwd

# 保留名字供 DatabaseSearchView 用；MySQL 系统库 + PG 系统库合并
FILTER_DB_NAMES = MYSQL_SYSTEM_DBS | {'postgres', 'template0', 'template1'}
_FILTER_DB_TUPLE = tuple(FILTER_DB_NAMES)


def _connect(ip, port, account, passwd, db=None):
    kwargs = dict(host=ip, port=port, user=account, password=passwd,
                  charset='utf8mb4', connect_timeout=5)
    if db:
        kwargs['db'] = db
    return pymysql.connect(**kwargs)


class DatabaseListView(APIView):
    """查询目标实例的数据库列表（支持 MySQL/TiDB/PostgreSQL）"""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        instance_id = request.GET.get('instance_id', '').strip()
        account     = request.GET.get('account', '')
        passwd      = request.GET.get('passwd', '')
        ip          = request.GET.get('ip', '')
        port_str    = request.GET.get('port', '')
        try:
            port = int(port_str) if port_str else 0
        except (TypeError, ValueError):
            port = 0

        try:
            ip, port, db_type, inst = _resolve_instance(request, ip, port, instance_id)
        except PermissionError as e:
            return Response({'error': True, 'message': str(e), 'db_names': []},
                            status=status.HTTP_403_FORBIDDEN)
        except ValueError as e:
            return Response({'error': True, 'message': str(e), 'db_names': []},
                            status=status.HTTP_400_BAD_REQUEST)

        account, passwd = _resolve_credentials(account, passwd)
        try:
            connector = get_connector(db_type, ip, port, account, passwd)
            db_names = connector.get_databases()
            return Response({'error': False, 'message': '', 'db_names': db_names})
        except Exception as exc:
            logger.error('查询数据库列表失败 %s:%d %s', ip, port, exc)
            err_msg = str(exc)
            if 'Access denied' in err_msg or 'authentication' in err_msg.lower():
                err_msg = f'连接失败：请在目标实例上创建账号并授权。（原始错误：{err_msg}）'
            return Response({'error': True, 'message': err_msg, 'db_names': []},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TableListView(APIView):
    """查询指定数据库的表和视图列表（支持 MySQL/TiDB/PostgreSQL）"""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        instance_id = request.GET.get('instance_id', '').strip()
        account     = request.GET.get('account', '')
        passwd      = request.GET.get('passwd', '')
        db          = request.GET.get('db', '')
        ip          = request.GET.get('ip', '')
        port_str    = request.GET.get('port', '')
        try:
            port = int(port_str) if port_str else 0
        except (TypeError, ValueError):
            port = 0

        if not db:
            return Response({'error': True, 'message': '参数不完整', 'tables': []},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            ip, port, db_type, inst = _resolve_instance(request, ip, port, instance_id)
        except PermissionError as e:
            return Response({'error': True, 'message': str(e), 'tables': []},
                            status=status.HTTP_403_FORBIDDEN)
        except ValueError as e:
            return Response({'error': True, 'message': str(e), 'tables': []},
                            status=status.HTTP_400_BAD_REQUEST)

        account, passwd = _resolve_credentials(account, passwd)
        try:
            connector = get_connector(db_type, ip, port, account, passwd)
            tables = connector.get_tables(db)
            return Response({'error': False, 'tables': tables})
        except Exception as exc:
            logger.error('查询表列表失败 %s:%d/%s %s', ip, port, db, exc)
            err_msg = str(exc)
            if 'Access denied' in err_msg or 'authentication' in err_msg.lower():
                err_msg = f'连接失败：请在目标实例上创建账号并授权。（原始错误：{err_msg}）'
            return Response({'error': True, 'message': err_msg, 'tables': []},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ExecuteSqlView(APIView):
    """执行 SQL 语句并返回结果（支持 MySQL/TiDB/PostgreSQL）"""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data        = request.data
        instance_id = str(data.get('instance_id', '')).strip()
        account     = data.get('account', '')
        passwd      = data.get('passwd', '')
        db          = data.get('db', '')
        sql         = data.get('sql', '').strip()
        ip          = data.get('ip', '')
        try:
            port = int(data.get('port', 0))
        except (TypeError, ValueError):
            port = 0

        if not sql:
            return Response({'error': True, 'message': '参数不完整'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            ip, port, db_type, inst = _resolve_instance(request, ip, port, instance_id)
        except PermissionError as e:
            return Response({'error': True, 'message': str(e)},
                            status=status.HTTP_403_FORBIDDEN)
        except ValueError as e:
            return Response({'error': True, 'message': str(e)},
                            status=status.HTTP_400_BAD_REQUEST)

        if _is_query_role(request.user):
            ok, bad_stmt = _is_readonly_sql(sql)
            if not ok:
                return Response(
                    {'error': True,
                     'message': f'query 角色仅允许执行查询语句，禁止执行：{bad_stmt[:60]}'},
                    status=status.HTTP_403_FORBIDDEN,
                )

        account, passwd = _resolve_credentials(account, passwd)
        if db_type == 'postgresql':
            sql = sql.replace('`', '"')
        try:
            connector = get_connector(db_type, ip, port, account, passwd)
            results, elapsed = connector.execute_sql(sql, db or '')
            return Response({'error': False, 'results': results, 'elapsed_ms': elapsed})
        except Exception as exc:
            logger.error('执行 SQL 失败 %s:%d %s', ip, port, exc)
            err_msg = str(exc)
            if 'Access denied' in err_msg or 'authentication' in err_msg.lower():
                err_msg = f'连接失败：请在目标实例上创建账号并授权。（原始错误：{err_msg}）'
            return Response({'error': True, 'message': err_msg},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _is_admin_or_root(user):
    if user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    return profile and profile.role == 'admin'


def _inst_to_dict_full(inst):
    """含 ip/port，仅 root 使用。"""
    return {
        'id': inst.id, 'remark': inst.remark,
        'ip': inst.ip, 'port': inst.port,
        'env': inst.env, 'db_type': inst.db_type,
    }


def _inst_to_dict_safe(inst):
    """不含 ip/port，非 root 使用。"""
    return {
        'id': inst.id, 'remark': inst.remark,
        'env': inst.env, 'db_type': inst.db_type,
    }


def _inst_to_dict(inst, user=None):
    """按用户角色返回对应格式（兼容旧调用）。"""
    if user and user.is_superuser:
        return _inst_to_dict_full(inst)
    return _inst_to_dict_safe(inst)


class InstanceListView(APIView):
    """实例注册表：GET 列出所有实例，POST 新增（admin/root）"""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Instance.objects.all().order_by('id')

        # query 角色只返回其所在用户组内的实例
        if _is_query_role(request.user):
            from accounts.models import InstanceGroup
            allowed = set()
            for group in InstanceGroup.objects.filter(members=request.user):
                for item in (group.instances or []):
                    allowed.add((str(item.get('ip')), int(item.get('port', 0))))
            qs = [inst for inst in qs if (str(inst.ip), inst.port) in allowed]

        to_dict = _inst_to_dict_full if request.user.is_superuser else _inst_to_dict_safe
        return Response([to_dict(inst) for inst in qs])

    def post(self, request):
        if not _is_admin_or_root(request.user):
            return Response({'error': '无权限'}, status=status.HTTP_403_FORBIDDEN)
        remark  = request.data.get('remark', '').strip()
        ip      = request.data.get('ip', '').strip()
        port    = request.data.get('port')
        env     = request.data.get('env', 'test')
        db_type = request.data.get('db_type', 'mysql')

        if not ip or not port:
            return Response({'error': 'ip 和 port 为必填项'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            port = int(port)
        except (TypeError, ValueError):
            return Response({'error': 'port 必须为整数'}, status=status.HTTP_400_BAD_REQUEST)
        if db_type not in ('mysql', 'tidb', 'postgresql'):
            return Response({'error': 'db_type 不合法'}, status=status.HTTP_400_BAD_REQUEST)

        if Instance.objects.filter(ip=ip, port=port).exists():
            return Response({'error': f'{ip}:{port} 已存在'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            inst = Instance.objects.create(
                remark=remark or ip, ip=ip, port=port,
                env=env, db_type=db_type, created_by=request.user.username,
            )
            return Response(_inst_to_dict_full(inst), status=status.HTTP_201_CREATED)
        except Exception as exc:
            logger.error('新增实例失败: %s', exc)
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class InstanceDetailView(APIView):
    """实例注册表：PUT 修改、DELETE 删除（admin/root）"""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def put(self, request, pk):
        if not _is_admin_or_root(request.user):
            return Response({'error': '无权限'}, status=status.HTTP_403_FORBIDDEN)
        try:
            inst = Instance.objects.get(pk=pk)
        except Instance.DoesNotExist:
            return Response({'error': '实例不存在'}, status=status.HTTP_404_NOT_FOUND)

        remark  = (request.data.get('remark', inst.remark) or '').strip() or inst.ip
        env     = request.data.get('env', inst.env)
        db_type = request.data.get('db_type', inst.db_type)
        ip      = (request.data.get('ip', inst.ip) or '').strip()
        port    = request.data.get('port', inst.port)
        try:
            port = int(port)
        except (TypeError, ValueError):
            return Response({'error': 'port 必须为整数'}, status=status.HTTP_400_BAD_REQUEST)
        if db_type not in ('mysql', 'tidb', 'postgresql'):
            return Response({'error': 'db_type 不合法'}, status=status.HTTP_400_BAD_REQUEST)

        if (ip != inst.ip or port != inst.port) and \
                Instance.objects.filter(ip=ip, port=port).exclude(pk=pk).exists():
            return Response({'error': f'{ip}:{port} 已被其他实例占用'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            inst.remark = remark
            inst.ip = ip
            inst.port = port
            inst.env = env
            inst.db_type = db_type
            inst.save()
            return Response(_inst_to_dict_full(inst))
        except Exception as exc:
            logger.error('更新实例失败: %s', exc)
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, pk):
        if not _is_admin_or_root(request.user):
            return Response({'error': '无权限'}, status=status.HTTP_403_FORBIDDEN)
        try:
            inst = Instance.objects.get(pk=pk)
        except Instance.DoesNotExist:
            return Response({'error': '实例不存在'}, status=status.HTTP_404_NOT_FOUND)
        try:
            inst.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as exc:
            logger.error('删除实例失败: %s', exc)
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DatabaseSearchView(APIView):
    """按数据库名或 IP+端口 跨实例查询数据库信息，所有角色可用"""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        db_name   = request.GET.get('db_name', '').strip()
        ip_filter = request.GET.get('ip', '').strip()
        port_str  = request.GET.get('port', '').strip()

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
        if ip_filter and port_str and _is_query_role(request.user):
            return Response(
                {'error': True, 'message': '无权限通过 IP+端口 方式查询，请使用数据库名称查询', 'results': []},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            qs = Instance.objects.all().order_by('id')
            if ip_filter and port_str:
                qs = qs.filter(ip=ip_filter, port=int(port_str))
            instances = list(qs)
        except Exception as exc:
            logger.error('获取实例列表失败: %s', exc)
            return Response({'error': True, 'message': str(exc), 'results': []},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        is_root = request.user.is_superuser
        results = []

        for inst in instances:
            try:
                connector = get_connector(
                    inst.db_type, inst.ip, inst.port,
                    QUERY_DEFAULT_ACCOUNT, QUERY_DEFAULT_PASSWORD,
                )
                db_stats = connector.search_databases(db_name)
            except Exception as exc:
                logger.warning('搜索实例 %s:%s 失败: %s', inst.ip, inst.port, exc)
                base = _inst_to_dict_full(inst) if is_root else _inst_to_dict_safe(inst)
                base.update({'db_name': '-', 'table_count': '-', 'size_mb': '-',
                             'error': str(exc)})
                results.append(base)
                continue

            for db in db_stats:
                base = _inst_to_dict_full(inst) if is_root else _inst_to_dict_safe(inst)
                base.update({
                    'db_name':     db['db_name'],
                    'table_count': db['table_count'],
                    'size_mb':     db['size_mb'],
                })
                results.append(base)

        return Response({'error': False, 'results': results})
