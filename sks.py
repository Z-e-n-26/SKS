import streamlit as st
import sqlite3
import pandas as pd
import datetime
import io
from fpdf import FPDF

# --- DB Setup ---
conn = sqlite3.connect("SKSparcel.db", check_same_thread=False)
c = conn.cursor()

# Create tables if not exist
c.execute('''CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE
)''')

c.execute('''CREATE TABLE IF NOT EXISTS weekly_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER,
    week_start DATE,
    day TEXT,
    total REAL,
    received REAL,
    balance REAL,
    FOREIGN KEY (customer_id) REFERENCES customers (id)
)''')
conn.commit()

# --- Helper Functions ---
def add_customer(name):
    try:
        c.execute("INSERT INTO customers (name) VALUES (?)", (name,))
        conn.commit()
    except:
        pass

def delete_customer(customer_id):
    c.execute("DELETE FROM weekly_payments WHERE customer_id=?", (customer_id,))
    c.execute("DELETE FROM customers WHERE id=?", (customer_id,))
    conn.commit()

def get_customers():
    c.execute("SELECT * FROM customers")
    return c.fetchall()

def save_week_data(customer_id, week_start, df):
    c.execute("DELETE FROM weekly_payments WHERE customer_id=? AND week_start=?", (customer_id, week_start))
    for _, row in df.iterrows():
        c.execute("""INSERT INTO weekly_payments 
                     (customer_id, week_start, day, total, received, balance)
                     VALUES (?, ?, ?, ?, ?, ?)""",
                  (customer_id, week_start, row["Day"], row["Total"], row["Received"], row["Balance"]))
    conn.commit()

def get_weeks_for_customer(customer_id):
    c.execute("SELECT DISTINCT week_start FROM weekly_payments WHERE customer_id=?", (customer_id,))
    return [r[0] for r in c.fetchall()]

def get_week_data(customer_id, week_start):
    c.execute("""SELECT day, total, received, balance FROM weekly_payments 
                 WHERE customer_id=? AND week_start=?""", (customer_id, week_start))
    rows = c.fetchall()
    return pd.DataFrame(rows, columns=["Day", "Total", "Received", "Balance"])

def generate_invoice_pdf(customer_name, week_start, df):
    pdf = FPDF()
    pdf.add_page()

    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, f"Invoice for {customer_name}", ln=True, align="C")
    pdf.set_font("Arial", "", 12)
    pdf.ln(5)
    pdf.cell(0, 10, f"Week Starting: {week_start}", ln=True)
    pdf.ln(5)

    pdf.set_font("Arial", "B", 12)
    pdf.cell(40, 10, "Day", 1)
    pdf.cell(40, 10, "Total", 1)
    pdf.cell(40, 10, "Received", 1)
    pdf.cell(40, 10, "Balance", 1)
    pdf.ln()

    pdf.set_font("Arial", "", 12)
    for _, row in df.iterrows():
        pdf.cell(40, 10, str(row["Day"]), 1)
        pdf.cell(40, 10, f"₹{row['Total']:.2f}", 1)
        pdf.cell(40, 10, f"₹{row['Received']:.2f}", 1)
        pdf.cell(40, 10, f"₹{row['Balance']:.2f}", 1)
        pdf.ln()

    pdf.ln(5)
    total_balance = df["Balance"].sum()
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, f"Total Pending Balance: ₹{total_balance:.2f}", ln=True)

    pdf_bytes = pdf.output(dest="S").encode("latin1")
    return io.BytesIO(pdf_bytes)

# --- Streamlit App ---
st.title("📦 Parcel Service Payment Tracker")

tab1, tab2 = st.tabs(["➕ Current Week", "📜 History"])

# --- Current Week Tab ---
with tab1:
    st.subheader("Add / Delete Customer")
    new_customer = st.text_input("Enter customer name")

    if st.button("Add Customer"):
        if new_customer:
            add_customer(new_customer)
            st.success(f"Customer '{new_customer}' added!")

    customers = get_customers()
    if customers:
        customer_dict = {c[1]: c[0] for c in customers}
        selected_customer = st.selectbox("Select Customer", list(customer_dict.keys()))
        customer_id = customer_dict[selected_customer]

        # Delete customer
        if st.button("🗑 Delete Customer"):
            confirm = st.checkbox(f"Confirm delete '{selected_customer}'?")
            if confirm:
                delete_customer(customer_id)
                st.success(f"Customer '{selected_customer}' and all history deleted!")
                st.experimental_rerun()

        # Weekly table
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        df = pd.DataFrame({"Day": days, "Total": [0]*7, "Received": [0]*7})

        with st.container():
            st.subheader("Weekly Payment Table")
            with st.expander("Show/Hide Weekly Table", expanded=True):
                temp_df = st.data_editor(
                    df[["Day", "Total", "Received"]],
                    num_rows="dynamic",
                    use_container_width=True,
                    column_config={
                        "Day": st.column_config.TextColumn(disabled=True),
                        "Total": st.column_config.NumberColumn("Total", min_value=0),
                        "Received": st.column_config.NumberColumn("Received", min_value=0),
                    },
                    key="weekly_editor",
                    hide_index=True
                )
                temp_df["Balance"] = temp_df["Total"] - temp_df["Received"]
                st.metric("Total Pending This Week", f"₹{temp_df['Balance'].sum():.2f}")

        # Save week data
        if st.button("💾 Save This Week"):
            week_start = datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday())
            save_week_data(customer_id, week_start, temp_df)
            st.success("Week data saved successfully!")

        # Generate invoice PDF
        if st.button("📄 Download Invoice PDF"):
            week_start = datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday())
            pdf_file = generate_invoice_pdf(selected_customer, week_start, temp_df)
            st.download_button(
                label="Download Invoice",
                data=pdf_file,
                file_name=f"Invoice_{selected_customer}_{week_start}.pdf",
                mime="application/pdf"
            )

# --- History Tab ---
with tab2:
    st.subheader("Customer Payment History")
    customers = get_customers()
    if customers:
        customer_dict = {c[1]: c[0] for c in customers}
        selected_customer = st.selectbox("Select Customer (History)", list(customer_dict.keys()))
        customer_id = customer_dict[selected_customer]

        weeks = get_weeks_for_customer(customer_id)
        if weeks:
            selected_week = st.selectbox("Select Week Start Date", weeks)
            week_data = get_week_data(customer_id, selected_week)
            st.dataframe(week_data, use_container_width=True)
            st.metric("Total Pending That Week", f"₹{week_data['Balance'].sum():.2f}")

            # Download invoice for history
            if st.button("📄 Download History Invoice PDF"):
                pdf_file = generate_invoice_pdf(selected_customer, selected_week, week_data)
                st.download_button(
                    label="Download Invoice",
                    data=pdf_file,
                    file_name=f"Invoice_{selected_customer}_{selected_week}.pdf",
                    mime="application/pdf"
                )
        else:
            st.info("No history available for this customer.")
