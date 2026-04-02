# Linux 巡检工具实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个单机 Linux 巡检工具，采集五大类指标，支持终端/HTML/JSON/CSV 输出，阈值可配置。

**Architecture:** Python 单文件入口 + checkers 模块（各类采集）+ reporters 模块（各类输出）。每个 checker 返回统一结构的列表，reporter 只负责渲染。配置由 config.yaml 提供默认值，CLI 参数可覆盖。

**Tech Stack:** Python 3.6+，psutil，pyyaml，标准库（argparse、subprocess、socket、csv、json）

---

## Aider 调用约定

本计划所有实现步骤均通过 aider 生成代码。每次调用格式：

```bash
cd /opt/aider-test/linux-inspect && \
OPENAI_API_KEY="sk-aa2156fdca9c4b089ec408ab927ea340" \
OPENAI_API_BASE="https://dashscope-intl.aliyuncs.com/compatible-mode/v1" \
aider --model openai/qwen-max --yes --no-auto-commits \
  --message "<指令>" \
  <文件列表>
```

---

## 文件清单

| 文件 | 职责 |
|------|------|
| `inspect.py` | CLI 入口，参数解析，调度 checkers 和 reporter |
| `config.yaml` | 默认阈值和配置 |
| `requirements.txt` | 依赖声明 |
| `checkers/__init__.py` | 配置加载器 `load_config(path, overrides)` |
| `checkers/system.py` | CPU/内存/磁盘/负载/运行时间采集 |
| `checkers/network.py` | 网卡状态/开放端口/外网连通性 |
| `checkers/security.py` | SSH 配置/空密码用户/sudo 权限 |
| `checkers/services.py` | systemd 服务状态/僵尸进程 |
| `checkers/logs.py` | 日志文件关键字扫描 |
| `reporters/__init__.py` | 空，包标记 |
| `reporters/terminal.py` | ANSI 彩色终端输出 |
| `reporters/html.py` | 单文件 HTML 报告（内嵌 CSS） |
| `reporters/json_csv.py` | JSON / CSV 导出 |
| `tests/test_config.py` | 配置加载测试 |
| `tests/test_system.py` | 系统巡检测试 |
| `tests/test_network.py` | 网络巡检测试 |
| `tests/test_security.py` | 安全巡检测试 |
| `tests/test_services.py` | 服务巡检测试 |
| `tests/test_logs.py` | 日志巡检测试 |
| `tests/test_reporters.py` | 三种 reporter 输出测试 |

---

## CheckItem 结构（所有 checker 返回此格式）

```python
{
    "category": str,       # "system" / "network" / "security" / "services" / "logs"
    "name": str,           # 人类可读名称，如 "CPU 使用率"
    "value": str,          # 显示用字符串，如 "45%"
    "raw_value": float,    # 原始数值（无法量化时为 None）
    "status": str,         # "OK" / "WARN" / "CRITICAL" / "SKIP"
    "threshold": str,      # 阈值说明，如 "warn>70%, critical>90%"
    "detail": str,         # 可选补充，如具体路径、进程名
}
```

---

## Task 1: 项目初始化

**Files:**
- Create: `/opt/aider-test/linux-inspect/` （目录）
- Create: `requirements.txt`
- Create: `config.yaml`
- Create: `checkers/__init__.py`、`checkers/system.py` 等（空文件）
- Create: `reporters/__init__.py` 等（空文件）
- Create: `tests/__init__.py`

- [ ] **Step 1: 创建目录结构**

```bash
mkdir -p /opt/aider-test/linux-inspect/{checkers,reporters,tests}
cd /opt/aider-test/linux-inspect
touch checkers/__init__.py checkers/system.py checkers/network.py \
      checkers/security.py checkers/services.py checkers/logs.py
touch reporters/__init__.py reporters/terminal.py reporters/html.py reporters/json_csv.py
touch tests/__init__.py inspect.py
git init && git add . && git commit -m "chore: init project structure"
```

- [ ] **Step 2: 写 requirements.txt**

```
psutil>=5.8.0
pyyaml>=5.4.0
pytest>=7.0.0
```

- [ ] **Step 3: 写 config.yaml**

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

- [ ] **Step 4: 安装依赖**

```bash
pip install psutil pyyaml pytest
```

- [ ] **Step 5: Commit**

```bash
cd /opt/aider-test/linux-inspect
git add requirements.txt config.yaml
git commit -m "chore: add requirements and default config"
```

---

## Task 2: 配置加载器（checkers/__init__.py）

