import uvicorn

from app.main import CONFIG


uvicorn.run(
    "app.main:app",
    host=CONFIG["host"],
    port=CONFIG["port"],
    workers=1,
)
