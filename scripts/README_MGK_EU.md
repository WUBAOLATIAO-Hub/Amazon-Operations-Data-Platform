# MGK-EU 数据导入与利润计算

## 文件结构

```
lmg-platform/
├── database/
│   └── migration_v7_mgk_eu.sql    # 数据库迁移脚本
├── scripts/
│   ├── import_mgk_eu.py           # 数据导入脚本
│   ├── calculate_profit_mgk_eu.py # 利润计算脚本
│   └── README_MGK_EU.md           # 本文档
```

## 执行顺序

### 1. 数据库迁移
```bash
mysql -u root -p < database/migration_v7_mgk_eu.sql
```

### 2. 导入数据
```bash
# 全部导入
python scripts/import_mgk_eu.py

# 单独导入
python scripts/import_mgk_eu.py products     # 产品 + 运费
python scripts/import_mgk_eu.py sales         # 销售明细
python scripts/import_mgk_eu.py advertising   # 广告数据
python scripts/import_mgk_eu.py storage       # 仓储费
python scripts/import_mgk_eu.py aged          # 超龄仓储费
python scripts/import_mgk_eu.py returns       # 退回处理费
```

### 3. 计算利润
```bash
python scripts/calculate_profit_mgk_eu.py
```

## 运费逻辑

| 国家 | 运费来源 |
|------|---------|
| 🇬🇧 UK | `dim_freight` WHERE country = UK |
| 🇮🇪 IE | `dim_freight` WHERE country = IE |
| 其他 | `dim_freight` WHERE country = 对应国家（默认运费） |

运费 = `freight_rmb × quantity`

## 利润公式

```
净利润(RMB) = 亚马逊到账(外币) × 汇率
             - 产品成本(RMB)
             - 运费(RMB)
             - 广告费(RMB)
             - 仓储费(RMB)
             - 退回处理费(RMB)

净利率 = 净利润 / (净销售额 × 汇率)
```

## 多语言列名映射

导入脚本内置了 7 种语言的列名映射（英/德/法/西/意/荷/瑞），
自动将各国 CSV 的本地化列名转换为统一英文字段。

## 汇率配置

在 `calculate_profit_mgk_eu.py` 的 `EXCHANGE_RATES` 字典中修改。
