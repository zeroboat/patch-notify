from fastapi import FastAPI
from dotenv import load_dotenv
import os

load_dotenv()

app = FastAPI(
    title="Patch Notify API",
    description="Patch Notify REST API 서비스",
    version="0.1.0",
)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/")
def root():
    return {"service": "patch-notify-api", "version": "0.1.0"}