**Files:**
- Create: `checkers/__init__.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_config.py
import os, yaml, pytest
from checkers import load_config

FIXTURE_CONFIG = {
    "thresholds": {
        "cpu_warn": 70, "cpu_critical": 90,
        "mem_warn": 80, "mem_critical": 95,
        "disk_warn": 80, "disk_critical": 90,
        "load_warn": 1.5, "load_critical": 3.0,
        "zombie_warn": 1, "zombie_critical": 10,
    },
    "security": {
        "check_ssh_root": True,
        "check_ssh_password_auth": True,
        "check_empty_password": True,
    },
    "services": {"critical_services": ["sshd", "cron", "rsyslog"]},
    "logs": {
        "scan_files": ["/var/log/syslog"],
        "warn_keywords": ["error", "warning"],
        "critical_keywords": ["critical", "panic", "oom"],
        "tail_lines": 1000,
    },
}

def test_load_default_config(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml.dump(FIXTURE_CONFIG))
    cfg = load_config(str(cfg_file), overrides={})
    assert cfg["thresholds"]["cpu_warn"] == 70
    assert cfg["thresholds"]["disk_critical"] == 90

def test_cli_overrides_threshold(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml.dump(FIXTURE_CONFIG))
    cfg = load_config(str(cfg_file), overrides={"cpu_warn": 60, "disk_warn": 75})
    assert cfg["thresholds"]["cpu_warn"] == 60
    assert cfg["thresholds"]["disk_warn"] == 75
    assert cfg["thresholds"]["mem_warn"] == 80  # 未覆盖的保持不变

def test_missing_config_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(str(tmp_path / "nonexistent.yaml"), overrides={})
```

- [ ] **Step 2: 运行测试，验证失败**

```bash
cd /opt/aider-test/linux-inspect && pytest tests/test_config.py -v
```

Expected: FAIL with `ImportError: cannot import name 'load_config'`

- [ ] **Step 3: 用 aider 实现 load_config**

```bash
cd /opt/aider-test/linux-inspect && \
OPENAI_API_KEY="sk-aa2156fdca9c4b089ec408ab927ea340" \
OPENAI_API_BASE="https://dashscope-intl.aliyuncs.com/compatible-mode/v1" \
aider --model openai/qwen-max --yes --no-auto-commits \
  --message "实现 load_config(path, overrides) 函数。
功能：
1. 读取 path 指定的 YAML 配置文件，文件不存在时抛出 FileNotFoundError
2. overrides 是一个 dict，键为阈值名（如 cpu_warn），将覆盖 cfg['thresholds'] 中对应值
3. 返回合并后的 config dict
请只实现这一个函数，不要添加其他内容。" \
  checkers/__init__.py
```

- [ ] **Step 4: 运行测试，验证通过**

```bash
cd /opt/aider-test/linux-inspect && pytest tests/test_config.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
cd /opt/aider-test/linux-inspect
git add checkers/__init__.py tests/test_config.py
git commit -m "feat: add config loader with CLI override support"
```

---

## Task 3: 系统巡检（checkers/system.py）

**Files:**
- Create: `checkers/system.py`
- Create: `tests/test_system.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_system.py
from unittest.mock import patch, MagicMock
from checkers.system import check_system

DEFAULT_THRESHOLDS = {
    "cpu_warn": 70, "cpu_critical": 90,
    "mem_warn": 80, "mem_critical": 95,
    "disk_warn": 80, "disk_critical": 90,
    "load_warn": 1.5, "load_critical": 3.0,
}

def _run(cpu=45.0, mem_pct=60.0, disk_pct=50.0, load=0.5, thresholds=None):
    t = thresholds or DEFAULT_THRESHOLDS
    mem = MagicMock(); mem.percent = mem_pct
    disk = MagicMock(); disk.percent = disk_pct
    part = MagicMock(); part.mountpoint = "/"; part.device = "/dev/sda1"
    with patch("psutil.cpu_percent", return_value=cpu), \
         patch("psutil.virtual_memory", return_value=mem), \
         patch("psutil.disk_partitions", return_value=[part]), \
         patch("psutil.disk_usage", return_value=disk), \
         patch("psutil.getloadavg", return_value=(load, load, load)), \
         patch("psutil.cpu_count", return_value=4), \
         patch("psutil.boot_time", return_value=0.0):
        return check_system(t)

def test_all_ok():
    items = _run(cpu=45, mem_pct=60, disk_pct=50, load=0.5)
    statuses = {i["name"]: i["status"] for i in items}
    assert statuses["CPU 使用率"] == "OK"
    assert statuses["内存使用率"] == "OK"
    assert statuses["磁盘 /"] == "OK"
    assert statuses["系统负载"] == "OK"

def test_cpu_warn():
    items = _run(cpu=75)
    cpu_item = next(i for i in items if i["name"] == "CPU 使用率")
    assert cpu_item["status"] == "WARN"

def test_cpu_critical():
    items = _run(cpu=95)
    cpu_item = next(i for i in items if i["name"] == "CPU 使用率")
    assert cpu_item["status"] == "CRITICAL"

def test_disk_critical():
    items = _run(disk_pct=92)
    disk_item = next(i for i in items if i["name"] == "磁盘 /")
    assert disk_item["status"] == "CRITICAL"

def test_item_structure():
    items = _run()
    for item in items:
        assert "category" in item and item["category"] == "system"
        assert "name" in item
        assert "value" in item
        assert "status" in item and item["status"] in ("OK", "WARN", "CRITICAL", "SKIP")
        assert "threshold" in item
        assert "detail" in item
```

