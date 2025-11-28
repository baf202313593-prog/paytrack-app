import streamlit as st
import pandas as pd
from datetime import datetime
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 1. CONNECTION ---
def get_db_connection():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open("paytrack_db")
    return sheet

# --- 2. HELPER FUNCTIONS ---
def get_all_users():
    sheet = get_db_connection()
    worksheet = sheet.worksheet("Users")
    return worksheet.get_all_records()

def add_new_user(user_data):
    sheet = get_db_connection()
    worksheet = sheet.worksheet("Users")
    worksheet.append_row(user_data)

def update_user_rate(user_id, new_rate, new_ot):
    sheet = get_db_connection()
    worksheet = sheet.worksheet("Users")
    cell = worksheet.find(user_id)
    worksheet.update_cell(cell.row, 7, new_rate)
    worksheet.update_cell(cell.row, 8, new_ot)

def get_attendance_logs():
    sheet = get_db_connection()
    worksheet = sheet.worksheet("Attendance")
    return worksheet.get_all_records()

def get_payroll_logs():
    sheet = get_db_connection()
    # Ensure you created this tab!
    try:
        worksheet = sheet.worksheet("Payroll")
        return worksheet.get_all_records()
    except:
        return []

def log_punch_in(user_id, date, time_in):
    sheet = get_db_connection()
    worksheet = sheet.worksheet("Attendance")
    log_id = int(time.time())
    # We log 0 for hours initially
    worksheet.append_row([log_id, user_id, date, time_in, "", 0.0, 0.0])

def log_punch_out(user_id, date, time_out):
    sheet = get_db_connection()
    worksheet = sheet.worksheet("Attendance")
    data = worksheet.get_all_records()
    row_index = -1
    for i, row in enumerate(data):
        # Find the open session
        if str(row['user_id']).strip() == str(user_id).strip() and row['date'] == date and row['out_time'] == "":
            row_index = i + 2 
            break
            
    if row_index != -1:
        # Calculate session duration only (No money yet!)
        fmt = "%H:%M:%S"
        t_in = datetime.strptime(data[row_index-2]['in_time'], fmt) # -2 because index vs row mismatch
        t_out = datetime.strptime(time_out, fmt)
        duration = (t_out - t_in).total_seconds() / 3600
        
        # Update Out Time and Duration
        worksheet.update_cell(row_index, 5, time_out)
        worksheet.update_cell(row_index, 6, round(duration, 2))
        return True
    return False

def log_end_shift(user_id, date, rate, ot_mult):
    # 1. Get all sessions for today
    logs = get_attendance_logs()
    today_sessions = [l for l in logs if str(l['user_id']).strip() == str(user_id).strip() and l['date'] == date]
    
    # 2. Check if all sessions are closed (Must punch out first)
    if any(s['out_time'] == "" for s in today_sessions):
        return "ERROR_OPEN"

    # 3. Sum total hours
    total_hours = sum(float(s['hours_worked']) for s in today_sessions if s['hours_worked'] != "")
    
    # 4. Calculate Logic
    if total_hours > 8:
        norm = 8.0
        ot = total_hours - 8.0
    else:
        norm = total_hours
        ot = 0.0
        
    final_pay = (norm * rate) + (ot * rate * ot_mult)
    
    # 5. Save to PAYROLL Tab
    sheet = get_db_connection()
    try:
        worksheet = sheet.worksheet("Payroll")
        # Check if already submitted today to prevent duplicates
        existing = worksheet.get_all_records()
        if any(str(r['user_id']).strip() == str(user_id).strip() and r['date'] == date for r in existing):
            return "ERROR_DUP"
            
        worksheet.append_row([date, user_id, round(total_hours, 2), round(ot, 2), round(final_pay, 2)])
        return "SUCCESS"
    except:
        return "ERROR_TAB"

# --- 3. UI FUNCTIONS ---

