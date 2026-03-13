-- ============================================================
-- DBS Online v2 数据库初始化脚本
-- 执行账号：root  目标库：jmms / test
-- ============================================================

-- ══ 一、初始化 jmms 库 ══════════════════════════════════════

USE jmms;

-- ── 1. zabbix_server_group ────────────────────────────────
-- 服务器组与 Zabbix 群组映射，安装接口依赖此表获取 zbx_group_id
CREATE TABLE IF NOT EXISTS zabbix_server_group (
    id           INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    server_group VARCHAR(64)     NOT NULL COMMENT '服务器组名称',
    zbx_group_id INT UNSIGNED    NOT NULL COMMENT 'Zabbix 群组 ID',
    group_id     INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT '内部群组 ID，关联 init_grant',
    created_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_server_group (server_group)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='服务器组与 Zabbix 群组映射';

INSERT IGNORE INTO zabbix_server_group (server_group, zbx_group_id, group_id) VALUES
    ('default',    1, 1),
    ('prod-bj',    2, 2),
    ('prod-sh',    3, 2),
    ('test-bj',   10, 3),
    ('dev',       20, 4);

-- ── 2. init_grant ────────────────────────────────────────
-- 各服务器组安装完成后自动执行的初始化授权语句
CREATE TABLE IF NOT EXISTS init_grant (
    id          INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    group_id    INT UNSIGNED  NOT NULL COMMENT '关联 zabbix_server_group.group_id',
    grant_stmt  TEXT          NOT NULL COMMENT '安装后执行的 GRANT 语句',
    remark      VARCHAR(128)  DEFAULT '' COMMENT '备注',
    PRIMARY KEY (id),
    KEY idx_group_id (group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='安装后初始化授权语句';

INSERT IGNORE INTO init_grant (group_id, grant_stmt, remark) VALUES
    (1, "GRANT SELECT ON *.* TO 'monitor'@'%' IDENTIFIED BY 'monitor123'", '默认监控账号'),
    (1, "GRANT REPLICATION SLAVE ON *.* TO 'repl'@'%' IDENTIFIED BY 'repl123'",  '默认复制账号'),
    (2, "GRANT SELECT ON *.* TO 'monitor'@'%' IDENTIFIED BY 'monitor123'", '生产监控账号'),
    (2, "GRANT REPLICATION SLAVE ON *.* TO 'repl'@'%' IDENTIFIED BY 'repl123'",  '生产复制账号');

-- ── 3. mysql_install_log ─────────────────────────────────
-- MySQL 安装进度与状态日志，安装接口读写此表
CREATE TABLE IF NOT EXISTS mysql_install_log (
    id            INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    order_id      VARCHAR(64)   NOT NULL COMMENT '工单 ID',
    ip            VARCHAR(64)   NOT NULL COMMENT '目标主机 IP',
    install_stage TINYINT       NOT NULL DEFAULT 0  COMMENT '安装阶段 0-10',
    status        TINYINT       NOT NULL DEFAULT 0
                  COMMENT '0=待安装 1=安装中 2=失败 3=成功',
    install_type  TINYINT       NOT NULL DEFAULT 0  COMMENT '0=集群安装 1=扩容',
    message       TEXT          COMMENT '安装日志/错误信息',
    start_time    DATETIME      COMMENT '开始时间',
    end_time      DATETIME      COMMENT '结束时间',
    created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_order_ip (order_id, ip),
    KEY idx_ip (ip)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='MySQL 安装任务日志';

-- ── 4. machines_replicationsetup ────────────────────────
-- 主从扩容任务记录，扩容接口读写此表
CREATE TABLE IF NOT EXISTS machines_replicationsetup (
    id                  INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    order_id            VARCHAR(64)   NOT NULL COMMENT '工单 ID',
    master_ip           VARCHAR(64)   NOT NULL COMMENT '数据源主库 IP',
    master_port         INT           NOT NULL DEFAULT 3306 COMMENT '数据源主库端口',
    slaves              TEXT          COMMENT '新从库列表，格式: ip:port;ip:port',
    new_master          VARCHAR(64)   DEFAULT '' COMMENT '新主库 IP（切主场景）',
    new_second_slaves   TEXT          COMMENT '新二级从库列表',
    type                TINYINT       DEFAULT 0  COMMENT '扩容类型',
    from_choice         TINYINT       DEFAULT 0  COMMENT '数据源类型 0=主库 1=从库',
    finished            TINYINT       DEFAULT 0  COMMENT '0=待执行 1=执行中 2=完成',
    update_mgrinfo      TINYINT       DEFAULT 0  COMMENT '是否更新 mgr 信息',
    acter               VARCHAR(64)   DEFAULT '' COMMENT '执行人',
    check_envok         TINYINT       DEFAULT 0,
    check_envmessage    TEXT,
    rep_ok              TINYINT       DEFAULT 0,
    rep_message         TEXT,
    zabbix_identifiers  TEXT          COMMENT 'Zabbix 主机标识 JSON',
    created_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_order_id (order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='主从扩容任务记录';

-- ── 5. t_domain ──────────────────────────────────────────
-- DNS 域名与 IP 映射，DNS 接口降级查询时使用
CREATE TABLE IF NOT EXISTS t_domain (
    id         INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    domain     VARCHAR(255)  NOT NULL COMMENT '域名',
    ip         VARCHAR(64)   NOT NULL COMMENT '对应 IP',
    remark     VARCHAR(128)  DEFAULT '' COMMENT '备注',
    created_at DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_ip (ip),
    KEY idx_domain (domain)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='域名 IP 映射表';

INSERT IGNORE INTO t_domain (domain, ip, remark) VALUES
    ('db-prod-01.jddb.com',  '192.168.10.101', '生产主库01'),
    ('db-prod-02.jddb.com',  '192.168.10.102', '生产从库01'),
    ('db-test-01.jddb.com',  '127.0.0.1',      '测试主库'),
    ('db-dev-01.jddb.com',   '192.168.20.11',  '开发库01');

-- ── 6. t_jbxx（实例基础信息表）及视图 t_jbxx_view ──────────
-- dbbaseinfo 接口查询 t_jbxx_view，字段由调用方通过 queryList 指定
CREATE TABLE IF NOT EXISTS t_jbxx (
    id            INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    inst_ip       VARCHAR(64)   NOT NULL COMMENT '实例 IP',
    inst_port     INT           NOT NULL DEFAULT 3306 COMMENT '实例端口',
    db_version    VARCHAR(32)   DEFAULT '' COMMENT 'MySQL 版本',
    server_group  VARCHAR(64)   DEFAULT '' COMMENT '服务器组',
    env           VARCHAR(16)   DEFAULT 'prod' COMMENT '环境 prod/test/dev',
    hostname      VARCHAR(128)  DEFAULT '' COMMENT '主机名',
    disk_type     VARCHAR(16)   DEFAULT 'ssd'  COMMENT '磁盘类型',
    data_dir      VARCHAR(255)  DEFAULT '/data/mysql' COMMENT '数据目录',
    cpu_cores     INT           DEFAULT 0 COMMENT 'CPU 核数',
    mem_gb        INT           DEFAULT 0 COMMENT '内存 GB',
    remark        VARCHAR(255)  DEFAULT '' COMMENT '备注',
    created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_inst (inst_ip, inst_port)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='MySQL 实例基础信息';

-- 视图（dbbaseinfo 接口直接查 t_jbxx_view）
CREATE OR REPLACE VIEW t_jbxx_view AS
    SELECT * FROM t_jbxx;

INSERT IGNORE INTO t_jbxx
    (inst_ip, inst_port, db_version, server_group, env, hostname, disk_type, cpu_cores, mem_gb, remark)
VALUES
    ('127.0.0.1',       3306, '8.0.45', 'test-bj',  'test', 'claw-test001', 'ssd', 4,   8,  '本机测试库'),
    ('192.168.10.101',  3306, '8.0.36', 'prod-bj',  'prod', 'db-prod-01',   'ssd', 32, 128, '生产主库01'),
    ('192.168.10.102',  3306, '8.0.36', 'prod-bj',  'prod', 'db-prod-02',   'ssd', 32, 128, '生产从库01'),
    ('192.168.10.103',  3306, '8.0.36', 'prod-sh',  'prod', 'db-prod-sh01', 'ssd', 32, 128, '上海生产主库'),
    ('192.168.20.11',   3306, '5.7.44', 'dev',      'dev',  'db-dev-01',    'hdd',  8,  16, '开发库01');

-- ══ 二、新建 test 库并创建测试表 ════════════════════════════

CREATE DATABASE IF NOT EXISTS `testdb`
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE testdb;

-- ── 表1: 用户信息表 user_info ────────────────────────────
CREATE TABLE IF NOT EXISTS user_info (
    id          INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    username    VARCHAR(64)     NOT NULL COMMENT '用户名',
    email       VARCHAR(128)    NOT NULL COMMENT '邮箱',
    phone       VARCHAR(20)     DEFAULT '' COMMENT '手机号',
    department  VARCHAR(64)     DEFAULT '' COMMENT '部门',
    role        VARCHAR(32)     DEFAULT 'user' COMMENT '角色 admin/dba/user',
    status      TINYINT         NOT NULL DEFAULT 1 COMMENT '1=启用 0=禁用',
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户信息';

INSERT INTO user_info (username, email, phone, department, role) VALUES
    ('admin',       'admin@example.com',       '13800000001', 'IT 部',   'admin'),
    ('zhangsan',    'zhangsan@example.com',     '13800000002', 'DBA 组',  'dba'),
    ('lisi',        'lisi@example.com',         '13800000003', 'DBA 组',  'dba'),
    ('wangwu',      'wangwu@example.com',       '13800000004', '开发组',  'user'),
    ('zhaoliu',     'zhaoliu@example.com',      '13800000005', '开发组',  'user'),
    ('sunqi',       'sunqi@example.com',        '13800000006', '运维组',  'user'),
    ('zhouba',      'zhouba@example.com',       '13800000007', '测试组',  'user'),
    ('wujiu',       'wujiu@example.com',        '13800000008', '开发组',  'user'),
    ('zhengs',      'zhengs@example.com',       '13800000009', '运维组',  'user'),
    ('qianshi',     'qianshi@example.com',      '13800000010', 'DBA 组',  'dba');

-- ── 表2: 数据库工单表 db_order ────────────────────────────
CREATE TABLE IF NOT EXISTS db_order (
    id          INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    order_no    VARCHAR(32)     NOT NULL COMMENT '工单编号',
    order_type  VARCHAR(32)     NOT NULL COMMENT '类型 install/expand/grant/clone',
    db_ip       VARCHAR(64)     NOT NULL COMMENT '目标数据库 IP',
    db_port     INT             NOT NULL DEFAULT 3306,
    db_name     VARCHAR(64)     DEFAULT '' COMMENT '涉及数据库名',
    applicant   VARCHAR(64)     NOT NULL COMMENT '申请人',
    status      TINYINT         NOT NULL DEFAULT 0
                COMMENT '0=待审批 1=审批中 2=执行中 3=完成 4=拒绝',
    remark      VARCHAR(512)    DEFAULT '' COMMENT '工单备注',
    approved_by VARCHAR(64)     DEFAULT '' COMMENT '审批人',
    approved_at DATETIME        COMMENT '审批时间',
    finished_at DATETIME        COMMENT '完成时间',
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_order_no (order_no),
    KEY idx_applicant (applicant),
    KEY idx_db_ip (db_ip)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据库运维工单';

INSERT INTO db_order (order_no, order_type, db_ip, db_port, db_name, applicant, status, remark, approved_by, approved_at, finished_at) VALUES
    ('ORD20260301001', 'install', '192.168.10.101', 3306, '',        'zhangsan', 3, '生产主库安装',     'admin', '2026-03-01 09:00:00', '2026-03-01 10:30:00'),
    ('ORD20260301002', 'install', '192.168.10.102', 3306, '',        'zhangsan', 3, '生产从库安装',     'admin', '2026-03-01 09:05:00', '2026-03-01 11:00:00'),
    ('ORD20260302001', 'grant',   '192.168.10.101', 3306, 'shop_db', 'wangwu',   3, '申请只读权限',     'lisi',  '2026-03-02 10:00:00', '2026-03-02 10:15:00'),
    ('ORD20260303001', 'expand',  '192.168.10.101', 3306, '',        'lisi',     3, '磁盘扩容 200G',    'admin', '2026-03-03 08:30:00', '2026-03-03 14:00:00'),
    ('ORD20260305001', 'grant',   '192.168.10.103', 3306, 'user_db', 'zhaoliu',  3, '申请写权限',       'lisi',  '2026-03-05 11:00:00', '2026-03-05 11:30:00'),
    ('ORD20260306001', 'install', '192.168.20.11',  3306, '',        'wujiu',    3, '开发库安装',       'admin', '2026-03-06 09:00:00', '2026-03-06 10:00:00'),
    ('ORD20260308001', 'grant',   '192.168.10.101', 3306, 'order_db','sunqi',    2, '申请 DML 权限',    'lisi',  '2026-03-08 14:00:00', NULL),
    ('ORD20260310001', 'expand',  '192.168.10.103', 3306, '',        'zhangsan', 1, '上海生产库扩容',   'admin', NULL,                  NULL),
    ('ORD20260311001', 'grant',   '192.168.20.11',  3306, 'test_db', 'zhouba',   0, '申请测试库权限',   '',      NULL,                  NULL),
    ('ORD20260312001', 'install', '192.168.10.104', 3306, '',        'lisi',     0, '新机器安装 MySQL', '',      NULL,                  NULL);
