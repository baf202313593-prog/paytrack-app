import streamlit as st
import pandas as pd
from datetime import datetime
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 1. GOOGLE SHEETS CONNECTION SETUP ---
# We use Streamlit Secrets to handle the connection securely
def get_db_connection():
    # Define the scope
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    # Load credentials from Streamlit secrets
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    
    # Authorize client
    client = gspread.authorize(creds)
    
    # Open the spreadsheet
    # Make sure your Google Sheet is named EXACTLY "paytrack_db"
    sheet = client.open("paytrack_db")
    return sheet

# --- 2. DATABASE HELPER FUNCTIONS (No more SQL!) ---

def get_all_users():
    sheet = get_db_connection()
    worksheet = sheet.worksheet("Users")
    return worksheet.get_all_records()

def add_new_user(user_data):
    sheet = get_db_connection()
    worksheet = sheet.worksheet("Users")
    # user_data is a list: [id, name, age, email, pass, role, rate, ot, resume]
    worksheet.append_row(user_data)

def update_user_rate(user_id, new_rate, new_ot):
    sheet = get_db_connection()
    worksheet = sheet.worksheet("Users")
    # Find the row with the user_id
    cell = worksheet.find(user_id)
    # Update Rate (Column 7) and OT (Column 8)
    worksheet.update_cell(cell.row, 7, new_rate)
    worksheet.update_cell(cell.row, 8, new_ot)

def get_attendance_logs():
    sheet = get_db_connection()
    worksheet = sheet.worksheet("Attendance")
    return worksheet.get_all_records()

def log_punch_in(user_id, date, time_in):
    sheet = get_db_connection()
    worksheet = sheet.worksheet("Attendance")
    # Generate a simple unique ID using timestamp
    log_id = int(time.time())
    # Columns: id, user_id, date, in_time, out_time, hours_worked, overtime_hours
    worksheet.append_row([log_id, user_id, date, time_in, "", 0.0, 0.0])

def log_punch_out(user_id, date, time_out, normal_hours, ot_hours):
    sheet = get_db_connection()
    worksheet = sheet.worksheet("Attendance")
    data = worksheet.get_all_records()
    
    # Find the row manually (Google Sheets doesn't have SQL WHERE)
    row_index = -1
    for i, row in enumerate(data):
        # We look for the user, the date, and an empty out_time
        # Note: gspread reads empty cells as empty strings ""
        if str(row['user_id']) == str(user_id) and row['date'] == date and row['out_time'] == "":
            row_index = i + 2 # +2 because logic is 0-indexed but Sheets is 1-indexed + 1 for header
            break
            
    if row_index != -1:
        # Update Out Time (Col 5), Hours (Col 6), OT (Col 7)
        worksheet.update_cell(row_index, 5, time_out)
        worksheet.update_cell(row_index, 6, normal_hours)
        worksheet.update_cell(row_index, 7, ot_hours)
        return True
    return False

# --- 3. DESIGN FUNCTIONS ---

def add_login_page_design():
    st.markdown("""
    <style>
    .stApp {
        background: linear-gradient(to bottom right, #e0f2f7, #ffffff);
    }
    .stTextInput>div>div>input {
        background-color: #f0f2f6; border: 1px solid #d0d2d6; border-radius: 8px; padding: 10px 15px;
    }
    .stButton>button {
        background-color: #f0f2f6; color: #555; border: 1px solid #d0d2d6; border-radius: 8px; padding: 10px 25px;
    }
    .stButton>button:hover { background-color: #e0e2e6; }
    section[data-testid="stSidebar"] { display: none !important; }
    </style>
    """, unsafe_allow_html=True)

def add_cheerful_design():
    st.markdown("""
    <style>
    .stApp { background: linear-gradient(to bottom right, #FFEFBA, #FFFFFF); }
    .stButton>button {
        background-color: #FF9966; color: white; border-radius: 20px; border: none; font-weight: bold; transition: 0.3s;
    }
    .stButton>button:hover { background-color: #FF5E62; transform: scale(1.05); color: white; }
    section[data-testid="stSidebar"] { background-color: #FFF5E1; }
    h1, h2, h3 { color: #FF6B6B; font-family: 'Comic Sans MS', 'Chalkboard SE', sans-serif; }
    </style>
    """, unsafe_allow_html=True)

# --- 4. PAGE LOGIC ---

def login_page():
    add_login_page_design()
    col_left, col_center, col_right = st.columns([1, 2, 1])
    
    with col_center:
        # Ensure logo.png is in your folder!
        try:
            st.image("logo.png", width=150)
        except:
            st.warning("Logo not found")
            
        with st.form("login_form"):
            st.write("")
            user_id = st.text_input("User ID")
            password = st.text_input("Password", type='password')
            submit = st.form_submit_button("Log In")
        
        if submit:
            try:
                users = get_all_users()
                # Find user in list of dicts
                valid_user = next((u for u in users if str(u['user_id']) == user_id and str(u['password']) == password), None)
                
                if valid_user:
                    st.session_state['logged_in_user'] = valid_user['user_id']
                    st.session_state['role'] = valid_user['role']
                    st.session_state['user_name'] = valid_user['name']
                    st.rerun()
                else:
                    st.error("Invalid credentials")
            except Exception as e:
                st.error(f"Connection Error: {e}")

