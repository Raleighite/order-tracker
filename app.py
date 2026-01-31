from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta, timezone
import os

# Set up Flask app
app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(basedir, 'database.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Order model
def utcnow():
    return datetime.now(timezone.utc)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vendor = db.Column(db.String(100), nullable=False)
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
    # Receiving/verification
    is_verified = db.Column(db.Boolean, default=False)
    received_at = db.Column(db.DateTime, nullable=True)

    items = db.relationship('LineItem', backref='order', cascade="all, delete", lazy=True)

# Line item model
class LineItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    cost = db.Column(db.Float, nullable=True)  # per-unit acquisition cost
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)

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
    if request.method == 'POST':
        try:
            vendor = request.form['vendor']
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

            new_order = Order(
                vendor=vendor,
                status=status,
                tracking_number=tracking_number,
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

                item = LineItem(product=product, quantity=quantity, cost=cost, order_id=new_order.id)
                db.session.add(item)

            db.session.commit()
            return redirect(url_for('view_orders'))
        except Exception as e:
            print("❌ Error while processing order:", e)
            return render_template('add_order.html')

    return render_template('add_order.html')

# Edit order
@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_order(id):
    order = Order.query.get_or_404(id)
    if request.method == 'POST':
        order.vendor = request.form['vendor']
        order.status = request.form['status']
        order.tracking_number = request.form['tracking_number']

        LineItem.query.filter_by(order_id=order.id).delete()

        products = request.form.getlist('product[]')
        quantities = request.form.getlist('quantity[]')

        for product, qty in zip(products, quantities):
            if product.strip():
                item = LineItem(product=product, quantity=int(qty), order_id=order.id)
                db.session.add(item)

        db.session.commit()
        return redirect(url_for('view_orders'))

    return render_template('edit_order.html', order=order)

# Update status only
@app.route('/update/<int:id>', methods=['POST'])
def update_order(id):
    order = Order.query.get_or_404(id)
    order.status = request.form['status']
    db.session.commit()
    return redirect(url_for('view_orders'))


# Receive order and verify items
@app.route('/receive/<int:id>', methods=['GET', 'POST'])
def receive_order(id):
    order = Order.query.get_or_404(id)
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
        db.session.commit()
        return render_template('receive_order.html', order=order, discrepancies=discrepancies)

    return render_template('receive_order.html', order=order, discrepancies=None)

# Delete order
@app.route('/delete/<int:id>', methods=['POST'])
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
    app.run(host="0.0.0.0", port=5000, debug=True)
