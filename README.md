# dbquery · DBS 数据查询平台

[中文](#中文说明) | [English](#english)

---

## 中文说明

基于 Django 4.2 + Django REST Framework 构建的 MySQL 数据库运维查询平台，提供跨实例数据库查询、在线 SQL 编辑器、集群拓扑查询、用户与权限管理等功能，界面支持中文 / 英文切换。

### 功能概览

| 模块 | 功能 |
|------|------|
| 数据库查询 | 按数据库名或 IP+端口跨实例检索数据库信息 |
| SQL 查询 | 在线 SQL 编辑器，支持多语句执行、对象浏览器、结果导出 |
| 实例管理 | 注册 / 编辑 / 删除 MySQL 实例（admin / root 可操作） |
| 集群拓扑查询 | 查询指定节点的主从角色与复制状态 |
| 用户管理 | 创建 / 编辑用户，支持三种角色（root / admin / query） |
| 用户组管理 | 管理实例访问权限组，控制 query 用户可见的实例范围 |
| 多语言 | 界面支持中文 / English 切换，偏好持久化到浏览器本地存储 |

### 角色权限

| 角色 | 说明 |
|------|------|
| `root` | 全部权限，不受任何限制 |
| `admin` | 可管理实例、用户、用户组；不可修改 root 账号 |
| `query` | 只能执行只读 SQL；只能看到所属用户组内的实例；禁止查询系统库 |

### 技术栈

- **后端**：Python 3.10+、Django 4.2、Django REST Framework
- **数据库**：MySQL 8.0（业务数据库）+ SQLite（Django 框架元数据）
- **前端**：Bootstrap 5.3、Bootstrap Icons、CodeMirror 5（单页应用，无需构建）
- **认证**：Session 认证 + CSRF 保护

### 目录结构

```
.
├── accounts/        # 用户认证、角色、用户组管理
├── clusters/        # 集群拓扑角色查询
├── common/          # 配置、数据库连接工具
├── databases/       # 数据库 / 实例查询与 SQL 执行
├── dbquery/         # Django 项目配置、路由
├── templates/       # 前端页面（index.html、sql_editor.html、登录页）
├── ui/              # 前端视图入口
├── init_db.sql      # ops_db 初始化 SQL
├── requirements.txt # Python 依赖
└── restart.sh       # 快速重启脚本
```

### 快速部署

**1. 安装依赖**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**2. 配置环境变量**

```bash
cp .env.example .env
# 编辑 .env，填写数据库连接信息
```

`.env` 关键配置项：

```ini
DBS_DB_HOST=localhost
DBS_DB_PORT=3306
DBS_DB_USER=ops_user
DBS_DB_PASSWORD=your-password
DBS_DB_NAME=ops_db

QUERY_DEFAULT_ACCOUNT=dbs_admin
QUERY_DEFAULT_PASSWORD=your-dbs-admin-password
```

**3. 初始化数据库**

```bash
# 在目标 MySQL 执行建表 SQL
mysql -u root -p ops_db < init_db.sql

# Django 迁移（创建用户认证相关表）
python3 manage.py migrate
```

**4. 创建超级管理员**

```bash
python3 manage.py create_dbsroot
# 默认账号：dbsroot / Dbs@Root2026
```

**5. 在目标 MySQL 实例上创建查询账号**

```sql
CREATE USER 'dbs_admin'@'%' IDENTIFIED BY 'your-password';
GRANT SELECT, SHOW DATABASES, REPLICATION CLIENT, PROCESS ON *.* TO 'dbs_admin'@'%';
FLUSH PRIVILEGES;
```

**6. 启动服务**

```bash
bash restart.sh
# 或
python3 manage.py runserver 0.0.0.0:8000
```

访问 `http://localhost:8000`

### 注意事项

- `.env` 含敏感信息，已加入 `.gitignore`，**请勿提交**
- 生产环境请将 `DEBUG=False`，并配置 `ALLOWED_HOSTS`
- `SECRET_KEY` 生产环境必须替换为随机字符串
- 当前使用 Django `runserver`，生产建议改用 `gunicorn` + `nginx`

---

## English

A MySQL database operations and query platform built with Django 4.2 + Django REST Framework. Features cross-instance database search, an online SQL editor, cluster topology inspection, and user/permission management. The UI supports Chinese / English language switching.

### Features

| Module | Description |
|--------|-------------|
| DB Search | Search databases by name or IP+port across all registered instances |
| SQL Query | Online SQL editor with multi-statement execution, object browser, and CSV export |
| Instance Management | Register / edit / delete MySQL instances (admin / root only) |
| Cluster Topology | Query master/slave role and replication status for any node |
| User Management | Create / edit users with three roles: root / admin / query |
| Group Management | Manage instance access groups to control which instances query users can see |
| i18n | UI language switches between Chinese and English; preference saved in localStorage |

### Roles & Permissions

| Role | Description |
|------|-------------|
| `root` | Full access, no restrictions |
| `admin` | Manage instances, users, and groups; cannot modify root account |
| `query` | Read-only SQL only; can only see instances in their assigned groups; system databases are blocked |

### Tech Stack

- **Backend**: Python 3.10+, Django 4.2, Django REST Framework
- **Database**: MySQL 8.0 (business data) + SQLite (Django metadata)
- **Frontend**: Bootstrap 5.3, Bootstrap Icons, CodeMirror 5 (SPA, no build step)
- **Auth**: Session authentication + CSRF protection

### Project Structure

```
.
├── accounts/        # Auth, roles, user group management
├── clusters/        # Cluster topology query
├── common/          # Config and DB connection utilities
├── databases/       # Database / instance query and SQL execution
├── dbquery/         # Django project settings and routing
├── templates/       # Frontend pages (index.html, sql_editor.html, login)
├── ui/              # Frontend view entry points
├── init_db.sql      # ops_db initialization SQL
├── requirements.txt # Python dependencies
└── restart.sh       # Quick restart script
```

### Quick Start

**1. Install dependencies**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**2. Configure environment**

```bash
cp .env.example .env
# Edit .env with your database credentials
```

Key `.env` settings:

```ini
DBS_DB_HOST=localhost
DBS_DB_PORT=3306
DBS_DB_USER=ops_user
DBS_DB_PASSWORD=your-password
DBS_DB_NAME=ops_db

QUERY_DEFAULT_ACCOUNT=dbs_admin
QUERY_DEFAULT_PASSWORD=your-dbs-admin-password
```

**3. Initialize the database**

```bash
# Run the init SQL on your MySQL server
mysql -u root -p ops_db < init_db.sql

# Run Django migrations
python3 manage.py migrate
```

**4. Create the superuser**

```bash
python3 manage.py create_dbsroot
# Default credentials: dbsroot / Dbs@Root2026
```

**5. Create the query account on each MySQL instance**

```sql
CREATE USER 'dbs_admin'@'%' IDENTIFIED BY 'your-password';
GRANT SELECT, SHOW DATABASES, REPLICATION CLIENT, PROCESS ON *.* TO 'dbs_admin'@'%';
FLUSH PRIVILEGES;
```

**6. Start the server**

```bash
bash restart.sh
# or
python3 manage.py runserver 0.0.0.0:8000
```

Open `http://localhost:8000`

### Notes

- `.env` contains sensitive credentials and is listed in `.gitignore` — **do not commit it**
- Set `DEBUG=False` and configure `ALLOWED_HOSTS` for production
- Replace `SECRET_KEY` with a random string in production
- The default server is Django `runserver`; use `gunicorn` + `nginx` for production
