# Medical Library Skill

Access medical textbooks via a local SQLite FTS5 database.

## Tools
- `query_library_db` — Execute SQL queries against the library
- `read_textbook_file` — Read markdown block files

## Database Views

| View | Purpose |
|------|---------|
| `v_book_overview` | Browse catalog: isbn, title, speciality, total_blocks, file_path |
| `v_toc` | Table of contents: speciality, book_title, book_isbn, level, heading, block_number, block_file_path, line_number |
| `v_paragraphs` | All paragraphs: id, speciality, book_title, book_isbn, section_heading, text, line_start, line_end, block_number, block_file_path |

## Full-Text Search (FTS5)

### paragraphs_fts — Search paragraph content
Best for: specific facts, drug names, mechanisms, surgical steps.
```sql
SELECT book_title, section_heading, block_file_path, line_start, line_end,
       snippet(paragraphs_fts, 0, '>>>', '<<<', '...', 30) as snippet
FROM paragraphs_fts WHERE paragraphs_fts MATCH 'search terms' ORDER BY rank LIMIT 10
```

### headings_fts — Search section headings
Best for: finding chapters, broad topics, procedure sections.
```sql
SELECT title, book_title, speciality, block_file_path, line_number
FROM headings_fts WHERE headings_fts MATCH 'search terms' ORDER BY rank LIMIT 10
```

## FTS5 Syntax
- `"phrase"` — exact phrase match
- `term1 AND term2` — both terms present
- `prefix*` — prefix matching
- `term1 OR term2` — either term
- Hyphenated terms MUST be double-quoted: `'"Sturge-Weber" syndrome'`

## Search Strategy for Surgical Prep

1. **Find relevant books**: Query `v_book_overview` for speciality matching the surgery
2. **Find procedure sections**: Use `headings_fts` MATCH for the procedure name
3. **Get details**: Use `paragraphs_fts` for specific aspects (instruments, steps, complications)
4. **Read content**: Use `read_textbook_file` with the block_file_path from results

## Rules
- Max 20 rows per query
- Only SELECT/WITH queries allowed
- Always use line offsets from results when reading files
- Copy file_path verbatim from query output
