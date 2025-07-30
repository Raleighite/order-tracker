from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

# Set up Flask app
app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(basedir, 'database.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Order model
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vendor = db.Column(db.String(100), nullable=False)
    date_ordered = db.Column(db.DateTime, default=datetime.now)
    status = db.Column(db.String(20), default='Pending')
    tracking_number = db.Column(db.String(100))
    items = db.relationship('LineItem', backref='order', cascade="all, delete", lazy=True)

# Line item model
class LineItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)

# Home route
@app.route('/')
def index():
    return render_template('index.html')

# View all orders
@app.route('/orders')
def view_orders():
    orders = Order.query.order_by(Order.date_ordered.desc()).all()
    return render_template('orders.html', orders=orders)

# Add new order
@app.route('/add', methods=['GET', 'POST'])
def add_order():
    if request.method == 'POST':
        try:
            vendor = request.form['vendor']
            status = request.form['status']
            tracking_number = request.form['tracking_number']

            new_order = Order(vendor=vendor, status=status, tracking_number=tracking_number)
            db.session.add(new_order)
            db.session.commit()

            products = request.form.getlist('product[]')
            quantities = request.form.getlist('quantity[]')

            for product, qty in zip(products, quantities):
                if not product.strip():
                    continue
                try:
                    quantity = int(qty)
                except ValueError:
                    quantity = 1  # fallback
                item = LineItem(product=product, quantity=quantity, order_id=new_order.id)
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
    app.run(debug=True)
