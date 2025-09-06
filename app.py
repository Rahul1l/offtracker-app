import streamlit as st
from datetime import datetime, timedelta
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from streamlit_calendar import calendar
import pandas as pd
from io import BytesIO

# -------------------
# Page Config
# -------------------
st.set_page_config(page_title="OFFTRACKER", page_icon="📊", layout="centered")

# -------------------
# Custom Styling
# -------------------
st.markdown("""
    <style>
    body {
        background-color: #f8f9fa;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    .main-title {
        font-size: 36px;
        font-weight: 700;
        color: #2c3e50;
        text-align: center;
        margin-bottom: 20px;
    }
    .section-title {
        font-size: 24px;
        font-weight: 600;
        color: #34495e;
        margin-top: 20px;
        margin-bottom: 10px;
    }
    .stButton button {
        width: 100%;
        background-color: #2c3e50 !important;
        color: white !important;
        border-radius: 8px;
        padding: 0.6em 0 !important;
        font-weight: 600;
    }
    .stTextInput input, .stPasswordInput input {
        border-radius: 8px !important;
        padding: 0.6em !important;
        border: 1px solid #ced4da !important;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown("<div class='main-title'>📊 OFFTRACKER</div>", unsafe_allow_html=True)

# -------------------
# DB Connection
# -------------------
mongo_client = MongoClient(st.secrets["mongo"]["uri"])
db = mongo_client["offtracker"]
users_col = db["users"]
admins_col = db["admins"]
schedules_col = db["schedules"]

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
def compute_off_days(training_days):
    off_days = []
    training_days = sorted([datetime.fromisoformat(d) for d in training_days])
    count = 0
    for i in range(len(training_days)):
        if i > 0 and training_days[i] == training_days[i-1] + timedelta(days=1):
            count += 1
        else:
            count = 1
        if count == 5:
            off1 = training_days[i] + timedelta(days=1)
            off2 = training_days[i] + timedelta(days=2)
            off_days.extend([off1, off2])
            count = 0
    return [d.date().isoformat() for d in off_days]

# -------------------
# Session Init
# -------------------
if "page" not in st.session_state:
    st.session_state["page"] = "home"
if "user" not in st.session_state:
    st.session_state["user"] = None
if "admin" not in st.session_state:
    st.session_state["admin"] = None

# -------------------
# Navbar
# -------------------
def navbar():
    cols = st.columns(4)
    if st.session_state["user"]:
        if cols[0].button("🏠 Dashboard"):
            st.session_state["page"] = "user_dashboard"
        if cols[1].button("🚪 Logout"):
            st.session_state["user"] = None
            st.session_state["page"] = "home"

    elif st.session_state["admin"]:
        if cols[0].button("🏠 Admin Dashboard"):
            st.session_state["page"] = "admin_dashboard"
        if cols[1].button("🚪 Logout"):
            st.session_state["admin"] = None
            st.session_state["page"] = "home"

    else:
        if cols[0].button("🔑 User Login"):
            st.session_state["page"] = "login"
        if cols[1].button("🆕 Register"):
            st.session_state["page"] = "register"
        if cols[2].button("👨‍💼 Admin Login"):
            st.session_state["page"] = "admin_login"

navbar()

# -------------------
# User Register
# -------------------
if st.session_state["page"] == "register":
    st.markdown("<div class='section-title'>🆕 New User Registration</div>", unsafe_allow_html=True)
    with st.form("register_form"):
        name = st.text_input("Full Name")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        confirm_password = st.text_input("Confirm Password", type="password")
        submit = st.form_submit_button("Register")

    if submit:
        if password != confirm_password:
            st.error("❌ Passwords do not match.")
        elif users_col.find_one({"username": username}):
            st.error("⚠️ Username already exists.")
        else:
            users_col.insert_one({
                "name": name,
                "username": username,
                "password": generate_password_hash(password)
            })
            st.success("✅ Registered successfully! You can now log in.")

# -------------------
# User Login
# -------------------
elif st.session_state["page"] == "login":
    st.markdown("<div class='section-title'>🔑 User Login</div>", unsafe_allow_html=True)
    with st.form("user_login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")

    if submit:
        user = users_col.find_one({"username": username})
        if user and check_password_hash(user["password"], password):
            st.session_state["user"] = user
            st.session_state["page"] = "user_dashboard"
        else:
            st.error("❌ Invalid username or password")

# -------------------
# Admin Login
# -------------------
elif st.session_state["page"] == "admin_login":
    st.markdown("<div class='section-title'>👨‍💼 Admin Login</div>", unsafe_allow_html=True)
    with st.form("admin_login_form"):
        admin_user = st.text_input("Admin Username")
        admin_pass = st.text_input("Admin Password", type="password")
        submit = st.form_submit_button("Login as Admin")

    if submit:
        admin = admins_col.find_one({"username": admin_user})
        if admin and check_password_hash(admin["password"], admin_pass):
            st.session_state["admin"] = admin
            st.session_state["page"] = "admin_dashboard"
        else:
            st.error("❌ Invalid admin credentials")

# -------------------
# User Dashboard
# -------------------
elif st.session_state["page"] == "user_dashboard" and st.session_state["user"]:
    st.markdown(f"### 👋 Welcome, {st.session_state['user']['name']}!")

    menu = st.selectbox("Menu", ["📅 Enter New Schedule", "📖 View Existing Schedule", "🛌 View Off Days"])

    # --- Enter Schedule ---
    if menu == "📅 Enter New Schedule":
        trainer_name = st.session_state["user"]["name"]
        course = st.text_input("Course name")
        st.markdown("#### Select training days from calendar")
        calendar_options = {"initialView": "dayGridMonth", "selectable": True}
        cal = calendar(events=[], options=calendar_options, key="calendar_ui")
        selected_dates = []
        if cal and "select" in cal:
            start = datetime.fromisoformat(cal["select"]["start"]).date()
            end = datetime.fromisoformat(cal["select"]["end"]).date() - timedelta(days=1)
            while start <= end:
                selected_dates.append(start.isoformat())
                start += timedelta(days=1)
        st.write("📅 Selected training days:", selected_dates)

        if st.button("Submit Schedule"):
            if not course or not selected_dates:
                st.error("⚠️ Please fill course name and select dates.")
            else:
                off_days = compute_off_days(selected_dates)
                schedules_col.insert_one({
                    "trainer_username": st.session_state["user"]["username"],
                    "trainer_name": trainer_name,
                    "course": course,
                    "training_days": selected_dates,
                    "off_days_earned": off_days,
                    "created_at": datetime.utcnow()
                })
                ok, msg = send_schedule_email(trainer_name, st.session_state["user"]["username"], course, selected_dates, off_days)
                if ok:
                    st.success("✅ Schedule saved & email sent.")
                else:
                    st.warning(f"⚠️ Schedule saved, email failed: {msg}")

    # --- View Schedule ---
    elif menu == "📖 View Existing Schedule":
        schedules = list(schedules_col.find({"trainer_username": st.session_state["user"]["username"]}))
        if not schedules:
            st.info("ℹ️ No schedules found.")
        else:
            for sch in schedules:
                st.write(f"**Course**: {sch['course']}")
                st.write(f"**Training Days**: {', '.join(sch['training_days'])}")
                st.write(f"**Off Days**: {', '.join(sch['off_days_earned'])}")
                if st.button(f"❌ Delete {sch['course']}", key=str(sch["_id"])):
                    schedules_col.delete_one({"_id": sch["_id"]})
                    st.success(f"Deleted schedule for {sch['course']}")
                    st.experimental_rerun()
                st.write("---")

            # Export schedules to Excel
            df = pd.DataFrame(schedules)
            df.drop(columns=["_id"], inplace=True)
            output = BytesIO()
            df.to_excel(output, index=False, engine="openpyxl")
            st.download_button(
                "📥 Download Schedules (Excel)",
                output.getvalue(),
                file_name="user_schedules.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    # --- View Off Days ---
    elif menu == "🛌 View Off Days":
        schedules = list(schedules_col.find({"trainer_username": st.session_state["user"]["username"]}))
        total_off = sum([len(sch["off_days_earned"]) for sch in schedules])
        st.info(f"🛌 Total unused off days: {total_off}")

# -------------------
# Admin Dashboard
# -------------------
elif st.session_state["page"] == "admin_dashboard" and st.session_state["admin"]:
    st.markdown(f"### 👨‍💼 Welcome, Admin {st.session_state['admin']['name']}!")
    schedules = list(schedules_col.find())
    if not schedules:
        st.info("ℹ️ No schedules submitted yet.")
    else:
        for sch in schedules:
            st.write(f"👨‍🏫 **{sch['trainer_name']}** ({sch['trainer_username']})")
            st.write(f"📘 Course: {sch['course']}")
            st.write(f"📅 Training Days: {', '.join(sch['training_days'])}")
            st.write(f"🛌 Off Days: {', '.join(sch['off_days_earned'])}")
            if st.button(f"❌ Delete {sch['course']} ({sch['trainer_username']})", key=str(sch["_id"])):
                schedules_col.delete_one({"_id": sch["_id"]})
                st.success(f"Deleted schedule for {sch['course']} by {sch['trainer_name']}")
                st.experimental_rerun()
            st.write("---")

        # Export all schedules to Excel
        df = pd.DataFrame(schedules)
        df.drop(columns=["_id"], inplace=True)
        output = BytesIO()
        df.to_excel(output, index=False, engine="openpyxl")
        st.download_button(
            "📥 Download All Schedules (Excel)",
            output.getvalue(),
            file_name="all_schedules.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
