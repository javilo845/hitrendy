import os
import sys
import shutil
import socket
import subprocess

def check_env_file():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_file = os.path.join(root_dir, ".env")
    env_example = os.path.join(root_dir, ".env.example")
    
    if not os.path.exists(env_file):
        print(f"[*] Creating .env from .env.example")
        shutil.copy(env_example, env_file)
    else:
        print("[+] .env file exists")

def check_docker():
    try:
        result = subprocess.run(["docker", "info"], capture_output=True, text=True)
        if result.returncode == 0:
            print("[+] Docker is running")
            return True
        else:
            print("[-] Docker is installed but not running")
            return False
    except FileNotFoundError:
        print("[-] Docker command not found on PATH")
        return False

def check_port(host, port, name):
    try:
        with socket.create_connection((host, port), timeout=2):
            print(f"[+] Service {name} is accessible on {host}:{port}")
            return True
    except (socket.timeout, ConnectionRefusedError):
        print(f"[-] Service {name} is NOT accessible on {host}:{port}")
        return False

def main():
    print("=== Environment Verification ===")
    check_env_file()
    docker_ok = check_docker()
    
    # Check default ports for docker services (postgres: 5432, redis: 6379, minio: 9000)
    check_port("localhost", 5432, "PostgreSQL")
    check_port("localhost", 6379, "Redis")
    check_port("localhost", 9000, "MinIO")
    
    print("================================")

if __name__ == "__main__":
    main()