def add_login_page_design():
    st.markdown("""
    <style>
    .stApp { background: linear-gradient(to bottom, #e3f2fd, #ffffff); }
    .block-container { padding-top: 3rem; }
    .stTextInput>div>div>input { background-color: #FFFFFF; border: 1px solid #d1d5db; border-radius: 8px; padding: 12px 15px; }
    section[data-testid="stSidebar"] { display: none !important; }
    .stButton>button { width: 100%; border-radius: 8px; height: 45px; font-weight: 600; }
    </style>
    """, unsafe_allow_html=True)

def add_cheerful_design():
    st.markdown("""
    <style>
    .stApp { background: linear-gradient(to bottom right, #FFEFBA, #FFFFFF); }
    .stButton>button { background-color: #FF9966; color: white; border-radius: 20px; border: none; font-weight: bold; transition: 0.3s; }
    .stButton>button:hover { background-color: #FF5E62; transform: scale(1.05); color: white; }
    section[data-testid="stSidebar"] { background-color: #FFF5E1; }
    </style>
    """, unsafe_allow_html=True)

# --- 4. PAGE LOGIC ---

def login_page():
    add_login_page_design()
    c1, c2, c3 = st.columns([3, 2, 3])
    with c2:
        try: st.image("logo.png", use_container_width=True)
        except: pass
    
    col_left, col_center, col_right = st.columns([1, 2, 1])
    with col_center:
        st.write("")
        user_id = st.text_input("User ID", placeholder="Enter your ID")
        password = st.text_input("Password", type='password', placeholder="Enter your Password")
        st.write("")
        b_col1, b_col2 = st.columns(2, gap="small")
        with b_col1:
            if st.button("Log In", type="primary"):
                try:
                    users = get_all_users()
                    valid_user = next((u for u in users if str(u['user_id']).strip() == user_id.strip() and str(u['password']) == password), None)
                    if valid_user:
                        st.session_state['logged_in_user'] = valid_user['user_id']
                        st.session_state['role'] = valid_user['role']
                        st.session_state['user_name'] = valid_user['name']
                        st.rerun()
                    else: st.error("Invalid credentials")
                except Exception as e: st.error(f"Error: {e}")
        with b_col2:
            if st.button("Register"):
                st.session_state['auth_mode'] = 'register'
                st.rerun()

def register_page():
    add_login_page_design()
    col_left, col_center, col_right = st.columns([1, 2, 1])
    with col_center:
        st.header("📝 Join the Team!")
        with st.form("reg"):
            name = st.text_input("Name")
            age = st.number_input("Age", min_value=18)
            email = st.text_input("Email")
            uid = st.text_input("Create ID")
            pas = st.text_input("Password", type='password')
            resume = st.file_uploader("Resume")
            if st.form_submit_button("Create Account"):
                add_new_user([uid, name, age, email, pas, 'user', 10.0, 1.5, "Uploaded" if resume else "None"])
                st.success("Registered! Go to Login.")
        if st.button("Back to Login"):
            st.session_state['auth_mode'] = 'login'
            st.rerun()

