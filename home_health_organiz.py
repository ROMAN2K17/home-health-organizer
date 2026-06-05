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
    last_updated TEXT
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

def load_patients():
    return pd.read_sql_query("SELECT * FROM patients WHERE home_health = 1", conn)

def load_notes(patient_id):
    return pd.read_sql_query(
        "SELECT * FROM notes WHERE patient_id = ? ORDER BY created_at DESC",
        conn,
        params=(patient_id,)
    )

def get_overdue_count(patients_df):
    return sum(is_overdue(p) for p in patients_df["last_updated"])

def delete_patient(patient_id):
    # Delete notes
    c.execute("DELETE FROM notes WHERE patient_id = ?", (patient_id,))
    # Delete patient
    c.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
    conn.commit()
    log_action(patient_id, "DELETE_PATIENT", f"Patient ID {patient_id} deleted")
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
            (first_name, last_name, mrn, insurance, city, home_health, last_updated)
            VALUES (?, ?, ?, ?, ?, 1, ?)
        """, (first_name, last_name, mrn, insurance, city, now))
        conn.commit()
        log_action(None, "CREATE_PATIENT", f"{first_name} {last_name} MRN:{mrn}")
        safe_rerun()

# -----------------------------
# Load and Search Patients
# -----------------------------
patients = load_patients()

search = st.text_input("🔍 Search patients (name, MRN, city)").lower()
if search:
    patients = patients[
        patients["first_name"].str.lower().str.contains(search) |
        patients["last_name"].str.lower().str.contains(search) |
        patients["mrn"].str.lower().str.contains(search) |
        patients["city"].str.lower().str.contains(search)
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
# Patient Selection State
# -----------------------------
if "selected_patient_id" not in st.session_state:
    st.session_state["selected_patient_id"] = None

# -----------------------------
# Card-Based Layout (FULL CLICKABLE CARDS)
# -----------------------------
st.markdown("## 🏠 Home Health Patients")

cols = st.columns(3)

for i, p in patients.iterrows():
    overdue = is_overdue(p["last_updated"])
    color = "#ffd6d6" if overdue else "#d9f7d9"
    card_id = f"patient_{p['id']}"
    confirm_key = f"confirm_delete_{p['id']}"

    with cols[i % 3]:
        # Invisible button to select patient
        if st.button(label=f"Select {p['first_name']} {p['last_name']}", key=card_id):
            st.session_state["selected_patient_id"] = p["id"]
            safe_rerun()

        # Visual card
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

        # Delete patient button with confirmation
        if st.button("🗑️ Delete", key=f"del_{p['id']}"):
            st.session_state[confirm_key] = True

        if st.session_state.get(confirm_key):
            st.warning(f"⚠ Are you sure you want to delete {p['first_name']} {p['last_name']}?")
            col_yes, col_no = st.columns([1, 1])
            if col_yes.button("✅ Yes", key=f"yes_{p['id']}"):
                delete_patient(p["id"])
                st.session_state[confirm_key] = False
            if col_no.button("❌ No", key=f"no_{p['id']}"):
                st.session_state[confirm_key] = False

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

        # -----------------------------
        # Notes Section
        # -----------------------------
        st.markdown("### 📝 Notes")
        notes = load_notes(selected_id)
        if notes.empty:
            st.info("No notes yet.")

        for _, n in notes.iterrows():
            col1, col2 = st.columns([6, 1])
            col1.write(f"**{n['created_at']}** — {n['note']}")
            if col2.button("🗑️", key=f"delete_note_{n['id']}"):
                c.execute("DELETE FROM notes WHERE id = ?", (n["id"],))
                conn.commit()
                log_action(selected_id, "DELETE_NOTE", f"Note ID {n['id']}")
                safe_rerun()

        # Add new note
        new_note = st.text_area("Add a new note", key=f"note_box_{selected_id}")
        if st.button("➕ Add Note", key=f"add_note_{selected_id}"):
            if new
