# RiskGuard AI

**Risk, Fraud & Regulatory Intelligence Copilot**

Built for the Snowflake CoCo CLI Hackathon 2026 — Track 1: Risk, Fraud and Regulatory Intelligence Copilot.

## Problem Statement

Risk and compliance teams at financial institutions face a fragmented workflow: transaction monitoring systems generate alerts, but investigating those alerts requires manually querying databases, cross-referencing customer profiles, looking up regulatory guidance, and writing narrative reports. Each investigation can take hours of analyst time, and the growing volume of alerts leads to backlogs and missed signals.

## Solution

RiskGuard AI is an AI-native application deployed entirely on Snowflake that unifies these workflows into a single interface. It combines structured data analytics (Cortex Analyst), regulatory document retrieval (Cortex Search), and natural-language reasoning (Cortex Agent) so that compliance analysts can investigate alerts, understand regulations, and generate audit-ready reports through conversation.

The application enables analysts to:

- Triage fraud alerts from a real-time dashboard
- Investigate high-risk customers with full transaction histories and AI-generated risk explanations
- Ask natural-language questions over both transactional data and regulatory documents
- Generate SAR (Suspicious Activity Report) narratives grounded in actual transaction evidence and regulatory citations
- Maintain a complete audit trail of all AI-assisted interactions

## Architecture

```
+-----------------------------------------------------------+
|                Streamlit-in-Snowflake                      |
|  [Dashboard] [Investigation] [Ask RiskGuard] [Audit]      |
|                         |                                  |
|              Cortex Agent (Orchestrator)                   |
|              RISKGUARD_DB.APP.RISKGUARD_AGENT              |
|                    /              \                        |
|       Cortex Analyst          Cortex Search                |
|       (Semantic View)         (RAG Service)                |
|            |                       |                       |
|   CORE + ANALYTICS tables    RAG.REGULATORY_DOCS           |
|   (structured data)         (200 regulatory chunks)        |
+-----------------------------------------------------------+
```

The Cortex Agent acts as the orchestration layer. When a user asks a question, the agent determines which tool to invoke:

- **RiskAnalytics** (Cortex Analyst via Semantic View) — for any question that requires querying structured data: customer profiles, transaction histories, alert counts, risk scores, investigation status
- **RegulatorySearch** (Cortex Search) — for questions about BSA/AML regulations, FATF recommendations, OFAC sanctions, CDD/EDD requirements, SAR filing procedures

For questions that require both data and regulatory context (such as generating a SAR narrative), the agent invokes both tools and synthesizes the results.

## Snowflake Components

### Database: `RISKGUARD_DB`

| Schema | Purpose |
|---|---|
| `CORE` | Transactional data — customers, accounts, transactions, watchlist entries |
| `ANALYTICS` | Derived data — risk scores, fraud alerts, alert rules, investigations, SAR reports |
| `RAG` | Regulatory documents chunked for retrieval-augmented generation |
| `APP` | Application objects — semantic view, agent, Streamlit app, audit log |

### Cortex AI Objects

| Object | Type | Location | Role |
|---|---|---|---|
| `RISKGUARD_SEMANTIC_VIEW` | Semantic View | `APP` schema | Defines 9 logical tables, 10 relationships, 31 dimensions, 5 facts, and 12 metrics over the CORE and ANALYTICS tables. Enables Cortex Analyst to convert natural-language questions into SQL. |
| `REGULATORY_SEARCH_SERVICE` | Cortex Search Service | `RAG` schema | Indexes 200 regulatory document chunks across 5 categories (BSA_AML, CDD, EDD, FATF, SANCTIONS) with filterable attributes for category, source document, and section title. |
| `RISKGUARD_AGENT` | Cortex Agent | `APP` schema | Orchestrates between the Analyst and Search tools. Configured with domain-specific instructions for risk/compliance terminology and evidence-based responses. |
| `RISKGUARD_APP` | Streamlit App | `APP` schema | Four-tab user interface deployed as Streamlit-in-Snowflake. |

