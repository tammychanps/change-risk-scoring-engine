# Design Decisions

## 1. Deterministic Scoring + AI Narrative (Not Full AI Scoring)

Risk scores must be **reproducible and auditable**. In regulated environments (PCI DSS, SOX, FFIEC), a CAB reviewer needs to understand exactly why a change received a particular score. If the entire scoring were LLM-based, the same change request could produce different scores on different runs, making it impossible to defend decisions during an audit.

The architecture separates concerns: deterministic, rule-based scoring provides the defensible numbers, while AI generates the human-readable narrative that explains them. If the LLM is unavailable, the report still contains every score and recommendation — the narrative simply uses a template. This means the tool is useful from day one, even before Ollama is configured.

## 2. FAISS Over ChromaDB for Vector Search

ChromaDB requires a running server process, adds SQLite dependencies that conflict on some Windows environments, and is overkill for our dataset (~20 past changes, <10KB). FAISS operates purely in-memory, has zero infrastructure requirements, and uses the same LangChain retriever interface — so switching to ChromaDB later is a one-line change.

For a portfolio project that reviewers will clone and run locally, minimizing setup friction matters more than supporting millions of documents.

## 3. Local LLM (Ollama) Instead of Cloud API

Financial services change requests contain sensitive operational details: system names, deployment schedules, incident histories, security configurations. Sending this to a cloud API (OpenAI, Anthropic) would violate data handling policies at most banks and insurance companies.

Ollama runs entirely on the user's machine. No API keys, no network calls, no data exfiltration risk. This is a deliberate architectural choice that demonstrates awareness of data sovereignty requirements in regulated industries — exactly the kind of judgment a Technology Risk Manager or IT Program Manager should show.

## 4. Configurable YAML Weights

Different organizations have different risk appetites. A fintech startup might weight deployment speed higher than rollback readiness; a Tier 1 bank might weight security exposure at 3x everything else. Hard-coding weights would make the tool a toy. Making them configurable in a human-readable YAML file means:

- Risk committees can adjust weights without touching code
- The same engine serves different business units
- Weight changes are version-controlled and auditable
- New dimensions can be added by editing config + adding one scoring function

## 5. Go/No-Go Recommendation Format

CAB meetings follow a structured approval workflow. The output is not "here's a score, figure it out" — it is a clear **GO**, **GO (conditional)**, or **NO-GO** with specific, numbered mitigations. This mirrors how real Change Advisory Boards operate at companies like HSBC, JPMorgan, and Visa.

The numbered mitigations serve as an action checklist: each maps to a high-scoring dimension, giving the change implementer a clear path from "NO-GO" to "GO (conditional)." This reduces CAB meeting time and eliminates ambiguity about what needs to happen before re-assessment.
