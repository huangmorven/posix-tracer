# posix-tracer 核心功能技术实现方案

> 本方案基于 `specs/001-core-functionality/spec.md` 与项目根目录 `constitution.md` 制定。实现时必须严格遵循 TDD：每个功能先写失败测试，再写最小实现，再重构。

## 1. 技术上下文总结

### 1.1 产品目标

`posix-tracer` 是一个面向离线 POSIX 语义兼容性评估的采集工具。MVP 目标是：用户指定一个目录，工具在系统范围内捕获访问该目录的元数据与控制类 POSIX 文件系统 syscall，并输出紧凑的 strace-like 日志。

### 1.2 技术选型

| 维度 | 选择 | 说明 |
| --- | --- | --- |
| 主语言 | Python 3 | 用于 CLI、BCC 加载、事件解码、日志格式化、summary 统计。 |
| 内核追踪 | eBPF via BCC | 使用 syscall tracepoint 挂钩 entry/exit。 |
| 事件传输 | perf buffer | BPF 向用户态传输命中事件，并统计 lost events。 |
| 测试框架 | Python 标准库 `unittest` | 遵循标准库优先，不引入 pytest 等额外依赖。 |
| 输出格式 | strace-like 文本 | 默认带 `[time pid comm latency matched]` 前缀，`--compact` 可去掉事件前缀。 |
| 运行平台 | Linux x86_64 | kernel >= 4.18，推荐 >= 5.4；开发机可运行纯 Python 单元测试。 |

### 1.3 MVP 边界

MVP 只实现 `spec.md` 明确要求的能力：

1. CLI：`--dir/-d`、`--output/-o`、`--duration/-t`、`--follow`、`--compact`。
2. 默认覆盖 A-H syscall 白名单。
3. 路径前缀过滤。
4. fd→path 映射。
5. close/close_range/dup/dup2/dup3/fcntl dup 内部维护 fd 映射，但不输出业务事件。
6. syscall exit 单行输出。
7. header 与 summary footer。
8. perf buffer lost events 统计。

不实现 `--format jsonl`、syscall group include/exclude、`-- command...`、`--fail-on-lost-events`、文件系统类型检测、完整 fork/clone fd 继承、完整复杂结构体展开。

## 2. “合宪性”审查

### 2.1 第一条：简单性原则

#### 2.1.1 YAGNI

方案只实现 `spec.md` 中的 MVP 功能。所有 P1/P2 能力均不进入第一版，包括 JSONL、分析报告、命令启动模式、文件系统类型检测、arm64 支持等。

#### 2.1.2 标准库优先

除 BCC 这一项目必要依赖外，Python 代码仅使用标准库：

- `argparse`：CLI 解析。
- `dataclasses`：事件、配置、summary 数据结构。
- `enum`：匹配类型、事件类型。
- `os` / `pathlib`：路径校验与输出文件处理。
- `platform`：kernel 信息。
- `signal` / `time`：运行时长与 Ctrl-C。
- `sys`：stderr/stdout 与退出码。
- `unittest`：测试。

不引入 Click、pytest、pydantic、rich、loguru 等非必需依赖。

#### 2.1.3 反过度工程

实现采用“单入口脚本 + 少量内聚数据结构 + 纯函数”的结构。第一版不建立复杂 package、插件系统、抽象 tracing backend 或 formatter registry。

#### 2.1.4 包内聚

MVP 采用一个可执行模块 `posix-tracer`，其内部按职责分区：

1. CLI 与配置解析。
2. syscall 元数据定义。
3. 事件数据结构。
4. 纯 Python 格式化与 summary。
5. BPF C 源码生成。
6. BCC tracer 生命周期管理。

测试放在 `tests/` 下，并按行为拆分。若单文件超过可读性阈值，再按“功能内聚”拆分为 package；MVP 不预先拆分。

### 2.2 第二条：测试先行铁律

#### 2.2.1 TDD 循环

所有 Python 侧可测试逻辑必须先写失败测试：

1. CLI 参数解析。
2. 路径规范化与前缀匹配。
3. fd 表维护。
4. strace-like 格式化。
5. summary 统计。
6. header/footer 生成。
7. syscall 元数据白名单。

