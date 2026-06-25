# ruff: noqa
import os
import json
import re
import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from google.adk.agents import LlmAgent
from google.adk.workflow import Workflow, node, START, FunctionNode
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.adk.apps import App, ResumabilityConfig
from google.adk.models import Gemini
from google.genai import types
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from .config import config

# Initialize local MCP server toolsets with specific tool filters
citation_mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="uv",
            args=[
                "run",
                os.path.abspath(os.path.join(os.path.dirname(__file__), "mcp_server.py"))
            ]
        )
    ),
    tool_filter=["verify_citation", "validate_academic_format"]
)

novelty_mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="uv",
            args=[
                "run",
                os.path.abspath(os.path.join(os.path.dirname(__file__), "mcp_server.py"))
            ]
        )
    ),
    tool_filter=["search_literature", "fetch_journal_metrics"]
)

# ==============================================================================
# Pydantic Schemas for Node Inputs, Outputs, and State
# ==============================================================================

class PeerReviewInput(BaseModel):
    abstract: str = Field(description="The academic paper abstract to be reviewed.")

class CitationReview(BaseModel):
    formatted_correctly: bool = Field(description="True if references/citations are properly formatted, False otherwise.")
    citation_errors: List[str] = Field(default_factory=list, description="List of formatting or structure errors in citations.")
    detailed_feedback: str = Field(description="Detailed critique of citations and formatting.")

class NoveltyReview(BaseModel):
    novelty_score: int = Field(description="Score /5 for novelty and contribution.")
    similar_works_found: List[str] = Field(default_factory=list, description="Similar papers or topics found in literature.")
    detailed_feedback: str = Field(description="Detailed feedback regarding the originality and state-of-the-art alignment.")

class LanguageReview(BaseModel):
    clarity_score: int = Field(description="Score /5 for writing quality, grammar, and tone.")
    issues_found: List[str] = Field(default_factory=list, description="Specific language or clarity issues found.")
    detailed_feedback: str = Field(description="Detailed critique of spelling, grammar, readability, and academic tone.")

class ChairSynthesis(BaseModel):
    originality_score: int = Field(description="Score /5 for Originality")
    clarity_score: int = Field(description="Score /5 for Clarity")
    methodology_score: int = Field(description="Score /5 for Methodology")
    impact_score: int = Field(description="Score /5 for Impact")
    verdict: str = Field(description="Recommendation: Accept, Minor Revision, Major Revision, or Reject")
    meta_review: str = Field(description="Synthesis report summarizing all aspects: methodology, originality, clarity, and citations.")

class RevisionOutput(BaseModel):
    actionable_revisions: List[str] = Field(description="List of 3-5 specific revisions.")
    feedback_summary: str = Field(description="Constructive concluding remarks for the author.")

class ReviewState(BaseModel):
    original_abstract: str = ""
    scrubbed_abstract: str = ""
    structure_analysis: Dict[str, Any] = Field(default_factory=dict)
    citation_review: Dict[str, Any] = Field(default_factory=dict)
    novelty_review: Dict[str, Any] = Field(default_factory=dict)
    language_review: Dict[str, Any] = Field(default_factory=dict)
    chair_synthesis: Dict[str, Any] = Field(default_factory=dict)
    user_approved_verdict: str = ""
    user_approved_scores: Dict[str, int] = Field(default_factory=dict)
    user_comments: str = ""
    revision_results: Dict[str, Any] = Field(default_factory=dict)
    security_flagged: bool = False
    security_reason: str = ""

# ==============================================================================
# Security Checkpoint Node
# ==============================================================================

