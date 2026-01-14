import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 1. CONNECTION & SETUP (UPDATED) ---
@st.cache_resource
def get_db_connection():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    # Ensure you have your secrets.toml set up correctly!
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    
    # Open the sheet once and keep it open
    sheet = client.open("paytrack_db")
    return sheet

# --- 2. HELPER FUNCTIONS ---

def get_all_users_list():
    """Raw list from Google Sheets"""
    sheet = get_db_connection()
    worksheet = sheet.worksheet("Users")
    return worksheet.get_all_records()

def fetch_users_dict():
    """
    Fetches all users from Google Sheets and returns a dictionary.
    Keys are User IDs (always as strings) for fast lookup.
    """
    try:
        sheet = get_db_connection()
        rows = sheet.worksheet("Users").get_all_values()
        
        users_dict = {}
        for row in rows[1:]:
            if len(row) > 0:
                user_id = str(row[0]).strip() 
                users_dict[user_id] = {
                    "name": row[1],
                    "age": row[2],
                    "email": row[3],
                    "password": str(row[4]).strip(),
                    "role": row[5],
                    "rate": float(row[6]) if row[6] else 0.0,
                    "ot_multiplier": float(row[7]) if row[7] else 1.0,
                    "resume": row[8] if len(row) > 8 else "No Resume"
                }
        return users_dict
    except Exception as e:
        st.error(f"Database Error: {e}")
        return {}

def add_new_user(user_data):
    sheet = get_db_connection()
    worksheet = sheet.worksheet("Users")
    worksheet.append_row(user_data)

def get_attendance_logs():
    sheet = get_db_connection()
    worksheet = sheet.worksheet("Attendance")
    try:
        # Tries to get records. If sheet is empty, this often fails.
        return worksheet.get_all_records()
    except gspread.exceptions.APIError:
        # If an API error happens (likely empty sheet), return an empty list
        return []
    except Exception:
        # Fallback for other errors
        return []

def get_payroll_logs():
    sheet = get_db_connection()
    try:
        worksheet = sheet.worksheet("Payroll")
        return worksheet.get_all_records()
    except:
        # This catches "Sheet not found" OR "Empty Sheet" errors
        return []

def log_punch_in(user_id, date, time_in):
    """Creates a new open session."""
    sheet = get_db_connection()
    worksheet = sheet.worksheet("Attendance")
    log_id = int(time.time())
    # Structure: [log_id, user_id, date, in_time, out_time, hours_worked]
    worksheet.append_row([log_id, str(user_id), date, time_in, "", ""])

def log_punch_out(user_id, date, time_out):
    """Closes the currently open session."""
    sheet = get_db_connection()
    worksheet = sheet.worksheet("Attendance")
    data = worksheet.get_all_records()
    
    row_to_update = -1
    previous_in_time = ""

    # Find the row that has NO out_time
    for i, row in enumerate(data):
        if str(row['user_id']).strip() == str(user_id).strip() and row['out_time'] == "":
            row_to_update = i + 2  # +2 for header and 0-index
            previous_in_time = row['in_time']
            break
    
    if row_to_update != -1:
        try:
            fmt = "%H:%M:%S"
            t_in = datetime.strptime(str(previous_in_time), fmt)
            t_out = datetime.strptime(time_out, fmt)
            
            if t_out < t_in:
                t_out += timedelta(days=1)
                
            duration = (t_out - t_in).total_seconds() / 3600
        except:
            duration = 0.0
            
        worksheet.update_cell(row_to_update, 5, time_out)
        worksheet.update_cell(row_to_update, 6, round(duration, 2))
        return True
    return False

def get_user_consolidated_history(user_id):
    """
    Merges Attendance (Sessions) and Payroll (Money) into one table.
    Shows: Date | Morning (S1) | Evening (S2) | OT (S3) | Total Pay
    """
    att_logs = get_attendance_logs()
    pay_logs = get_payroll_logs()
    
    my_att = [x for x in att_logs if str(x['user_id']).strip() == str(user_id).strip()]
    my_pay = {x['date']: x['total_pay'] for x in pay_logs if str(x['user_id']).strip() == str(user_id).strip()}
    
    grouped = {}
    for log in my_att:
        d = log['date']
        if d not in grouped:
            grouped[d] = []
        t_in = log.get('in_time', '?')
        t_out = log.get('out_time', 'Active')
        grouped[d].append(f"{t_in} - {t_out}")
        
    final_data = []
    sorted_dates = sorted(grouped.keys(), reverse=True)
    
    for d in sorted_dates:
        sessions = grouped[d]
        s1 = sessions[0] if len(sessions) > 0 else "-"
        s2 = sessions[1] if len(sessions) > 1 else "-"
        s3 = sessions[2] if len(sessions) > 2 else "-"
        
        pay = my_pay.get(d, "Pending")
        if pay != "Pending":
            pay = f"RM {pay}"
            
        final_data.append({
            "Date": d,
            "Morning (Session 1)": s1,
            "Evening (Session 2)": s2,
            "Overtime (Session 3)": s3,
            "Total Salary": pay
        })
        
    return final_data

