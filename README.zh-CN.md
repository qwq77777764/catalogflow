# CatalogFlow

CatalogFlow 是一条安全优先、需要人工确认的商品目录流水线。它把获得授权的供应商商品事实，转换为结构统一的 WooCommerce 隐藏草稿。

当前公开版刻意不包含：生产密钥、供应商网页存档、客户数据、商店导出文件以及自动公开上架功能。

## 核心保证

- 默认只在本地生成预览，不写商店。
- 写入 WooCommerce 必须显式同时使用 `--draft --yes`。
- WooCommerce 适配器只能创建 `draft + hidden`，不能公开发布。
- 示例数据全部为合成数据，不需要 CJ、Alibaba、WooCommerce 或 AI 账号。
- 凭据只从环境变量读取，不能写入商品 JSON。
- 不提供批量网页爬虫；只处理用户拥有、获授权或通过官方 API 获得的数据。

## 本地演示

```bash
python -m venv .venv
.venv/Scripts/activate
python -m pip install -e ".[dev]"
catalogflow examples/synthetic_product.json --source cj
pytest
```

完整说明以英文 [README](README.md) 为准。