def security_checkpoint(ctx: Context, node_input: Any) -> Event:
    text = ""
    has_binary_attachment = False
    binary_parts = []
    
    if hasattr(node_input, "parts") and node_input.parts:
        for part in node_input.parts:
            if part.text:
                text += part.text
            elif part.inline_data or part.file_data:
                has_binary_attachment = True
                binary_parts.append(part)
                
        if has_binary_attachment and binary_parts:
            try:
                from google.adk.models import Gemini
                from google.genai import types
                from .config import config
                
                # Recreate parts to strip extra fields like display_name
                clean_parts = []
                for p in binary_parts:
                    if p.inline_data:
                        clean_parts.append(types.Part.from_bytes(
                            data=p.inline_data.data,
                            mime_type=p.inline_data.mime_type
                        ))
                    elif p.file_data:
                        clean_parts.append(types.Part.from_uri(
                            file_uri=p.file_data.file_uri,
                            mime_type=p.file_data.mime_type
                        ))
                
                g_model = Gemini(model=config.model)
                client = g_model.api_client
                prompt = (
                    "Extract and return only the text of the abstract from this document. "
                    "Do not include any formatting, markdown, or commentary. Just return the abstract text."
                )
                response = client.models.generate_content(
                    model=config.model,
                    contents=clean_parts + [prompt]
                )
                if response.text:
                    text = response.text.strip()
            except Exception as e:
                print(f"Error extracting text from document attachment: {e}")
    elif isinstance(node_input, dict) and "abstract" in node_input:
        text = node_input["abstract"]
    elif isinstance(node_input, str):
        text = node_input
    else:
        text = str(node_input)
    
    # 1. PII Scrubbing
    # Regexes for email and phone numbers
    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    phone_pattern = r'\+?\d{1,4}?[-.\s]?\(?\d{1,3}?\)?[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}'
    # Clean author tags like "By Dr. Jane Doe", "Authors: Jane Doe, John Smith"
    author_pattern = r'(?i)(author[s]?|by|dr\.|prof\.)\s*:\s*[A-Za-z\s,\.\-\(\)]+'
    
    scrubbed = text
    scrubbed = re.sub(email_pattern, "[REDACTED EMAIL]", scrubbed)
    scrubbed = re.sub(phone_pattern, "[REDACTED PHONE]", scrubbed)
    scrubbed = re.sub(author_pattern, "[REDACTED AUTHOR INFO] ", scrubbed)
    
    # 2. Prompt Injection Detection
    injection_keywords = [
        "ignore previous instructions",
        "ignore all instructions",
        "system prompt",
        "you are now a",
        "override instructions",
        "developer mode",
        "ignore rules"
    ]
    
    flagged = False
    reason = ""
    
    for kw in injection_keywords:
        if kw in text.lower():
            flagged = True
            reason = f"Security Violation: Potential prompt injection keyword '{kw}' detected."
            break
            
    # 3. Domain Specific Check (e.g. extremely short input or offensive content)
    if len(text.strip()) < 50:
        flagged = True
        reason = "Security Violation: The submitted abstract is too short to be evaluated (< 50 characters)."
        
    # 4. Structured JSON Audit Log
    log_severity = "INFO"
    if flagged:
        log_severity = "CRITICAL" if "injection" in reason.lower() else "WARNING"
        
    audit_log = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "event": "security_checkpoint_scan",
        "status": "FAIL" if flagged else "PASS",
        "severity": log_severity,
        "details": reason if flagged else "Abstract cleared for double-blind peer review."
    }
    
    print(json.dumps(audit_log))
    
    if flagged:
        return Event(
            output="Security scan failed. Review aborted.",
            route="SECURITY_EVENT",
            state={"security_flagged": True, "security_reason": reason}
        )
        
    return Event(
        output=scrubbed,
        route="SECURITY_PASS",
        state={"original_abstract": text, "scrubbed_abstract": scrubbed}
    )

# ==============================================================================
# Structure Analyzer Node
# ==============================================================================

def structure_analyzer(ctx: Context, node_input: str) -> Event:
    text = node_input
    
    # Look for key structural indicators in academic abstracts
    has_intro = any(x in text.lower() for x in ["introduction", "background", "motivation", "aim", "objective", "challenge"])
    has_methods = any(x in text.lower() for x in ["method", "methodology", "approach", "framework", "design", "experiment", "algorithm"])
    has_results = any(x in text.lower() for x in ["result", "finding", "show", "observe", "analysis", "outcome", "evaluation"])
    has_conclusion = any(x in text.lower() for x in ["conclusion", "conclude", "implication", "future work", "summary", "discuss"])
    
    word_count = len(text.split())
    
    missing = []
    if not has_intro: missing.append("Introduction/Background")
    if not has_methods: missing.append("Methodology/Approach")
    if not has_results: missing.append("Results/Findings")
    if not has_conclusion: missing.append("Conclusion/Implications")
    
    if missing:
        feedback = f"Abstract word count: {word_count}. Formatting issue: Missing or unclear sections for {', '.join(missing)}."
    else:
        feedback = f"Abstract word count: {word_count}. Good structure. All typical academic abstract components are present."
        
    analysis_result = {
        "word_count": word_count,
        "sections_found": {
            "Introduction": "Yes" if has_intro else "No",
            "Methodology": "Yes" if has_methods else "No",
            "Results": "Yes" if has_results else "No",
            "Conclusion": "Yes" if has_conclusion else "No"
        },
        "feedback": feedback
    }
    
    return Event(output=text, state={"structure_analysis": analysis_result})

# ==============================================================================
# Sub-Agents
# ==============================================================================

