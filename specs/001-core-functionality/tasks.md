# posix-tracer 核心功能任务列表

> 基于 `specs/001-core-functionality/spec.md` 与 `specs/001-core-functionality/plan.md` 生成。  
> 必须遵守 `constitution.md`：TDD 优先、标准库优先、显式错误处理、无全局可变状态传递。  
> 标记 `[P]` 的任务没有直接依赖关系，可并行执行。未标记 `[P]` 的任务必须按顺序执行。

## 任务依赖总览

```text
Phase 1 测试先行
  T001-T007 可并行创建测试文件
  T008 运行测试确认失败

Phase 2 纯 Python 核心实现
  T009 -> T010 -> T011 -> T012 -> T013 -> T014 -> T015 -> T016 -> T017

Phase 3 BPF/BCC 运行时
  T018 -> T019 -> T020 -> T021 -> T022

Phase 4 集成测试与验收
  T023 -> T024 -> T025
```

## Phase 1：测试先行任务

### T001 [P] 创建 CLI 参数解析测试

**文件：** 创建 `tests/test_cli.py`

**目标：** 用标准库 `unittest` 表格驱动测试 CLI 行为。

**测试必须覆盖：**

1. `--dir/-d` 必填。
2. `--output/-o` 可选。
3. `--duration/-t` 转为浮点秒数。
4. `--follow` 布尔开关。
5. `--compact` 布尔开关。
6. 目标目录不存在时由配置校验报错。

**依赖：** 无。

**完成标准：** 文件只创建测试，不修改生产代码。

---

### T002 [P] 创建路径过滤测试

**文件：** 创建 `tests/test_path_filter.py`

**目标：** 表格驱动测试目标目录规范化与前缀匹配。

**测试必须覆盖：**

1. `/mnt/objstore` 命中目标目录自身。
2. `/mnt/objstore/a.txt` 命中。
3. `/mnt/objstore/sub/a.txt` 命中。
4. `/mnt/objstore2/a.txt` 不命中。
5. `/mnt/objstore-link/a.txt` 不因字符串相似而命中。
6. 目标目录末尾带 `/` 时仍规范化为无尾随斜杠。

**依赖：** 无。

**完成标准：** 文件只创建测试，不修改生产代码。

---

### T003 [P] 创建 fd 映射表测试

**文件：** 创建 `tests/test_fd_table.py`

**目标：** 表格驱动测试 Python 侧 `FdTable` 语义模型。

**测试必须覆盖：**

1. `open(pid, fd, path)` 后可 `resolve(pid, fd)`。
2. `close(pid, fd)` 后不可 resolve。
3. `close_range(pid, first, last)` 删除范围内 fd。
4. `dup(pid, old_fd, new_fd)` 复制路径映射。
5. 复制未知 fd 不应创建映射。
6. 不同 pid 的同一 fd 互不影响。

**依赖：** 无。

**完成标准：** 文件只创建测试，不修改生产代码。

---

### T004 [P] 创建事件格式化测试

**文件：** 创建 `tests/test_formatter.py`

**目标：** 测试 strace-like 事件行格式。

**测试必须覆盖：**

1. 成功事件输出 `= <ret>`。
2. 失败事件输出 `= -1 (errno=N)`。
3. 默认模式包含 `[time pid comm latency matched]` 前缀。
4. `compact=True` 时不包含前缀。
5. latency 纳秒格式化为 `us`。
6. fd 参数文本可包含 `fd=5</path>` 或 `fd=5<?>`。

**依赖：** 无。

**完成标准：** 文件只创建测试，不修改生产代码。

---

### T005 [P] 创建 header 与 summary 测试

**文件：** 创建 `tests/test_summary.py`

**目标：** 测试采集 header 与 summary footer。

**测试必须覆盖：**

1. header 包含 `target_dir`。
2. header 包含 `target_dir_realpath`。
3. header 包含 `kernel`。
4. header 包含 `mode=exit-only`。
5. header 包含 `output_format=strace-like`。
6. header 包含 `compact=<true|false>`。
7. header 包含 `skipped_syscalls`。
8. summary 统计 `total_events`。
9. summary 统计 `failed_events`。
10. summary 统计 `lost_events`。
11. summary 统计 syscall 分布。
12. summary 统计 errno 分布。
13. `lost_events > 0` 时 summary 包含不完整 warning。

**依赖：** 无。

**完成标准：** 文件只创建测试，不修改生产代码。

---

### T006 [P] 创建 syscall catalog 测试

**文件：** 创建 `tests/test_syscall_catalog.py`

