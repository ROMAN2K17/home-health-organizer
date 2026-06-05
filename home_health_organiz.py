# streamlit_app.py
import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta

# -----------------------------
# Safe rerun helper
# -----------------------------
def safe_rerun():
    try:
        st.rerun()
    except AttributeError:
        try:
            st.experimental_rerun()
        except AttributeError:
            pass

# -----------------------------
# Database Setup
# -----------------------------
conn = sqlite3.connect("patients.db", check_same_thread=False)
c = conn.cursor()

# Patients table with archived column
c.execute("""
CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT,
    last_name TEXT,
    mrn TEXT,
    insurance TEXT,
    city TEXT,
    home_health INTEGER,
    last_updated TEXT,
    archived INTEGER DEFAULT 0
)
""")

# Notes table
c.execute("""
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER,
    note TEXT,
    created_at TEXT
)
""")

# Audit log table
c.execute("""
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER,
    action TEXT,
    details TEXT,
    created_at TEXT
)
""")

conn.commit()

# -----------------------------
# Helper Functions
# -----------------------------
def log_action(patient_id, action, details=""):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
        INSERT INTO audit_log (patient_id, action, details, created_at)
        VALUES (?, ?, ?, ?)
    """, (patient_id, action, details, now))
    conn.commit()

def is_overdue(last_updated):
    if not last_updated:
        return True
    last_time = datetime.strptime(last_updated, "%Y-%m-%d %H:%M:%S")
    return datetime.now() - last_time > timedelta(hours=2)

def load_patients(active=True):
    """Load patients. If active=True, return non-archived."""
    status = 0 if active else 1
    return pd.read_sql_query(
        "SELECT * FROM patients WHERE home_health=1 AND archived=?",
        conn,
        params=(status,)
    )

def load_notes(patient_id):
    return pd.read_sql_query(
        "SELECT * FROM notes WHERE patient_id=? ORDER BY created_at DESC",
        conn,
        params=(patient_id,)
    )

def get_overdue_count(patients_df):
    return sum(is_overdue(p) for p in patients_df["last_updated"])

def archive_patient(patient_id):
    c.execute("UPDATE patients SET archived=1 WHERE id=?", (patient_id,))
    conn.commit()
    log_action(patient_id, "ARCHIVE_PATIENT", f"Patient ID {patient_id} archived")
    safe_rerun()

def restore_patient(patient_id):
    c.execute("UPDATE patients SET archived=0 WHERE id=?", (patient_id,))
    conn.commit()
    log_action(patient_id, "RESTORE_PATIENT", f"Patient ID {patient_id} restored")
    safe_rerun()

# -----------------------------
# Streamlit App
# -----------------------------
st.set_page_config(layout="wide")
st.title("🏠 Home Health Patient Tracker")

# -----------------------------
# Add New Patient Form (Sidebar)
# -----------------------------
st.sidebar.header("➕ Add New Patient")
with st.sidebar.form("add_patient_form"):
    first_name = st.text_input("First Name")
    last_name = st.text_input("Last Name")
    mrn = st.text_input("MRN #")
    insurance = st.text_input("Insurance")
    city = st.text_input("City")
    submitted = st.form_submit_button("Add Patient")

    if submitted:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
            INSERT INTO patients 
            (first_name, last_name, mrn, insurance, city, home_health, last_updated, archived)
            VALUES (?, ?, ?, ?, ?, 1, ?, 0)
        """, (first_name, last_name, mrn, insurance, city, now))
        conn.commit()
        log_action(None, "CREATE_PATIENT", f"{first_name} {last_name} MRN:{mrn}")
        safe_rerun()

# -----------------------------
# Tabs: Active Patients / Archived Patients
# -----------------------------
tab_active, tab_archive = st.tabs(["🏠 Active Patients", "📦 Archived Patients"])

# -----------------------------
# Active Patients Tab
# -----------------------------
with tab_active:
    patients = load_patients(active=True)

    search = st.text_input("🔍 Search active patients (name, MRN, city)").lower()
    if search:
        patients = patients[
            patients["first_name"].str.lower().str.contains(search) |
            patients["last_name"].str.lower().str.contains(search) |
            patients["mrn"].str.lower().str.contains(search) |
            patients["city"].str.lower().str.contains(search)
        ]

    overdue_count = get_overdue_count(patients)
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Home Health", len(patients))
    col2.metric("Overdue Patients", overdue_count)
    col3.metric("Up to Date", len(patients) - overdue_count)

    st.markdown("---")

    if "selected_patient_id" not in st.session_state:
        st.session_state["selected_patient_id"] = None

    cols = st.columns(3)
    for i, p in patients.iterrows():
        overdue = is_overdue(p["last_updated"])
        color = "#ffd6d6" if overdue else "#d9f7d9"
        card_id = f"patient_{p['id']}"
        confirm_key = f"confirm_archive_{p['id']}"

        with cols[i % 3]:
            if st.button(label=f"Select {p['first_name']} {p['last_name']}", key=card_id):
                st.session_state["selected_patient_id"] = p["id"]
                safe_rerun()

            st.markdown(f"""
            <div style="
                border-radius:12px;
                padding:15px;
                margin-top:-10px;
                margin-bottom:10px;
                background-color:{color};
                box-shadow:0 2px 8px rgba(0,0,0,0.1);
                cursor:pointer;
            ">
                <h4 style="margin-bottom:5px;">{p['first_name']} {p['last_name']}</h4>
                <p><b>MRN:</b> {p['mrn']}</p>
                <p><b>Insurance:</b> {p['insurance']}</p>
                <p><b>City:</b> {p['city']}</p>
                <p><b>Last Update:</b> {p['last_updated']}</p>
                {"<p style='color:red;font-weight:bold;'>⚠ OVERDUE</p>" if overdue else ""}
            </div>
            """, unsafe_allow_html=True)

            if st.button("🗄️ Archive", key=f"archive_{p['id']}"):
                st.session_state[confirm_key] = True

            if st.session_state.get(confirm_key):
                st.warning(f"⚠ Are you sure you want to archive {p['first_name']} {p['last_name']}?")
                col_yes, col_no = st.columns([1, 1])
                if col_yes.button("✅ Yes", key=f"yes_{p['id']}"):
                    archive_patient(p["id"])
                    st.session_state[confirm_key] = False
                if col_no.button("❌ No", key=f"no_{p['id']}"):
                    st.session_state[confirm_key] = False

# -----------------------------
# Archived Patients Tab
# -----------------------------
with tab_archive:
    archived_patients = load_patients(active=False)
    st.markdown("### 📦 Archived Patients")
    if archived_patients.empty:
        st.info("No archived patients.")
    else:
        for _, p in archived_patients.iterrows():
            col1, col2, col3 = st.columns([3, 1, 1])
            col1.write(f"**{p['first_name']} {p['last_name']}** — MRN: {p['mrn']}")
            if col2.button("♻ Restore", key=f"restore_{p['id']}"):
                restore_patient(p['id'])
            if col3.button("🗑️ Delete", key=f"del_archived_{p['id']}"):
                archive_key = f"confirm_delete_archived_{p['id']}"
                st.session_state[archive_key] = True
            if st.session_state.get(f"confirm_delete_archived_{p['id']}"):
                st.warning(f"⚠ Permanently delete {p['first_name']} {p['last_name']}?")
                col_yes, col_no = st.columns([1
