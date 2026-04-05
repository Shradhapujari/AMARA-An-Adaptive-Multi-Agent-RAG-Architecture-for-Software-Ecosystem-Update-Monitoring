"""
Unified Autonomous Agent System
Combines: Coding + Research + Customer Support + Workflow + CrewAI Multi-Agent + Browser agents
Orchestrated with RLAIF evaluation loop — runs on Ollama (llama3.1:latest)

Usage:
  python unified_agent_system.py
  python unified_agent_system.py --task "your task here"
  python unified_agent_system.py --demo   # runs all 6 agent demos
"""

import json
import re
import time
import argparse
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field

try:
    from ollama import Client as OllamaClient
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────

MODEL = "llama3.1:latest"
TEMPERATURE = 0.0      # deterministic for demos
MAX_RETRIES = 2        # RLAIF retry limit

# ──────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────

@dataclass
class AgentResult:
    agent_name: str
    task: str
    output: str
    score: float = 0.0
    retries: int = 0
    tools_used: list = field(default_factory=list)
    duration_ms: int = 0

@dataclass
class UnifiedResult:
    original_query: str
    agents_activated: list
    results: list
    final_answer: str
    total_duration_ms: int
    rlaif_improved: bool = False


# ──────────────────────────────────────────────
# LLM caller (Ollama or mock fallback)
# ──────────────────────────────────────────────

def call_llm(system_prompt: str, user_prompt: str, temperature: float = TEMPERATURE) -> str:
    """Call Ollama. Falls back to structured mock if Ollama not running."""
    if OLLAMA_AVAILABLE:
        try:
            client = OllamaClient()
            response = client.chat(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                options={"temperature": temperature}
            )
            return response["message"]["content"].strip()
        except Exception as e:
            return f"[Ollama error: {e}] Using mock response for: {user_prompt[:80]}"

    # Structured mock when Ollama not available
    return f"[MOCK LLM] System: {system_prompt[:60]}... | Query: {user_prompt[:80]}..."


# ──────────────────────────────────────────────
# 1. CODING AGENT  (GitHub Copilot / Cursor style)
# ──────────────────────────────────────────────

class CodingAgent:
    """
    Reads repo context, writes code, runs tests, fixes errors in a loop.
    Inspired by: GitHub Copilot, Cursor, Claude Code
    """
    name = "CodingAgent"

    SYSTEM = """You are an expert software engineer agent.
Given a coding task, you:
1. Analyze the requirement
2. Write clean, working code with docstrings
3. Add test cases
4. Point out potential bugs or edge cases
Respond with: [CODE], [TESTS], [NOTES] sections."""

    def run(self, task: str) -> AgentResult:
        t0 = time.time()
        tools = ["code_writer", "test_runner", "linter"]

        # Step 1: write code
        code_response = call_llm(
            self.SYSTEM,
            f"Task: {task}\nWrite the implementation and tests."
        )

        # Step 2: self-review loop (simulates test-fix loop)
        review = call_llm(
            "You are a code reviewer. Find bugs or improvements.",
            f"Review this code output:\n{code_response[:600]}\nReturn: PASS or list issues."
        )

        final = code_response
        if "PASS" not in review.upper() and len(review) > 20:
            # Simulates fixing based on review
            final = call_llm(
                self.SYSTEM,
                f"Fix the following issues in your code:\n{review}\n\nOriginal:\n{code_response[:400]}"
            )

        return AgentResult(
            agent_name=self.name,
            task=task,
            output=final,
            tools_used=tools,
            duration_ms=int((time.time() - t0) * 1000)
        )


# ──────────────────────────────────────────────
# 2. RESEARCH AGENT  (Perplexity / Deep Research style)
# ──────────────────────────────────────────────

