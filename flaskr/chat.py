import os
import uuid
from flask import (
    Blueprint, flash, g, redirect, render_template, request, url_for, jsonify, session
)
from groq import Groq
from dotenv import load_dotenv
from flaskr.db import get_db

load_dotenv()

bp = Blueprint('chat', __name__)

def get_groq_client():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    return Groq(api_key=api_key)

def get_session_owner_id():
    """Returns logged-in user id or session key string for guest users."""
    if g.user:
        return g.user['id']
    if 'session_key' not in session:
        session['session_key'] = str(uuid.uuid4())
    return session['session_key']

@bp.route('/api/conversations', methods=['GET'])
def list_conversations():
    owner = get_session_owner_id()
    db = get_db()
    
    if isinstance(owner, int):
        cursor = db.execute(
            "SELECT id, title, created_at FROM conversations WHERE user_id = ? ORDER BY created_at DESC",
            (owner,)
        )
    else:
        cursor = db.execute(
            "SELECT id, title, created_at FROM conversations WHERE user_id IS NULL AND id LIKE ? ORDER BY created_at DESC",
            (f"{owner}%",)
        )
        
    conversations = [
        {"id": row['id'], "title": row['title'], "created_at": str(row['created_at'])}
        for row in cursor.fetchall()
    ]
    return jsonify({"conversations": conversations}), 200

@bp.route('/api/conversations', methods=['POST'])
def create_conversation():
    owner = get_session_owner_id()
    data = request.get_json() or {}
    title = data.get('title', 'New Chat').strip() or 'New Chat'
    
    # Generate unique ID
    conv_id = f"{owner}_{uuid.uuid4().hex[:8]}" if isinstance(owner, str) else str(uuid.uuid4())
    user_id = owner if isinstance(owner, int) else None

    db = get_db()
    db.execute(
        "INSERT INTO conversations (id, user_id, title) VALUES (?, ?, ?)",
        (conv_id, user_id, title)
    )
    db.commit()

    return jsonify({"id": conv_id, "title": title}), 201

@bp.route('/api/conversations/<conv_id>/messages', methods=['GET'])
def get_conversation_messages(conv_id):
    db = get_db()
    cursor = db.execute(
        "SELECT role, content, timestamp FROM messages WHERE conversation_id = ? ORDER BY id ASC",
        (conv_id,)
    )
    messages = [
        {"role": row['role'], "content": row['content'], "timestamp": str(row['timestamp'])}
        for row in cursor.fetchall()
    ]
    return jsonify({"messages": messages}), 200

@bp.route('/api/conversations/<conv_id>/messages', methods=['POST'])
def send_message(conv_id):
    data = request.get_json() or {}
    user_message = data.get('message', '').strip()

    if not user_message:
        return jsonify({"error": "Message content cannot be empty"}), 400

    db = get_db()

    # Check if conversation exists, create if not
    conv = db.execute("SELECT id, title FROM conversations WHERE id = ?", (conv_id,)).fetchone()
    if not conv:
        owner = get_session_owner_id()
        user_id = owner if isinstance(owner, int) else None
        title = user_message[:30] if len(user_message) > 30 else user_message
        db.execute(
            "INSERT INTO conversations (id, user_id, title) VALUES (?, ?, ?)",
            (conv_id, user_id, title)
        )
        db.commit()
    elif conv['title'] == 'New Chat':
        # Auto-update title based on first user prompt
        new_title = user_message[:30] + ("..." if len(user_message) > 30 else "")
        db.execute("UPDATE conversations SET title = ? WHERE id = ?", (new_title, conv_id))
        db.commit()

    # Save user message
    db.execute(
        "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
        (conv_id, 'user', user_message)
    )
    db.commit()

    # Fetch past conversation history
    cursor = db.execute(
        "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id ASC",
        (conv_id,)
    )
    history = [{"role": "system", "content": "You are a concise, helpful assistant."}]
    for row in cursor.fetchall():
        history.append({"role": row['role'], "content": row['content']})

    client = get_groq_client()
    if not client:
        reply_text = "GROQ_API_KEY is not configured in your .env file."
    else:
        try:
            bot_response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=history,
                temperature=0.7
            )
            reply_text = bot_response.choices[0].message.content
        except Exception as e:
            reply_text = f"Error from Groq API: {str(e)}"

    # Save assistant response
    db.execute(
        "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
        (conv_id, 'assistant', reply_text)
    )
    db.commit()

    # Get updated title
    current_conv = db.execute("SELECT title FROM conversations WHERE id = ?", (conv_id,)).fetchone()
    title = current_conv['title'] if current_conv else 'Chat'

    return jsonify({"reply": reply_text, "title": title}), 200

@bp.route('/api/conversations/<conv_id>', methods=['DELETE'])
def delete_conversation(conv_id):
    db = get_db()
    db.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
    db.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    db.commit()
    return jsonify({"success": True, "message": "Conversation deleted"}), 200