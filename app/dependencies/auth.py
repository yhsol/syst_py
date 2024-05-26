# app/dependencies/auth.py
import os
from fastapi import Header, HTTPException, status
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("API_KEY")


def verify_api_key(api_key: str = Header(...)):
    if api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API Key",
        )
