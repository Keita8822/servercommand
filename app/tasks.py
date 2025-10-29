import subprocess

def run_command(command: str):
    """コンテナ内で安全にコマンドを実行"""
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=5
        )
        return {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}
    except Exception as e:
        return {"error": str(e)}