class ResearchAgent:
    """
    Multi-hop search: searches, extracts, synthesizes across sources.
    Inspired by: Perplexity, Deep Research, Elicit
    """
    name = "ResearchAgent"

    SYSTEM = """You are a research agent that synthesizes information from multiple sources.
Given a research query:
1. Identify 3 key sub-questions to answer it fully
2. For each sub-question, provide a detailed answer
3. Synthesize into a final comprehensive answer with citations
Format: [SUB-QUESTIONS] → [FINDINGS] → [SYNTHESIS]"""

    def _simulate_search(self, query: str) -> str:
        """Simulates web search retrieval."""
        return call_llm(
            "You are a web search engine. Return 3 relevant facts about the query.",
            f"Search query: {query}"
        )

    def run(self, task: str) -> AgentResult:
        t0 = time.time()
        tools = ["web_search", "document_retriever", "fact_extractor"]

        # Multi-hop: decompose → search each → synthesize
        decomposition = call_llm(
            "Break this research question into 3 focused sub-questions. Return them as a numbered list.",
            f"Research question: {task}"
        )

        # Simulate searching each sub-question
        search_results = []
        for i, line in enumerate(decomposition.split("\n")[:3]):
            if line.strip():
                result = self._simulate_search(line)
                search_results.append(f"Sub-question {i+1}: {result[:200]}")

        combined = "\n".join(search_results)

        synthesis = call_llm(
            self.SYSTEM,
            f"Original query: {task}\n\nSearch findings:\n{combined}\n\nSynthesize a complete answer."
        )

        return AgentResult(
            agent_name=self.name,
            task=task,
            output=synthesis,
            tools_used=tools,
            duration_ms=int((time.time() - t0) * 1000)
        )


# ──────────────────────────────────────────────
# 3. CUSTOMER SUPPORT AGENT  (Salesforce Agentforce style)
# ──────────────────────────────────────────────

MOCK_CRM = {
    "ORD-001": {"customer": "Alice Chen", "product": "Pro Plan", "status": "active", "issue": None},
    "ORD-002": {"customer": "Bob Smith", "product": "Starter Plan", "status": "cancelled", "issue": "billing"},
    "ORD-003": {"customer": "Carol Wu", "product": "Enterprise", "status": "active", "issue": "feature_request"},
}

class CustomerSupportAgent:
    """
    Looks up orders, resolves tickets, updates CRM records end-to-end.
    Inspired by: Salesforce Agentforce, Intercom Fin, Zendesk AI
    """
    name = "CustomerSupportAgent"

    SYSTEM = """You are a customer support agent with CRM access.
You can: look up orders, check status, issue refunds, escalate issues.
Always be empathetic, concise, and resolution-focused.
Format response as: [DIAGNOSIS] → [ACTION TAKEN] → [RESOLUTION]"""

    def _lookup_order(self, order_id: str) -> dict:
        return MOCK_CRM.get(order_id.upper(), {"error": "Order not found"})

    def _extract_order_id(self, text: str) -> Optional[str]:
        match = re.search(r"ORD-\d+", text.upper())
        return match.group(0) if match else None

    def run(self, task: str) -> AgentResult:
        t0 = time.time()
        tools = ["crm_lookup", "ticket_creator", "refund_processor"]

        order_id = self._extract_order_id(task)
        crm_context = ""
        if order_id:
            record = self._lookup_order(order_id)
            crm_context = f"\nCRM Record: {json.dumps(record, indent=2)}"

        response = call_llm(
            self.SYSTEM,
            f"Support ticket: {task}{crm_context}\n\nResolve this ticket."
        )

        return AgentResult(
            agent_name=self.name,
            task=task,
            output=response,
            tools_used=tools,
            duration_ms=int((time.time() - t0) * 1000)
        )


# ──────────────────────────────────────────────
# 4. WORKFLOW AGENT  (Zapier AI / n8n style)
# ──────────────────────────────────────────────

class WorkflowAgent:
    """
    Connects apps, automates multi-step processes, triggers actions.
    Inspired by: Zapier AI, n8n, Make.com
    """
    name = "WorkflowAgent"

    SYSTEM = """You are an automation workflow agent.
Given a task, you design and execute a multi-step automation workflow:
1. Parse the trigger event
2. Identify the apps/services involved
3. Design the workflow steps (Trigger → Filter → Transform → Action → Notify)
4. Generate the workflow config as JSON
5. Simulate execution and return results"""

    def run(self, task: str) -> AgentResult:
        t0 = time.time()
        tools = ["webhook_listener", "api_connector", "data_transformer", "notification_sender"]

        # Step 1: design workflow
        design = call_llm(
            self.SYSTEM,
            f"Design a workflow for: {task}\nReturn a JSON workflow config with: trigger, steps[], actions[]"
        )

        # Step 2: simulate execution
        execution = call_llm(
            "You are a workflow execution engine. Simulate running this workflow and return results.",
            f"Workflow:\n{design[:400]}\n\nSimulate execution. Show each step status: SUCCESS/FAILED."
        )

        combined = f"WORKFLOW DESIGN:\n{design}\n\nEXECUTION LOG:\n{execution}"

        return AgentResult(
            agent_name=self.name,
            task=task,
            output=combined,
            tools_used=tools,
            duration_ms=int((time.time() - t0) * 1000)
        )


