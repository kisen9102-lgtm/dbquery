# dbs_online v2 — MySQL 数据库运维自动化平台

基于原 `dbs_online` 项目重构，升级技术栈并修复全部安全隐患。

---

## 新技术栈

| 组件 | 旧版 | 新版 |
|------|------|------|
| Python | 2.7 | 3.x |
| Django | 1.8 | 4.2 LTS |
| API 框架 | 原生 HttpResponse | Django REST Framework |
| HTTP 客户端 | `urllib2` | `requests` |
| 配置管理 | 硬编码凭证 | `python-decouple` + `.env` |

---

## 安全修复

| 问题 | 修复方式 |
|------|------|
| CSRF 中间件被禁用 | DRF 纯 API 服务，不依赖 Session/CSRF；IP 白名单作为统一鉴权层 |
| SQL 注入（字符串拼接） | **全面参数化查询**（`cursor.execute(sql, (params,))`），消除所有字符串拼接 SQL |
| 凭证硬编码 | 所有密码/密钥移至 `.env` 文件，通过环境变量读取，不再出现在代码中 |
| `ALLOWED_HOSTS = ['*']` | 改为从环境变量配置具体主机名 |
| Shell 注入 | `my.cnf` 通过 SFTP 上传临时文件写入，SQL 初始化同样走临时文件，避免 `echo` 直接写入 |
| `dbbaseinfo` 动态字段注入 | 对 `queryList` / `otherParams` 中的字段名增加白名单正则校验（`^[A-Za-z0-9_]+$`） |

---

## 架构改进

- **`common/` 模块**：集中管理配置 (`config.py`)、数据库连接池 (`db_util.py`)、IP 白名单权限类 (`permissions.py`)，消除原项目中各 app 重复的 `config_para.py` / `db_util.py`
- **IP 白名单**：统一实现为 DRF `Permission` 类 (`IPWhitelistPermission`)，从各 view 中消除重复检查代码
- **Python 2 语法全面升级**：`unicode()` → `str()`，`has_key()` → `in`，`print` 语句 → `logger`，`thread` 模块 → `threading`，`urllib2` → `requests`

---

## 目录结构

```
dbs_online_v2/
├── .env.example             # 配置模板，复制为 .env 后填写真实值
├── requirements.txt         # Python 依赖
├── manage.py
├── logs/                    # 运行日志目录
├── dbs_online/              # Django 项目配置
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── common/                  # 公共模块（新增）
│   ├── config.py            # 全局配置，从环境变量读取
│   ├── db_util.py           # 数据库连接池与 context manager
│   └── permissions.py       # IP 白名单 DRF 权限类
├── instances/               # MySQL 实例安装与扩容
│   ├── views.py
│   ├── installer.py         # 集群安装线程
│   ├── expansion.py         # 集群扩容线程
│   ├── check_env.py         # 安装前环境检查
│   ├── install_remote.py    # SSH 远程安装操作
│   ├── add_host_to_zabbix_jmms.py  # Zabbix 注册
│   ├── scp_ssh.py           # Xtrabackup 扩容脚本
│   └── my_cnf.py            # MySQL 配置文件模板
├── clusters/                # 集群拓扑查询与构建
│   ├── views.py
│   ├── query_arch.py        # 拓扑查询（递归追溯主从）
│   └── build_arch.py        # 主从架构构建
├── databases/               # 数据库列表查询
├── grants/                  # MySQL 权限批量授予
├── dbs_dns/                 # 域名/IP 查询
└── dbbaseinfo/              # 数据库基本信息查询
```

---

## API 端点

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/instances/install/` | 自动化安装 MySQL 集群 |
| POST | `/instances/expand_capacity/` | 集群容量扩展 |
| GET  | `/clusters/query_arch/` | 查询集群主从拓扑 |
| POST | `/clusters/build_cluster/` | 构建主从架构 |
| GET  | `/master_slave_arch/query_arch/` | 同上（别名） |
| POST | `/master_slave_arch/build_cluster/` | 同上（别名） |
| GET  | `/databases/` | 查询数据库列表 |
| GET  | `/db_names/` | 同上（别名） |
| POST | `/grants/` | 批量授予 MySQL 权限 |
| GET  | `/dbs_dns/get_domains_by_ip/` | 根据 IP 查询域名 |
| GET  | `/dbs_dns/get_ip_by_domain/` | 根据域名查询 IP |
| POST | `/dbbaseinfo/` | 查询数据库基本信息 |

---

## 快速启动

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填写数据库连接信息、密码、允许访问的 IP 等
```

`.env` 关键配置项：

```ini
SECRET_KEY=your-secret-key-here          # Django 密钥，务必修改
DEBUG=False
ALLOWED_HOSTS=127.0.0.1,your-server-ip

DBS_DB_HOST=localhost                    # 运维数据库地址
DBS_DB_PORT=3306
DBS_DB_USER=ops_user
DBS_DB_PASSWORD=your-db-password

ALLOW_ACCESS_IPS=127.0.0.1,172.20.133.53  # 允许访问的 IP 白名单

DEFAULT_SSH_PASSWORDS=password1,password2  # 新机器 SSH 初始密码列表

NOTIFY_URL=http://your-system/finish_db_install
DNS_API_URL=http://your-dnsapi/dns/lan/getdomain
ZABBIX_API_URL=http://your-zabbix/api_jsonrpc.php
ZABBIX_USER=monitor
ZABBIX_PASSWORD=your-zabbix-password

ONLINE_ENV=True
```

### 3. 初始化 & 启动

```bash
# 创建日志目录（首次运行）
mkdir -p logs

# 开发环境
python manage.py runserver 0.0.0.0:8000

# 生产环境（推荐 gunicorn）
gunicorn dbs_online.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

---

## 与旧版主要差异对照

| 旧版问题 | 新版修复 |
|---------|---------|
| `thread.start_new_thread(...)` | `threading.Thread(..., daemon=True).start()` |
| `urllib2.urlopen(...)` | `requests.post/get(...)` |
| `unicode(e)` | `str(e)` |
| `dict.has_key(k)` | `k in dict` |
| `print` 语句 | `logger.info/error(...)` |
| `WHERE server_group='%s' % val` | `WHERE server_group = %s`, `(val,)` |
| 各 app 独立 `config_para.py` + `db_util.py` | 统一 `common/` 模块 |
| IP 白名单分散在各 view | 统一 `IPWhitelistPermission` 类 |
| `my.cnf` 通过 `echo "..." > file` 写入 | SFTP 上传临时文件，避免 shell 注入 |
