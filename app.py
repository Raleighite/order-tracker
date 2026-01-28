from flask import Flask, render_template, request, redirect, url_for, abort, flash
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os
import secrets

# Set up Flask app
app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))

# Security: SECRET_KEY from environment or generate one (for dev only)
# In production, always set FLASK_SECRET_KEY environment variable!
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY') or secrets.token_hex(32)

app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(basedir, 'database.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Security: Enable CSRF protection
csrf = CSRFProtect(app)

db = SQLAlchemy(app)

# Setup Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'warning'

# Valid status values (for validation)
VALID_STATUSES = {'Pending', 'Shipped'}


def validate_status(status):
    """Validate that status is an allowed value."""
    if status not in VALID_STATUSES:
        return 'Pending'  # Default to Pending if invalid
    return status


# User model for authentication
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# Order model
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vendor = db.Column(db.String(100), nullable=False)
    date_ordered = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='Pending')
    tracking_number = db.Column(db.String(100))
    items = db.relationship('LineItem', backref='order', cascade="all, delete", lazy=True)


# Line item model
class LineItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)


# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            flash('Logged in successfully!', 'success')
            return redirect(next_page if next_page else url_for('index'))
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('login.html')


# Logout route
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


# Setup route (only works if no users exist)
@app.route('/setup', methods=['GET', 'POST'])
def setup():
    # Only allow setup if no users exist
    if User.query.first() is not None:
        flash('Setup already completed.', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not username or not password:
            flash('Username and password are required.', 'danger')
        elif len(password) < 8:
            flash('Password must be at least 8 characters.', 'danger')
        elif password != confirm_password:
            flash('Passwords do not match.', 'danger')
        else:
            user = User(username=username)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash('Account created! Please log in.', 'success')
            return redirect(url_for('login'))

    return render_template('setup.html')


# Home route
@app.route('/')
@login_required
def index():
    return render_template('index.html')


# View all orders
@app.route('/orders')
@login_required
def view_orders():
    orders = Order.query.order_by(Order.date_ordered.desc()).all()

    # Add "overdue" flag to orders with no shipping
    for order in orders:
        order.is_overdue = (
            order.status == 'Pending' and
            datetime.utcnow() - order.date_ordered > timedelta(days=7)
        )
    return render_template('orders.html', orders=orders)


# Add new order
@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_order():
    if request.method == 'POST':
        try:
            vendor = request.form.get('vendor', '').strip()
            if not vendor:
                abort(400, description="Vendor is required")

            status = validate_status(request.form.get('status', 'Pending'))
            tracking_number = request.form.get('tracking_number', '').strip()

            new_order = Order(vendor=vendor, status=status, tracking_number=tracking_number)
            db.session.add(new_order)
            db.session.commit()

            products = request.form.getlist('product[]')
            quantities = request.form.getlist('quantity[]')

            for product, qty in zip(products, quantities):
                product = product.strip()
                if not product:
                    continue
                try:
                    quantity = max(1, int(qty))  # Ensure at least 1
                except (ValueError, TypeError):
                    quantity = 1
                item = LineItem(product=product, quantity=quantity, order_id=new_order.id)
                db.session.add(item)

            db.session.commit()
            return redirect(url_for('view_orders'))
        except Exception as e:
            db.session.rollback()
            print("❌ Error while processing order:", e)
            return render_template('add_order.html'), 500

    return render_template('add_order.html')


# Edit order
@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_order(id):
    order = Order.query.get_or_404(id)
    if request.method == 'POST':
        vendor = request.form.get('vendor', '').strip()
        if not vendor:
            abort(400, description="Vendor is required")

        order.vendor = vendor
        order.status = validate_status(request.form.get('status', 'Pending'))
        order.tracking_number = request.form.get('tracking_number', '').strip()

        LineItem.query.filter_by(order_id=order.id).delete()

        products = request.form.getlist('product[]')
        quantities = request.form.getlist('quantity[]')

        for product, qty in zip(products, quantities):
            product = product.strip()
            if product:
                try:
                    quantity = max(1, int(qty))
                except (ValueError, TypeError):
                    quantity = 1
                item = LineItem(product=product, quantity=quantity, order_id=order.id)
                db.session.add(item)

        db.session.commit()
        return redirect(url_for('view_orders'))

    return render_template('edit_order.html', order=order)


# Update status only
@app.route('/update/<int:id>', methods=['POST'])
@login_required
def update_order(id):
    order = Order.query.get_or_404(id)
    order.status = validate_status(request.form.get('status', 'Pending'))
    db.session.commit()
    return redirect(url_for('view_orders'))


# Delete order
@app.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete_order(id):
    order = Order.query.get_or_404(id)
    db.session.delete(order)
    db.session.commit()
    return redirect(url_for('view_orders'))


# Create DB and run app
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("✅ Database initialized at:", os.path.abspath("database.db"))

        # Check if setup is needed
        if User.query.first() is None:
            print("⚠️  No users found. Visit /setup to create your account.")

    # Security: Use DEBUG from environment, default to False
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1', 'yes')

    if not debug_mode:
        print("🔒 Running in production mode (debug=False)")

    app.run(host="0.0.0.0", port=5000, debug=debug_mode)