# ──────────────────────────────────────────────
# 5. CREW AGENT  (CrewAI / AutoGPT multi-agent style)
# ──────────────────────────────────────────────

class CrewAgent:
    """
    Multiple specialized sub-agents collaborate: Manager → Analyst → Writer → Reviewer
    Inspired by: CrewAI, AutoGPT, your own multiagent_rag_v2.py
    """
    name = "CrewAgent"

    def _manager(self, task: str) -> str:
        return call_llm(
            "You are a project manager. Break this task into 3 sub-tasks for your team.",
            f"Task: {task}\nReturn: SUBTASK_1, SUBTASK_2, SUBTASK_3"
        )

    def _analyst(self, subtask: str) -> str:
        return call_llm(
            "You are a data analyst. Analyze and provide insights.",
            f"Analyze: {subtask}"
        )

    def _writer(self, analysis: str, original_task: str) -> str:
        return call_llm(
            "You are a technical writer. Synthesize analysis into a clear response.",
            f"Original task: {original_task}\nAnalysis: {analysis[:400]}\nWrite the final answer."
        )

    def _reviewer(self, draft: str) -> str:
        return call_llm(
            "You are a quality reviewer. Review for accuracy and completeness. Return: APPROVED or list issues.",
            f"Review: {draft[:400]}"
        )

    def run(self, task: str) -> AgentResult:
        t0 = time.time()
        tools = ["manager_agent", "analyst_agent", "writer_agent", "reviewer_agent"]

        # Multi-agent pipeline
        plan = self._manager(task)
        analysis = self._analyst(plan)
        draft = self._writer(analysis, task)
        review = self._reviewer(draft)

        if "APPROVED" not in review.upper():
            # One revision pass
            draft = self._writer(f"{analysis}\n\nRevision notes: {review}", task)

        crew_log = (
            f"MANAGER PLAN:\n{plan}\n\n"
            f"ANALYST FINDINGS:\n{analysis[:300]}\n\n"
            f"FINAL ANSWER:\n{draft}"
        )

        return AgentResult(
            agent_name=self.name,
            task=task,
            output=crew_log,
            tools_used=tools,
            duration_ms=int((time.time() - t0) * 1000)
        )


# ──────────────────────────────────────────────
# 6. BROWSER AGENT  (Claude Computer Use / Operator style)
# ──────────────────────────────────────────────

class BrowserAgent:
    """
    Navigates websites, fills forms, extracts structured data.
    Inspired by: Claude Computer Use, Operator, Browser Use
    """
    name = "BrowserAgent"

    SYSTEM = """You are a browser automation agent.
Given a web task, you:
1. Plan the navigation steps (URL → actions → extract)
2. Generate the browser automation script (Playwright-style pseudocode)
3. Describe what was found/done on each page
4. Return the extracted data or confirmation of action taken
Format: [NAVIGATION PLAN] → [ACTIONS] → [EXTRACTED DATA]"""

    def run(self, task: str) -> AgentResult:
        t0 = time.time()
        tools = ["navigate", "click", "fill_form", "extract_text", "screenshot"]

        # Plan navigation
        plan = call_llm(
            self.SYSTEM,
            f"Browser task: {task}\n\nGenerate a step-by-step browser automation plan with pseudocode."
        )

        # Simulate page interactions
        simulation = call_llm(
            "You are a browser. Simulate executing these navigation steps and return what you found.",
            f"Automation plan:\n{plan[:400]}\n\nReturn simulated results for each step."
        )

        output = f"AUTOMATION PLAN:\n{plan}\n\nSIMULATED EXECUTION:\n{simulation}"

        return AgentResult(
            agent_name=self.name,
            task=task,
            output=output,
            tools_used=tools,
            duration_ms=int((time.time() - t0) * 1000)
        )


# ──────────────────────────────────────────────
# RLAIF EVALUATOR
# ──────────────────────────────────────────────

class RLAIFEvaluator:
    """
    Scores agent outputs 0-10 and triggers retry if below threshold.
    Zero Human Feedback — LLM judges LLM.
    """
    THRESHOLD = 6.0

    SYSTEM = """You are a strict quality evaluator for AI agent outputs.
Score the response on:
- Relevance to the task (0-3)
- Completeness (0-3)
- Clarity and structure (0-2)
- Actionability (0-2)
Total: 0-10. Return ONLY: {"score": X, "reason": "brief reason", "suggestion": "improvement"}"""

    def evaluate(self, task: str, output: str) -> tuple[float, str]:
        raw = call_llm(
            self.SYSTEM,
            f"Task: {task}\n\nAgent output:\n{output[:500]}\n\nScore this output."
        )
        try:
            # Try to parse JSON from response
            match = re.search(r'\{.*?\}', raw, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                return float(data.get("score", 5.0)), data.get("suggestion", "")
        except Exception:
            pass
        # Fallback: extract any number 0-10
        numbers = re.findall(r'\b([0-9]|10)\b', raw)
        score = float(numbers[0]) if numbers else 5.0
        return score, raw[:100]

    def should_retry(self, score: float) -> bool:
        return score < self.THRESHOLD


# ──────────────────────────────────────────────
# ORCHESTRATOR — routes + merges + evaluates
# ──────────────────────────────────────────────

class UnifiedOrchestrator:
    """
    Routes any task to the right sub-agent(s), merges results,
    runs RLAIF evaluation, retries if score too low.
    """

    ROUTING_SYSTEM = """You are a task router. Given a user task, identify which agents should handle it.
Available agents: CodingAgent, ResearchAgent, CustomerSupportAgent, WorkflowAgent, CrewAgent, BrowserAgent
Rules:
- coding/programming/debug/implement → CodingAgent
- research/explain/summarize/find info → ResearchAgent
- customer/order/refund/ticket/support → CustomerSupportAgent
- automate/workflow/trigger/connect apps → WorkflowAgent
- complex multi-step/analysis/team task → CrewAgent
- web/browser/scrape/navigate/fill form → BrowserAgent
Return ONLY a JSON array of agent names, e.g. ["ResearchAgent", "CodingAgent"]"""

    def __init__(self):
        self.agents = {
            "CodingAgent":          CodingAgent(),
            "ResearchAgent":        ResearchAgent(),
            "CustomerSupportAgent": CustomerSupportAgent(),
            "WorkflowAgent":        WorkflowAgent(),
            "CrewAgent":            CrewAgent(),
            "BrowserAgent":         BrowserAgent(),
        }
        self.evaluator = RLAIFEvaluator()

    def _route(self, task: str) -> list[str]:
        raw = call_llm(self.ROUTING_SYSTEM, f"Task: {task}")
        try:
            match = re.search(r'\[.*?\]', raw, re.DOTALL)
            if match:
                names = json.loads(match.group(0))
                valid = [n for n in names if n in self.agents]
                if valid:
                    return valid
        except Exception:
            pass
        # Fallback: keyword match
        task_lower = task.lower()
        if any(w in task_lower for w in ["code", "function", "bug", "implement", "python"]):
            return ["CodingAgent"]
        if any(w in task_lower for w in ["order", "refund", "support", "ticket"]):
            return ["CustomerSupportAgent"]
        if any(w in task_lower for w in ["automate", "workflow", "trigger", "zapier"]):
            return ["WorkflowAgent"]
        if any(w in task_lower for w in ["browse", "website", "navigate", "scrape"]):
            return ["BrowserAgent"]
        if any(w in task_lower for w in ["analyze", "team", "complex", "multiple"]):
            return ["CrewAgent"]
        return ["ResearchAgent"]

    def _merge(self, task: str, results: list[AgentResult]) -> str:
        if len(results) == 1:
            return results[0].output

        summary_parts = []
        for r in results:
            summary_parts.append(f"[{r.agent_name}]:\n{r.output[:400]}")

        combined = "\n\n---\n\n".join(summary_parts)
        merged = call_llm(
            "You are a synthesis agent. Merge multiple agent outputs into one coherent, non-redundant answer.",
            f"Original task: {task}\n\nAgent outputs:\n{combined}\n\nSynthesize into a single unified response."
        )
        return merged

    def run(self, task: str, verbose: bool = True) -> UnifiedResult:
        t0 = time.time()

        if verbose:
            print(f"\n{'='*60}")
            print(f"  UNIFIED AGENT SYSTEM")
            print(f"  Task: {task[:80]}")
            print(f"{'='*60}")

        # 1. Route
        agent_names = self._route(task)
        if verbose:
            print(f"\n  Routing to: {', '.join(agent_names)}")

        # 2. Run each agent with RLAIF retry
        results = []
        rlaif_improved = False

        for name in agent_names:
            agent = self.agents[name]
            if verbose:
                print(f"\n  [{name}] running...")

            result = agent.run(task)
            score, suggestion = self.evaluator.evaluate(task, result.output)
            result.score = score

            if verbose:
                print(f"  [{name}] RLAIF score: {score:.1f}/10")

            # Retry loop if score below threshold
            retries = 0
            while self.evaluator.should_retry(score) and retries < MAX_RETRIES:
                retries += 1
                rlaif_improved = True
                if verbose:
                    print(f"  [{name}] Score {score:.1f} below threshold. Retry {retries}/{MAX_RETRIES}...")

                retry_task = f"{task}\n\nImprovement needed: {suggestion}"
                result = agent.run(retry_task)
                score, suggestion = self.evaluator.evaluate(task, result.output)
                result.score = score
                result.retries = retries

                if verbose:
                    print(f"  [{name}] Retry score: {score:.1f}/10")

            results.append(result)

        # 3. Merge
        final_answer = self._merge(task, results)

        total_ms = int((time.time() - t0) * 1000)

        if verbose:
            print(f"\n{'─'*60}")
            print("  FINAL ANSWER:")
            print(f"{'─'*60}")
            print(final_answer[:800])
            print(f"\n  Agents used: {[r.agent_name for r in results]}")
            print(f"  RLAIF improved: {rlaif_improved}")
            print(f"  Total time: {total_ms}ms")
            print(f"{'='*60}\n")

        return UnifiedResult(
            original_query=task,
            agents_activated=[r.agent_name for r in results],
            results=results,
            final_answer=final_answer,
            total_duration_ms=total_ms,
            rlaif_improved=rlaif_improved
        )


# ──────────────────────────────────────────────
# DEMO RUNNER — showcases all 6 agent types
# ──────────────────────────────────────────────

DEMO_TASKS = [
    # (label, task)
    ("CODING",    "Write a Python function that finds the top-k most frequent words in a text file, with tests."),
    ("RESEARCH",  "What are the key differences between RAG and fine-tuning for LLM adaptation?"),
    ("SUPPORT",   "Customer ORD-002 says their account was cancelled but they never requested it. Please help."),
    ("WORKFLOW",  "When a new GitHub PR is opened, automatically notify the Slack #dev channel and create a Jira ticket."),
    ("CREW",      "Analyze the pros and cons of using FAISS vs ChromaDB for a production RAG system."),
    ("BROWSER",   "Go to arxiv.org and find the 3 most cited papers on multi-agent systems from 2024."),
]

def run_demo():
    orchestrator = UnifiedOrchestrator()
    print("\n" + "="*60)
    print("  UNIFIED AGENT SYSTEM — FULL DEMO")
    print("  Running all 6 agent type demos...")
    print("="*60)

    for label, task in DEMO_TASKS:
        print(f"\n{'▶'*3} DEMO: {label}")
        result = orchestrator.run(task, verbose=True)
        print(f"  Avg RLAIF score: {sum(r.score for r in result.results)/len(result.results):.1f}/10")

    print("\nAll demos complete.")


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unified Multi-Agent System")
    parser.add_argument("--task",  type=str, help="Single task to run")
    parser.add_argument("--demo",  action="store_true", help="Run all 6 agent demos")
    args = parser.parse_args()

    orchestrator = UnifiedOrchestrator()

    if args.demo:
        run_demo()
    elif args.task:
        orchestrator.run(args.task)
    else:
        # Interactive mode
        print("\nUnified Agent System — Interactive Mode")
        print("Type 'demo' to run all demos, 'quit' to exit\n")

        while True:
            try:
                task = input("Task: ").strip()
                if not task:
                    continue
                if task.lower() == "quit":
                    break
                if task.lower() == "demo":
                    run_demo()
                else:
                    orchestrator.run(task)
            except KeyboardInterrupt:
                print("\nExiting.")
                break
