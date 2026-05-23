from flask import Flask, render_template, request, jsonify, session, redirect
from flask_cors import CORS
import sqlite3
import json
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "baccarat_secret_2026"
CORS(app)

DB = "baccarat_system.db"

ADMIN_USER = "admin"
ADMIN_PASS = "Baccarat2026!"

DG_TABLES = ["RB01","RB02","RB03","RB04","RB05","RB06","RB07","RB08","RB09","RB10"]
MT_TABLES = ["01","02","03","03A","04","05","06","07","08","09","10"]


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column(cur, table, col, typ):
    cols = [r["name"] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
    if col not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS members(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        expire TEXT,
        enabled INTEGER DEFAULT 1,
        role TEXT DEFAULT 'member',
        agent TEXT DEFAULT '',
        currentPlatform TEXT DEFAULT '',
        currentTable TEXT DEFAULT '',
        device TEXT DEFAULT '',
        ip TEXT DEFAULT '',
        lastLogin TEXT DEFAULT '',
        lastActive TEXT DEFAULT '',
        createdAt TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS records(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT,
        table_name TEXT,
        result TEXT,
        cards TEXT,
        source TEXT,
        countBet INTEGER DEFAULT 0,
        aiSuggest TEXT,
        aiHit INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS ai_learning(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT,
        table_name TEXT,
        bankerScore REAL DEFAULT 50,
        playerScore REAL DEFAULT 50,
        totalPredict INTEGER DEFAULT 0,
        totalHit INTEGER DEFAULT 0,
        updatedAt TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT
