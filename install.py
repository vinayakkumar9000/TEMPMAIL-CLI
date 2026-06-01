#!/usr/bin/env python3
"""
Cross-platform installer for TempMail Watcher
Uses only Python standard library - no external dependencies required
"""

import sys
import subprocess
import platform
from pathlib import Path


def check_python_version():
    """Check if Python version is >= 3.7"""
    if sys.version_info < (3, 7):
        print("ERROR: Python 3.7 or higher is required.")
        print(f"Current version: {sys.version}")
        sys.exit(1)
    print(f"✓ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} detected")


def create_virtualenv(venv_path):
    """Create a virtual environment"""
    if venv_path.exists():
        print("Virtual env already exists, reinstalling deps...")
        return False
    
    print("Creating virtual environment...")
    try:
        subprocess.check_call([sys.executable, "-m", "venv", str(venv_path)])
        print("✓ Virtual environment created")
        return True
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to create virtual environment: {e}")
        sys.exit(1)


def get_pip_executable(venv_path):
    """Get the pip executable path for the virtual environment"""
    system = platform.system()
    if system == "Windows":
        return venv_path / "Scripts" / "pip.exe"
    else:
        return venv_path / "bin" / "pip"


def install_dependencies(venv_path, requirements_file):
    """Install dependencies from requirements.txt"""
    pip_exe = get_pip_executable(venv_path)
    
    if not pip_exe.exists():
        print(f"ERROR: pip not found at {pip_exe}")
        sys.exit(1)
    
    if not requirements_file.exists():
        print(f"ERROR: requirements.txt not found at {requirements_file}")
        sys.exit(1)
    
    print("Installing dependencies...")
    try:
        subprocess.check_call([str(pip_exe), "install", "-r", str(requirements_file)])
        print("✓ Dependencies installed")
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to install dependencies: {e}")
        sys.exit(1)


def print_run_instructions():
    """Print OS-specific instructions for running the application"""
    system = platform.system()
    
    print("\n" + "=" * 60)
    print("Installation complete.")
    print("=" * 60)
    print("\nTo run TempMail Watcher:\n")
    
    if system == "Windows":
        print("  1. Activate the virtual environment:")
        print("     .venv\\Scripts\\activate")
        print("\n  2. Run the application:")
        print("     python tempmail.py")
    else:
        print("  1. Activate the virtual environment:")
        print("     source .venv/bin/activate")
        print("\n  2. Run the application:")
        print("     python tempmail.py")
    
    print("\n" + "=" * 60)


def main():
    """Main installation routine"""
    print("=" * 60)
    print("TempMail Watcher - Installation")
    print("=" * 60)
    print()
    
    # Check Python version
    check_python_version()
    
    # Get paths
    project_dir = Path(__file__).parent.resolve()
    venv_path = project_dir / ".venv"
    requirements_file = project_dir / "requirements.txt"
    
    # Create virtual environment
    create_virtualenv(venv_path)
    
    # Install dependencies
    install_dependencies(venv_path, requirements_file)
    
    # Print run instructions
    print_run_instructions()


if __name__ == "__main__":
    main()
