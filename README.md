# posix-tracer

`posix-tracer` 是一个基于 Python + eBPF/BCC 的指定目录 POSIX 调用追踪器，用于捕获访问指定目录的文件系统 metadata/control 类 syscall，辅助评估使用场景的 POSIX 语义兼容性。

## 1. 编译说明

本项目是 **Python 单文件脚本 + BCC/eBPF**，不需要传统编译。

当前主程序：

```text
posix-tracer
```

可以用 Python 自带工具做语法检查：

```bash
python3 -m py_compile posix-tracer
```

运行单元测试：

```bash
python3 -m unittest discover -s tests -v
```

在非 Linux、非 root 或缺少 BCC 的环境下，Linux/BCC 集成测试会被跳过，只运行纯 Python 单元测试。

## 2. 运行依赖

### 2.1 系统要求

MVP 目标运行环境：

```text
Linux x86_64
kernel >= 4.18
推荐 kernel >= 5.4
root 权限
BCC / iovisor bcc Python 绑定
```

macOS / Darwin 不能运行 eBPF/BCC 追踪功能，只能跑纯 Python 单元测试。

注意：BCC Python 绑定需要安装到实际运行脚本的 Python 解释器可见的位置。如果使用 venv/conda，系统包 `python3-bpfcc` 可能不会被该解释器自动找到。

### 2.2 Ubuntu / Debian 依赖安装示例

不同发行版包名可能略有差异。

```bash
sudo apt-get update
sudo apt-get install -y \
  python3 \
  python3-bpfcc \
  bpfcc-tools \
  linux-headers-$(uname -r)
```

验证 BCC Python 绑定：

```bash
python3 - <<'PY'
from bcc import BPF
print("BCC python binding OK")
PY
```

如果成功，会输出：

```text
BCC python binding OK
```

### 2.3 检查 tracepoint 是否存在

```bash
sudo ls /sys/kernel/debug/tracing/events/syscalls | head
```

如果 `/sys/kernel/debug/tracing` 不存在，可能需要挂载 debugfs：

```bash
sudo mount -t debugfs debugfs /sys/kernel/debug
```

## 3. 打包方式

### 3.1 单文件分发

最简单方式是直接分发：

```text
posix-tracer
```

赋予执行权限：

```bash
chmod +x posix-tracer
```

然后运行：

```bash
sudo ./posix-tracer -d /mnt/objstore -o trace.log -t 60
```

### 3.2 tar.gz 打包

在项目根目录执行：

```bash
tar -czf posix-tracer.tar.gz \
  posix-tracer \
  specs \
  tests \
  AGENT.md \
  constitution.md \
  README.md
```

解包：

```bash
tar -xzf posix-tracer.tar.gz
```

运行测试：

```bash
python3 -m unittest discover -s tests -v
```

### 3.3 安装到系统路径

可以安装为系统命令：

```bash
sudo install -m 755 posix-tracer /usr/local/bin/posix-tracer
```

然后使用：

```bash
sudo posix-tracer -d /mnt/objstore -o trace.log -t 60
```

## 4. 基本使用

### 4.1 最小用法

```bash
sudo python3 posix-tracer -d /mnt/objstore
```

含义：

- 追踪 `/mnt/objstore` 目录下的 POSIX metadata/control syscall。
- 输出到 stdout。
- 一直运行，直到 Ctrl-C。

注意：目标目录路径会写入 BPF 程序用于内核侧前缀匹配，UTF-8 编码长度必须小于 256 bytes。当前实现的 `target_dir` 匹配策略是**字面绝对路径前缀匹配**，不会把事件路径解析成 realpath 后再比较。如果目标目录或 workload 访问路径包含符号链接，trace 结果可能漏报或误报；日志 header 中的 `target_dir_realpath` 仅用于辅助识别真实目录。为减少歧义，建议直接传入真实路径，例如：

```bash
sudo python3 posix-tracer -d "$(readlink -f /mnt/objstore)"
```

### 4.2 追踪 60 秒并写入文件

```bash
sudo python3 posix-tracer \
  -d /mnt/objstore \
  -o trace.log \
  -t 60
```

输出文件以 append 模式打开，多次运行会追加到同一个日志文件。

### 4.3 写文件同时打印到 stdout

```bash
sudo python3 posix-tracer \
  -d /mnt/objstore \
  -o trace.log \
  -t 60 \
  --follow
```

### 4.4 紧凑输出模式

默认事件行类似：

```text
[12:01:03.123456 pid=1234 comm=python3 latency=34us matched=path] getxattr('/mnt/objstore/archive/data.tar', size=255) = -1 (errno=95)
```

使用 `--compact` 后，事件行去掉前缀：