- [ ] **Step 2: 运行测试，验证失败**

```bash
cd /opt/aider-test/linux-inspect && pytest tests/test_system.py -v
```

Expected: FAIL with `ImportError`

- [ ] **Step 3: 用 aider 实现 check_system**

```bash
cd /opt/aider-test/linux-inspect && \
OPENAI_API_KEY="sk-aa2156fdca9c4b089ec408ab927ea340" \
OPENAI_API_BASE="https://dashscope-intl.aliyuncs.com/compatible-mode/v1" \
aider --model openai/qwen-max --yes --no-auto-commits \
  --message "实现 check_system(thresholds: dict) -> list 函数。
返回 CheckItem 列表（每项包含 category/name/value/raw_value/status/threshold/detail 字段），category 固定为 'system'。
采集项及阈值逻辑：
1. CPU 使用率：psutil.cpu_percent(interval=1)，name='CPU 使用率'，value='xx%'，raw_value=float，warn>thresholds['cpu_warn']，critical>thresholds['cpu_critical']
2. 内存使用率：psutil.virtual_memory().percent，name='内存使用率'，warn>thresholds['mem_warn']，critical>thresholds['mem_critical']
3. 各磁盘分区：psutil.disk_partitions() 遍历，name='磁盘 <mountpoint>'，warn>thresholds['disk_warn']，critical>thresholds['disk_critical']
4. 系统负载：psutil.getloadavg()[0]/psutil.cpu_count()，name='系统负载'，value='x.xx'，warn>thresholds['load_warn']，critical>thresholds['load_critical']
5. 运行时间：psutil.boot_time() 计算天时分，name='系统运行时间'，status 始终 OK，threshold=''
每个采集项用独立 try/except，失败时 status='SKIP'，detail 写明错误原因。" \
  checkers/system.py
```

- [ ] **Step 4: 运行测试，验证通过**

```bash
cd /opt/aider-test/linux-inspect && pytest tests/test_system.py -v
```

Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
cd /opt/aider-test/linux-inspect
git add checkers/system.py tests/test_system.py
git commit -m "feat: add system checker (CPU/mem/disk/load/uptime)"
```

---

## Task 4: 网络巡检（checkers/network.py）

**Files:**
- Create: `checkers/network.py`
- Create: `tests/test_network.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_network.py
from unittest.mock import patch, MagicMock
from checkers.network import check_network

def _make_nic(isup=True, speed=1000):
    stat = MagicMock(); stat.isup = isup; stat.speed = speed
    return stat

def test_nic_up():
    with patch("psutil.net_if_stats", return_value={"eth0": _make_nic(isup=True)}), \
         patch("psutil.net_connections", return_value=[]), \
         patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        items = check_network()
    nic = next(i for i in items if "eth0" in i["name"])
    assert nic["status"] == "OK"

def test_nic_down():
    with patch("psutil.net_if_stats", return_value={"eth0": _make_nic(isup=False)}), \
         patch("psutil.net_connections", return_value=[]), \
         patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        items = check_network()
    nic = next(i for i in items if "eth0" in i["name"])
    assert nic["status"] == "CRITICAL"

def test_connectivity_fail():
    with patch("psutil.net_if_stats", return_value={}), \
         patch("psutil.net_connections", return_value=[]), \
         patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        items = check_network()
    conn = next(i for i in items if i["name"] == "外网连通性")
    assert conn["status"] == "WARN"

def test_connectivity_ok():
    with patch("psutil.net_if_stats", return_value={}), \
         patch("psutil.net_connections", return_value=[]), \
         patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        items = check_network()
    conn = next(i for i in items if i["name"] == "外网连通性")
    assert conn["status"] == "OK"

def test_item_structure():
    with patch("psutil.net_if_stats", return_value={}), \
         patch("psutil.net_connections", return_value=[]), \
         patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        items = check_network()
    for item in items:
        assert item["category"] == "network"
        assert item["status"] in ("OK", "WARN", "CRITICAL", "SKIP")
```

- [ ] **Step 2: 运行测试，验证失败**

```bash
cd /opt/aider-test/linux-inspect && pytest tests/test_network.py -v
```

Expected: FAIL

- [ ] **Step 3: 用 aider 实现 check_network**

```bash
cd /opt/aider-test/linux-inspect && \
OPENAI_API_KEY="sk-aa2156fdca9c4b089ec408ab927ea340" \
OPENAI_API_BASE="https://dashscope-intl.aliyuncs.com/compatible-mode/v1" \
aider --model openai/qwen-max --yes --no-auto-commits \
  --message "实现 check_network() -> list 函数，返回 CheckItem 列表，category='network'。
采集项：
1. 网卡状态：遍历 psutil.net_if_stats()，跳过 'lo'，每块网卡一条 item，name='网卡 <name>'，isup=True 则 OK，isup=False 则 CRITICAL，detail 包含速度信息，threshold='DOWN则CRITICAL'
2. 开放端口：psutil.net_connections(kind='inet')，收集所有 LISTEN 状态端口，合并为一条 item，name='开放端口'，status='OK'，value='22,80,443,...'，threshold=''
3. 外网连通性：subprocess.run(['ping','-c','1','-W','3','8.8.8.8'], capture_output=True)，returncode=0 则 OK，否则 WARN，name='外网连通性'，threshold='不通则WARN'
每项独立 try/except，失败时 status='SKIP'。" \
  checkers/network.py
