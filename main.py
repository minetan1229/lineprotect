import asyncio
import json
import time
import webbrowser
import aiofiles  # 非同期ファイル操作用
from CHRLINE import CHRLINE

# CHRLINEクライアントのインスタンス作成（QRコードログイン）
client = CHRLINE()

# ファイルの保存処理用フラグ
save_pending = {"blacklist": False, "whitelist": False, "logs": False}

# 非同期ファイル保存関数
async def save_to_file(data, filename, immediate=False):
    try:
        if not immediate:
            save_pending[filename] = True
        else:
            async with aiofiles.open(filename, "w") as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=4))
            save_pending[filename] = False
    except Exception as e:
        print(f"ファイル保存エラー: {filename} - {str(e)}")

# 非同期ファイル読み込み関数
async def load_from_file(filename):
    try:
        async with aiofiles.open(filename, "r") as f:
            content = await f.read()
            return json.loads(content)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"エラー: {filename} の読み込み中にエラーが発生しました。")
        return {}

# データ初期化
blacklist = set(await load_from_file("blacklist.json").get("blacklist", []))
whitelist = set(await load_from_file("whitelist.json").get("whitelist", []))
logs = await load_from_file("logs.json")
invite_count = {}  # 招待回数の管理
message_history = {}  # スパム検出用
admin_ids = set(whitelist)  # 管理者IDのセット
error_log_file = "error_log.json"

# QRコードログイン処理
async def qr_login():
    print("QRコードを取得しています...")
    url = client.getAuthQRCode()  # 認証用QRコードのURLを取得
    print(f"次のURLをQRコードリーダーでスキャンしてください:\n{url}")
    webbrowser.open(url)  # OS依存しない方法でURLを開く

# ホワイトリストユーザーによる自動管理開始
async def on_invited_to_group(op):
    group_id = op["groupId"]
    inviter_id = op["param3"]

    if inviter_id in whitelist:
        await client.sendMessage(group_id, "ホワイトリストの管理者による招待を確認しました。管理を開始します。")

# 新しいメンバーがグループに参加したとき
async def on_member_joined(group_id, new_members):
    for member in new_members:
        user_name = await client.getDisplayName(member)
        await client.sendMessage(group_id, f"@{user_name} さん、参加ありがとうございます！", [member])

# メンバーが退会したとき
async def on_member_left(group_id, left_member):
    user_name = await client.getDisplayName(left_member)
    await client.sendMessage(group_id, f"@{user_name} さんが退会しました。ブロック・削除を推奨します。", [left_member])

# 権限確認
async def is_admin(user_id):
    return user_id in admin_ids

# スパム検出とコマンド処理
async def on_message(message):
    try:
        group_id = message["group"]
        user_id = message["user"]
        text = message["text"]
        sender_name = await client.getDisplayName(user_id)
        current_time = time.time()

        # グループ内の招待回数初期化
        if group_id not in invite_count:
            invite_count[group_id] = {}
        if user_id not in invite_count[group_id]:
            invite_count[group_id][user_id] = 0

        # グループごとのログ管理
        if group_id not in logs:
            logs[group_id] = []
        logs[group_id].append(f"{sender_name}: {text}")
        await save_to_file(logs, "logs.json")

        # スパムメッセージ履歴管理
        if group_id not in message_history:
            message_history[group_id] = {}
        if user_id not in message_history[group_id]:
            message_history[group_id][user_id] = []

        # 古いメッセージ削除（10秒以上経過したもの）
        message_history[group_id][user_id] = [
            t for t in message_history[group_id][user_id] if current_time - t < 10
        ]
        message_history[group_id][user_id].append(current_time)

        # スパム検出（5件以上の短時間投稿）
        if len(message_history[group_id][user_id]) > 5:
            await client.kickoutFromGroup(group_id, [user_id])
            blacklist.add(user_id)
            await save_to_file({"blacklist": list(blacklist)}, "blacklist.json", immediate=True)
            await client.sendMessage(group_id, f"{sender_name} がスパム検出され、グループから削除されました。")

        # コマンド処理
        if text.startswith("/"):
            command = text.split()[0]

            if command == "/help":
                await client.sendMessage(
                    group_id,
                    """
[コマンド一覧]
/help - コマンド一覧を表示
/addadmin @user - 管理者追加
/deladmin @user - 管理者削除
/bkl - ブラックリスト表示
/bk @user - ブラックリスト追加
/bkc @user - ブラックリストから削除
/lg - グループログ表示
/lgc - グループログ削除
                    """
                )

            elif command == "/addadmin":
                if not await is_admin(user_id):
                    await client.sendMessage(group_id, "権限がありません。")
                    return

                mentions = message.get("mentions", [])
                for mention in mentions:
                    admin_ids.add(mention)
                await save_to_file({"whitelist": list(admin_ids)}, "whitelist.json", immediate=True)
                await client.sendMessage(group_id, "管理者を追加しました。")

            elif command == "/deladmin":
                if not await is_admin(user_id):
                    await client.sendMessage(group_id, "権限がありません。")
                    return

                mentions = message.get("mentions", [])
                for mention in mentions:
                    admin_ids.discard(mention)
                await save_to_file({"whitelist": list(admin_ids)}, "whitelist.json", immediate=True)
                await client.sendMessage(group_id, "管理者を削除しました。")

            elif command == "/bkl":
                await client.sendMessage(group_id, f"ブラックリスト: {', '.join(blacklist)}")

            elif command == "/bk":
                mentions = message.get("mentions", [])
                for mention in mentions:
                    blacklist.add(mention)
                await save_to_file({"blacklist": list(blacklist)}, "blacklist.json", immediate=True)
                await client.sendMessage(group_id, "ユーザーをブラックリストに追加しました。")

            elif command == "/bkc":
                mentions = message.get("mentions", [])
                for mention in mentions:
                    blacklist.discard(mention)
                await save_to_file({"blacklist": list(blacklist)}, "blacklist.json", immediate=True)
                await client.sendMessage(group_id, "ユーザーをブラックリストから削除しました。")

            elif command == "/lg":
                await client.sendMessage(group_id, "\n".join(logs.get(group_id, [])))

            elif command == "/lgc":
                logs[group_id] = []
                await save_to_file(logs, "logs.json", immediate=True)
                await client.sendMessage(group_id, "ログをクリアしました。")

    except Exception as e:
        error_message = f"エラー: {e}"
        await save_to_file({"error": error_message}, error_log_file, immediate=True)
        print(error_message)

# メイン処理
async def main():
    await qr_login()
    while True:
        try:
            events = await client.poll.fetchOps()
            for event in events:
                if event.type == 25:  # メッセージイベント
                    await on_message(event.message)
                elif event.type == 13:  # グループ招待
                    await on_invited_to_group(event)
                elif event.type == 17:  # メンバー参加
                    await on_member_joined(event.group, event.param1)
                elif event.type == 15:  # メンバー退会
                    await on_member_left(event.group, event.param1)
        except Exception as e:
            print(f"エラー: {e}")
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
