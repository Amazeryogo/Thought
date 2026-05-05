from flask import request
from flask_socketio import emit, join_room, leave_room
from flask_login import current_user
from core import socketio, db
from models import Messages, User
from datetime import datetime

def update_last_seen():
    if current_user.is_authenticated:
        db.userdb.update_one(
            {"_id": current_user._id},
            {"$set": {"last_seen": datetime.utcnow()}}
        )

@socketio.on('join')
def on_join(data):
    if not current_user.is_authenticated:
        print("Unauthenticated join attempt")
        return
    room = current_user.username
    join_room(room)
    print(f"User {current_user.username} joined their notification room: {room}")
    update_last_seen()

@socketio.on('leave')
def on_leave(data):
    if not current_user.is_authenticated:
        return
    room = current_user.username
    leave_room(room)
    print(f"User {current_user.username} left their notification room: {room}")

@socketio.on('send_message')
def handle_send_message(data):
    if not current_user.is_authenticated:
        print("Unauthorized send_message attempt")
        return

    update_last_seen()
    recipient = data.get('recipient')
    content = data.get('message')

    if not recipient or not content:
        print(f"Malformed message from {current_user.username}")
        return

    try:
        # Save message to DB
        msg_json = Messages.send_message(current_user.username, recipient, content)

        # Emit to recipient's room
        emit('new_message', msg_json, room=recipient)

        # Emit back to sender to confirm
        emit('message_sent', msg_json)
        print(f"Message from {current_user.username} to {recipient} delivered.")
    except Exception as e:
        print(f"Error sending message: {str(e)}")
        emit('error', {'message': 'Failed to send message.'})

@socketio.on('mark_read')
def handle_mark_read(data):
    if not current_user.is_authenticated:
        return

    other_user = data.get('username')
    if other_user:
        Messages.mark_as_read(other_user, current_user.username)
        emit('messages_read', {'username': other_user}, room=other_user)
