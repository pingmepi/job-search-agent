"""Build profile/skill_index.json from resumes, profile, and synonym seed.

Usage:
    python main.py build-skill-index          # Text-only extraction
    python main.py build-skill-index --llm    # LLM-enriched extraction

The skill index supplements text-based resume matching with:
- Pre-extracted skills per resume (so matching isn't limited to substring search)
- Synonym mappings (SDLC ↔ software development lifecycle, etc.)
- Profile-aware skills (allowed_tools mapped to relevant resumes)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from core.config import get_settings

# ── Synonym seed ─────────────────────────────────────────────────
# Common abbreviations/acronyms and their expanded forms.
# Both directions are useful: "sdlc" → ["software development lifecycle"]
# and the index lookup handles bidirectional containment.

SYNONYM_SEED: dict[str, list[str]] = {
    "sdlc": ["software development lifecycle", "development lifecycle"],
    "ci/cd": ["continuous integration", "continuous deployment", "cicd"],
    "ci": ["continuous integration"],
    "cd": ["continuous deployment"],
    "llm": ["large language model"],
    "llms": ["large language models", "llm", "language models"],
    "ai": ["artificial intelligence"],
    "ml": ["machine learning"],
    "ai/ml": ["artificial intelligence", "machine learning", "ai", "ml"],
    "nlp": ["natural language processing"],
    "rlhf": ["reinforcement learning from human feedback"],
    "crm": ["customer relationship management"],
    "cms": ["content management system"],
    "gtm": ["go to market"],
    "prd": ["product requirements document"],
    "prds": ["product requirements documents", "product requirements"],
    "ux": ["user experience"],
    "ui": ["user interface"],
    "seo": ["search engine optimization"],
    "ga4": ["google analytics 4", "google analytics"],
    "cli": ["command line interface", "command line"],
    "api": ["application programming interface"],
    "apis": ["application programming interfaces", "api"],
    "saas": ["software as a service"],
    "sql": ["structured query language"],
    "etl": ["extract transform load"],
    "kpi": ["key performance indicator"],
    "kpis": ["key performance indicators"],
    "okr": ["objectives and key results"],
    "okrs": ["objectives and key results"],
    "csat": ["customer satisfaction"],
    "nps": ["net promoter score"],
    "rag": ["retrieval augmented generation"],
    "sdk": ["software development kit"],
    "postgres": ["postgresql"],
    "postgresql": ["postgres"],
    "react.js": ["react", "reactjs"],
    "node.js": ["node", "nodejs"],
    "fastapi": ["fast api"],
    "bigquery": ["big query"],
    "langchain": ["lang chain"],
    "openai": ["open ai"],
    "a/b testing": ["ab testing", "split testing", "experimentation"],
    "ab testing": ["a/b testing", "split testing"],
}


def _normalize(text: str) -> str:
    return re.sub(r"[-_]", " ", text.lower().strip())


def _extract_skills_from_tex(tex_content: str) -> list[str]:
    """Extract skills from a LaTeX resume using text parsing.

    Looks at:
    - Skills section entries
    - Technologies/tools mentioned in bullet points
    - Section headers for domain signals
    """
    text = _normalize(tex_content)
    skills: set[str] = set()

    # Extract from Skills section (lines after \section*{Skills})
    in_skills = False
    for line in tex_content.splitlines():
        if re.search(r"\\section\*\{.*[Ss]kills", line):
            in_skills = True
            continue
        if in_skills and re.search(r"\\section\*\{", line):
            break
        if in_skills:
            # Extract items between colons and line breaks
            # e.g., "Product Management: Roadmap ownership, PRDs, ..."
            parts = re.split(r"[,;\\\\]", line)
            for part in parts:
                cleaned = re.sub(r"\\textbf\{([^}]*)\}", r"\1", part)
                cleaned = re.sub(r"[{}\\]", "", cleaned).strip(" .\t\n")
                cleaned = cleaned.strip()
                if cleaned and len(cleaned) > 1 and len(cleaned) < 60:
                    skills.add(_normalize(cleaned))

    # Extract tool/tech mentions from bullet items
    tool_patterns = [
        r"\b(Python|SQL|Tableau|Mixpanel|Amplitude|Jira|Linear|Figma)\b",
        r"\b(BigQuery|HubSpot|Netcore|CleverTap|WebEngage|Metabase)\b",
        r"\b(AWS|GCP|Docker|FastAPI|PostgreSQL|LangChain|Railway)\b",
        r"\b(GA4|Google Tag Manager|Google Analytics|Splunk|Datadog)\b",
        r"\b(n8n|dbt|Postman|Swagger|Confluence|GitHub|LaTeX)\b",
        r"\b(OpenAI|Anthropic|Claude|Cursor|Codex|OpenRouter)\b",
        r"\b(Typeform|Qualtrics|SurveyMonkey)\b",
    ]
    for pattern in tool_patterns:
        for match in re.finditer(pattern, tex_content, re.IGNORECASE):
            skills.add(_normalize(match.group(0)))

    return sorted(skills)


def _map_profile_tools_to_resumes(
    allowed_tools: list[str],
    resume_contents: dict[str, str],
    resume_skills: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Add profile allowed_tools to resumes that mention them."""
    for tool in allowed_tools:
        tool_lower = _normalize(tool)
        for resume_name, content in resume_contents.items():
            content_lower = _normalize(content)
            if tool_lower in content_lower or any(
                tool_lower in s or s in tool_lower
                for s in resume_skills.get(resume_name, [])
                if len(s) > 2
            ):
                if tool_lower not in resume_skills.get(resume_name, []):
                    resume_skills.setdefault(resume_name, []).append(tool_lower)
    return resume_skills


