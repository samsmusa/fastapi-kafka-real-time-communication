from typing import List, Optional

from pydantic import BaseModel


class Items(BaseModel):
    product_id: int
    quantity: int
    price: float


class Msg(BaseModel):
    message: str


class Client(BaseModel):
    id: int
    active: bool
    x: float
    y: float


class Message(BaseModel):
    client: Client
    created_at: Optional[int] = None
