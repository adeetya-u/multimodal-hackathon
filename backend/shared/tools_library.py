"""Tools for the doctor voice agent — queries local SQLite and reads textbook files."""

import asyncio
import re
from pathlib import Path

import aiosqlite
from langchain_core.tools import tool

from shared.paths import DATA_DIR, DB_PATH, TEXTBOOKS_DIR

MAX_ROWS = 20

_pool: asyncio.Queue[aiosqlite.Connection] | None = None
_pool_lock = asyncio.Lock()


async def _open_conn() -> aiosqlite.Connection:
    conn = await aiosqlite.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    await conn.execute("PRAGMA busy_timeout = 30000")
    await conn.execute("PRAGMA mmap_size = 268435456")
    conn.row_factory = aiosqlite.Row
    return conn


async def _get_pool() -> asyncio.Queue[aiosqlite.Connection]:
    global _pool
    async with _pool_lock:
        if _pool is None:
            _pool = asyncio.Queue(maxsize=5)
            for _ in range(5):
                _pool.put_nowait(await _open_conn())
    return _pool


_MATCH_RE = re.compile(r"(MATCH\s+')([^']+)(')", re.IGNORECASE)
_HYPHENATED_TOKEN_RE = re.compile(r'(?<!")(\b\w+(?:-\w+)+\b)(?!")')


def _sanitize_fts_match(sql: str) -> str:
    def _quote_hyphenated(m: re.Match) -> str:
        prefix, value, suffix = m.group(1), m.group(2), m.group(3)
        fixed = _HYPHENATED_TOKEN_RE.sub(r'"\1"', value)
        return f"{prefix}{fixed}{suffix}"
    return _MATCH_RE.sub(_quote_hyphenated, sql)


@tool
async def query_library_db(sql: str) -> str:
    """Execute a read-only SQL query against the medical textbook library database.

    Key views:
    - v_book_overview: isbn, title, speciality, total_blocks, file_path
    - v_toc: speciality, book_title, book_isbn, level, heading, block_number, block_file_path, line_number
    - v_paragraphs: id, speciality, book_title, book_isbn, section_heading, text, line_start, line_end, block_number, block_file_path

    FTS5 heading search:
        SELECT title, book_title, speciality, block_file_path, line_number
        FROM headings_fts WHERE headings_fts MATCH 'search terms' ORDER BY rank LIMIT 10

    FTS5 paragraph search:
        SELECT book_title, section_heading, block_file_path, line_start, line_end,
               snippet(paragraphs_fts, 0, '>>>', '<<<', '...', 30) as snippet
        FROM paragraphs_fts WHERE paragraphs_fts MATCH 'search terms' ORDER BY rank LIMIT 10

    FTS5 syntax: "phrase", term1 AND term2, prefix*, term1 OR term2
    Hyphenated terms must be double-quoted: '"Sturge-Weber" syndrome'

    Args:
        sql: A read-only SQL query (SELECT only). Max 20 rows returned.
    """
    normalized = sql.strip().upper()
    if not normalized.startswith("SELECT") and not normalized.startswith("WITH"):
        return "Error: Only SELECT queries are allowed."

    sql = _sanitize_fts_match(sql)

    pool = await _get_pool()
    conn = await pool.get()
    try:
        async with conn.execute(sql) as cursor:
            rows = await cursor.fetchmany(MAX_ROWS + 1)
    except Exception:
        try:
            await conn.close()
        except Exception:
            pass
        conn = await _open_conn()
        try:
            async with conn.execute(sql) as cursor:
                rows = await cursor.fetchmany(MAX_ROWS + 1)
        except Exception as e:
            return f"SQL Error: {e}"
    finally:
        await pool.put(conn)

    if not rows:
        return "No results."

    columns = rows[0].keys()
    header = " | ".join(columns)
    separator = "-+-".join("-" * max(len(c), 8) for c in columns)

    lines = [header, separator]
    for row in rows[:MAX_ROWS]:
        lines.append(" | ".join(
            str(row[c]) if row[c] is not None else "" for c in columns
        ))

    if len(rows) > MAX_ROWS:
        lines.append(f"... ({MAX_ROWS} rows shown, query returned more)")

    return "\n".join(lines)


@tool
async def read_textbook_file(file_path: str, offset: int = 0, limit: int = 100) -> str:
    """Read lines from a textbook markdown file.

    The file_path comes from query_library_db results (block_file_path column).
    Example: "9780071837781/9780071837781_block10.md"

    Args:
        file_path: Relative path within the textbooks directory (from block_file_path column).
        offset: Line number to start reading from (0-based). Default 0.
        limit: Number of lines to read. Default 100.
    """
    full_path = TEXTBOOKS_DIR / file_path
    if not full_path.exists():
        return f"Error: File not found: {file_path}"
    if not full_path.resolve().is_relative_to(TEXTBOOKS_DIR.resolve()):
        return "Error: Access denied."

    text = await asyncio.to_thread(full_path.read_text, encoding="utf-8")
    lines = text.splitlines()

    selected = lines[offset:offset + limit]
    if not selected:
        return f"No content at offset {offset} (file has {len(lines)} lines)."

    result = "\n".join(selected)
    if offset + limit < len(lines):
        result += f"\n\n[... {len(lines) - offset - limit} more lines. Use offset={offset + limit} to continue.]"
    return result
