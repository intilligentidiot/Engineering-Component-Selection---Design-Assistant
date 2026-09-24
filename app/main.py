from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from app.api.routes import router as api_router
from app.database.database import engine, Base

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Tesla Motor & Gearbox Selection Tool")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Include API routes
app.include_router(api_router, prefix="/api")

@app.get("/")
def read_root(request: Request):
    return templates.TemplateResponse(
        request=request, 
        name="index.html"
    )

@app.get("/health")
def health_check():
    return {"status": "ok"}