```

- [ ] **Step 4: 运行测试，验证通过**

```bash
cd /opt/aider-test/linux-inspect && pytest tests/test_network.py -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
cd /opt/aider-test/linux-inspect
git add checkers/network.py tests/test_network.py
git commit -m "feat: add network checker (NIC/ports/connectivity)"
```

---

## Task 5: 安全巡检（checkers/security.py）

**Files:**
- Create: `checkers/security.py`
- Create: `tests/test_security.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_security.py
from unittest.mock import patch, mock_open
from checkers.security import check_security

DEFAULT_SEC_CFG = {
    "check_ssh_root": True,
    "check_ssh_password_auth": True,
    "check_empty_password": True,
}

SSH_CONFIG_SECURE = "PermitRootLogin no\nPasswordAuthentication no\n"
SSH_CONFIG_INSECURE = "PermitRootLogin yes\nPasswordAuthentication yes\n"

def test_ssh_secure():
    with patch("builtins.open", mock_open(read_data=SSH_CONFIG_SECURE)), \
         patch("checkers.security._get_empty_password_users", return_value=[]), \
         patch("checkers.security._get_sudo_users", return_value=["root"]):
        items = check_security(DEFAULT_SEC_CFG)
    root_item = next(i for i in items if i["name"] == "SSH Root 登录")
    pwd_item = next(i for i in items if i["name"] == "SSH 密码认证")
    assert root_item["status"] == "OK"
    assert pwd_item["status"] == "OK"

def test_ssh_insecure():
    with patch("builtins.open", mock_open(read_data=SSH_CONFIG_INSECURE)), \
         patch("checkers.security._get_empty_password_users", return_value=[]), \
         patch("checkers.security._get_sudo_users", return_value=["root"]):
        items = check_security(DEFAULT_SEC_CFG)
    root_item = next(i for i in items if i["name"] == "SSH Root 登录")
    pwd_item = next(i for i in items if i["name"] == "SSH 密码认证")
    assert root_item["status"] == "WARN"
    assert pwd_item["status"] == "WARN"

def test_empty_password_critical():
    with patch("builtins.open", mock_open(read_data=SSH_CONFIG_SECURE)), \
         patch("checkers.security._get_empty_password_users", return_value=["baduser"]), \
         patch("checkers.security._get_sudo_users", return_value=["root"]):
        items = check_security(DEFAULT_SEC_CFG)
    empty_item = next(i for i in items if i["name"] == "空密码用户")
    assert empty_item["status"] == "CRITICAL"
    assert "baduser" in empty_item["detail"]

def test_no_empty_password():
    with patch("builtins.open", mock_open(read_data=SSH_CONFIG_SECURE)), \
         patch("checkers.security._get_empty_password_users", return_value=[]), \
         patch("checkers.security._get_sudo_users", return_value=["root"]):
        items = check_security(DEFAULT_SEC_CFG)
    empty_item = next(i for i in items if i["name"] == "空密码用户")
    assert empty_item["status"] == "OK"
```

- [ ] **Step 2: 运行测试，验证失败**

```bash
cd /opt/aider-test/linux-inspect && pytest tests/test_security.py -v
```

Expected: FAIL

- [ ] **Step 3: 用 aider 实现 check_security**

```bash
cd /opt/aider-test/linux-inspect && \
OPENAI_API_KEY="sk-aa2156fdca9c4b089ec408ab927ea340" \
OPENAI_API_BASE="https://dashscope-intl.aliyuncs.com/compatible-mode/v1" \
aider --model openai/qwen-max --yes --no-auto-commits \
  --message "实现 check_security(sec_cfg: dict) -> list，category='security'。
需要实现以下内容：
1. _get_sudo_users() -> list: 读取 /etc/sudoers 和 /etc/sudoers.d/ 下文件，提取有 sudo 权限的用户名列表（忽略注释行）
2. _get_empty_password_users() -> list: 读取 /etc/shadow，找出密码字段为空或为 '!' 以外空值的用户（权限不足时返回空列表）
3. check_security(sec_cfg): 读取 /etc/ssh/sshd_config，检查：
   - name='SSH Root 登录'：PermitRootLogin 不是 no/prohibit-password 则 WARN，否则 OK，threshold='建议禁止'
   - name='SSH 密码认证'：PasswordAuthentication 不是 no 则 WARN，否则 OK，threshold='建议关闭'
   - name='空密码用户'：_get_empty_password_users() 有结果则 CRITICAL（detail 列出用户名），否则 OK，threshold='存在则CRITICAL'
   - name='Sudo 用户列表'：status='OK'，value=逗号分隔用户名，threshold=''
   每项独立 try/except，失败时 status='SKIP'，detail 写明原因。" \
  checkers/security.py
