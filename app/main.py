from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Query, Response
from pydantic import BaseModel, Field

# =========================================================
# FastAPI アプリ本体
# =========================================================

app = FastAPI(
    title="サーバーコマンド実行システム",
    docs_url="/commandtest/docs",           # Swagger UI の URL
    openapi_url="/commandtest/openapi.json", # OpenAPI JSON の URL
    redoc_url=None,
)

# ストーリー用の作業ディレクトリ
STORY_ROOT = Path("/tmp/command_story")


def get_story_workspace() -> Path:
    """ストーリー用の作業ディレクトリを返す。なければ作成する。"""
    STORY_ROOT.mkdir(parents=True, exist_ok=True)
    return STORY_ROOT


# =========================================================
# コマンド実行の共通処理
# =========================================================

class CommandRequest(BaseModel):
    command: str = Field(..., description="実行するコマンド（例: echo hello）")
    timeout_sec: int = Field(5, ge=1, le=60, description="タイムアウト秒（1〜60）")


def run_shell_command(cmd: str, timeout_sec: int, cwd: Path | None = None):
    """コマンド実行"""
    try:
        result = subprocess.run(
            cmd, shell=True, text=True,
            capture_output=True, timeout=timeout_sec,
            cwd=str(cwd) if cwd else None,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return None, "", f"TIMEOUT (> {timeout_sec}s)"
    except Exception as e:
        return None, "", f"ERROR: {e!r}"


# =========================================================
# 通常コマンド実行 API
# =========================================================

class CommandResult(BaseModel):
    return_code: int | None
    stdout: str
    stderr: str


@app.post("/command/run", response_model=CommandResult, tags=["コマンド"])
def run_command(req: CommandRequest, mode: Literal["json", "preview", "download"] = "json"):
    """任意のコマンドを実行"""
    code, out, err = run_shell_command(req.command, req.timeout_sec)
    text = f"終了コード: {code}\n標準出力:\n{out}\n標準エラー:\n{err}"

    if mode == "preview":
        return Response(content=text, media_type="text/plain; charset=utf-8")
    elif mode == "download":
        return Response(
            content=text, media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=result.txt"},
        )
    else:
        return CommandResult(return_code=code, stdout=out, stderr=err)


# =========================================================
# ストーリー性コマンド実行 API
# =========================================================

class StoryStartResponse(BaseModel):
    message: str
    workspace: str
    first_hint: str


@app.post("/story/start", response_model=StoryStartResponse, tags=["ストーリー"])
def story_start():
    """ストーリー用ワークスペースを初期化"""
    if STORY_ROOT.exists():
        shutil.rmtree(STORY_ROOT)
    ws = get_story_workspace()
    readme = ws / "README.txt"
    readme.write_text(
        "ここはストーリー用ワークスペースです。\n"
        "例: mkdir test → cd test → touch file.txt → ls -l\n",
        encoding="utf-8",
    )
    return StoryStartResponse(
        message="ストーリー開始。/tmp/command_story が作成されました。",
        workspace=str(ws),
        first_hint="`pwd` または `ls` で確認してみましょう。",
    )


class StoryStepResult(BaseModel):
    return_code: int | None
    stdout: str
    stderr: str
    next_hint: str | None = None


@app.post("/story/step", response_model=StoryStepResult, tags=["ストーリー"])
def story_step(req: CommandRequest):
    """ストーリー用コマンド実行"""
    ws = get_story_workspace()
    code, out, err = run_shell_command(req.command, req.timeout_sec, cwd=ws)

    hint = None
    if "mkdir" in req.command:
        hint = "test フォルダを作ったら cd test して中を見てみましょう。"
    elif "touch" in req.command:
        hint = "ファイルができたか ls -l で確認。"
    elif "rm" in req.command:
        hint = "削除したら ls で確認してみましょう。"

    return StoryStepResult(return_code=code, stdout=out, stderr=err, next_hint=hint)


@app.post("/story/reset", tags=["ストーリー"])
def story_reset():
    """ストーリー用フォルダを再作成"""
    if STORY_ROOT.exists():
        shutil.rmtree(STORY_ROOT)
    ws = get_story_workspace()
    return {"message": "リセット完了", "workspace": str(ws)}


@app.get("/health")
def health():
    return {"status": "ok"}
