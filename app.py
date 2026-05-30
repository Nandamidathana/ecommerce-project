import streamlit as st
import pyodbc
import hashlib
import pandas as pd
from datetime import datetime

# ================= PAGE CONFIG =================
st.set_page_config(page_title="Flipkart Style Ecommerce", page_icon="🛍️", layout="wide", initial_sidebar_state="expanded")

# ================= CUSTOM CSS =================
st.markdown("""
<style>
    /* Make typography clean */
    .stApp { font-family: 'Inter', 'Roboto', sans-serif; }
    
    /* Flipkart Blue Theme headers */
    [data-testid="stHeader"] { background-color: #2874f0; color: white !important; }
    .css-1d391kg { padding-top: 2rem; }
    
    /* Premium Orange Buttons */
    .stButton>button {
        background-color: #fb641b;
        color: white !important;
        border: none;
        border-radius: 4px;
        padding: 0.5rem 1rem;
        font-weight: 500;
        width: 100%;
        transition: transform 0.2s, background-color 0.2s;
    }
    .stButton>button:hover { 
        background-color: #ff9f00; 
        color: white !important;
        transform: scale(1.02);
    }
    
    /* Top Menu Styling */
    .top-menu-title { font-size: 2rem; font-weight: bold; color: #2874f0; margin-bottom: 20px;}
    
    /* Adaptive Product Cards for Light & Dark Themes */
    .product-card {
        background-color: rgba(128, 128, 128, 0.05); /* Works beautiful on both themes */
        border: 1px solid rgba(128, 128, 128, 0.2);
        padding: 15px;
        border-radius: 8px;
        text-align: center;
        height: 100%;
        margin-bottom: 20px;
        transition: box-shadow 0.2s;
    }
    .product-card:hover { box-shadow: 0 4px 12px 0 rgba(0,0,0,0.15); }
    
    .product-title { font-size: 1.1rem; font-weight: 600; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; margin-top: 10px;}
    .product-price { font-size: 1.25rem; font-weight: bold; margin: 10px 0; }
    .product-rating { font-size: 0.9rem; font-weight: bold; color: white !important; background-color: #388e3c; padding: 2px 6px; border-radius: 3px; display: inline-block;}
    .product-category { font-size: 0.8rem; text-transform: uppercase; margin-top: 5px; opacity: 0.7; }
    
    /* Adaptive form layouts */
    div[data-testid="stForm"] { 
        background-color: rgba(128, 128, 128, 0.05); 
        padding: 20px; 
        border: 1px solid rgba(128, 128, 128, 0.2);
        border-radius: 8px; 
    }
</style>
""", unsafe_allow_html=True)

# ================= DB CONNECTION =================
def get_db_connection():
    return pyodbc.connect(
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=localhost;"
        "DATABASE=EcommerceDB;"
        "Trusted_Connection=yes;"
    )

def init_schema():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 1. Base Tables Creation (Skip if exists)
        schema_queries = [
            """
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Users' and xtype='U')
            CREATE TABLE Users (Username VARCHAR(50) PRIMARY KEY, PasswordHash VARCHAR(255), Role VARCHAR(20))
            """,
            """
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Products' and xtype='U')
            CREATE TABLE Products (ProductID INT IDENTITY(1,1) PRIMARY KEY, ProductName VARCHAR(200), Price DECIMAL(10,2), Stock INT, ImageURL VARCHAR(MAX))
            """,
            """
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Cart' and xtype='U')
            CREATE TABLE Cart (CartID INT IDENTITY(1,1) PRIMARY KEY, Username VARCHAR(50), ProductID INT, Quantity INT)
            """,
            """
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='ShopOrders' and xtype='U')
            CREATE TABLE ShopOrders (
                OrderID INT IDENTITY(1,1) PRIMARY KEY, 
                Username VARCHAR(50), 
                TotalAmount DECIMAL(10,2), 
                OrderDate DATETIME, 
                Status VARCHAR(50), 
                DeliveryAddress VARCHAR(MAX), 
                PaymentMethod VARCHAR(50)
            )
            """,
            """
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='ShopOrderItems' and xtype='U')
            CREATE TABLE ShopOrderItems (
                OrderItemID INT IDENTITY(1,1) PRIMARY KEY, 
                OrderID INT, 
                ProductID INT, 
                Quantity INT, 
                Price DECIMAL(10,2)
            )
            """
        ]
        for q in schema_queries:
            cursor.execute(q)
            
        # 2. Alter existing tables for new rich features safely
        alter_queries = [
            "IF COL_LENGTH('Products', 'Category') IS NULL ALTER TABLE Products ADD Category VARCHAR(100) DEFAULT 'General'",
            "IF COL_LENGTH('Products', 'Description') IS NULL ALTER TABLE Products ADD Description VARCHAR(MAX) DEFAULT 'No description available.'",
            "IF COL_LENGTH('Products', 'Rating') IS NULL ALTER TABLE Products ADD Rating DECIMAL(3,1) DEFAULT 4.5",
            "IF COL_LENGTH('Users', 'Email') IS NULL ALTER TABLE Users ADD Email VARCHAR(100) DEFAULT ''",
            "IF COL_LENGTH('Users', 'Address') IS NULL ALTER TABLE Users ADD Address VARCHAR(MAX) DEFAULT ''",
            "IF COL_LENGTH('Users', 'Phone') IS NULL ALTER TABLE Users ADD Phone VARCHAR(20) DEFAULT ''"
        ]
        
        for q in alter_queries:
            try:
                cursor.execute(q)
            except:
                pass # Ignore if fails
            
        conn.commit()
        conn.close()
    except Exception as e:
        # Proceed silently or show warning if db doesn't exist
        st.warning(f"DB Warning: {e}")

