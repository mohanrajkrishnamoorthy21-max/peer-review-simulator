# Submission Write-Up: Academic Peer Review Simulator

## 📋 Problem Statement
The academic peer-review process is a fundamental pillar of scientific advancement. However, it suffers from several critical bottlenecks and challenges:
1. **Human Bias and Single-Point Failures**: Double-blind review integrity is easily compromised if author details (PII) are accidentally left in abstracts.
2. **Reviewer Fatigue**: Evaluating papers for basic formatting, structural components, citation formatting, and preliminary literature cross-checking takes valuable time away from assessing deep technical merits.
3. **Consistency & Originality Verification**: Checking for state-of-the-art (SOTA) alignment and cross-referencing databases is tedious and error-prone.

The **Academic Peer Review Simulator** solves these issues by automating the initial triage, structural validation, citation validation, novelty assessment, and language review using a secure, multi-agent network, under the ultimate oversight of a human reviewer (Review Chair).

---

## 🗺️ Solution Architecture

The system uses a sequential ADK workflow graph with specialized agents, an MCP toolset, and structured human-in-the-loop validation:

```mermaid
graph TD
    START --> SC[Security Checkpoint Node]
    SC -- SECURITY_PASS --> SA[Structure Analyzer Node]
    SC -- SECURITY_EVENT --> FO[Final Output Node]
    SA --> CV[Citation Verifier Agent]
    CV --> NE[Novelty Evaluator Agent]
    NE --> LC[Language Critic Agent]
    LC --> SC2[Synthesizer Chair Agent]
    SC2 --> HA[Human Approval Node]
    HA --> RA[Revision Assistant Agent]
    RA --> FO

    subgraph MCP Server Tools
        CV -. Uses .-> V_CIT[verify_citation]
        CV -. Uses .-> V_AC[validate_academic_format]
        NE -. Uses .-> S_LIT[search_literature]
        NE -. Uses .-> F_JM[fetch_journal_metrics]
    end

    subgraph Human-in-the-Loop (HITL)
        HA
    end
```

---

## 💡 Concepts Used

The application is built using the Google Agent Development Kit (ADK) 2.0 and Model Context Protocol (MCP):

1. **ADK Workflow**: The review pipeline is orchestrated as a state-based DAG in [app/agent.py](file:///c:/Users/HP/Downloads/capstone_project/peer-review-simulator/app/agent.py#L445-L459) containing functional nodes and LLM agents.
2. **LlmAgent**: Four distinct specialized agents are defined:
   - `citation_verifier` ([app/agent.py:L221](file:///c:/Users/HP/Downloads/capstone_project/peer-review-simulator/app/agent.py#L221))
   - `novelty_evaluator` ([app/agent.py:L236](file:///c:/Users/HP/Downloads/capstone_project/peer-review-simulator/app/agent.py#L236))
   - `language_critic` ([app/agent.py:L249](file:///c:/Users/HP/Downloads/capstone_project/peer-review-simulator/app/agent.py#L249))
   - `synthesizer_chair` ([app/agent.py:L264](file:///c:/Users/HP/Downloads/capstone_project/peer-review-simulator/app/agent.py#L264))
   - `revision_assistant` ([app/agent.py:L354](file:///c:/Users/HP/Downloads/capstone_project/peer-review-simulator/app/agent.py#L354))
3. **McpToolset**: Integrates a custom FastMCP server ([app/mcp_server.py](file:///c:/Users/HP/Downloads/capstone_project/peer-review-simulator/app/mcp_server.py)) with stdio transport, filtering specific tool groups for the verifier and evaluator agents ([app/agent.py:L24-L49](file:///c:/Users/HP/Downloads/capstone_project/peer-review-simulator/app/agent.py#L24-L49)).
4. **Security Checkpoint Node**: Implement a robust functional node `security_checkpoint` ([app/agent.py:L103](file:///c:/Users/HP/Downloads/capstone_project/peer-review-simulator/app/agent.py#L103)) scanning inputs before any LLM invocations occur.
5. **Agents CLI**: Project scaffolded and managed using `agents-cli`, which compiles metadata and coordinates deployments.

---

## 🔒 Security Design

Security is critical to keep the double-blind review process unbiased and protect the model prompts:
* **PII Redaction**: Regular expressions target and replace emails, phone numbers, and common author tags (e.g. `By Dr. Jane Doe` to `[REDACTED AUTHOR INFO]`) dynamically.
* **Prompt Injection Defense**: Scans input text against a blacklist of instructions (e.g., `ignore previous instructions`, `you are now a`) to prevent malicious prompt overrides.
* **Domain-Specific Constraints**: Restricts the review process to reasonable inputs by validating length (aborts on text shorter than 50 characters).
* **Audit Logging**: Emits JSON-formatted logs containing metadata of every security check (severity, pass/fail status, timestamp) to stdout for tracking.
* **Conditional Routing**: Aborted requests bypass the agents completely and route directly to `final_output` via `SECURITY_EVENT`.

---

## 🔌 MCP Server Design

The custom FastMCP server ([app/mcp_server.py](file:///c:/Users/HP/Downloads/capstone_project/peer-review-simulator/app/mcp_server.py)) implements 4 core tools:
1. `validate_academic_format(text: str)`: Analyzes word count and checks for structural markers (Intro, Method, Results, Conclusion).
2. `search_literature(keywords: str)`: Searches a mock paper database for overlapping topics to find pre-existing papers.
3. `fetch_journal_metrics(domain: str)`: Suggests targeted journals and provides metrics (Impact Factor, Acceptance Rate) matching the domain of study.
4. `verify_citation(citation: str)`: Validates formatting or DOI against patterns and checks CrossRef mock registries.

---

## ✋ Human-in-the-Loop (HITL) Flow

A key component of the ADK 2.0 framework is its support for state resumability and human interaction. In [app/agent.py](file:///c:/Users/HP/Downloads/capstone_project/peer-review-simulator/app/agent.py#L292-L348), the `human_approval` node uses `yield RequestInput(...)` to pause review execution.
* **Why it matters**: Automating scores is useful, but the Synthesizer Chair's recommendations must be reviewed and signed off on by a human.
* **Resumability**: The UI displays a form showing the chair's verdict and scores. The user can type `Approve` or type overrides such as `Override: Verdict=Accept, Clarity=5`, which are dynamically parsed and used to update the state before the `revision_assistant` finishes.

---

## 🧪 Demo Walkthrough

The project supports three test scenarios (as detailed in the `README.md`):
1. **Happy Path (Standard Abstract)**: Abstract enters -> security clears -> structure analyzed -> agents evaluate (using MCP tools) -> chair synthesizes -> HITL prompt triggers -> user inputs "Approve" -> revisions generated -> final report shown.
2. **Short Abstract Event**: Abstract enters -> security scans -> length is < 50 characters -> routed to `SECURITY_EVENT` -> outputs "Security scan failed" with detail -> exits immediately.
3. **Prompt Injection Event**: Abstract enters -> security scans -> keyword "ignore previous instructions" matches -> routed to `SECURITY_EVENT` -> outputs "Security scan failed" with injection details -> exits immediately.

---

## 📈 Impact / Value Statement
The **Academic Peer Review Simulator** significantly reduces the administrative overhead of journal editors and reviewers. By filtering poorly formatted papers, protecting double-blind integrity, and compiling primary reports, it allows reviewers to spend their limited time assessing deep methodological and intellectual contributions, accelerating the scientific publishing lifecycle securely.
