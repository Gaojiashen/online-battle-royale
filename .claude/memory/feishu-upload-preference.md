---
name: feishu-upload-preference
description: 飞书文件上传偏好：xlsx自动转为多维表格
metadata: 
  node_type: memory
  type: user
  originSessionId: 378a4af7-f23c-4a22-a4f2-ff212b0d9419
---

上传 Excel (.xlsx) 到飞书时，默认使用 `lark-cli drive +import --type bitable` 转为多维表格（Base），而非作为普通文件上传。

项目文件夹：密教模拟器S2（folder_token: `Z4hBfj0STl3jhsdGhqKcq2DEnJf`）
项目文件夹链接：https://acn5j59fiukt.feishu.cn/drive/folder/Z4hBfj0STl3jhsdGhqKcq2DEnJf

**Why:** 多维表格支持多人在线协作编辑、多种视图（表格/看板/日历）、实时同步，适合和橙子一起当法官查牌改数据。
**How to apply:** 上传 xlsx/csv 到飞书时，用 `lark-cli drive +import --type bitable --folder-token "Z4hBfj0STl3jhsdGhqKcq2DEnJf" --name "文档名"`，而不是 `drive +upload`。