# Run schema init once at startup
init_schema()

# ================= UTILITIES =================
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def format_currency(amount):
    return f"₹ {amount:,.2f}"

# ================= SESSION STATE =================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""
    
if "current_view" not in st.session_state:
    st.session_state.current_view = "Home"

if "selected_product" not in st.session_state:
    st.session_state.selected_product = None

def navigate(view):
    st.session_state.current_view = view
    st.session_state.selected_product = None
    st.rerun()

# ================= DB FUNCTIONS =================
def add_to_cart(pid, qty=1):
    if not st.session_state.logged_in:
        st.warning("Please login to add items to cart!")
        return
    if st.session_state.role != "Customer":
        st.warning("Only customers can buy products!")
        return
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if item exists in cart
    cursor.execute("SELECT CartID, Quantity FROM Cart WHERE Username=? AND ProductID=?", 
                   (st.session_state.username, pid))
    existing = cursor.fetchone()
    
    if existing:
        cursor.execute("UPDATE Cart SET Quantity=Quantity+? WHERE CartID=?", (qty, existing[0]))
    else:
        cursor.execute("INSERT INTO Cart (Username, ProductID, Quantity) VALUES (?, ?, ?)", 
                       (st.session_state.username, pid, qty))
    
    conn.commit()
    conn.close()
    st.success("Item added to Cart!")

# ================= VIEWS (PAGES) =================

def view_login_register():
    st.markdown('<div class="top-menu-title">Welcome to Ecommerce clone</div>', unsafe_allow_html=True)
    t1, t2 = st.tabs(["🔒 Login", "📝 Register"])
    
    with t1:
        st.subheader("Login to your Account")
        with st.form("login_form"):
            l_user = st.text_input("Username")
            l_pass = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")
            
            if submitted:
                h = hash_password(l_pass)
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT Role FROM Users WHERE Username=? AND PasswordHash=?", (l_user, h))
                user = cursor.fetchone()
                conn.close()
                
                if user:
                    st.session_state.logged_in = True
                    st.session_state.username = l_user
                    st.session_state.role = user[0]
                    navigate("Home" if user[0] == "Customer" else "Dashboard")
                else:
                    st.error("Invalid Username or Password")
                    
    with t2:
        st.subheader("Create a new Account")
        with st.form("register_form"):
            r_user = st.text_input("Username")
            r_email = st.text_input("Email")
            r_pass = st.text_input("Password", type="password")
            r_role = st.selectbox("Role", ["Customer", "Admin"])
            r_submit = st.form_submit_button("Sign Up")
            
            if r_submit:
                if not r_user or not r_pass:
                    st.error("Please fill all fields!")
                else:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM Users WHERE Username=?", (r_user,))
                    if cursor.fetchone():
                        st.error("User already exists!")
                    else:
                        h = hash_password(r_pass)
                        try:
                            cursor.execute("INSERT INTO Users (Username, PasswordHash, Role, Email) VALUES (?, ?, ?, ?)", 
                                           (r_user, h, r_role, r_email))
                            conn.commit()
                            st.success("Registration Successful! Please login.")
                        except Exception as e:
                            st.error(f"Error: {e}")
                    conn.close()


