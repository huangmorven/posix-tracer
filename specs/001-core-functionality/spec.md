# fuse-posix-tracer 核心功能规格说明

## 1. 背景与目标

`fuse-posix-tracer` 是一个基于 Python + eBPF/BCC 的 Linux 文件系统 syscall 追踪器，用于对指定目录下的 FUSE workload 进行 POSIX 语义兼容性评估。

MVP 的核心目标是：用户指定一个目标目录，工具在系统范围内自动捕获所有访问该目录的进程所发起的元数据与控制类 POSIX 文件系统调用，并输出紧凑、可离线分析的 strace-like 日志。

第一版定位为**离线兼容性评估采集工具**，而不是生产级长期采样系统。典型使用方式是：用户启动 tracer，运行一段真实 workload 或测试 workload，停止 tracer 后分析日志中的 syscall 分布、失败 errno、xattr、rename、flock、fsync 等语义敏感调用表现。

实时观察仅作为辅助能力支持：未指定输出文件时事件直接输出到 stdout；指定输出文件时可通过 `--follow` 同时写文件并打印到 stdout。

## 2. 非目标

MVP 不追求以下能力：

1. 不作为长期生产常驻采样系统。
2. 不提供生产级零丢失保证。
3. 不提供完整 VFS 对象归属判定。
4. 不提供完整 symlink、bind mount、mount namespace、chroot 语义解析。
5. 不提供 `-- command...` 子进程启动模式。
6. 不默认输出 JSON Lines、CSV 或复杂分析报告。
7. 不检测目标目录是否为 FUSE 文件系统；目标目录是否为 FUSE 挂载目录由用户保证。
8. 不追踪并输出 read/write/close 及其变体作为业务事件。

## 3. MVP 使用方式

```bash
sudo python3 fuse_posix_tracer.py -d /mnt/objstore [-o output.log] [-t 60] [--follow] [--compact]
```

### 3.1 CLI 参数

MVP 只支持以下参数：

| 参数 | 必填 | 含义 |
| --- | --- | --- |
| `-d, --dir PATH` | 是 | 目标追踪目录。工具按该目录路径前缀过滤事件。 |
| `-o, --output FILE` | 否 | 输出文件。不指定时输出到 stdout。 |
| `-t, --duration SEC` | 否 | 采集时长，单位秒。不指定时持续运行直到 Ctrl-C。 |
| `--follow` | 否 | 当指定 `--output` 时，同时将事件打印到 stdout。未指定 `--output` 时天然输出 stdout。 |
| `--compact` | 否 | 仅影响事件行：去掉 `[time pid comm latency matched]` 前缀，只输出 syscall 文本。 |

以下能力不进入 MVP，作为后续增强：

- `--include-groups`
- `--exclude-groups`
- `--list-groups`
- `--format jsonl`
- `--no-header`
- `--fail-on-lost-events`
- `-- command...`

## 4. 运行环境

MVP 支持范围：

1. Linux x86_64。
2. Linux kernel >= 4.18，推荐 >= 5.4。
3. 已安装 BCC / iovisor bcc Python 绑定。
4. 以 root 运行，或具备加载 eBPF、使用 perf buffer 所需的 capability。
5. 使用 syscall tracepoint，例如 `syscalls:sys_enter_openat`、`syscalls:sys_exit_openat`。

运行时应探测目标 syscall tracepoint 是否存在。不存在的 syscall 自动跳过，并在 header 或 stderr warning 中记录。缺失 tracepoint 不应导致整体启动失败，除非核心 BPF 程序无法加载或没有任何可用追踪点。

MVP 不承诺：

1. 32-bit compat syscall 覆盖。
2. arm64 或其他架构支持。
3. 容器、mount namespace、chroot 下的完整路径归属准确性。

## 5. 追踪范围

MVP 默认覆盖以下 A-H 八类元数据与控制类 POSIX 文件系统调用。

### A. 路径解析 / 打开类

- `open`
- `openat`
- `openat2`
- `creat`
- `name_to_handle_at`

