from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import create_db_and_tables
from app.routers import auth, generation

app = FastAPI(title=settings.app_name, debug=settings.debug_mode)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    try:
        create_db_and_tables()
    except Exception as e:
        print(f"Warning: Database initialization skipped or failed: {e}")

app.include_router(auth.router)
app.include_router(generation.router)

@app.get("/")
def root():
    return {"message": "3D Generator API is live with OrthoCAD integration!"}
