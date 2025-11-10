from typing import Literal

from fastapi import FastAPI, Body
from pydantic import BaseModel, Field
import subprocess

# =========================
# アプリ本体の設定
# =========================

app = FastAPI(
    title="サーバーコマンド実行システム",
    description=(
        "サーバー上で Linux コマンドを実行できる学習用 API です。\n"
        "・「通常コマンド実行」で自由にコマンドを試せます。\n"
        "・「ストーリー学習」で手順書どおりにコマンド練習ができます。"
    ),
    docs_url="/commandtest/docs",
    openapi_url="/commandtest/openapi.json",
)

CMD_TIMEOUT = 5  # 秒
MAX_BYTES = 200_000  # 出力の最大バイト数


# =========================
# 共通: コマンド実行ロジック
# =========================

class RunResponse(BaseModel):
    終了コード: int | None = Field(None, description="0 なら成功")
    標準出力: str = ""
    標準エラー: str = ""


def _truncate(s: str | None, limit: int) -> str:
    if s is None:
        return ""
    b = s.encode("utf-8")
    if len(b) <= limit:
        return s
    return b[:limit].decode("utf-8", errors="ignore") + "\n[... 省略しました ...]"


def run_shell(command: str) -> RunResponse:
    try:
        r = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=CMD_TIMEOUT,
        )
        return RunResponse(
            終了コード=r.returncode,
            標準出力=_truncate(r.stdout, MAX_BYTES),
            標準エラー=_truncate(r.stderr, MAX_BYTES),
        )
    except subprocess.TimeoutExpired:
        return RunResponse(
            終了コード=None,
            標準出力="",
            標準エラー=f"{CMD_TIMEOUT}秒を超えてタイムアウトしました。",
        )
    except Exception as e:
        return RunResponse(
            終了コード=None,
            標準出力="",
            標準エラー=f"実行時エラー: {e!r}",
        )


# =========================
# ① 通常コマンド実行
# =========================

@app.post(
    "/commandtest/run",
    response_model=RunResponse,
    tags=["通常コマンド実行"],
    summary="自由にコマンドを実行",
    description=(
        "任意の Linux コマンドを 1 行で入力して実行します。\n"
        "例: `echo hello`, `pwd`, `ls -l` など。\n"
        "※ 入力欄に **コマンド名だけ** を書けばよく、先頭に『コマンド』などを付ける必要はありません。"
    ),
)
def run_command(
    cmd: str = Body(
        ...,
        title="実行するコマンド",
        description="例: echo hello / pwd / ls -l などをそのまま入力します。",
        examples=["echo hello", "pwd", "ls -l"],
    )
):
    """
    通常のコマンド実行用エンドポイント。
    - 入力欄には「echo hello」のようにコマンドだけを書けば OK。
    - 結果は JSON で返します。
    """
    return run_shell(cmd)


# =========================
# ② ストーリー形式学習（cd → mkdir → rm など）
# =========================

class StoryStep(BaseModel):
    id: int
    説明: str
    期待コマンド: str


STORY_STEPS: list[StoryStep] = [
    StoryStep(
        id=1,
        説明="作業場所を /tmp に移動してみましょう。",
        期待コマンド="cd /tmp",
    ),
    StoryStep(
        id=2,
        説明="test というディレクトリを作成してみましょう。",
        期待コマンド="mkdir test",
    ),
    StoryStep(
        id=3,
        説明="test ディレクトリの中に移動してみましょう。",
        期待コマンド="cd test",
    ),
    StoryStep(
        id=4,
        説明="空の test.txt ファイルを作成してみましょう。",
        期待コマンド="touch test.txt",
    ),
    StoryStep(
        id=5,
        説明="1つ上の /tmp に戻って、test ディレクトリを削除しましょう。",
        期待コマンド="cd /tmp; rm -r test",
    ),
]

# 超シンプルに、サーバー全体で 1 つの進行状態だけ持つ
_current_step_index: int | None = None


class StoryStartResponse(BaseModel):
    現在ステップ番号: int
    説明: str
    例コマンド: str


@app.post(
    "/commandtest/story/start",
    response_model=StoryStartResponse,
    tags=["ストーリー学習"],
    summary="ストーリー形式学習を開始",
)
def story_start():
    """
    ストーリーを最初から開始する。
    現在ステップ番号・説明・例コマンドを返す。
    """
    global _current_step_index
    _current_step_index = 0
    step = STORY_STEPS[_current_step_index]
    return StoryStartResponse(
        現在ステップ番号=step.id,
        説明=step.説明,
        例コマンド=step.期待コマンド,
    )


class StoryNextRequest(BaseModel):
    入力コマンド: str = Field(
        ...,
        title="実行するコマンド",
        description="ストーリーの指示どおりにコマンドを入力します。",
        examples=["cd /tmp"],
    )


class StoryNextResponse(BaseModel):
    正解か: bool
    期待コマンド: str
    実行結果: RunResponse
    次ステップ説明: str | None = None
    完了: bool = False


@app.post(
    "/commandtest/story/next",
    response_model=StoryNextResponse,
    tags=["ストーリー学習"],
    summary="現在のステップを実行して次に進む",
)
def story_next(req: StoryNextRequest):
    """
    現在のステップに対して、入力されたコマンドを実行し、
    ・期待していたコマンドと一致しているか（正解か）
    ・実行結果
    ・次のステップの説明
    などを返す。
    """
    global _current_step_index

    if _current_step_index is None:
        # まだ start が呼ばれていない場合
        _current_step_index = 0

    step = STORY_STEPS[_current_step_index]
    ok = req.入力コマンド.strip() == step.期待コマンド

    result = run_shell(req.入力コマンド)

    完了 = False
    次の説明: str | None = None

    if ok:
        # 最後のステップなら完了
        if _current_step_index >= len(STORY_STEPS) - 1:
            完了 = True
        else:
            _current_step_index += 1
            次の説明 = STORY_STEPS[_current_step_index].説明

    return StoryNextResponse(
        正解か=ok,
        期待コマンド=step.期待コマンド,
        実行結果=result,
        次ステップ説明=次の説明,
        完了=完了,
    )