每个任务必须遵循 Red-Green-Refactor：先运行测试确认失败，再写最小实现，再运行测试通过。

#### 2.2.2 表格驱动测试

单元测试使用 `unittest.TestCase.subTest` 编写表格驱动测试。例如路径匹配、返回值格式化、errno 统计等均以 case 表驱动。

#### 2.2.3 拒绝 mocks，优先真实依赖

纯 Python 逻辑不需要 mock。BCC/eBPF 集成测试在 Linux root 环境运行真实 BPF 程序。由于当前开发环境可能不是 Linux，集成测试用 `@unittest.skipUnless(...)` 在非 Linux 或无 root/BCC 时显式跳过，而不是 mock BCC 行为。

### 2.3 第三条：明确性原则

#### 2.3.1 显式错误处理

所有错误必须显式处理并转换为清晰用户消息与退出码：

1. 缺少 `--dir`。
2. 目标路径不存在或不是目录。
3. 输出文件无法创建或写入。
4. BCC import 失败。
5. BPF 程序加载失败。
6. tracepoint 全部不可用。
7. perf buffer 轮询异常。

实现中禁止裸 `except:`。允许捕获具体异常，写入 stderr，并返回非 0。

#### 2.3.2 无全局变量传递状态

Python 侧禁止使用可变全局变量传递运行状态。状态必须通过以下对象显式传递：

- `TracerConfig`
- `TraceEvent`
- `FdTable`
- `Summary`
- `OutputWriter`
- `TracerRuntime`

模块级常量仅用于不可变配置，例如 syscall 定义、errno/flag 名称映射。eBPF C 中的 BPF map 是内核 API 要求的数据结构，必须命名清晰并只用于 `entry context`、`fd path map`、`perf events`，不得引入额外隐式状态。

## 3. 总体架构

### 3.1 高层数据流

```text
用户 CLI
  |
  v
TracerConfig
  |
  v
BPF 程序生成与加载
  |
  v
syscall tracepoint entry/exit
  |
  v
BPF maps: entry context / fd path / perf events
  |
  v
Python perf buffer callback
  |
  v
TraceEvent 解码
  |
  +--> Summary 更新
  |
  +--> strace-like Formatter
  |
  v
OutputWriter(stdout / file / follow)
```

### 3.2 关键设计决策

#### ADR-001：使用单文件脚本作为 MVP 交付形态

- **决策**：第一版创建 `posix-tracer`，不预先拆分 package。
- **原因**：项目规模小，MVP 功能集中，符合简单性原则。
- **代价**：文件可能增长较快。
- **缓解**：内部按章节组织；如果后续功能扩展，再按测试保护进行拆分。

#### ADR-002：用户态负责日志格式化和 summary

- **决策**：BPF 只传输结构化字段，Python 负责将 flags、errno、fd path 等格式化为 strace-like 文本。
- **原因**：BPF 字符串处理能力有限，用户态更易测试和演进。
- **代价**：perf event 结构需要覆盖足够字段。
- **缓解**：事件结构按 syscall family 设计通用字段，不追求复杂结构体完整展开。

#### ADR-003：MVP 采用路径字符串前缀匹配

- **决策**：BPF entry 阶段读取路径字符串并做目标目录前缀匹配。
- **原因**：实现简单、可解释，符合 spec 的准确性边界。
- **代价**：不处理 symlink、`..`、mount namespace 等真实对象等价。
- **缓解**：在 header/spec/文档中明确限制。

#### ADR-004：fd→path 映射在 BPF map 中维护

- **决策**：以进程标识 + fd 为 key，在 BPF map 中保存路径摘要。
- **原因**：fd-based syscall 需要内核态快速判断是否命中目标目录，避免用户态读取 `/proc/<pid>/fd` 的竞态和开销。
- **代价**：BPF map 大小有限，fork/clone 继承不完整。
- **缓解**：设置合理 map 上限，记录限制，并追踪 close/dup 降低 fd 复用误判。

## 4. 文件与模块规划

### 4.1 生产代码

创建：

- `posix-tracer`

内部建议结构：

```python
# 1. imports
# 2. constants: syscall names, groups, flag maps
# 3. dataclasses: TracerConfig, TraceEvent, Summary, FdEntry
# 4. pure helpers: path matching, flag formatting, errno formatting
# 5. formatter: header, event line, summary footer
# 6. fd table model for Python-side tests
# 7. BPF source builder
# 8. BCC adapter / tracer runtime
# 9. CLI parse + main
```

### 4.2 测试代码

创建：

- `tests/test_cli.py`
- `tests/test_path_filter.py`
- `tests/test_fd_table.py`
- `tests/test_formatter.py`
- `tests/test_summary.py`
- `tests/test_syscall_catalog.py`
- `tests/test_integration_linux.py`

说明：

- 前 6 个测试文件只依赖标准库，可在 macOS 开发机运行。
- `test_integration_linux.py` 在非 Linux、非 root 或 BCC 不可用时跳过。

## 5. 核心数据结构

### 5.1 `TracerConfig`

字段：

- `target_dir: str`
- `target_dir_realpath: str`
- `output_path: str | None`
- `duration_sec: float | None`
- `follow: bool`
- `compact: bool`

职责：保存 CLI 解析后的不可变配置。路径校验失败时不创建运行时。

### 5.2 `TraceEvent`

字段：

- `timestamp_ns: int`
- `pid: int`
- `tid: int`
- `comm: str`
- `syscall: str`
- `matched: str`
- `latency_ns: int`
- `ret: int`
- `errno: int | None`
- `args_text: str`

职责：作为用户态格式化的统一事件对象。BPF 原始事件解码后转换为该对象。

### 5.3 `Summary`

字段：

- `total_events: int`
- `failed_events: int`
- `lost_events: int`
- `syscall_counts: dict[str, int]`
- `errno_counts: dict[int, int]`

职责：接收 `TraceEvent` 后更新统计；生成 summary footer。

### 5.4 `FdTable`

Python 侧 `FdTable` 主要用于测试 fd 映射规则，确保语义明确。运行时权威 fd 映射在 BPF map 中维护。

方法：

- `open(pid, fd, path)`
- `close(pid, fd)`
- `close_range(pid, first, last)`
- `dup(pid, old_fd, new_fd)`
- `resolve(pid, fd) -> str | None`

## 6. eBPF/BCC 实现策略

### 6.1 tracepoint 探测

用户态启动时探测每个目标 syscall 是否存在：

```text
/sys/kernel/debug/tracing/events/syscalls/sys_enter_<name>
/sys/kernel/debug/tracing/events/syscalls/sys_exit_<name>
```

存在 entry/exit 才附加。缺失 syscall 记录到 `skipped_syscalls`，写入 header。

### 6.2 BPF maps

MVP 使用以下 BPF maps：

1. `entry_map`：key 为 `pid_tgid`，value 保存 entry 上下文。
2. `fd_map`：key 为 `{tgid, fd}`，value 保存路径摘要。
3. `events`：perf output。

### 6.3 事件结构

BPF 向用户态传输固定大小结构，避免动态分配：

- `timestamp_ns`
- `pid`
- `tid`
- `comm[16]`
- `syscall_id` 或 `syscall_name_id`
- `matched_mask`
- `latency_ns`
- `ret`
- `errno`
- `fd`
- `dirfd`
- `flags`
- `mode`
- `size`
- `offset`
- `request`
- `path1[MAX_PATH_LEN]`
- `path2[MAX_PATH_LEN]`
- `xattr_name[MAX_XATTR_NAME_LEN]`（仅在显式启用 xattr name 捕获时进入 event struct）

MVP 可选择较小常量：

- `MAX_PATH_LEN = 256`
- `MAX_XATTR_NAME_LEN = 256`（仅用于 `--capture-xattr-name`）

路径或 xattr name 过长时允许截断，并在格式化中用 `...` 表示。

### 6.4 syscall family 处理

为降低复杂度，不为每个 syscall 手写完全不同的事件结构，而是按 family 编写少量处理路径：

1. 单路径 syscall：`path1`。
2. 双路径 syscall：`path1` + `path2`，并计算 `matched=src/dst/src,dst`。
3. fd syscall：读取 fd 并查询 `fd_map`。
4. open family：entry 保存路径与 flags/mode；exit 成功后更新 `fd_map` 并输出 open 事件。
5. fd maintenance family：close/close_range/dup/fcntl dup 只更新 `fd_map`，默认不输出业务事件。

### 6.5 BPF 复杂度控制

第一版不解析完整复杂结构体。`openat2` 只尝试读取 `open_how.flags/mode/resolve`。读取失败时字段置 0，并继续记录基础事件。

## 7. 输出设计

### 7.1 Header

启动成功后立即写入 header：

```text
# posix-tracer started_at=<ISO8601>
# target_dir=<input>
# target_dir_realpath=<realpath>
# kernel=<platform.release()>
# bcc_version=<detected-or-unknown>
# mode=exit-only
# output_format=strace-like
# compact=<true|false>
# skipped_syscalls=<comma-separated-or-none>
```

### 7.2 Event line

默认：

```text
[HH:MM:SS.micro pid=<pid> comm=<comm> latency=<Nus> matched=<matched>] <syscall>(<args>) = <ret> [(errno=N)]
```

compact：

```text
<syscall>(<args>) = <ret> [(errno=N)]
```

### 7.3 Summary

退出时：

1. stderr 打印 summary。
2. 如果指定 `--output`，文件尾部追加 `# summary`。
3. `lost_events > 0` 时增加 warning。

## 8. 错误处理策略

实现统一入口：

```python
def main(argv: list[str] | None = None) -> int:
    try:
        ...
    except UserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
```

要求：

1. CLI/路径/输出文件错误返回 2。
2. BCC/BPF/tracepoint 运行时错误返回 1。
3. 正常完成、Ctrl-C、lost events 返回 0。
4. 不允许吞掉异常。
5. 不允许输出 Python traceback 给普通用户，除非后续新增 debug 模式。

## 9. TDD 实施计划

### Task 1：CLI 参数解析

**文件：**

- 创建：`posix-tracer`
- 创建：`tests/test_cli.py`

**步骤：**

1. 写 `test_cli.py`，覆盖 `--dir` 必填、`--output`、`--duration`、`--follow`、`--compact`。
2. 运行 `python3 -m unittest tests.test_cli -v`，确认失败。
3. 实现 `parse_args(argv)` 和 `TracerConfig`。
4. 再次运行测试，确认通过。

### Task 2：路径规范化与前缀匹配

**文件：**

- 修改：`posix-tracer`
- 创建：`tests/test_path_filter.py`

**步骤：**

1. 使用 `subTest` 表格测试目标目录 `/mnt/objstore` 下的命中与非命中路径。
2. 覆盖 `/mnt/objstore/a` 命中、`/mnt/objstore2/a` 不命中、目标目录自身命中。
3. 实现 `normalize_target_dir()` 与 `is_path_under_target()`。
4. 确认测试通过。

### Task 3：fd 表语义

**文件：**

- 修改：`posix-tracer`
- 创建：`tests/test_fd_table.py`

**步骤：**

1. 表格测试 open/close/dup/close_range/resolve。
2. 先确认失败。
3. 实现 `FdTable`。
4. 确认测试通过。

### Task 4：事件格式化

**文件：**

- 修改：`posix-tracer`
- 创建：`tests/test_formatter.py`

**步骤：**

1. 表格测试成功事件、失败事件、compact 模式、matched 字段、latency 单位。
2. 先确认失败。
3. 实现 `TraceEvent` 与 `format_event_line()`。
4. 确认测试通过。

### Task 5：header 与 summary

**文件：**

- 修改：`posix-tracer`
- 创建：`tests/test_summary.py`

**步骤：**

1. 测试 header 包含 target_dir、kernel、mode、compact、skipped_syscalls。
2. 测试 summary 统计 total、failed、lost、syscall_counts、errno_counts。
3. 先确认失败。
4. 实现 `Summary`、`format_header()`、`format_summary()`。
5. 确认测试通过。

### Task 6：syscall catalog

**文件：**

- 修改：`posix-tracer`
- 创建：`tests/test_syscall_catalog.py`

