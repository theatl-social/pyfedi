"""
Simple test to verify finalize_user_setup is called in private registration
This test uses code inspection rather than full integration testing
"""
import ast
import os


def test_create_private_user_calls_finalize_user_setup():
    """
    Verify that the create_private_user function contains a call to finalize_user_setup
    """
    # Read the private_registration.py file
    file_path = os.path.join(
        os.path.dirname(__file__),
        '..',
        'app',
        'api',
        'admin',
        'private_registration.py'
    )

    with open(file_path, 'r') as f:
        source = f.read()

    # Parse the source code
    tree = ast.parse(source)

    # Find the create_private_user function
    create_private_user_found = False
    finalize_user_setup_called = False
    finalize_user_setup_imported = False

    for node in ast.walk(tree):
        # Check for the function definition
        if isinstance(node, ast.FunctionDef) and node.name == 'create_private_user':
            create_private_user_found = True

            # Look for calls to finalize_user_setup within this function
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Name) and child.func.id == 'finalize_user_setup':
                        finalize_user_setup_called = True

        # Check for import statement
        if isinstance(node, ast.ImportFrom):
            if node.module == 'app.utils':
                for alias in node.names:
                    if alias.name == 'finalize_user_setup':
                        finalize_user_setup_imported = True

    assert create_private_user_found, "create_private_user function not found"
    assert finalize_user_setup_called, "finalize_user_setup is not called in create_private_user function"
    assert finalize_user_setup_imported, "finalize_user_setup is not imported from app.utils"

    print("✓ create_private_user properly calls finalize_user_setup")
    print("✓ finalize_user_setup is imported from app.utils")


def test_finalize_user_setup_call_is_conditional():
    """
    Verify that finalize_user_setup is called conditionally based on auto_activate
    """
    file_path = os.path.join(
        os.path.dirname(__file__),
        '..',
        'app',
        'api',
        'admin',
        'private_registration.py'
    )

    with open(file_path, 'r') as f:
        source = f.read()

    # Simple string check - verify it's in an if block with auto_activate
    assert 'if auto_activate:' in source, "finalize_user_setup should be called conditionally on auto_activate"
    assert 'finalize_user_setup(new_user)' in source, "finalize_user_setup should be called with new_user"

    # Verify the logic makes sense - there should be an else clause
    lines = source.split('\n')
    found_if_auto_activate = False
    found_finalize_call = False
    found_else_clause = False

    for i, line in enumerate(lines):
        if 'if auto_activate:' in line:
            found_if_auto_activate = True
        if found_if_auto_activate and 'finalize_user_setup(new_user)' in line:
            found_finalize_call = True
        if found_finalize_call and 'else:' in line and i < len(lines) - 1:
            # Check if the next few lines mention activation
            next_lines = ' '.join(lines[i:i+3])
            if 'activation' in next_lines.lower() or 'finalized' in next_lines.lower():
                found_else_clause = True
                break

    assert found_if_auto_activate, "Could not find 'if auto_activate:' block"
    assert found_finalize_call, "Could not find finalize_user_setup call after auto_activate check"
    assert found_else_clause, "Could not find else clause explaining delayed finalization"

    print("✓ finalize_user_setup is properly conditioned on auto_activate")
    print("✓ Else clause exists to document delayed finalization")


if __name__ == '__main__':
    test_create_private_user_calls_finalize_user_setup()
    test_finalize_user_setup_call_is_conditional()
    print("\nAll tests passed!")
