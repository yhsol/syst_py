from contextlib import asynccontextmanager
import os
from typing import Union

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore
import aiohttp

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pytz import timezone

from app.api import coin_analysis, signal, trade
from app.dependencies.auth import verify_api_key

load_dotenv()

CLIENT_URL = os.getenv("CLIENT_URL")
SYST_URL = os.getenv("SYST_URL")

# CORS 설정 추가
origins = [
    "http://localhost:3000",
    CLIENT_URL,
    SYST_URL,
]

API_KEY = os.getenv("API_KEY")


# mm 시작 전에 stop_all 하고, mm 종료 후에 run_trade 해야하지 않을까 싶음.
# 좀 더 고민해보고 커밋
async def run_trade():
    async with aiohttp.ClientSession() as session:

        async with session.get(
            f"{SYST_URL}/trade/run", headers={"api-key": API_KEY}
        ) as response:
            if response.status:
                print("Successfully called run-mm")
            else:
                print("Failed to call run-mm")


async def stop_trade():
    async with aiohttp.ClientSession() as session:

        async with session.get(
            f"{SYST_URL}/trade/stop-all", headers={"api-key": API_KEY}
        ) as response:
            if response.status:
                print("Successfully called stop-mm")
            else:
                print("Failed to call stop-mm")


async def run_mm():
    async with aiohttp.ClientSession() as session:

        async with session.get(
            f"{SYST_URL}/trade/run-mm", headers={"api-key": API_KEY}
        ) as response:
            if response.status == 200:
                print("Successfully called run-mm")
            else:
                print("Failed to call run-mm")


async def stop_mm():
    async with aiohttp.ClientSession() as session:

        async with session.get(
            f"{SYST_URL}/trade/stop-mm", headers={"api-key": API_KEY}
        ) as response:
            if response.status == 200:
                print("Successfully called stop-mm")
            else:
                print("Failed to call stop-mm")


def schedule_run_mm():
    kst = timezone("Asia/Seoul")
    scheduler = AsyncIOScheduler(timezone=kst)
    scheduler.add_job(run_mm, "cron", hour=23, minute=58, timezone=kst)
    scheduler.add_job(stop_mm, "cron", hour=0, minute=8, timezone=kst)
    scheduler.start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        schedule_run_mm()
        yield
    finally:
        await stop_mm()


app = FastAPI(lifespan=lifespan)


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
