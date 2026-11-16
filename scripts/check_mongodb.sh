#!/bin/bash
# MongoDB connectivity check script for Campus development

set -e

# MongoDB connection parameters (matching devcontainer setup)
export MONGODB_HOST=${MONGODB_HOST:-mongo}
export MONGODB_PORT=${MONGODB_PORT:-27017}
export MONGO_INITDB_ROOT_USERNAME=${MONGO_INITDB_ROOT_USERNAME:-devuser}
export MONGO_INITDB_ROOT_PASSWORD=${MONGO_INITDB_ROOT_PASSWORD:-devpass}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Show MongoDB status
show_mongodb_status() {
    echo -e "${BLUE}🔍 MongoDB Server Status:${NC}"
    
    # Check if MongoDB client is available
    if command -v mongosh &> /dev/null; then
        echo "✅ mongosh client found"
        
        # Test connection
        if mongosh "mongodb://$MONGO_INITDB_ROOT_USERNAME:$MONGO_INITDB_ROOT_PASSWORD@$MONGODB_HOST:$MONGODB_PORT/" --eval "db.runCommand('ping')" --quiet; then
            echo "✅ MongoDB connection successful"
            
            # Show server version
            echo -n "📋 Server Version: "
            mongosh "mongodb://$MONGO_INITDB_ROOT_USERNAME:$MONGO_INITDB_ROOT_PASSWORD@$MONGODB_HOST:$MONGODB_PORT/" --eval "db.version()" --quiet 2>/dev/null || echo "Could not get version"
        else
            echo -e "${RED}❌ MongoDB connection failed${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️  mongosh client not found${NC}"
        echo "   Try: npm install -g mongosh"
    fi
    echo ""
}

# Show connection details
show_connection_details() {
    echo -e "${BLUE}🔌 DevContainer Connection Details:${NC}"
    echo "   Host: $MONGODB_HOST (Docker service)"
    echo "   Port: $MONGODB_PORT"
    echo "   Username: $MONGO_INITDB_ROOT_USERNAME"
    echo "   Password: $MONGO_INITDB_ROOT_PASSWORD"
    echo ""
    
    echo -e "${BLUE}🔗 Connection String:${NC}"
    echo "   mongodb://$MONGO_INITDB_ROOT_USERNAME:$MONGO_INITDB_ROOT_PASSWORD@$MONGODB_HOST:$MONGODB_PORT/"
    echo ""
}

# Show databases
show_databases() {
    echo -e "${BLUE}🗃️  Available Databases:${NC}"
    if command -v mongosh &> /dev/null; then
        if mongosh "mongodb://$MONGO_INITDB_ROOT_USERNAME:$MONGO_INITDB_ROOT_PASSWORD@$MONGODB_HOST:$MONGODB_PORT/" --eval "db.adminCommand('listDatabases')" --quiet 2>/dev/null; then
            echo ""
        else
            echo "   Could not retrieve database list"
        fi
    else
        echo -e "${YELLOW}   mongosh not available${NC}"
    fi
    echo ""
}

# Test campus connection
test_campus_connection() {
    echo -e "${BLUE}🧪 Testing Campus MongoDB Connection:${NC}"
    
    if command -v mongosh &> /dev/null; then
        echo "   Testing storagedb..."
        if mongosh "mongodb://$MONGO_INITDB_ROOT_USERNAME:$MONGO_INITDB_ROOT_PASSWORD@$MONGODB_HOST:$MONGODB_PORT/storagedb" --eval "db.runCommand('ping')" --quiet 2>/dev/null; then
            echo "   ✅ storagedb connection successful"
        else
            echo -e "   ${RED}❌ Could not connect to storagedb${NC}"
        fi
    else
        echo -e "${YELLOW}   mongosh not available${NC}"
    fi
    echo ""
}

# Main function
main() {
    echo -e "${GREEN}🚀 Campus MongoDB Connectivity Check${NC}"
    echo "================================================="
    echo ""
    
    show_connection_details
    show_mongodb_status
    
    # Check if we can connect from the devcontainer
    if docker ps | grep -q mongo; then
        show_databases
        test_campus_connection
    else
        echo -e "${YELLOW}💡 MongoDB is running in Docker container 'mongo'${NC}"
        echo "   Check if the devcontainer is properly started"
        echo "   Try: docker-compose up -d"
        echo ""
    fi
    
    echo -e "${BLUE}💡 Useful commands:${NC}"
    echo "   Connect to MongoDB: mongosh mongodb://$MONGO_INITDB_ROOT_USERNAME:$MONGO_INITDB_ROOT_PASSWORD@$MONGODB_HOST:$MONGODB_PORT/"
    echo "   Connect to storagedb: mongosh mongodb://$MONGO_INITDB_ROOT_USERNAME:$MONGO_INITDB_ROOT_PASSWORD@$MONGODB_HOST:$MONGODB_PORT/storagedb"
    echo "   List databases: mongosh mongodb://$MONGO_INITDB_ROOT_USERNAME:$MONGO_INITDB_ROOT_PASSWORD@$MONGODB_HOST:$MONGODB_PORT/ --eval 'show dbs'"
}

main "$@"
