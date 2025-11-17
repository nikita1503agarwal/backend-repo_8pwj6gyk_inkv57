import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from database import db, create_document, get_documents
from bson import ObjectId

app = FastAPI(title="Secret Closet API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------
# Utilities
# -----------------------------

def to_object_id(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID format")


def serialize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return doc
    doc["id"] = str(doc.pop("_id")) if "_id" in doc else None
    # Convert datetimes to isoformat
    for k, v in list(doc.items()):
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
        if isinstance(v, dict):
            doc[k] = serialize_doc(v)
        if isinstance(v, list):
            new_list = []
            for item in v:
                if isinstance(item, dict):
                    new_list.append(serialize_doc(item))
                elif isinstance(item, datetime):
                    new_list.append(item.isoformat())
                else:
                    new_list.append(item)
            doc[k] = new_list
    return doc


# -----------------------------
# Models
# -----------------------------

class ProductIn(BaseModel):
    name: str
    brand: Optional[str] = None
    price: float = Field(..., ge=0)
    category: str
    description: Optional[str] = None
    specs: Optional[Dict[str, Any]] = None
    images: List[str] = Field(default_factory=list)
    stock: int = Field(0, ge=0)
    options: Dict[str, List[str]] = Field(default_factory=dict)  # size/color/etc
    is_featured: bool = False
    tags: List[str] = Field(default_factory=list)
    sale_price: Optional[float] = Field(None, ge=0)


class ProductOut(ProductIn):
    id: str


class OrderItem(BaseModel):
    product_id: str
    name: str
    price: float
    quantity: int = Field(ge=1)
    image: Optional[str] = None
    options: Optional[Dict[str, str]] = None


class ShippingInfo(BaseModel):
    full_name: str
    email: str
    phone: Optional[str] = None
    address_line1: str
    address_line2: Optional[str] = None
    city: str
    state: str
    postal_code: str
    country: str


class PaymentInfo(BaseModel):
    method: str  # e.g. stripe, paypal, cod
    status: str = "pending"
    transaction_id: Optional[str] = None


class OrderIn(BaseModel):
    items: List[OrderItem]
    shipping: ShippingInfo
    payment: PaymentInfo
    notes: Optional[str] = None


class OrderOut(BaseModel):
    id: str
    order_number: str
    total_amount: float
    status: str
    created_at: str


# -----------------------------
# Root & Health
# -----------------------------

@app.get("/")
def read_root():
    return {"message": "Secret Closet API is running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "Unknown"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:20]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response


# -----------------------------
# Categories
# -----------------------------

@app.get("/api/categories", response_model=List[str])
def get_categories():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    cats = db.product.distinct("category")
    return sorted([c for c in cats if isinstance(c, str)])


# -----------------------------
# Products
# -----------------------------

@app.get("/api/products")
def list_products(
    q: Optional[str] = None,
    category: Optional[str] = None,
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    sort: Optional[str] = Query(None, description="price_asc|price_desc|new|popular"),
    page: int = Query(1, ge=1),
    limit: int = Query(12, ge=1, le=60)
):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    filter_q: Dict[str, Any] = {}
    if q:
        filter_q["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"brand": {"$regex": q, "$options": "i"}},
            {"category": {"$regex": q, "$options": "i"}},
            {"tags": {"$regex": q, "$options": "i"}},
        ]
    if category:
        filter_q["category"] = category
    price_filter = {}
    if min_price is not None:
        price_filter["$gte"] = float(min_price)
    if max_price is not None:
        price_filter["$lte"] = float(max_price)
    if price_filter:
        filter_q["price"] = price_filter

    sort_tuple = None
    if sort == "price_asc":
        sort_tuple = ("price", 1)
    elif sort == "price_desc":
        sort_tuple = ("price", -1)
    elif sort == "new":
        sort_tuple = ("created_at", -1)
    elif sort == "popular":
        sort_tuple = ("rating.count", -1)

    cursor = db.product.find(filter_q)
    total = cursor.count() if hasattr(cursor, 'count') else db.product.count_documents(filter_q)
    if sort_tuple:
        cursor = cursor.sort([sort_tuple])
    cursor = cursor.skip((page - 1) * limit).limit(limit)
    items = [serialize_doc(d) for d in list(cursor)]
    return {"items": items, "page": page, "limit": limit, "total": total}


@app.get("/api/products/best")
def best_sellers(limit: int = 8):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    cursor = db.product.find({}).sort([( "rating.count", -1)]).limit(limit)
    return [serialize_doc(d) for d in cursor]


@app.get("/api/products/new")
def new_arrivals(limit: int = 8):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    cursor = db.product.find({}).sort([( "created_at", -1)]).limit(limit)
    return [serialize_doc(d) for d in cursor]


@app.get("/api/products/{product_id}", response_model=ProductOut)
def get_product(product_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    doc = db.product.find_one({"_id": to_object_id(product_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Product not found")
    return serialize_doc(doc)


@app.post("/api/admin/products", response_model=ProductOut)
def create_product(product: ProductIn):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    data = product.model_dump()
    now = datetime.now(timezone.utc)
    data.update({
        "created_at": now,
        "updated_at": now,
        "rating": {"average": 0.0, "count": 0}
    })
    inserted_id = db.product.insert_one(data).inserted_id
    doc = db.product.find_one({"_id": inserted_id})
    return serialize_doc(doc)


@app.put("/api/admin/products/{product_id}", response_model=ProductOut)
def update_product(product_id: str, product: ProductIn):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    data = product.model_dump()
    data["updated_at"] = datetime.now(timezone.utc)
    res = db.product.update_one({"_id": to_object_id(product_id)}, {"$set": data})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
    doc = db.product.find_one({"_id": to_object_id(product_id)})
    return serialize_doc(doc)


# -----------------------------
# Orders
# -----------------------------

@app.post("/api/orders", response_model=OrderOut)
def create_order(order: OrderIn):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    total_amount = sum(item.price * item.quantity for item in order.items)
    now = datetime.now(timezone.utc)
    order_number = f"ORD-{now.strftime('%Y%m%d%H%M%S')}"

    data = order.model_dump()
    data.update({
        "order_number": order_number,
        "total_amount": total_amount,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
    })

    inserted_id = db.order.insert_one(data).inserted_id
    return OrderOut(
        id=str(inserted_id),
        order_number=order_number,
        total_amount=total_amount,
        status="pending",
        created_at=now.isoformat(),
    )


@app.get("/api/orders/{order_id}")
def get_order(order_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    doc = db.order.find_one({"_id": to_object_id(order_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found")
    return serialize_doc(doc)


@app.put("/api/orders/{order_id}/status")
def update_order_status(order_id: str, status: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    res = db.order.update_one(
        {"_id": to_object_id(order_id)},
        {"$set": {"status": status, "updated_at": datetime.now(timezone.utc)}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"id": order_id, "status": status}


# -----------------------------
# Seed endpoint (optional for demo)
# -----------------------------

@app.post("/api/admin/seed")
def seed_products():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    if db.product.count_documents({}) > 0:
        return {"message": "Products already seeded"}
    sample = [
        {
            "name": "Classic Tee",
            "brand": "Secret",
            "price": 29.99,
            "sale_price": 24.99,
            "category": "Apparel",
            "description": "Soft cotton tee",
            "specs": {"material": "100% Cotton"},
            "images": ["https://images.unsplash.com/photo-1512436991641-6745cdb1723f?q=80&w=800&auto=format&fit=crop"],
            "stock": 42,
            "options": {"size": ["S","M","L","XL"], "color": ["Black","White"]},
            "is_featured": True,
            "tags": ["bestseller", "new"],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "rating": {"average": 4.6, "count": 120}
        },
        {
            "name": "Everyday Jeans",
            "brand": "Secret",
            "price": 59.0,
            "category": "Apparel",
            "description": "Slim fit denim",
            "specs": {"material": "Denim"},
            "images": ["https://images.unsplash.com/photo-1519741497674-611481863552?q=80&w=800&auto=format&fit=crop"],
            "stock": 18,
            "options": {"size": ["28","30","32","34"], "color": ["Blue","Dark Blue"]},
            "is_featured": False,
            "tags": ["denim"],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "rating": {"average": 4.3, "count": 80}
        },
        {
            "name": "Minimal Sneakers",
            "brand": "Secret",
            "price": 79.0,
            "sale_price": 69.0,
            "category": "Footwear",
            "description": "Clean silhouette",
            "specs": {"material": "Vegan leather"},
            "images": ["https://images.unsplash.com/photo-1542291026-7eec264c27ff?q=80&w=800&auto=format&fit=crop"],
            "stock": 25,
            "options": {"size": ["7","8","9","10","11"], "color": ["White","Black"]},
            "is_featured": True,
            "tags": ["sneakers", "minimal"],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "rating": {"average": 4.8, "count": 200}
        },
        {
            "name": "No. 7 Eau de Parfum",
            "brand": "Secret Scents",
            "price": 110.0,
            "category": "Fragrance",
            "description": "Amber, vanilla and cedar. Long-lasting.",
            "specs": {"volume": "50ml"},
            "images": ["https://images.unsplash.com/photo-1616606347407-23ca041ac856?q=80&w=800&auto=format&fit=crop"],
            "stock": 12,
            "options": {"volume": ["30ml","50ml","100ml"]},
            "is_featured": True,
            "tags": ["perfume","fragrance"],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "rating": {"average": 4.9, "count": 310}
        }
    ]
    db.product.insert_many(sample)
    return {"message": "Seeded sample products", "count": len(sample)}


# -----------------------------
# Auto-seed on startup so homepage is never empty
# -----------------------------

@app.on_event("startup")
async def ensure_seed_on_startup():
    try:
        if db is not None and db.product.count_documents({}) == 0:
            await app.router.lifespan_context(app) if False else None  # no-op to keep async signature lint-happy
            sample = [
                {
                    "name": "Classic Tee",
                    "brand": "Secret",
                    "price": 29.99,
                    "sale_price": 24.99,
                    "category": "Apparel",
                    "description": "Soft cotton tee",
                    "specs": {"material": "100% Cotton"},
                    "images": ["https://images.unsplash.com/photo-1512436991641-6745cdb1723f?q=80&w=800&auto=format&fit=crop"],
                    "stock": 42,
                    "options": {"size": ["S","M","L","XL"], "color": ["Black","White"]},
                    "is_featured": True,
                    "tags": ["bestseller", "new"],
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                    "rating": {"average": 4.6, "count": 120}
                },
                {
                    "name": "Everyday Jeans",
                    "brand": "Secret",
                    "price": 59.0,
                    "category": "Apparel",
                    "description": "Slim fit denim",
                    "specs": {"material": "Denim"},
                    "images": ["https://images.unsplash.com/photo-1519741497674-611481863552?q=80&w=800&auto=format&fit=crop"],
                    "stock": 18,
                    "options": {"size": ["28","30","32","34"], "color": ["Blue","Dark Blue"]},
                    "is_featured": False,
                    "tags": ["denim"],
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                    "rating": {"average": 4.3, "count": 80}
                },
                {
                    "name": "Minimal Sneakers",
                    "brand": "Secret",
                    "price": 79.0,
                    "sale_price": 69.0,
                    "category": "Footwear",
                    "description": "Clean silhouette",
                    "specs": {"material": "Vegan leather"},
                    "images": ["https://images.unsplash.com/photo-1542291026-7eec264c27ff?q=80&w=800&auto=format&fit=crop"],
                    "stock": 25,
                    "options": {"size": ["7","8","9","10","11"], "color": ["White","Black"]},
                    "is_featured": True,
                    "tags": ["sneakers", "minimal"],
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                    "rating": {"average": 4.8, "count": 200}
                },
                {
                    "name": "No. 7 Eau de Parfum",
                    "brand": "Secret Scents",
                    "price": 110.0,
                    "category": "Fragrance",
                    "description": "Amber, vanilla and cedar. Long-lasting.",
                    "specs": {"volume": "50ml"},
                    "images": ["https://images.unsplash.com/photo-1616606347407-23ca041ac856?q=80&w=800&auto=format&fit=crop"],
                    "stock": 12,
                    "options": {"volume": ["30ml","50ml","100ml"]},
                    "is_featured": True,
                    "tags": ["perfume","fragrance"],
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                    "rating": {"average": 4.9, "count": 310}
                }
            ]
            db.product.insert_many(sample)
    except Exception:
        # Swallow seeding errors to not block startup
        pass


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
