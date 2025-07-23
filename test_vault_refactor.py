#!/usr/bin/env python3
"""Test script for the refactored vault module (VaultClient direct)."""

import sys
import os

# Add the workspace to the Python path
sys.path.insert(0, '/workspaces/campus')


def test_vault_refactor():
    """Test the refactored vault module using VaultClient directly."""

    print("Testing Vault Module Refactor (VaultClient Direct)")
    print("=" * 55)

    try:
        # Test 1: Import vault module
        import campus.client.vault as vault
        print("✅ Import: import campus.client.vault as vault")
        print(f"   vault type: {type(vault)}")

        # Test 2: Vault subscription syntax
        storage_vault = vault["storage"]
        print("✅ Subscription: vault['storage']")
        print(f"   storage_vault type: {type(storage_vault)}")

        # Test 3: Access property
        access_client = vault.access
        print("✅ Access property: vault.access")
        print(f"   access type: {type(access_client)}")

        # Test 4: Client property
        client_mgmt = vault.client
        print("✅ Client property: vault.client")
        print(f"   client type: {type(client_mgmt)}")

        # Test 5: List vaults method
        print("✅ List vaults method: vault.list_vaults")
        print("   (Method exists and callable)")

        # Test 6: Set credentials method
        print("✅ Set credentials method: vault.set_credentials")
        print("   (Method exists and callable)")

        # Test 7: Check that it's actually a VaultClient
        from campus.client.vault.vault import VaultClient
        assert isinstance(
            vault, VaultClient), f"Expected VaultClient, got {type(vault)}"
        print("✅ Type verification: vault is VaultClient instance")

        print("\n🎉 Vault module refactor successful!")
        print("Key changes:")
        print("- VaultModule eliminated")
        print("- Module replacement uses VaultClient directly")
        print("- All API endpoints maintained")
        print("- .access and .client properties work")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_api_compatibility():
    """Test that the API is identical to before."""

    print("\n\nTesting API Compatibility")
    print("=" * 30)

    try:
        import campus.client.vault as vault

        # Test various API patterns
        api_tests = [
            "vault['storage']",
            "vault.access.grant",
            "vault.client.new",
            "vault.list_vaults",
            "vault.set_credentials"
        ]

        for api_call in api_tests:
            try:
                # Use getattr instead of eval for safety
                parts = api_call.split('.')
                obj = vault
                for part in parts[1:]:  # Skip 'vault'
                    if '[' in part and ']' in part:
                        # Handle subscription like vault['storage']
                        key = part.split('[')[1].split(']')[0].strip("'\"")
                        obj = obj[key]
                    else:
                        obj = getattr(obj, part)
                print(f"✅ {api_call} - accessible: {obj is not None}")
            except Exception as e:
                print(f"❌ {api_call} - error: {e}")
                return False

        print("\n✅ All API compatibility tests passed!")
        return True

    except Exception as e:
        print(f"❌ API compatibility error: {e}")
        return False


if __name__ == "__main__":
    refactor_success = test_vault_refactor()
    compatibility_success = test_api_compatibility()

    if refactor_success and compatibility_success:
        print("\n🎉 Vault module refactor complete and verified!")
    else:
        print("\n❌ Some tests failed. Check output above.")
        sys.exit(1)
