# dbs_online_v2 接口测试文档

> **Base URL**: `http://127.0.0.1:8000`
> **注意**: 带 🔒 的接口需 IP 白名单（当前仅 `127.0.0.1` 可访问），需在服务器本地执行 curl。

---

## 1. 数据库列表 `/databases/`

**方法**: GET | **鉴权**: 无（凭 MySQL 账号密码）

```bash
curl "http://127.0.0.1:8000/databases/?ip=127.0.0.1&port=3306&account=test&passwd=test"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| ip | 是 | MySQL 服务器 IP |
| port | 是 | MySQL 端口 |
| account | 是 | MySQL 账号 |
| passwd | 否 | MySQL 密码 |

**期望返回**:
```json
{"error": false, "message": "", "db_names": ["jmms", "ops_db"]}
```

---

## 2. 集群拓扑查询 `/clusters/query_arch/` 🔒

**方法**: GET

```bash
curl "http://127.0.0.1:8000/clusters/query_arch/?ip=127.0.0.1&port=3306&account=test&passwd=test"
```

| 参数 | 必填 | 说明 |
|------|------|------|
| ip | 是 | MySQL 实例 IP |
| port | 是 | 端口 |
| account | 是 | 账号 |
| passwd | 否 | 密码 |

**期望返回**:
```json
{"error": false, "message": "", "nodes": [...]}
```

---

## 3. 构建主从架构 `/clusters/build_cluster/` 🔒

**方法**: POST | **Content-Type**: application/json

```bash
curl -X POST "http://127.0.0.1:8000/clusters/build_cluster/" \
  -H "Content-Type: application/json" \
  -d '{
    "account_repl": "repl_user",
    "passwd_repl": "repl_pass",
    "account_build": "root",
    "passwd_build": "root123",
    "need_grant": true,
    "cluster_hosts": [
      {"ip": "192.168.1.10", "port": 3306, "role": "master"},
      {"ip": "192.168.1.11", "port": 3306, "role": "slave"}
    ]
  }'
```

| 参数 | 必填 | 说明 |
|------|------|------|
| account_repl | 是 | 复制账号 |
| passwd_repl | 是 | 复制密码 |
| account_build | 是 | 执行构建的账号 |
| passwd_build | 是 | 执行构建的密码 |
| cluster_hosts | 是 | 集群节点列表 |
| need_grant | 否 | 是否需要授权，默认 false |

---

## 4. DNS — IP 查域名 `/dbs_dns/get_domains_by_ip/`

**方法**: GET | **鉴权**: 无

```bash
curl "http://127.0.0.1:8000/dbs_dns/get_domains_by_ip/?ip=127.0.0.1"
```

**期望返回**:
```json
{"error": false, "message": "", "domains": ["xxx.jddb.com"]}
```

> 当前 DNS API（`dbs.jd.com`）未更新，会降级到数据库查询，jmms 库中无数据时返回空列表。

---

## 5. DNS — 域名查 IP `/dbs_dns/get_ip_by_domain/`

**方法**: GET | **鉴权**: 无

```bash
curl "http://127.0.0.1:8000/dbs_dns/get_ip_by_domain/?domain=www.baidu.com"
```

**期望返回**:
```json
{"error": false, "message": "", "ip": "110.242.68.66"}
```

---

## 6. 权限授予 `/grants/` 🔒

**方法**: POST | **Content-Type**: application/json

```bash
curl -X POST "http://127.0.0.1:8000/grants/" \
  -H "Content-Type: application/json" \
  -d '{
    "group1": [
      {
        "dbIp": "127.0.0.1",
        "dbPort": "3306",
        "dbName": "ops_db",
        "tbName": "*",
        "privilege": "SELECT",
        "username": "readonly_user",
        "iplist": "192.168.1.0/24",
        "erp": "admin"
      }
    ]
  }'