**目标：** 测试 A-H syscall 白名单与内部 fd maintenance 集合。

**测试必须覆盖：**

1. A-H 分组包含 `spec.md` 中列出的 syscall。
2. 业务输出 syscall 集合包含 A-H 分组。
3. `read`、`write`、`close`、`close_range` 不在业务输出 syscall 集合中。
4. `close`、`close_range`、`dup`、`dup2`、`dup3`、`fcntl` 在 fd maintenance 集合中。
5. `open/openat/openat2/creat` 在 fd producer 集合中。

**依赖：** 无。

**完成标准：** 文件只创建测试，不修改生产代码。

---

### T007 [P] 创建 Linux 集成测试骨架

**文件：** 创建 `tests/test_integration_linux.py`

**目标：** 创建真实依赖集成测试骨架，非 Linux/root/BCC 环境显式跳过。

**测试必须覆盖：**

1. 非 Linux 环境 skip。
2. 非 root 环境 skip。
3. BCC 不可 import 时 skip。
4. Linux root + BCC 环境下创建临时目标目录。
5. 后续可启动 tracer 并运行真实 `touch/stat/mv` 命令。

**依赖：** 无。

**完成标准：** 文件只创建测试，不 mock BCC 行为。

---

### T008 运行全部测试确认初始失败

**文件：** 不修改文件。

**命令：**

```bash
python3 -m unittest discover -s tests -v
```

**预期：** 失败，原因应为 `posix-tracer` 脚本或目标函数/类尚不存在。

**依赖：** T001, T002, T003, T004, T005, T006, T007。

**完成标准：** 确认 Red 阶段成立；不要为通过测试修改测试期望。

## Phase 2：纯 Python 核心实现任务

### T009 创建生产入口文件与基础错误类型

**文件：** 创建 `posix-tracer`

**目标：** 创建最小生产模块，定义显式错误类型与 `main()` 骨架。

**必须实现：**

1. `UserError(Exception)`。
2. `TracerRuntimeError(Exception)`。
3. `main(argv=None) -> int`，捕获上述错误并返回明确退出码。
4. `if __name__ == "__main__": raise SystemExit(main())`。
5. 不导入 BCC；BCC 只能在后续运行时适配器中延迟导入。

**依赖：** T008。

**验证：**

```bash
python3 -m unittest discover -s tests -v
```

**预期：** 测试仍失败，但不应再因为模块不存在而失败。

---

### T010 实现 CLI 参数解析与配置校验

**文件：** 修改 `posix-tracer`

**目标：** 让 `tests/test_cli.py` 通过。

**必须实现：**

1. `TracerConfig` dataclass。
2. `parse_args(argv)`。
3. `build_config(args)` 或等价函数。
4. `--dir/-d`、`--output/-o`、`--duration/-t`、`--follow`、`--compact`。
5. 目标目录不存在或非目录时抛 `UserError`。
6. 不校验目标目录的文件系统类型。

**依赖：** T009。

**验证：**

```bash
python3 -m unittest tests.test_cli -v
```

**预期：** `tests/test_cli.py` 全部通过。

---

### T011 实现路径规范化与前缀匹配

**文件：** 修改 `posix-tracer`

**目标：** 让 `tests/test_path_filter.py` 通过。

**必须实现：**

1. `normalize_target_dir(path: str) -> str`。
2. `is_path_under_target(path: str, target_dir: str) -> bool`。
3. 目标目录自身命中。
4. 子路径命中。
5. `/mnt/objstore2` 不因前缀相似误命中。
6. 不做 symlink 真实对象解析。

**依赖：** T010。

**验证：**

```bash
python3 -m unittest tests.test_path_filter -v
```

**预期：** `tests/test_path_filter.py` 全部通过。

---

### T012 实现 Python 侧 fd 映射语义模型

**文件：** 修改 `posix-tracer`

**目标：** 让 `tests/test_fd_table.py` 通过。

**必须实现：**

1. `FdTable` 类。
2. `open(pid, fd, path)`。
3. `close(pid, fd)`。
4. `close_range(pid, first, last)`。
5. `dup(pid, old_fd, new_fd)`。
6. `resolve(pid, fd) -> str | None`。
7. 状态保存在实例字段中，不使用全局可变状态。

**依赖：** T011。

**验证：**

```bash
python3 -m unittest tests.test_fd_table -v
```

**预期：** `tests/test_fd_table.py` 全部通过。

---

### T013 实现 TraceEvent 与事件行格式化

