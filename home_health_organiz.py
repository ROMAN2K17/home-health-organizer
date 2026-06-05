
import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta

# -----------------------------
# STREAMLIT CONFIG (MUST BE FIRST STREAMLIT CALL)
# -----------------------------
st.set_page_config(layout="wide")
st.title("🏠 Home Health Patient Tracker")

# -----------------------------
# SAFE RERUN (COMPATIBILITY)
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
# SESSION STATE (MUST COME AFTER st.set_page_config)
# -----------------------------
if "selected_patient_id" not in st.session_state:
    st.session_state["selected_patient_id"] = None

# -----------------------------
# DATABASE
# -----------------------------
conn = sqlite3.connect("patients.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT,
    last_name TEXT,
    mrn TEXT,
    insurance TEXT,
    city TEXT,
    home_health INTEGER,
    last_updated TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER,
    note TEXT,
    created_at TEXT
)
""")

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
# HELPERS
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

def load_patients():
    return pd.read_sql_query(
        "SELECT * FROM patients WHERE home_health = 1",
        conn
    )

def load_notes(patient_id):
    return pd.read_sql_query(
        "SELECT * FROM notes WHERE patient_id = ? ORDER BY created_at DESC",
        conn,
        params=(patient_id,)
    )

# -----------------------------
# ADD PATIENT (SIDEBAR)
# -----------------------------
st.sidebar.header("➕ Add Patient")

with st.sidebar.form("add_patient"):
    first_name = st.text_input("First Name")
    last_name = st.text_input("Last Name")
    mrn = st.text_input("MRN")
    insurance = st.text_input("Insurance")
    city = st.text_input("City")

    submitted = st.form_submit_button("Add")

    if submitted:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        c.execute("""
            INSERT INTO patients
            (first_name, last_name, mrn, insurance, city, home_health, last_updated)
            VALUES (?, ?, ?, ?, ?, 1, ?)
        """, (first_name, last_name, mrn, insurance, city, now))

        conn.commit()
        log_action(None, "CREATE_PATIENT", f"{first_name} {last_name}")
        safe_rerun()

# -----------------------------
# LOAD PATIENTS
# -----------------------------
patients = load_patients()

# SEARCH
search = st.text_input("🔍 Search patients").lower()
if search:
    patients = patients[
        patients["first_name"].str.lower().str.contains(search) |
        patients["last_name"].str.lower().str.contains(search) |
        patients["mrn"].str.lower().str.contains(search) |
        patients["city"].str.lower().str.contains(search)
    ]

# -----------------------------
# METRICS
# -----------------------------
overdue_count = sum(is_overdue(p) for p in patients["last_updated"])

c1, c2, c3 = st.columns(3)
c1.metric("Total Patients", len(patients))
c2.metric("Overdue", overdue_count)
c3.metric("Up to Date", len(patients) - overdue_count)

st.markdown("---")

# ---------
