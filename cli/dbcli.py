#!/usr/bin/env python3
"""dbcli — dbquery command-line interface"""
import argparse
import sys

import requests

from cli.api_client import ApiClient
from cli.config import load_config, save_config

CONFIG_PATH = None  # use default (~/.dbcli.json)


# ── Output helpers ────────────────────────────────────────────────────────────

def format_table(columns, rows):
    if not columns and not rows:
        return '(empty)'
    col_widths = [len(str(c)) for c in columns]
    for row in rows:
        for i, val in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(str(val)))
    sep = '+' + '+'.join('-' * (w + 2) for w in col_widths) + '+'
    header = '|' + '|'.join(f' {str(c):<{w}} ' for c, w in zip(columns, col_widths)) + '|'
    lines = [sep, header, sep]
    for row in rows:
        line = '|' + '|'.join(
            f' {str(v):<{w}} '
            for (v, w) in zip(row, col_widths)
        ) + '|'
        lines.append(line)
    lines.append(sep)
    return '\n'.join(lines)


def print_results(results, elapsed_ms):
    for r in results:
        if r['type'] == 'resultset':
            print(format_table(r['columns'], r['rows']))
            suffix = ' (已截断)' if r.get('limited') else ''
            print(f'{r["row_count"]} 行{suffix}  ({elapsed_ms} ms)\n')
        else:
            print(f'影响行数: {r["affected_rows"]}  ({elapsed_ms} ms)\n')


# ── Argument parser ───────────────────────────────────────────────────────────

def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog='dbcli', description='dbquery CLI')
    parser.add_argument('--url', default=None, help='dbquery 服务地址')
    parser.add_argument('--user', default=None, help='登录用户名')
    parser.add_argument('--password', default=None, help='登录密码')

    sub = parser.add_subparsers(dest='command')

    # ── instance ──────────────────────────────────────────────────────────────
    inst_p = sub.add_parser('instance', help='管理数据库实例')
    inst_sub = inst_p.add_subparsers(dest='instance_cmd')

    list_p = inst_sub.add_parser('list', help='列出实例')
    list_p.add_argument('--env', default=None, choices=['prod', 'test', 'dev'])
    list_p.add_argument('--type', default=None,
                        choices=['mysql', 'tidb', 'postgresql', 'redis', 'mongodb'])

    get_p = inst_sub.add_parser('get', help='查看实例详情')
    get_p.add_argument('id')

    add_p = inst_sub.add_parser('add', help='新增实例')
    add_p.add_argument('--ip', default=None)
    add_p.add_argument('--port', default=None)
    add_p.add_argument('--db-type', dest='db_type', default=None,
                       choices=['mysql', 'tidb', 'postgresql', 'redis', 'mongodb'])
    add_p.add_argument('--env', default=None, choices=['prod', 'test', 'dev'])
    add_p.add_argument('--remark', default='')
    add_p.add_argument('--auth-username', dest='auth_username', default='')
    add_p.add_argument('--auth-password', dest='auth_password', default='')
    add_p.add_argument('--auth-source', dest='auth_source', default='')

    del_p = inst_sub.add_parser('delete', help='删除实例')
    del_p.add_argument('id')

    # ── query ─────────────────────────────────────────────────────────────────
    q_p = sub.add_parser('query', help='进入交互式查询 shell')
    q_p.add_argument('-i', '--instance-id', dest='instance_id', default=None)
    q_p.add_argument('-d', '--database', dest='database', default='')
    q_p.add_argument('--host', default=None, help='直连主机（直连模式）')
    q_p.add_argument('--port', default=None, help='直连端口（直连模式）')
    q_p.add_argument('--db-type', dest='db_type', default=None,
                     choices=['mysql', 'tidb', 'postgresql', 'redis', 'mongodb'],
                     help='数据库类型（直连模式）')

    return parser.parse_args(argv)


# ── API client factory ────────────────────────────────────────────────────────

def _build_api_client(args, config):
    """Return ApiClient, saving session if newly logged in. Raises on failure."""
    url = args.url or config.get('url', 'http://127.0.0.1:8000')
    cookies = config.get('cookies', {})
    client = ApiClient(url, cookies)

    if not cookies:
        import getpass
        user = args.user or input('用户名: ')
        password = args.password or getpass.getpass('密码: ')
        if not client.login(user, password):
            print('登录失败：用户名或密码错误', file=sys.stderr)
            sys.exit(1)
        config['url'] = url
        config['cookies'] = client.get_cookies()
        save_config(config)
    return client


# ── instance commands ─────────────────────────────────────────────────────────

def cmd_instance_list(client, args):
    instances = client.list_instances()
    if args.env:
        instances = [i for i in instances if i.get('env') == args.env]
    if args.type:
        instances = [i for i in instances if i.get('db_type') == args.type]
    if not instances:
        print('(无实例)')
        return
    columns = list(instances[0].keys())
    rows = [[str(inst.get(c, '')) for c in columns] for inst in instances]
    print(format_table(columns, rows))


def cmd_instance_get(client, args):
    instances = client.list_instances()
    found = [i for i in instances if str(i.get('id')) == str(args.id)]
    if not found:
        print(f'实例 {args.id} 不存在', file=sys.stderr)
        sys.exit(1)
    inst = found[0]
    for k, v in inst.items():
        print(f'{k}: {v}')


def cmd_instance_add(client, args):
    ip = args.ip or input('IP: ')
    port = args.port or input('Port: ')
    db_type = args.db_type or input('DB Type (mysql/tidb/postgresql/redis/mongodb): ')
    env = args.env or input('Env (prod/test/dev): ')
    inst = client.create_instance(
        ip=ip, port=port, db_type=db_type, env=env,
        remark=args.remark,
        auth_username=args.auth_username,
        auth_password=args.auth_password,
        auth_source=args.auth_source,
    )
    print(f'创建成功，实例 ID: {inst["id"]}')


def cmd_instance_delete(client, args):
    client.delete_instance(args.id)
    print(f'已删除实例 {args.id}')


# ── main ──────────────────────────────────────────────────────────────────────

def main(argv=None):
    args = parse_args(argv)
    if not args.command:
        parse_args(['--help'])
        return

    config = load_config()

    if args.command == 'instance':
        try:
            client = _build_api_client(args, config)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            print('错误：无法连接到 dbquery 服务。实例管理不支持直连模式。', file=sys.stderr)
            sys.exit(1)

        cmd = args.instance_cmd
        if cmd == 'list':
            cmd_instance_list(client, args)
        elif cmd == 'get':
            cmd_instance_get(client, args)
        elif cmd == 'add':
            cmd_instance_add(client, args)
        elif cmd == 'delete':
            cmd_instance_delete(client, args)
        else:
            print('请指定子命令: list / get / add / delete', file=sys.stderr)
            sys.exit(1)

    elif args.command == 'query':
        # handled in Task 5
        print('query 命令尚未实现', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