def view_home():
    st.markdown('<div class="top-menu-title">🛍️ Explore Categories</div>', unsafe_allow_html=True)
    
    conn = get_db_connection()
    df = pd.read_sql("SELECT * FROM Products", conn)
    conn.close()
    
    if df.empty:
        st.info("No products currently available!")
        return
        
    # Search and Filter Top Bar
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        search_q = st.text_input("🔍 Search products...", placeholder="E.g., iPhone 14")
    with c2:
        categories = ["All"] + list(df['Category'].unique())
        cat_filter = st.selectbox("Filter by Category", categories)
    with c3:
        sort_by = st.selectbox("Sort", ["Relevance", "Price: Low to High", "Price: High to Low", "Rating"])
        
    # Apply Filters
    if cat_filter != "All":
        df = df[df['Category'] == cat_filter]
    if search_q:
        df = df[df['ProductName'].str.contains(search_q, case=False)]
        
    # Apply Sort
    if sort_by == "Price: Low to High":
        df = df.sort_values(by="Price", ascending=True)
    elif sort_by == "Price: High to Low":
        df = df.sort_values(by="Price", ascending=False)
    elif sort_by == "Rating":
        df = df.sort_values(by="Rating", ascending=False)
        
    st.write(f"**Showing {len(df)} results**")
    
    # Render Grid
    cols_per_row = 4
    for i in range(0, len(df), cols_per_row):
        cols = st.columns(cols_per_row)
        for j, col in enumerate(cols):
            if i + j < len(df):
                p = df.iloc[i + j]
                with col:
                    img_url = p['ImageURL'] if p['ImageURL'] else "https://via.placeholder.com/200"
                    
                    st.markdown(f'<div class="product-card">', unsafe_allow_html=True)
                    st.image(img_url, use_container_width=True)
                    st.markdown(f'<div class="product-title">{p["ProductName"]}</div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="product-category">{p["Category"]}</div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="product-rating">{p["Rating"]} ⭐</div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="product-price">{format_currency(p["Price"])}</div>', unsafe_allow_html=True)
                    
                    if p["Stock"] > 0:
                        st.write(f"🔥 Only {p['Stock']} left in stock!")
                        c_a, c_b = st.columns(2)
                        with c_a:
                            if st.button("View", key=f"view_{p['ProductID']}", use_container_width=True):
                                st.session_state.selected_product = p.to_dict()
                                st.session_state.current_view = "ProductDetails"
                                st.rerun()
                        with c_b:
                            if st.button("Add 🛒", key=f"add_{p['ProductID']}", use_container_width=True):
                                add_to_cart(int(p['ProductID']))
                    else:
                        st.error("Out of Stock")
                        if st.button("View", key=f"view_{p['ProductID']}", use_container_width=True):
                            st.session_state.selected_product = p.to_dict()
                            st.session_state.current_view = "ProductDetails"
                            st.rerun()
                            
                    st.markdown('</div>', unsafe_allow_html=True)


def view_product_details():
    if not st.session_state.selected_product:
        navigate("Home")
        
    p = st.session_state.selected_product
    
    if st.button("← Back to Products"):
        navigate("Home")
        
    st.markdown('<div class="top-menu-title">Product Details</div>', unsafe_allow_html=True)
    
    c1, c2 = st.columns([1, 2])
    with c1:
        img_url = p['ImageURL'] if p['ImageURL'] else "https://via.placeholder.com/400"
        st.image(img_url, use_container_width=True)
    with c2:
        st.markdown(f"<h2>{p['ProductName']}</h2>", unsafe_allow_html=True)
        st.markdown(f'<span class="product-rating">{p["Rating"]} ⭐</span>', unsafe_allow_html=True)
        st.markdown(f'<h3 class="product-price">{format_currency(p["Price"])}</h3>', unsafe_allow_html=True)
        st.markdown(f"**Category:** {p['Category']}")
        st.markdown(f"**Status:** {'In Stock (' + str(p['Stock']) + ' available)' if p['Stock'] > 0 else 'Out of Stock'}")
        
        st.markdown("### Description")
        st.write(p.get("Description", "No description provided."))
        
        st.markdown("---")
        if p["Stock"] > 0:
            qty = st.number_input("Select Quantity", min_value=1, max_value=int(p['Stock']), value=1)
            c_add, c_buy = st.columns(2)
            with c_add:
                if st.button("Add to Cart", use_container_width=True):
                    add_to_cart(int(p['ProductID']), qty)
            with c_buy:
                # Direct Buy sends to cart and redirects
                if st.button("Buy Now", type="primary", use_container_width=True):
                    add_to_cart(int(p['ProductID']), qty)
                    navigate("Cart")
        else:
            st.error("We're sorry, this product is currently out of stock.")