```bash
sudo python3 posix-tracer \
  -d /mnt/objstore \
  -o trace.log \
  -t 60 \
  --compact
```

输出类似：

```text
getxattr('/mnt/objstore/archive/data.tar', size=255) = -1 (errno=95)
```

### 4.5 可选 xattr name 捕获

默认情况下，事件结构不包含 xattr name 字段，以减少 perf buffer 带宽占用。需要分析具体 xattr key 时，可以显式启用：

```bash
sudo python3 posix-tracer \
  -d /mnt/objstore \
  -o trace.log \
  -t 60 \
  --capture-xattr-name
```

启用后，`getxattr`、`setxattr`、`removexattr` 及对应 `l*` / `f*` 形式会尝试输出 `name=...`。该字段使用 256 字节缓冲区，超过缓冲区的 xattr name 会被内核侧字符串读取截断。

## 5. 推荐 smoke test

在 Linux + root + BCC 环境中执行。

### 5.1 终端 1：启动 tracer

```bash
mkdir -p /tmp/posix-tracer-target

sudo python3 posix-tracer \
  -d /tmp/posix-tracer-target \
  -o /tmp/trace.log \
  -t 10 \
  --follow
```

### 5.2 终端 2：制造文件系统操作

```bash
touch /tmp/posix-tracer-target/a
stat /tmp/posix-tracer-target/a
mv /tmp/posix-tracer-target/a /tmp/posix-tracer-target/b
```

### 5.3 查看日志

```bash
cat /tmp/trace.log
```

日志应包含：

```text
# posix-tracer started_at=...
# target_dir=...
# target_dir_realpath=...
# target_match=literal absolute path prefix
# target_match_warning=symlinked target directories or access paths can cause missed or ambiguous events; pass the realpath, for example readlink -f <dir>, to reduce ambiguity
# capture_xattr_name=false
# xattr_name_buffer_bytes=0
# kernel=...
# bcc_version=...
# mode=exit-only
# output_format=strace-like
# compact=false
# skipped_syscalls=...
```

结束时应包含 summary：

```text
# summary:
# total_events=...
# failed_events=...
# lost_events=...
# syscall_counts:
# errno_counts:
```

## 6. 退出码说明

| 退出码 | 含义 |
| --- | --- |
| `0` | 正常结束，包括 duration 到期、Ctrl-C、存在 syscall 失败事件、存在 lost events。 |
| `1` | 运行时错误，例如 BCC 不可用、BPF 加载失败、无可用 tracepoint。 |
| `2` | 用户输入错误，例如缺少 `--dir`、目标目录不存在、目标路径不是目录、输出文件无法打开。 |

## 7. 常见问题

### 7.1 `error: no usable syscall tracepoints found`

可能原因：

1. 当前不是 Linux。
2. 没有挂载 debugfs。
3. 内核没有启用 syscall tracepoint。
4. 权限不足。
5. `/sys/kernel/debug/tracing/events/syscalls` 不存在。

检查：

```bash
uname -a
sudo ls /sys/kernel/debug/tracing/events/syscalls
```

### 7.2 `BCC Python bindings are not available`

说明 Python 找不到 BCC 绑定。

Ubuntu/Debian 可尝试：

```bash
sudo apt-get install -y python3-bpfcc bpfcc-tools
```

验证：

```bash
python3 - <<'PY'
from bcc import BPF
print("ok")
PY
```

### 7.3 非 Linux 环境能做什么？

当前 macOS/Darwin 环境只能运行纯 Python 测试：

```bash
python3 -m unittest discover -s tests -v
```

不能运行真实 eBPF 追踪。

## 8. 当前实现状态说明

当前代码已经具备：

- CLI
- 配置校验
- 路径匹配逻辑
- fd 映射模型
- 日志格式化
- summary
- tracepoint 探测
- BCC runtime 生命周期管理
- eBPF entry/exit tracepoint 参数采集
- eBPF 路径前缀过滤
- eBPF fd map 维护，覆盖 open 成功建表、close 删除、dup/fcntl duplicate 复制
- perf buffer 事件上报与 lost event 统计
- Python 侧 perf event 解码、事件行写入与 summary 统计
- Linux 集成测试

当前实现优先覆盖 MVP 的通用采集链路和 smoke test 关键 syscall。参数格式化采用通用字段输出，尚未对每个 syscall family 做完整的 flags 名称、人类可读 errno 名称、复杂结构体展开或 openat2 `open_how` 细节解析。

当前版本仍需要在 Linux + root + BCC 环境中执行以下验收：

```bash
sudo python3 -m unittest tests.test_integration_linux -v
```

非 Linux 环境只能验证纯 Python 逻辑；集成测试会被显式跳过。
