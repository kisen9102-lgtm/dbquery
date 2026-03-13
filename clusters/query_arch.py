"""
集群拓扑查询：连接目标节点，收集主从复制状态并返回。
- 兼容 MySQL 8.0 新字段名（Source_Host / Replica_IO_Running）和旧字段名
- 不尝试递归连接 Docker 内网 IP / 容器名，只展示目标节点自己掌握的拓扑信息
"""
import logging

from common.db_util import open_remote_cursor

logger = logging.getLogger('dbs')

_REPL_USERS = {'repl', 'replication', 'replicater', 'replica'}


def query_nodes_in_cluster(ip: str, port: int, account: str, passwd: str) -> list:
    node = {'ip': ip, 'port': port, 'status': 1, 'comment': ''}

    with open_remote_cursor(ip, port, account, passwd) as cursor:
        # ── 基本信息 ──────────────────────────────────────────────────────
        cursor.execute(
            "SELECT @@server_id AS server_id, @@read_only AS read_only, "
            "@@version AS version, @@gtid_mode AS gtid_mode"
        )
        info = cursor.fetchone() or {}
        node.update({
            'server_id': info.get('server_id'),
            'version':   info.get('version', ''),
            'read_only': bool(info.get('read_only')),
            'gtid_mode': str(info.get('gtid_mode', '')),
        })

        # ── 主从状态 ──────────────────────────────────────────────────────
        replica = _get_replica_status(cursor)
        if replica:
            # 这是一个从库
            running = (replica['io_running'].lower() == 'yes'
                       and replica['sql_running'].lower() == 'yes')
            node.update({
                'role':           'slave',
                'level':          1,
                'master_host':    replica['master_host'],
                'master_port':    replica['master_port'],
                'io_running':     replica['io_running'],
                'sql_running':    replica['sql_running'],
                'seconds_behind': replica['seconds_behind'],
                'last_error':     replica['last_error'],
                'status':         1 if running else 2,
                'comment':        '' if running else
                                  f"IO:{replica['io_running']} SQL:{replica['sql_running']} "
                                  f"Error:{replica['last_error']}",
            })
        else:
            # 这是主库或独立节点
            slaves = _get_slave_connections(cursor)
            node.update({
                'role':   'master' if slaves else 'standalone',
                'level':  0,
                'slaves': slaves,
            })

    return [node]


def _get_replica_status(cursor) -> dict | None:
    """尝试 SHOW REPLICA STATUS（8.0+）和 SHOW SLAVE STATUS（旧版），兼容两套字段名。"""
    for sql in ('SHOW REPLICA STATUS', 'SHOW SLAVE STATUS'):
        try:
            cursor.execute(sql)
            row = cursor.fetchone()
            if row is None:
                return None
            # MySQL 8.0 新字段名
            if 'Source_Host' in row:
                return {
                    'master_host':    row.get('Source_Host', ''),
                    'master_port':    row.get('Source_Port', 3306),
                    'io_running':     row.get('Replica_IO_Running', ''),
                    'sql_running':    row.get('Replica_SQL_Running', ''),
                    'seconds_behind': row.get('Seconds_Behind_Source'),
                    'last_error':     row.get('Last_Error', ''),
                }
            # 旧字段名
            if 'Master_Host' in row:
                return {
                    'master_host':    row.get('Master_Host', ''),
                    'master_port':    row.get('Master_Port', 3306),
                    'io_running':     row.get('Slave_IO_Running', ''),
                    'sql_running':    row.get('Slave_SQL_Running', ''),
                    'seconds_behind': row.get('Seconds_Behind_Master'),
                    'last_error':     row.get('Last_Error', ''),
                }
            return None
        except Exception as exc:
            logger.debug('%s 执行失败: %s', sql, exc)
    return None


def _get_slave_connections(cursor) -> list:
    """从 PROCESSLIST 找到正在复制的从库连接。"""
    try:
        cursor.execute('SHOW PROCESSLIST')
        rows = cursor.fetchall()
        slaves = []
        for row in rows:
            if row.get('User', '').lower() in _REPL_USERS:
                host_str = row.get('Host', '')
                slave_ip = host_str.split(':')[0] if host_str else ''
                slaves.append({
                    'host':    slave_ip,
                    'user':    row.get('User', ''),
                    'state':   row.get('State', ''),
                    'command': row.get('Command', ''),
                })
        return slaves
    except Exception as exc:
        logger.debug('SHOW PROCESSLIST 失败: %s', exc)
        return []