def view_cart():
    st.markdown('<div class="top-menu-title">🛒 Your Shopping Cart</div>', unsafe_allow_html=True)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.CartID, c.ProductID, p.ProductName, p.Price, c.Quantity, p.Stock, p.ImageURL
        FROM Cart c JOIN Products p ON c.ProductID = p.ProductID
        WHERE c.Username = ?
    """, (st.session_state.username,))
    items = cursor.fetchall()
    
    if not items:
        st.info("Your cart is empty! Start shopping.")
        if st.button("Go to Home"):
            navigate("Home")
        conn.close()
        return
        
    total = 0
    c1, c2 = st.columns([2, 1])
    
    with c1:
        st.subheader("Cart Items")
        for item in items:
            cart_id, pid, name, price, qty, stock, img = item
            subtotal = price * qty
            total += subtotal
            
            with st.container():
                rc1, rc2, rc3 = st.columns([1, 3, 1])
                with rc1:
                    st.image(img if img else "https://via.placeholder.com/100", width=80)
                with rc2:
                    st.markdown(f"**{name}**")
                    st.write(f"Unit Price: {format_currency(price)}")
                    st.write(f"Qty: {qty} (Stock: {stock})")
                with rc3:
                    st.markdown(f"**{format_currency(subtotal)}**")
                    if st.button("Remove", key=f"rm_{cart_id}"):
                        cursor.execute("DELETE FROM Cart WHERE CartID=?", (cart_id,))
                        conn.commit()
                        st.rerun()
                st.markdown("---")
                
    with c2:
        st.subheader("Price Details")
        st.markdown(f"**Total Items:** {len(items)}")
        st.markdown(f"**Delivery Charges:** <span style='color:green;'>FREE</span>", unsafe_allow_html=True)
        st.markdown(f"### Total Amount: {format_currency(total)}")
        
        st.markdown("---")
        st.subheader("Checkout")
        with st.form("checkout_form"):
            cursor.execute("SELECT Address FROM Users WHERE Username=?", (st.session_state.username,))
            user_addr = cursor.fetchone()[0]
            
            address = st.text_area("Delivery Address", value=user_addr if user_addr else "")
            payment_method = st.radio("Payment Method", ["Cash on Delivery", "UPI", "Credit/Debit Card"])
            
            if payment_method == "UPI":
                st.text_input("Enter UPI ID")
            elif payment_method == "Credit/Debit Card":
                st.text_input("Card Number", type="password")
                
            checkout_btn = st.form_submit_button("Place Order")
            if checkout_btn:
                if not address:
                    st.error("Please provide a delivery address.")
                else:
                    # Checkout Transaction
                    try:
                        cursor.execute("""
                            INSERT INTO ShopOrders (Username, TotalAmount, OrderDate, Status, DeliveryAddress, PaymentMethod)
                            VALUES (?, ?, GETDATE(), 'Pending', ?, ?)
                        """, (st.session_state.username, total, address, payment_method))
                        
                        # Fetch latest OrderID for this user
                        cursor.execute("SELECT TOP 1 OrderID FROM ShopOrders WHERE Username=? ORDER BY OrderID DESC", (st.session_state.username,))
                        order_id = cursor.fetchone()[0]
                        
                        for i in items:
                            cursor.execute("INSERT INTO ShopOrderItems (OrderID, ProductID, Quantity, Price) VALUES (?, ?, ?, ?)", 
                                           (order_id, i[1], i[4], i[3]))
                            # Update stock
                            cursor.execute("UPDATE Products SET Stock = Stock - ? WHERE ProductID = ?", (i[4], i[1]))
                            
                        # Clear cart
                        cursor.execute("DELETE FROM Cart WHERE Username=?", (st.session_state.username,))
                        conn.commit()
                        st.success("🎉 Order Placed Successfully!")
                        import time
                        time.sleep(1)
                        navigate("My Orders")
                    except Exception as e:
                        conn.rollback()
                        st.error(f"Failed to process checkout: {e}")
                        
    conn.close()


def view_my_orders():
    st.markdown('<div class="top-menu-title">📦 My Orders</div>', unsafe_allow_html=True)
    
    conn = get_db_connection()
    df_orders = pd.read_sql("SELECT * FROM ShopOrders WHERE Username=? ORDER BY OrderDate DESC", conn, params=(st.session_state.username,))
    
    if df_orders.empty:
        st.info("You haven't placed any orders yet.")
        conn.close()
        return
        
    for _, order in df_orders.iterrows():
        with st.expander(f"Order #{order['OrderID']} | Placed on {order['OrderDate'].strftime('%d %b %Y')} | Status: {order['Status']}"):
            st.write(f"**Delivery Address:** {order['DeliveryAddress']}")
            st.write(f"**Payment Method:** {order['PaymentMethod']}")
            st.write(f"**Total Amount:** {format_currency(order['TotalAmount'])}")
            
            # Fetch order items
            df_items = pd.read_sql("""
                SELECT p.ProductName, p.ImageURL, oi.Quantity, oi.Price 
                FROM ShopOrderItems oi 
                JOIN Products p ON oi.ProductID = p.ProductID 
                WHERE oi.OrderID=?
            """, conn, params=(int(order['OrderID']),))
            
            st.table(df_items[['ProductName', 'Quantity', 'Price']])
    conn.close()


def view_profile():
    st.markdown('<div class="top-menu-title">👤 My Profile</div>', unsafe_allow_html=True)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT Email, Phone, Address FROM Users WHERE Username=?", (st.session_state.username,))
    user = cursor.fetchone()
    
    with st.form("profile_form"):
        email = st.text_input("Email", value=user[0] if user[0] else "")
        phone = st.text_input("Phone Number", value=user[1] if user[1] else "")
        address = st.text_area("Saved Address", value=user[2] if user[2] else "")
        
        if st.form_submit_button("Update Profile"):
            cursor.execute("UPDATE Users SET Email=?, Phone=?, Address=? WHERE Username=?", 
                           (email, phone, address, st.session_state.username))
            conn.commit()
            st.success("Profile Updated Successfully!")
    conn.close()


def view_admin_dashboard():
    st.markdown('<div class="top-menu-title">📊 Admin Dashboard</div>', unsafe_allow_html=True)
    conn = get_db_connection()
    
    c1, c2, c3, c4 = st.columns(4)
    # Total Revenue
    rev = pd.read_sql("SELECT SUM(TotalAmount) as Total FROM ShopOrders WHERE Status != 'Cancelled'", conn).iloc[0]['Total']
    # Total Orders
    orders = pd.read_sql("SELECT COUNT(*) as Cnt FROM ShopOrders", conn).iloc[0]['Cnt']
    # Total Customers
    cust = pd.read_sql("SELECT COUNT(*) as Cnt FROM Users WHERE Role='Customer'", conn).iloc[0]['Cnt']
    # Low Stock Items
    low_stock = pd.read_sql("SELECT COUNT(*) as Cnt FROM Products WHERE Stock < 5", conn).iloc[0]['Cnt']
    
    c1.metric("Total Revenue", format_currency(rev if pd.notna(rev) else 0))
    c2.metric("Total Orders", orders)
    c3.metric("Total Customers", cust)
    c4.metric("Low Stock Alerts", low_stock)
    
    st.markdown("---")
    st.subheader("Sales by Category")
    try:
        sales_cat = pd.read_sql("""
            SELECT p.Category, SUM(oi.Quantity * oi.Price) as Revenue
            FROM ShopOrderItems oi
            JOIN Products p ON oi.ProductID = p.ProductID
            JOIN ShopOrders o ON oi.OrderID = o.OrderID
            WHERE o.Status != 'Cancelled'
            GROUP BY p.Category
        """, conn)
        if not sales_cat.empty:
            st.bar_chart(sales_cat.set_index('Category'))
    except:
        st.write("Not enough data to display sales charts.")
        
    conn.close()

def view_admin_products():
    st.markdown('<div class="top-menu-title">📦 Manage Inventory</div>', unsafe_allow_html=True)
    conn = get_db_connection()
    
    t1, t2 = st.tabs(["Add New Product", "View & Edit Inventory"])
    
    with t1:
        with st.form("add_product"):
            name = st.text_input("Product Name")
            category = st.selectbox("Category", ["Electronics", "Mobiles", "Fashion", "Home & Furniture", "Appliances", "Books", "Other"])
            desc = st.text_area("Description")
            price = st.number_input("Price (₹)", min_value=0.0, value=0.0)
            stock = st.number_input("Initial Stock", min_value=0, value=10)
            img = st.text_input("Image URL", placeholder="https://example.com/image.jpg")
            
            if st.form_submit_button("Add Product"):
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO Products (ProductName, Category, Description, Price, Stock, ImageURL, Rating)
                    VALUES (?, ?, ?, ?, ?, ?, 4.0)
                """, (name, category, desc, price, stock, img))
                conn.commit()
                st.success(f"Product '{name}' added!")
                
    with t2:
        df = pd.read_sql("SELECT * FROM Products ORDER BY ProductID DESC", conn)
        st.dataframe(df, use_container_width=True)
        
        st.write("### Update Existing Product")
        if not df.empty:
            sel_pid = st.selectbox("Select Product to Update", df['ProductID'].tolist(), format_func=lambda x: f"ID {x}: {df[df['ProductID']==x]['ProductName'].iloc[0]}")
            row = df[df['ProductID'] == sel_pid].iloc[0]
            
            with st.form("update_product"):
                u_price = st.number_input("New Price", value=float(row['Price']))
                u_stock = st.number_input("New Stock", value=int(row['Stock']))
                
                if st.form_submit_button("Update Product"):
                    cursor = conn.cursor()
                    cursor.execute("UPDATE Products SET Price=?, Stock=? WHERE ProductID=?", (u_price, u_stock, int(sel_pid)))
                    conn.commit()
                    st.success("Product Updated!")
                    st.rerun()

    conn.close()