def user_dashboard():
    add_cheerful_design()
    uid = str(st.session_state['logged_in_user']).strip()
    name = st.session_state['user_name']
    
    # Get Rate
    all_users = get_all_users()
    user_data = next((u for u in all_users if str(u['user_id']).strip() == uid), None)
    try:
        raw_rate = str(user_data.get('rate', 0)).replace('RM', '').strip()
        rate = float(raw_rate)
        ot_mult = float(user_data.get('ot_multiplier', 1.5))
    except: rate, ot_mult = 0.0, 1.5

    st.title(f"🌞 Hi, {name}!")
    st.info(f"Rate: RM {rate}/hr | OT: {ot_mult}x")
    
    today = datetime.now().strftime("%Y-%m-%d")
    now_time = datetime.now().strftime("%H:%M:%S")

    # --- PUNCH CONTROLS ---
    col1, col2, col3 = st.columns(3)

    # 1. PUNCH IN (Start or Resume)
    with col1:
        if st.button("🚀 PUNCH IN"):
            logs = get_attendance_logs()
            # Check if currently inside a session (Open out_time)
            active = any(str(l['user_id']).strip() == uid and l['date'] == today and l['out_time'] == "" for l in logs)
            if active:
                st.warning("You are already clocked in!")
            else:
                log_punch_in(uid, today, now_time)
                st.success("Started working!")
                time.sleep(1)
                st.rerun()

    # 2. PUNCH OUT (Break/Pause)
    with col2:
        if st.button("⏸️ PUNCH OUT (BREAK)"):
            logs = get_attendance_logs()
            # Find open session
            active_session = next((l for l in logs if str(l['user_id']).strip() == uid and l['date'] == today and l['out_time'] == ""), None)
            if active_session:
                log_punch_out(uid, today, now_time)
                st.success("Paused! Go take a break.")
                time.sleep(1)
                st.rerun()
            else:
                st.warning("You are not clocked in.")

    # 3. END SHIFT (Finalize Day)
    with col3:
        # Use a distinct color for End Shift
        if st.button("🏁 END SHIFT"):
            result = log_end_shift(uid, today, rate, ot_mult)
            if result == "SUCCESS":
                st.balloons()
                st.success("Shift Ended! Salary calculated.")
                time.sleep(2)
                st.rerun()
            elif result == "ERROR_OPEN":
                st.error("You are still punched in! Please Punch Out first.")
            elif result == "ERROR_DUP":
                st.warning("You have already ended your shift for today.")
            elif result == "ERROR_TAB":
                st.error("Missing 'Payroll' tab in Google Sheets!")

    st.divider()
    
    # --- SHOW HISTORY ---
    # We now show the FINALIZED Payroll data, not raw logs
    st.subheader("💰 Completed Shifts (Payroll)")
    pay_logs = get_payroll_logs()
    my_pay = [p for p in pay_logs if str(p['user_id']).strip() == uid]
    
    if my_pay:
        df = pd.DataFrame(my_pay)
        st.dataframe(df)
        # Calculate Total sum safely
        total_earned = sum(float(str(x).replace('RM','').strip()) for x in df['daily_pay'] if x != "")
        st.metric("Total Earnings", f"RM {total_earned:,.2f}")
    else:
        st.info("No completed shifts yet. Work today and press 'End Shift'!")
        
    # Show Raw Logs for Today (Optional, so they can see their sessions)
    with st.expander("View Today's Raw Sessions"):
        logs = get_attendance_logs()
        today_logs = [l for l in logs if str(l['user_id']).strip() == uid and l['date'] == today]
        if today_logs:
            st.dataframe(pd.DataFrame(today_logs))

    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()

def admin_dashboard():
    add_cheerful_design()
    st.title("Admin Panel")
    
    # Admin now looks at Payroll Data
    pay_logs = get_payroll_logs()
    
    if pay_logs:
        df = pd.DataFrame(pay_logs)
        st.subheader("📋 Finalized Payroll")
        st.dataframe(df)
        
        # Analytics
        st.divider()
        st.subheader("📈 Analytics")
        if not df.empty:
            # Clean currency string to float for charting
            df['daily_pay_num'] = df['daily_pay'].astype(str).str.replace('RM','').str.strip().astype(float)
            st.bar_chart(df, x="user_id", y="daily_pay_num", color="#2ecc71")
    else:
        st.info("No payroll data generated yet.")

    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()

def main():
    if 'logged_in_user' not in st.session_state: st.session_state['logged_in_user'] = None
    if 'auth_mode' not in st.session_state: st.session_state['auth_mode'] = 'login'

    if st.session_state['logged_in_user']:
        if st.session_state['role'] == 'admin': admin_dashboard()
        else: user_dashboard()
    else:
        if st.session_state['auth_mode'] == 'login': login_page()
        else: register_page()

if __name__ == "__main__":
    main()