**步骤：**

1. 测试 A-H 白名单包含 spec 中列出的 syscall。
2. 测试 read/write/close 不在业务输出 syscall 集合中。
3. 测试 close/dup/fcntl dup 在 fd maintenance 集合中。
4. 实现 syscall catalog 常量。
5. 确认测试通过。

### Task 7：BPF source builder

**文件：**

- 修改：`posix-tracer`
- 可追加：`tests/test_syscall_catalog.py`

**步骤：**

1. 测试 `build_bpf_source(target_dir, enabled_syscalls)` 返回字符串包含必要 map、event struct、目标目录常量。
2. 先确认失败。
3. 实现最小 BPF source builder。
4. 确认纯 Python 测试通过。

### Task 8：BCC runtime adapter

**文件：**

- 修改：`posix-tracer`

**步骤：**

1. 实现 `TracerRuntime`，负责 import BCC、加载 BPF、附加 tracepoint、poll perf buffer。
2. 所有 BCC import 放在运行时函数内，避免非 Linux 单元测试 import 失败。
3. 显式处理 BCC 不存在、BPF 加载失败、tracepoint 不存在。
4. 手动在 Linux root 环境运行 smoke test。

### Task 9：Linux 集成测试

**文件：**

- 创建：`tests/test_integration_linux.py`

**步骤：**

1. 使用 `unittest.skipUnless` 检查 Linux、root、BCC 可用。
2. 创建临时目录作为目标目录。
3. 启动 tracer 短时间采集。
4. 执行 `stat`、`touch`、`mv`、`getfattr` 等真实命令。
5. 验证输出包含期望 syscall，不包含 read/write/close 业务事件。

### Task 10：端到端手动验收

**命令：**

```bash
sudo python3 posix-tracer -d /mnt/objstore -o trace.log -t 60 --follow
```

**检查：**

1. 文件开头有 header。
2. 事件行为 strace-like 格式。
3. 失败事件包含 errno。
4. fd-based 事件尽量包含 `fd=N<path>`。
5. 文件尾部有 summary。
6. stderr 有 summary。
7. read/write/close 不作为业务事件输出。

## 10. 验证命令

开发机通用单元测试：

```bash
python3 -m unittest discover -s tests -v
```

Linux root 集成测试：

```bash
sudo python3 -m unittest tests.test_integration_linux -v
```

手动 smoke test：

```bash
mkdir -p /tmp/posix-tracer-target
sudo python3 posix-tracer -d /tmp/posix-tracer-target -o /tmp/trace.log -t 10 --follow
```

另一个终端执行：

```bash
touch /tmp/posix-tracer-target/a
stat /tmp/posix-tracer-target/a
mv /tmp/posix-tracer-target/a /tmp/posix-tracer-target/b
```

## 11. 风险与缓解

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| syscall tracepoint 在目标内核不存在 | 某些 syscall 无法追踪 | 启动时探测，写入 skipped_syscalls。 |
| BPF verifier 拒绝复杂程序 | 程序无法加载 | 分 syscall family 保持简单，限制循环和结构体解析。 |
| perf buffer 丢事件 | 日志不完整 | lost events callback 计数，summary warning。 |
| fd map 容量不足 | fd-based syscall 漏记 | 设定合理 map size，后续按需要调优。 |
| 路径截断 | 日志路径不完整 | 标记截断，保持 MAX_PATH_LEN 简单可调。 |
| macOS 开发环境不能运行 BPF | 无法本地集成验证 | 单元测试覆盖纯逻辑；集成测试在 Linux root 环境运行。 |

## 12. 实施顺序建议

推荐顺序：

1. 先完成纯 Python 可测试核心：CLI、路径、fd、formatter、summary、catalog。
2. 再实现 BPF source builder。
3. 最后接入 BCC runtime。
4. Linux 上做 smoke test 和集成测试。
5. 根据 verifier 错误最小化 BPF 程序，禁止为绕过问题引入复杂抽象。

该顺序可以最大化 TDD 覆盖，降低 BPF 调试成本，并符合项目宪法的简单性、测试先行和明确性原则。
