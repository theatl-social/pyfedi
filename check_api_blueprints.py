#!/usr/bin/env python3
"""
Quick check to verify all API blueprints are properly defined and can be imported.
"""

def check_blueprints():
    print("🔍 Checking API Blueprint Definitions and Registration\n")
    
    # Check what blueprints are defined in __init__.py
    print("1. Blueprints defined in app/api/alpha/__init__.py:")
    from app.api.alpha import (
        bp, site_bp, misc_bp, comm_bp, feed_bp, topic_bp, 
        user_bp, reply_bp, post_bp, private_message_bp, 
        upload_bp, admin_bp
    )
    
    defined_blueprints = {
        'bp (main)': bp,
        'site_bp': site_bp,
        'misc_bp': misc_bp,
        'comm_bp': comm_bp,
        'feed_bp': feed_bp,
        'topic_bp': topic_bp,
        'user_bp': user_bp,
        'reply_bp': reply_bp,
        'post_bp': post_bp,
        'private_message_bp': private_message_bp,
        'upload_bp': upload_bp,
        'admin_bp': admin_bp,
    }
    
    for name, blueprint in defined_blueprints.items():
        if blueprint:
            bp_name = getattr(blueprint, 'name', 'Unknown')
            print(f"  ✅ {name}: {bp_name}")
        else:
            print(f"  ❌ {name}: Not defined!")
    
    # Check what's imported and registered in app/__init__.py
    print("\n2. Checking app/__init__.py registration:")
    
    with open('app/__init__.py', 'r') as f:
        content = f.read()
        
    # Check imports
    import_line = "from app.api.alpha import"
    import_section = []
    in_import = False
    
    for line in content.split('\n'):
        if import_line in line:
            in_import = True
            import_section.append(line)
        elif in_import and line.strip().startswith(('reply_bp', 'post_bp', 'admin_bp', 'upload_bp', 'private_message_bp')):
            import_section.append(line)
        elif in_import and not line.strip().endswith('\\'):
            if line.strip():
                import_section.append(line)
            in_import = False
    
    print("  Import statement found:")
    for line in import_section:
        print(f"    {line.strip()}")
    
    # Check registrations
    print("\n  Blueprint registrations found:")
    registration_count = 0
    for bp_name in ['site_bp', 'misc_bp', 'comm_bp', 'feed_bp', 'topic_bp', 
                    'user_bp', 'reply_bp', 'post_bp', 'admin_bp', 'upload_bp', 'private_message_bp']:
        if f"rest_api.register_blueprint({bp_name})" in content:
            print(f"    ✅ {bp_name} is registered")
            registration_count += 1
        else:
            print(f"    ❌ {bp_name} is NOT registered!")
    
    print(f"\n  Total: {registration_count}/11 API blueprints registered")
    
    # Summary
    print("\n3. Summary:")
    all_defined = all(bp is not None for bp in defined_blueprints.values())
    all_registered = registration_count == 11
    
    if all_defined and all_registered:
        print("  ✅ All blueprints are properly defined and registered!")
    else:
        if not all_defined:
            print("  ❌ Some blueprints are not properly defined")
        if not all_registered:
            print("  ❌ Some blueprints are not registered in app/__init__.py")
    
    # Check for routes
    print("\n4. Checking routes defined in app/api/alpha/routes.py:")
    
    route_patterns = {
        'site_bp': '@site_bp.route',
        'misc_bp': '@misc_bp.route',
        'comm_bp': '@comm_bp.route',
        'feed_bp': '@feed_bp.route',
        'topic_bp': '@topic_bp.route',
        'user_bp': '@user_bp.route',
        'reply_bp': '@reply_bp.route',
        'post_bp': '@post_bp.route',
        'private_message_bp': '@private_message_bp.route',
        'upload_bp': '@upload_bp.route',
        'admin_bp': '@admin_bp.route',
    }
    
    with open('app/api/alpha/routes.py', 'r') as f:
        routes_content = f.read()
    
    for bp_name, pattern in route_patterns.items():
        count = routes_content.count(pattern)
        if count > 0:
            print(f"  ✅ {bp_name}: {count} routes defined")
        else:
            print(f"  ❌ {bp_name}: NO routes defined!")
    
    return all_defined and all_registered


if __name__ == '__main__':
    import sys
    try:
        result = check_blueprints()
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)