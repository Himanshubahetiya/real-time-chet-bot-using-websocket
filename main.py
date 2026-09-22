from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from jose import jwt
import json, uvicorn
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from database import Base, engine, get_db
import model
from passlib.context import CryptContext
from pwdlib import PasswordHash


SECRET_KEY = "supersecretkey"
ALGORITHM = "HS256"

Base.metadata.create_all(bind=engine)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

active_users = {}           # username: websocket

password_hash = PasswordHash.recommended()


class AuthRequest(BaseModel):
    username: str
    password: str


@app.get("/")
def home():
    return RedirectResponse(url="/static/auth.html")


@app.post("/signup")
def signup(data: AuthRequest, db: Session = Depends(get_db)):

    user = db.query(model.Users).filter(
        model.Users.username == data.username
    ).first()

    if user:
        raise HTTPException(400, "User exists")

    hashed_password = password_hash.hash(data.password)

    new_user = model.Users(
        username=data.username,
        password=hashed_password
    )

    db.add(new_user)
    db.commit()

    return {"message": "Signup success"}


@app.post("/login")
def login(data: AuthRequest, db: Session = Depends(get_db)):

    user = db.query(model.Users).filter(
        model.Users.username == data.username
    ).first()

    if not user or not password_hash.verify(
        data.password,
        user.password
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    token = jwt.encode({"username": data.username},
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return {"token": token}

@app.get("/messages")
def get_messages(db: Session = Depends(get_db)):

    messages = db.query(model.Messages).filter(
        model.Messages.message_type == "text",
        model.Messages.receiver.is_(None)
    ).order_by(
        model.Messages.created_at.asc()
    ).all()

    return messages

@app.get("/private-messages/{username}")
def get_private_messages(
    username: str,
    db: Session = Depends(get_db)
):
    messages = db.query(model.Messages).filter(
        (
            (model.Messages.sender == username) |
            (model.Messages.receiver == username)
        ),
        model.Messages.message_type == "private"
    ).order_by(
        model.Messages.created_at.asc()
    ).all()

    return messages



@app.websocket("/ws")
async def websocket_endpoint(
    ws: WebSocket,
    token: str,
    db: Session = Depends(get_db)
):
    await ws.accept()

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        username = payload["username"]
        active_users[username] = ws

        await broadcast_users()

        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)

            # Typing
            if msg["type"] == "typing":
                await broadcast_except(username, {
                    "type": "typing",
                    "user": username
                })

            # Public message
            elif msg["type"] == "message":

                new_message = model.Messages(
                    sender=username,
                    message=msg["data"],
                    message_type="text"
                )

                db.add(new_message)
                db.commit()

                await broadcast({
                    "type": "message",
                    "user": username,
                    "text": msg["data"]
                })

            # Image
            elif msg["type"] == "image":

                await broadcast({
                    "type": "image",
                    "user": username,
                    "data": msg["data"]
                })

            # Private message
            elif msg["type"] == "private":

                to = msg["to"]

                new_message = model.Messages(
                    sender=username,
                    receiver=to,
                    message=msg["data"],
                    message_type="private"
                )

                db.add(new_message)
                db.commit()

                await send_private_message(
                    to,
                    {
                        "type": "private",
                        "from": username,
                        "text": msg["data"]
                    }
                )

    except WebSocketDisconnect:
        active_users.pop(username, None)
        await broadcast_users()


async def send_private_message(to, message):

    if to in active_users:
        await active_users[to].send_text(
            json.dumps(message)
        )


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