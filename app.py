import os
import secrets
from flask import Flask, render_template, request, redirect, url_for, flash
from cs50 import SQL
from flask_session import Session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename

# Configure application
app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # Use a secure key

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Define the folder where images will be saved
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Function to check allowed extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///app.db")

def create_tables():
    try:
        # Enable foreign key constraints
        db.execute("PRAGMA foreign_keys = ON;")

        # Create 'users' table
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0  -- 0 for regular user, 1 for admin
            )
        """)

        # Create 'profiles' table
        db.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                name TEXT,
                dob TEXT,
                address TEXT,
                gender TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)

        # Create 'properties' table
        db.execute("""
            CREATE TABLE IF NOT EXISTS properties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                location TEXT NOT NULL,
                price REAL NOT NULL,
                rooms INTEGER NOT NULL,
                type TEXT NOT NULL,
                description TEXT,
                image TEXT
            )
        """)

        # Create 'clients' table
        db.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE,
                phone TEXT,
                inquiries TEXT
            )
        """)

        # Create 'transactions' table
        db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                property_id INTEGER,
                client_id INTEGER,
                transaction_type TEXT NOT NULL,
                amount REAL,
                date TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(property_id) REFERENCES properties(id),
                FOREIGN KEY(client_id) REFERENCES clients(id)
            )
        """)
    except Exception as e:
        print(f"Error creating tables: {e}")

create_tables()

# Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)

class User(UserMixin):
    def __init__(self, id, name, email, password):
        self.id = id
        self.name = name
        self.email = email
        self.password = password

@login_manager.user_loader
def load_user(user_id):
    user = db.execute("SELECT * FROM users WHERE id = ?", user_id)
    if user:
        return User(id=user[0]['id'], name=user[0]['name'], email=user[0]['email'], password=user[0]['password'])
    return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['POST'])
def register():
    name = request.form['name']
    email = request.form['email']
    password = request.form['password']
    is_admin = int(request.form.get('is_admin', 0))  # Check if registering as admin
    hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

    if db.execute("SELECT * FROM users WHERE email = ?", email):
        flash('Email already registered.', 'error')
        return redirect(url_for('index'))

    db.execute("INSERT INTO users (name, email, password, is_admin) VALUES (?, ?, ?, ?)", name, email, hashed_password, is_admin)
    user = db.execute("SELECT * FROM users WHERE email = ?", email)
    if user:
        user_id = user[0]['id']
        login_user(User(id=user_id, name=name, email=email, password=hashed_password))
        return redirect(url_for('index'))
    else:
        flash('Registration failed. Please try again.', 'error')
        return redirect(url_for('index'))

@app.route('/login', methods=['POST'])
def login():
    email = request.form['email']
    password = request.form['password']

    user = db.execute("SELECT * FROM users WHERE email = ?", email)
    if user and check_password_hash(user[0]['password'], password):
        user_obj = User(id=user[0]['id'], name=user[0]['name'], email=user[0]['email'], password=user[0]['password'])
        login_user(user_obj)
        if user[0]['is_admin']:  # Check if the user is an admin
            return render_template('admin.html')  # Redirect to admin page
        return render_template('dashboard.html')  # Redirect to normal user dashboard
    else:
        flash('Login Failed. Check your email and/or password.', 'error')
        return redirect(url_for('index'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        name = request.form['name']
        dob = request.form['dob']
        address = request.form['address']
        gender = request.form['gender']

        existing_profile = db.execute("SELECT * FROM profiles WHERE user_id = ?", current_user.id)

        if existing_profile:
            db.execute("""
                UPDATE profiles
                SET name = ?, dob = ?, address = ?, gender = ?
                WHERE user_id = ?
                """, name, dob, address, gender, current_user.id)
            flash('Profile updated successfully.', 'success')
        else:
            db.execute("""
                INSERT INTO profiles (user_id, name, dob, address, gender)
                VALUES (?, ?, ?, ?, ?)
                """, current_user.id, name, dob, address, gender)
            flash('Profile created successfully.', 'success')

        return redirect(url_for('profile'))

    profile_info = db.execute("SELECT * FROM profiles WHERE user_id = ?", current_user.id)
    return render_template('profile.html', profile=profile_info[0] if profile_info else None)

@app.route('/search', methods=['GET', 'POST'])
def search():
    # Fetch all properties
    properties = db.execute("SELECT * FROM properties")

    # Fetch trends (how many times each property is sold or rented)
    trends = db.execute("""
        SELECT 
            p.name AS property_name, 
            p.location, 
            SUM(CASE WHEN t.transaction_type = 'sale' THEN 1 ELSE 0 END) AS times_sold, 
            SUM(CASE WHEN t.transaction_type = 'rental' THEN 1 ELSE 0 END) AS times_rented
        FROM properties p
        LEFT JOIN transactions t ON p.id = t.property_id
        GROUP BY p.id, p.name, p.location
    """)

    print(trends)  # Debugging line to print the trends in the console

    return render_template('search.html', properties=properties, trends=trends)

@app.route('/properties', methods=['GET', 'POST'])
@login_required
def manage_properties():
    if request.method == 'POST':
        name = request.form['name']
        location = request.form['location']
        price = float(request.form['price'])
        rooms = int(request.form['rooms'])
        property_type = request.form['type']
        description = request.form['description']

        file = request.files.get('image')
        image_path = None
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_path = f'{UPLOAD_FOLDER}/{filename}'

        db.execute(
            "INSERT INTO properties (name, location, price, rooms, type, description, image) VALUES (?, ?, ?, ?, ?, ?, ?)",
            name, location, price, rooms, property_type, description, image_path
        )
        flash('Property added successfully.', 'success')
        return redirect(url_for('manage_properties'))

    properties = db.execute("SELECT * FROM properties")
    return render_template('manage_properties.html', properties=properties)

@app.route('/property/update/<int:id>', methods=['GET', 'POST'])
@login_required
def update_property(id):
    if request.method == 'POST':
        name = request.form['name']
        location = request.form['location']
        price = float(request.form['price'])
        rooms = int(request.form['rooms'])
        property_type = request.form['type']
        description = request.form['description']

        db.execute("""
            UPDATE properties
            SET name = ?, location = ?, price = ?, rooms = ?, type = ?, description = ?
            WHERE id = ?
        """, name, location, price, rooms, property_type, description, id)

        flash('Property updated successfully.', 'success')
        return redirect(url_for('search'))

    property = db.execute("SELECT * FROM properties WHERE id = ?", id)
    return render_template('update_property.html', property=property[0])

@app.route('/property/delete/<int:id>', methods=['POST'])
@login_required
def delete_property(id):
    db.execute("DELETE FROM properties WHERE id = ?", id)
    flash('Property deleted successfully.', 'success')
    return redirect(url_for('search'))

@app.route('/manage_clients')
@login_required
def manage_clients():
    transactions = db.execute("""
        SELECT transactions.id, transactions.amount, transactions.date, transactions.transaction_type,
               properties.name AS property_name, clients.name AS client_name
        FROM transactions
        JOIN properties ON transactions.property_id = properties.id
        JOIN clients ON transactions.client_id = clients.id
    """)
    return render_template('manage_clients.html', transactions=transactions)

@app.route('/delete_client/<int:id>', methods=['POST'])
@login_required
def delete_client(id):
    db.execute("DELETE FROM clients WHERE id = ?", id)
    flash('Client deleted successfully.', 'success')
    return redirect(url_for('manage_clients'))

@app.route('/transactions', methods=['GET', 'POST'])
@login_required
def manage_transactions():
    if request.method == 'POST':
        property_id = request.form.get('property_id')
        transaction_type = request.form['transaction_type']
        amount = float(request.form['amount'])
        date = request.form['date']

        if not property_id:
            flash('Property ID must be provided.', 'error')
            return redirect(url_for('manage_transactions'))

        # Check if the property exists
        property_result = db.execute("SELECT * FROM properties WHERE id = ?", (property_id,))
        if not property_result:
            flash('Invalid Property ID.', 'error')
            return redirect(url_for('manage_transactions'))

        # Check if the client exists, otherwise add them
        client_result = db.execute("SELECT * FROM clients WHERE email = ?", (current_user.email,))
        if not client_result:
            db.execute("""
                INSERT INTO clients (name, email, phone, inquiries)
                VALUES (?, ?, ?, ?)
            """, current_user.name, current_user.email, "", "")
            client_result = db.execute("SELECT * FROM clients WHERE email = ?", (current_user.email,))

        client_id = client_result[0]['id'] if client_result else None

        try:
            # Insert the transaction record
            db.execute("""
                INSERT INTO transactions (property_id, client_id, transaction_type, amount, date)
                VALUES (?, ?, ?, ?, ?)
            """, property_id, client_id, transaction_type, amount, date)
            flash('Transaction completed successfully.', 'success')
        except Exception as e:
            flash(f'Error completing transaction: {e}', 'error')

        # Redirect to the order summary page
        return redirect(url_for('order'))

    property_id = request.args.get('property_id')
    property_result = db.execute("SELECT * FROM properties WHERE id = ?", (property_id,))
    property = property_result[0] if property_result else None
    return render_template('manage_transactions.html', property=property)


@app.route('/update_transaction/<int:id>', methods=['GET', 'POST'])
@login_required
def update_transaction(id):
    # Fetch the transaction details
    transaction_result = db.execute("SELECT * FROM transactions WHERE id = ?", id)

    # Check if the transaction exists
    transaction = transaction_result[0] if transaction_result else None

    if request.method == 'POST':
        # Only allow updates if the transaction type is 'rental'
        if transaction and transaction['transaction_type'] == 'rental':
            new_amount = float(request.form['amount'])
            new_date = request.form['date']

            # Update the transaction
            db.execute("""
                UPDATE transactions
                SET amount = ?, date = ?
                WHERE id = ?
            """, new_amount, new_date, id)
            flash('Rental transaction updated successfully.', 'success')
        else:
            flash('Only rental transactions can be updated.', 'error')

        return redirect(url_for('manage_clients'))

    return render_template('update_transaction.html', transaction=transaction)

@app.route('/delete_transaction/<int:id>', methods=['POST'])
@login_required
def delete_transaction(id):
    # Fetch the transaction type
    transaction_result = db.execute("SELECT transaction_type FROM transactions WHERE id = ?", id)

    # Check if the transaction exists
    transaction = transaction_result[0] if transaction_result else None

    if transaction and transaction['transaction_type'] == 'rental':
        # Delete the transaction if it is a rental
        db.execute("DELETE FROM transactions WHERE id = ?", id)
        flash('Rental transaction deleted successfully.', 'success')
    else:
        flash('Only rental transactions can be deleted.', 'error')

    return redirect(url_for('manage_clients'))


@app.route('/order')
@login_required
def order():
    transactions = db.execute("""
        SELECT transactions.*, properties.name AS property_name
        FROM transactions
        JOIN properties ON transactions.property_id = properties.id
        WHERE transactions.client_id IN (SELECT id FROM clients WHERE name = ?)
    """, current_user.name)

    total_amount = sum(transaction['amount'] for transaction in transactions)
    return render_template('order.html', transactions=transactions, total_amount=total_amount)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

if __name__ == "__main__":
    app.run(debug=True)
