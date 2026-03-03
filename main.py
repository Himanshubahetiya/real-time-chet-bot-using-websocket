from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from jose import jwt
import json, uvicorn

SECRET_KEY = "supersecretkey"
ALGORITHM = "HS256"

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

users_db = {}               # username: password
active_users = {}           # username: websocket


class AuthRequest(BaseModel):
    username: str
    password: str


@app.post("/signup")
def signup(data: AuthRequest):
    if data.username in users_db:
        raise HTTPException(400, "User exists")
    users_db[data.username] = data.password
    return {"message": "Signup success"}


@app.post("/login")
def login(data: AuthRequest):
    if users_db.get(data.username) != data.password:
        raise HTTPException(401, "Invalid credentials")

    token = jwt.encode({"username": data.username}, SECRET_KEY, algorithm=ALGORITHM)
    return {"token": token}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str):
    await ws.accept()

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload["username"]
        active_users[username] = ws

        # 🔔 send online users
        await broadcast_users()

        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)

            # 🟢 Typing indicator
            if msg["type"] == "typing":
                await broadcast_except(username, {
                    "type": "typing",
                    "user": username
                })

            # 💬 Public message
            elif msg["type"] == "message":
                await broadcast({
                    "type": "message",
                    "user": username,
                    "text": msg["data"]
                })

            # 🖼️ Image/File (base64)
            elif msg["type"] == "image":
                await broadcast({
                    "type": "image",
                    "user": username,
                    "data": msg["data"]
                })

            # 🔐 Private chat
            elif msg["type"] == "private":
                to = msg["to"]
                if to in active_users:
                    await active_users[to].send_text(json.dumps({
                        "type": "private",
                        "from": username,
                        "text": msg["data"]
                    }))

    except WebSocketDisconnect:
        active_users.pop(username)
        await broadcast_users()


async def broadcast(message: dict):
    for ws in active_users.values():
        await ws.send_text(json.dumps(message))


async def broadcast_except(skip_user, message):
    for user, ws in active_users.items():
        if user != skip_user:
            await ws.send_text(json.dumps(message))


async def broadcast_users():
    await broadcast({
        "type": "users",
        "users": list(active_users.keys())
    })


if __name__ == "__main__":
    uvicorn.run("main:app", reload=True)
