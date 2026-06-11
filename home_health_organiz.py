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
# ADMIN PANEL (CLEAN VERSION)
# -----------------------------
if user["role"] == "admin":

    st.sidebar.markdown("---")
    st.sidebar.subheader("👑 Admin Panel")

    # =============================
    # CREATE USER (ONLY ONE FORM)
    # =============================
    with st.sidebar.form("admin_create_user_form", clear_on_submit=True):

        new_user = st.text_input("New Username", key="admin_new_user")
        new_pass = st.text_input("New Password", type="password", key="admin_new_pass")
        role = st.selectbox("Role", ["user", "admin"], key="admin_role_select")

        submitted = st.form_submit_button("Create User")

        if submitted and new_user and new_pass:

            try:
                c.execute(
                    "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                    (new_user, hash_password(new_pass), role)
                )
                conn.commit()

                st.success("User created")

            except sqlite3.IntegrityError:
                st.error("Username already exists")

    # =============================
    # RESET PASSWORD (SINGLE SECTION)
    # =============================
    st.sidebar.markdown("### 🔄 Reset Password")

    users_df = pd.read_sql_query("SELECT username FROM users", conn)

    selected_user = st.selectbox(
        "Select User",
        users_df["username"].tolist(),
        key="admin_reset_user"
    )

    new_pass_reset = st.text_input(
        "New Password",
        type="password",
        key="admin_reset_pass"
    )

    if st.button("Reset Password", key="admin_reset_button"):

        if new_pass_reset:

            c.execute(
                "UPDATE users SET password=? WHERE username=?",
                (hash_password(new_pass_reset), selected_user)
            )
            conn.commit()

            st.success("Password updated")
# -----------------------------
# SIDEBAR: ADD PATIENT
# -----------------------------
st.sidebar.header("➕ Add New Patient")

with st.sidebar.form("add_patient_form", clear_on_submit=True):

    first_name = st.text_input("First Name")
    last_name = st.text_input("Last Name")
    mrn = st.text_input("MRN")
    insurance = st.text_input("Insurance")
    city = st.text_input("City")

    submitted = st.form_submit_button("Add Patient")

    if submitted and first_name and last_name:

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        c.execute("""
            INSERT INTO patients
            (first_name, last_name, mrn, insurance, city, home_health, last_updated)
            VALUES (?,?,?,?,?,1,?)
        """, (first_name, last_name, mrn, insurance, city, now))

        conn.commit()

        log_action(None, "CREATE_PATIENT", f"{first_name} {last_name}")

        safe_rerun()



    # -----------------------------
    # RESET PASSWORD SECTION
    # -----------------------------
    st.sidebar.markdown("### 🔄 Reset Password")

    users_df = pd.read_sql_query("SELECT username FROM users", conn)

    selected_user = st.selectbox(
        "User",
        users_df["username"].tolist(),
        key="reset_user_select"
    )

    new_pass_reset = st.text_input(
        "New Password",
        type="password",
        key="reset_password_input"
    )

    if st.button("Reset Password", key="reset_password_btn"):

        if new_pass_reset:

            c.execute(
                "UPDATE users SET password=? WHERE username=?",
                (hash_password(new_pass_reset), selected_user)
            )
            conn.commit()

            st.success("Password updated")
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
# PATIENT CARDS (INTEGRATED VERSION)
# -----------------------------

# Ensure session state exists
if "archive_confirm" not in st.session_state:
    st.session_state["archive_confirm"] = None

cols = st.columns(3)

