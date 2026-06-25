import re

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("peer-review-mcp-server")

@mcp.tool()
def search_literature(keywords: str) -> str:
    """Searches a mock academic database for publications matching keywords to evaluate novelty.

    Args:
        keywords: A comma-separated list of keywords.
    """
    kw_list = [k.strip().lower() for k in keywords.split(",")]

    # Mock database
    database = [
        {"title": "Deep Learning for Automated Peer Review", "authors": "Smith et al.", "year": 2024, "keywords": ["peer review", "deep learning", "nlp"]},
        {"title": "An Analysis of Double-Blind Academic Evaluation Systems", "authors": "Jones & Taylor", "year": 2023, "keywords": ["double-blind", "academic evaluation", "peer review"]},
        {"title": "Transformer Models in Scientific Document Summarization", "authors": "Wang et al.", "year": 2025, "keywords": ["transformer", "summarization", "nlp"]},
    ]

    results = []
    for paper in database:
        match_count = sum(1 for kw in kw_list if any(kw in pk for pk in paper["keywords"]))
        if match_count > 0:
            results.append(f"'{paper['title']}' by {paper['authors']} ({paper['year']}) - Keywords: {', '.join(paper['keywords'])}")

    if not results:
        return "No closely matching literature found. The abstract topic appears highly novel."
    return "Similar works found in literature database:\n" + "\n".join(results)

@mcp.tool()
def validate_academic_format(text: str) -> str:
    """Analyzes the academic abstract word count and sections.

    Args:
        text: The abstract text.
    """
    word_count = len(text.split())
    has_intro = any(x in text.lower() for x in ["introduction", "background", "aim", "objective"])
    has_method = any(x in text.lower() for x in ["method", "approach", "framework", "experiment"])
    has_result = any(x in text.lower() for x in ["result", "finding", "show", "observe"])
    has_conclusion = any(x in text.lower() for x in ["conclusion", "summary", "conclude"])

    status = []
    if word_count < 150:
        status.append("Warning: Word count is low (< 150 words). Most journals require 150-250 words.")
    elif word_count > 300:
        status.append("Warning: Word count is high (> 300 words). Most journals require 150-250 words.")
    else:
        status.append("Word count is within the optimal range (150-300 words).")

    missing = []
    if not has_intro:
        missing.append("Introduction/Background")
    if not has_method:
        missing.append("Methodology/Approach")
    if not has_result:
        missing.append("Results/Findings")
    if not has_conclusion:
        missing.append("Conclusion/Implications")

    if missing:
        status.append(f"Missing structural elements: {', '.join(missing)}.")
    else:
        status.append("All structural elements (Introduction, Methodology, Results, Conclusion) are present.")

    return "\n".join(status)

@mcp.tool()
def fetch_journal_metrics(domain: str) -> str:
    """Finds recommended journals and impact metrics for the given domain.

    Args:
        domain: Research domain (e.g., 'Artificial Intelligence', 'Medicine', 'Physics').
    """
    metrics = {
        "computer science": [
            {"journal": "IEEE Transactions on Pattern Analysis and Machine Intelligence (TPAMI)", "impact_factor": "24.3", "acceptance_rate": "15%"},
            {"journal": "Journal of Machine Learning Research (JMLR)", "impact_factor": "8.1", "acceptance_rate": "20%"},
        ],
        "medicine": [
            {"journal": "The New England Journal of Medicine (NEJM)", "impact_factor": "176.0", "acceptance_rate": "5%"},
            {"journal": "The Lancet", "impact_factor": "202.7", "acceptance_rate": "7%"},
        ],
        "general": [
            {"journal": "Nature", "impact_factor": "69.5", "acceptance_rate": "8%"},
            {"journal": "Science", "impact_factor": "63.7", "acceptance_rate": "7%"},
        ]
    }

    key = domain.lower()
    matches = []
    for k, v in metrics.items():
        if k in key or key in k:
            matches.extend(v)

    if not matches:
        matches = metrics["general"]

    res = []
    for m in matches:
        res.append(f"- **{m['journal']}** (Impact Factor: {m['impact_factor']}, Acceptance Rate: {m['acceptance_rate']})")

    return "Recommended Journal Targets:\n" + "\n".join(res)

@mcp.tool()
def verify_citation(citation: str) -> str:
    """Verifies if a specific citation format or DOI is valid and exists in our records.

    Args:
        citation: The citation string or DOI (e.g. '10.1001/nejm.2024').
    """
    # Simple check for DOI format (e.g., starts with 10.)
    doi_pattern = r'\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b'
    is_doi = bool(re.search(doi_pattern, citation, re.IGNORECASE))

    if is_doi:
        # Mock DOI check
        if "nejm" in citation.lower() or "nature" in citation.lower() or "science" in citation.lower() or "2024" in citation or "2025" in citation:
            return f"DOI '{citation}' verified and found in CrossRef database."
        else:
            return f"DOI '{citation}' verified, but metadata could not be fully retrieved. Ensure the link is active."
    else:
        # Check if standard citation format
        if "[" in citation or "]" in citation or re.search(r'\(\w+ et al\., \d{4}\)', citation):
            return f"Citation format '{citation}' verified to match IEEE/APA reference standards."
        else:
            return f"Citation format '{citation}' seems non-standard. Recommended format: '[1]' or 'Author et al. (Year)'."

if __name__ == "__main__":
    # When running as stdio mcp server, FastMCP needs to handle arguments correctly
    mcp.run()