def view_admin_orders():
    st.markdown('<div class="top-menu-title">🚚 Manage Orders</div>', unsafe_allow_html=True)
    conn = get_db_connection()
    df = pd.read_sql("SELECT * FROM ShopOrders ORDER BY OrderDate DESC", conn)
    
    if df.empty:
        st.info("No orders found.")
    else:
        st.dataframe(df, use_container_width=True)
        st.markdown("---")
        st.subheader("Update Order Status")
        order_id = st.selectbox("Select Order ID to update", df['OrderID'].tolist())
        new_status = st.selectbox("New Status", ["Pending", "Shipped", "Out for Delivery", "Delivered", "Cancelled"])
        
        if st.button("Update Status"):
            cursor = conn.cursor()
            cursor.execute("UPDATE ShopOrders SET Status=? WHERE OrderID=?", (new_status, int(order_id)))
            conn.commit()
            st.success(f"Order #{order_id} updated to {new_status}!")
            st.rerun()
            
    conn.close()


# ================= MAIN APPLICATION ROUTING =================

# Sidebar Setup
st.sidebar.markdown(f"<h2>🛍️ Flipkart Clone</h2>", unsafe_allow_html=True)
st.sidebar.markdown("---")

if not st.session_state.logged_in:
    menu = st.sidebar.radio("Navigation Menu", ["Home", "Login / Register"])
    st.session_state.current_view = menu
