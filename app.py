from flask import Flask, render_template, request, redirect, url_for, abort, flash, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, timezone
import os
import secrets
import requests

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
VALID_STATUSES = {'Pending', 'Shipped', 'Received'}


def validate_status(status):
    """Validate that status is an allowed value."""
    if status not in VALID_STATUSES:
        return 'Pending'  # Default to Pending if invalid
    return status


def parse_float(value):
    """Parse a float from a form field, returning None on empty/invalid input."""
    if value in (None, ''):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
def utcnow():
    return datetime.now(timezone.utc)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vendor = db.Column(db.String(100), nullable=False)
    date_ordered = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='Pending')
    tracking_number = db.Column(db.String(100))
    # Optional cost and shipping fields
    sales_tax = db.Column(db.Float, nullable=True)
    shipping_cost = db.Column(db.Float, nullable=True)
    customs_tariff = db.Column(db.Float, nullable=True)
    shipper = db.Column(db.String(100), nullable=True)
    vendor_platform = db.Column(db.String(100), nullable=True)
    # Category to separate different product types (optional)
    category = db.Column(db.String(50), nullable=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendor.id'), nullable=True)
    # Receiving/verification
    is_verified = db.Column(db.Boolean, default=False)
    received_at = db.Column(db.DateTime, nullable=True)

    items = db.relationship('LineItem', backref='order', cascade="all, delete", lazy=True)


# Line item model
class LineItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    cost = db.Column(db.Float(), nullable=True)  # per-unit acquisition cost
    upc = db.Column(db.String(50), nullable=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)


class Vendor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    platform = db.Column(db.String(100), nullable=True)
    contact_email = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)


class Inventory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product = db.Column(db.String(100), nullable=False)
    upc = db.Column(db.String(50), nullable=True)
    quantity = db.Column(db.Integer, default=0)
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendor.id'), nullable=True)
    notes = db.Column(db.Text, nullable=True)


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
        # Normalize stored datetimes: if date_ordered is naive, treat it as UTC
        dt = order.date_ordered
        if dt is None:
            order.is_overdue = False
            continue
        if dt.tzinfo is None:
            # assume naive datetimes are UTC (matches previous behavior)
            dt = dt.replace(tzinfo=timezone.utc)

        order.is_overdue = (
            order.status == 'Pending' and
            (datetime.now(timezone.utc) - dt) > timedelta(days=7)
        )
        # calculate total cost (sum of item.cost * qty) + shipping + tax + tariff
        items_total = 0.0
        for it in order.items:
            items_total += (it.cost or 0.0) * (it.quantity or 0)

        order.items_total = items_total
        order.order_total_cost = (
            items_total + (order.shipping_cost or 0.0) + (order.sales_tax or 0.0) + (order.customs_tariff or 0.0)
        )
    return render_template('orders.html', orders=orders)


# Add new order
@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_order():
    vendors = Vendor.query.order_by(Vendor.name).all()
    if request.method == 'POST':
        try:
            vendor = request.form.get('vendor', '').strip()
            if not vendor:
                abort(400, description="Vendor is required")

            status = validate_status(request.form.get('status', 'Pending'))
            tracking_number = request.form.get('tracking_number', '').strip()

            sales_tax = parse_float(request.form.get('sales_tax'))
            shipping_cost = parse_float(request.form.get('shipping_cost'))
            customs_tariff = parse_float(request.form.get('customs_tariff'))
            shipper = request.form.get('shipper') or None
            vendor_platform = request.form.get('vendor_platform') or None
            category = request.form.get('category') or None
            vendor_id = request.form.get('vendor_id')

            # If vendor free-text is empty but vendor_id provided, derive the vendor string
            resolved_vendor = vendor
            resolved_vendor_id = int(vendor_id) if vendor_id not in (None, '', '0') else None
            if (not resolved_vendor or resolved_vendor.strip() == '') and resolved_vendor_id:
                vobj = db.session.get(Vendor, resolved_vendor_id)
                if vobj:
                    resolved_vendor = vobj.name

            new_order = Order(
                vendor=resolved_vendor,
                vendor_id=resolved_vendor_id,
                status=status,
                tracking_number=tracking_number,
                category=category,
                sales_tax=sales_tax,
                shipping_cost=shipping_cost,
                customs_tariff=customs_tariff,
                shipper=shipper,
                vendor_platform=vendor_platform,
            )
            db.session.add(new_order)
            db.session.commit()

            products = request.form.getlist('product[]')
            quantities = request.form.getlist('quantity[]')
            costs = request.form.getlist('cost[]')
            upcs = request.form.getlist('upc[]')

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

    return render_template('add_order.html', vendors=vendors)


# Edit order
@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_order(id):
    order = db.session.get(Order, id)
    if order is None:
        abort(404)
    vendors = Vendor.query.order_by(Vendor.name).all()
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
        costs = request.form.getlist('cost[]')
        upcs = request.form.getlist('upc[]')

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

    return render_template('edit_order.html', order=order, vendors=vendors)


