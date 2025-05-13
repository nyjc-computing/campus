import os

def init(verbose: bool = False) -> None:
    """Initialize the test environment."""
    # Set up the test environment variables
    print("Set ENV=testing")
    os.environ['ENV'] = 'testing'
    
