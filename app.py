# app.py
import streamlit as st
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, datetime, timedelta
from email.message import EmailMessage
import smtplib
import pandas as pd
from io import BytesIO
from st_aggrid import AgGrid, GridOptionsBuilder
from streamlit_calendar import calendar

# ---------- Page config & styling ----------
st.set_page_config(page_title="OFFTRACKER", layout="wide", page_icon="🗓️")
st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; }
    .app-header { font-size:28px; font-weight:700; margin-bottom: 8px; }
    .card { padding: 12px; border-radius: 12px; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
    </style>
""", unsafe_allow_html=True)

# ---------- DB ----------
@st.cache_resource
def get_db():
    uri = st.secrets["mongo"]["uri"]
    client = MongoClient(uri)
    db = client.get_database("offtracker")
    return db

db = get_db()
users_col = db["users"]
admins_col = db["admins"]
schedules_col = db["schedules"]

# ---------- Auth & utils ----------
def register_user(username, name, password):
    if users_col.find_one({"username": username}) or admins_col.find_one({"username": username}):
        return False, "Username already exists"
    users_col.insert_one({
        "username": username,
        "name": name,
        "password": generate_password_hash(password)
    })
    return True, "Registered successfully"

def authenticate_user(username, password, admin=False):
    col = admins_col if admin else users_col
    user = col.find_one({"username": username})
    if not user:
        return False, None
    if check_password_hash(user["password"], password):
        return True, user
    return False, None

def compute_off_days(date_list):
    if not date_list:
        return []
    dates = sorted(set(date_list))
    runs = []
    start = dates[0]
    end = dates[0]
    for d in dates[1:]:
        if d == end + timedelta(days=1):
            end = d
        else:
            runs.append((start, end))
            start = d
            end = d
    runs.append((start, end))
    off_days = []
    for s, e in runs:
        L = (e - s).days + 1
        groups = L // 5
        if groups > 0:
            days_to_add = 2 * groups
            for i in range(days_to_add):
                off_days.append(e + timedelta(days=i+1))
    return sorted(set(off_days))

def send_schedule_email(trainer_name, trainer_username, course, training_dates, off_days):
    try:
        owner = st.secrets["email"]["owner"]
        sender = st.secrets["email"]["username"]
        smtp_server = st.secrets["email"]["smtp_server"]
        smtp_port = int(st.secrets["email"]["smtp_port"])
        smtp_pw = st.secrets["email"]["password"]

        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = owner
        msg["Subject"] = f"[OFFTRACKER] New schedule: {trainer_name} ({trainer_username})"
        lines = [
            f"Trainer: {trainer_name} ({trainer_username})",
            f"Course: {course}",
            "",
            "Training days:"
        ]
        lines += [f" - {d}" for d in training_dates]
        lines += ["", "Off days (earned):"]
        lines += [f" - {d}" for d in off_days]
        msg.set_content("\n".join(lines))

        with smtplib.SMTP_SSL(smtp_server, smtp_port) as smtp:
            smtp.login(sender, smtp_pw)
            smtp.send_message(msg)
        return True, "Email sent"
    except Exception as e:
        return False, str(e)

# ---------- Session ----------
if "user" not in st.session_state:
    st.session_state["user"] = None
if "is_admin" not in st.session_state:
    st.session_state["is_admin"] = False
if "selected_blocks" not in st.session_state:
    st.session_state["selected_blocks"] = []
if "calendar_selection_preview" not in st.session_state:
    st.session_state["calendar_selection_preview"] = []

# ---------- Header ----------
st.markdown('<div class="app-header">OFFTRACKER — Trainer Off-Day Manager</div>', unsafe_allow_html=True)
st.markdown("Register, record training days via calendar, auto-calc off-days, send notifications to owner, and export schedules for HR/payroll.")
st.write("---")

# ---------- Landing ----------
col1, col2 = st.columns([1, 2])
with col1:
    role = st.radio("I am a:", ("Existing user", "New user", "Admin"))
with col2:
    st.empty()

# ---------- Register ----------
if role == "New user":
    st.header("Register as a Trainer")
    with st.form("register_form"):
        name = st.text_input("Full name")
        username = st.text_input("Username (unique)")
        password = st.text_input("Password", type="password")
        password2 = st.text_input("Confirm Password", type="password")
        register_submit = st.form_submit_button("Register")
    if register_submit:
        if not (name and username and password):
            st.error("Please complete all fields.")
        elif password != password2:
            st.error("Passwords do not match.")
        else:
            ok, msg = register_user(username.strip(), name.strip(), password)
            if ok:
                st.success(msg + " — now use 'Existing user' to log in.")
            else:
                st.error(msg)

# ---------- Login: Existing user ----------
if role == "Existing user":
    st.header("Trainer Login")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        login_submit = st.form_submit_button("Login")
    if login_submit:
        ok, user = authenticate_user(username.strip(), password, admin=False)
        if ok:
            st.session_state["user"] = user
            st.session_state["is_admin"] = False
            st.success(f"Welcome, {user['name']}!")
        else:
            st.error("Invalid credentials. Try again or register as a new user.")

# ---------- Admin Login ----------
if role == "Admin":
    st.header("Admin Login")
    with st.form("admin_login_form"):
        username = st.text_input("Admin username")
        password = st.text_input("Admin password", type="password")
        admin_login_submit = st.form_submit_button("Login as Admin")
    if admin_login_submit:
        ok, user = authenticate_user(username.strip(), password, admin=True)
        if ok:
            st.session_state["user"] = user
            st.session_state["is_admin"] = True
            st.success(f"Admin logged in as {user['name']}")
        else:
            st.error("Invalid admin credentials.")

# ---------- Dashboard ----------
if st.session_state["user"]:
    user = st.session_state["user"]
    is_admin = st.session_state["is_admin"]
    st.write("---")
    if is_admin:
        # Admin UI
        st.header("Admin Dashboard")
        colA, colB, colC, colD = st.columns(4)
        total_trainers = users_col.count_documents({})
        total_schedules = schedules_col.count_documents({})
        total_off_earned = sum(len(s.get("off_days_earned", [])) for s in schedules_col.find())
        total_off_taken = sum(len(s.get("off_days_taken", [])) for s in schedules_col.find())
        total_unused = total_off_earned - total_off_taken
        colA.metric("Total Trainers", total_trainers)
        colB.metric("Total Schedules", total_schedules)
        colC.metric("Off Days Earned", total_off_earned)
        colD.metric("Unused Off Days", total_unused)

        st.markdown("### All schedules")
        rows = []
        for s in schedules_col.find().sort("created_at", -1):
            rows.append({
                "id": str(s.get("_id")),
                "Trainer": s.get("trainer_name"),
                "Username": s.get("trainer_username"),
                "Course": s.get("course"),
                "Training Days Count": len(s.get("training_days", [])),
                "Off Earned (count)": len(s.get("off_days_earned", [])),
                "Off Taken (count)": len(s.get("off_days_taken", [])),
                "Unused Off Days": len(s.get("off_days_earned", [])) - len(s.get("off_days_taken", [])),
                "Created At": s.get("created_at").isoformat() if s.get("created_at") else ""
            })
        df_all = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["id", "Trainer"])
        gb = GridOptionsBuilder.from_dataframe(df_all)
        gb.configure_default_column(resizable=True, filter=True, sortable=True)
        gb.configure_pagination(paginationAutoPageSize=True)
        AgGrid(df_all, gridOptions=gb.build(), theme="streamlit")

        st.markdown("### Export for Payroll / HR")
        if not df_all.empty:
            csv_bytes = df_all.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Download CSV", data=csv_bytes, file_name="offtracker_schedules.csv", mime="text/csv")
            towrite = BytesIO()
            with pd.ExcelWriter(towrite, engine="openpyxl") as writer:
                df_all.to_excel(writer, index=False, sheet_name="Schedules")
            st.download_button("⬇️ Download Excel", data=towrite.getvalue(), file_name="offtracker_schedules.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            st.info("No schedules yet to export.")

        st.markdown("### Inspect / Modify a trainer's schedules")
        sel_username = st.text_input("Enter trainer username to inspect", value="")
        if sel_username:
            docs = list(schedules_col.find({"trainer_username": sel_username}).sort("created_at", -1))
            if not docs:
                st.info("No schedules for this username.")
            else:
                for doc in docs:
                    st.write("---")
                    st.markdown(f"**Course:** {doc['course']} — created: {doc.get('created_at')}")
                    st.write("Training days:", doc.get("training_days", []))
                    st.write("Off (earned):", doc.get("off_days_earned", []))
                    st.write("Off (taken):", doc.get("off_days_taken", []))
                    st.write("Unused:", len(doc.get("off_days_earned", [])) - len(doc.get("off_days_taken", [])))
                    taken = set(doc.get("off_days_taken", []))
                    new_taken = []
                    for od in doc.get("off_days_earned", []):
                        checked = od in taken
                        ck = st.checkbox(f"{od}", value=checked, key=f"{str(doc['_id'])}_{od}")
                        if ck:
                            new_taken.append(od)
                    if st.button("Save taken off-days for this schedule", key=f"save_{str(doc['_id'])}"):
                        schedules_col.update_one({"_id": doc["_id"]}, {"$set": {"off_days_taken": new_taken}})
                        st.success("Saved taken off-days for schedule.")

    else:
        # Trainer UI
        st.header(f"Trainer: {user['name']} (@{user['username']})")
        menu = st.selectbox("Choose action", ("Enter new schedule", "View my schedules", "View off days"))

        if menu == "Enter new schedule":
            st.subheader("Create schedule via calendar (select range, then 'Add selection' to accumulate)")
            col1, col2 = st.columns([2, 1])
            with col1:
                st.markdown("#### Pick a date range on the calendar (drag or click)")
                calendar_options = {"initialView": "dayGridMonth", "selectable": True, "editable": False}
                cal = calendar(events=[], options=calendar_options, key="trainer_calendar")
                preview_block = []
                if cal and "select" in cal:
                    start_iso = cal["select"]["start"]
                    end_iso = cal["select"]["end"]
                    start_date = datetime.fromisoformat(start_iso).date()
                    end_date = datetime.fromisoformat(end_iso).date() - timedelta(days=1)
                    preview_block = (start_date, end_date)
                    st.session_state["calendar_selection_preview"] = [start_date, end_date]
                if preview_block:
                    st.info(f"Preview selection: {preview_block[0].isoformat()} → {preview_block[1].isoformat()}")
                if st.button("Add selection"):
                    if st.session_state["calendar_selection_preview"]:
                        s, e = st.session_state["calendar_selection_preview"]
                        st.session_state["selected_blocks"].append((s, e))
                        st.session_state["calendar_selection_preview"] = []
                        st.success("Selection added.")
                if st.button("Clear all selections"):
                    st.session_state["selected_blocks"] = []
                    st.success("Cleared selected blocks.")
            with col2:
                st.markdown("#### Current blocks")
                if not st.session_state["selected_blocks"]:
                    st.info("No selections yet.")
                else:
                    to_remove = None
                    for i, (s, e) in enumerate(st.session_state["selected_blocks"]):
                        st.write(f"Block {i+1}: {s.isoformat()} → {e.isoformat()}")
                        if st.button(f"Remove block {i+1}", key=f"remove_{i}"):
                            to_remove = i
                    if to_remove is not None:
                        st.session_state["selected_blocks"].pop(to_remove)
                        st.experimental_rerun()

            # Aggregate
            selected_dates_set = set()
            for s, e in st.session_state["selected_blocks"]:
                cur = s
                while cur <= e:
                    selected_dates_set.add(cur)
                    cur += timedelta(days=1)
            selected_dates = sorted(selected_dates_set)
            st.markdown("#### Final training days (aggregated)")
            st.write([d.isoformat() for d in selected_dates])

            course = st.text_input("Course name")
            if st.button("Submit schedule"):
                if not course:
                    st.error("Enter course name.")
                elif not selected_dates:
                    st.error("Add at least one date block.")
                else:
                    off_days = compute_off_days(selected_dates)
                    doc = {
                        "trainer_username": user["username"],
                        "trainer_name": user["name"],
                        "course": course,
                        "training_days": [d.isoformat() for d in selected_dates],
                        "off_days_earned": [d.isoformat() for d in off_days],
                        "off_days_taken": [],
                        "created_at": datetime.utcnow()
                    }
                    schedules_col.insert_one(doc)
                    ok, msg = send_schedule_email(user["name"], user["username"], course,
                                                  [d.isoformat() for d in selected_dates],
                                                  [d.isoformat() for d in off_days])
                    if ok:
                        st.success("Schedule saved and email sent to owner.")
                    else:
                        st.warning("Schedule saved but email failed: " + msg)
                    st.session_state["selected_blocks"] = []

        elif menu == "View my schedules":
            st.subheader("Your schedules")
            docs = list(schedules_col.find({"trainer_username": user["username"]}).sort("created_at", -1))
            if not docs:
                st.info("No schedules found.")
            else:
                for doc in docs:
                    with st.expander(f"{doc['course']} — created {doc.get('created_at')}"):
                        st.write("Training days:", doc.get("training_days", []))
                        st.write("Off (earned):", doc.get("off_days_earned", []))
                        st.write("Off (taken):", doc.get("off_days_taken", []))
                        st.write("Unused:", len(doc.get("off_days_earned", [])) - len(doc.get("off_days_taken", [])))
                        taken = set(doc.get("off_days_taken", []))
                        new_taken = []
                        for od in doc.get("off_days_earned", []):
                            checked = od in taken
                            ck = st.checkbox(f"{od}", value=checked, key=f"user_{str(doc['_id'])}_{od}")
                            if ck:
                                new_taken.append(od)
                        if st.button("Save taken off-days for this schedule", key=f"user_save_{str(doc['_id'])}"):
                            schedules_col.update_one({"_id": doc["_id"]}, {"$set": {"off_days_taken": new_taken}})
                            st.success("Saved")

        elif menu == "View off days":
            st.subheader("Off-day summary")
            docs = list(schedules_col.find({"trainer_username": user["username"]}))
            total_earned = sum(len(d.get("off_days_earned", [])) for d in docs)
            total_taken = sum(len(d.get("off_days_taken", [])) for d in docs)
            total_unused = total_earned - total_taken
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Earned", total_earned)
            c2.metric("Total Taken", total_taken)
            c3.metric("Total Unused", total_unused)
            st.markdown("Details per schedule")
            for d in docs:
                st.write("---")
                st.write(f"Course: {d['course']}")
                st.write("Earned:", d.get("off_days_earned", []))
                st.write("Taken:", d.get("off_days_taken", []))
                st.write("Unused:", len(d.get("off_days_earned", [])) - len(d.get("off_days_taken", [])))

    st.write("---")
    if st.button("Logout"):
        st.session_state.clear()
        st.experimental_rerun()
