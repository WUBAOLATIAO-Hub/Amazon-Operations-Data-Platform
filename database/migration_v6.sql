-- v6: 数据查询优化索引
CREATE INDEX idx_ms_query ON monthly_summary(country_id, time_id, store_id, product_id);
