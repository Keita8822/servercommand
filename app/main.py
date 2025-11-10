from fastapi import FastAPI, Body
from pydantic import BaseModel, Field
import subprocess

app = FastAPI(
    title="サーバーコマンド実行システム",
    description=(
        "単一の画面から『通常コマンド実行』と『ストーリー学習』の両方を操作できます。\n"
        "・通常: 任意のコマンドを入力して実行\n"
        "・ストーリー: 手順に沿った学習モード\n"
        "同じエンドポイント (/commandtest/run) で動作します。"
    ),
    docs_url="/commandtest/docs",
    openapi_url="/commandtest/openapi.json",
)

CMD_TIMEOUT = 5
MAX_BYTES = 200_000


class RunResponse(BaseModel):
    終了コード: int | None = Field(None, description="0なら成功")
    標準出力: str = ""
    標準エラー: str = ""
    正解か: bool | None = None
    現在ステップ: int | None = None
    次ステップ説明: str | None = None
    完了: bool = False


def _truncate(s: str | None, limit: int) -> str:
    if s is None:
        return ""
    b = s.encode("utf-8")
    if len(b) <= limit:
        return s
    return b[:limit].decode("utf-8", errors="ignore") + "\n[...省略しました...]"


def run_shell(command: str) -> RunResponse:
    try:
        r = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=CMD_TIMEOUT
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
        return RunResponse(終了コード=None, 標準出力="", 標準エラー=f"実行時エラー: {e!r}")


# =====================
# ストーリー定義
# =====================
class StoryStep(BaseModel):
    id: int
    説明: str
    期待コマンド: str


STORY_STEPS = [
    StoryStep(id=1, 説明="作業ディレクトリを /tmp に移動", 期待コマンド="cd /tmp"),
    StoryStep(id=2, 説明="test ディレクトリを作成", 期待コマンド="mkdir test"),
    StoryStep(id=3, 説明="test に移動", 期待コマンド="cd test"),
    StoryStep(id=4, 説明="空の test.txt を作成", 期待コマンド="touch test.txt"),
    StoryStep(id=5, 説明="/tmp に戻って test を削除", 期待コマンド="cd /tmp; rm -r test"),
]

current_step = 0  # ストーリー進行状況


@app.post(
    "/commandtest/run",
    response_model=RunResponse,
    tags=["統合コマンド実行"],
    summary="通常／ストーリー統合コマンド実行",
    description=(
        "1つの入力欄からすべてのコマンドを実行できます。\n"
        "・通常: 普通にコマンド入力 → 実行結果を返す\n"
        "・ストーリー: 手順どおりなら次の説明が出る\n\n"
        "ストーリーをリセットしたいときは『reset』と入力してください。"
    ),
)
def run_command(cmd: str = Body(..., title="コマンド", examples=["echo hello", "pwd", "cd /tmp"])):
    global current_step

    # リセット用
    if cmd.strip().lower() == "reset":
        current_step = 0
        return RunResponse(
            標準出力="ストーリーを最初からやり直します。",
            標準エラー="",
            現在ステップ=1,
            次ステップ説明=STORY_STEPS[0].説明,
        )

    result = run_shell(cmd)

    # ストーリーモード処理
    if current_step < len(STORY_STEPS):
        step = STORY_STEPS[current_step]
        if cmd.strip() == step.期待コマンド:
            current_step += 1
            if current_step >= len(STORY_STEPS):
                result.正解か = True
                result.完了 = True
                result.次ステップ説明 = "すべての手順が完了しました！お疲れさまです。"
            else:
                result.正解か = True
                result.現在ステップ = current_step + 1
                result.次ステップ説明 = STORY_STEPS[current_step].説明
        else:
            result.正解か = False
            result.現在ステップ = current_step + 1
            result.次ステップ説明 = f"期待されるコマンド: {step.期待コマンド}"

    return result
