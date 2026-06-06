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
def list_stores(country: str = None, db: Session = Depends(get_db)):
    """返回可用店铺列表"""
    from models import DimStore, DimCountry
    q = db.query(DimStore)
    if country:
        q = q.join(DimCountry).filter(DimCountry.code == country.upper())
    stores = q.all()
    return [{"id": s.id, "code": s.code, "name": s.name, "country_id": s.country_id} for s in stores]


@app.get("/health")
def health():
    return {"status": "ok"}
