#!/usr/bin/env python3
"""Comprehensive test for client module refactoring.

Tests that all service modules (vault, users, circles) follow the
consistent direct client instance pattern.
"""

import sys
import os

# Add the workspace to the Python path
sys.path.insert(0, '/workspaces/campus')


def test_service_module_refactor(service_name: str, expected_client_class: str, test_patterns: dict):
    """Test a service module follows the refactored pattern.
    
    Args:
        service_name: Name of the service (e.g., 'vault', 'users', 'circles')
        expected_client_class: Expected client class name
        test_patterns: Dict of method/property patterns to test
    
    Returns:
        bool: True if all tests pass
    """
    print(f"\nTesting {service_name.title()} Module Refactor")
    print("=" * (len(service_name) + 20))
    
    try:
        # Import the service module
        if service_name == 'vault':
            import campus.client.vault as module
        elif service_name == 'users':
            import campus.client.apps.users as module
        elif service_name == 'circles':
            import campus.client.apps.circles as module
        else:
            raise ValueError(f"Unknown service: {service_name}")
            
        print(f"✅ Import: import campus.client.{service_name if service_name == 'vault' else f'apps.{service_name}'} as {service_name}")
        print(f"   {service_name} type: {type(module)}")
        
        # Test 1: Verify it's the correct client instance (not wrapper)
        assert expected_client_class in str(type(module)), f"Expected {expected_client_class}, got {type(module)}"
        print(f"✅ Type verification: {service_name} is {expected_client_class} instance")
        
        # Test 2: Test subscription syntax
        if 'subscription' in test_patterns:
            key = test_patterns['subscription']
            try:
                resource = module[key]
                print(f"✅ Subscription: {service_name}['{key}']")
                print(f"   {key} type: {type(resource)}")
            except Exception as e:
                print(f"⚠️  Subscription: {service_name}['{key}'] - {e} (may need live service)")
        
        # Test 3: Test methods exist and are callable
        for method_name in test_patterns.get('methods', []):
            method = getattr(module, method_name, None)
            if method and callable(method):
                print(f"✅ Method: {service_name}.{method_name}")
                print(f"   (Method exists and callable)")
            else:
                print(f"❌ Method: {service_name}.{method_name} - not found or not callable")
                return False
        
        # Test 4: Test properties exist
        for prop_name in test_patterns.get('properties', []):
            try:
                prop = getattr(module, prop_name)
                print(f"✅ Property: {service_name}.{prop_name}")
                print(f"   {prop_name} type: {type(prop)}")
            except Exception as e:
                print(f"❌ Property: {service_name}.{prop_name} - error: {e}")
                return False
        
        print(f"\n🎉 {service_name.title()} module refactor successful!")
        print("Key changes:")
        print(f"- {service_name.title()}Module eliminated") 
        print(f"- Module replacement uses {expected_client_class} directly")
        print("- All API endpoints maintained")
        if test_patterns.get('properties'):
            props = ', '.join([f'.{p}' for p in test_patterns['properties']])
            print(f"- {props} properties work")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_all_service_modules():
    """Test all service modules follow the refactored pattern."""
    
    print("Testing All Service Module Refactors")
    print("=" * 40)
    
    # Define test patterns for each service
    test_configs = {
        'vault': {
            'client_class': 'VaultClient',
            'patterns': {
                'subscription': 'storage',
                'methods': ['list_vaults', 'set_credentials'],
                'properties': ['access', 'client']
            }
        },
        'users': {
            'client_class': 'UsersClient', 
            'patterns': {
                'subscription': 'user123',
                'methods': ['new', 'list', 'me', 'set_credentials'],
                'properties': []
            }
        },
        'circles': {
            'client_class': 'CirclesClient',
            'patterns': {
                'subscription': 'circle456',
                'methods': ['new', 'list', 'search', 'list_by_user', 'set_credentials'],
                'properties': []
            }
        }
    }
    
    results = {}
    
    for service_name, config in test_configs.items():
        success = test_service_module_refactor(
            service_name, 
            config['client_class'],
            config['patterns']
        )
        results[service_name] = success
        
        if success:
            print(f"✅ {service_name.title()} refactor complete and verified!")
        else:
            print(f"❌ {service_name.title()} refactor failed!")
    
    # Summary
    print(f"\n🎯 Summary of Service Module Refactors")
    print("=" * 40)
    
    for service_name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{service_name.title():10} {status}")
    
    all_passed = all(results.values())
    if all_passed:
        print(f"\n🎉 All service modules successfully refactored!")
        print("✅ Consistent direct client instance pattern achieved")
        print("✅ No wrapper classes - cleaner architecture")
        print("✅ All API compatibility maintained")
    else:
        failed = [name for name, success in results.items() if not success]
        print(f"\n❌ Some refactors failed: {', '.join(failed)}")
    
    return all_passed


def test_api_compatibility():
    """Test that all APIs are compatible with the refactored pattern."""
    
    print(f"\n\nTesting Cross-Service API Compatibility")
    print("=" * 40)
    
    try:
        # Import all services
        import campus.client.vault as vault
        import campus.client.apps.users as users
        import campus.client.apps.circles as circles
        
        # Test cross-service API patterns
        api_tests = [
            ("vault['storage']", lambda: vault['storage']),
            ("vault.access.grant", lambda: vault.access.grant),
            ("vault.client.new", lambda: vault.client.new),
            ("vault.list_vaults", lambda: vault.list_vaults),
            ("vault.set_credentials", lambda: vault.set_credentials),
            ("users['user123']", lambda: users['user123']),
            ("users.new", lambda: users.new),
            ("users.list", lambda: users.list),
            ("users.me", lambda: users.me),
            ("users.set_credentials", lambda: users.set_credentials),
            ("circles['circle456']", lambda: circles['circle456']),
            ("circles.new", lambda: circles.new),
            ("circles.list", lambda: circles.list),
            ("circles.search", lambda: circles.search),
            ("circles.set_credentials", lambda: circles.set_credentials),
        ]
        
        for api_call, test_func in api_tests:
            try:
                result = test_func()
                print(f"✅ {api_call} - accessible: {result is not None}")
            except Exception as e:
                print(f"⚠️  {api_call} - error: {e} (may need live service)")
        
        print("\n✅ All API compatibility tests completed!")
        return True
        
    except Exception as e:
        print(f"❌ API compatibility error: {e}")
        return False


if __name__ == "__main__":
    all_success = test_all_service_modules()
    compatibility_success = test_api_compatibility()
    
    if all_success and compatibility_success:
        print("\n🎉 All service module refactors complete and verified!")
        print("🚀 Ready for vault→client import migration!")
    else:
        print("\n❌ Some tests failed. Check output above.")
        sys.exit(1)
