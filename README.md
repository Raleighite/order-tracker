# 📦 Order Tracker

![Test Status](https://github.com/Raleighite/order-tracker/actions/workflows/python-tests.yml/badge.svg)

A simple, fast, and extensible order tracking tool built with Flask and SQLite — designed to help manage and organize inventory orders for your online store.

This lightweight app runs locally and gives you a clear interface to view, update, and track orders from your vendors. Perfect for ecommerce owners managing multiple inbound shipments.

---

## ✨ Features

- 🧾 Add and view incoming inventory orders
- 🛍 Track multiple line items per order (each with quantity)
- 🚚 Record shipping status and tracking numbers
- ⚠️ Highlight overdue unshipped orders (7+ days)
- 🛠 Edit and delete orders easily
- 🔐 Runs locally with no cloud dependencies
- ✅ Automatically tested with GitHub Actions on every push

---

## 🖥 Tech Stack

- [Python 3.x](https://www.python.org/)
- [Flask](https://flask.palletsprojects.com/)
- [SQLite (via SQLAlchemy)](https://docs.sqlalchemy.org/)
- [Bootstrap 5](https://getbootstrap.com/)
- [GitHub Actions](https://docs.github.com/en/actions) for CI testing

---

## 🚀 Getting Started

### 🧰 Setup

1. **Clone the repo**
   ```bash
   git clone https://github.com/Raleighite/order-tracker.git
   cd order-tracker
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   # OR
   source venv/bin/activate  # macOS/Linux
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the app**
   ```bash
   python app.py
   ```

5. Open your browser to [http://localhost:5000](http://localhost:5000)

---

### 🧪 Running Tests

```bash
python test_app.py
```

Tests run automatically on every push via GitHub Actions.

---

## 🔮 Planned Improvements

- ✅ CSV export for reports
- 🔍 Search and filter interface
- 📧 Email notifications for overdue orders
- ☁️ Optional cloud deployment (Railway, Render, etc.)
- 🛠 MongoDB support (planned as optional future backend)

---

## 🛡 License

MIT License © Travis Bailey