citation_verifier = LlmAgent(
    name="citation_verifier",
    model=Gemini(model=config.model),
    instruction="""You are an academic Citation Verifier.
Your task is to analyze the citation style and format of the paper abstract.
Check if citations are properly formatted (e.g., in brackets [1] or Author (Year) style).
Check for any inconsistencies in references.
Use verify_citation to check individual citation entries, and validate_academic_format to check word counts and structures.

You MUST return a JSON object matching the CitationReview schema.
If the abstract doesn't contain any citations, return:
{
  "formatted_correctly": false,
  "citation_errors": ["No citations found in the abstract."],
  "detailed_feedback": "The abstract does not contain any academic citations or references."
}
Do NOT return conversational text or plain text explanation. Output ONLY valid JSON matching the schema.""",
    tools=[citation_mcp_toolset],
    output_schema=CitationReview,
    output_key="citation_review",
)

novelty_evaluator = LlmAgent(
    name="novelty_evaluator",
    model=Gemini(model=config.model),
    instruction="""You are an academic Novelty Evaluator.
Your goal is to evaluate the originality, contribution, and state-of-the-art (SOTA) alignment of the proposed abstract.
Evaluate whether the methodology or findings represent a significant contribution to the field.
Use search_literature to find similar papers and fetch_journal_metrics to find relevant journals for the domain of research.
Provide a novelty score out of 5.

You MUST return a JSON object matching the NoveltyReview schema.
Do NOT write conversational text or plain text explanation. Output ONLY valid JSON matching the schema.""",
    tools=[novelty_mcp_toolset],
    output_schema=NoveltyReview,
    output_key="novelty_review",
)

language_critic = LlmAgent(
    name="language_critic",
    model=Gemini(model=config.model),
    instruction="""You are an academic Language Critic.
Analyze the writing quality, clarity, grammar, and academic tone of the abstract.
Identify spelling errors, passive voice issues, jargon, or clarity concerns.
Provide a clarity score out of 5.

You MUST return a JSON object matching the LanguageReview schema.
Do NOT write conversational text or plain text explanation. Output ONLY valid JSON matching the schema.""",
    output_schema=LanguageReview,
    output_key="language_review",
)

# ==============================================================================
# Synthesizer Chair (Meta-Agent)
# ==============================================================================

synthesizer_chair = LlmAgent(
    name="synthesizer_chair",
    model=Gemini(model=config.model),
    instruction="""You are the Synthesizer Chair of the Academic Peer-Review Committee.
Your role is to consolidate and synthesize all preceding evaluations of the abstract.
Analyze the:
- Structure Analysis feedback
- Citation Verifier feedback
- Novelty Evaluator feedback
- Language Critic feedback

You must output:
1. Originality score (1-5)
2. Clarity score (1-5)
3. Methodology score (1-5)
4. Impact score (1-5)
5. Recommendation Verdict: Accept, Minor Revision, Major Revision, or Reject
6. Meta Review: A unified, formal synthesis paragraph explaining the overall decision and main strengths/weaknesses.

You MUST return a JSON object matching the ChairSynthesis schema.
Do NOT write conversational text or plain text explanation. Output ONLY valid JSON matching the schema.""",
    output_schema=ChairSynthesis,
    output_key="chair_synthesis",
)

# ==============================================================================
# Human-in-the-Loop Approval Node
# ==============================================================================

async def human_approval(ctx: Context, node_input: dict) -> Event:
    chair_data = ChairSynthesis(**node_input)
    
    if not ctx.resume_inputs:
        yield RequestInput(
            interrupt_id="verdict_approval",
            message=(
                f"### Academic Committee Recommendation Review\n"
                f"* **Synthesized Verdict**: **{chair_data.verdict}**\n"
                f"* **Committee Scores**:\n"
                f"  - Originality: {chair_data.originality_score}/5\n"
                f"  - Clarity: {chair_data.clarity_score}/5\n"
                f"  - Methodology: {chair_data.methodology_score}/5\n"
                f"  - Impact: {chair_data.impact_score}/5\n\n"
                f"Please reply with 'Approve' to proceed with the recommendation, or write an override "
                f"(e.g., 'Override: Verdict=Minor Revision, Clarity=4')."
            )
        )
        return
        
    user_reply = ctx.resume_inputs.get("verdict_approval", "").strip()
    
    final_verdict = chair_data.verdict
    final_scores = {
        "Originality": chair_data.originality_score,
        "Clarity": chair_data.clarity_score,
        "Methodology": chair_data.methodology_score,
        "Impact": chair_data.impact_score
    }
    
    # Parse simple overrides (e.g. "Override: Verdict=Minor Revision, Clarity=4")
    if "override" in user_reply.lower():
        parts = user_reply.split(",")
        for part in parts:
            if "=" in part:
                k, v = part.split("=")
                k = k.replace("Override:", "").strip().lower()
                v = v.strip()
                if k == "verdict":
                    final_verdict = v
                elif k == "clarity":
                    final_scores["Clarity"] = int(v)
                elif k == "originality":
                    final_scores["Originality"] = int(v)
                elif k == "methodology":
                    final_scores["Methodology"] = int(v)
                elif k == "impact":
                    final_scores["Impact"] = int(v)
                    
    yield Event(
        output={"verdict": final_verdict, "scores": final_scores},
        state={
            "user_approved_verdict": final_verdict,
            "user_approved_scores": final_scores,
            "user_comments": user_reply
        }
    )

