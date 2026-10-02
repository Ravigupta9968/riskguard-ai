import streamlit as st
import json
import pandas as pd
from snowflake.snowpark.context import get_active_session

st.set_page_config(page_title="RiskGuard AI", page_icon="🛡️", layout="wide")

session = get_active_session()


def run_query(sql):
    return session.sql(sql).to_pandas()


def call_agent(question):
    payload = json.dumps({"messages": [{"role": "user", "content": [{"type": "text", "text": question}]}]})
    result = session.sql(
        f"""SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
            'RISKGUARD_DB.APP.RISKGUARD_AGENT',
            $${payload}$$,
            FALSE
        ) AS resp"""
    ).collect()[0]["RESP"]
    return json.loads(result)


def extract_agent_text(resp):
    texts = []
    if "content" in resp:
        for block in resp["content"]:
            if block.get("type") == "text":
                texts.append(block["text"])
    elif "message" in resp:
        return resp["message"]
    return "\n".join(texts) if texts else "No response generated."


def extract_agent_sql_results(resp):
    if "content" not in resp:
        return None
    for block in resp["content"]:
        if block.get("type") == "tool_result":
            content = block.get("tool_result", {}).get("content", [])
            for c in content:
                if c.get("type") == "json" and "result_set" in c.get("json", {}):
                    rs = c["json"]["result_set"]
                    cols = [col["name"] for col in rs["resultSetMetaData"]["rowType"]]
                    return pd.DataFrame(rs["data"], columns=cols)
    return None


def log_audit(action_type, input_text, output_text, customer_id=None, alert_id=None):
    safe_input = input_text.replace("'", "''")[:5000]
    safe_output = output_text.replace("'", "''")[:10000]
    cust = f"'{customer_id}'" if customer_id else "NULL"
    alt = f"'{alert_id}'" if alert_id else "NULL"
    session.sql(f"""
        INSERT INTO RISKGUARD_DB.APP.AUDIT_LOG
        (LOG_ID, USER_NAME, ACTION_TYPE, INPUT_TEXT, OUTPUT_TEXT, MODEL_USED, RELATED_CUSTOMER_ID, RELATED_ALERT_ID, CREATED_AT)
        SELECT UUID_STRING(), CURRENT_USER(), '{action_type}', '{safe_input}', '{safe_output}', 'cortex-agent', {cust}, {alt}, CURRENT_TIMESTAMP()
    """).collect()


# --- HEADER ---
st.title("RiskGuard AI")
st.caption("Risk, Fraud & Regulatory Intelligence Copilot")

tab1, tab2, tab3, tab4 = st.tabs(["Dashboard", "Investigation Panel", "Ask RiskGuard", "Audit & Reports"])

# ==================== TAB 1: DASHBOARD ====================
with tab1:
    kpi = run_query("""
        SELECT
            (SELECT COUNT(*) FROM RISKGUARD_DB.ANALYTICS.FRAUD_ALERTS WHERE STATUS = 'OPEN') AS open_alerts,
            (SELECT COUNT(*) FROM RISKGUARD_DB.ANALYTICS.INVESTIGATIONS WHERE STATUS IN ('OPEN','IN_PROGRESS','PENDING_REVIEW')) AS active_investigations,
            (SELECT ROUND(AVG(RISK_SCORE),1) FROM RISKGUARD_DB.ANALYTICS.RISK_SCORES) AS avg_risk_score,
            (SELECT COUNT(*) FROM RISKGUARD_DB.ANALYTICS.SAR_REPORTS WHERE STATUS = 'FILED') AS sars_filed
    """)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Open Alerts", int(kpi["OPEN_ALERTS"][0]))
    c2.metric("Active Investigations", int(kpi["ACTIVE_INVESTIGATIONS"][0]))
    c3.metric("Avg Risk Score", float(kpi["AVG_RISK_SCORE"][0]))
    c4.metric("SARs Filed", int(kpi["SARS_FILED"][0]))

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Alerts by Severity")
        alerts_sev = run_query("""
            SELECT SEVERITY, COUNT(*) AS COUNT
            FROM RISKGUARD_DB.ANALYTICS.FRAUD_ALERTS
            WHERE STATUS = 'OPEN'
            GROUP BY SEVERITY
            ORDER BY CASE SEVERITY WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END
        """)
        st.bar_chart(alerts_sev, x="SEVERITY", y="COUNT")

    with col_right:
        st.subheader("Alerts by Type")
        alerts_type = run_query("""
            SELECT ALERT_TYPE, COUNT(*) AS COUNT
            FROM RISKGUARD_DB.ANALYTICS.FRAUD_ALERTS
            WHERE STATUS = 'OPEN'
            GROUP BY ALERT_TYPE
            ORDER BY COUNT DESC
        """)
        st.bar_chart(alerts_type, x="ALERT_TYPE", y="COUNT")

    st.subheader("Top 10 High-Risk Customers")
    top_risk = run_query("""
        SELECT c.CUSTOMER_ID, c.FULL_NAME, c.COUNTRY, c.RISK_RATING, c.INDUSTRY,
               rs.RISK_SCORE, c.PEP_FLAG, c.SANCTIONS_FLAG,
               (SELECT COUNT(*) FROM RISKGUARD_DB.ANALYTICS.FRAUD_ALERTS fa WHERE fa.CUSTOMER_ID = c.CUSTOMER_ID AND fa.STATUS = 'OPEN') AS OPEN_ALERTS
        FROM RISKGUARD_DB.CORE.CUSTOMERS c
        JOIN RISKGUARD_DB.ANALYTICS.RISK_SCORES rs ON c.CUSTOMER_ID = rs.CUSTOMER_ID
        ORDER BY rs.RISK_SCORE DESC
        LIMIT 10
    """)
    st.dataframe(top_risk, use_container_width=True)

