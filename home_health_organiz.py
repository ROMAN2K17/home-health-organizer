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

    with cols[i % 3]:

        # Invisible button to make the whole card clickable
        if st.button(label=f"Select {p['first_name']} {p['last_name']}", key=card_id):
            st.session_state["selected_patient_id"] = p["id"]
            safe_rerun()

        # Visual card (styled)
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
            <h4 style="margin-bottom:5px;">
                {p['first_name']} {p['last_name']}
            </h4>
            <p><b>MRN:</b> {p['mrn']}</p>
            <p><b>Insurance:</b> {p['insurance']}</p>
            <p><b>City:</b> {p['city']}</p>
            <p><b>Last Update:</b> {p['last_updated']}</p>
            {"<p style='color:red;font-weight:bold;'>⚠ OVERDUE</p>" if overdue else ""}
        </div>
        """, unsafe_allow_html=True)

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

        # -----------------------------
        # Add Note
        # -----------------------------
        new_note = st.text_area("Add a new note", key=f"note_box_{selected_id}")

        if st.button("➕ Add Note", key=f"add_note_{selected_id}"):

            if new_note.strip():
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                c.execute(
                    "INSERT INTO notes (patient_id, note, created_at) VALUES (?, ?, ?)",
                    (selected_id, new_note, now)
                )

                c.execute(
                    "UPDATE patients SET last_updated = ? WHERE id = ?",
                    (now, selected_id)
                )

                conn.commit()

                log_action(selected_id, "ADD_NOTE", new_note)

                safe_rerun()
