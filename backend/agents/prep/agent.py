"""Pre-op preparation deepagent — fetches guidelines, builds patient context, generates procedure steps."""

from cases.llm import openai_chat_config
from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from deepagents.middleware.summarization import create_summarization_tool_middleware
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware
from langchain_openai import ChatOpenAI

from shared.tools_library import query_library_db, read_textbook_file
from shared.tools_web import web_search, web_extract
from shared.pubmed import pubmed_search, pubmed_detail
from agents.prep.tools import (
    save_procedure_steps,
    save_context_file,
    read_patient_info,
    list_patient_context,
    download_guideline_pdf,
    save_textbook_extract,
)

PREP_SYSTEM_PROMPT = """You are a fast surgery prep agent. Be quick and direct. Do NOT over-research.

WORKFLOW — execute in order, no extra loops:

1. read_patient_info — get patient details.
2. query_library_db ONCE — search for the procedure.
3. read_textbook_file ONCE — read the best result.
4. save_textbook_extract — save what you found.
5. web_search ONCE — find guidelines for this procedure.
6. save_context_file — save a brief guidelines summary.
7. save_procedure_steps — 8-12 steps, each with ONLY step_number, title, one-line description. Keep it SHORT.

DONE. Stop after step 7.

RULES:
- One call per fetch tool. No redundant searches.
- query_library_db: SELECT title, book_title, block_file_path FROM headings_fts WHERE headings_fts MATCH 'procedure' ORDER BY rank LIMIT 5
- save_procedure_steps: MINIMAL steps only — title + one sentence description. No instruments, no warnings, no considerations. Fast.
"""


def create_prep_agent():
    model, base_url, api_key = openai_chat_config()

    llm = ChatOpenAI(
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=0.2,
        max_tokens=4096,
    )

    return create_deep_agent(
        model=llm,
        tools=[
            read_patient_info,
            query_library_db,
            read_textbook_file,
            pubmed_search,
            pubmed_detail,
            web_search,
            web_extract,
            save_procedure_steps,
            save_context_file,
            save_textbook_extract,
            download_guideline_pdf,
            list_patient_context,
        ],
        system_prompt=PREP_SYSTEM_PROMPT,
        middleware=[
            ModelCallLimitMiddleware(run_limit=20, exit_behavior="end"),
            ToolCallLimitMiddleware(tool_name="query_library_db", run_limit=2, exit_behavior="continue"),
            ToolCallLimitMiddleware(tool_name="read_textbook_file", run_limit=2, exit_behavior="continue"),
            ToolCallLimitMiddleware(tool_name="pubmed_search", run_limit=1, exit_behavior="continue"),
            ToolCallLimitMiddleware(tool_name="pubmed_detail", run_limit=1, exit_behavior="continue"),
            ToolCallLimitMiddleware(tool_name="web_search", run_limit=1, exit_behavior="continue"),
            ToolCallLimitMiddleware(tool_name="web_extract", run_limit=1, exit_behavior="continue"),
            create_summarization_tool_middleware(llm, StateBackend()),
        ],
        subagents=[{
            "name": "general-purpose",
            "description": "Do not use.",
            "system_prompt": "Not available.",
            "tools": [],
        }],
    )


prep_agent = create_prep_agent()
