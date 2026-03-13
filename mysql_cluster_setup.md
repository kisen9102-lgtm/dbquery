# MySQL 一主一从集群搭建记录

创建时间：2026-03-12

---

## 集群信息

| 角色 | 容器名 | 宿主机端口 | 容器内端口 | server-id | 网络 |
|------|--------|-----------|-----------|-----------|------|
| 主库 | mysql-master | 4003 | 3306 | 1 | mysql-cluster |
| 从库 | mysql-slave  | 4004 | 3306 | 2 | mysql-cluster |

| 账号 | 密码 | 用途 |
|------|------|------|
| root | Root@2026 | 容器 root 管理账号 |
| repl | Repl@2026 | 主从复制专用账号 |
| dbs_admin | Dbs@Admin2026 | DBS 平台管理账号 |
| dbs_query  | Dbs@Query2026  | DBS 平台只读账号 |

- 复制模式：GTID + ROW format
- 从库只读：`read-only=ON`
- MySQL 版本：8.0
- Docker 镜像：mysql:8.0

---

## 搭建步骤

### 1. 创建 Docker 网络

```bash
docker network create mysql-cluster
```

### 2. 启动主库容器

```bash
docker run -d \
  --name mysql-master \
  --network mysql-cluster \
  -p 4003:3306 \
  -e MYSQL_ROOT_PASSWORD=Root@2026 \
  --restart unless-stopped \
  mysql:8.0 \
  --server-id=1 \
  --log-bin=mysql-bin \
  --binlog-format=ROW \
  --gtid-mode=ON \
  --enforce-gtid-consistency=ON \
  --character-set-server=utf8mb4 \
  --collation-server=utf8mb4_unicode_ci
```

### 3. 启动从库容器

```bash
docker run -d \
  --name mysql-slave \
  --network mysql-cluster \
  -p 4004:3306 \
  -e MYSQL_ROOT_PASSWORD=Root@2026 \
  --restart unless-stopped \
  mysql:8.0 \
  --server-id=2 \
  --log-bin=mysql-bin \
  --binlog-format=ROW \
  --gtid-mode=ON \
  --enforce-gtid-consistency=ON \
  --relay-log=relay-bin \
  --read-only=ON \
  --character-set-server=utf8mb4 \
  --collation-server=utf8mb4_unicode_ci
```

### 4. 主库初始化（等容器就绪后执行）

```bash
docker exec mysql-master mysql -uroot -pRoot@2026 -e "
-- 创建复制账号
CREATE USER 'repl'@'%' IDENTIFIED WITH mysql_native_password BY 'Repl@2026';
GRANT REPLICATION SLAVE ON *.* TO 'repl'@'%';
FLUSH PRIVILEGES;
"
```

### 5. 配置从库复制

```bash
docker exec mysql-slave mysql -uroot -pRoot@2026 -e "
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST='mysql-master',
  SOURCE_PORT=3306,
  SOURCE_USER='repl',
  SOURCE_PASSWORD='Repl@2026',
  SOURCE_AUTO_POSITION=1;
START REPLICA;
"
```

### 6. 创建 DBS 平台账号（主库和从库各执行一次）

```bash
for node in mysql-master mysql-slave; do
  docker exec \$node mysql -uroot -pRoot@2026 -e "
    CREATE USER IF NOT EXISTS 'dbs_admin'@'%' IDENTIFIED WITH mysql_native_password BY 'Dbs@Admin2026';
    GRANT SELECT,INSERT,UPDATE,DELETE,CREATE,DROP,INDEX,ALTER,
          CREATE VIEW,SHOW VIEW,CREATE ROUTINE,ALTER ROUTINE,
          EXECUTE,REFERENCES,TRIGGER,LOCK TABLES ON *.* TO 'dbs_admin'@'%';
    CREATE USER IF NOT EXISTS 'dbs_query'@'%' IDENTIFIED WITH mysql_native_password BY 'Dbs@Query2026';
    GRANT SELECT,SHOW VIEW ON *.* TO 'dbs_query'@'%';
    FLUSH PRIVILEGES;
  "
done
```

---

## 验证命令

### 查看复制状态

```bash
docker exec mysql-slave mysql -uroot -pRoot@2026 -e "SHOW REPLICA STATUS\G" | \
  grep -E "Replica_IO_Running|Replica_SQL_Running|Last_Error|Seconds_Behind"
```

正常输出：
```
Replica_IO_Running: Yes
Replica_SQL_Running: Yes
Last_Error:
Seconds_Behind_Source: 0
```

### 测试数据同步

```bash
# 主库写入
docker exec mysql-master mysql -uroot -pRoot@2026 \
  -e "INSERT INTO demo_cluster.orders (item,qty) VALUES ('Test',1);"

# 从库查询（1秒后）
docker exec mysql-slave mysql -uroot -pRoot@2026 \
  -e "SELECT * FROM demo_cluster.orders ORDER BY id DESC LIMIT 1;"
```

---

## 常用管理命令

```bash
# 查看容器状态
docker ps --filter name=mysql-master --filter name=mysql-slave

# 停止集群
docker stop mysql-master mysql-slave

# 启动集群
docker start mysql-master mysql-slave

# 查看主库 binlog 状态
docker exec mysql-master mysql -uroot -pRoot@2026 -e "SHOW MASTER STATUS\G"

# 暂停/恢复复制
docker exec mysql-slave mysql -uroot -pRoot@2026 -e "STOP REPLICA;"
docker exec mysql-slave mysql -uroot -pRoot@2026 -e "START REPLICA;"
```

---

## 注意事项

1. `--binlog-do-db` 参数**不要**传空字符串，否则会导致 DML 语句不写入 binlog
2. 从库设置了 `read-only=ON`，root 账号不受限制，业务账号无法在从库写入
3. 容器重启后主从复制会自动恢复（`--restart unless-stopped`）
4. 从库的 dbs_admin/dbs_query 账号需单独创建，不会通过复制同步（用户创建发生在复制建立之前）
