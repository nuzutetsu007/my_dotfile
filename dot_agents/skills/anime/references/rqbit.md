# rqbit 配置

唯一 BitTorrent 下载工具。v8.1.1。

## 下载链接

```
https://github.com/ikatson/rqbit/releases/download/v9.0.0-beta.2/rqbit-linux-amd64
```

## 安装

```bash
# 下载
curl -sL "https://github.com/ikatson/rqbit/releases/download/v9.0.0-beta.2/rqbit-linux-amd64" -o /tmp/rqbit
chmod +x /tmp/rqbit

# 有 sudo:
sudo cp /tmp/rqbit /usr/local/bin/rqbit

# 无 sudo:
mkdir -p ~/.local/bin
cp /tmp/rqbit ~/.local/bin/rqbit
```

## 检测

```bash
command -v rqbit || ~/.local/bin/rqbit --version 2>/dev/null
```

## 常用命令

### 单集下载

```bash
rqbit download -o "{output_dir}" -e --overwrite "{magnet_url}"
```

### 文件名过滤（只下特定文件）

```bash
rqbit download -o "{output_dir}" -r ".*{episode_padded}.*" -e --overwrite "{magnet_url}"
```

### 查看种子内容

```bash
rqbit download -o /tmp/rqbit-list -l "{magnet_url}"
```

### 参数说明

| 参数 | 作用 |
|------|------|
| `-o {path}` | 输出目录 |
| `-e` | 下载完成后退出 (`--exit-on-finish`) |
| `--overwrite` | 覆盖已有文件 |
| `-l` | 仅列出种子内容，不下 |
| `-r "{regex}"` | 文件名过滤正则 |

## 后台队列

```bash
# 启动下载
rqbit download -o "{dir}" -e --overwrite "{magnet}" > "{log_file}" 2>&1 &
PID=$!
echo $PID >> /tmp/rqbit-pids-{anime_id}.txt

# 等待完成
wait $PID

# 清理
rm -f /tmp/rqbit-pids-{anime_id}.txt
```

并发控制: 同时 2-3 个任务。