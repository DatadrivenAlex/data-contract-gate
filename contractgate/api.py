from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

from contractgate.engine import validate_csv
from contractgate.models import Contract

app = FastAPI(title="Data Contract Gate", version="0.1.0")


class Check(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract: Contract
    csv: str = Field(max_length=1000000)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/validate")
def validate(check: Check):
    return validate_csv(check.csv, check.contract)
