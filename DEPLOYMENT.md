# 部署指南

本文档说明如何将错别字检测服务部署到生产服务器。

## 前提条件

- Python 3.11+ 已安装
- 服务器至少 2GB 内存（模型加载需要）
- 约 500MB 磁盘空间（模型文件 + 依赖）

## 部署步骤

### 1. 上传项目文件

```bash
# 在本地打包项目
cd /Users/yuzhe/Desktop/ai/wrong-word
tar -czf wrong-word.tar.gz *.py requirements.txt

# 上传到服务器
scp wrong-word.tar.gz user@your-server:/path/to/deploy/

# 在服务器上解压
ssh user@your-server
cd /path/to/deploy
tar -xzf wrong-word.tar.gz
```

### 2. 服务器端环境配置

```bash
# 创建虚拟环境
python3.12 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 下载 MacBERT 模型（约 391MB）
mkdir -p models
huggingface-cli download shibing624/macbert4csc-base-chinese \
  --local-dir models/macbert4csc
```

### 3. 测试启动

```bash
# 单进程测试
uvicorn app:app --host 0.0.0.0 --port 8000

# 访问健康检查接口
curl http://localhost:8000/health
# 预期返回: {"status":"ok","model_loaded":true}
```

### 4. 使用 systemd 配置开机自启

创建 systemd 服务文件 `/etc/systemd/system/wrong-word.service`：

```ini
[Unit]
Description=Chinese Text Correction API
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/path/to/deploy
Environment="PATH=/path/to/deploy/venv/bin"
ExecStart=/path/to/deploy/venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启用并启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable wrong-word
sudo systemctl start wrong-word
sudo systemctl status wrong-word
```

### 5. 使用 Nginx 反向代理（推荐）

创建 Nginx 配置 `/etc/nginx/sites-available/wrong-word`：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    client_max_body_size 20M;  # 允许上传 20MB PDF 文件

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # 超时设置（PDF 处理可能需要时间）
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

启用配置：

```bash
sudo ln -s /etc/nginx/sites-available/wrong-word /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## 生产环境优化

### 1. Worker 数量

根据 CPU 核心数调整：

```bash
# 推荐公式：workers = (2 * CPU核心数) + 1
uvicorn app:app --host 0.0.0.0 --port 8000 --workers 4
```

### 2. 日志配置

在 `app.py` 中添加日志：

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("/var/log/wrong-word/app.log"),
        logging.StreamHandler()
    ]
)
```

### 3. 监控与告警

使用 systemd 日志查看运行状态：

```bash
# 查看实时日志
sudo journalctl -u wrong-word -f

# 查看最近日志
sudo journalctl -u wrong-word -n 100
```

## 客户端调用示例

部署完成后，其他系统可通过 HTTP 调用：

### Python 客户端

```python
import requests

# 文本纠错
response = requests.post(
    "http://your-server:8000/correct",
    json={"text": "少先队员因该为老人让坐"}
)
print(response.json())

# PDF 检查
with open("招标文件.pdf", "rb") as f:
    response = requests.post(
        "http://your-server:8000/correct/pdf",
        files={"file": f}
    )
print(response.json())
```

### cURL 示例

```bash
# 单句纠错
curl -X POST http://your-server:8000/correct \
  -H "Content-Type: application/json" \
  -d '{"text": "少先队员因该为老人让坐"}'

# PDF 检查
curl -X POST http://your-server:8000/correct/pdf \
  -F "file=@招标文件.pdf"
```

## 故障排查

### 问题 1：模型加载失败

**现象**：`/health` 返回 `"model_loaded": false`

**解决**：
```bash
# 检查模型文件是否存在
ls -lh models/macbert4csc/

# 重新下载模型
rm -rf models/macbert4csc
huggingface-cli download shibing624/macbert4csc-base-chinese \
  --local-dir models/macbert4csc
```

### 问题 2：PDF 处理超时

**现象**：大 PDF 文件上传后超时

**解决**：
- 调整 Nginx 超时配置（见上文 Nginx 配置）
- 增加 PDF 分块处理（`pdf_check.py` 中 `CHUNK_SIZE` 可调小）

### 问题 3：内存不足

**现象**：服务进程被 OOM killer 杀死

**解决**：
- 减少 worker 数量（改为 1-2 个）
- 增加服务器内存
- 使用 `rule` 模型替代 `macbert`（更轻量，见 `main.py` 配置）

## 安全建议

1. **限制访问来源**：在 Nginx 中添加 IP 白名单
2. **启用 HTTPS**：使用 Let's Encrypt 配置 SSL 证书
3. **API 认证**：在 `app.py` 中添加 Bearer Token 验证
4. **速率限制**：使用 Nginx limit_req 模块防止滥用

## 更新部署

```bash
# 停止服务
sudo systemctl stop wrong-word

# 拉取最新代码
cd /path/to/deploy
git pull  # 或重新上传文件

# 更新依赖
source venv/bin/activate
pip install -r requirements.txt --upgrade

# 重启服务
sudo systemctl start wrong-word
```

## 性能基准

测试环境：2 核 CPU，4GB 内存，2 workers

- **单句纠错**：~50-100ms/请求
- **批量纠错**（32 条）：~500-800ms/请求
- **PDF 检查**（10 页）：~3-5 秒

实际性能取决于服务器配置和文本长度。
