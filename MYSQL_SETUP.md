# MySQL Setup Guide

This guide will help you set up MySQL for the arXiv paper ingestion flow.

## Table of Contents

1. [Installation](#installation)
2. [Database Creation](#database-creation)
3. [User Setup](#user-setup)
4. [Connection Testing](#connection-testing)
5. [Environment Configuration](#environment-configuration)
6. [Troubleshooting](#troubleshooting)

## Installation

### Windows

1. **Download MySQL:**

   - Visit https://dev.mysql.com/downloads/installer/
   - Download MySQL Installer (recommended: MySQL Installer for Windows)
   - Run the installer and follow the setup wizard

2. **During Installation:**

   - Choose "Developer Default" or "Server only"
   - Set a password for the `root` user (remember this!)
   - Set port (default: 3306)
   - Complete the installation

3. **Verify Installation:**
   ```powershell
   mysql --version
   ```

### macOS

**Using Homebrew (Recommended):**

```bash
brew install mysql
brew services start mysql
```

**Or download from:**

- Visit https://dev.mysql.com/downloads/mysql/
- Download and install the MySQL Community Server DMG

**Verify Installation:**

```bash
mysql --version
```

**Secure Installation (First Time Setup):**

```bash
mysql_secure_installation
```

This will help you set up a root password and secure your installation.

### Linux (Ubuntu/Debian)

```bash
# Update package list
sudo apt update

# Install MySQL
sudo apt install mysql-server

# Start MySQL service
sudo systemctl start mysql
sudo systemctl enable mysql

# Secure installation
sudo mysql_secure_installation

# Verify installation
mysql --version
```

## Database Creation

### Method 1: Using mysql Command Line

1. **Connect to MySQL:**

   ```bash
   # macOS/Linux
   mysql -u root -p

   # Windows (if MySQL is in PATH)
   mysql -u root -p
   ```

   Enter your root password when prompted.

2. **Create Database:**

   ```sql
   CREATE DATABASE arxiv_db;
   ```

3. **Verify Database:**

   ```sql
   SHOW DATABASES;
   ```

   You should see `arxiv_db` in the list.

4. **Exit mysql:**
   ```sql
   EXIT;
   ```

### Method 2: Using MySQL Workbench (Windows/macOS)

1. Open MySQL Workbench
2. Connect to your MySQL server (use the password you set during installation)
3. Right-click in the left panel → "Create Schema"
4. Name: `arxiv_db`
5. Click "Apply"

## User Setup

### Option 1: Use Default root User (Simple, for development)

For development, you can use the default `root` user. Just use it in your `.env` file.

### Option 2: Create Dedicated User (Recommended for production)

1. **Connect to MySQL:**

   ```bash
   mysql -u root -p
   ```

2. **Create User:**

   ```sql
   CREATE USER 'arxiv_user'@'localhost' IDENTIFIED BY 'your_secure_password';
   ```

3. **Grant Privileges:**

   ```sql
   GRANT ALL PRIVILEGES ON arxiv_db.* TO 'arxiv_user'@'localhost';
   FLUSH PRIVILEGES;
   ```

4. **Exit:**
   ```sql
   EXIT;
   ```

## Connection Testing

### Test Connection from Command Line

```bash
# Using root user
mysql -u root -p -D arxiv_db

# Using custom user
mysql -u arxiv_user -p -D arxiv_db -h localhost
```

If you can connect, you'll see a prompt like:

```
mysql>
```

Type `EXIT;` to exit.

### Test Connection from Python

Create a test script `test_db_connection.py`:

```python
import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

try:
    # Try DATABASE_URL first
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        from urllib.parse import urlparse
        parsed = urlparse(database_url)
        conn = mysql.connector.connect(
            host=parsed.hostname or "localhost",
            port=int(parsed.port) if parsed.port else 3306,
            database=parsed.path.lstrip('/'),
            user=parsed.username,
            password=parsed.password
        )
    else:
        # Use individual variables
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "3306")),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
        )

    cur = conn.cursor()
    cur.execute("SELECT VERSION();")
    version = cur.fetchone()
    print(f"✓ Connected successfully!")
    print(f"MySQL version: {version[0]}")

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
   DATABASE_URL=mysql://username:password@localhost:3306/arxiv_db
   ```

   Replace:

   - `username`: Your MySQL username (e.g., `root` or `arxiv_user`)
   - `password`: Your MySQL password
   - `localhost`: Database host (use `localhost` for local setup)
   - `3306`: Database port (default is 3306)
   - `arxiv_db`: Your database name

   **Option 2: Using Individual Variables**

   ```env
   DB_HOST=localhost
   DB_PORT=3306
   DB_NAME=arxiv_db
   DB_USER=root
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
mysql -u root -p arxiv_db < schema.sql
```

## Troubleshooting

### Connection Refused

**Error:** `mysql.connector.errors.InterfaceError: 2003: Can't connect to MySQL server`

**Solutions:**

1. Check if MySQL is running:

   ```bash
   # Windows
   Get-Service MySQL*

   # macOS
   brew services list | grep mysql

   # Linux
   sudo systemctl status mysql
   ```

2. Start MySQL if not running:

   ```bash
   # Windows
   net start MySQL80  # Version may vary

   # macOS
   brew services start mysql

   # Linux
   sudo systemctl start mysql
   ```

3. Check firewall settings (if connecting remotely)

### Authentication Failed

**Error:** `mysql.connector.errors.ProgrammingError: Access denied for user`

**Solutions:**

1. Verify username and password in `.env` file
2. Reset password if needed:
   ```sql
   ALTER USER 'root'@'localhost' IDENTIFIED BY 'new_password';
   FLUSH PRIVILEGES;
   ```
3. Check user privileges:
   ```sql
   SHOW GRANTS FOR 'your_user'@'localhost';
   ```

### Database Does Not Exist

**Error:** `mysql.connector.errors.ProgrammingError: Unknown database 'arxiv_db'`

**Solution:**
Create the database (see [Database Creation](#database-creation) section)

### Permission Denied

**Error:** `mysql.connector.errors.ProgrammingError: Access denied`

**Solutions:**

1. Grant privileges to your user:

   ```sql
   GRANT ALL PRIVILEGES ON arxiv_db.* TO 'your_user'@'localhost';
   FLUSH PRIVILEGES;
   ```

2. Or use the `root` user for development

### Port Already in Use

**Error:** Port 3306 is already in use

**Solutions:**

1. Find what's using the port:

   ```bash
   # Windows
   netstat -ano | findstr :3306

   # macOS/Linux
   lsof -i :3306
   ```

2. Change MySQL port in `my.cnf` or use a different port in `.env`

### macOS: mysql Command Not Found

**Solution:**
Add MySQL bin directory to PATH:

```bash
# For Homebrew installation
echo 'export PATH="/opt/homebrew/opt/mysql/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### JSON Support

MySQL 5.7+ has native JSON support. If you're using an older version, you may need to upgrade:

```bash
# Check MySQL version
mysql --version

# Upgrade if needed (macOS)
brew upgrade mysql
```

## Next Steps

Once MySQL is set up:

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

- [MySQL Official Documentation](https://dev.mysql.com/doc/)
- [mysql-connector-python Documentation](https://dev.mysql.com/doc/connector-python/en/)
- [MySQL Tutorial](https://www.mysqltutorial.org/)
