import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import time

# --- 1. DATABASE SETUP ---
DB_FILE = 'paytrack.db'

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Updated Users Table: Added 'ot_multiplier'
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            name TEXT,
            age INTEGER,
            email TEXT,
            password TEXT,
            role TEXT,
            rate REAL,
            ot_multiplier REAL, 
            resume_path TEXT
        )
    ''')
    
    # Updated Attendance Table: Added 'overtime_hours'
    c.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            date TEXT,
            in_time TEXT,
            out_time TEXT,
            hours_worked REAL,
            overtime_hours REAL,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    ''')
    
    # Create Admin if not exists (Default OT rate is 1.5x)
    c.execute('SELECT * FROM users WHERE role="admin"')
    if not c.fetchone():
        c.execute('INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?)', 
                  ('admin', 'Administrator', 99, 'admin@paytrack.com', 'admin123', 'admin', 0.0, 1.5, None))
        conn.commit()
        
    conn.close()

# --- 2. HELPER FUNCTIONS ---
def run_query(query, params=(), fetch_data=False):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(query, params)
    
    if fetch_data:
        data = c.fetchall()
        conn.close()
        return data
    else:
        conn.commit()
        conn.close()
        return None

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
    .stAlert { border-radius: 15px; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. PAGE FUNCTIONS ---

def register_page():
    add_cheerful_design()
    st.header("📝 Join the Team!")
    
    with st.form("register_form"):
        name = st.text_input("Name")
        age = st.number_input("Age", min_value=18, step=1)
        email = st.text_input("Email")
        new_id = st.text_input("Create ID (Unique)")
        new_pass = st.text_input("Create Password", type='password')
        resume = st.file_uploader("Upload Resume (Optional)", type=['pdf', 'docx'])
        submit = st.form_submit_button("Register")
        
        if submit:
            existing = run_query("SELECT * FROM users WHERE user_id=?", (new_id,), fetch_data=True)
            if existing:
                st.error("ID taken!")
            elif not new_id or not new_pass:
                st.warning("ID/Password required.")
            else:
                resume_status = "Uploaded" if resume else "None"
                # Default Rate: $10, Default OT Multiplier: 1.5x
                run_query("INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?)",
                          (new_id, name, age, email, new_pass, 'user', 10.0, 1.5, resume_status))
                st.success("Success! Please Login.")

def login_page():
    add_cheerful_design()
    st.header("🔐 Login to Paytrack")
    
    user_id = st.text_input("User ID")
    password = st.text_input("Password", type='password')
    
    if st.button("Log In"):
        user = run_query("SELECT * FROM users WHERE user_id=? AND password=?", (user_id, password), fetch_data=True)
        if user:
            user_data = user[0] 
            st.session_state['logged_in_user'] = user_data[0] # user_id
            st.session_state['role'] = user_data[5] # role
            st.session_state['user_name'] = user_data[1] # name
            st.rerun()
        else:
            st.error("Invalid ID or Password")

def user_dashboard():
    add_cheerful_design()
    u_id = st.session_state['logged_in_user']
    u_name = st.session_state['user_name']
    
    # Fetch user rate and OT multiplier
    user_info = run_query("SELECT rate, ot_multiplier FROM users WHERE user_id=?", (u_id,), fetch_data=True)
    rate = user_info[0][0] if user_info else 0.0
    ot_mult = user_info[0][1] if user_info else 1.5

    st.title(f"🌞 Good Morning, {u_name}!")
    
    col1, col2 = st.columns(2)
    today = datetime.now().strftime("%Y-%m-%d")
    now_time = datetime.now().strftime("%H:%M:%S")

    # --- PUNCH IN ---
    with col1:
        if st.button("🚀 PUNCH IN"):
            existing_log = run_query("SELECT * FROM attendance WHERE user_id=? AND date=? AND out_time IS NULL", (u_id, today), fetch_data=True)
            if existing_log:
                st.warning("Already working! 💪")
            else:
                run_query("INSERT INTO attendance (user_id, date, in_time) VALUES (?,?,?)", (u_id, today, now_time))
                st.success(f"Clocked in at {now_time}")

    # --- PUNCH OUT (WITH OVERTIME LOGIC) ---
    with col2:
        if st.button("🎉 PUNCH OUT"):
            open_log = run_query("SELECT id, in_time FROM attendance WHERE user_id=? AND date=? AND out_time IS NULL", (u_id, today), fetch_data=True)
            if open_log:
                log_id = open_log[0][0]
                t_in = datetime.strptime(open_log[0][1], "%H:%M:%S")
                t_out = datetime.strptime(now_time, "%H:%M:%S")
                
                # Calculate Duration
                total_hours = (t_out - t_in).total_seconds() / 3600
                
                # ⚡ OVERTIME LOGIC ⚡
                if total_hours > 8.0:
                    normal_hours = 8.0
                    ot_hours = total_hours - 8.0
                    msg = f"Wow! You worked {ot_hours:.2f} hours Overtime! 💸"
                else:
                    normal_hours = total_hours
                    ot_hours = 0.0
                    msg = "Good job today!"

                run_query("UPDATE attendance SET out_time=?, hours_worked=?, overtime_hours=? WHERE id=?", 
                          (now_time, round(normal_hours, 2), round(ot_hours, 2), log_id))
                
                st.balloons()
                st.success(f"{msg} (Total: {total_hours:.2f} hrs)")
            else:
                st.warning("You haven't punched in yet.")

    st.divider()
    
    # --- STATISTICS ---
    st.subheader("📊 Your Earnings (Including Overtime)")
    logs = run_query("SELECT date, in_time, out_time, hours_worked, overtime_hours FROM attendance WHERE user_id=?", (u_id,), fetch_data=True)
    
    if logs:
        # Create Dataframe
        df = pd.DataFrame(logs, columns=['Date', 'In', 'Out', 'Normal Hrs', 'OT Hrs'])
        
        # Calculate Salary per row
        # Salary = (Normal * Rate) + (OT * Rate * Multiplier)
        df['Daily Pay'] = (df['Normal Hrs'] * rate) + (df['OT Hrs'] * rate * ot_mult)
        
        st.dataframe(df, use_container_width=True)
        
        total_normal = df['Normal Hrs'].sum()
        total_ot = df['OT Hrs'].sum()
        total_pay = df['Daily Pay'].sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Normal Hours", f"{total_normal:.2f}")
        c2.metric("Overtime Hours", f"{total_ot:.2f}", delta="x " + str(ot_mult) + " rate")
        c3.metric("Total Salary", f"${total_pay:,.2f} 💰")
    else:
        st.info("No work history yet.")

    if st.button("👋 Log Out"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

def admin_dashboard():
    add_cheerful_design()
    st.title("Admin Panel")
    
    employees = run_query("SELECT user_id, name, rate, ot_multiplier FROM users WHERE role='user'", fetch_data=True)
    
    if employees:
        st.subheader("Employee Payroll Summary")
        summary_data = []
        
        for emp in employees:
            eid, ename, erate, e_ot_mult = emp
            
            # Fetch sums
            stats = run_query("SELECT SUM(hours_worked), SUM(overtime_hours) FROM attendance WHERE user_id=?", (eid,), fetch_data=True)
            t_norm = stats[0][0] if stats[0][0] else 0.0
            t_ot = stats[0][1] if stats[0][1] else 0.0
            
            salary = (t_norm * erate) + (t_ot * erate * e_ot_mult)
            
            summary_data.append([eid, ename, erate, e_ot_mult, t_norm, t_ot, salary])
            
        df_admin = pd.DataFrame(summary_data, columns=['ID', 'Name', 'Base Rate', 'OT Multiplier', 'Normal Hrs', 'OT Hrs', 'Total Pay'])
        st.dataframe(df_admin)
        
        st.divider()
        
        # --- ADJUST RATES ---
        st.subheader("💰 Adjust Salary & Overtime")
        colA, colB, colC = st.columns(3)
        
        with colA:
            target_id = st.selectbox("Select Employee", [e[0] for e in employees])
        with colB:
            new_rate = st.number_input("Base Hourly Rate ($)", min_value=0.0, step=0.5)
        with colC:
            new_ot_mult = st.number_input("OT Multiplier (e.g. 1.5)", min_value=1.0, step=0.1, value=1.5)
            
        if st.button("Update Employee Compensation"):
            run_query("UPDATE users SET rate=?, ot_multiplier=? WHERE user_id=?", (new_rate, new_ot_mult, target_id))
            st.success(f"Updated compensation for {target_id}")
            time.sleep(1)
            st.rerun()
    else:
        st.info("No employees found.")

    if st.button("Log Out"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# --- 4. MAIN APP ---
def main():
    init_db()
    
    if 'logged_in_user' not in st.session_state:
        st.session_state['logged_in_user'] = None

    if st.session_state['logged_in_user'] is None:
        # Simple Sidebar Menu
        menu = st.sidebar.selectbox("Menu", ["Login", "Register"])
        if menu == "Login":
            login_page()
        else:
            register_page()
    else:
        if st.session_state['role'] == 'admin':
            admin_dashboard()
        else:
            user_dashboard()

if __name__ == "__main__":
    main()