```

- [ ] **Step 4: 运行测试，验证通过**

```bash
cd /opt/aider-test/linux-inspect && pytest tests/test_security.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
cd /opt/aider-test/linux-inspect
git add checkers/security.py tests/test_security.py
git commit -m "feat: add security checker (SSH/empty-passwd/sudo)"
```

---

## Task 6: 服务巡检（checkers/services.py）

**Files:**
- Create: `checkers/services.py`
- Create: `tests/test_services.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_services.py
from unittest.mock import patch, MagicMock
from checkers.services import check_services

DEFAULT_SVC_CFG = {
    "critical_services": ["sshd", "cron", "rsyslog"],
}
DEFAULT_THRESHOLDS = {"zombie_warn": 1, "zombie_critical": 10}

def _mock_systemctl(service, active=True):
    result = MagicMock()
    result.returncode = 0 if active else 1
    result.stdout = "active\n" if active else "failed\n"
    return result

def test_service_active():
    def fake_run(cmd, **kw):
        return _mock_systemctl(cmd[-1], active=True)
    with patch("subprocess.run", side_effect=fake_run), \
         patch("psutil.process_iter", return_value=[]):
        items = check_services(DEFAULT_SVC_CFG, DEFAULT_THRESHOLDS)
    sshd = next(i for i in items if "sshd" in i["name"])
    assert sshd["status"] == "OK"

def test_service_failed():
    def fake_run(cmd, **kw):
        return _mock_systemctl(cmd[-1], active=False)
    with patch("subprocess.run", side_effect=fake_run), \
         patch("psutil.process_iter", return_value=[]):
        items = check_services(DEFAULT_SVC_CFG, DEFAULT_THRESHOLDS)
    sshd = next(i for i in items if "sshd" in i["name"])
    assert sshd["status"] == "CRITICAL"

def test_zombie_warn():
    def fake_run(cmd, **kw):
        return _mock_systemctl(cmd[-1], active=True)
    procs = []
    for _ in range(3):
        p = MagicMock(); p.status.return_value = "zombie"; procs.append(p)
    with patch("subprocess.run", side_effect=fake_run), \
         patch("psutil.process_iter", return_value=procs):
        items = check_services(DEFAULT_SVC_CFG, DEFAULT_THRESHOLDS)
    zombie = next(i for i in items if i["name"] == "僵尸进程")
    assert zombie["status"] == "WARN"

def test_zombie_critical():
    def fake_run(cmd, **kw):
        return _mock_systemctl(cmd[-1], active=True)
    procs = []
    for _ in range(15):
        p = MagicMock(); p.status.return_value = "zombie"; procs.append(p)
    with patch("subprocess.run", side_effect=fake_run), \
         patch("psutil.process_iter", return_value=procs):
        items = check_services(DEFAULT_SVC_CFG, DEFAULT_THRESHOLDS)
    zombie = next(i for i in items if i["name"] == "僵尸进程")
    assert zombie["status"] == "CRITICAL"
```

- [ ] **Step 2: 运行测试，验证失败**

```bash
cd /opt/aider-test/linux-inspect && pytest tests/test_services.py -v
```

Expected: FAIL

- [ ] **Step 3: 用 aider 实现 check_services**

```bash
cd /opt/aider-test/linux-inspect && \
OPENAI_API_KEY="sk-aa2156fdca9c4b089ec408ab927ea340" \
OPENAI_API_BASE="https://dashscope-intl.aliyuncs.com/compatible-mode/v1" \
aider --model openai/qwen-max --yes --no-auto-commits \
  --message "实现 check_services(svc_cfg: dict, thresholds: dict) -> list，category='services'。
采集项：
1. 对 svc_cfg['critical_services'] 中每个服务名：
   - 运行 subprocess.run(['systemctl','is-active','<name>'], capture_output=True, text=True)
   - returncode=0 则 OK，否则 CRITICAL
   - name='服务 <name>'，value=stdout.strip()，threshold='failed则CRITICAL'
2. 僵尸进程：psutil.process_iter(['status']) 统计 status=='zombie' 的进程数
   - name='僵尸进程'，value='N 个'
   - count>thresholds['zombie_critical'] 则 CRITICAL
   - count>thresholds['zombie_warn'] 则 WARN，否则 OK
   - threshold='warn>zombie_warn, critical>zombie_critical'
每项独立 try/except，失败时 status='SKIP'。" \
  checkers/services.py
```

- [ ] **Step 4: 运行测试，验证通过**

```bash
cd /opt/aider-test/linux-inspect && pytest tests/test_services.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
cd /opt/aider-test/linux-inspect
git add checkers/services.py tests/test_services.py
git commit -m "feat: add services checker (systemd/zombie)"
```

---

## Task 7: 日志巡检（checkers/logs.py）

**Files:**
- Create: `checkers/logs.py`
- Create: `tests/test_logs.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_logs.py
import os
from checkers.logs import check_logs

