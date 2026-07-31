# 客户端测试脚本

用于测试 FastAPI 服务。

当前测试脚本：

```text
test.py
test_ltx.py
```

FastAPI 默认地址：

```text
http://127.0.0.1:8000
```

如果 FastAPI 部署在 AutoDL，需要先在本地建立 SSH Tunnel。

```bash
ssh -fN \
  -o ExitOnForwardFailure=yes \
  -L 8000:127.0.0.1:8000 \
  -p 3940 \
  root@connect.bjb1.seetacloud.com
```

## 安装依赖

```bash
pip install requests
```

---

## Qwen-Image-2512

文生图测试：

```bash
python3 test.py qwen-image-2512
```

生成结果：

```text
qwen-image-2512.png
```

---

## Qwen-Image-Edit-2511

准备输入图片：

```text
input.png
```

执行：

```bash
python3 test.py qwen-image-edit-2511 --input input.png
```

生成结果：

```text
qwen-image-edit-2511.png
```

---

## LTX-2.3 T2V

文生视频：

```bash
python3 test_ltx.py t2v
```

生成结果：

```text
ltx-2.3-t2v.mp4
```

---

## LTX-2.3 I2V

准备输入图片：

```text
input.png
```

执行：

```bash
python3 test_ltx.py i2v --input input.png
```

生成结果：

```text
ltx-2.3-i2v.mp4
```

---

## 测试顺序建议

先测试 FastAPI 健康状态：

```bash
curl http://127.0.0.1:8000/health
```

正常返回：

```json
{
  "status": "ok"
}
```

然后依次测试：

```bash
python3 test.py qwen-image-2512

python3 test.py qwen-image-edit-2511 --input input.png

python3 test_ltx.py t2v

python3 test_ltx.py i2v --input input.png
```
