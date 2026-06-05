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
    except AttributeError:
        try:
            st.experimental_rerun()
        except AttributeError:
            pass

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
    return pd.read_sql_query("SELECT * FROM patients WHERE home_health = 1", conn)

def load_notes(patient_id):
    return pd.read_sql_query(
        "SELECT * FROM notes WHERE patient_id = ? ORDER BY created_at DESC",
        conn,
        params=(patient_id,)
    )

# -----------------------------
# DELETE PATIENT (MAIN FUNCTION)
# -----------------------------
def delete_patient(patient_id):
    c.execute("DELETE FROM notes WHERE patient_id = ?", (patient_id,))
    c.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
    conn.commit()

    log_action(patient_id, "DELETE_PATIENT", f"Deleted patient {patient_id}")

    if st.session_state.get("selected_patient_id") == patient_id:
        st.session_state["selected_patient_id"] = None

    safe_rerun()

# -----------------------------
# STREAMLIT CONFIG
# -----------------------------
st.set_page_config(layout="wide")
st.title("🏠 Home Health Patient Tracker")

# -----------------------------
# SESSION STATE
# -----------------------------
if "selected_patient_id" not in st.session_state:
    st.session_state["selected_patient_id"] = None

# -----------------------------
# ADD PATIENT
# -----------------------------
st.sidebar.header("➕ Add New Patient")

with st.sidebar.form("add_patient"):
    first_name = st.text_input("First Name")
    last_name = st.text_input("Last Name")
    mrn = st.text_input("MRN")
    insurance = st.text_input("Insurance")
    city = st.text_input("City")
    submitted = st.form_submit_button("Add Patient")

    if submitted and first_name.strip():
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        c.execute("""
            INSERT INTO patients
            (first_name, last_name, mrn, insurance, city, home_health, last_updated)
            VALUES (?, ?, ?, ?, ?, 1, ?)
        """, (first_name, last_name, mrn, insurance, city, now))

        conn.commit()
        log_action(None, "CREATE_PATIENT", f"{first_name} {last_name}")

        st.session_state["selected_patient_id"] = None
        safe_rerun()

# -----------------------------
# LOAD PATIENTS
# -----------------------------
patients = load_patients()

# -----------------------------
# SEARCH
# -----------------------------
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
overdue_count = sum(is_overdue(x) for x in patients["last_updated"])

c1, c2, c3 = st.columns(3)
c1.metric("Total", len(patients))
c2.metric("Overdue", overdue_count)
c3.metric("Up to Date", len(patients) - overdue_count)

st.markdown("---")

# -----------------------------
# PATIENT CARDS
# -----------------------------
st.subheader("🏠 Patients")

cols = st.columns(3)

for i, p in patients.iterrows():
    overdue = is_overdue(p["last_updated"])
    color = "#ffd6d6" if overdue else "#d9f7d9"

    with cols[i % 3]:

        # OPEN PATIENT
        if st.button(f"{p['first_name']} {p['last_name']}", key=f"open_{p['id']}"):
            st.session_state["selected_patient_id"] = p["id"]
            safe_rerun()

        # DELETE PATIENT (CARD)
        if st.button("🗑️ Delete", key=f"del_{p['id']}"):
            delete_patient(p["id"])

        # CARD UI
        st.markdown(f"""
        <div style="
            border-radius:12px;
            padding:12px;
            margin-top:-10px;
            margin-bottom:20px;
            background-color:{color};
            box-shadow:0 2px 8px rgba(0,0,0,0.1);
        ">
            <b>MRN:</b> {p['mrn']}<br>
            <b>Insurance:</b> {p['insurance']}<br>
            <b>City:</b> {p['city']}<br>
            <b>Last Update:</b> {p['last_updated']}<br>
            {"<b style='color:red;'>⚠ OVERDUE</b>" if overdue else ""}
        </div>
        """, unsafe_allow_html=True)

# -----------------------------
# SELECTED PATIENT
# -----------------------------
selected_id = st.session_state["selected_patient_id"]

if selected_id:

    patient_rows = patients[patients["id"] == selected_id]

    if not patient_rows.empty:

        patient = patient_rows.iloc[0]

        st.markdown("---")
        st.subheader(f"📋 {patient['first_name']} {patient['last_name']}")

        if is_overdue(patient["last_updated"]):
            st.error("⚠ OVERDUE")
        else:
            st.success("Up to date")

        st.write(f"MRN: {patient['mrn']}")
        st.write(f"Insurance: {patient['insurance']}")
        st.write(f"City: {patient['city']}")

        # DELETE PATIENT (WORKSPACE)
        if st.button("🗑️ Delete Patient"):
            delete_patient(selected_id)

        # -----------------------------
        # NOTES
        # -----------------------------
        st.markdown("### 📝 Notes")
        notes = load_notes(selected_id)

        for _, n in notes.iterrows():
            col1, col2 = st.columns([6, 1])

            col1.write(f"{n['created_at']} — {n['note']}")

            if col2.button("🗑️", key=f"note_{n['id']}"):
                c.execute("DELETE FROM notes WHERE id=?", (n["id"],))
                conn.commit()
                log_action(selected_id, "DELETE_NOTE", n["note"])
                safe_rerun()

        new_note = st.text_area("Add note", key=f"note_{selected_id}")

        if st.button("➕ Add Note", key=f"add_{selected_id}"):
            if new_note.strip():
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                c.execute("""
                    INSERT INTO notes (patient_id, note, created_at)
                    VALUES (?, ?, ?)
                """, (selected_id, new_note, now))

                c.execute("""
                    UPDATE patients SET last_updated=? WHERE id=?
                """, (now, selected_id))

                conn.commit()
                log_action(selected_id, "ADD_NOTE", new_note)
                safe_rerun()

# -----------------------------
# AUDIT TRAIL
# -----------------------------
st.sidebar.markdown("## 🧾 Audit Log")

audit = pd.read_sql_query(
    "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 20",
    conn
)

st.sidebar.dataframe(audit)
