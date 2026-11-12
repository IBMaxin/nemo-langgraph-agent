import sqlite3
from pathlib import Path
from typing import Any

from src.agent.core.decorators import guardrailed_action
from src.agent.core.security import sanitize_memory_content

DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "memory.db"


def _get_connection(db_file: Path | None = None) -> sqlite3.Connection:
    target_path = db_file or DB_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target_path), check_same_thread=False)

    try:
        import sqlite_vec

        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
    except Exception:
        pass

    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE,
            content TEXT,
            category TEXT DEFAULT 'general',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
            key,
            content,
            category,
            content='memories',
            content_rowid='id'
        );
    """)

    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
            INSERT INTO memories_fts(rowid, key, content, category) VALUES (new.id, new.key, new.content, new.category);
        END;
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, key, content, category) VALUES('delete', old.id, old.key, old.content, old.category);
        END;
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, key, content, category) VALUES('delete', old.id, old.key, old.content, old.category);
            INSERT INTO memories_fts(rowid, key, content, category) VALUES (new.id, new.key, new.content, new.category);
        END;
    """)

    conn.commit()
    return conn


@guardrailed_action(name="store_memory")
async def store_memory(key: str, content: str, category: str = "general") -> dict[str, Any]:
    """Stores information or facts in local SQLite memory with FTS5 indexing."""
    if not key or not key.strip():
        return {"success": False, "error": "Memory key cannot be empty."}

    if not content or not content.strip():
        return {"success": False, "error": "Memory content cannot be empty."}

    clean_key = key.strip()
    clean_category = category.strip() if category else "general"
    clean_content, was_sanitized, detected = sanitize_memory_content(content)

    if not clean_content:
        return {
            "success": False,
            "error": "Content contained only prompt injection directives.",
        }

    try:
        conn = _get_connection()
        with conn:
            conn.execute(
                """
                INSERT INTO memories (key, content, category, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    content=excluded.content,
                    category=excluded.category,
                    updated_at=CURRENT_TIMESTAMP;
            """,
                (clean_key, clean_content, clean_category),
            )

        msg = f"Stored '{clean_key}' under '{clean_category}'."
        if was_sanitized:
            msg += f" (Sanitized prompt injection: {detected})"

        return {
            "success": True,
            "key": clean_key,
            "category": clean_category,
            "was_sanitized": was_sanitized,
            "sanitized_content": clean_content,
            "message": msg,
        }
    except Exception as e:
        return {"success": False, "error": f"Database error: {e}"}


@guardrailed_action(name="search_memory")
async def search_memory(query: str, limit: int = 5) -> dict[str, Any]:
    """Searches local memory using SQLite FTS5 full-text search with BM25 ranking."""
    if not query or not query.strip():
        return {"success": False, "error": "Query cannot be empty."}

    clean_query = query.strip()
    matches: list[dict[str, Any]] = []

    try:
        conn = _get_connection()
        cursor = conn.cursor()

        fts_query = " OR ".join([f'"{term}"' for term in clean_query.split() if term])
        try:
            cursor.execute(
                """
                SELECT m.key, m.content, m.category, m.updated_at, rank
                FROM memories_fts f
                JOIN memories m ON f.rowid = m.id
                WHERE memories_fts MATCH ?
                ORDER BY rank
                LIMIT ?;
            """,
                (fts_query, limit),
            )
            for row in cursor.fetchall():
                matches.append(
                    {
                        "key": row[0],
                        "content": row[1],
                        "category": row[2],
                        "updated_at": row[3],
                    }
                )
        except Exception:
            matches = []

        if not matches:
            cursor.execute(
                """
                SELECT key, content, category, updated_at
                FROM memories
                WHERE key LIKE ? OR content LIKE ?
                ORDER BY updated_at DESC
                LIMIT ?;
            """,
                (f"%{clean_query}%", f"%{clean_query}%", limit),
            )
            for row in cursor.fetchall():
                matches.append(
                    {
                        "key": row[0],
                        "content": row[1],
                        "category": row[2],
                        "updated_at": row[3],
                    }
                )

        return {
            "success": True,
            "query": clean_query,
            "count": len(matches),
            "results": matches,
        }
    except Exception as e:
        return {"success": False, "error": f"Search error: {e}"}