**文件：** 修改 `posix-tracer`

**目标：** 让 `tests/test_formatter.py` 通过。

**必须实现：**

1. `TraceEvent` dataclass。
2. `format_latency(latency_ns)`。
3. `format_event_line(event, compact=False)`。
4. 成功返回值格式。
5. 失败 errno 格式。
6. 默认前缀格式。
7. compact 模式。

**依赖：** T012。

**验证：**

```bash
python3 -m unittest tests.test_formatter -v
```

**预期：** `tests/test_formatter.py` 全部通过。

---

### T014 实现 Header 与 Summary

**文件：** 修改 `posix-tracer`

**目标：** 让 `tests/test_summary.py` 通过。

**必须实现：**

1. `Summary` dataclass 或类。
2. `Summary.record_event(event)`。
3. `Summary.record_lost(count)`。
4. `format_header(config, kernel, bcc_version, skipped_syscalls)`。
5. `format_summary(summary)`。
6. lost events warning。

**依赖：** T013。

**验证：**

```bash
python3 -m unittest tests.test_summary -v
```

**预期：** `tests/test_summary.py` 全部通过。

---

### T015 实现 syscall catalog 常量

**文件：** 修改 `posix-tracer`

**目标：** 让 `tests/test_syscall_catalog.py` 的 catalog 断言通过。

**必须实现：**

1. `SYSCALL_GROUPS`。
2. `BUSINESS_SYSCALLS`。
3. `FD_MAINTENANCE_SYSCALLS`。
4. `FD_PRODUCER_SYSCALLS`。
5. A-H 分组严格匹配 `spec.md`。
6. read/write/close 不进入业务输出集合。

**依赖：** T014。

**验证：**

```bash
python3 -m unittest tests.test_syscall_catalog -v
```

**预期：** `tests/test_syscall_catalog.py` 中 catalog 相关测试通过。

---

### T016 扩展 BPF source builder 测试

**文件：** 修改 `tests/test_syscall_catalog.py`

**目标：** 在现有 catalog 测试文件中增加 BPF source builder 测试，保持每个任务只改一个主要文件。

**测试必须覆盖：**

1. `build_bpf_source(target_dir, enabled_syscalls)` 返回字符串。
2. 字符串包含 `BPF_HASH(entry_map` 或等价 map 定义。
3. 字符串包含 `BPF_HASH(fd_map` 或等价 map 定义。
4. 字符串包含 `BPF_PERF_OUTPUT(events)` 或等价 perf output。
5. 字符串包含目标目录常量。
6. 字符串包含 event struct。

**依赖：** T015。

**验证：**

```bash
python3 -m unittest tests.test_syscall_catalog -v
```

**预期：** 失败，原因是 `build_bpf_source` 尚未实现。

---

### T017 实现 BPF source builder

**文件：** 修改 `posix-tracer`

**目标：** 让 BPF source builder 测试通过。

**必须实现：**

1. `build_bpf_source(target_dir, enabled_syscalls)`。
2. 固定大小 event struct。
3. `entry_map`。
4. `fd_map`。
5. `events` perf output。
6. `MAX_PATH_LEN = 256`。
7. `MAX_XATTR_NAME_LEN = 64`。
8. 代码只生成字符串，不在该任务加载 BCC。

**依赖：** T016。

**验证：**

```bash
python3 -m unittest tests.test_syscall_catalog -v
python3 -m unittest discover -s tests -v
```

**预期：** 纯 Python 单元测试通过；Linux 集成测试在非 Linux/root/BCC 环境应 skip。

## Phase 3：BPF/BCC 运行时任务

### T018 创建 tracepoint 探测测试

**文件：** 创建 `tests/test_tracepoint_discovery.py`

**目标：** 测试 tracepoint 路径探测逻辑，使用临时目录模拟 tracing fs，不 mock BCC。

**测试必须覆盖：**

1. enter 与 exit 路径都存在时 syscall 可用。
2. enter 缺失时 syscall 跳过。
3. exit 缺失时 syscall 跳过。
4. 返回 `enabled_syscalls` 与 `skipped_syscalls`。

**依赖：** T017。

**验证：**

```bash
python3 -m unittest tests.test_tracepoint_discovery -v
```

**预期：** 失败，原因是 tracepoint 探测函数尚未实现。

---

### T019 实现 tracepoint 探测

**文件：** 修改 `posix-tracer`

**目标：** 让 `tests/test_tracepoint_discovery.py` 通过。

**必须实现：**

1. `discover_tracepoints(syscalls, tracing_events_dir="/sys/kernel/debug/tracing/events/syscalls")`。
2. 只在 `sys_enter_<name>` 与 `sys_exit_<name>` 都存在时启用。
3. 返回 enabled/skipped。
4. 显式处理 tracing 目录不存在的情况。

**依赖：** T018。

**验证：**

```bash
python3 -m unittest tests.test_tracepoint_discovery -v
```

**预期：** `tests/test_tracepoint_discovery.py` 全部通过。

---

### T020 创建 OutputWriter 测试

**文件：** 创建 `tests/test_output_writer.py`

**目标：** 测试 stdout/file/follow 写入行为。

**测试必须覆盖：**

1. 未指定 output 时写 stdout。
2. 指定 output 时写文件。
3. 指定 output + follow 时同时写文件与 stdout。
4. 输出文件无法创建时抛 `UserError`。
5. `close()` 可重复调用且显式 flush。

**依赖：** T019。

**验证：**

```bash
python3 -m unittest tests.test_output_writer -v
```

**预期：** 失败，原因是 `OutputWriter` 尚未实现。

---

### T021 实现 OutputWriter

**文件：** 修改 `posix-tracer`

**目标：** 让 `tests/test_output_writer.py` 通过。

**必须实现：**

1. `OutputWriter` 类。
2. 构造时显式处理输出文件打开错误。
3. `write_line(line)`。
4. `flush()`。
5. `close()`。
6. follow 逻辑。

**依赖：** T020。

**验证：**

```bash
python3 -m unittest tests.test_output_writer -v
```

**预期：** `tests/test_output_writer.py` 全部通过。

---

### T022 实现 BCC 运行时适配器

**文件：** 修改 `posix-tracer`

**目标：** 接入真实 BCC 运行时生命周期。

**必须实现：**

1. `TracerRuntime` 类。
2. BCC 延迟 import。
3. BPF 加载。
4. tracepoint attach。
5. perf buffer callback。
6. lost event callback。
7. duration / Ctrl-C 停止。
8. header 写入。
9. event line 写入。
10. summary stderr 与 output footer。
11. BCC 不存在、BPF 加载失败、无可用 tracepoint 时显式抛 `TracerRuntimeError`。

**依赖：** T021。

**验证：**

```bash
python3 -m unittest discover -s tests -v
```

**预期：** 纯 Python 测试通过；非 Linux/root/BCC 环境集成测试 skip。

## Phase 4：集成测试与验收任务

### T023 完善 Linux 集成测试执行逻辑

**文件：** 修改 `tests/test_integration_linux.py`

**目标：** 将 T007 骨架扩展为真实 Linux 集成测试。

**测试必须覆盖：**

1. 启动 tracer，目标目录为临时目录。
2. 执行真实 `touch`、`stat`、`mv` 命令。
3. 验证日志有 header。
4. 验证日志有 summary。
5. 验证存在 open/stat/rename 或平台对应 syscall。
6. 验证不输出 read/write/close 业务事件。

**依赖：** T022。

**验证：**

```bash
sudo python3 -m unittest tests.test_integration_linux -v
```

**预期：** Linux root + BCC 环境通过；其他环境 skip。

---

### T024 执行全量单元测试

**文件：** 不修改文件。

**命令：**

```bash
python3 -m unittest discover -s tests -v
```

**依赖：** T023。

**完成标准：**

1. 所有纯 Python 单元测试通过。
2. Linux 集成测试在当前环境不满足条件时明确 skip。
3. 不允许存在非预期 error/failure。

---

### T025 执行 Linux root 手动 smoke test

**文件：** 不修改文件。

**命令：**

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

**依赖：** T024。

**完成标准：**

1. `/tmp/trace.log` 开头包含 header。
2. 事件行为 strace-like 格式。
3. 文件尾部包含 summary。
4. stderr 输出 summary。
5. 不输出 read/write/close 业务事件。
6. 如发生 lost events，summary 包含 warning，但退出码仍为 0。

## 执行规则

1. 必须先完成 T001-T008，再进入任何生产实现任务。
2. 每个实现任务只修改 `posix-tracer` 一个主要文件。
3. 每个测试任务只创建或修改一个 `tests/*.py` 文件。
4. 不允许引入非标准库测试依赖。
5. 不允许用 mock 替代 BCC 集成测试；不可用时显式 skip。
6. 每个任务完成后运行对应验证命令。
7. 若验证失败，必须先修复当前任务，不得继续后续任务。
8. 不实现 `spec.md` 明确列为后续增强的能力。
