#!/usr/bin/env python3
"""
Simple demo data loader for Order Tracker.
Run with: ./venv/bin/python scripts/populate_demo.py
"""
from app import app, db, Vendor, Order, LineItem, Inventory
from datetime import datetime

with app.app_context():
    db.create_all()
    v = Vendor(name='Demo Vendor', platform='Demo')
    db.session.add(v)
    db.session.commit()
    o = Order(vendor='Demo Vendor', vendor_id=v.id, status='Pending', tracking_number='demo-123')
    db.session.add(o)
    db.session.commit()
    li = LineItem(product='Demo Card Pack', quantity=10, cost=2.5, upc='123456789012')
    li.order_id = o.id
    db.session.add(li)
    db.session.commit()
    inv = Inventory(product='Demo Card Pack', upc='123456789012', quantity=5, vendor_id=v.id)
    db.session.add(inv)
    db.session.commit()
    print('Demo data inserted')
