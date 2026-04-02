# Linux 巡检工具设计文档

**日期：** 2026-04-02  
**项目目录：** `/opt/aider-test/linux-inspect/`  
**技术栈：** Python 3.6+，psutil，标准库

---

## 1. 概述

一个单机 Linux 巡检工具，采集系统、网络、安全、服务、日志五大类指标，与可配置阈值对比后输出 OK/WARN/CRITICAL 状态，支持终端彩色输出、HTML 报告、JSON/CSV 三种输出格式。

---

## 2. 项目结构

```
linux-inspect/
├── inspect.py          # 主入口，CLI 参数解析
├── config.yaml         # 默认阈值配置
├── checkers/
│   ├── __init__.py
│   ├── system.py       # CPU、内存、磁盘、负载、运行时间
│   ├── network.py      # 网卡状态、开放端口、外网连通性
│   ├── security.py     # SSH配置、空密码用户、sudo权限
│   ├── services.py     # systemd 服务状态、僵尸进程
│   └── logs.py         # 日志关键字扫描
└── reporters/
    ├── __init__.py
    ├── terminal.py     # 彩色终端输出（ANSI 颜色）
    ├── html.py         # HTML 报告（内嵌 CSS）
    └── json_csv.py     # JSON / CSV 导出
```

---

## 3. 数据流

```
CLI 参数 + config.yaml
        ↓
   各 checker 采集原始数据
        ↓
   与阈值对比，每项标记 status: OK / WARN / CRITICAL
        ↓
   reporter 按指定格式输出结果
```

每个 checker 返回一个列表，每项为：
```python
{
    "category": "system",
    "name": "CPU 使用率",
    "value": "45%",
    "raw_value": 45.0,
    "status": "OK",       # OK / WARN / CRITICAL
    "threshold": "warn>70%, critical>90%",
    "detail": ""          # 可选，补充说明
}
```

---

## 4. 巡检项与默认阈值

### 4.1 系统（system.py）
| 巡检项 | 默认 WARN | 默认 CRITICAL |
|--------|-----------|---------------|
| CPU 使用率 | >70% | >90% |
| 内存使用率 | >80% | >95% |
| 各磁盘分区使用率 | >80% | >90% |
| 系统负载（load1/cpu数） | >1.5 | >3.0 |
| 系统运行时间 | — | — |

### 4.2 网络（network.py）
| 巡检项 | 状态规则 |
|--------|----------|
| 网卡状态 | DOWN 则 CRITICAL |
| 开放端口列表 | 仅展示，不告警 |
| 外网连通性（ping 8.8.8.8） | 不通则 WARN |

### 4.3 安全（security.py）
| 巡检项 | 状态规则 |
|--------|----------|
| SSH PermitRootLogin | 未禁用则 WARN |
| SSH PasswordAuthentication | 未关闭则 WARN |
| 空密码用户 | 存在则 CRITICAL |
| sudo 权限用户列表 | 仅展示 |

### 4.4 服务（services.py）
| 巡检项 | 默认 WARN | 默认 CRITICAL |
|--------|-----------|---------------|
| 关键 systemd 服务（sshd/cron/rsyslog） | — | failed 则 CRITICAL |
| 僵尸进程数量 | >0 | >10 |

### 4.5 日志（logs.py）
| 巡检项 | 规则 |
|--------|------|
| /var/log/syslog 等关键字扫描 | error/warning → WARN；critical/panic/oom → CRITICAL |
| 扫描最近 N 行（默认 1000 行） | 可配置 |

---

## 5. 配置文件（config.yaml）

```yaml
thresholds:
  cpu_warn: 70
  cpu_critical: 90
  mem_warn: 80
  mem_critical: 95
  disk_warn: 80
  disk_critical: 90
  load_warn: 1.5
  load_critical: 3.0
  zombie_warn: 1
  zombie_critical: 10

security:
  check_ssh_root: true
  check_ssh_password_auth: true
  check_empty_password: true

services:
  critical_services:
    - sshd
    - cron
    - rsyslog

logs:
  scan_files:
    - /var/log/syslog
    - /var/log/messages
  warn_keywords:
    - error
    - warning
  critical_keywords:
    - critical
    - panic
    - oom
  tail_lines: 1000
```

---

## 6. CLI 接口

```bash
# 终端输出（默认）
python inspect.py

# 指定输出格式
python inspect.py --output html --report /tmp/report.html
python inspect.py --output json --report /tmp/report.json
python inspect.py --output csv  --report /tmp/report.csv

# 覆盖阈值
python inspect.py --disk-warn 70 --disk-critical 90 --cpu-warn 60

# 指定配置文件
python inspect.py --config /etc/inspect/config.yaml

# 只运行指定类别
python inspect.py --only system,security
```

---

## 7. 输出格式

### 7.1 终端（ANSI 彩色）
- 绿色 `✓ OK`，黄色 `⚠ WARN`，红色 `✗ CRITICAL`
- 顶部显示汇总：`OK: 18  WARN: 2  CRITICAL: 1`
- 按类别分节展示

### 7.2 HTML 报告
- 内嵌 CSS，无外部依赖，单文件可独立打开
- 顶部汇总卡片，各类别折叠表格
- 状态颜色与终端一致

### 7.3 JSON 输出
每项结构：
```json
{
  "category": "system",
  "name": "CPU 使用率",
  "value": "45%",
  "status": "OK",
  "threshold": "warn>70%, critical>90%"
}
```

### 7.4 CSV 输出
列：`category, name, value, status, threshold, detail`

---

## 8. 依赖

| 包 | 用途 | 安装 |
|----|------|------|
| `psutil` | CPU/内存/磁盘/进程采集 | `pip install psutil` |
| `pyyaml` | 读取 config.yaml | `pip install pyyaml` |
| 标准库 | 其余所有功能 | 无需安装 |

---

## 9. 错误处理

- 每个 checker 独立 try/except，单个 checker 失败不影响其他
- 权限不足的检查项（如读取 /etc/shadow）标记为 `SKIP` 并说明原因
- 日志文件不存在时跳过该文件，不报错