DEFAULT_LOG_CFG = {
    "scan_files": [],  # 由各测试用 tmp 文件替换
    "warn_keywords": ["error", "warning"],
    "critical_keywords": ["critical", "panic", "oom"],
    "tail_lines": 100,
}

def test_no_issues(tmp_path):
    log = tmp_path / "syslog"
    log.write_text("normal log line\nanother normal line\n")
    cfg = {**DEFAULT_LOG_CFG, "scan_files": [str(log)]}
    items = check_logs(cfg)
    item = next(i for i in items if str(log) in i["name"])
    assert item["status"] == "OK"

def test_warn_keyword(tmp_path):
    log = tmp_path / "syslog"
    log.write_text("Jan 1 error: something failed\n")
    cfg = {**DEFAULT_LOG_CFG, "scan_files": [str(log)]}
    items = check_logs(cfg)
    item = next(i for i in items if str(log) in i["name"])
    assert item["status"] == "WARN"

def test_critical_keyword(tmp_path):
    log = tmp_path / "syslog"
    log.write_text("Jan 1 kernel panic: oops\n")
    cfg = {**DEFAULT_LOG_CFG, "scan_files": [str(log)]}
    items = check_logs(cfg)
    item = next(i for i in items if str(log) in i["name"])
    assert item["status"] == "CRITICAL"

def test_missing_file_skipped(tmp_path):
    cfg = {**DEFAULT_LOG_CFG, "scan_files": ["/nonexistent/log/file"]}
    items = check_logs(cfg)
    assert items[0]["status"] == "SKIP"

def test_critical_beats_warn(tmp_path):
    log = tmp_path / "syslog"
    log.write_text("error: something\ncritical: oh no\n")
    cfg = {**DEFAULT_LOG_CFG, "scan_files": [str(log)]}
    items = check_logs(cfg)
    item = next(i for i in items if str(log) in i["name"])
    assert item["status"] == "CRITICAL"
```

- [ ] **Step 2: 运行测试，验证失败**

```bash
cd /opt/aider-test/linux-inspect && pytest tests/test_logs.py -v
```

Expected: FAIL

- [ ] **Step 3: 用 aider 实现 check_logs**

```bash
cd /opt/aider-test/linux-inspect && \
OPENAI_API_KEY="sk-aa2156fdca9c4b089ec408ab927ea340" \
OPENAI_API_BASE="https://dashscope-intl.aliyuncs.com/compatible-mode/v1" \
aider --model openai/qwen-max --yes --no-auto-commits \
  --message "实现 check_logs(log_cfg: dict) -> list，category='logs'。
对 log_cfg['scan_files'] 中每个文件：
- 文件不存在：status='SKIP'，detail='文件不存在'
- 读取最后 log_cfg['tail_lines'] 行（用 collections.deque(maxlen=N) 实现）
- 逐行检查（大小写不敏感）：
  - 包含 critical_keywords 中任意词 → CRITICAL（优先级最高）
  - 包含 warn_keywords 中任意词 → WARN
  - 否则 OK
- name='日志 <filepath>'
- value='发现N条CRITICAL, M条WARN' 或 '无异常'
- threshold='warn关键字/critical关键字'
- detail 列出前5条匹配行
- CRITICAL 优先于 WARN（一旦发现 critical 关键字即为 CRITICAL）
整体 try/except，失败时 status='SKIP'。" \
  checkers/logs.py
```

- [ ] **Step 4: 运行测试，验证通过**

```bash
cd /opt/aider-test/linux-inspect && pytest tests/test_logs.py -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
cd /opt/aider-test/linux-inspect
git add checkers/logs.py tests/test_logs.py
git commit -m "feat: add logs checker (keyword scan)"
```

---

## Task 8: 终端 Reporter（reporters/terminal.py）

**Files:**
- Create: `reporters/terminal.py`
- Create: `tests/test_reporters.py`（第一部分）

- [ ] **Step 1: 写测试**

```python
# tests/test_reporters.py
import json, csv, io
from reporters.terminal import render_terminal
from reporters.html import render_html
from reporters.json_csv import render_json, render_csv

SAMPLE_ITEMS = [
    {"category": "system", "name": "CPU 使用率", "value": "45%",
     "raw_value": 45.0, "status": "OK", "threshold": "warn>70%", "detail": ""},
    {"category": "system", "name": "内存使用率", "value": "85%",
     "raw_value": 85.0, "status": "WARN", "threshold": "warn>80%", "detail": ""},
    {"category": "security", "name": "空密码用户", "value": "baduser",
     "raw_value": None, "status": "CRITICAL", "threshold": "存在则CRITICAL", "detail": "baduser"},
]

def test_terminal_contains_status_indicators():
    output = render_terminal(SAMPLE_ITEMS)
    assert "OK" in output
    assert "WARN" in output
    assert "CRITICAL" in output

def test_terminal_contains_summary():
    output = render_terminal(SAMPLE_ITEMS)
    assert "1" in output  # 1 OK
    # 汇总行包含 OK/WARN/CRITICAL 计数
    assert "WARN" in output