# ==============================================================================
# Revision Assistant
# ==============================================================================

revision_assistant = LlmAgent(
    name="revision_assistant",
    model=Gemini(model=config.model),
    instruction="""You are an academic Revision Assistant.
Based on the finalized peer-review verdict and evaluation scores, formulate constructive, specific feedback and actionable revision suggestions.
Read the review details and comments from state:
- Structure analysis: {state[structure_analysis]}
- Citation review: {state[citation_review]}
- Novelty review: {state[novelty_review]}
- Language review: {state[language_review]}
- Final Approved Verdict: {state[user_approved_verdict]}
- Final Approved Scores: {state[user_approved_scores]}
- User/Chair Comments: {state[user_comments]}

You MUST return a JSON object matching the RevisionOutput schema.
Do NOT write conversational text or plain text explanation. Output ONLY valid JSON matching the schema.""",
    output_schema=RevisionOutput,
    output_key="revision_results",
)

# ==============================================================================
# Final Output Node
# ==============================================================================

def final_output(ctx: Context, node_input: Any) -> Event:
    state = ctx.state
    
    if state.get("security_flagged"):
        report = f"### ❌ SECURITY CHECKPOINT FAILURE\n\n{state.get('security_reason')}"
        return Event(
            content=types.Content(role='model', parts=[types.Part.from_text(text=report)]),
            output=report
        )
        
    scores = state.get("user_approved_scores", {})
    verdict = state.get("user_approved_verdict", "N/A")
    comments = state.get("user_comments", "N/A")
    
    revisions_data = state.get("revision_results", {})
    revisions = revisions_data.get("actionable_revisions", [])
    summary = revisions_data.get("feedback_summary", "")
    
    struct = state.get("structure_analysis", {})
    struct_feedback = struct.get("feedback", "N/A")
    
    cit = state.get("citation_review", {})
    cit_feedback = cit.get("detailed_feedback", "N/A")
    
    nov = state.get("novelty_review", {})
    nov_feedback = nov.get("detailed_feedback", "N/A")
    
    lang = state.get("language_review", {})
    lang_feedback = lang.get("detailed_feedback", "N/A")
    
    report = (
        f"# 🎓 Academic Peer Review Report\n\n"
        f"## 📊 Committee Evaluation Scores\n"
        f"| Evaluation Metric | Score (out of 5) |\n"
        f"| :--- | :---: |\n"
        f"| **Originality** | {scores.get('Originality', 'N/A')}/5 |\n"
        f"| **Clarity** | {scores.get('Clarity', 'N/A')}/5 |\n"
        f"| **Methodology** | {scores.get('Methodology', 'N/A')}/5 |\n"
        f"| **Impact** | {scores.get('Impact', 'N/A')}/5 |\n\n"
        f"### Final Recommendation Verdict: **{verdict}**\n\n"
        f"---\n\n"
        f"## 🔍 Detailed Sub-Committee Reviews\n\n"
        f"### 📋 Structure Analysis\n"
        f"{struct_feedback}\n\n"
        f"### 🔗 Citations & Formatting\n"
        f"{cit_feedback}\n\n"
        f"### 💡 Novelty & Contribution\n"
        f"{nov_feedback}\n\n"
        f"### ✍️ Language, Tone & Readability\n"
        f"{lang_feedback}\n\n"
        f"---\n\n"
        f"## 🛠️ Actionable Revisions Required\n"
    )
    for r in revisions:
        report += f"* {r}\n"
        
    report += f"\n### 💬 Concluding Remarks\n{summary}\n\n"
    report += f"*(Review Chair Notes: {comments})*"
    
    return Event(
        content=types.Content(role='model', parts=[types.Part.from_text(text=report)]),
        output=report
    )

# ==============================================================================
# Workflow Construction
# ==============================================================================

peer_review_workflow = Workflow(
    name="peer_review_workflow",
    state_schema=ReviewState,
    edges=[
        (START, security_checkpoint),
        (security_checkpoint, {"SECURITY_PASS": structure_analyzer, "SECURITY_EVENT": final_output}),
        (structure_analyzer, citation_verifier),
        (citation_verifier, novelty_evaluator),
        (novelty_evaluator, language_critic),
        (language_critic, synthesizer_chair),
        (synthesizer_chair, human_approval),
        (human_approval, revision_assistant),
        (revision_assistant, final_output)
    ]
)

# App Container
app = App(
    root_agent=peer_review_workflow,
    name="app",
    resumability_config=ResumabilityConfig(enabled=True)
)

root_agent = peer_review_workflow