```

| 参数（每项） | 必填 | 说明 |
|------|------|------|
| dbIp | 是 | 目标数据库 IP |
| dbPort | 是 | 端口 |
| dbName | 是 | 数据库名 |
| tbName | 是 | 表名（`*` 表示所有表） |
| privilege | 是 | 权限（SELECT/INSERT/ALL 等） |
| username | 是 | 被授权用户名 |
| iplist | 是 | 允许访问的客户端 IP |
| erp | 是 | 申请人工号 |

> **注意**: grants 实际调用外部 API（`10.191.251.143`），当前环境无法访问会报错，这属于正常现象。

---

## 7. 数据库基础信息 `/dbbaseinfo/` 🔒

**方法**: POST | **Content-Type**: application/json

```bash
curl -X POST "http://127.0.0.1:8000/dbbaseinfo/" \
  -H "Content-Type: application/json" \
  -d '{
    "ip": "127.0.0.1",
    "port": 3306,
    "queryList": ["inst_ip", "inst_port", "db_version"],
    "otherParams": {}
  }'
```

| 参数 | 必填 | 说明 |
|------|------|------|
| ip | 是 | 实例 IP 或 `*.jddb.com` 域名 |
| port | 是 | 端口 |
| queryList | 是 | 要查询的字段列表（仅允许字母数字下划线） |
| otherParams | 否 | 额外过滤条件，如 `{"env": "prod"}` |

> **注意**: 查询 jmms 库的 `t_jbxx_view` 视图，当前库中无数据时返回空列表。

---

## 8. MySQL 安装 `/instances/install/` 🔒

**方法**: POST | **Content-Type**: application/json（后台异步执行，立即返回）

```bash
curl -X POST "http://127.0.0.1:8000/instances/install/" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "ORD20260312001",
    "mysql_version": "8.0",
    "server_group": "default",
    "passwd_ssh_root": "root_ssh_pass",
    "passwd_ssh_mysql": "mysql_ssh_pass",
    "account_visit": "app_user",
    "passwd_visit": "app_pass",
    "account_repl": "repl_user",
    "passwd_repl": "repl_pass",
    "passwd_mysql_backup": "backup_pass",
    "cluster_list": [
      [
        {"ip": "192.168.1.10", "port": 3306, "role": "master"},
        {"ip": "192.168.1.11", "port": 3306, "role": "slave"}
      ]
    ]
  }'
```

**期望返回**（立即）:
```json
{"error": false, "message": "ok"}
```

> 实际安装在后台线程执行，需依赖 jmms 库中有对应 `server_group` 的 Zabbix 配置。

---

## 9. 扩容 `/instances/expand_capacity/` 🔒

**方法**: POST | **Content-Type**: application/json

```bash
curl -X POST "http://127.0.0.1:8000/instances/expand_capacity/" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "ORD20260312001",
    "mysql_version": "8.0",
    "server_group": "default",
    "disk_type": "ssd",
    "task_ids": [1, 2],
    "passwd_ssh_root": "root_ssh_pass",
    "passwd_ssh_mysql": "mysql_ssh_pass",
    "account_visit": "app_user",
    "passwd_visit": "app_pass",
    "account_repl": "repl_user",
    "passwd_repl": "repl_pass",
    "account_backup": "backup_user",
    "passwd_backup": "backup_pass",
    "passwd_mysql_backup": "backup_pass"
  }'
```

**期望返回**（立即）:
```json
{"error": false, "message": "ok"}
```

> 实际扩容在后台线程执行，需依赖 jmms 库中有对应扩容任务记录。

---

## 当前可直接测试的接口（本地环境有效）

| 接口 | 状态 | 说明 |
|------|------|------|
| `GET /databases/` | ✅ 正常 | 可返回本地 MySQL 数据库列表 |
| `GET /clusters/query_arch/` | ✅ 正常 | 可连本地 MySQL 查拓扑 |
| `GET /dbs_dns/get_ip_by_domain/` | ✅ 正常 | 域名解析正常 |
| `GET /dbs_dns/get_domains_by_ip/` | ⚠️ 返回空 | DNS API 不通，jmms 库无数据 |
| `POST /dbbaseinfo/` | ⚠️ 返回空 | jmms 库中 t_jbxx_view 无数据 |
| `POST /grants/` | ⚠️ 报错 | 外部授权 API（10.191.251.143）不通 |
| `POST /instances/install/` | ⚠️ 报错 | 需 jmms 库中有 Zabbix server_group 配置 |
| `POST /clusters/build_cluster/` | ⚠️ 需真实节点 | 需可 SSH 访问的 MySQL 从库节点 |
