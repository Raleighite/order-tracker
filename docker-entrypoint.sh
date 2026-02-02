#!/bin/sh
set -e
echo "🔧 Initializing database (if needed)..."
python - <<PY
from app import db
try:
    db.create_all()
    print('✅ Tables created or already exist')
except Exception as e:
    print('⚠️  Error creating tables:', e)
PY

echo "🚀 Starting Flask app"
exec python app.py
