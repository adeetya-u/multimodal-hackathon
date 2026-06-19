import asyncio
import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from backend.cases.prompts import build_logger_router_prompt
from backend.cases.checklist import ChecklistState, ChecklistStep
from backend.cases.bedrock import converse_text

load_dotenv()

async def main():
    checklist = ChecklistState(procedure="test", mode="logging", steps=[
        ChecklistStep(id="1", label="Incision", aliases=["cut"]),
        ChecklistStep(id="2", label="Allergy Check", aliases=["allergies"])
    ])
    
    # Test 1: Ask a question
    prompt1 = build_logger_router_prompt(
        current_mode="logging",
        step_checklist=checklist,
        segment="Can you tell me more about this patient's allergy history?",
        context_block=""
    )
    res1 = await asyncio.to_thread(converse_text, prompt1, model="amazon.nova-lite-v1:0")
    print("TEST 1: Question")
    print(res1)
    
    # Test 2: Logging after a question, assuming mode got stuck
    prompt2 = build_logger_router_prompt(
        current_mode="logging",
        step_checklist=checklist,
        segment="The allergy test seems to be working just fine.",
        context_block=""
    )
    res2 = await asyncio.to_thread(converse_text, prompt2, model="amazon.nova-lite-v1:0")
    print("\nTEST 2: Regular log while stuck in 'query' mode")
    print(res2)
    
if __name__ == "__main__":
    asyncio.run(main())
