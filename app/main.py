
from typing import Literal
from fastapi import FastAPI, Response, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
import subprocess

app = FastAPI(
    title="サーバコマンドシステム",
    description="コマンドを安全な範囲で実行し、結果をJSON/プレビュー/ダウンロードで返します。",
    version="1.0.0",
)

class CommandRequest(BaseModel):
    コマンド: str = Field(
        ...,
        title="実行するコマンド",
        description="例: `echo Hello` / `pwd` / `ls -l` など",
        examples=["echo Hello", "pwd", "ls -l"],
    )
    タイムアウト秒: int = Field(
        5,
        ge=1,
        le=60,
        title="タイムアウト（秒）",
        description="コマンドがこの秒数を超えて応答しない場合は中断します（1〜60）。",
        examples=[5, 10, 30],
    )

@app.post(
    "/実行",
    summary="コマンドを実行する",
    description="入力したシェルコマンドを実行し、結果を返します。既定はJSON。`形式`を `preview` または `download` にするとテキストとして返却/ダウンロードされます。",
)
def 実行(
    req: CommandRequest,
    形式: Literal["json", "preview", "download"] = Query(
        "json",
        description="結果の返却形式: `json`（既定）/ `preview`（テキスト表示）/ `download`（テキストダウンロード）",
        examples=["json", "preview", "download"],
    ),
):
    try:
        r = subprocess.run(
            req.コマンド,
            shell=True,
            capture_output=True,
            text=True,
            timeout=req.タイムアウト秒,
        )
    except subprocess.TimeoutExpired:
        body = f"{req.タイムアウト秒}秒を超えてタイムアウトしました。"
        if 形式 == "download":
            return Response(
                content=body,
                media_type="text/plain; charset=utf-8",
                headers={"Content-Disposition": 'attachment; filename="timeout.txt"'},
            )
        if 形式 == "preview":
            return Response(content=body, media_type="text/plain; charset=utf-8")
        return JSONResponse({"終了コード": -1, "標準出力": "", "標準エラー": body})


    body = (
        f"終了コード: {r.returncode}\n"
        f"標準出力:\n{r.stdout}\n"
        f"標準エラー:\n{r.stderr}"
    )

    if 形式 == "download":
        return Response(
            content=body,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="result.txt"'},
        )
    if 形式 == "preview":
        return Response(content=body, media_type="text/plain; charset=utf-8")


    return JSONResponse({"終了コード": r.returncode, "標準出力": r.stdout, "標準エラー": r.stderr})


