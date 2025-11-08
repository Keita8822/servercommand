from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Response
from pydantic import BaseModel, Field

# =========================================================
# FastAPI アプリ本体
# 重要: root_path="/commandtest" を指定
# =========================================================

app = FastAPI(
    title="サーバーコマンド実行システム",
    root_path="/commandtest",  # ← ここが今回のポイント
)

# ストーリー用の作業ディレクトリ
STORY_ROOT = Path("/tmp/command_story")


def get_story_workspace() -> Path:
    """
    ストーリー用の作業ディレクトリを返す。
    なければ作成する。
    """
    STORY_ROOT.mkdir(parents=True, exist_ok=True)
    return STORY_ROOT


# =========================================================
# 共通：コマンド実行の処理
# =========================================================

class CommandRequest(BaseModel):
    command: str = Field(..., description="サーバで実行するコマンド（例: echo hello）")
    timeout_sec: int = Field(
        5,
        ge=1,
        le=60,
        description="タイムアウト秒（1〜60、未指定は 5 秒）",
    )


def run_shell_command(
    cmd: str,
    timeout_sec: int,
    cwd: Path | None = None,
) -> tuple[int | None, str, str]:
    """
    シェルコマンドを実行するヘルパー関数。
    return_code, stdout, stderr を返す。
    タイムアウト時は return_code=None にする。
    """
    try:
        r = subprocess.run(
            cmd,
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
            cwd=str(cwd) if cwd else None,
        )
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return None, "", f"TIMEOUT (> {timeout_sec} sec)"
    except Exception as e:  # 予期しない例外
        return None, "", f"ERROR: {e!r}"


# =========================================================
# 1) 通常のコマンド実行 API
# =========================================================

class CommandResult(BaseModel):
    return_code: int | None = Field(None, description="終了コード（タイムアウト時は null）")
    stdout: str = Field("", description="標準出力")
    stderr: str = Field("", description="標準エラー出力")


@app.post(
    "/command/run",
    response_model=CommandResult,
    summary="コマンド実行（通常）",
    tags=["コマンド"],
)
def command_run(
    req: CommandRequest,
    mode: Literal["json", "preview", "download"] = Query(
        "json",
        description="結果の返し方: json / preview / download",
    ),
):
    """
    単発でコマンドを実行するエンドポイント。

    - `mode=json`     … JSON で結果を返す（標準的な使い方）
    - `mode=preview`  … テキストとして画面にそのまま表示
    - `mode=download` … result.txt としてダウンロード
    """
    return_code, stdout, stderr = run_shell_command(
        req.command,
        timeout_sec=req.timeout_sec,
        cwd=None,
    )

    body_text = (
        f"終了コード: {return_code}\n"
        f"標準出力:\n{stdout}\n"
        f"標準エラー:\n{stderr}"
    )

    # ダウンロード
    if mode == "download":
        return Response(
            content=body_text,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="result.txt"'},
        )

    # 画面プレビュー
    if mode == "preview":
        return Response(content=body_text, media_type="text/plain; charset=utf-8")

    # JSON（通常）
    return CommandResult(return_code=return_code, stdout=stdout, stderr=stderr)


# =========================================================
# 2) ストーリー用 API
# =========================================================

class StoryStartResponse(BaseModel):
    message: str
    workspace: str
    first_hint: str


@app.post(
    "/story/start",
    response_model=StoryStartResponse,
    summary="ストーリー開始（ワークスペース作成）",
    tags=["ストーリー"],
)
def story_start():
    """
    ストーリー用の作業ディレクトリを作り直して初期化する。
    例として /tmp/command_story を利用。
    """
    # 既存を消して作り直し
    if STORY_ROOT.exists():
        shutil.rmtree(STORY_ROOT)
    workspace = get_story_workspace()

    # 説明用の README を作っておく（なくても動作には影響なし）
    readme = workspace / "README.txt"
    readme.write_text(
        "ここはストーリー用の作業ディレクトリです。\n"
        "例: 以下の順番でコマンドを打ってみてください。\n"
        "  1) pwd\n"
        "  2) mkdir test\n"
        "  3) cd test && touch test.txt\n"
        "  4) cd test && ls -l\n"
        "  5) cd .. && rm -r test\n",
        encoding="utf-8",
    )

    return StoryStartResponse(
        message="ストーリー用ワークスペースを初期化しました。",
        workspace=str(workspace),
        first_hint="最初は `pwd` や `ls` で中身を確認してみてください。",
    )


class StoryStepResult(BaseModel):
    return_code: int | None
    stdout: str
    stderr: str
    next_hint: str | None = None


@app.post(
    "/story/step",
    response_model=StoryStepResult,
    summary="ストーリー用コマンド実行（ワークスペース内）",
    tags=["ストーリー"],
)
def story_step(req: CommandRequest):
    """
    ストーリー用ワークスペースをカレントディレクトリにしてコマンド実行。
    `command_run` との違いは cwd が固定されること。
    """
    workspace = get_story_workspace()

    return_code, stdout, stderr = run_shell_command(
        req.command,
        timeout_sec=req.timeout_sec,
        cwd=workspace,
    )

    # ざっくりした次のヒント（本格的な判定はしていない）
    hint = None
    if "mkdir" in req.command and "test" in req.command:
        hint = "作った test ディレクトリの中にファイルを作ってみましょう。例: cd test && touch test.txt"
    elif "touch" in req.command and "test.txt" in req.command:
        hint = "ファイルができたか `cd test && ls -l` で確認してみましょう。"
    elif "rm" in req.command and "test" in req.command:
        hint = "`ls` でディレクトリが消えているか確認してみましょう。"

    return StoryStepResult(
        return_code=return_code,
        stdout=stdout,
        stderr=stderr,
        next_hint=hint,
    )


@app.post(
    "/story/reset",
    summary="ストーリー用ワークスペースのリセット",
    tags=["ストーリー"],
)
def story_reset():
    """
    ストーリー用ディレクトリを完全に消して作り直す。
    """
    if STORY_ROOT.exists():
        shutil.rmtree(STORY_ROOT)
    workspace = get_story_workspace()
    return {"message": "ストーリー用ワークスペースをリセットしました。", "workspace": str(workspace)}


# =========================================================
# シンプルなヘルスチェック
# =========================================================

@app.get("/health", tags=["その他"], summary="疎通確認用ヘルスチェック")
def health_check():
    return {"status": "ok"}