# ==================== TAB 2: INVESTIGATION PANEL ====================
with tab2:
    inv_col1, inv_col2 = st.columns([1, 3])

    with inv_col1:
        st.subheader("Select Customer")
        customers = run_query("""
            SELECT c.CUSTOMER_ID, c.FULL_NAME, rs.RISK_SCORE
            FROM RISKGUARD_DB.CORE.CUSTOMERS c
            JOIN RISKGUARD_DB.ANALYTICS.RISK_SCORES rs ON c.CUSTOMER_ID = rs.CUSTOMER_ID
            ORDER BY rs.RISK_SCORE DESC LIMIT 50
        """)
        selected = st.selectbox(
            "Customer",
            customers["CUSTOMER_ID"].tolist(),
            format_func=lambda x: f"{x} - {customers[customers['CUSTOMER_ID']==x]['FULL_NAME'].iloc[0]} (Score: {customers[customers['CUSTOMER_ID']==x]['RISK_SCORE'].iloc[0]})"
        )

    with inv_col2:
        if selected:
            profile = run_query(f"""
                SELECT c.*, rs.RISK_SCORE, rs.RISK_CATEGORY
                FROM RISKGUARD_DB.CORE.CUSTOMERS c
                JOIN RISKGUARD_DB.ANALYTICS.RISK_SCORES rs ON c.CUSTOMER_ID = rs.CUSTOMER_ID
                WHERE c.CUSTOMER_ID = '{selected}'
            """)
            p = profile.iloc[0]

            st.subheader(f"Customer Profile: {p['FULL_NAME']}")
            pc1, pc2, pc3, pc4 = st.columns(4)
            pc1.metric("Risk Score", float(p["RISK_SCORE"]))
            pc2.metric("Risk Rating", p["RISK_RATING"])
            pc3.metric("PEP", "Yes" if p["PEP_FLAG"] else "No")
            pc4.metric("Sanctions", "Yes" if p["SANCTIONS_FLAG"] else "No")

            det1, det2 = st.columns(2)
            with det1:
                st.markdown(f"**Country:** {p['COUNTRY']}")
                st.markdown(f"**Industry:** {p['INDUSTRY']}")
                st.markdown(f"**KYC Status:** {p['KYC_STATUS']}")
            with det2:
                st.markdown(f"**Type:** {p['CUSTOMER_TYPE']}")
                st.markdown(f"**Onboarded:** {p['ONBOARDING_DATE']}")
                st.markdown(f"**Risk Category:** {p['RISK_CATEGORY']}")

            st.subheader("Fraud Alerts")
            alerts = run_query(f"""
                SELECT fa.ALERT_ID, fa.ALERT_TYPE, fa.SEVERITY, fa.STATUS, fa.DESCRIPTION,
                       ar.RULE_NAME, fa.CREATED_AT
                FROM RISKGUARD_DB.ANALYTICS.FRAUD_ALERTS fa
                JOIN RISKGUARD_DB.ANALYTICS.ALERT_RULES ar ON fa.RULE_ID = ar.RULE_ID
                WHERE fa.CUSTOMER_ID = '{selected}'
                ORDER BY fa.CREATED_AT DESC
            """)
            if not alerts.empty:
                st.dataframe(alerts, use_container_width=True)
            else:
                st.info("No alerts for this customer.")

            st.subheader("Recent Transactions")
            txns = run_query(f"""
                SELECT t.TXN_ID, t.TXN_DATE, t.AMOUNT, t.TXN_TYPE, t.CHANNEL, t.DIRECTION,
                       t.COUNTERPARTY_NAME, t.COUNTERPARTY_COUNTRY, t.IS_CASH
                FROM RISKGUARD_DB.CORE.TRANSACTIONS t
                JOIN RISKGUARD_DB.CORE.ACCOUNTS a ON t.ACCOUNT_ID = a.ACCOUNT_ID
                WHERE a.CUSTOMER_ID = '{selected}'
                ORDER BY t.TXN_DATE DESC
                LIMIT 50
            """)
            st.dataframe(txns, use_container_width=True)

            st.subheader("AI-Powered Analysis")
            ac1, ac2 = st.columns(2)

            with ac1:
                if st.button("Explain Risk Factors", key="explain"):
                    with st.spinner("Analyzing..."):
                        resp = call_agent(f"Explain why customer {selected} was flagged as high risk. Include specific transaction evidence.")
                        text = extract_agent_text(resp)
                        st.markdown(text)
                        log_audit("RISK_EXPLANATION", f"Explain risk for {selected}", text, customer_id=selected)

            with ac2:
                if st.button("Draft SAR Narrative", key="sar"):
                    with st.spinner("Generating SAR narrative..."):
                        resp = call_agent(
                            f"Generate a complete SAR narrative for customer {selected}. "
                            f"Include: subject identification, suspicious activity description with specific transaction IDs and amounts, "
                            f"timeline of events, and regulatory basis for filing. Reference BSA/AML requirements."
                        )
                        text = extract_agent_text(resp)
                        st.markdown(text)
                        log_audit("SAR_GENERATION", f"Draft SAR for {selected}", text, customer_id=selected)