def log_end_shift(user_id, date, rate, ot_multiplier):
    """
    Calculates total hours for the day and saves to Payroll.
    """
    # 1. Get all logs
    logs = get_attendance_logs()
    
    # 2. Filter for TODAY and THIS USER
    # We use str().strip() to ensure " 1001 " matches "1001"
    today_sessions = [
        l for l in logs 
        if str(l['user_id']).strip() == str(user_id).strip() 
        and l['date'] == date
    ]
    
    if not today_sessions:
        return "ERROR_NO_LOGS"

    # 3. Check if any session is still OPEN (User forgot to punch out)
    for s in today_sessions:
        if s['out_time'] == "" or s['out_time'] is None:
            return "ERROR_OPEN"

    # 4. Sum up total hours (HANDLE TEXT vs NUMBERS)
    total_hours = 0.0
    for s in today_sessions:
        try:
            # Force conversion to float. If empty string, use 0.0
            h = float(s['hours_worked']) if s['hours_worked'] else 0.0
            total_hours += h
        except ValueError:
            continue # Skip bad data rows

    # 5. Calculate Salary
    if total_hours > 8:
        normal_hours = 8.0
        ot_hours = total_hours - 8.0
    else:
        normal_hours = total_hours
        ot_hours = 0.0
        
    # Ensure rates are floats
    rate = float(rate)
    ot_multiplier = float(ot_multiplier)

    final_pay = (normal_hours * rate) + (ot_hours * rate * ot_multiplier)
    
    # 6. Save to Payroll Tab
    sheet = get_db_connection()
    try:
        worksheet = sheet.worksheet("Payroll")
        
        # Check if already paid today
        existing_payroll = worksheet.get_all_records()
        for row in existing_payroll:
            if str(row['user_id']).strip() == str(user_id).strip() and row['date'] == date:
                return "ERROR_DUP"
            
        # Append [Date, UserID, TotalHours, OTHours, TotalPay]
        worksheet.append_row([
            date, 
            str(user_id), 
            round(total_hours, 2), 
            round(ot_hours, 2), 
            f"{final_pay:.2f}" # Save as clean string "85.50"
        ])
        return "SUCCESS"
    except Exception as e:
        print(f"Payroll Error: {e}") # Print error to terminal for debugging
        return "ERROR_TAB"
# --- 3. UI STYLING ---

