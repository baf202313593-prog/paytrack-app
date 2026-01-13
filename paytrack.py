import streamlit as st
import pandas as pd
from datetime import datetime, timedelta  # <--- Add timedelta
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 1. CONNECTION & SETUP ---
def get_db_connection():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    # Ensure you have your secrets.toml set up correctly!
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
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
        # Get all values from the "Users" worksheet
        rows = sheet.worksheet("Users").get_all_values()
        
        users_dict = {}
        # Skip the header row (index 0)
        for row in rows[1:]:
            if len(row) > 0:
                # FORCE ID TO STRING + REMOVE SPACES
                user_id = str(row[0]).strip() 
                
                # Store data in a clear structure
                users_dict[user_id] = {
                    "name": row[1],
                    "age": row[2],      # Now capturing Age
                    "email": row[3],    # Now capturing Email
                    "password": str(row[4]).strip(),
                    "role": row[5],
                    "rate": float(row[6]) if row[6] else 0.0,
                    "ot_multiplier": float(row[7]) if row[7] else 1.0,
                    "resume": row[8] if len(row) > 8 else "No Resume" # Capture Resume Filename
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
    return worksheet.get_all_records()

def get_payroll_logs():
    sheet = get_db_connection()
    try:
        worksheet = sheet.worksheet("Payroll")
        return worksheet.get_all_records()
    except:
        return []

def log_punch_in(user_id, date, time_in):
    sheet = get_db_connection()
    worksheet = sheet.worksheet("Attendance")
    log_id = int(time.time())
    # Structure: [ID, UserID, Date, InTime, OutTime, Hours, LogID]
    # Note: Adjust columns based on your actual sheet headers
    worksheet.append_row([log_id, user_id, date, time_in, "", 0.0])

def log_punch_out(user_id, date, time_out):
    sheet = get_db_connection()
    worksheet = sheet.worksheet("Attendance")
    data = worksheet.get_all_records()
    
    # Find the row index (gspread is 1-based, plus header)
    row_to_update = -1
    
    # Iterate to find the open session
    for i, row in enumerate(data):
        if str(row['user_id']).strip() == str(user_id).strip() and row['date'] == date and row['out_time'] == "":
            row_to_update = i + 2 # +2 accounts for 0-index list and 1-row header
            previous_in_time = row['in_time']
            break
            
    if row_to_update != -1:
        # Calculate Duration
        fmt = "%H:%M:%S"
        t_in = datetime.strptime(previous_in_time, fmt)
        t_out = datetime.strptime(time_out, fmt)
        duration = (t_out - t_in).total_seconds() / 3600
        
        # Update Google Sheet
        # Column 5 is Out Time, Column 6 is Hours Worked (Adjust if your columns differ)
        worksheet.update_cell(row_to_update, 5, time_out)
        worksheet.update_cell(row_to_update, 6, round(duration, 2))
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
        # Check for duplicates
        existing = worksheet.get_all_records()
        if any(str(r['user_id']).strip() == str(user_id).strip() and r['date'] == date for r in existing):
            return "ERROR_DUP"
            
        # Headers: [Date, UserID, TotalHours, OTHours, TotalPay]
        worksheet.append_row([date, user_id, round(total_hours, 2), round(ot, 2), round(final_pay, 2)])
        return "SUCCESS"
    except:
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
                # SUCCESS
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
    
    # --- A. REGISTER NEW USER (UPDATED) ---
    with st.expander("➕ Register New Employee", expanded=False):
        st.markdown("### Create New Account")
        with st.form("admin_register_form"):
            # 1. Basic Info
            new_name = st.text_input("Full Name")
            new_uid = st.text_input("User ID (Unique)")
            
            c1, c2 = st.columns(2)
            with c1:
                new_age = st.number_input("Age", min_value=16, max_value=80, value=20)
            with c2:
                new_pass = st.text_input("Password", type="password")

            # 2. Contact & Resume
            new_email = st.text_input("Email Address")
            new_resume = st.file_uploader("Upload Resume (Optional)", type=["pdf", "docx"])
            
            # 3. Job Role & Salary
            st.markdown("---")
            st.markdown("##### 💼 Job Details")
            new_role = st.selectbox("Role", ["user", "admin"])
            
            c3, c4 = st.columns(2)
            with c3:
                new_rate = st.number_input("Hourly Rate (RM)", value=10.0, step=0.5)
            with c4:
                new_ot = st.number_input("OT Multiplier (e.g. 1.5)", value=1.5, step=0.1)
            
            submit_reg = st.form_submit_button("Create Account")
            
            if submit_reg:
                if new_uid and new_pass and new_name and new_email:
                    users = fetch_users_dict()
                    
                    # Convert input ID to string for safety
                    clean_uid = str(new_uid).strip()
                    
                    if clean_uid in users:
                        st.error("User ID already exists! Please try a different one.")
                    else:
                        # Handle Resume Name
                        resume_name = new_resume.name if new_resume else "N/A"
                        
                        # Prepare Data Row (9 Columns)
                        # [ID, Name, Age, Email, Password, Role, Rate, OT, ResumeName]
                        new_user_data = [
                            clean_uid, 
                            new_name, 
                            new_age, 
                            new_email, 
                            new_pass, 
                            new_role, 
                            new_rate, 
                            new_ot,
                            resume_name
                        ]
                        
                        add_new_user(new_user_data)
                        st.success(f"✅ User {new_name} created successfully!")
                        st.balloons()
                        time.sleep(1)
                        st.rerun()
                else:
                    st.warning("Please fill in Name, ID, Password, and Email.")

    # --- B. MANAGE EXISTING USERS ---
    with st.expander("✏️ Update Employee Rates", expanded=False):
        st.markdown("### Adjust Salary for Existing Staff")
        users = fetch_users_dict()
        worker_list = [u for u in users.values()]
        
        selected_user_id = st.selectbox(
            "Select Employee", 
            options=[u['user_id'] for u in worker_list] if worker_list else [], # Fix for empty list
            format_func=lambda x: f"{x} - {users[str(x)]['name']}"
        )
        
        if selected_user_id:
            current_data = users[str(selected_user_id)]
            st.info(f"Current Rate: **RM {current_data.get('rate')}** | OT: **{current_data.get('ot_multiplier')}x**")
            
            with st.form("update_rate_form"):
                upd_rate = st.number_input("New Hourly Rate (RM)", value=float(current_data.get('rate', 0)), step=0.5)
                upd_ot = st.number_input("New OT Multiplier", value=float(current_data.get('ot_multiplier', 1.5)), step=0.1)
                
                if st.form_submit_button("Update Rates"):
                    sheet = get_db_connection()
                    ws = sheet.worksheet("Users")
                    cell = ws.find(str(selected_user_id))
                    if cell:
                        # Column 7 = Rate, Column 8 = OT
                        ws.update_cell(cell.row, 7, upd_rate)
                        ws.update_cell(cell.row, 8, upd_ot)
                        st.success(f"Updated {current_data['name']}'s salary details!")
                        time.sleep(1)
                        st.rerun()

    st.divider()

    # --- C. PAYROLL OVERVIEW ---
    st.subheader("📊 Payroll Overview")
    payroll_data = get_payroll_logs()
    
    if payroll_data:
        df = pd.DataFrame(payroll_data)
        
        df['safe_pay'] = pd.to_numeric(df['total_pay'].astype(str).str.replace('RM','').str.strip(), errors='coerce').fillna(0)
        df['safe_hours'] = pd.to_numeric(df['total_hours'].astype(str), errors='coerce').fillna(0)
        
        total_payout = df['safe_pay'].sum()
        c1, c2 = st.columns(2)
        c1.metric("Total Payout Pending", f"RM {total_payout:,.2f}")
        c2.metric("Total Shifts Completed", len(df))
        
        tab1, tab2, tab3 = st.tabs(["📈 Salary Statistics", "📜 Raw Data", "👤 User Information"])
        
        with tab1:
            st.markdown("##### Total Salary by Employee")
            chart_data = df.groupby("user_id")["safe_pay"].sum()
            st.bar_chart(chart_data)
            
        with tab2:
            st.dataframe(df.drop(columns=['safe_pay', 'safe_hours']))
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download CSV", csv, "payroll_data.csv", "text/csv")
            
        with tab3:
            st.markdown("##### 👤 Employee Summary (Aggregated)")
            df_grouped = df.groupby("user_id")[["safe_hours", "safe_pay"]].sum().reset_index()
            all_users = fetch_users_dict()
            df_grouped['name'] = df_grouped['user_id'].apply(lambda x: all_users.get(str(x).strip(), {}).get('name', 'Unknown'))
            df_final = df_grouped[['user_id', 'name', 'safe_hours', 'safe_pay']]
            df_final.columns = ['User ID', 'Name', 'Full Total Hours Worked', 'Full Total Salary (RM)']
            st.dataframe(df_final)
            csv_sum = df_final.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Summary CSV", csv_sum, "employee_summary.csv", "text/csv")

    else:
        st.info("No payroll records found yet.")

    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()
        
def user_dashboard():
    add_dashboard_design()
    uid = str(st.session_state['user_id']).strip()
    name = st.session_state['user_name']
    
    # Refresh user data to get latest rate
    users = fetch_users_dict()
    my_data = users.get(uid, {})
    try:
        rate = float(my_data.get('rate', 0))
        ot_mult = float(my_data.get('ot_multiplier', 1.5))
    except:
        rate, ot_mult = 0.0, 1.5

    st.title(f"🌞 Hi, {name}!")
    st.info(f"Rate: RM {rate}/hr | OT Multiplier: {ot_mult}x")
    
    today = datetime.now().strftime("%Y-%m-%d")
    now_time = datetime.now().strftime("%H:%M:%S")

    # --- PUNCH CONTROLS ---
    col1, col2, col3 = st.columns(3)

    # 1. PUNCH IN
    with col1:
        if st.button("🚀 PUNCH IN"):
            logs = get_attendance_logs()
            active = any(str(l['user_id']).strip() == uid and l['date'] == today and l['out_time'] == "" for l in logs)
            if active:
                st.warning("You are already clocked in!")
            else:
                log_punch_in(uid, today, now_time)
                st.success("Started working!")
                time.sleep(1)
                st.rerun()

    # 2. PUNCH OUT
    with col2:
        if st.button("⏸️ PUNCH OUT"):
            logs = get_attendance_logs()
            active_session = any(str(l['user_id']).strip() == uid and l['date'] == today and l['out_time'] == "" for l in logs)
            if active_session:
                log_punch_out(uid, today, now_time)
                st.success("Paused! Go take a break.")
                time.sleep(1)
                st.rerun()
            else:
                st.warning("You are not clocked in.")

    # 3. END SHIFT
    with col3:
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
    st.subheader("💰 My Completed Shifts")
    pay_logs = get_payroll_logs()
    my_pay = [p for p in pay_logs if str(p['user_id']).strip() == uid]
    
    if my_pay:
        df = pd.DataFrame(my_pay)
        st.dataframe(df)
        total_earned = sum(float(str(x).replace('RM','').strip()) for x in df['total_pay'])
        st.metric("Total Earnings", f"RM {total_earned:,.2f}")
    else:
        st.info("No completed shifts yet.")
        
    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()

# --- 5. MAIN APP ---

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










