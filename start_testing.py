#!/usr/bin/env python3
"""
Start All Campus Services for Testing

This script starts all campus services in the correct dependency order:
1. campus.vault (foundation service)
2. campus.apps (depends on vault + yapper database)

Note: Yapper is a database wrapper (not a service) and is initialized during setup.
Each service is started in the background and health-checked before starting the next.
"""
import os
import signal
import subprocess
import sys
import time
import requests
from urllib.parse import urljoin

from tests.fixtures import require

# Add the project root to Python path so we can import from tests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# Service configuration
SERVICES = [
    {
        'name': 'vault',
        'display_name': 'Campus Vault',
        'deploy': 'vault',
        'port': '8080',
        'url': 'http://127.0.0.1:8080',
        'health_endpoint': '/',
        'emoji': '🔐'
    },
    {
        'name': 'apps',
        'display_name': 'Campus Apps',
        'deploy': 'apps',
        'port': '8081',
        'url': 'http://127.0.0.1:8081',
        'health_endpoint': '/',
        'emoji': '🏫'
    }
]

# Global list to track running processes
running_processes = []


def cleanup_processes():
    """Clean up all running processes on exit."""
    print("\n🛑 Shutting down all services...")
    for proc in running_processes:
        if proc.poll() is None:  # Process is still running
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    print("✅ All services stopped")


def signal_handler(signum, frame):
    """Handle interrupt signals to clean up processes."""
    cleanup_processes()
    sys.exit(0)


def wait_for_health_check(service, timeout=30):
    """Wait for a service to become healthy."""
    print(f"⏳ Waiting for {service['display_name']} to become healthy...")

    url = urljoin(service['url'], service['health_endpoint'])
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                print(f"✅ {service['display_name']} is healthy")
                return True
        except requests.RequestException:
            # Service not ready yet, keep waiting
            pass

        time.sleep(1)

    print(
        f"❌ {service['display_name']} failed to become healthy within {timeout}s")
    return False


def start_service(service):
    """Start a campus service in the background."""
    print(
        f"{service['emoji']} Starting {service['display_name']} on {service['url']}")

    # Set up environment for this service
    env = os.environ.copy()
    env.update({
        'DEPLOY': service['deploy'],
        'ENV': 'testing',
        'HOST': '127.0.0.1',
        'PORT': service['port']
    })

    # Start the service
    try:
        proc = subprocess.Popen(
            [sys.executable, 'main.py'],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        running_processes.append(proc)
        print(f"✅ {service['display_name']} started (PID: {proc.pid})")
        return proc
    except Exception as e:
        print(f"❌ Failed to start {service['display_name']}: {e}")
        return None


def main():
    """Main function to start all services."""
    # Set up signal handlers for clean shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("🚀 Starting Campus Testing Services")
    print("=" * 40)
    print("")

    # Ensure we're in testing environment and have credentials
    try:
        require.env("testing")
        require.envvar("CLIENT_ID")
        require.envvar("CLIENT_SECRET")
    except RuntimeError as e:
        print(f"❌ Environment check failed: {e}")
        print("💡 Run './setup_testing.py' first to set up the testing environment")
        sys.exit(1)

    print("✅ Environment and credentials verified")
    print("")

    # Start services sequentially with health checks
    for i, service in enumerate(SERVICES):
        print(f"Step {i+1}/{len(SERVICES)}: {service['display_name']}")
        print("-" * 30)

        # Start the service
        proc = start_service(service)
        if not proc:
            cleanup_processes()
            sys.exit(1)

        # Wait for health check
        if not wait_for_health_check(service):
            cleanup_processes()
            sys.exit(1)

        print("")

    print("🎉 All services are running and healthy!")
    print("")
    print("🌐 Service URLs:")
    for service in SERVICES:
        print(
            f"   {service['emoji']} {service['display_name']}: {service['url']}")
    print("")
    print("💡 Tips:")
    print("   - VS Code will auto-detect these ports for forwarding")
    print("   - Press Ctrl+C to stop all services")
    print("   - Check service logs if any issues occur")
    print("")
    print("⏸️  Services running... (Press Ctrl+C to stop)")

    # Keep the script running and monitor processes
    try:
        while True:
            # Check if any processes have died
            for i, proc in enumerate(running_processes):
                if proc.poll() is not None:
                    service = SERVICES[i]
                    print(
                        f"⚠️  {service['display_name']} has stopped unexpectedly")
                    cleanup_processes()
                    sys.exit(1)

            time.sleep(5)
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)


if __name__ == '__main__':
    main()
