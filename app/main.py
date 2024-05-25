from typing import Union

from fastapi import FastAPI

from app.api import coin_analysis, signal, trade

app = FastAPI()

app.include_router(coin_analysis.router)
app.include_router(signal.router)
app.include_router(trade.router)


@app.get("/")
async def read_root():
    return "Hello World! It's syst!"


@app.get("/items/{item_id}")
async def read_item(item_id: int, q: Union[str, None] = None):
    return {"item_id": item_id, "q": q}
