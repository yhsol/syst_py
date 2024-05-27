import os
from typing import Union

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import coin_analysis, signal, trade
from app.dependencies.auth import verify_api_key

app = FastAPI()

load_dotenv()

CLIENT_URL = os.getenv("CLIENT_URL")

# CORS 설정 추가
origins = [
    "http://localhost:3000",
    CLIENT_URL,
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(coin_analysis.router, dependencies=[Depends(verify_api_key)])
app.include_router(signal.router, dependencies=[Depends(verify_api_key)])
app.include_router(trade.router, dependencies=[Depends(verify_api_key)])


@app.get("/")
async def read_root():
    return "Hello World! It's syst!"


@app.get("/items/{item_id}")
async def read_item(item_id: int, q: Union[str, None] = None):
    return {"item_id": item_id, "q": q}
