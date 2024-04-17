import asyncio
import datetime
import json
import sys
from uuid import uuid4

from confluent_kafka import Producer, Consumer, KafkaError, KafkaException
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from model.order import Message, Msg, Client
from settings import settings

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

topic = settings.KAFKA_TOPIC

producer_conf = {'bootstrap.servers': settings.BOOTSTRAP_SERVERS}
producer = Producer(producer_conf)

consumer_conf = {'bootstrap.servers': settings.BOOTSTRAP_SERVERS,
                 'group.id': 'foo',
                 'auto.offset.reset': 'earliest'}
consumer = Consumer(consumer_conf)


class ConnectionManager:
    def __init__(self):
        self.active_connections = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)


manager = ConnectionManager()


@app.get("/", response_class=HTMLResponse)
async def get(request: Request):
    return templates.TemplateResponse("game.html", context={"request": request})


@app.post("/{client_id}/send-msg")
async def send_message(client_id: int, message: Msg):
    msg = Message(id=str(uuid4()), client_id=client_id, message=message.message, x=10.2,
                  y=23.4)
    await produce_message(msg)
    return {"details": "ok"}


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: int):
    await manager.connect(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            client = Client(**json.loads(data), active=True)

            msg = Message(client=client)
            await produce_message(msg)
            # await manager.send_personal_message(f"You wrote: {data}", websocket)
            # await manager.broadcast(f"Client #{client_id} says: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print(f"disconnected {client_id}")
        # await manager.broadcast(f"Client #{client_id} left the chat")


async def produce_message(message: Message):
    message.created_at = round(datetime.datetime.now().timestamp() * 1000)
    producer.produce(topic=topic,
                     key=str(uuid4()),
                     value=json.dumps(message.model_dump_json()))
    producer.flush()
    print(f"Order {message} created successfully!")


async def consume_messages():
    consumer.subscribe([topic])

    try:
        while True:
            msg = await asyncio.to_thread(consumer.poll, 1.0)
            if msg is None:
                continue

            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    sys.stderr.write(
                        f'%% {msg.topic()} [{msg.partition()}] reached end at offset {msg.offset()}\n')
                elif msg.error():
                    raise KafkaException(msg.error())
            else:
                data = json.loads(msg.value())
                print("dd", data)
                await manager.broadcast(data)
    finally:
        consumer.close()


def between_callback():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    loop.run_until_complete(consume_messages())
    loop.close()


if __name__ == "__main__":
    import uvicorn
    import threading

    kafka_consumer_thread = threading.Thread(target=between_callback)
    kafka_consumer_thread.start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