def build_skill_index(use_llm: bool = False) -> None:
    """Build and write the skill index JSON."""
    settings = get_settings()
    resumes_dir = settings.resumes_dir
    profile_path = settings.profile_path
    output_path = settings.skill_index_path

    # Load profile
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    allowed_tools = profile.get("allowed_tools", [])

    # Extract skills from each resume
    resume_contents: dict[str, str] = {}
    resume_skills: dict[str, list[str]] = {}

    for tex_file in sorted(resumes_dir.glob("master_*.tex")):
        content = tex_file.read_text(encoding="utf-8")
        resume_contents[tex_file.name] = content

        if use_llm:
            skills = _extract_skills_llm(content, tex_file.name)
        else:
            skills = _extract_skills_from_tex(content)

        resume_skills[tex_file.name] = skills
        print(f"  {tex_file.name}: {len(skills)} skills extracted")

    # Enrich with profile tools
    resume_skills = _map_profile_tools_to_resumes(
        allowed_tools, resume_contents, resume_skills
    )

    # Deduplicate and sort
    for name in resume_skills:
        resume_skills[name] = sorted(set(resume_skills[name]))

    index = {
        "version": 1,
        "synonyms": SYNONYM_SEED,
        "resumes": resume_skills,
    }

    # Atomic write
    tmp_path = output_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(output_path)

    total_skills = sum(len(v) for v in resume_skills.values())
    print(f"\nSkill index written to {output_path}")
    print(f"  {len(resume_skills)} resumes, {total_skills} total skill entries")
    print(f"  {len(SYNONYM_SEED)} synonym mappings")


def _extract_skills_llm(tex_content: str, resume_name: str) -> list[str]:
    """Use LLM to extract skills from a resume. Requires OPENROUTER_API_KEY."""
    from core.llm import chat_text

    system = (
        "Extract every discrete skill, tool, technology, methodology, and domain "
        "competency from this resume. Include both explicit mentions (e.g., 'SQL') "
        "and implicit ones (e.g., if the resume mentions 'A/B testing framework' "
        "extract 'a/b testing' and 'experimentation'). Return a JSON array of "
        "lowercase strings. 25-50 items typical. Return ONLY the JSON array."
    )
    response = chat_text(system, tex_content, json_mode=True)
    try:
        skills = json.loads(response.text)
        if isinstance(skills, list):
            return [_normalize(s) for s in skills if isinstance(s, str)]
    except json.JSONDecodeError:
        print(f"  Warning: LLM returned invalid JSON for {resume_name}, falling back to text extraction")
    return _extract_skills_from_tex(tex_content)


if __name__ == "__main__":
    use_llm = "--llm" in sys.argv
    build_skill_index(use_llm=use_llm)