### B. 元数据读取类

- `stat`
- `lstat`
- `fstat`
- `newfstatat` / `fstatat`
- `statx`
- `access`
- `faccessat`
- `faccessat2`
- `readlink`
- `readlinkat`

### C. 元数据修改类

- `chmod`
- `fchmod`
- `fchmodat`
- `chown`
- `fchown`
- `lchown`
- `fchownat`
- `utime`
- `utimes`
- `utimensat`
- `futimesat`
- `truncate`
- `ftruncate`

### D. 目录操作类

- `mkdir`
- `mkdirat`
- `rmdir`
- `getdents`
- `getdents64`

### E. 链接 / 重命名 / 删除类

- `link`
- `linkat`
- `symlink`
- `symlinkat`
- `unlink`
- `unlinkat`
- `rename`
- `renameat`
- `renameat2`

### F. fd 控制 / 同步 / 定位类

- `fcntl`
- `ioctl`
- `flock`
- `fsync`
- `fdatasync`
- `syncfs`
- `lseek`

### G. 扩展属性类

- `getxattr`
- `lgetxattr`
- `fgetxattr`
- `setxattr`
- `lsetxattr`
- `fsetxattr`
- `listxattr`
- `llistxattr`
- `flistxattr`
- `removexattr`
- `lremovexattr`
- `fremovexattr`

### H. 文件空间控制类

- `fallocate`

### 5.1 默认排除输出的 syscall

以下 syscall 不作为业务事件输出：

- `read` 及其变体
- `write` 及其变体
- `close`
- `close_range`

注意：`close`、`close_range` 仍可能作为内部 fd 映射维护事件被追踪，但默认不输出到日志。

## 6. 过滤语义

### 6.1 目录过滤

MVP 使用“路径字符串前缀 + fd→path 映射”的可解释过滤方案。

1. 启动时将 `--dir` 转换为规范化目标目录路径。
2. 对带路径参数的 syscall，在 syscall entry 阶段读取用户态路径字符串。
3. 若路径字符串以目标目录前缀开头，则该 syscall 命中。
4. 用户态输出中保留原始路径，并尽力补充规范化路径相关信息。
5. 第一版不承诺完全解析 symlink、`..`、bind mount、mount namespace、chroot 等造成的真实路径等价性。

### 6.2 fd-based syscall 过滤

对于 `fstat`、`fsync`、`ftruncate`、`fchmod`、`fchown`、`fgetxattr`、`flock`、`lseek` 等基于 fd 的 syscall，MVP 通过 fd→path 映射判断是否命中目标目录。

fd→path 映射来源：

1. `open`、`openat`、`openat2`、`creat` 成功返回 fd 后建立映射。
2. 如果打开路径命中目标目录，则记录该进程的 fd 对应路径。
3. open 系列 syscall 失败时不建立 fd 映射。

### 6.3 多路径 syscall 过滤

对 `rename`、`renameat`、`renameat2`、`link`、`linkat`、`symlink`、`symlinkat` 等多路径 syscall，采用：

> 任意一个路径命中目标目录即记录。

日志中应标注命中侧：

- `matched=src`
- `matched=dst`
- `matched=src,dst`
- `matched=path`
- `matched=fd`

示例：

```text
[12:01:03.123456 pid=1234 comm=mv latency=80us matched=dst] rename("/tmp/a", "/mnt/objstore/b") = -1 (errno=18)
[12:01:03.123456 pid=1234 comm=mv latency=75us matched=src] rename("/mnt/objstore/a", "/tmp/b") = 0
[12:01:03.123456 pid=1234 comm=mv latency=70us matched=src,dst] rename("/mnt/objstore/a", "/mnt/objstore/b") = 0
```

## 7. fd→path 映射维护

MVP 将 fd 映射维护分为“内部追踪”和“日志输出”。

### 7.1 内部必须追踪

以下 syscall 用于维护 fd→path 映射，但默认不输出为业务日志：

