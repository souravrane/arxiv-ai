# PostgreSQL Setup Guide

This guide will help you set up PostgreSQL for the arXiv paper ingestion flow.

## Table of Contents

1. [Installation](#installation)
2. [Database Creation](#database-creation)
3. [User Setup](#user-setup)
4. [Connection Testing](#connection-testing)
5. [Environment Configuration](#environment-configuration)
6. [Troubleshooting](#troubleshooting)

## Installation

### Windows

1. **Download PostgreSQL:**
   - Visit https://www.postgresql.org/download/windows/
   - Download the PostgreSQL installer (recommended: latest stable version)
   - Run the installer and follow the setup wizard

2. **During Installation:**
   - Choose installation directory (default is fine)
   - Select components: PostgreSQL Server, pgAdmin 4, Command Line Tools
   - Set a password for the `postgres` superuser (remember this!)
   - Set port (default: 5432)
   - Set locale (default is fine)

3. **Verify Installation:**
   ```powershell
   psql --version
   ```

### macOS

**Using Homebrew (Recommended):**
```bash
brew install postgresql@15
brew services start postgresql@15
```

**Or download from:**
- Visit https://www.postgresql.org/download/macosx/
- Download and install the PostgreSQL.app or use the installer

**Verify Installation:**
```bash
psql --version
```

### Linux (Ubuntu/Debian)

```bash
# Update package list
sudo apt update

# Install PostgreSQL
sudo apt install postgresql postgresql-contrib

# Start PostgreSQL service
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Verify installation
psql --version
```

## Database Creation

### Method 1: Using psql Command Line

1. **Connect to PostgreSQL:**
   ```bash
   # Windows (use Command Prompt or PowerShell)
   psql -U postgres
   
   # macOS/Linux
   sudo -u postgres psql
   ```

2. **Create Database:**
   ```sql
   CREATE DATABASE arxiv_db;
   ```

3. **Verify Database:**
   ```sql
   \l
   ```
   You should see `arxiv_db` in the list.

4. **Exit psql:**
   ```sql
   \q
   ```

### Method 2: Using pgAdmin (Windows/macOS)

1. Open pgAdmin 4
2. Connect to your PostgreSQL server (use the password you set during installation)
3. Right-click on "Databases" → "Create" → "Database"
4. Name: `arxiv_db`
5. Click "Save"

## User Setup

### Option 1: Use Default postgres User (Simple, for development)

For development, you can use the default `postgres` user. Just use it in your `.env` file.

### Option 2: Create Dedicated User (Recommended for production)

1. **Connect to PostgreSQL:**
   ```bash
   psql -U postgres
   ```

2. **Create User:**
   ```sql
   CREATE USER arxiv_user WITH PASSWORD 'your_secure_password';
   ```

3. **Grant Privileges:**
   ```sql
   GRANT ALL PRIVILEGES ON DATABASE arxiv_db TO arxiv_user;
   ```

4. **Connect to arxiv_db and grant schema privileges:**
   ```sql
   \c arxiv_db
   GRANT ALL ON SCHEMA public TO arxiv_user;
   ```

5. **Exit:**
   ```sql
   \q
   ```

## Connection Testing

### Test Connection from Command Line

```bash
# Using postgres user
psql -U postgres -d arxiv_db

# Using custom user
psql -U arxiv_user -d arxiv_db -h localhost
```

If you can connect, you'll see a prompt like:
```
arxiv_db=#
```

Type `\q` to exit.

### Test Connection from Python

Create a test script `test_db_connection.py`:

```python
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

try:
    # Try DATABASE_URL first
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        conn = psycopg2.connect(database_url)
    else:
        # Use individual variables
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
        )
    
    cur = conn.cursor()
    cur.execute("SELECT version();")
    version = cur.fetchone()
    print(f"✓ Connected successfully!")
    print(f"PostgreSQL version: {version[0]}")
    
    cur.close()
    conn.close()
    
except Exception as e:
    print(f"✗ Connection failed: {e}")
```

Run it:
```bash
python test_db_connection.py
```

## Environment Configuration

### Create .env File

1. Copy the example file (if available):
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your database credentials:

   **Option 1: Using DATABASE_URL (Recommended)**
   ```env
   DATABASE_URL=postgresql://username:password@localhost:5432/arxiv_db
   ```
   
   Replace:
   - `username`: Your PostgreSQL username (e.g., `postgres` or `arxiv_user`)
   - `password`: Your PostgreSQL password
   - `localhost`: Database host (use `localhost` for local setup)
   - `5432`: Database port (default is 5432)
   - `arxiv_db`: Your database name

   **Option 2: Using Individual Variables**
   ```env
   DB_HOST=localhost
   DB_PORT=5432
   DB_NAME=arxiv_db
   DB_USER=postgres
   DB_PASSWORD=your_password
   ```

3. **Configure Other Settings:**
   ```env
   # arXiv Paper Categories (comma-separated)
   ARXIV_CATEGORIES=cs.AI,cs.LG,cs.CV,cs.CL,cs.NE
   
   # Rate Limiting (seconds between papers)
   RATE_LIMIT_SECONDS=4
   
   # Max Results Per Search
   MAX_RESULTS_PER_SEARCH=10
   ```

### Verify Configuration

The ingestion flow will automatically:
1. Validate your configuration on startup
2. Create the `papers` table if it doesn't exist
3. Create necessary indexes

You can also manually run the schema:
```bash
psql -U postgres -d arxiv_db -f schema.sql
```

## Troubleshooting

### Connection Refused

**Error:** `psycopg2.OperationalError: could not connect to server`

**Solutions:**
1. Check if PostgreSQL is running:
   ```bash
   # Windows
   Get-Service postgresql*
   
   # macOS/Linux
   sudo systemctl status postgresql
   ```

2. Start PostgreSQL if not running:
   ```bash
   # Windows
   net start postgresql-x64-15  # Version may vary
   
   # macOS
   brew services start postgresql@15
   
   # Linux
   sudo systemctl start postgresql
   ```

3. Check firewall settings (if connecting remotely)

### Authentication Failed

**Error:** `psycopg2.OperationalError: password authentication failed`

**Solutions:**
1. Verify username and password in `.env` file
2. Reset password if needed:
   ```sql
   ALTER USER postgres WITH PASSWORD 'new_password';
   ```
3. Check `pg_hba.conf` file (usually in PostgreSQL data directory)

### Database Does Not Exist

**Error:** `psycopg2.OperationalError: database "arxiv_db" does not exist`

**Solution:**
Create the database (see [Database Creation](#database-creation) section)

### Permission Denied

**Error:** `psycopg2.ProgrammingError: permission denied`

**Solutions:**
1. Grant privileges to your user:
   ```sql
   GRANT ALL PRIVILEGES ON DATABASE arxiv_db TO your_user;
   \c arxiv_db
   GRANT ALL ON SCHEMA public TO your_user;
   ```

2. Or use the `postgres` superuser for development

### Port Already in Use

**Error:** Port 5432 is already in use

**Solutions:**
1. Find what's using the port:
   ```bash
   # Windows
   netstat -ano | findstr :5432
   
   # macOS/Linux
   lsof -i :5432
   ```

2. Change PostgreSQL port in `postgresql.conf` or use a different port in `.env`

### Windows: psql Command Not Found

**Solution:**
Add PostgreSQL bin directory to PATH:
1. Find PostgreSQL installation (usually `C:\Program Files\PostgreSQL\15\bin`)
2. Add to System Environment Variables → Path
3. Restart terminal

## Next Steps

Once PostgreSQL is set up:

1. **Verify your `.env` file** has all required variables
2. **Test the connection** using the test script above
3. **Run the ingestion flow:**
   ```bash
   python ingestion/arxiv_ingestion_flow.py
   ```

The flow will automatically:
- Validate configuration
- Create the `papers` table
- Start ingesting papers from arXiv

## Additional Resources

- [PostgreSQL Official Documentation](https://www.postgresql.org/docs/)
- [psycopg2 Documentation](https://www.psycopg.org/docs/)
- [PostgreSQL Tutorial](https://www.postgresqltutorial.com/)

