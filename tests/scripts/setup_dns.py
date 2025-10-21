#!/usr/bin/env python3
"""
Setup DNS Mappings for Campus Testing

This script sets up the /etc/hosts entries needed for Campus testing domains.
This allows the integration tests to use realistic domain names instead of raw IP addresses.
"""
import os
import subprocess
import sys


DNS_MAPPINGS = [
    "# Campus Testing DNS Mappings",
    "127.0.0.1    apps.campus.testing",
    "127.0.0.1    vault.campus.testing"
]


def check_existing_mappings():
    """Check if DNS mappings are already configured."""
    try:
        with open('/etc/hosts', 'r') as f:
            hosts_content = f.read()

        # Check if all our mappings already exist
        missing_mappings = []
        for mapping in DNS_MAPPINGS:
            if mapping.startswith('#'):
                continue  # Skip comments
            if mapping not in hosts_content:
                missing_mappings.append(mapping)

        return missing_mappings
    except Exception as e:
        print(f"❌ Error reading /etc/hosts: {e}")
        return DNS_MAPPINGS[1:]  # Return all non-comment mappings


def add_dns_mappings():
    """Add DNS mappings to /etc/hosts if they don't exist."""
    print("🌐 Setting up Campus Testing DNS mappings...")

    missing_mappings = check_existing_mappings()

    if not missing_mappings:
        print("✅ DNS mappings already configured")
        return True

    print(f"📝 Adding {len(missing_mappings)} DNS mapping(s)...")

    try:
        # Add the missing mappings
        mappings_text = '\n'.join([''] + DNS_MAPPINGS + [''])

        # Use sudo to append to /etc/hosts
        process = subprocess.Popen(
            ['sudo', 'tee', '-a', '/etc/hosts'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        stdout, stderr = process.communicate(input=mappings_text)

        if process.returncode == 0:
            print("✅ DNS mappings added successfully")
            return True
        else:
            print(f"❌ Failed to add DNS mappings: {stderr}")
            return False

    except Exception as e:
        print(f"❌ Error adding DNS mappings: {e}")
        return False


def verify_dns_mappings():
    """Verify that DNS mappings are working."""
    print("🔍 Verifying DNS mappings...")

    test_domains = ['apps.campus.testing', 'vault.campus.testing']

    for domain in test_domains:
        try:
            result = subprocess.run(
                ['getent', 'hosts', domain],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0 and '127.0.0.1' in result.stdout:
                print(f"✅ {domain} → 127.0.0.1")
            else:
                print(f"❌ {domain} DNS resolution failed")
                return False

        except Exception as e:
            print(f"❌ Error testing {domain}: {e}")
            return False

    print("✅ All DNS mappings verified")
    return True


def main():
    """Main function."""
    print("🏫 Campus Testing DNS Setup")
    print("=" * 30)
    print("")

    # Check if running with appropriate privileges
    if os.geteuid() != 0:
        # We're not root, but that's OK - we'll use sudo for the file write
        pass

    # Add DNS mappings
    if not add_dns_mappings():
        sys.exit(1)

    print("")

    # Verify mappings
    if not verify_dns_mappings():
        sys.exit(1)

    print("")
    print("🎉 DNS setup complete!")
    print("")
    print("💡 Testing domains configured:")
    print("   📍 apps.campus.testing:8081  → Campus Apps service")
    print("   📍 vault.campus.testing:8080 → Campus Vault service")
    print("")
    print("🚀 Ready for integration testing with realistic domain names!")


if __name__ == '__main__':
    main()