# Vendor detail page
@app.route('/vendor/<int:id>')
def vendor_detail(id):
    vendor = db.session.get(Vendor, id)
    if vendor is None:
        abort(404)
    orders = Order.query.filter_by(vendor_id=vendor.id).order_by(Order.date_ordered.desc()).all()
    # compute totals per order similar to view_orders
    for order in orders:
        items_total = 0.0
        for it in order.items:
            items_total += (it.cost or 0.0) * (it.quantity or 0)
        order.items_total = items_total
        order.order_total_cost = (
            items_total + (order.shipping_cost or 0.0) + (order.sales_tax or 0.0) + (order.customs_tariff or 0.0)
        )
    return render_template('vendor.html', vendor=vendor, orders=orders)


@app.route('/health')
def health():
    return {'status': 'ok'}, 200


@app.route('/set_theme', methods=['POST'])
def set_theme():
    theme = request.form.get('theme') or request.json.get('theme') if request.is_json else None
    if theme not in ('dark', 'light'):
        # accept only dark/light
        return {'error': 'invalid theme'}, 400
    resp = make_response({'status': 'ok'})
    # persist theme for 30 days
    resp.set_cookie('theme', theme, max_age=30*24*60*60, httponly=False)
    return resp


# Inventory UI
@app.route('/inventory')
def list_inventory():
    items = Inventory.query.order_by(Inventory.product).all()
    return render_template('inventory.html', items=items)


@app.route('/inventory/new', methods=['GET', 'POST'])
def create_inventory():
    if request.method == 'POST':
        product = request.form.get('product')
        try:
            qty = int(request.form.get('quantity') or 0)
        except Exception:
            qty = 0
        upc = request.form.get('upc') or None
        vendor_id = request.form.get('vendor_id')
        vendor_id = int(vendor_id) if vendor_id not in (None, '', '0') else None
        notes = request.form.get('notes') or None
        inv = Inventory(product=product, upc=upc, quantity=qty, vendor_id=vendor_id, notes=notes)
        db.session.add(inv)
        db.session.commit()
        return redirect(url_for('list_inventory'))
    vendors = Vendor.query.order_by(Vendor.name).all()
    return render_template('inventory_new.html', vendors=vendors)


@app.route('/api/inventory', methods=['GET', 'POST'])
def api_inventory():
    if request.method == 'GET':
        its = Inventory.query.order_by(Inventory.product).all()
        return {'items': [{'id': i.id, 'product': i.product, 'upc': i.upc, 'quantity': i.quantity} for i in its]}
    # POST -> create or update inventory
    product = request.form.get('product')
    upc = request.form.get('upc') or None
    try:
        qty = int(request.form.get('quantity') or 0)
    except Exception:
        qty = 0
    # if upc provided try to find existing
    inv = None
    if upc:
        inv = Inventory.query.filter_by(upc=upc).first()
    if not inv and product:
        inv = Inventory(product=product, upc=upc, quantity=qty)
        db.session.add(inv)
    else:
        inv.quantity = (inv.quantity or 0) + qty
    db.session.commit()
    return {'id': inv.id, 'product': inv.product, 'upc': inv.upc, 'quantity': inv.quantity}


@app.route('/api/upc_lookup', methods=['POST'])
def api_upc_lookup():
    upc = request.form.get('upc') or (request.json.get('upc') if request.is_json else None)
    if not upc:
        return {'error': 'upc required'}, 400
    api_key = os.environ.get('UPCITEMDB_KEY')
    if not api_key:
        return {'error': 'UPC lookup not configured (UPCITEMDB_KEY missing)'}, 503
    # call UPCItemDB public API
    url = 'https://api.upcitemdb.com/prod/trial/lookup'
    try:
        res = requests.post(url, json={'upc': upc}, headers={'Content-Type': 'application/json', 'Accept': 'application/json', 'user_key': api_key}, timeout=10)
        if res.status_code != 200:
            return {'error': 'lookup failed', 'status': res.status_code, 'body': res.text}, 502
        data = res.json()
        # return the first item if available
        items = data.get('items') or []
        if not items:
            return {'items': []}
        return {'items': items}
    except Exception as e:
        return {'error': 'exception', 'detail': str(e)}, 502


# Vendor management page: list, basic stats, delete
@app.route('/vendors')
def list_vendors():
    vendors = Vendor.query.order_by(Vendor.name).all()
    # attach order_count and total_spend
    for v in vendors:
        orders = Order.query.filter_by(vendor_id=v.id).all()
        v.order_count = len(orders)
        total = 0.0
        for o in orders:
            items_total = sum((it.cost or 0.0) * (it.quantity or 0) for it in o.items)
            total += items_total + (o.shipping_cost or 0.0) + (o.sales_tax or 0.0) + (o.customs_tariff or 0.0)
        v.total_spend = total
    return render_template('vendors.html', vendors=vendors)


