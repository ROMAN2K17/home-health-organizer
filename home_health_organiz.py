import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import hashlib

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

# Users table
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT,
    role TEXT DEFAULT 'user'
)
""")

conn.commit()

# -----------------------------
# Security helpers (NO bcrypt)
# -----------------------------
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def check_password(password, hashed):
    return hashlib.sha256(password.encode()).hexdigest() == hashed

def create_default_admin():
    c.execute("SELECT * FROM users WHERE username=?", ("admin",))
    if not c.fetchone():
        c.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            ("admin", hash_password("admin123"), "admin")
        )
        conn.commit()

create_default_admin()

def authenticate(username, password):
    c.execute("SELECT * FROM users WHERE username=?", (username,))
    user = c.fetchone()
    if user and check_password(password, user[2]):
        return user
    return None

def current_user():
    return st.session_state.get("user")

# -----------------------------
# Helper Functions
# -----------------------------
def log_action(patient_id, action, details=""):
    user = current_user()
    username = user["username"] if user else "unknown"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute(
        "INSERT INTO audit_log (patient_id, action, details, created_at) VALUES (?, ?, ?, ?)",
        (patient_id, action, f"{details} | by {username}", now)
    )
    conn.commit()

def is_overdue(last_updated):
    if not last_updated:
        return True
    try:
        last_time = datetime.strptime(last_updated, "%Y-%m-%d %H:%M:%S")
        return datetime.now() - last_time > timedelta(hours=2)
    except:
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
# LOGIN SYSTEM
# -----------------------------
if "user" not in st.session_state:
    st.session_state["user"] = None

if st.session_state["user"] is None:
    st.title("🔐 Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        user = authenticate(username, password)
        if user:
            st.session_state["user"] = {
                "id": user[0],
                "username": user[1],
                "role": user[3]
            }
            safe_rerun()
        else:
            st.error("Invalid username or password")

    st.stop()

user = current_user()

# -----------------------------
# APP UI
# -----------------------------
st.set_page_config(layout="wide", page_title="Home Health Tracker")
st.title("🏠 Home Health Patient Tracker")

# -----------------------------
# SIDEBAR USER INFO
# -----------------------------
st.sidebar.markdown("## 👤 User")
st.sidebar.write(f"**{user['username']}**")
st.sidebar.write(f"Role: **{user['role']}**")

# -----------------------------
# ADMIN PANEL
# -----------------------------
if user["role"] == "admin":
    st.sidebar.markdown("---")
    st.sidebar.subheader("👑 Admin Panel")

    with st.sidebar.form("create_user"):
        new_user = st.text_input("New Username")
        new_pass = st.text_input("New Password", type="password")
        role = st.selectbox("Role", ["user", "admin"])

        if st.form_submit_button("Create User"):
            try:
                c.execute(
                    "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                    (new_user, hash_password(new_pass), role)
                )
                conn.commit()
                st.success("User created")
            except sqlite3.IntegrityError:
                st.error("Username already exists")

    st.sidebar.markdown("### 🔄 Reset Password")

    users_df = pd.read_sql_query("SELECT username FROM users", conn)
    selected_user = st.selectbox("User", users_df["username"].tolist())
    new_pass_reset = st.text_input("New Password", type="password")

    if st.button("Reset Password"):
        c.execute(
            "UPDATE users SET password=? WHERE username=?",
            (hash_password(new_pass_reset), selected_user)
        )
        conn.commit()
        st.success("Password updated")

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

    if st.form_submit_button("Add Patient"):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        c.execute("""
            INSERT INTO patients
            (first_name,last_name,mrn,insurance,city,home_health,last_updated)
            VALUES (?,?,?,?,?,1,?)
        """, (first_name, last_name, mrn, insurance, city, now))

        conn.commit()
        log_action(None, "CREATE_PATIENT", f"{first_name} {last_name}")
        safe_rerun()

# -----------------------------
# PATIENT LIST
# -----------------------------
if "selected_patient_id" not in st.session_state:
    st.session_state["selected_patient_id"] = None

patients = load_patients(0)

search = st.text_input("🔍 Search").lower()
if search:
    patients = patients[
        patients["first_name"].fillna("").str.lower().str.contains(search) |
        patients["last_name"].fillna("").str.lower().str.contains(search) |
        patients["mrn"].fillna("").str.lower().str.contains(search) |
        patients["city"].fillna("").str.lower().str.contains(search)
    ]

# -----------------------------
# METRICS
# -----------------------------
overdue_count = get_overdue_count(patients)

col1, col2, col3 = st.columns(3)
col1.metric("Total", len(patients))
col2.metric("Overdue", overdue_count)
col3.metric("Up to date", len(patients) - overdue_count)

st.markdown("---")

# -----------------------------
# PATIENT CARDS (FULL FIXED VERSION)
# -----------------------------

# Ensure session state exists
if "archive_confirm" not in st.session_state:
    st.session_state["archive_confirm"] = None

if "selected_patient_id" not in st.session_state:
    st.session_state["selected_patient_id"] = None

cols = st.columns(3)

for i, p in patients.iterrows():
    overdue = is_overdue(p["last_updated"])
    color = "#ffd6d6" if overdue else "#d9f7d9"

    with cols[i % 3]:

        # -----------------------------
        # CLICKABLE CARD (selection)
        # -----------------------------
        if st.button(
            f"{p['first_name']} {p['last_name']}",
            key=f"card_{p['id']}_select",
            use_container_width=True
        ):
            st.session_state["selected_patient_id"] = p["id"]
            safe_rerun()

        # -----------------------------
        # CARD DETAILS
        # -----------------------------
        st.markdown(f"""
        <div style="padding:10px;background:{color};
                    border-radius:10px;
                    margin-bottom:10px;">
            <b>MRN:</b> {p['mrn']}<br>
            <b>City:</b> {p['city']}<br>
            <b>Last Update:</b> {p['last_updated']}
        </div>
        """, unsafe_allow_html=True)

        # -----------------------------
        # ARCHIVE (ADMIN ONLY)
        # -----------------------------
        if user["role"] == "admin":

            # If this patient is in confirmation mode
            if st.session_state.get("archive_confirm") == p["id"]:
                st.warning(
                    f"Are you sure you want to archive "
                    f"{p['first_name']} {p['last_name']}?"
                )

                yes_col, no_col = st.columns(2)

                with yes_col:
                    if st.button(
                        "Yes",
                        key=f"archive_yes_{p['id']}"
                    ):
                        c.execute(
                            "UPDATE patients SET archived=1 WHERE id=?",
                            (p["id"],)
                        )
                        conn.commit()

                        log_action(
                            p["id"],
                            "ARCHIVE",
                            f"{p['first_name']} {p['last_name']}"
                        )

                        st.session_state["archive_confirm"] = None
                        safe_rerun()

                with no_col:
                    if st.button(
                        "No",
                        key=f"archive_no_{p['id']}"
                    ):
                        st.session_state["archive_confirm"] = None
                        safe_rerun()

            # Otherwise show archive button
            else:
                if st.button(
                    "Archive",
                    key=f"archive_{p['id']}"
                ):
                    st.session_state["archive_confirm"] = p["id"]
                    safe_rerun()
        # -----------------------------
        # Archive button (admin only)
        # -----------------------------
        if user["role"] == "admin":
            if st.session_state.get("archive_confirm") == p["id"]:
                st.warning(f"Are you sure you want to archive {p['first_name']} {p['last_name']}?")

                yes_col, no_col = st.columns(2)

                with yes_col:
                    if st.button("Yes", key=f"yes_{p['id']}"):
                        c.execute(
                            "UPDATE patients SET archived=1 WHERE id=?",
                            (p["id"],)
                        )
                        conn.commit()
                        log_action(p["id"], "ARCHIVE", f"{p['first_name']} {p['last_name']}")
                        st.session_state["archive_confirm"] = None
                        safe_rerun()

                with no_col:
                    if st.button("No", key=f"no_{p['id']}"):
                        st.session_state["archive_confirm"] = None
                        safe_rerun()
            else:
                if st.button("Archive", key=f"a_{p['id']}"):
                    st.session_state["archive_confirm"] = p["id"]
                    safe_rerun()
        # -----------------------------
        # Archive (admin only)
        # -----------------------------
        if user["role"] == "admin":

            if st.session_state.get("archive_confirm") == p["id"]:
                st.warning(f"Are you sure you want to archive {p['first_name']} {p['last_name']}?")

                yes_col, no_col = st.columns(2)

                with yes_col:
                    if st.button("Yes", key=f"yes_{p['id']}"):
                        c.execute(
                            "UPDATE patients SET archived=1 WHERE id=?",
                            (p["id"],)
                        )
                        conn.commit()
                        log_action(p["id"], "ARCHIVE", f"{p['first_name']} {p['last_name']}")
                        st.session_state["archive_confirm"] = None
                        safe_rerun()

                with no_col:
                    if st.button("No", key=f"no_{p['id']}"):
                        st.session_state["archive_confirm"] = None
                        safe_rerun()

            else:
                if st.button("Archive", key=f"a_{p['id']}"):
                    st.session_state["archive_confirm"] = p["id"]
                    safe_rerun()
# -----------------------------
# SELECTED PATIENT
# -----------------------------
selected_id = st.session_state.get("selected_patient_id")

if selected_id:
    patient_rows = patients[patients["id"] == selected_id]

    if not patient_rows.empty:
        patient = patient_rows.iloc[0]

        st.markdown("---")
        st.subheader(f"📋 {patient['first_name']} {patient['last_name']}")

        # Patient info columns
        info1, info2, info3 = st.columns(3)

        with info1:
            st.info(
                f"""
**Patient Information**

Name: {patient['first_name']} {patient['last_name']}

MRN: {patient['mrn']}

City: {patient['city']}
"""
            )

        with info2:
            st.success(
                f"""
**Insurance Information**

Insurance: {patient['insurance']}
"""
            )

        with info3:
            st.warning(
                f"""
**Status**

Last Updated:
{patient['last_updated']}
"""
            )

        # Load notes
        notes = load_notes(selected_id)

        for _, n in notes.iterrows():
            st.write(f"{n['created_at']} — {n['note']}")

        # Add new note
        new_note = st.text_area("Add note")

        if st.button("➕ Add Note"):
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            c.execute(
                """
                INSERT INTO notes (patient_id, note, created_at)
                VALUES (?,?,?)
                """,
                (selected_id, new_note, now)
            )

            c.execute(
                """
                UPDATE patients SET last_updated=? WHERE id=?
                """,
                (now, selected_id)
            )

            conn.commit()
            log_action(selected_id, "ADD_NOTE", new_note)
            safe_rerun()
# -----------------------------
# AUDIT LOG
# -----------------------------
st.markdown("---")
st.subheader("📜 Recent Activity")

audit_df = pd.read_sql_query(
    "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 50",
    conn
)

st.dataframe(audit_df, use_container_width=True)