# ==================== TAB 3: ASK RISKGUARD ====================
with tab3:
    st.subheader("Ask RiskGuard AI")
    st.caption("Ask questions about your risk data, regulatory requirements, or request investigations.")

    quick_questions = [
        "How many open alerts do we have by severity?",
        "Which customers sent more than $100K to high-risk countries?",
        "What are the SAR filing deadlines?",
        "Show me all structuring alerts with transaction details",
        "What is the OFAC penalty for sanctions violations?",
    ]

    st.markdown("**Quick questions:**")
    qcols = st.columns(len(quick_questions))
    for i, q in enumerate(quick_questions):
        if qcols[i].button(q[:30] + "...", key=f"qq_{i}"):
            st.session_state["chat_input"] = q

    user_input = st.text_area(
        "Your question:",
        value=st.session_state.get("chat_input", ""),
        height=80,
        key="user_question"
    )

    if st.button("Ask RiskGuard", type="primary"):
        if user_input.strip():
            with st.spinner("RiskGuard AI is thinking..."):
                resp = call_agent(user_input)
                text = extract_agent_text(resp)
                st.markdown("---")
                st.markdown("### Answer")
                st.markdown(text)

                sql_df = extract_agent_sql_results(resp)
                if sql_df is not None:
                    st.markdown("### Data Results")
                    st.dataframe(sql_df, use_container_width=True)

                log_audit("QUERY", user_input, text)
        else:
            st.warning("Please enter a question.")

# ==================== TAB 4: AUDIT & REPORTS ====================
with tab4:
    st.subheader("Audit Log")
    st.caption("All AI-generated outputs are logged for compliance and audit purposes.")

    audit_data = run_query("""
        SELECT LOG_ID, USER_NAME, ACTION_TYPE, INPUT_TEXT, MODEL_USED,
               RELATED_CUSTOMER_ID, RELATED_ALERT_ID, CREATED_AT
        FROM RISKGUARD_DB.APP.AUDIT_LOG
        ORDER BY CREATED_AT DESC
        LIMIT 100
    """)

    if not audit_data.empty:
        aud1, aud2 = st.columns(2)
        with aud1:
            st.metric("Total AI Interactions", len(audit_data))
        with aud2:
            action_counts = audit_data["ACTION_TYPE"].value_counts()
            st.markdown("**By action type:** " + ", ".join(f"{k}: {v}" for k, v in action_counts.items()))

        st.dataframe(audit_data, use_container_width=True)
    else:
        st.info("No audit log entries yet. AI interactions will be logged as you use the app.")

    st.subheader("Investigation Summary")
    investigations = run_query("""
        SELECT i.INVESTIGATION_ID, i.CUSTOMER_ID, c.FULL_NAME, i.STATUS, i.PRIORITY,
               i.ASSIGNED_TO, i.OPENED_AT, i.SUMMARY
        FROM RISKGUARD_DB.ANALYTICS.INVESTIGATIONS i
        JOIN RISKGUARD_DB.CORE.CUSTOMERS c ON i.CUSTOMER_ID = c.CUSTOMER_ID
        ORDER BY
            CASE i.STATUS WHEN 'OPEN' THEN 1 WHEN 'IN_PROGRESS' THEN 2 WHEN 'PENDING_REVIEW' THEN 3 ELSE 4 END,
            i.OPENED_AT DESC
    """)
    st.dataframe(investigations, use_container_width=True)

    st.subheader("SAR Filing Queue")
    sars = run_query("""
        SELECT s.SAR_ID, s.CUSTOMER_ID, c.FULL_NAME, s.STATUS, s.FILING_DATE,
               s.TOTAL_SUSPICIOUS_AMOUNT, s.GENERATED_BY, s.REVIEWED_BY
        FROM RISKGUARD_DB.ANALYTICS.SAR_REPORTS s
        JOIN RISKGUARD_DB.CORE.CUSTOMERS c ON s.CUSTOMER_ID = c.CUSTOMER_ID
        ORDER BY CASE s.STATUS WHEN 'DRAFT' THEN 1 WHEN 'PENDING_REVIEW' THEN 2 WHEN 'FILED' THEN 3 ELSE 4 END
    """)
    st.dataframe(sars, use_container_width=True)
