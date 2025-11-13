from fastapi import FastAPI, Body
import subprocess
from pathlib import Path
from threading import Lock
from typing import Optional
 
# ===== 実行制御用の設定 =====
CMD_TIMEOUT = 5          # コマンドの最大実行時間（秒）
MAX_BYTES = 200_000      # 標準出力・標準エラーの最大バイト数
 
 
# ===== 作業用ディレクトリの設定 =====
BASE_DIR = Path("/tmp/commandtest_workspace")
BASE_DIR.mkdir(exist_ok=True)
 
# 現在の作業ディレクトリ（初期値は BASE_DIR）
_current_dir = BASE_DIR
_dir_lock = Lock()
 
 
def get_current_dir() -> Path:
    """スレッドセーフに現在ディレクトリを取得"""
    with _dir_lock:
        return _current_dir
 
 
def change_dir(target: str) -> str:
    """
    cd コマンド用。
    - 相対パス/絶対パスどちらもOK
    - BASE_DIR の外には出られないように制限
    """
    global _current_dir
    with _dir_lock:
        if target in ("", "~"):
            new_dir = BASE_DIR
        else:
            # 相対パス扱い（ただし絶対パスを渡されても resolve で正規化）
            new_dir = (_current_dir / target).resolve()
 
        # /tmp/commandtest_workspace から外に出ないようにチェック
        if not (new_dir == BASE_DIR or BASE_DIR in new_dir.parents):
            return "エラー: 作業ディレクトリの外には移動できません。"
 
        if not new_dir.exists():
            return f"エラー: ディレクトリが存在しません: {new_dir}"
 
        if not new_dir.is_dir():
            return f"エラー: ディレクトリではありません: {new_dir}"
 
        _current_dir = new_dir
        return f"現在のディレクトリ: {new_dir}"
 
 
def _truncate(s: Optional[str], limit: int) -> str:
    """UTF-8 バイト数で安全に切り詰める"""
    if s is None:
        return ""
    b = s.encode("utf-8")
    if len(b) <= limit:
        return s
    return b[:limit].decode("utf-8", errors="ignore") + "\n[...省略しました...]"
 
 
# ===== FastAPI 本体 =====
app = FastAPI(
    title="サーバーコマンドシステム",
    description=(
        "サーバー上で Linux コマンドを実行する API です。\n"
        "- 作業ディレクトリは /tmp/commandtest_workspace 配下に限定\n"
        "- cd コマンドで現在ディレクトリを移動\n"
        "- それ以外のコマンドは現在ディレクトリ内で実行\n"
    ),
    docs_url="/commandtest/docs",
    openapi_url="/commandtest/openapi.json",
)
 
 
@app.post("/commandtest/run")
async def run_command(
    command: str = Body(
        ...,
        example="ls",
        description="実行したいLinuxコマンドをそのまま入力（例: ls, mkdir test, rm -r test, cd test）",
    )
):
    """
    サーバー上でLinuxコマンドを実行するAPI。
 
    - 1回に1つのコマンドを実行
    - cd のみ特別扱い（カレントディレクトリを変更）
    - それ以外のコマンドは現在の作業ディレクトリ内で実行
    """
    command = command.strip()
 
    if not command:
        cwd = get_current_dir()
        return {
            "作業ディレクトリ": str(cwd),
            "エラー": "コマンドが空です。何か入力してください。",
        }
 
    # --- cd 専用処理 ---
    if command.startswith("cd "):
        target = command[3:].strip()
        msg = change_dir(target)
        return {
            "作業ディレクトリ": str(get_current_dir()),
            "結果": msg,
        }
 
    if command == "cd":
        msg = change_dir("")
        return {
            "作業ディレクトリ": str(get_current_dir()),
            "結果": msg,
        }
 
    # --- 通常コマンド ---
    cwd = get_current_dir()
 
    try:
        result = subprocess.run(
            command,
            shell=True,
            text=True,
            capture_output=True,
            cwd=str(cwd),
            timeout=CMD_TIMEOUT,
        )
 
        stdout = _truncate((result.stdout or "").strip(), MAX_BYTES)
        stderr = _truncate((result.stderr or "").strip(), MAX_BYTES)
 
        if not stdout:
            stdout = "出力なし"
 
        response = {
            "作業ディレクトリ": str(cwd),
            "結果": stdout,
        }
 
        if stderr:
            response["エラー"] = stderr
 
        response["終了コード"] = result.returncode
 
        return response
 
    except subprocess.TimeoutExpired:
        return {
            "作業ディレクトリ": str(cwd),
            "エラー": f"{CMD_TIMEOUT}秒を超えてタイムアウトしました。",
        }
    except Exception as e:
        return {
            "作業ディレクトリ": str(cwd),
            "エラー": f"実行中に問題が発生しました: {e!r}",
        }
