from fastapi import FastAPI, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from database import get_db
from routers import dashboard, advertising, import_data, query

app = FastAPI(title="LMG 数据平台", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router, prefix="/api/dashboard", tags=["看板"])
app.include_router(advertising.router, prefix="/api/advertising", tags=["广告"])
app.include_router(import_data.router, prefix="/api/import", tags=["导入"])
app.include_router(query.router, prefix="/api/query", tags=["查询"])


@app.get("/api/stores")
def list_stores(db: Session = Depends(get_db)):
    """返回可用店铺列表"""
    from models import DimStore
    stores = db.query(DimStore).all()
    return [{"id": s.id, "code": s.code, "name": s.name} for s in stores]


@app.post("/api/admin/stores")
def create_store(code: str, name: str, db: Session = Depends(get_db)):
    """创建店铺"""
    from models import DimStore
    if db.query(DimStore).filter(DimStore.code == code).first():
        return {"detail": "店铺代码已存在"}
    store = DimStore(code=code, name=name)
    db.add(store)
    db.commit()
    return {"id": store.id, "code": store.code, "name": store.name}


@app.delete("/api/admin/stores/{store_code}")
def delete_store(store_code: str, db: Session = Depends(get_db)):
    from models import DimStore, MonthlySummary
    store = db.query(DimStore).filter(DimStore.code == store_code).first()
    if not store: return {"detail": "店铺不存在"}
    if db.query(MonthlySummary).filter(MonthlySummary.store_id == store.id).first():
        return {"detail": "有数据无法删除"}
    db.delete(store); db.commit()
    return {"message": "已删除"}

@app.put("/api/admin/stores/{code}")
def update_store(code: str, name: str, new_code: str = None, db: Session = Depends(get_db)):
    from models import DimStore
    s = db.query(DimStore).filter(DimStore.code == code).first()
    if not s: return {"detail": "不存在"}
    s.name = name
    if new_code and new_code != code:
        if db.query(DimStore).filter(DimStore.code == new_code).first(): return {"detail": "代码已存在"}
        s.code = new_code
    db.commit()
    return {"id": s.id, "code": s.code, "name": s.name}

@app.delete("/api/admin/countries/{code}")
def delete_country(code: str, db: Session = Depends(get_db)):
    from models import DimCountry, MonthlySummary
    c = db.query(DimCountry).filter(DimCountry.code == code.upper()).first()
    if not c: return {"detail": "不存在"}
    if db.query(MonthlySummary).filter(MonthlySummary.country_id == c.id).first():
        return {"detail": "有数据无法删除"}
    db.delete(c); db.commit()
    return {"message": "已删除"}

@app.put("/api/admin/countries/{code}")
def update_country(code: str, name: str, currency: str = None, new_code: str = None, db: Session = Depends(get_db)):
    from models import DimCountry
    c = db.query(DimCountry).filter(DimCountry.code == code.upper()).first()
    if not c: return {"detail": "不存在"}
    c.name = name
    if currency: c.currency = currency
    if new_code and new_code.upper() != code.upper():
        if db.query(DimCountry).filter(DimCountry.code == new_code.upper()).first(): return {"detail": "代码已存在"}
        c.code = new_code.upper()
    db.commit()
    return {"id": c.id, "code": c.code, "name": c.name}


@app.get("/api/admin/countries")
def list_countries(db: Session = Depends(get_db)):
    from models import DimCountry
    return [{"id": c.id, "code": c.code, "name": c.name, "currency": c.currency} for c in db.query(DimCountry).all()]

@app.post("/api/admin/countries")
def create_country(code: str, name: str, currency: str = "USD", db: Session = Depends(get_db)):
    from models import DimCountry
    if db.query(DimCountry).filter(DimCountry.code == code.upper()).first():
        return {"detail": "国家代码已存在"}
    c = DimCountry(code=code.upper(), name=name, currency=currency)
    db.add(c)
    db.commit()
    return {"id": c.id, "code": c.code, "name": c.name}

@app.delete("/api/admin/countries/{code}")
def delete_country(code: str, db: Session = Depends(get_db)):
    from models import DimCountry
    c = db.query(DimCountry).filter(DimCountry.code == code.upper()).first()
    if not c: return {"detail": "国家不存在"}
    db.delete(c)
    db.commit()
    return {"message": "已删除"}

# === 汇率管理 ===
@app.get("/api/admin/exchange-rates")
def list_rates(country_id: int = None, year_month: str = None, db: Session = Depends(get_db)):
    from models import DimExchangeRate, DimCountry
    q = db.query(DimExchangeRate.id, DimCountry.code, DimExchangeRate.year_month, DimExchangeRate.rate).join(DimCountry)
    if country_id: q = q.filter(DimExchangeRate.country_id == country_id)
    if year_month: q = q.filter(DimExchangeRate.year_month == year_month)
    return [{"id": r[0], "country_code": r[1], "year_month": r[2], "rate": float(r[3])} for r in q.all()]

@app.post("/api/admin/exchange-rates")
def create_rate(country_id: int, year_month: str, rate: float, db: Session = Depends(get_db)):
    from models import DimExchangeRate
    r = DimExchangeRate(country_id=country_id, year_month=year_month, rate=rate)
    db.add(r)
    db.commit()
    return {"id": r.id, "year_month": r.year_month, "rate": float(r.rate)}

@app.delete("/api/admin/exchange-rates/{rate_id}")
def delete_rate(rate_id: int, db: Session = Depends(get_db)):
    from models import DimExchangeRate
    r = db.query(DimExchangeRate).filter(DimExchangeRate.id == rate_id).first()
    if not r: return {"detail": "不存在"}
    db.delete(r)
    db.commit()
    return {"message": "已删除"}

@app.put("/api/admin/exchange-rates/{rate_id}")
def update_rate(rate_id: int, rate: float, db: Session = Depends(get_db)):
    from models import DimExchangeRate
    r = db.query(DimExchangeRate).filter(DimExchangeRate.id == rate_id).first()
    if not r: return {"detail": "不存在"}
    r.rate = rate
    db.commit()
    return {"id": r.id, "rate": float(r.rate)}

def _get_exchange_rate(db: Session, country_id: int, year_month: str) -> float:
    """获取某国某月汇率，fallback到最近月份"""
    from models import DimExchangeRate
    r = db.query(DimExchangeRate).filter(DimExchangeRate.country_id == country_id, DimExchangeRate.year_month == year_month).first()
    if r: return float(r.rate)
    r = db.query(DimExchangeRate).filter(DimExchangeRate.country_id == country_id).order_by(DimExchangeRate.year_month.desc()).first()
    return float(r.rate) if r else 6.8

@app.get("/health")
def health():
    return {"status": "ok"}