for i, p in patients.iterrows():
    overdue = is_overdue(p["last_updated"])
    color = "#ffd6d6" if overdue else "#d9f7d9"

    with cols[i % 3]:

        # Initialize toggle
        if f"open_{p['id']}" not in st.session_state:
            st.session_state[f"open_{p['id']}"] = False

        # Card click toggles
        if st.button(
            f"{p['first_name']} {p['last_name']}",
            key=f"toggle_{p['id']}_{i}",
            use_container_width=True
        ):
            st.session_state[f"open_{p['id']}"] = not st.session_state[f"open_{p['id']}"]
            safe_rerun()

        # Card display
        st.markdown(f"""
        <div style="
            padding:12px;
            background:{color};
            border-radius:12px;
            border:1px solid #ddd;
        ">
            <div style="font-size:18px;font-weight:700;">
                {p['first_name']} {p['last_name']}
            </div>
            <div style="margin-top:6px;font-size:13px;">
                <b>MRN:</b> {p['mrn']}<br>
                <b>City:</b> {p['city']}<br>
                <b>Last Update:</b> {p['last_updated']}
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Expanded view
        if st.session_state[f"open_{p['id']}"]:
            st.markdown("### 📝 Notes")

            notes = load_notes(p["id"])
            for _, n in notes.iterrows():
                st.write(f"{n['created_at']} — {n['note']}")

            # Add note form
            with st.form(f"note_form_{p['id']}", clear_on_submit=True):
                new_note = st.text_area("Add note")
                submitted = st.form_submit_button("➕ Add Note")
                if submitted and new_note.strip():
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    c.execute(
                        "INSERT INTO notes (patient_id, note, created_at) VALUES (?,?,?)",
                        (p["id"], new_note, now)
                    )
                    c.execute(
                        "UPDATE patients SET last_updated=? WHERE id=?",
                        (now, p["id"])
                    )
                    conn.commit()
                    log_action(p["id"], "ADD_NOTE", new_note)
                    safe_rerun()

        # Archive (admin only)
        if user["role"] == "admin":
            if st.session_state.get("archive_confirm") == p["id"]:
                st.warning(f"Archive {p['first_name']} {p['last_name']}?")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Yes", key=f"archive_yes_{p['id']}_{i}"):
                        c.execute(
                            "UPDATE patients SET archived=1 WHERE id=?",
                            (p["id"],)
                        )
                        conn.commit()
                        log_action(p["id"], "ARCHIVE", "archived")
                        st.session_state["archive_confirm"] = None
                        safe_rerun()
                with c2:
                    if st.button("No", key=f"archive_no_{p['id']}_{i}"):
                        st.session_state["archive_confirm"] = None
                        safe_rerun()
            else:
                if st.button("Archive", key=f"archive_btn_{p['id']}_{i}"):
                    st.session_state["archive_confirm"] = p["id"]
                    safe_rerun()
# -----------------------------
# SELECTED PATIENT PANEL
# -----------------------------
selected_id = st.session_state.get("selected_patient_id")

if selected_id:

    patient_df = pd.read_sql_query(
        "SELECT * FROM patients WHERE id=?",
        conn,
        params=(selected_id,)
    )

    if not patient_df.empty:
        patient = patient_df.iloc[0]

        st.markdown("---")
        st.subheader(f"📋 {patient['first_name']} {patient['last_name']}")

        # INFO CARDS
        col1, col2, col3 = st.columns(3)

        with col1:
            st.info(f"""
**Patient Info**

Name: {patient['first_name']} {patient['last_name']}
MRN: {patient['mrn']}
City: {patient['city']}
""")

        with col2:
            st.success(f"""
**Insurance**

{patient['insurance']}
""")

        with col3:
            st.warning(f"""
**Status**

Last Updated: {patient['last_updated']}
""")

        # NOTES
        notes = load_notes(selected_id)

        st.markdown("### 📝 Notes")

        for _, n in notes.iterrows():
            st.write(f"{n['created_at']} — {n['note']}")

        new_note = st.text_area("Add note")

        if st.button("➕ Add Note", key=f"add_note_{selected_id}"):
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            c.execute(
                "INSERT INTO notes (patient_id, note, created_at) VALUES (?,?,?)",
                (selected_id, new_note, now)
            )

            c.execute(
                "UPDATE patients SET last_updated=? WHERE id=?",
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
