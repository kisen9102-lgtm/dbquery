# dbquery · DBS 数据查询平台

[中文](#中文说明) | [English](#english)

## SQL 查询
<img width="1191" height="525" alt="image" src="https://github.com/user-attachments/assets/696a119b-be2a-40cb-a382-faa185b3d836" />

## redis查询
<img width="1192" height="453" alt="image" src="https://github.com/user-attachments/assets/b59df4c5-b3f3-4a93-85e9-2713d1d8e437" />
<img width="1188" height="367" alt="image" src="https://github.com/user-attachments/assets/59d0d0c3-91f3-4ff0-b0a3-f83f19836da1" />

## mongodb 查询
<img width="1191" height="410" alt="image" src="https://github.com/user-attachments/assets/c2547111-88ed-49cb-a19c-edbb23e3c4f2" />
<img width="1185" height="391" alt="image" src="https://github.com/user-attachments/assets/d5ae03a7-498c-4fd0-828e-a806542bcbd4" />




## 实例管理
<img width="1280" height="510" alt="image" src="https://github.com/user-attachments/assets/01ca6578-3c7d-4ab0-80ad-a3fe62be2f62" />

## 用户管理
<img width="1280" height="514" alt="image" src="https://github.com/user-attachments/assets/241056ab-9b16-4ec9-bb19-723806ce122a" />



---

## 中文说明

基于 Django 4.2 + Django REST Framework 构建的数据库运维查询平台，支持 MySQL、TiDB 和 PostgreSQL，提供跨实例数据库查询、在线 SQL 编辑器、集群拓扑查询、用户与权限管理等功能，界面支持中文 / 英文切换。

### 功能概览

| 模块 | 功能 |
|------|------|
| 数据库查询 | 按数据库名或 IP+端口跨实例检索数据库信息 |
| SQL 查询 | 在线 SQL 编辑器，支持多语句执行、对象浏览器、结果导出 |
| 实例管理 | 注册 / 编辑 / 删除 MySQL / TiDB / PostgreSQL / Redis / MongoDB 实例（admin / root 可操作） |
| 集群拓扑查询 | 查询指定节点的主从角色与复制状态 |
| 用户管理 | 创建 / 编辑用户，支持三种角色（root / admin / query） |
| 用户组管理 | 管理实例访问权限组，控制 query 用户可见的实例范围 |
| 多语言 | 界面支持中文 / English 切换，偏好持久化到浏览器本地存储 |

### 支持的数据库类型

| 类型 | 说明 |
|------|------|
| MySQL 8.0 | 完整支持 |
| TiDB | 兼容 MySQL 协议，完整支持 |
| PostgreSQL 14+ | 支持多 Schema，数据库选择器显示 `dbname_schema` 格式 |
| Redis 7+ | 只读命令白名单（GET/KEYS/HGETALL 等），固定 db0–db15 |
| MongoDB 6+ | 支持 find/count_documents/aggregate，每实例独立凭据 |

### 角色权限

| 角色 | 说明 |
|------|------|
| `root` | 全部权限，不受任何限制 |
| `admin` | 可管理实例、用户、用户组；不可修改 root 账号 |
| `query` | 只能执行只读 SQL；只能看到所属用户组内的实例；**不可见实例 IP/端口**；禁止查询系统库 |

### 技术栈

- **后端**：Python 3.10+、Django 4.2、Django REST Framework
- **元数据库**：外部 MySQL 8.0（由用户自行提供）
- **前端**：Bootstrap 5.3、Bootstrap Icons、CodeMirror 5（单页应用，无需构建）
- **认证**：Session 认证 + CSRF 保护
- **数据库驱动**：pymysql（MySQL/TiDB）、psycopg2-binary（PostgreSQL）、redis-py（Redis）、pymongo（MongoDB）

### 目录结构

```
.
├── accounts/             # 用户认证、角色、用户组管理
├── clusters/             # 集群拓扑角色查询
├── common/               # 连接器抽象层（BaseConnector / MySQLConnector / PostgreSQLConnector）
├── databases/            # 数据库 / 实例查询与 SQL 执行
├── dbquery/              # Django 项目配置、路由
├── templates/            # 前端页面（index.html、sql_editor.html、登录页）
├── ui/                   # 前端视图入口
├── Dockerfile            # 镜像构建（multi-stage）
├── docker-compose.yml    # 一键启动编排
├── docker-entrypoint.sh  # 容器启动脚本（migrate + gunicorn）
├── .env.docker.example   # Docker 环境变量模板
└── requirements.txt      # Python 依赖
```

### 部署方式一：Docker Compose（推荐）

> **前提**：需要一个外部 MySQL 8.0 实例作为平台元数据库（存储实例信息、用户等）。

**1. 准备外部 MySQL**

在 MySQL 上创建数据库和用户：

```sql
CREATE DATABASE ops_db CHARACTER SET utf8mb4;
CREATE USER 'ops_user'@'%' IDENTIFIED BY 'your-password';
GRANT ALL PRIVILEGES ON ops_db.* TO 'ops_user'@'%';
FLUSH PRIVILEGES;
```

> 若 MySQL 在同一宿主机，需将 `bind-address` 改为 `0.0.0.0` 并重启 MySQL。

**2. 准备环境变量**

```bash
cp .env.docker.example .env
# 按需修改 .env 中的密码和配置项
```

`.env` 关键配置项：

```ini
# 外部 MySQL（Docker 部署时宿主机 MySQL 填 host.docker.internal）
DBS_DB_HOST=host.docker.internal
DBS_DB_PORT=3306
DBS_DB_USER=ops_user
DBS_DB_PASSWORD=your-ops-password
DBS_DB_NAME=ops_db

# 被查询的目标 MySQL / TiDB 实例登录账号
QUERY_DEFAULT_ACCOUNT=dbs_admin
QUERY_DEFAULT_PASSWORD=your-dbs-admin-password

SECRET_KEY=your-secret-key
DEBUG=False
ALLOWED_HOSTS=*
```

**3. 启动服务**

方式 A：直接拉取预构建镜像（推荐，无需本地编译）

```bash
# 修改 docker-compose.yml，将 build: . 替换为：
# image: ghcr.io/kisen9102-lgtm/dbquery:1.1
docker-compose up -d
```

方式 B：从源码本地构建

```bash
docker-compose up -d --build
```

首次启动时容器会自动完成：
- 等待 MySQL 就绪
- 执行 `migrate`
- 创建超级管理员（`dbsroot / Dbs@Root2026`）
- 使用 gunicorn 启动服务（4 workers）

**4. 访问**

```
http://localhost:8000
```

**常用命令**

```bash
# 查看日志
docker-compose logs -f app

# 停止服务
docker-compose down

# 重新构建镜像
docker-compose up -d --build
```

> **注意**：`docker-compose.override.yml` 仅用于本地开发测试，包含以下测试数据库容器，服务本身不需要它们。
> 生产部署时，指定只使用主配置文件以避免启动这些容器：
>
> ```bash
> docker-compose -f docker-compose.yml up -d
> ```
>
> 测试容器账号一览：
>
> | 容器 | 端口 | 账号 | 密码 |
> |------|------|------|------|
> | mysql-test | 13306 | root | root123 |
> | mysql-test | 13306 | dbs_admin | Dbs@Admin2026 |
> | tidb-test | 14000 | root | root123 |
> | tidb-test | 14000 | dbs_admin | Dbs@Admin2026 |
> | postgres-test | 15432 | dbs_admin | Dbs@Admin2026 |
> | redis-test | 16379 | — | 无密码 |
> | mongo-test | 27117 | dbs_admin | Dbs@Admin2026 |

---

### 部署方式二：本地运行

**1. 安装依赖**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**2. 配置环境变量**

```bash
cp .env.docker.example .env
# 编辑 .env，填写数据库连接信息
```

**3. 初始化数据库**

```bash
python3 manage.py migrate
python3 manage.py create_dbsroot
# 默认账号：dbsroot / Dbs@Root2026
```

**4. 在目标实例上创建查询账号**

MySQL / TiDB：

```sql
CREATE USER 'dbs_admin'@'%' IDENTIFIED BY 'your-password';
GRANT SELECT, SHOW DATABASES, REPLICATION CLIENT, PROCESS ON *.* TO 'dbs_admin'@'%';
FLUSH PRIVILEGES;
```

PostgreSQL：

```sql
CREATE USER dbs_admin WITH PASSWORD 'your-password';
GRANT CONNECT ON DATABASE your_db TO dbs_admin;
GRANT USAGE ON SCHEMA public TO dbs_admin;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO dbs_admin;
-- 如有多个 schema，对每个 schema 重复 GRANT USAGE / SELECT
```

Redis（可选，无密码时留空）：

```bash
# 如需密码认证（Redis 6+ ACL）：
ACL SETUSER dbs_admin on >your-password ~* &* +@read
```

MongoDB：

```javascript
db.createUser({
  user: "dbs_admin",
  pwd: "your-password",
  roles: [{ role: "read", db: "your_db" }]
})
```

**5. 启动服务**

```bash
python3 manage.py runserver 0.0.0.0:8000
```

访问 `http://localhost:8000`

### CLI 工具（dbcli）

`cli/` 目录提供了一个命令行工具，可通过 API 管理实例，无需打开浏览器。

**使用方式**

在项目根目录下执行：

```bash
python3 -m cli.dbcli [全局选项] <命令> [子命令] [参数]
```

首次使用时会提示输入用户名和密码，登录态保存在 `~/.dbcli.json`，后续无需重复登录。

**全局选项**

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--url` | dbquery 服务地址 | `http://127.0.0.1:8000` |
| `--user` | 登录用户名 | 交互输入 |
| `--password` | 登录密码 | 交互输入 |

**instance 命令**

```bash
# 列出所有实例
python3 -m cli.dbcli instance list

# 按环境或类型过滤
python3 -m cli.dbcli instance list --env prod
python3 -m cli.dbcli instance list --type mysql

# 查看实例详情
python3 -m cli.dbcli instance get <id>

# 新增实例（交互式，或通过参数指定）
python3 -m cli.dbcli instance add
python3 -m cli.dbcli instance add --ip 10.0.0.1 --port 3306 --db-type mysql --env prod

# 删除实例
python3 -m cli.dbcli instance delete <id>
```

---

### 注意事项

- `.env` 含敏感信息，已加入 `.gitignore`，**请勿提交**
- 生产环境请将 `DEBUG=False`，并配置 `ALLOWED_HOSTS`
- `SECRET_KEY` 生产环境必须替换为随机字符串
- Docker 部署已使用 gunicorn（4 workers），如需 nginx 反代可在 docker-compose 中扩展

---

## English

A database operations and query platform built with Django 4.2 + Django REST Framework. Supports MySQL, TiDB, and PostgreSQL with cross-instance database search, an online SQL editor, cluster topology inspection, and user/permission management. The UI supports Chinese / English language switching.

### Features

| Module | Description |
|--------|-------------|
| DB Search | Search databases by name or IP+port across all registered instances |
| SQL Query | Online SQL editor with multi-statement execution, object browser, and CSV export |
| Instance Management | Register / edit / delete MySQL / TiDB / PostgreSQL / Redis / MongoDB instances (admin / root only) |
| Cluster Topology | Query master/slave role and replication status for any node |
| User Management | Create / edit users with three roles: root / admin / query |
| Group Management | Manage instance access groups to control which instances query users can see |
| i18n | UI language switches between Chinese and English; preference saved in localStorage |

### Supported Database Types

| Type | Notes |
|------|-------|
| MySQL 8.0 | Fully supported |
| TiDB | MySQL-protocol compatible, fully supported |
| PostgreSQL 14+ | Multi-schema support; DB selector uses `dbname_schema` format |
| Redis 7+ | Read-only command whitelist (GET/KEYS/HGETALL etc.), fixed db0–db15 |
| MongoDB 6+ | Supports find/count_documents/aggregate; per-instance credentials |

### Roles & Permissions

| Role | Description |
|------|-------------|
| `root` | Full access, no restrictions |
| `admin` | Manage instances, users, and groups; cannot modify root account |
| `query` | Read-only SQL only; can only see instances in their assigned groups; **instance IP/port hidden**; system databases are blocked |

### Tech Stack

- **Backend**: Python 3.10+, Django 4.2, Django REST Framework
- **Metadata DB**: External MySQL 8.0 (user-provided)
- **Frontend**: Bootstrap 5.3, Bootstrap Icons, CodeMirror 5 (SPA, no build step)
- **Auth**: Session authentication + CSRF protection
- **DB Drivers**: pymysql (MySQL/TiDB), psycopg2-binary (PostgreSQL), redis-py (Redis), pymongo (MongoDB)

### Project Structure

```
.
├── accounts/             # Auth, roles, user group management
├── clusters/             # Cluster topology query
├── common/               # Connector abstraction layer (BaseConnector / MySQLConnector / PostgreSQLConnector)
├── databases/            # Database / instance query and SQL execution
├── dbquery/              # Django project settings and routing
├── templates/            # Frontend pages (index.html, sql_editor.html, login)
├── ui/                   # Frontend view entry points
├── Dockerfile            # Multi-stage image build
├── docker-compose.yml    # One-command orchestration
├── docker-entrypoint.sh  # Container startup (migrate + gunicorn)
├── .env.docker.example   # Docker environment template
└── requirements.txt      # Python dependencies
```

### Option 1: Docker Compose (Recommended)

> **Prerequisite**: An external MySQL 8.0 instance is required as the platform metadata database.

**1. Prepare external MySQL**

```sql
CREATE DATABASE ops_db CHARACTER SET utf8mb4;
CREATE USER 'ops_user'@'%' IDENTIFIED BY 'your-password';
GRANT ALL PRIVILEGES ON ops_db.* TO 'ops_user'@'%';
FLUSH PRIVILEGES;
```

> If MySQL is on the same host, set `bind-address = 0.0.0.0` in `mysqld.cnf` and restart MySQL.

**2. Prepare environment variables**

```bash
cp .env.docker.example .env
# Edit .env to set passwords and other config
```

Key `.env` settings:

```ini
# External MySQL (use host.docker.internal if MySQL is on the same host)
DBS_DB_HOST=host.docker.internal
DBS_DB_PORT=3306
DBS_DB_USER=ops_user
DBS_DB_PASSWORD=your-ops-password
DBS_DB_NAME=ops_db

# Credentials used to connect to the target MySQL / TiDB instances being queried
QUERY_DEFAULT_ACCOUNT=dbs_admin
QUERY_DEFAULT_PASSWORD=your-dbs-admin-password

SECRET_KEY=your-secret-key
DEBUG=False
ALLOWED_HOSTS=*
```

**3. Start services**

Option A: Pull the pre-built image (recommended, no local build required)

```bash
# In docker-compose.yml, replace "build: ." with:
# image: ghcr.io/kisen9102-lgtm/dbquery:1.1
docker-compose up -d
```

Option B: Build from source

```bash
docker-compose up -d --build
```

On first start the container will automatically:
- Wait for MySQL to be ready
- Run `migrate`
- Create the superuser (`dbsroot / Dbs@Root2026`)
- Start gunicorn with 4 workers

**4. Open**

```
http://localhost:8000
```

**Useful commands**

```bash
# Follow logs
docker-compose logs -f app

# Stop services
docker-compose down

# Rebuild image
docker-compose up -d --build
```

> **Note**: `docker-compose.override.yml` is for local development only. It starts the following test database containers that the application itself does not require.
> For production, use only the main compose file to avoid starting these containers:
>
> ```bash
> docker-compose -f docker-compose.yml up -d
> ```
>
> Test container credentials:
>
> | Container | Port | User | Password |
> |-----------|------|------|----------|
> | mysql-test | 13306 | root | root123 |
> | mysql-test | 13306 | dbs_admin | Dbs@Admin2026 |
> | tidb-test | 14000 | root | root123 |
> | tidb-test | 14000 | dbs_admin | Dbs@Admin2026 |
> | postgres-test | 15432 | dbs_admin | Dbs@Admin2026 |
> | redis-test | 16379 | — | no password |
> | mongo-test | 27117 | dbs_admin | Dbs@Admin2026 |

---

### Option 2: Local Run

**1. Install dependencies**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**2. Configure environment**

```bash
cp .env.docker.example .env
# Edit .env with your database credentials
```

**3. Initialize the database**

```bash
python3 manage.py migrate
python3 manage.py create_dbsroot
# Default credentials: dbsroot / Dbs@Root2026
```

**4. Create the query account on each target instance**

MySQL / TiDB:

```sql
CREATE USER 'dbs_admin'@'%' IDENTIFIED BY 'your-password';
GRANT SELECT, SHOW DATABASES, REPLICATION CLIENT, PROCESS ON *.* TO 'dbs_admin'@'%';
FLUSH PRIVILEGES;
```

PostgreSQL:

```sql
CREATE USER dbs_admin WITH PASSWORD 'your-password';
GRANT CONNECT ON DATABASE your_db TO dbs_admin;
GRANT USAGE ON SCHEMA public TO dbs_admin;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO dbs_admin;
-- Repeat GRANT USAGE / SELECT for each additional schema
```

Redis (optional, leave password blank if no auth):

```bash
# For password authentication (Redis 6+ ACL):
ACL SETUSER dbs_admin on >your-password ~* &* +@read
```

MongoDB:

```javascript
db.createUser({
  user: "dbs_admin",
  pwd: "your-password",
  roles: [{ role: "read", db: "your_db" }]
})
```

**5. Start the server**

```bash
python3 manage.py runserver 0.0.0.0:8000
```

Open `http://localhost:8000`

### CLI Tool (dbcli)

The `cli/` directory provides a command-line tool for managing instances via the API without opening a browser.

**Usage**

Run from the project root:

```bash
python3 -m cli.dbcli [global options] <command> [subcommand] [args]
```

On first use you will be prompted for credentials. The session is saved to `~/.dbcli.json` so subsequent calls don't require re-login.

**Global options**

| Option | Description | Default |
|--------|-------------|---------|
| `--url` | dbquery service URL | `http://127.0.0.1:8000` |
| `--user` | Login username | prompted |
| `--password` | Login password | prompted |

**instance commands**

```bash
# List all instances
python3 -m cli.dbcli instance list

# Filter by environment or type
python3 -m cli.dbcli instance list --env prod
python3 -m cli.dbcli instance list --type mysql

# Show instance details
python3 -m cli.dbcli instance get <id>

# Add an instance (interactive, or pass flags directly)
python3 -m cli.dbcli instance add
python3 -m cli.dbcli instance add --ip 10.0.0.1 --port 3306 --db-type mysql --env prod

# Delete an instance
python3 -m cli.dbcli instance delete <id>
```

---

### Notes

- `.env` contains sensitive credentials and is listed in `.gitignore` — **do not commit it**
- Set `DEBUG=False` and configure `ALLOWED_HOSTS` for production
- Replace `SECRET_KEY` with a random string in production
- Docker deployments use gunicorn (4 workers); add an nginx service to docker-compose for reverse proxy if needed
