# app.py
import streamlit as st
from datetime import datetime, timedelta, date
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# -------------------
# Page Config & Styling
# -------------------
st.set_page_config(page_title="OFFTRACKER", page_icon="📊", layout="centered")

st.markdown(
    """
    <style>
    body { background-color: #f8f9fa; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
    .main-title { font-size: 36px; font-weight: 700; color: #2c3e50; text-align: center; margin-bottom: 12px; }
    .section-title { font-size: 22px; font-weight: 600; color: #34495e; margin-top: 14px; margin-bottom: 8px; }
    .stButton button { width: 100%; background-color: #2c3e50 !important; color: white !important; border-radius: 8px; padding: 0.6em 0 !important; font-weight: 600; }
    .stTextInput input, .stPasswordInput input { border-radius: 8px !important; padding: 0.6em !important; border: 1px solid #ced4da !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown("<div class='main-title'>📊 OFFTRACKER</div>", unsafe_allow_html=True)

# -------------------
# Initialize session state
# -------------------
if "user" not in st.session_state:
    st.session_state.user = None
if "admin" not in st.session_state:
    st.session_state.admin = None
if "temp_dates" not in st.session_state:
    st.session_state.temp_dates = []

# -------------------
# DB Connection
# -------------------
try:
    mongo_client = MongoClient(st.secrets["mongo"]["uri"])
    db = mongo_client["offtracker"]
    users_col = db["users"]
    admins_col = db["admins"]
    schedules_col = db["schedules"]
except Exception as e:
    st.error("⚠️ Could not connect to MongoDB. Check st.secrets['mongo']['uri'].")
    st.stop()

# -------------------
# Email Sender
# -------------------
def send_schedule_email(name, username, course, training_days, off_days):
    try:
        msg = MIMEMultipart()
        msg["From"] = st.secrets["email"]["sender"]
        msg["To"] = st.secrets["email"]["receiver"]
        msg["Subject"] = f"New Schedule Submitted - {name}"

        body = f"""
Trainer: {name} ({username})
Course: {course}
Training Days: {', '.join(training_days)}
Off Days: {', '.join(off_days)}
"""
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(st.secrets["email"]["sender"], st.secrets["email"]["password"])
            server.sendmail(msg["From"], msg["To"], msg.as_string())
        return True, "Email sent"
    except Exception as e:
        return False, str(e)

# -------------------
# Off Days Logic
# -------------------
def compute_off_days(training_days_iso):
    training_dates = sorted([datetime.fromisoformat(d).date() for d in training_days_iso])
    off_days = []
    count = 0
    for i in range(len(training_dates)):
        if i > 0 and training_dates[i] == training_dates[i - 1] + timedelta(days=1):
            count += 1
        else:
            count = 1
        if count == 5:
            off1 = training_dates[i] + timedelta(days=1)
            off2 = training_dates[i] + timedelta(days=2)
            off_days.extend([off1, off2])
            count = 0
    return [d.isoformat() for d in off_days]

# -------------------
# Helpers
# -------------------
def logout():
    st.session_state.user = None
    st.session_state.admin = None
    st.session_state.temp_dates = []

def add_temp_date(d: date):
    if d not in st.session_state.temp_dates:
        st.session_state.temp_dates.append(d)
        st.session_state.temp_dates.sort()
    else:
        st.warning("Date already added.")

def remove_temp_date(idx: int):
    if 0 <= idx < len(st.session_state.temp_dates):
        st.session_state.temp_dates.pop(idx)

# -------------------
# Navigation Tabs
# -------------------
tab_choice = st.radio(
    "Choose an option",
    ["🔑 Login as User", "🆕 Register as New User", "👨‍💼 Admin Login"],
    horizontal=True,
    label_visibility="collapsed",
)

# -------------------
# Register New User
# -------------------
if tab_choice == "🆕 Register as New User":
    st.markdown("<div class='section-title'>🆕 New User Registration</div>", unsafe_allow_html=True)
    with st.form("register_form", clear_on_submit=False):
        name = st.text_input("Full Name")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        confirm_password = st.text_input("Confirm Password", type="password")
        submitted = st.form_submit_button("Register")
    if submitted:
        if not name or not username or not password or not confirm_password:
            st.error("⚠️ Please fill all fields.")
        elif password != confirm_password:
            st.error("❌ Passwords do not match.")
        elif users_col.find_one({"username": username}):
            st.error("⚠️ Username already exists.")
        else:
            users_col.insert_one(
                {"name": name, "username": username, "password": generate_password_hash(password)}
            )
            st.success("✅ Registered successfully! You can now log in.")

# -------------------
# User Login
# -------------------
elif tab_choice == "🔑 Login as User":
    st.markdown("<div class='section-title'>🔑 User Login</div>", unsafe_allow_html=True)
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
    if submitted:
        user = users_col.find_one({"username": username})
        if user and check_password_hash(user["password"], password):
            st.session_state.user = {"username": user["username"], "name": user["name"]}
            st.success(f"✅ Welcome back, {user['name']}!")
        else:
            st.error("❌ Invalid username or password")

# -------------------
# Admin Login
# -------------------
elif tab_choice == "👨‍💼 Admin Login":
    st.markdown("<div class='section-title'>👨‍💼 Admin Login</div>", unsafe_allow_html=True)
    with st.form("admin_form"):
        admin_user = st.text_input("Admin Username")
        admin_pass = st.text_input("Admin Password", type="password")
        submitted = st.form_submit_button("Login as Admin")
    if submitted:
        admin = admins_col.find_one({"username": admin_user})
        if admin and check_password_hash(admin["password"], admin_pass):
            st.session_state.admin = {"username": admin["username"], "name": admin["name"]}
            st.success(f"✅ Welcome, Admin {admin['name']}!")
        else:
            st.error("❌ Invalid admin credentials")

# -------------------
# User Dashboard
# -------------------
if st.session_state.user:
    user = st.session_state.user
    st.markdown("<div class='section-title'>📋 Trainer Dashboard</div>", unsafe_allow_html=True)
    st.write(f"Signed in as **{user['name']}** ({user['username']})")
    if st.button("Logout"):
        logout()
        st.experimental_rerun()

    menu = st.selectbox("Menu", ["📅 Add New Schedule", "📖 View My Schedules", "🛌 View Off Days"])

    # --- Add New Schedule ---
    if menu == "📅 Add New Schedule":
        st.markdown("#### Add Schedule: Pick dates and submit once")
        course = st.text_input("Course name")

        col1, col2 = st.columns([2, 1])
        with col1:
            date_to_add = st.date_input("Pick a training date", value=date.today())
        with col2:
            if st.button("➕ Add Date"):
                add_temp_date(date_to_add)

        if st.session_state.temp_dates:
            st.write("**Selected Training Days:**")
            for idx, d in enumerate(st.session_state.temp_dates):
                cols = st.columns([6, 1])
                cols[0].write(f"- {d.isoformat()}")
                if cols[1].button("❌", key=f"remove_{idx}"):
                    remove_temp_date(idx)
                    st.experimental_rerun()
        else:
            st.info("No dates added yet.")

        if st.button("Clear All Dates"):
            st.session_state.temp_dates = []

        if st.button("✅ Submit Schedule"):
            if not course:
                st.error("⚠️ Please provide a course name.")
            elif not st.session_state.temp_dates:
                st.error("⚠️ Please add at least one training date.")
            else:
                iso_dates = [d.isoformat() for d in st.session_state.temp_dates]
                off_days = compute_off_days(iso_dates)
                schedules_col.insert_one({
                    "trainer_username": user["username"],
                    "trainer_name": user["name"],
                    "course": course,
                    "training_days": iso_dates,
                    "off_days_earned": off_days,
                    "created_at": datetime.utcnow()
                })
                ok, msg = send_schedule_email(user["name"], user["username"], course, iso_dates, off_days)
                if ok:
                    st.success("✅ Schedule saved & email sent.")
                else:
                    st.warning(f"⚠️ Schedule saved, email failed: {msg}")
                st.session_state.temp_dates = []

    # --- View My Schedules ---
    elif menu == "📖 View My Schedules":
        schedules = list(schedules_col.find({"trainer_username": user["username"]}).sort("created_at", -1))
        if not schedules:
            st.info("ℹ️ No schedules found.")
        else:
            for sch in schedules:
                st.write(f"**Course**: {sch.get('course','-')}")
                st.write(f"📅 Training Days: {', '.join(sch.get('training_days', []))}")
                st.write(f"🛌 Off Days: {', '.join(sch.get('off_days_earned', [])) or 'None'}")
                if sch.get("created_at"):
                    st.caption(f"Submitted on {sch['created_at'].strftime('%Y-%m-%d %H:%M:%S')}")
                st.write("---")

    # --- View Off Days ---
    elif menu == "🛌 View Off Days":
        schedules = list(schedules_col.find({"trainer_username": user["username"]}))
        if not schedules:
            st.info("ℹ️ You don’t have any schedules yet.")
        else:
            total_off = sum([len(sch.get("off_days_earned", [])) for sch in schedules])
            st.success(f"🛌 Total earned off days: {total_off}")
            st.write("### Breakdown by course")
            for sch in schedules:
                st.write(f"- {sch.get('course','-')}: {', '.join(sch.get('off_days_earned', [])) or 'None'}")

# -------------------
# Admin Dashboard
# -------------------
elif st.session_state.admin:
    admin = st.session_state.admin
    st.markdown("<div class='section-title'>🛠️ Admin Dashboard</div>", unsafe_allow_html=True)
    st.write(f"Signed in as Admin **{admin['name']}** ({admin['username']})")
    if st.button("Logout"):
        logout()
        st.experimental_rerun()

    view_mode = st.selectbox("Admin View", ["📊 All Trainer Schedules", "🔎 Search by Trainer Username"])
    if view_mode == "📊 All Trainer Schedules":
        schedules = list(schedules_col.find().sort("created_at", -1))
        if not schedules:
            st.info("ℹ️ No schedules submitted yet.")
        else:
            for sch in schedules:
                st.write(f"👨‍🏫 **{sch.get('trainer_name','-')}** ({sch.get('trainer_username','-')})")
                st.write(f"📘 Course: {sch.get('course','-')}")
                st.write(f"📅 Training Days: {', '.join(sch.get('training_days', []))}")
                st.write(f"🛌 Off Days: {', '.join(sch.get('off_days_earned', []))}")
                if sch.get("created_at"):
                    st.caption(f"Submitted: {sch['created_at'].strftime('%Y-%m-%d %H:%M:%S')}")
                st.write("---")
    elif view_mode == "🔎 Search by Trainer Username":
        username_q = st.text_input("Trainer username to search")
        if st.button("Search"):
            schedules = list(schedules_col.find({"trainer_username": username_q}))
            if not schedules:
                st.info("No schedules found for that username.")
            else:
                for sch in schedules:
                    st.write(f"**Course**: {sch.get('course','-')}")
                    st.write(f"📅 Training Days: {', '.join(sch.get('training_days', []))}")
                    st.write(f"🛌 Off Days: {', '.join(sch.get('off_days_earned', [])) or 'None'}")
                    st.write("---")
