#!/bin/bash
# PostgreSQL Status Checker and Connection Details

echo "🐘 PostgreSQL Status Checker"
echo "================================"
echo ""

# Check if PostgreSQL is running (in devcontainer, it's in the 'db' service)
check_postgres_running() {
    if PGPASSWORD=devpass psql -h db -U devuser -d storagedb -t -c "SELECT 1;" > /dev/null 2>&1; then
        echo "✅ PostgreSQL is running (in db container)"
        return 0
    else
        echo "❌ PostgreSQL is not accessible"
        return 1
    fi
}

# Get PostgreSQL version
get_postgres_version() {
    if command -v psql > /dev/null; then
        echo "📋 PostgreSQL Client Version:"
        psql --version
        echo ""
        
        # Try to connect and get server version
        echo "📋 PostgreSQL Server Version:"
        if PGPASSWORD=devpass psql -h db -U devuser -d storagedb -t -A -c "SELECT version();" 2>/dev/null; then
            echo ""
        else
            echo "   Could not connect to get server version"
            echo ""
        fi
    else
        echo "⚠️  psql client not found"
        echo ""
    fi
}

# Show connection details
show_connection_details() {
    echo "🔌 DevContainer Connection Details:"
    echo "   Host: db (Docker service)"
    echo "   Port: 5432"
    echo "   User: devuser"
    echo "   Password: devpass"
    echo ""
    
    echo "📊 Available Databases:"
    echo "   - storagedb (main storage database)"
    echo "   - vaultdb (vault database)"
    echo "   - yapperdb (yapper database)"
    echo ""
    
    echo "🔗 Connection Strings:"
    echo "   Storage: postgresql://devuser:devpass@db:5432/storagedb"
    echo "   Vault: postgresql://devuser:devpass@db:5432/vaultdb"
    echo "   Yapper: postgresql://devuser:devpass@db:5432/yapperdb"
    echo ""
}

# Show active connections
show_active_connections() {
    echo "🔗 Active Connections:"
    if PGPASSWORD=devpass psql -h db -U devuser -d storagedb -t -A -c "SELECT datname, usename, client_addr, state FROM pg_stat_activity WHERE state = 'active';" 2>/dev/null; then
        echo ""
    else
        echo "   Could not retrieve connection information"
        echo ""
    fi
}

# Show database list
show_databases() {
    echo "🗃️  Available Databases:"
    if PGPASSWORD=devpass psql -h db -U devuser -l -t -A 2>/dev/null | grep -v "^$" | head -10; then
        echo ""
    else
        echo "   Could not retrieve database list"
        echo ""
    fi
}

# Test specific connection
test_campus_connection() {
    echo "🧪 Testing Database Connections:"
    
    echo "   Testing storagedb..."
    if PGPASSWORD=devpass psql -h db -U devuser -d storagedb -t -A -c "SELECT 'storagedb connection successful' as status;" 2>/dev/null | grep -q "successful"; then
        echo "   ✅ storagedb connection successful"
    else
        echo "   ❌ Could not connect to storagedb"
    fi
    
    echo "   Testing vaultdb..."
    if PGPASSWORD=devpass psql -h db -U devuser -d vaultdb -t -A -c "SELECT 'vaultdb connection successful' as status;" 2>/dev/null | grep -q "successful"; then
        echo "   ✅ vaultdb connection successful"
    else
        echo "   ❌ Could not connect to vaultdb"
    fi
    
    echo "   Testing yapperdb..."
    if PGPASSWORD=devpass psql -h db -U devuser -d yapperdb -t -A -c "SELECT 'yapperdb connection successful' as status;" 2>/dev/null | grep -q "successful"; then
        echo "   ✅ yapperdb connection successful"
    else
        echo "   ❌ Could not connect to yapperdb"
    fi
    echo ""
}

# Main execution
main() {
    check_postgres_running
    postgres_running=$?
    
    echo ""
    get_postgres_version
    show_connection_details
    
    if [ $postgres_running -eq 0 ]; then
        show_active_connections
        show_databases
        test_campus_connection
    else
        echo "💡 PostgreSQL is running in Docker container 'db'"
        echo "   Check if the devcontainer is properly started"
        echo "   Try: docker-compose up -d"
        echo ""
    fi
    
    echo "💡 Useful commands:"
    echo "   Connect to storagedb: PGPASSWORD=devpass psql -h db -U devuser -d storagedb"
    echo "   Connect to vaultdb: PGPASSWORD=devpass psql -h db -U devuser -d vaultdb"
    echo "   Connect to yapperdb: PGPASSWORD=devpass psql -h db -U devuser -d yapperdb"
    echo "   List databases: PGPASSWORD=devpass psql -h db -U devuser -l"
}

main "$@"
