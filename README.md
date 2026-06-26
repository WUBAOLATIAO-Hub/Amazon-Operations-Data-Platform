# LMG 数据平台

Amazon 多店铺运营数据分析平台，支持 10 店 11 国全维度利润核算。

## 功能

- **数据导入**：Excel 工作簿一键导入 / 文件夹批量导入
- **利润核算**：多店铺、多国家、多月份自动汇总
- **可视化看板**：销售趋势、成本瀑布、店铺对比、国家对比、退货排名
- **数据查询**：按店铺/国家/月份/SKU 检索，支持导出
- **AI 助手**：自然语言查数据，利润 TOP/BOTTOM 分析

## 技术栈

- 后端：Python FastAPI + SQLAlchemy + MySQL
- 前端：React + Ant Design + ECharts + Vite
- AI：DeepSeek API（Anthropic 格式）

## 快速开始

```bash
# 后端
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000

# 前端
cd frontend
npm install
npx vite --host 0.0.0.0 --port 5173
```

## 数据库

按序执行 `database/migration_v*.sql`，或使用 ORM：

```python
from database import engine, Base
Base.metadata.create_all(engine)
```

## 业务规则

- 数据按 (店铺, 国家, 月份) 三重隔离，不跨店/不跨国家/不跨月
- 月份以导入时选择为准，不看数据内日期
- 同 SKU 同一 (店铺, 国家, 月份) 下只建一条汇总记录
