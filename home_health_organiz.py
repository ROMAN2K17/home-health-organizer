# home_health_organiz.py
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

# Patients table
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
    c.execute(
        "INSERT INTO audit_log (patient_id, action, details, created_at) VALUES (?, ?, ?, ?)",
        (patient_id, action, details, now)
    )
    conn.commit()

def is_overdue(last_updated):
    if not last_updated:
        return True
    try:
        last_time = datetime.strptime(last_updated, "%Y-%m-%d %H:%M:%S")
        return datetime.now() - last_time > timedelta(hours=2)
    except Exception:
        return True

def load_patients(archived=0):
    return pd.read_sql_query(
        "SELECT * FROM patients WHERE home_health=1 AND archived=? ORDER BY last_updated DESC",
        conn,
        params=(archived,)
    )

def load_notes(patient_id):
    return pd.read_sql_query(
        "SELECT * FROM notes WHERE patient_id=? ORDER BY created_at DESC",
        conn,
        params=(patient_id,)
    )

def get_overdue_count(patients_df):
    return sum(is_overdue(p) for p in patients_df["last_updated"])

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
        c.execute(
            "INSERT INTO patients (first_name,last_name,mrn,insurance,city,home_health,last_updated) VALUES (?,?,?,?,?,1,?)",
            (first_name, last_name, mrn, insurance, city, now)
        )
        conn.commit()
        log_action(None, "CREATE_PATIENT", f"{first_name} {last_name} MRN:{mrn}")
        safe_rerun()

# -----------------------------
# Patient Selection State
# -----------------------------
if "selected_patient_id" not in st.session_state:
    st.session_state["selected_patient_id"] = None

# -----------------------------
# Load and Search Patients
# -----------------------------
patients = load_patients(archived=0)
search = st.text_input("🔍 Search patients (name, MRN, city)").lower()
if search:
    patients = patients[
        patients["first_name"].fillna("").str.lower().str.contains(search) |
        patients["last_name"].fillna("").str.lower().str.contains(search) |
        patients["mrn"].fillna("").str.lower().str.contains(search) |
        patients["city"].fillna("").str.lower().str.contains(search)
    ]

# -----------------------------
# Dashboard Metrics
# -----------------------------
overdue_count = get_overdue_count(patients)
col1, col2, col3 = st.columns(3)
col1.metric("Total Home Health", len(patients))
col2.metric("Overdue Patients", overdue_count)
col3.metric("Up to Date", len(patients) - overdue_count)
st.markdown("---")

# -----------------------------
# Card-Based Layout (Clickable)
# -----------------------------
st.markdown("## 🏠 Home Health Patients")
cols = st.columns(3)

for i, p in patients.iterrows():
    overdue = is_overdue(p["last_updated"])
    color = "#ffd6d6" if overdue else "#d9f7d9"
    card_id = f"patient_{p['id']}"

    with cols[i % 3]:
        if st.button(f"Select {p['first_name']} {p['last_name']}", key=card_id):
            st.session_state["selected_patient_id"] = p["id"]
            safe_rerun()

        st.markdown(f"""
        <div style="
            border-radius:12px;
            padding:15px;
            margin-top:-10px;
            margin-bottom:20px;
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

        if st.button(f"Delete {p['first_name']} {p['last_name']}", key=f"delete_{p['id']}"):
            st.session_state["delete_patient_id"] = p['id']

# -----------------------------
# Delete Confirmation Modal
# -----------------------------
if "delete_patient_id" in st.session_state:
    pid = st.session_state["delete_patient_id"]
    patient_rows = patients[patients["id"] == pid]
    if not patient_rows.empty:
        patient = patient_rows.iloc[0]
        st.warning(f"Are you sure you want to delete {patient['first_name']} {patient['last_name']}?")
        col_yes, col_no = st.columns(2)
        if col_yes.button("Yes, delete", key=f"confirm_delete_{pid}"):
            c.execute("DELETE FROM patients WHERE id=?", (pid,))
            c.execute("DELETE FROM notes WHERE patient_id=?", (pid,))
            conn.commit()
            log_action(pid, "DELETE_PATIENT", f"{patient['first_name']} {patient['last_name']}")
            del st.session_state["delete_patient_id"]
            safe_rerun()
        if col_no.button("Cancel", key=f"cancel_delete_{pid}"):
            del st.session_state["delete_patient_id"]
            safe_rerun()

# -----------------------------
# Selected Patient Workspace
# -----------------------------
selected_id = st.session_state.get("selected_patient_id")
if selected_id:
    patient_rows = patients[patients["id"] == selected_id]
    if not patient_rows.empty:
        patient = patient_rows.iloc[0]
        st.markdown("---")
        st.subheader(f"📋 {patient['first_name']} {patient['last_name']}")
        if is_overdue(patient["last_updated"]):
            st.error("⚠️ OVERDUE: No update in over 2 hours")
        else:
            st.success("✅ Up to date")
        st.write(f"**MRN:** {patient['mrn']}")
        st.write(f"**Insurance:** {patient['insurance']}")
        st.write(f"**City:** {patient['city']}")
        st.write(f"**Last Updated:** {patient['last_updated']}")

        # Notes section
        st.markdown("### 📝 Notes")
        notes = load_notes(selected_id)
        if notes.empty:
            st.info("No notes yet.")

        for _, n in notes.iterrows():
            col1, col2 = st.columns([6,1])
            col1.write(f"**{n['created_at']}** — {n['note']}")
            if col2.button("🗑️", key=f"delete_note_{n['id']}"):
                c.execute("DELETE FROM notes WHERE id=?", (n["id"],))
                conn.commit()
                log_action(selected_id, "DELETE_NOTE", f"Note ID {n['id']}")
                safe_rerun()

        # Add new note
        new_note = st.text_area("Add a new note", key=f"note_box_{selected_id}")
        if st.button("
