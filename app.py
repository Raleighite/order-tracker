from flask import Flask, render_template, request, redirect, url_for, abort, make_response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta, timezone
import os
import requests

# Set up Flask app
app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(basedir, 'database.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Jinja filter for money
@app.template_filter('money')
def money_filter(v):
    try:
        return "${:,.2f}".format(float(v or 0.0))
    except Exception:
        return v

# pre-defined categories for orders
CATEGORIES = [
    'Trading Cards',
    '3D Printing Supplies',
    'Trading Card Accessories',
    'Handheld Emulators'
]

# Order model
def utcnow():
    return datetime.now(timezone.utc)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # backward-compatible vendor string (legacy) and a normalized vendor_id FK
    vendor = db.Column(db.String(100), nullable=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendor.id'), nullable=True)
    # Use a callable default so a new timestamp is generated per row and make it timezone-aware
    date_ordered = db.Column(db.DateTime, default=utcnow)
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
    # Receiving/verification
    is_verified = db.Column(db.Boolean, default=False)
    received_at = db.Column(db.DateTime, nullable=True)

    items = db.relationship('LineItem', backref='order', cascade="all, delete", lazy=True)


# Vendor model
class Vendor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    platform = db.Column(db.String(100), nullable=True)
    contact_email = db.Column(db.String(200), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    orders = db.relationship('Order', backref='vendor_obj', lazy=True)

# Line item model
class LineItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    cost = db.Column(db.Float(), nullable=True)  # per-unit acquisition cost
    upc = db.Column(db.String(50), nullable=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)


# Inventory model for tracking stock
class Inventory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product = db.Column(db.String(200), nullable=False)
    upc = db.Column(db.String(50), nullable=True, index=True)
    quantity = db.Column(db.Integer, default=0)
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendor.id'), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)

# Home route
@app.route('/')
def index():
    return render_template('index.html')

# View all orders
@app.route('/orders')
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
def add_order():
    vendors = Vendor.query.order_by(Vendor.name).all()
    if request.method == 'POST':
        try:
            # accept either vendor_id (preferred) or free-text vendor
            vendor_id = request.form.get('vendor_id')
            vendor = request.form.get('vendor')
            status = request.form['status']
            tracking_number = request.form['tracking_number']
            # helper to parse optional floats
            def parse_float(v):
                try:
                    return float(v) if v not in (None, '') else None
                except Exception:
                    return None

            sales_tax = parse_float(request.form.get('sales_tax'))
            shipping_cost = parse_float(request.form.get('shipping_cost'))
            customs_tariff = parse_float(request.form.get('customs_tariff'))
            shipper = request.form.get('shipper') or None
            vendor_platform = request.form.get('vendor_platform') or None
            category = request.form.get('category') or None

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

            for idx, (product, qty) in enumerate(zip(products, quantities)):
                if not product.strip():
                    continue
                try:
                    quantity = int(qty)
                except ValueError:
                    quantity = 1  # fallback
                # parse per-item cost if provided
                cost = None
                try:
                    if idx < len(costs):
                        c = costs[idx]
                        cost = float(c) if c not in (None, '') else None
                except Exception:
                    cost = None

                upc = None
                try:
                    if idx < len(upcs):
                        upc = upcs[idx] or None
                except Exception:
                    upc = None

                item = LineItem(product=product, quantity=quantity, cost=cost, upc=upc, order_id=new_order.id)
                db.session.add(item)

            db.session.commit()
            return redirect(url_for('view_orders'))
        except Exception as e:
            print("❌ Error while processing order:", e)
            return render_template('add_order.html')

    return render_template('add_order.html', vendors=vendors)

# Edit order
@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_order(id):
    order = db.session.get(Order, id)
    if order is None:
        abort(404)
    vendors = Vendor.query.order_by(Vendor.name).all()
    if request.method == 'POST':
        order.vendor = request.form.get('vendor')
        vendor_id = request.form.get('vendor_id')
        order.category = request.form.get('category') or None
        order.vendor_id = int(vendor_id) if vendor_id not in (None, '', '0') else None
        order.status = request.form['status']
        order.tracking_number = request.form['tracking_number']

        LineItem.query.filter_by(order_id=order.id).delete()
        products = request.form.getlist('product[]')
        quantities = request.form.getlist('quantity[]')
        costs = request.form.getlist('cost[]')
        upcs = request.form.getlist('upc[]')

        for idx, (product, qty) in enumerate(zip(products, quantities)):
            if product.strip():
                try:
                    quantity = int(qty)
                except Exception:
                    quantity = 1
                cost = None
                try:
                    if idx < len(costs):
                        c = costs[idx]
                        cost = float(c) if c not in (None, '') else None
                except Exception:
                    cost = None
                upc = None
                try:
                    if idx < len(upcs):
                        upc = upcs[idx] or None
                except Exception:
                    upc = None
                item = LineItem(product=product, quantity=quantity, cost=cost, upc=upc, order_id=order.id)
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
def update_order(id):
    order = db.session.get(Order, id)
    if order is None:
        abort(404)
    order.status = request.form['status']
    db.session.commit()
    return redirect(url_for('view_orders'))


# Receive order and verify items
@app.route('/receive/<int:id>', methods=['GET', 'POST'])
def receive_order(id):
    order = db.session.get(Order, id)
    if order is None:
        abort(404)
    if request.method == 'POST':
        # Expect received quantities in 'received_quantity[]'
        received = request.form.getlist('received_quantity[]')
        discrepancies = []
        for idx, item in enumerate(order.items):
            try:
                r = int(received[idx])
            except Exception:
                r = 0
            if r != (item.quantity or 0):
                discrepancies.append({'item': item.product, 'ordered': item.quantity, 'received': r})

        # mark as received and verified only if no discrepancies
        order.received_at = datetime.now(timezone.utc)
        order.is_verified = (len(discrepancies) == 0)
        if order.is_verified:
            order.status = 'Received'
            # update inventory: add quantities to Inventory for each item (by UPC if present, else product)
            for item in order.items:
                key_upc = item.upc
                inv = None
                if key_upc:
                    inv = Inventory.query.filter_by(upc=key_upc).first()
                if not inv:
                    inv = Inventory.query.filter_by(product=item.product).first()
                if not inv:
                    inv = Inventory(product=item.product, upc=key_upc, quantity=(item.quantity or 0))
                    db.session.add(inv)
                else:
                    inv.quantity = (inv.quantity or 0) + (item.quantity or 0)
        db.session.commit()
        return render_template('receive_order.html', order=order, discrepancies=discrepancies)

    return render_template('receive_order.html', order=order, discrepancies=None)

# Delete order
@app.route('/delete/<int:id>', methods=['POST'])
def delete_order(id):
    order = db.session.get(Order, id)
    if order is None:
        abort(404)
    db.session.delete(order)
    db.session.commit()
    return redirect(url_for('view_orders'))

# Create DB and run app
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("✅ Database initialized at:", os.path.abspath("database.db"))
    app.run(host="0.0.0.0", port=5000, debug=True)