# 日本語UI
@app.get("/ui", response_class=HTMLResponse, include_in_schema=False)
def ui():
    return HTMLResponse("""
<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>日本語コマンド実行UI</title>
<style>
  body{font-family:system-ui,-apple-system,Segoe UI,Roboto;max-width:880px;margin:24px auto;padding:0 16px}
  h1{font-size:20px;margin:0 0 16px}
  .card{border:1px solid #ddd;border-radius:12px;padding:16px;margin-bottom:16px}
  label{display:block;font-weight:600;margin:8px 0 6px}
  textarea,input[type=number]{width:100%;box-sizing:border-box;border:1px solid #ccc;border-radius:8px;padding:10px;font-family:ui-monospace,Consolas,monospace}
  textarea{min-height:110px}
  .row{display:flex;gap:12px;flex-wrap:wrap}
  .row .col{flex:1 1 220px}
  .hint{color:#666;font-size:12px;margin-top:4px}
  .presets{display:flex;flex-wrap:wrap;gap:8px;margin-top:4px}
  .preset{border:1px solid #aaa;background:#fafafa;border-radius:999px;padding:6px 10px;cursor:pointer}
  .actions{display:flex;gap:8px;margin-top:12px}
  button{padding:10px 14px;border:0;border-radius:8px;cursor:pointer}
  .primary{background:#2563eb;color:#fff}
  .ghost{background:#f3f4f6}
  .result{white-space:pre-wrap;background:#0b1020;color:#e2e8f0;border-radius:12px;padding:12px;min-height:120px;overflow:auto}
  .seg{display:flex;gap:8px;margin-top:6px}
  .seg label{font-weight:500}
</style>
</head>
<body>
  <h1>サーバコマンドシステム</h1>

  <div class="card">
    <label for="cmd">コマンド <span class="hint">（例：<code>echo こんにちは</code> / <code>pwd</code> / <code>ls -l</code>）</span></label>
    <textarea id="cmd" placeholder="例：echo こんにちは"></textarea>
    <div class="presets" id="presets"></div>

    <div class="row">
      <div class="col">
        <label for="timeout">タイムアウト（秒）</label>
        <input id="timeout" type="number" min="1" max="60" value="5" />
        <div class="hint">指定秒数を超えた場合は中断します（1〜60）。</div>
      </div>
      <div class="col">
        <label>返却形式</label>
        <div class="seg">
          <label><input type="radio" name="fmt" value="json" checked> JSON</label>
          <label><input type="radio" name="fmt" value="preview"> プレビュー（テキスト）</label>
          <label><input type="radio" name="fmt" value="download"> ダウンロード（txt）</label>
        </div>
      </div>
    </div>

    <div class="actions">
      <button class="primary" id="runBtn">実行する</button>
      <button class="ghost" id="clearBtn">クリア</button>
    </div>
  </div>

  <div class="card">
    <label>結果</label>
    <div id="result" class="result" aria-live="polite"></div>
  </div>

<script>
  // プリセット（必要に応じて増減OK）
  const PRESETS = [
    {label: "現在の場所を表示 (pwd)", cmd: "pwd"},
    {label: "ファイル一覧 (ls -l)", cmd: "ls -l"},
    {label: "テキスト出力 (echo)", cmd: "echo こんにちは"},
    {label: "OS情報 (uname -a)", cmd: "uname -a"},
    {label: "環境変数確認 (printenv | head)", cmd: "printenv | head"}
  ];

  const presetsWrap = document.getElementById("presets");
  PRESETS.forEach(p => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "preset";
    b.textContent = p.label;
    b.addEventListener("click", () => {
      document.getElementById("cmd").value = p.cmd;
    });
    presetsWrap.appendChild(b);
  });

  const runBtn = document.getElementById("runBtn");
  const clearBtn = document.getElementById("clearBtn");
  const result = document.getElementById("result");

  clearBtn.addEventListener("click", () => {
    document.getElementById("cmd").value = "";
    result.textContent = "";
  });

  runBtn.addEventListener("click", async () => {
    const cmd = document.getElementById("cmd").value.trim();
    const timeout = Number(document.getElementById("timeout").value || 5);
    const fmt = [...document.querySelectorAll('input[name="fmt"]')].find(x => x.checked)?.value || "json";
    result.textContent = "実行中…";

    if (!cmd) {
      result.textContent = "コマンドが空です。入力してください。";
      return;
    }

    try {
      const url = `/実行?形式=${encodeURIComponent(fmt)}`;
      const resp = await fetch(url, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ "コマンド": cmd, "タイムアウト秒": timeout })
      });

      if (fmt === "download") {
        // サーバが text/plain を返すのでダウンロード扱いにする
        const blob = await resp.blob();
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "result.txt";
        a.click();
        URL.revokeObjectURL(a.href);
        result.textContent = "ダウンロードを開始しました。";
        return;
      }

      // json / preview
      const ctype = resp.headers.get("content-type") || "";
      if (ctype.includes("application/json")) {
        const data = await resp.json();
        result.textContent = JSON.stringify(data, null, 2);
      } else {
        const text = await resp.text();
        result.textContent = text;
      }
    } catch (e) {
      result.textContent = "実行中にエラーが発生しました: " + String(e);
    }
  });
</script>
</body>
</html>
    """)

