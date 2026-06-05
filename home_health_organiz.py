import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta

# -----------------------------
# SAFE RERUN
# -----------------------------
def safe_rerun():
    try:
        st.rerun()
    except:
        st.experimental_rerun()

# -----------------------------
# DB SETUP
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
    last_updated TEXT,
    archived INTEGER DEFAULT 0
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
def log_action(pid, action, details=""):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
        INSERT INTO audit_log (patient_id, action, details, created_at)
        VALUES (?, ?, ?, ?)
    """, (pid, action, details, now))
    conn.commit()

def is_overdue(ts):
    if not ts:
        return True
    return datetime.now() - datetime.strptime(ts, "%Y-%m-%d %H:%M:%S") > timedelta(hours=2)

def load_patients(archived=0):
    return pd.read_sql_query(
        "SELECT * FROM patients WHERE home_health=1 AND archived=?",
        conn,
        params=(archived,)
    )

def load_notes(pid):
    return pd.read_sql_query(
        "SELECT * FROM notes WHERE patient_id=? ORDER BY created_at DESC",
        conn,
        params=(pid,)
    )

def archive_patient(pid):
    c.execute("UPDATE patients SET archived=1 WHERE id=?", (pid,))
    conn.commit()
    log_action(pid, "ARCHIVE", "Patient archived")
    safe_rerun()

def restore_patient(pid):
    c.execute("UPDATE patients SET archived=0 WHERE id=?", (pid,))
    conn.commit()
    log_action(pid, "RESTORE", "Patient restored")
    safe_rerun()

def delete_patient(pid):
    c.execute("DELETE FROM notes WHERE patient_id=?", (pid,))
    c.execute("DELETE FROM patients WHERE id=?", (pid,))
    conn.commit()
    log_action(pid, "DELETE", "Patient permanently deleted")
    safe_rerun()

# -----------------------------
# UI
# -----------------------------
st.set_page_config(layout="wide")
st.title("🏠 Home Health Tracker")

# -----------------------------
# SESSION STATE
# -----------------------------
if "selected_patient_id" not in st.session_state:
    st.session_state.selected_patient_id = None

# -----------------------------
# ADD PATIENT
# -----------------------------
st.sidebar.header("➕ Add Patient")
with st.sidebar.form("add"):
    fn = st.text_input("First Name")
    ln = st.text_input("Last Name")
    mrn = st.text_input("MRN")
    ins = st.text_input("Insurance")
    city = st.text_input("City")
    submit = st.form_submit_button("Add")

    if submit:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
            INSERT INTO patients
            (first_name,last_name,mrn,insurance,city,home_health,last_updated,archived)
            VALUES (?,?,?,?,?,?,?,0)
        """, (fn, ln, mrn, ins, city, 1, now))
        conn.commit()
        log_action(None, "CREATE", f"{fn} {ln}")
        safe_rerun()

# -----------------------------
# TABS
# -----------------------------
tab1, tab2 = st.tabs(["Active Patients", "Archive"])

# -----------------------------
# ACTIVE
# -----------------------------
with tab1:
    patients = load_patients(0)

    st.subheader("Active Patients")

    cols = st.columns(3)

    for i, p in patients.iterrows():
        overdue = is_overdue(p["last_updated"])
        color = "#ffd6d6" if overdue else "#d9f7d9"

        with cols[i % 3]:

            if st.button(f"Open {p['first_name']} {p['last_name']}", key=f"open_{p['id']}"):
                st.session_state.selected_patient_id = p["id"]
                safe_rerun()

            st.markdown(f"""
            <div style="padding:12px;border-radius:10px;background:{color};margin-bottom:10px">
                <b>{p['first_name']} {p['last_name']}</b><br>
                MRN: {p['mrn']}<br>
                Insurance: {p['insurance']}<br>
                City: {p['city']}<br>
                Last: {p['last_updated']}
            </div>
            """, unsafe_allow_html=True)

            # ARCHIVE BUTTON
            if st.button("📦 Archive", key=f"arc_{p['id']}"):
                archive_patient(p["id"])

# -----------------------------
# ARCHIVE
# -----------------------------
with tab2:
    archived = load_patients(1)

    st.subheader("Archived Patients")

    if archived.empty:
        st.info("No archived patients.")
    else:
        for _, p in archived.iterrows():
            col1, col2, col3 = st.columns([3,1,1])

            col1.write(f"{p['first_name']} {p['last_name']}")

            if col2.button("♻ Restore", key=f"res_{p['id']}"):
                restore_patient(p["id"])

            if col3.button("🗑️ Delete", key=f"del_{p['id']}"):
                st.warning("Confirm permanent delete below")

                c1, c2 = st.columns([1,1])

                if c1.button("YES", key=f"yes_{p['id']}"):
                    delete_patient(p["id"])

                if c2.button("NO", key=f"no_{p['id']}"):
                    st.info("Cancelled")

# -----------------------------
# WORKSPACE
# -----------------------------
pid = st.session_state.selected_patient_id

if pid:
    patient = patients[patients["id"] == pid]

    if not patient.empty:
        p = patient.iloc[0]

        st.markdown("---")
        st.subheader(f"{p['first_name']} {p['last_name']}")

        st.write("MRN:", p["mrn"])
        st.write("Insurance:", p["insurance"])
        st.write("City:", p["city"])

        if st.button("📦 Archive Patient"):
            archive_patient(pid)

        if st.button("🗑️ Delete Patient"):
            delete_patient(pid)

        st.markdown("### Notes")
        notes = load_notes(pid)

        for _, n in notes.iterrows():
            c1, c2 = st.columns([6,1])
            c1.write(n["note"])
            if c2.button("🗑️", key=f"n_{n['id']}"):
                c.execute("DELETE FROM notes WHERE id=?", (n["id"],))
                conn.commit()
                log_action(pid, "DELETE_NOTE", "")
                safe_rerun()

        new_note = st.text_area("Add note")
        if st.button("Add Note"):
            if new_note.strip():
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                c.execute(
                    "INSERT INTO notes (patient_id,note,created_at) VALUES (?,?,?)",
                    (pid, new_note, now)
                )

                c.execute(
                    "UPDATE patients SET last_updated=? WHERE id=?",
                    (now, pid)
                )

                conn.commit()
                log_action(pid, "ADD_NOTE", new_note)
                safe_rerun()

# -----------------------------
# AUDIT LOG
# -----------------------------
st.sidebar.header("Audit Log")

audit = pd.read_sql_query(
    "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 20",
    conn
)

st.sidebar.dataframe(audit)