def register_page():
    add_cheerful_design()
    st.header("📝 Join the Team!")
    with st.form("reg"):
        name = st.text_input("Name")
        age = st.number_input("Age", min_value=18)
        email = st.text_input("Email")
        uid = st.text_input("Create ID")
        pas = st.text_input("Password", type='password')
        resume = st.file_uploader("Resume")
        sub = st.form_submit_button("Register")
        
        if sub:
            users = get_all_users()
            if any(str(u['user_id']) == uid for u in users):
                st.error("ID Exists")
            else:
                # Add to Google Sheet
                add_new_user([uid, name, age, email, pas, 'user', 10.0, 1.5, "Uploaded" if resume else "None"])
                st.success("Registered! Go to Login.")

def user_dashboard():
    add_cheerful_design()
    uid = st.session_state['logged_in_user']
    name = st.session_state['user_name']
    
    # Get user details for rate
    all_users = get_all_users()
    user_data = next((u for u in all_users if str(u['user_id']) == uid), None)
    rate = float(user_data['rate']) if user_data else 0.0
    ot_mult = float(user_data['ot_multiplier']) if user_data else 1.5

    st.title(f"🌞 Hi, {name}!")
    
    col1, col2 = st.columns(2)
    today = datetime.now().strftime("%Y-%m-%d")
    now_time = datetime.now().strftime("%H:%M:%S")

    with col1:
        if st.button("🚀 PUNCH IN"):
            logs = get_attendance_logs()
            # Check if already punched in
            active = any(str(l['user_id']) == str(uid) and l['date'] == today and l['out_time'] == "" for l in logs)
            
            if active:
                st.warning("Already working!")
            else:
                log_punch_in(uid, today, now_time)
                st.success("Clocked In!")

    with col2:
        if st.button("🎉 PUNCH OUT"):
            success = False
            # Calculate hours logic handled inside log_punch_out somewhat, but we need time delta first
            # Re-fetch for calculation
            logs = get_attendance_logs()
            entry = next((l for l in logs if str(l['user_id']) == str(uid) and l['date'] == today and l['out_time'] == ""), None)
            
            if entry:
                fmt = "%H:%M:%S"
                t_in = datetime.strptime(entry['in_time'], fmt)
                t_out = datetime.strptime(now_time, fmt)
                total = (t_out - t_in).total_seconds() / 3600
                
                norm = 8.0 if total > 8 else total
                ot = total - 8.0 if total > 8 else 0.0
                
                log_punch_out(uid, today, now_time, round(norm, 2), round(ot, 2))
                st.balloons()
                st.success("Clocked Out!")
            else:
                st.warning("Not clocked in.")

    st.divider()
    st.subheader("Your History")
    # Show dataframe
    logs = get_attendance_logs()
    my_logs = [l for l in logs if str(l['user_id']) == str(uid)]
    if my_logs:
        df = pd.DataFrame(my_logs)
        # Calculate Pay
        df['Pay'] = (df['hours_worked'] * rate) + (df['overtime_hours'] * rate * ot_mult)
        st.dataframe(df[['date', 'in_time', 'out_time', 'hours_worked', 'overtime_hours', 'Pay']])
        st.metric("Total Earned", f"${df['Pay'].sum():,.2f}")

    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()

def admin_dashboard():
    add_cheerful_design()
    st.title("Admin Panel")
    
    # Get Data
    users = get_all_users()
    logs = get_attendance_logs()
    
    # Filter only 'user' role
    employees = [u for u in users if u['role'] == 'user']
    
    summary = []
    for e in employees:
        eid = str(e['user_id'])
        # Filter logs for this user
        u_logs = [l for l in logs if str(l['user_id']) == eid]
        
        t_norm = sum(l['hours_worked'] for l in u_logs if l['hours_worked'])
        t_ot = sum(l['overtime_hours'] for l in u_logs if l['overtime_hours'])
        
        rate = float(e['rate'])
        ot_m = float(e['ot_multiplier'])
        
        pay = (t_norm * rate) + (t_ot * rate * ot_m)
        summary.append([eid, e['name'], rate, ot_m, t_norm, t_ot, pay])
        
    df = pd.DataFrame(summary, columns=['ID', 'Name', 'Rate', 'OT x', 'Norm Hrs', 'OT Hrs', 'Pay'])
    st.dataframe(df)
    
    st.divider()
    st.subheader("Update Salary")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        target = st.selectbox("Employee", [e['ID'] for e in summary])
    with c2:
        nr = st.number_input("New Rate", value=10.0)
    with c3:
        not_m = st.number_input("New OT Multiplier", value=1.5)
        
    if st.button("Update"):
        update_user_rate(target, nr, not_m)
        st.success("Updated!")
        time.sleep(1)
        st.rerun()

    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()

def main():
    if 'logged_in_user' not in st.session_state:
        st.session_state['logged_in_user'] = None
        
    if st.session_state['logged_in_user']:
        if st.session_state['role'] == 'admin':
            admin_dashboard()
        else:
            user_dashboard()
    else:
        # Route based on sidebar for Login/Register
        # Note: Login page hides sidebar, Register shows it.
        # Simple hack: Default to Login, add link to switch? 
        # For simplicity with your requested design:
        menu = st.sidebar.selectbox("Menu", ["Login", "Register"])
        if menu == "Login":
            login_page()
        else:
            register_page()

if __name__ == "__main__":
    main()
        else:
            user_dashboard()

if __name__ == "__main__":

    main()