- `close`
- `close_range`
- `dup`
- `dup2`
- `dup3`
- `fcntl` 中的 fd duplicate 操作，例如 `F_DUPFD`、`F_DUPFD_CLOEXEC`

### 7.2 fd 映射规则

1. `open/openat/openat2/creat` 成功返回 fd 后，如果路径命中目标目录，则建立当前进程内的 fd→path 映射。
2. `close(fd)` 成功后删除对应 fd 映射。
3. `close_range(first, last, flags)` 成功后删除范围内 fd 映射。
4. `dup/dup2/dup3/fcntl(F_DUPFD*)` 成功后复制旧 fd 的路径映射到新 fd。
5. fd-based syscall 输出时尽量使用 `fd=5</mnt/objstore/a.txt>` 格式补充路径。
6. 若 fd 路径未知，则输出 `fd=5<?>`。

### 7.3 MVP 已知限制

MVP 不追踪或不完整保证 fork/clone 后的 fd 继承关系。即：

- 同一进程内由 open 系列建立的 fd 映射应尽量可靠。
- dup 系列导致的 fd 映射变化应尽量可靠。
- fork/clone 继承 fd 的场景不保证完整准确，必要时作为后续增强。

## 8. 事件记录时机

MVP 默认只在 syscall exit 输出一行完整事件。

1. syscall entry 阶段用于内部保存参数、路径、开始时间、匹配状态和 fd 关联上下文。
2. syscall exit 阶段获取返回值、errno、latency，并输出一行完整 strace-like 事件。
3. entry 事件不默认输出。
4. `--emit-entry` 不进入 MVP，可作为后续调试增强。

## 9. 参数记录粒度

MVP 参数记录原则：

1. 完整记录 syscall 的路径参数。
2. 完整记录 syscall 的标量参数，例如 flags、mode、fd、size、offset、request、cmd 等。
3. fd 参数尽量补充解析后的路径。
4. 复杂指针结构体第一版只做摘要或选择性展开。
5. 返回值和 errno 必须记录。
6. latency 必须记录。

### 9.1 复杂结构体处理

复杂结构体不要求完整展开：

- `stat` / `fstat` / `statx`：MVP 不打印完整结构体内容，只记录调用参数、返回值和 errno。
- `utimensat` / `utime` / `utimes`：可记录时间参数指针是否为 NULL，或记录摘要，不要求完整解析 timespec/timeval 数组。
- `ioctl`：记录 `request` 和 `arg` 地址，不解析具体 ioctl 结构体。
- `openat2`：作为例外，应尽量读取 `struct open_how` 中的 `flags`、`mode`、`resolve`，因为它们对路径解析和兼容性分析重要。

## 10. 输出格式

MVP 默认输出紧凑 strace-like 单行文本格式。

默认事件行格式：

```text
[12:01:03.123456 pid=1234 comm=python3 latency=34us matched=path] getxattr("/mnt/objstore/archive/data.tar", name="security.selinux", size=255) = -1 (errno=95)
```

`--compact` 事件行格式：

```text
getxattr("/mnt/objstore/archive/data.tar", name="security.selinux", size=255) = -1 (errno=95)
```

### 10.1 返回值与 errno

1. 成功 syscall 记录返回值：

```text
openat(AT_FDCWD, "/mnt/objstore/a.txt", flags=O_RDONLY|O_CLOEXEC, mode=0000) = 5
```

2. 失败 syscall 记录返回值和 errno：

```text
setxattr("/mnt/objstore/a.txt", name="user.key", value_ptr=0x7f..., size=12, flags=0) = -1 (errno=95)
```

3. 所有命中目标目录的 syscall，无论成功失败都记录。

### 10.2 header

输出开头应包含 `#` 注释形式的采集配置快照。

示例：

```text
# fuse-posix-tracer started_at=2026-05-11T12:00:00Z
# target_dir=/mnt/objstore
# target_dir_realpath=/mnt/objstore
# kernel=5.15.0-...
# bcc_version=...
# mode=exit-only
# output_format=strace-like
# compact=false
# skipped_syscalls=openat2,faccessat2
```

