# 📦 Order Tracker

![Unit Tests](https://github.com/Raleighite/order-tracker/actions/workflows/python-tests.yml/badge.svg)
![Smoke Test](https://github.com/Raleighite/order-tracker/actions/workflows/ci-smoke.yml/badge.svg)

A simple, fast, and extensible order tracking tool built with Flask and SQLite — designed to help manage and organize inventory orders for your online store.

This lightweight app runs locally and gives you a clear interface to view, update, and track orders from your vendors. Perfect for ecommerce owners managing multiple inbound shipments.

---

## ✨ Features

- 🧾 Add and view incoming inventory orders
- 🛍 Track multiple line items per order (each with quantity)
- 🚚 Record shipping status and tracking numbers
- ⚠️ Highlight overdue unshipped orders (7+ days)
- 🛠 Edit and delete orders easily
- 🔐 Runs locally or in Docker — no cloud dependencies
- ✅ Automatically tested with GitHub Actions on every push

---

## 🖥 Tech Stack

- [Python 3.x](https://www.python.org/)
- [Flask](https://flask.palletsprojects.com/)
- [SQLite (via SQLAlchemy)](https://docs.sqlalchemy.org/)
- [Bootstrap 5](https://getbootstrap.com/)
- [Docker](https://www.docker.com/)
- [GitHub Actions](https://docs.github.com/en/actions)

---

## 🚀 Getting Started

### 🧰 Local Setup (without Docker)

1. **Clone the repo**

   ```bash
   git clone https://github.com/Raleighite/order-tracker.git
   cd order-tracker
   ```

2. **Create and activate a virtual environment**
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

5. Visit [http://localhost:5000](http://localhost:5000)

---

### 🐳 Running with Docker

1. **Build the Docker image**
   ```bash
   docker build -t order-tracker .
   ```

2. **Run the container**

   ```bash
   docker run -p 5001:5000 order-tracker
   ```

3. Visit [http://localhost:5001](http://localhost:5001)

---

## Continuous Integration

This repository includes two CI checks:

- Unit tests: run on every push/PR (see `.github/workflows/python-tests.yml`).
- Smoke test: a Docker-based smoke workflow (`.github/workflows/ci-smoke.yml`) builds the image, starts the container, performs a quick smoke test (create vendor, create order, verify vendor page), and fails the job if any step fails.

You can run the smoke test locally with the helper script:

```bash
./scripts/dev.sh smoke
```

The smoke workflow in CI exposes the app on port 5000 within the runner; locally we avoid a common macOS port conflict by using host port 5001. Adjust the port mapping if you want to use 5000 locally.

---

### 🧪 Running Tests

```bash
python test_app.py
```

Or push to GitHub and let [GitHub Actions](https://github.com/Raleighite/order-tracker/actions) run them automatically.

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