else:
    st.sidebar.markdown(f"**Hello, {st.session_state.username}**")
    st.sidebar.markdown(f"Role: *{st.session_state.role}*")
    
    if st.session_state.role == "Admin":
        menu = st.sidebar.radio("Admin Menu", ["Dashboard", "Manage Products", "Manage Orders", "Logout"])
    else:
        menu = st.sidebar.radio("Customer Menu", ["Home", "Cart", "My Orders", "Profile", "Logout"])
    
    if menu == "Logout":
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.role = ""
        navigate("Home")
    elif menu != st.session_state.current_view:
        navigate(menu)

# Execute View
if st.session_state.current_view == "Home":
    view_home()
elif st.session_state.current_view == "ProductDetails":
    view_product_details()
elif st.session_state.current_view == "Login / Register":
    view_login_register()
elif st.session_state.current_view == "Cart" and st.session_state.role == "Customer":
    view_cart()
elif st.session_state.current_view == "My Orders" and st.session_state.role == "Customer":
    view_my_orders()
elif st.session_state.current_view == "Profile" and st.session_state.role == "Customer":
    view_profile()
elif st.session_state.current_view == "Dashboard" and st.session_state.role == "Admin":
    view_admin_dashboard()
elif st.session_state.current_view == "Manage Products" and st.session_state.role == "Admin":
    view_admin_products()
elif st.session_state.current_view == "Manage Orders" and st.session_state.role == "Admin":
    view_admin_orders()

# Footer
st.markdown("<br><hr><center><small>Developed using Streamlit | Flipkart Clone Demo</small></center>", unsafe_allow_html=True)