说明：

1. 事件分析器应跳过 `#` 开头行。
2. `--compact` 只影响事件行，不移除 header。
3. `--no-header` 不进入 MVP。

### 10.3 summary footer

MVP 在退出时输出极简 summary：

- 总事件数。
- 失败事件数。
- 丢失事件数。
- syscall 分布。
- errno 分布。

summary 默认打印到 stderr。如果指定 `--output`，也在输出文件末尾追加 `# summary` 注释 footer。

示例：

```text
# summary:
# total_events=12891
# failed_events=432
# lost_events=37
# warning=trace may be incomplete because perf buffer dropped events
# syscall_counts:
#   openat=3021
#   statx=2880
#   getxattr=900
# errno_counts:
#   errno=95 count=120
#   errno=18 count=8
```

## 11. 丢事件处理

事件通过 perf buffer 从内核态传递到用户态。MVP 必须检测 perf buffer lost events。

要求：

1. 运行中如发生 lost events，应向 stderr 打印 warning。
2. 退出 summary 中记录 `lost_events=N`。
3. 如果 `lost_events > 0`，summary 应标明日志可能不完整。
4. 默认不因 lost events 返回非 0。
5. 只有启动失败、参数错误、BPF 加载失败等硬错误才返回非 0。
6. `--fail-on-lost-events` 作为后续增强，不进入 MVP。

## 12. 成功与失败判定

### 12.1 正常退出

以下情况退出码应为 0：

1. 达到 `--duration` 指定时间后正常停止。
2. 用户 Ctrl-C 停止，且已正常输出 summary。
3. 采集过程中存在 syscall 失败事件。
4. 采集过程中存在 perf buffer lost events，但 tracer 本身仍正常运行。

### 12.2 异常退出

以下情况退出码应非 0：

1. 参数错误，例如缺少 `--dir`。
2. 目标目录不存在或不是目录。
3. 无 root/eBPF/perf 权限导致无法加载或附加 BPF 程序。
4. BCC 不可用。
5. BPF 程序加载失败。
6. 输出文件无法创建或写入。
7. 没有任何可用 syscall tracepoint 可追踪。

## 13. 架构设计

MVP 采用 Python 用户态控制程序 + BCC eBPF 程序。

### 13.1 用户态职责

Python 程序负责：

1. 解析 CLI 参数。
2. 校验目标目录。
3. 生成或加载 BPF 程序。
4. 探测 syscall tracepoint 是否存在。
5. 附加 syscall entry/exit tracepoint。
6. 从 perf buffer 读取事件。
7. 格式化 strace-like 日志。
8. 写入 stdout / output file。
9. 维护 summary 统计。
10. 处理 lost events。
11. 处理 Ctrl-C 和 duration 到期。

### 13.2 内核态职责

eBPF 程序负责：

1. 在 syscall entry 读取必要参数。
2. 对路径参数执行目标目录前缀匹配。
3. 记录 entry 上下文，包括开始时间、参数摘要、路径摘要、匹配状态。
4. 在 syscall exit 获取返回值。
5. 对 open 成功返回 fd 的场景产生 fd 映射更新事件或在 BPF map 中维护映射。
6. 对 close/close_range/dup/fcntl dup 维护 fd 映射。
7. 对命中的业务 syscall 通过 perf buffer 发送事件到用户态。

### 13.3 状态管理

至少需要以下状态：

1. entry context map：以线程 id 或 pid/tid 作为 key，保存 syscall entry 参数和开始时间。
2. fd path map：以进程标识 + fd 作为 key，保存路径摘要。
3. perf event buffer：向用户态传递完整事件或事件摘要。

实现时应优先保持简单，避免不必要抽象。

## 14. 准确性承诺与限制

### 14.1 MVP 尽力保证