def test_terminal_contains_item_names():
    output = render_terminal(SAMPLE_ITEMS)
    assert "CPU 使用率" in output
    assert "内存使用率" in output
    assert "空密码用户" in output

def test_html_is_valid_html():
    output = render_html(SAMPLE_ITEMS)
    assert output.strip().startswith("<!DOCTYPE html>") or "<html" in output
    assert "</html>" in output
    assert "CPU 使用率" in output
    assert "CRITICAL" in output

def test_json_is_valid():
    output = render_json(SAMPLE_ITEMS)
    data = json.loads(output)
    assert isinstance(data, list)
    assert len(data) == 3
    assert data[0]["name"] == "CPU 使用率"
    assert data[0]["status"] == "OK"

def test_csv_is_valid():
    output = render_csv(SAMPLE_ITEMS)
    reader = csv.DictReader(io.StringIO(output))
    rows = list(reader)
    assert len(rows) == 3
    assert rows[0]["name"] == "CPU 使用率"
    assert rows[2]["status"] == "CRITICAL"
    assert set(reader.fieldnames) >= {"category", "name", "value", "status", "threshold", "detail"}
```

- [ ] **Step 2: 运行测试，验证失败**

```bash
cd /opt/aider-test/linux-inspect && pytest tests/test_reporters.py -v
```

Expected: FAIL

- [ ] **Step 3: 用 aider 实现 render_terminal**

```bash
cd /opt/aider-test/linux-inspect && \
OPENAI_API_KEY="sk-aa2156fdca9c4b089ec408ab927ea340" \
OPENAI_API_BASE="https://dashscope-intl.aliyuncs.com/compatible-mode/v1" \
aider --model openai/qwen-max --yes --no-auto-commits \
  --message "实现 render_terminal(items: list) -> str 函数，返回 ANSI 彩色终端报告字符串。
要求：
1. 顶部打印：'===== Linux 巡检报告 =====' 和主机名、当前时间
2. 汇总行：'OK: N  WARN: M  CRITICAL: K'（OK绿色，WARN黄色，CRITICAL红色）
3. 按 category 分节，每节标题如 '[系统]'
4. 每条 item 一行：name 左对齐20字符，value 左对齐15字符，status 带颜色（OK绿✓，WARN黄⚠，CRITICAL红✗），threshold
5. ANSI 颜色常量：GREEN='\033[92m', YELLOW='\033[93m', RED='\033[91m', RESET='\033[0m'
6. 返回完整字符串（不直接 print）" \
  reporters/terminal.py
```

- [ ] **Step 4: 用 aider 实现 render_html**

```bash
cd /opt/aider-test/linux-inspect && \
OPENAI_API_KEY="sk-aa2156fdca9c4b089ec408ab927ea340" \
OPENAI_API_BASE="https://dashscope-intl.aliyuncs.com/compatible-mode/v1" \
aider --model openai/qwen-max --yes --no-auto-commits \
  --message "实现 render_html(items: list) -> str 函数，返回完整 HTML 字符串。
