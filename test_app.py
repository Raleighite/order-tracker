import unittest

from app import app, db, Order, LineItem
from flask import url_for
from datetime import datetime

class OrderTrackerTestCase(unittest.TestCase):
    def setUp(self):
        # Set up test client and in-memory test DB
        app.config["TESTING"] = True
        app.config["SQLALCHEMY_DATABASE_URI"] = 'sqlite:///:memory:'
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()
        
        with app.app_context():
            db.create_all()
            
    def tearDown(self):
        # Get rid of all the tables after the test
        with app.app_context():
            db.drop_all()
            
    def test_home_page_loads(self):
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Order Tracker', res.data)
        
    def test_add_order(self):
        # Simulate adding a new order
        res = self.client.post('/add', data={
            'vendor': "Test Vendor",
            'status': 'pending',
            'tracking_number': '12345',
            'product[]': ['Widget A'],
            'quantity[]': ['3']
        }, follow_redirects=True)
        
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Test Vendor', res.data)
        
        # Confirm order is in the DB
        with app.app_context():
            order = Order.query.first()
            self.assertIsNotNone(order)
            self.assertEqual(order.vendor, 'Test Vendor')
            self.assertEqual(order.items[0].product, 'Widget A')
            
    def test_view_orders(self):
        # Add directly to the db
        with app.app_context():
            order = Order(vendor='Vendor X', status='Pending', tracking_number='abc')
            db.session.add(order)
            db.session.commit()
            
        res = self.client.get('/orders')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Vendor X', res.data)
        
if __name__ == '__main__':
    unittest.main()