1. 对路径参数直接以目标目录前缀开头的 syscall，能够记录。
2. 对由成功 `open/openat/openat2/creat` 建立的 fd，后续 fd-based metadata/control syscall 能够记录。
3. 多路径 syscall 任意路径命中即记录。
4. 成功和失败调用都记录。
5. `close/close_range/dup/dup2/dup3/fcntl dup` 内部维护 fd 表，以降低 fd 复用误判。
6. 每条输出事件包含返回值、失败 errno、latency。
7. perf buffer lost events 会被统计和暴露。

### 14.2 MVP 不保证

1. symlink 解析后的真实路径一定能匹配目标目录。
2. `..`、相对路径、`chroot`、mount namespace、bind mount 下的真实对象归属完全准确。
3. fork/clone 后继承 fd 的映射完全准确。
4. 未经 open 系列建立映射的 fd-based syscall 一定能解析到路径。
5. 32-bit compat syscall、非 x86_64 架构全覆盖。
6. BPF perf buffer 满时事件零丢失。
7. `ioctl`、`stat` 等复杂结构体内容完整解析。
8. 目标目录一定是 FUSE 文件系统；MVP 不检测文件系统类型。

## 15. 测试与验收标准

### 15.1 基础验收

给定目标目录 `/mnt/objstore`，当进程执行：

```bash
stat /mnt/objstore/a
getfattr -n security.selinux /mnt/objstore/a
touch /mnt/objstore/b
mv /tmp/a /mnt/objstore/b
```

tracer 应输出对应命中的 metadata/control syscall 事件。

### 15.2 排除 read/write/close 输出

当进程执行：

```bash
cat /mnt/objstore/a > /dev/null
```

tracer 可因 open/stat 等记录事件，但不应输出 read/write/close 事件。

### 15.3 fd-based syscall

当进程成功打开 `/mnt/objstore/a` 并随后调用 `fstat(fd)`、`fsync(fd)`、`ftruncate(fd)` 等 fd-based syscall，tracer 应能通过 fd→path 映射记录事件，并在日志中体现 fd 对应路径。

### 15.4 fd 复用

当进程：

1. 打开 `/mnt/objstore/a` 得到 fd 5。
2. 关闭 fd 5。
3. 打开 `/tmp/b` 再次得到 fd 5。
4. 调用 `fstat(5)`。

tracer 不应将最后的 `fstat(5)` 错误归因到 `/mnt/objstore/a`。

### 15.5 多路径 syscall

以下任意路径命中的调用都应记录：

```text
rename("/tmp/a", "/mnt/objstore/b")
rename("/mnt/objstore/a", "/tmp/b")
rename("/mnt/objstore/a", "/mnt/objstore/b")
```

日志中应标注 `matched=dst`、`matched=src` 或 `matched=src,dst`。

### 15.6 失败 syscall

失败 syscall 也必须记录：

```text
setxattr("/mnt/objstore/a", name="security.selinux", ...) = -1 (errno=95)
rename("/mnt/objstore/a", "/tmp/b") = -1 (errno=18)
```

### 15.7 summary

采集结束后应输出 summary，至少包含：

1. `total_events`
2. `failed_events`
3. `lost_events`
4. syscall counts
5. errno counts

## 16. 后续增强候选

以下能力不进入 MVP，但可作为后续版本规划：

1. `--format jsonl`：输出机器友好的 JSON Lines。
2. `--include-groups` / `--exclude-groups` / `--list-groups`：按 syscall group 控制采集范围。
3. `-- command...`：启动 tracer 后运行指定 workload，workload 结束后自动退出。
4. `--fail-on-lost-events`：适配严格 CI。
5. `--emit-entry`：输出 entry 事件，用于定位阻塞 syscall。
6. `--no-header`：禁止输出 header。
7. 更完整的 fork/clone fd 继承追踪。
8. mount namespace / chroot / bind mount 感知。
9. symlink / `..` / realpath 更严格解析。
10. FUSE 文件系统类型检测和记录。
11. 独立 analyze/report 子命令，生成 POSIX 兼容性风险报告。
12. arm64 支持矩阵。
13. 更完整的 `statx`、`ioctl`、`utimensat` 结构体解析。