## Key Capabilities

### 1. Risk Dashboard
Four KPI cards (open alerts, active investigations, average risk score, SARs filed), alert distribution charts by severity and type, and a ranked table of the highest-risk customers.

### 2. Investigation Panel
Select any customer to view their full profile (risk score, PEP/sanctions flags, KYC status, industry, country), associated fraud alerts with rule details, and recent transaction history. Two AI-powered buttons:
- **Explain Risk Factors** — the agent queries the customer's data and generates a narrative explanation of why they were flagged
- **Draft SAR Narrative** — the agent combines transaction evidence with regulatory requirements to produce a filing-ready SAR narrative

### 3. Ask RiskGuard (Natural Language Interface)
Free-text input that routes to the Cortex Agent. The agent decides whether to query structured data, search regulatory documents, or both. Returns natural-language answers with supporting data tables when applicable.

### 4. Audit & Reports
Every AI interaction (queries, risk explanations, SAR generations) is logged to `APP.AUDIT_LOG` with timestamp, user, action type, input, output, and related customer/alert IDs. The tab also displays the investigation case queue and SAR filing status.

## Synthetic Dataset

All data is generated synthetically using Snowflake SQL functions (`UNIFORM`, `RANDOM`, `GENERATOR`, `DATEADD`). No real customer or financial data is used.

| Table | Rows | Details |
|---|---|---|
| `CORE.CUSTOMERS` | 500 | Mix of risk profiles: LOW, MEDIUM, HIGH, CRITICAL. ~10% PEP-flagged, ~4% sanctions-flagged. Countries span US, UK, Germany, Japan, Brazil, plus high-risk jurisdictions (Iran, Syria, North Korea, etc.). |
| `CORE.ACCOUNTS` | 855 | 1-3 accounts per customer (CHECKING, SAVINGS, WIRE, INVESTMENT). |
| `CORE.TRANSACTIONS` | 50,045 | 90 days of activity. Includes 372 embedded fraud-pattern transactions across 5 typologies. |
| `CORE.WATCHLIST_ENTRIES` | 100 | 25 fuzzy-matched to real customers, 75 unmatched entries across OFAC, UN, EU, PEP, and INTERPOL lists. |
| `ANALYTICS.ALERT_RULES` | 15 | Detection rules covering structuring, velocity, jurisdiction, dormant account, watchlist, and round-trip patterns. |
| `ANALYTICS.RISK_SCORES` | 500 | One per customer, computed from behavior (PEP flag, sanctions flag, watchlist matches, suspicious transaction count, high-risk country). |
| `ANALYTICS.FRAUD_ALERTS` | 179 | Generated from rule triggers against the embedded fraud patterns. Statuses: OPEN, INVESTIGATING, ESCALATED, CLOSED. |
| `ANALYTICS.INVESTIGATIONS` | 50 | Escalated from alerts. 10 closed with SAR filed, 10 closed no action, 30 active. |
| `ANALYTICS.SAR_REPORTS` | 10 | Full narratives covering structuring, round-tripping, sanctions, velocity, dormant abuse, watchlist, PEP, trade-based ML, and layering. |
| `RAG.REGULATORY_DOCS` | 200 | Chunked regulatory text: BSA/AML (84), CDD (38), EDD (20), FATF (21), Sanctions (37). Sources include FinCEN BSA/AML Manual, FATF Recommendations, OFAC Compliance Framework. |

### Embedded Fraud Patterns

| Pattern | Description | Transactions |
|---|---|---|
| Structuring | Multiple cash deposits just under $10,000 CTR threshold within 48 hours | 22 |
| Round-tripping | Wire out to Entity A, near-equal wire back from Entity B in same jurisdiction | 8 |
| Velocity spike | 10x normal transaction volume in a 7-day window | 250 |
| High-risk corridor | Wire transfers to/from Iran, Syria, North Korea, Venezuela | 80 |
| Dormant activation | Accounts inactive 6+ months suddenly processing large wires | 12 |

