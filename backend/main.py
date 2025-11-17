from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import ProductIn, ProductOut, OrderIn, OrderOut

app = FastAPI(title="Secret Closet API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Utility

def to_product_out(doc: Dict[str, Any]) -> ProductOut:
    return ProductOut(
        id=str(doc.get("_id")),
        name=doc["name"],
        brand=doc.get("brand", ""),
        category=doc.get("category", ""),
        price=float(doc.get("price", 0.0)),
        sale_price=float(doc.get("sale_price")) if doc.get("sale_price") is not None else None,
        stock=int(doc.get("stock", 0)),
        description=doc.get("description"),
        images=list(doc.get("images", [])),
        specs=doc.get("specs"),
        options=doc.get("options"),
        is_featured=bool(doc.get("is_featured", False)),
        tags=list(doc.get("tags", [])),
        rating=float(doc.get("rating", 0.0)),
        created_at=doc.get("created_at", datetime.utcnow()),
        updated_at=doc.get("updated_at", datetime.utcnow()),
    )


# Categories
@app.get("/api/categories", response_model=List[str])
async def get_categories():
    pipeline = [
        {"$group": {"_id": "$category"}},
        {"$sort": {"_id": 1}},
    ]
    categories = [d["_id"] for d in db["product"].aggregate(pipeline) if d.get("_id")]
    return categories


# Products
@app.get("/api/products", response_model=List[ProductOut])
async def list_products(
    category: Optional[str] = None,
    q: Optional[str] = None,
    sort: Optional[str] = None,  # price_asc | price_desc | newest | rating
    limit: int = 50,
):
    query: Dict[str, Any] = {}
    if category:
        query["category"] = category
    if q:
        query["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"brand": {"$regex": q, "$options": "i"}},
            {"tags": {"$regex": q, "$options": "i"}},
        ]

    sort_stage = None
    if sort == "price_asc":
        sort_stage = ("price", 1)
    elif sort == "price_desc":
        sort_stage = ("price", -1)
    elif sort == "newest":
        sort_stage = ("created_at", -1)
    elif sort == "rating":
        sort_stage = ("rating", -1)

    cursor = db["product"].find(query)
    if sort_stage:
        cursor = cursor.sort([sort_stage])
    cursor = cursor.limit(limit)
    return [to_product_out(d) for d in await cursor.to_list(length=limit)] if hasattr(cursor, 'to_list') else [to_product_out(d) for d in cursor]


@app.get("/api/products/best", response_model=List[ProductOut])
async def best_products(limit: int = 8):
    cursor = db["product"].find({"is_featured": True}).sort([("rating", -1)]).limit(limit)
    return [to_product_out(d) for d in cursor]


@app.get("/api/products/new", response_model=List[ProductOut])
async def new_products(limit: int = 8):
    cursor = db["product"].find({}).sort([("created_at", -1)]).limit(limit)
    return [to_product_out(d) for d in cursor]


@app.get("/api/products/{id}", response_model=ProductOut)
async def get_product(id: str):
    doc = db["product"].find_one({"_id": ObjectId(id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Product not found")
    return to_product_out(doc)


# Admin Products
@app.post("/api/admin/products", response_model=ProductOut)
async def create_product(p: ProductIn):
    data = p.dict()
    now = datetime.utcnow()
    data.update({"created_at": now, "updated_at": now})
    inserted = create_document("product", data)
    return to_product_out(inserted)


@app.put("/api/admin/products/{id}", response_model=ProductOut)
async def update_product(id: str, p: ProductIn):
    now = datetime.utcnow()
    update = {"$set": {**p.dict(), "updated_at": now}}
    res = db["product"].find_one_and_update({"_id": ObjectId(id)}, update, return_document=True)
    if not res:
        raise HTTPException(status_code=404, detail="Product not found")
    return to_product_out(res)


# Orders
@app.post("/api/orders", response_model=OrderOut)
async def create_order(order: OrderIn):
    now = datetime.utcnow()
    doc = order.dict()
    doc.update({"status": "received", "created_at": now, "updated_at": now})
    inserted = create_document("order", doc)
    return OrderOut(id=str(inserted["_id"]), **order.dict(), status="received", created_at=inserted["created_at"], updated_at=inserted["updated_at"]) 


@app.get("/api/orders", response_model=List[OrderOut])
async def list_orders(email: Optional[str] = None, limit: int = 50):
    query: Dict[str, Any] = {}
    if email:
        query["shipping.email"] = email
    cursor = db["order"].find(query).sort([("created_at", -1)]).limit(limit)
    results: List[OrderOut] = []
    for d in cursor:
        results.append(OrderOut(
            id=str(d["_id"]),
            items=d.get("items", []),
            shipping=d.get("shipping"),
            payment=d.get("payment"),
            subtotal=float(d.get("subtotal", 0)),
            shipping_cost=float(d.get("shipping_cost", 0)),
            discount=float(d.get("discount", 0)),
            total=float(d.get("total", 0)),
            status=d.get("status", "received"),
            created_at=d.get("created_at", now),
            updated_at=d.get("updated_at", now),
        ))
    return results


@app.put("/api/orders/{id}/status", response_model=OrderOut)
async def update_order_status(id: str, status: str):
    now = datetime.utcnow()
    res = db["order"].find_one_and_update({"_id": ObjectId(id)}, {"$set": {"status": status, "updated_at": now}}, return_document=True)
    if not res:
        raise HTTPException(status_code=404, detail="Order not found")
    return OrderOut(
        id=str(res["_id"]),
        items=res.get("items", []),
        shipping=res.get("shipping"),
        payment=res.get("payment"),
        subtotal=float(res.get("subtotal", 0)),
        shipping_cost=float(res.get("shipping_cost", 0)),
        discount=float(res.get("discount", 0)),
        total=float(res.get("total", 0)),
        status=res.get("status", "received"),
        created_at=res.get("created_at", now),
        updated_at=res.get("updated_at", now),
    )


# Seeding
SAMPLE_PRODUCTS = [
    {
        "name": "Essential Cotton Tee",
        "brand": "Secret Closet",
        "category": "Apparel",
        "price": 24.99,
        "sale_price": 19.99,
        "stock": 120,
        "description": "Soft, breathable cotton tee for everyday wear.",
        "images": [
            "https://images.unsplash.com/photo-1520975916090-3105956dac38?q=80&w=1200&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1512436991641-6745cdb1723f?q=80&w=1200&auto=format&fit=crop",
        ],
        "specs": {"material": "100% Cotton", "fit": "Regular"},
        "options": {"size": ["S", "M", "L", "XL"], "color": ["White", "Black", "Navy"]},
        "is_featured": True,
        "tags": ["tee", "cotton", "everyday"],
        "rating": 4.5,
    },
    {
        "name": "Slim Fit Denim Jeans",
        "brand": "Secret Closet",
        "category": "Apparel",
        "price": 59.99,
        "sale_price": 49.99,
        "stock": 80,
        "description": "Modern slim-fit denim with stretch for comfort.",
        "images": [
            "https://images.unsplash.com/photo-1516478177764-9fe5bd7e9717?q=80&w=1200&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1473966968600-fa801b869a1a?q=80&w=1200&auto=format&fit=crop",
        ],
        "specs": {"material": "Denim", "fit": "Slim"},
        "options": {"size": ["28", "30", "32", "34"], "color": ["Indigo", "Black"]},
        "is_featured": True,
        "tags": ["jeans", "denim"],
        "rating": 4.6,
    },
    {
        "name": "Classic White Sneakers",
        "brand": "Secret Closet",
        "category": "Footwear",
        "price": 79.99,
        "sale_price": 64.99,
        "stock": 60,
        "description": "Clean, versatile sneakers for any outfit.",
        "images": [
            "https://images.unsplash.com/photo-1542291026-7eec264c27ff?q=80&w=1200&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1519741497674-611481863552?q=80&w=1200&auto=format&fit=crop",
        ],
        "specs": {"upper": "Leather", "sole": "Rubber"},
        "options": {"size": ["7", "8", "9", "10", "11"], "color": ["White"]},
        "is_featured": True,
        "tags": ["sneakers", "footwear"],
        "rating": 4.7,
    },
    {
        "name": "Signature Eau de Parfum",
        "brand": "Secret Closet",
        "category": "Fragrance",
        "price": 99.99,
        "sale_price": 79.99,
        "stock": 40,
        "description": "A timeless blend of floral and musky notes.",
        "images": [
            "https://images.unsplash.com/photo-1594036209319-6db9c6c46c58?q=80&w=1200&auto=format&fit=crop",
            "https://images.unsplash.com/photo-1541643600914-78b084683601?q=80&w=1200&auto=format&fit=crop",
        ],
        "specs": {"volume": "50ml"},
        "options": {"size": ["30ml", "50ml", "100ml"]},
        "is_featured": True,
        "tags": ["perfume", "fragrance"],
        "rating": 4.8,
    },
]


@app.post("/api/admin/seed")
async def seed():
    col = db["product"]
    if col.count_documents({}) == 0:
        now = datetime.utcnow()
        for p in SAMPLE_PRODUCTS:
            data = {**p, "created_at": now, "updated_at": now}
            create_document("product", data)
        return {"seeded": True, "count": len(SAMPLE_PRODUCTS)}
    return {"seeded": False, "count": col.count_documents({})}


@app.on_event("startup")
async def startup_seed():
    try:
        await seed()
    except Exception:
        pass


# Health
@app.get("/test")
async def test():
    return {"ok": True}