要求：
1. 完整 HTML 文件，内嵌 CSS（无外部依赖）
2. 顶部汇总卡片：显示 OK/WARN/CRITICAL 数量，各自用绿/黄/红背景色
3. 按 category 分节，每节为表格（列：检查项、值、状态、阈值、详情）
4. 状态颜色：OK=绿(#28a745)，WARN=橙(#ffc107)，CRITICAL=红(#dc3545)，SKIP=灰(#6c757d)
5. 页面标题为 'Linux 巡检报告 - <hostname> - <datetime>'
6. 返回字符串" \
  reporters/html.py
```

- [ ] **Step 5: 用 aider 实现 render_json 和 render_csv**

```bash
cd /opt/aider-test/linux-inspect && \
OPENAI_API_KEY="sk-aa2156fdca9c4b089ec408ab927ea340" \
OPENAI_API_BASE="https://dashscope-intl.aliyuncs.com/compatible-mode/v1" \
aider --model openai/qwen-max --yes --no-auto-commits \
  --message "实现两个函数：
1. render_json(items: list) -> str：将 items 序列化为 JSON 字符串，ensure_ascii=False，indent=2
2. render_csv(items: list) -> str：将 items 输出为 CSV 字符串，列顺序为 category,name,value,status,threshold,detail，第一行为表头
两个函数都返回字符串（不写文件）。" \
  reporters/json_csv.py
```

- [ ] **Step 6: 运行全部 reporter 测试**

```bash
cd /opt/aider-test/linux-inspect && pytest tests/test_reporters.py -v
```

Expected: 6 passed

- [ ] **Step 7: Commit**

```bash
cd /opt/aider-test/linux-inspect
git add reporters/terminal.py reporters/html.py reporters/json_csv.py tests/test_reporters.py
git commit -m "feat: add terminal/html/json/csv reporters"
```

---

## Task 9: 主入口（inspect.py）

**Files:**
- Modify: `inspect.py`
- Create: `tests/test_inspect.py`

- [ ] **Step 1: 写集成测试**

```python
# tests/test_inspect.py
import subprocess, sys, json, os

INSPECT = os.path.join(os.path.dirname(__file__), "..", "inspect.py")

def test_terminal_output_runs():
    result = subprocess.run(
        [sys.executable, INSPECT, "--only", "system"],
        capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0
    assert "巡检报告" in result.stdout or "Linux" in result.stdout

def test_json_output(tmp_path):
    out = tmp_path / "report.json"
    result = subprocess.run(
        [sys.executable, INSPECT, "--only", "system",
         "--output", "json", "--report", str(out)],
        capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0
    assert out.exists()
    data = json.loads(out.read_text())
    assert isinstance(data, list)
    assert len(data) > 0
    assert "status" in data[0]

def test_html_output(tmp_path):
    out = tmp_path / "report.html"
    result = subprocess.run(
        [sys.executable, INSPECT, "--only", "system",
         "--output", "html", "--report", str(out)],
        capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0
    assert out.exists()
    assert "<html" in out.read_text()
```

- [ ] **Step 2: 运行测试，验证失败**

```bash
cd /opt/aider-test/linux-inspect && pytest tests/test_inspect.py -v
```

Expected: FAIL（inspect.py 为空）

- [ ] **Step 3: 用 aider 实现 inspect.py**

```bash
cd /opt/aider-test/linux-inspect && \
OPENAI_API_KEY="sk-aa2156fdca9c4b089ec408ab927ea340" \
OPENAI_API_BASE="https://dashscope-intl.aliyuncs.com/compatible-mode/v1" \
aider --model openai/qwen-max --yes --no-auto-commits \
  --message "实现 inspect.py，作为 CLI 主入口。
使用 argparse 解析以下参数：
- --config: 配置文件路径，默认 config.yaml（相对于脚本所在目录）
- --output: 输出格式，choices=['terminal','html','json','csv']，默认 terminal
- --report: 报告文件路径，--output 非 terminal 时必填
- --only: 逗号分隔的类别名，如 'system,security'，默认全部运行（system,network,security,services,logs）
- --cpu-warn, --cpu-critical, --mem-warn, --mem-critical: float 类型，覆盖对应阈值
- --disk-warn, --disk-critical: float 类型
- --load-warn, --load-critical: float 类型

逻辑：
1. 用 load_config(config_path, overrides) 加载配置，overrides 从 CLI 阈值参数构建
2. 根据 --only 决定运行哪些 checker：
   - 'system' → check_system(cfg['thresholds'])
   - 'network' → check_network()
   - 'security' → check_security(cfg['security'])
   - 'services' → check_services(cfg['services'], cfg['thresholds'])
   - 'logs' → check_logs(cfg['logs'])
3. 合并所有 checker 返回的 items
4. 根据 --output 选择 reporter：
   - terminal → print(render_terminal(items))
   - html → 写文件 render_html(items)
   - json → 写文件 render_json(items)
   - csv → 写文件 render_csv(items)
5. 退出码：有 CRITICAL 则 exit(2)，有 WARN 则 exit(1)，否则 exit(0)

导入路径使用相对导入（sys.path.insert(0, script_dir) 方式确保 checkers/reporters 可导入）。" \
  inspect.py
```

- [ ] **Step 4: 运行集成测试**

```bash
cd /opt/aider-test/linux-inspect && pytest tests/test_inspect.py -v
```

Expected: 3 passed

- [ ] **Step 5: 运行全部测试**

```bash
cd /opt/aider-test/linux-inspect && pytest -v
```

Expected: 全部通过

- [ ] **Step 6: 手动冒烟测试**

```bash
cd /opt/aider-test/linux-inspect
python inspect.py
python inspect.py --only system,security --output json --report /tmp/inspect.json
cat /tmp/inspect.json | head -30
python inspect.py --only system --output html --report /tmp/inspect.html
ls -lh /tmp/inspect.html
```

- [ ] **Step 7: Commit**

```bash
cd /opt/aider-test/linux-inspect
git add inspect.py tests/test_inspect.py
git commit -m "feat: add CLI entry point, wires up all checkers and reporters"
```

---

## Task 10: 最终验收

- [ ] **Step 1: 运行全量测试套件**

```bash
cd /opt/aider-test/linux-inspect && pytest -v --tb=short
```

Expected: 全部通过，0 failures

- [ ] **Step 2: 完整运行一次巡检**

```bash
cd /opt/aider-test/linux-inspect
python inspect.py
```

检查：各类别均有输出，状态颜色正常，汇总行准确。

- [ ] **Step 3: 验证 HTML 报告可用**

```bash
python inspect.py --output html --report /tmp/full_report.html
ls -lh /tmp/full_report.html
```

Expected: HTML 文件生成，大小 > 0

- [ ] **Step 4: 验证 JSON 格式正确**

```bash
python inspect.py --output json --report /tmp/full_report.json
python -c "import json; data=json.load(open('/tmp/full_report.json')); print(f'共 {len(data)} 条巡检项')"
```

- [ ] **Step 5: 最终 Commit**

```bash
cd /opt/aider-test/linux-inspect
git tag v1.0.0
git log --oneline
```