@app.route('/api/vendors', methods=['GET', 'POST'])
def api_vendors():
    if request.method == 'GET':
        vs = Vendor.query.order_by(Vendor.name).all()
        return {
            'vendors': [
                {'id': v.id, 'name': v.name, 'platform': v.platform, 'contact_email': v.contact_email}
                for v in vs
            ]
        }
    # POST -> create vendor, return JSON
    name = request.form.get('name')
    if not name:
        return {'error': 'Name required'}, 400
    v = Vendor(name=name.strip(), platform=request.form.get('platform') or None, contact_email=request.form.get('contact_email') or None, notes=None)
    db.session.add(v)
    db.session.commit()
    return {'id': v.id, 'name': v.name, 'platform': v.platform, 'contact_email': v.contact_email}


@app.route('/vendors/edit/<int:id>', methods=['GET', 'POST'])
def edit_vendor(id):
    v = db.session.get(Vendor, id)
    if v is None:
        abort(404)
    if request.method == 'POST':
        v.name = request.form.get('name') or v.name
        v.platform = request.form.get('platform') or v.platform
        v.contact_email = request.form.get('contact_email') or v.contact_email
        v.notes = request.form.get('notes') or v.notes
        db.session.commit()
        return redirect(url_for('list_vendors'))
    return render_template('vendors_new.html', vendor=v)


@app.route('/vendors/delete/<int:id>', methods=['POST'])
def delete_vendor(id):
    v = db.session.get(Vendor, id)
    if v is None:
        abort(404)
    # clear vendor_id from orders, keep legacy vendor string
    orders = Order.query.filter_by(vendor_id=v.id).all()
    for o in orders:
        o.vendor_id = None
    db.session.delete(v)
    db.session.commit()
    return redirect(url_for('list_vendors'))


@app.route('/dashboard')
def dashboard():
    # orders per vendor and spend per vendor
    vendors = Vendor.query.order_by(Vendor.name).all()
    labels = [v.name for v in vendors]
    orders_count = [Order.query.filter_by(vendor_id=v.id).count() for v in vendors]
    spend = []
    for v in vendors:
        total = 0.0
        for o in Order.query.filter_by(vendor_id=v.id).all():
            items_total = sum((it.cost or 0.0) * (it.quantity or 0) for it in o.items)
            total += items_total + (o.shipping_cost or 0.0) + (o.sales_tax or 0.0) + (o.customs_tariff or 0.0)
        spend.append(total)

    # simple time-series: orders per month (YYYY-MM)
    from collections import defaultdict
    counts = defaultdict(int)
    for o in Order.query.all():
        dt = o.date_ordered
        if dt is None:
            continue
        key = dt.strftime('%Y-%m')
        counts[key] += 1
    times = sorted(counts.keys())
    times_counts = [counts[t] for t in times]

    return render_template('dashboard.html')


@app.route('/api/dashboard/vendors')
def api_dashboard_vendors():
    vendors = Vendor.query.order_by(Vendor.name).all()
    labels = [v.name for v in vendors]
    orders_count = [Order.query.filter_by(vendor_id=v.id).count() for v in vendors]
    spend = []
    for v in vendors:
        total = 0.0
        for o in Order.query.filter_by(vendor_id=v.id).all():
            items_total = sum((it.cost or 0.0) * (it.quantity or 0) for it in o.items)
            total += items_total + (o.shipping_cost or 0.0) + (o.sales_tax or 0.0) + (o.customs_tariff or 0.0)
        spend.append(total)
    return {'labels': labels, 'orders': orders_count, 'spend': spend}


@app.route('/api/dashboard/timeseries')
def api_dashboard_timeseries():
    from collections import defaultdict
    counts = defaultdict(int)
    for o in Order.query.all():
        dt = o.date_ordered
        if dt is None:
            continue
        key = dt.strftime('%Y-%m')
        counts[key] += 1
    times = sorted(counts.keys())
    return {'times': times, 'counts': [counts[t] for t in times]}


# Create vendor (small UI)
@app.route('/vendors/new', methods=['GET', 'POST'])
def create_vendor():
    if request.method == 'POST':
        name = request.form.get('name')
        platform = request.form.get('platform')
        contact_email = request.form.get('contact_email')
        notes = request.form.get('notes')
        if not name:
            return render_template('vendors_new.html', error='Name is required')
        v = Vendor(name=name, platform=platform or None, contact_email=contact_email or None, notes=notes or None)
        db.session.add(v)
        db.session.commit()
        return redirect(url_for('add_order'))
    return render_template('vendors_new.html')


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
    order = db.session.get(Order, id)
    if order is None:
        abort(404)
    db.session.delete(order)
    db.session.commit()
    return redirect(url_for('view_orders'))


# Mark order received
@app.route('/receive/<int:id>')
@login_required
def receive_order(id):
    order = db.session.get(Order, id)
    if order is None:
        abort(404)
    order.status = 'Received'
    order.received_at = datetime.utcnow()
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