### Demo Customer: C-0042

The primary demo subject is customer **C-0042 (Yuki Oliveira)**: HIGH risk rating, PEP-flagged, sanctions-flagged, Jewelry & Precious Metals industry, risk score 100/100. Has 7 structuring deposits totaling $68,300 and round-trip wires to the UAE. 7 fraud alerts triggered across multiple rule categories.

## Demo Workflow

**"The Case of Customer C-0042"**

1. **Dashboard** — Open the app, review KPI cards and alert charts. Note C-0042 at the top of the high-risk customer list.
2. **Investigation Panel** — Select C-0042. Review the customer profile (PEP, sanctions, Jewelry industry), 7 fraud alerts, and transaction history showing structuring deposits and round-trip wires.
3. **Explain Risk** — Click "Explain Risk Factors". The agent queries C-0042's data and returns a narrative citing specific transaction IDs, amounts, and patterns.
4. **Regulatory Lookup** — Switch to "Ask RiskGuard" and ask: "What are the BSA reporting requirements for structuring?" The agent retrieves FinCEN guidance with CTR thresholds and SAR filing deadlines.
5. **Generate SAR** — Back in Investigation Panel, click "Draft SAR Narrative". The agent combines transaction evidence with regulatory context to produce a complete filing narrative.
6. **Audit Trail** — Switch to "Audit & Reports" to see all AI interactions logged with timestamps and action types.

## Tech Stack

| Layer | Technology |
|---|---|
| Database | Snowflake (RISKGUARD_DB) |
| AI Orchestration | Snowflake Cortex Agent |
| Structured Data AI | Snowflake Cortex Analyst + Semantic View |
| Document Retrieval | Snowflake Cortex Search Service |
| LLM | Auto-selected by Cortex (claude-opus-4-8 for orchestration during testing) |
| Embeddings | snowflake-arctic-embed-m-v1.5 (Cortex Search default) |
| Frontend | Streamlit-in-Snowflake |
| Data Generation | Snowflake SQL (GENERATOR, UNIFORM, RANDOM) |

All components run natively within Snowflake. No external APIs, services, or infrastructure are required.

## Project Structure

```
riskguard-ai/
  streamlit_app.py     # Streamlit-in-Snowflake app (4 tabs, 306 lines)
  snowflake.yml        # Deployment manifest for snow streamlit deploy
  README.md            # This file
```

The Snowflake objects (database, tables, semantic view, search service, agent, Streamlit app) are created via SQL DDL executed through the Snowflake CoCo CLI. The `streamlit_app.py` file is uploaded to a Snowflake stage (`@RISKGUARD_DB.APP.STREAMLIT_STAGE`) and served as a Streamlit-in-Snowflake application.

## Deployment

The application is deployed to Snowflake account `GNC03059` (AWS US-East-1) under the `RISKGUARD_DB.APP` schema.

**Prerequisites:**
- Snowflake account with ACCOUNTADMIN role
- `USE AI FUNCTIONS` granted on the account
- `CORTEX_ENABLED_CROSS_REGION` set to `ANY_REGION`
- `SNOWFLAKE.CORTEX_USER` database role granted to the deploying role
- Default warehouse (`COMPUTE_WH`) configured for the user

**Streamlit app access:**
Open Snowsight and navigate to Streamlit apps, or find `RISKGUARD_DB.APP.RISKGUARD_APP` in the object explorer.

## Hackathon Context

- **Event:** Snowflake CoCo CLI Hackathon 2026
- **Track:** Track 1 — Risk, Fraud and Regulatory Intelligence Copilot
- **Built with:** Snowflake Cortex Code (CoCo) CLI
- **Repository:** [github.com/Ravigupta9968/riskguard-ai](https://github.com/Ravigupta9968/riskguard-ai)

This is a prototype/MVP built for demonstration purposes using synthetic data. It is not intended for production use with real customer or financial data.