def add_login_design():
    st.markdown("""
    <style>
    .stApp { background: linear-gradient(to bottom, #e3f2fd, #ffffff); }
    .stTextInput>div>div>input { border-radius: 8px; padding: 10px; }
    .stButton>button { width: 100%; border-radius: 8px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

def add_dashboard_design():
    st.markdown("""
    <style>
    .stApp { background: linear-gradient(to bottom right, #FFEFBA, #FFFFFF); }
    .stButton>button { border-radius: 20px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 4. PAGE FUNCTIONS ---

def login_page():
    add_login_design()
    st.markdown("<h1 style='text-align: center; color: #333;'>🔐 PayTrack Login</h1>", unsafe_allow_html=True)
    st.write("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.info("👋 Welcome! Please log in.")
        uid = st.text_input("User ID")
        password = st.text_input("Password", type="password")
        
        if st.button("Log In", use_container_width=True):
            users = fetch_users_dict()
            if uid in users and str(users[uid]['password']) == str(password):
                st.session_state['logged_in'] = True
                st.session_state['user_id'] = uid
                st.session_state['user_name'] = users[uid]['name']
                st.session_state['role'] = users[uid]['role']
                st.success("Login Successful!")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("Invalid User ID or Password")

def admin_dashboard():
    add_dashboard_design()
    st.title("Admin Dashboard 🛠️")
    st.write(f"Logged in as: **{st.session_state['user_name']}**")
    
    with st.expander("➕ Register New Employee", expanded=False):
        st.markdown("### Create New Account")
        with st.form("admin_register_form"):
            new_name = st.text_input("Full Name")
            new_uid = st.text_input("User ID (Unique)")
            c1, c2 = st.columns(2)
            with c1:
                new_age = st.number_input("Age", min_value=16, max_value=80, value=20)
            with c2:
                new_pass = st.text_input("Password", type="password")
            new_email = st.text_input("Email Address")
            new_resume = st.file_uploader("Upload Resume", type=["pdf", "docx"])
            
            st.markdown("---")
            st.markdown("##### 💼 Job Details")
            new_role = st.selectbox("Role", ["user", "admin"])
            c3, c4 = st.columns(2)
            with c3:
                new_rate = st.number_input("Hourly Rate (RM)", value=10.0, step=0.5)
            with c4:
                new_ot = st.number_input("OT Multiplier", value=1.5, step=0.1)
            
            if st.form_submit_button("Create Account"):
                if new_uid and new_pass and new_name:
                    users = fetch_users_dict()
                    clean_uid = str(new_uid).strip()
                    if clean_uid in users:
                        st.error("User ID already exists!")
                    else:
                        resume_name = new_resume.name if new_resume else "N/A"
                        new_user_data = [clean_uid, new_name, new_age, new_email, new_pass, new_role, new_rate, new_ot, resume_name]
                        add_new_user(new_user_data)
                        st.success(f"User {new_name} created!")
                        time.sleep(1)
                        st.rerun()
                else:
                    st.warning("Please fill in Name, ID, and Password.")

    with st.expander("✏️ Update Employee Rates", expanded=False):
        users = fetch_users_dict()
        worker_list = [u for u in users.values()]
        selected_user_id = st.selectbox("Select Employee", options=[u['user_id'] for u in worker_list] if worker_list else [], format_func=lambda x: f"{x} - {users[str(x)]['name']}")
        
        if selected_user_id:
            current_data = users[str(selected_user_id)]
            st.info(f"Current Rate: RM {current_data.get('rate')} | OT: {current_data.get('ot_multiplier')}x")
            with st.form("update_rate_form"):
                upd_rate = st.number_input("New Hourly Rate", value=float(current_data.get('rate', 0)))
                upd_ot = st.number_input("New OT Multiplier", value=float(current_data.get('ot_multiplier', 1.5)))
                if st.form_submit_button("Update Rates"):
                    sheet = get_db_connection()
                    ws = sheet.worksheet("Users")
                    cell = ws.find(str(selected_user_id))
                    if cell:
                        ws.update_cell(cell.row, 7, upd_rate)
                        ws.update_cell(cell.row, 8, upd_ot)
                        st.success("Updated!")
                        time.sleep(1)
                        st.rerun()

    st.divider()
    # --- C. GENERATE DUMMY DATA ---
    with st.expander("🪄 Generate Dummy Data (Report Mode)", expanded=False):
        st.write("Click to add a user AND generate 7 days of work history.")
        col1, col2, col3 = st.columns(3)
        
        # BUTTON 1: SITI
        with col1:
            if st.button("Add 'Siti' (7 Days)"):
                sheet = get_db_connection()
                sheet.worksheet("Users").append_row(["SITI_01", "Siti Worker", 24, "siti@email.com", "123", "user", 25.0, 1.5])
                ws_att = sheet.worksheet("Attendance")
                ws_pay = sheet.worksheet("Payroll")
                for i in range(7):
                    day_str = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                    ws_att.append_row([int(time.time()), "SITI_01", day_str, "09:00:00", "17:00:00", 8.0, 0.0])
                    ws_pay.append_row([day_str, "SITI_01", 8.0, 0.0, 200.0])
                st.toast("✅ Added Siti!")
                time.sleep(1)
                st.rerun()

        # BUTTON 2: ALI
        with col2:
            if st.button("Add 'Ali' (7 Days)"):
                sheet = get_db_connection()
                sheet.worksheet("Users").append_row(["ALI_MGR", "Ali Manager", 35, "ali@email.com", "123", "user", 50.0, 1.5])
                ws_att = sheet.worksheet("Attendance")
                ws_pay = sheet.worksheet("Payroll")
                for i in range(7):
                    day_str = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                    ws_att.append_row([int(time.time()), "ALI_MGR", day_str, "08:00:00", "18:00:00", 9.0, 1.0])
                    ws_pay.append_row([day_str, "ALI_MGR", 9.0, 1.0, 475.0])
                st.toast("✅ Added Ali!")
                time.sleep(1)
                st.rerun()

        # BUTTON 3: ABU
        with col3:
            if st.button("Add 'Abu' (7 Days)"):
                sheet = get_db_connection()
                sheet.worksheet("Users").append_row(["ABU_PT", "Abu PartTime", 19, "abu@email.com", "123", "user", 8.0, 1.5])
                ws_att = sheet.worksheet("Attendance")
                ws_pay = sheet.worksheet("Payroll")
                for i in range(7):
                    day_str = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                    ws_att.append_row([int(time.time()), "ABU_PT", day_str, "12:00:00", "17:00:00", 5.0, 0.0])
                    ws_pay.append_row([day_str, "ABU_PT", 5.0, 0.0, 40.0])
                st.toast("✅ Added Abu!")
                time.sleep(1)
                st.rerun()

    st.divider()
    st.subheader("📊 Payroll Overview")
    payroll_data = get_payroll_logs()
    if payroll_data:
        df = pd.DataFrame(payroll_data)
        df['safe_pay'] = pd.to_numeric(df['total_pay'].astype(str).str.replace('RM','').str.strip(), errors='coerce').fillna(0)
        
        st.metric("Total Payout Pending", f"RM {df['safe_pay'].sum():,.2f}")
        
        t1, t2 = st.tabs(["Charts", "Raw Data"])
        with t1:
            st.bar_chart(df.groupby("user_id")["safe_pay"].sum())
        with t2:
            st.dataframe(df)
            st.download_button("Download CSV", df.to_csv().encode('utf-8'), "payroll.csv")
    else:
        st.info("No payroll records yet.")

    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()

def user_dashboard():
    add_dashboard_design()
    uid = str(st.session_state['user_id']).strip()
    name = st.session_state['user_name']
    role = st.session_state['role']
    
    st.title(f"👋 Hello, {name}")
    st.caption(f"User ID: {uid} | Role: {role.capitalize()}")
    
    logs = get_attendance_logs()
    current_session = next((l for l in logs if str(l['user_id']).strip() == uid and l['out_time'] == ""), None)
    is_clocked_in = current_session is not None
    
    if is_clocked_in:
        st.success(f"🟢 STATUS: CLOCKED IN at {current_session['in_time']}")
    else:
        st.error("🔴 STATUS: CLOCKED OUT")

    st.markdown("---")
    today = datetime.now().strftime("%Y-%m-%d")
    now_time = datetime.now().strftime("%H:%M:%S")
    users = fetch_users_dict()
    user_info = users.get(uid, {})
    rate = float(user_info.get('rate', 0.0))
    ot_mult = float(user_info.get('ot_multiplier', 1.5))

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("🟢 PUNCH IN", disabled=is_clocked_in, use_container_width=True):
            log_punch_in(uid, today, now_time)
            st.toast("Punch In Successful!")
            time.sleep(1)
            st.rerun()
    with c2:
        if st.button("⏸️ PUNCH OUT", disabled=not is_clocked_in, use_container_width=True):
            log_punch_out(uid, today, now_time)
            st.toast("Punch Out Successful!")
            time.sleep(1)
            st.rerun()
    with c3:
        if st.button("🏁 END SHIFT", disabled=is_clocked_in, use_container_width=True):
            result = log_end_shift(uid, today, rate, ot_mult)
            if result == "SUCCESS":
                st.balloons()
                st.success("Shift Closed! Salary Added.")
                time.sleep(2)
                st.rerun()
            elif result == "ERROR_DUP":
                st.warning("Shift already ended today!")
            elif result == "ERROR_OPEN":
                st.error("Punch Out first!")
    
    st.markdown("### 📅 My Work History")
    history_data = get_user_consolidated_history(uid)
    if history_data:
        st.table(pd.DataFrame(history_data))
    else:
        st.info("No records found.")
    
    st.markdown("---")
    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()

# --- 5. MAIN EXECUTION ---
def main():
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    if st.session_state['logged_in']:
        if st.session_state['role'] == 'admin':
            admin_dashboard()
        else:
            user_dashboard()
    else:
        login_page()

if __name__ == "__main__":
    main()




