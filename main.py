from CHRLINE import CHRLINE
from datetime import datetime, timedelta

# クライアントの初期化とログイン
client = CHRLINE()
client.loginWithCredential('your_email@example.com', 'your_password')

# グローバル変数
blacklist = []
whitelist = []
invite_count = {}  # {user_id: invite_count}
group_ids = []
message_history = {}  # {user_id: [message_time1, message_time2, ...]}

# アカウントが参加しているグループのIDを取得
def get_all_group_ids():
    global group_ids
    group_ids = client.getGroupIdsJoined()
    print(f"参加しているグループ: {group_ids}")

# グループの監視
def monitor_groups():
    for group_id in group_ids:
        monitor_group(group_id)

# 特定のグループの監視
def monitor_group(group_id):
    messages = client.getRecentMessages(group_id)
    for msg in messages:
        sender_id = msg['senderId']
        text = msg['text']

        # スパム検出
        if is_spamming(sender_id, text):
            add_to_blacklist(group_id, sender_id)
            client.deleteMessage(group_id, msg['id'])
            client.sendMessage(group_id, f"{msg['senderName']} が連投を検知したため削除しました。")

        # オールメンション検出
        if detect_all_mention(text) and sender_id not in whitelist:
            add_to_blacklist(group_id, sender_id)
            client.deleteMessage(group_id, msg['id'])
            client.sendMessage(group_id, f"{msg['senderName']} のオールメンションは禁止されています。")

        # 招待検出
        if is_invite_action(msg):
            handle_invite_action(group_id, msg)

# スパム検出（同じメッセージが5回以上連続した場合）
def is_spamming(user_id, text):
    now = datetime.now()

    # メッセージ履歴に追加
    if user_id not in message_history:
        message_history[user_id] = []

    message_history[user_id].append(now)

    # 2分以内のメッセージ数が5回を超えたらスパムと判断
    recent_messages = [msg_time for msg_time in message_history[user_id] if now - msg_time < timedelta(minutes=2)]

    if len(recent_messages) > 5:
        return True

    message_history[user_id] = recent_messages
    return False

# オールメンション検出
def detect_all_mention(text):
    # ここでメンションの特定ロジックを実装する必要があります。
    # 例として、@all や特定のキーワードを検出する実装を考慮。
    return '@all' in text

# 招待アクションかどうかを確認
def is_invite_action(msg):
    return msg.get('contentType') == 'INVITE'

# 招待アクションの処理
def handle_invite_action(group_id, msg):
    inviter_id = msg['senderId']
    
    # 招待されたユーザーが自分（アカウント自身）の場合、自動的に参加
    invitee_id = msg['inviteeId']
    if invitee_id == client.profile['mid']:  # 自分が招待されたか確認
        client.acceptGroupInvitation(group_id)
        client.sendMessage(group_id, "招待されたため、自動的にグループに参加しました。")

    # ホワイトリストに含まれていないユーザーが招待した場合
    elif inviter_id not in whitelist:
        # ホワイトリストに入っていない場合は招待をキャンセル
        cancel_invite(group_id, invitee_id)
        client.sendMessage(group_id, f"{msg['senderName']} さんの招待はキャンセルされました。")

# 招待をキャンセルする
def cancel_invite(group_id, invitee_id):
    client.cancelGroupInvitation(group_id, [invitee_id])

# コマンドの処理
def process_command(sender_id, group_id, text):
    if sender_id not in whitelist:
        client.sendMessage(group_id, "このコマンドを使用する権限がありません。")
        return

    if text == '/help':
        client.sendMessage(group_id, """
        利用可能なコマンド:
        /help - コマンド一覧を表示
        /bkl - ブラックリストを表示
        /whl - ホワイトリストを表示
        /bk - ブラックリストに追加
        /bkc - ブラックリストから削除
        /wh - ホワイトリストに追加
        /whc - ホワイトリストから削除
        """)

    elif text == '/bkl':
        blacklist_display = '\n'.join([client.getContact(uid)['displayName'] for uid in blacklist])
        client.sendMessage(group_id, f"ブラックリスト:\n{blacklist_display}")

    elif text == '/whl':
        whitelist_display = '\n'.join([client.getContact(uid)['displayName'] for uid in whitelist])
        client.sendMessage(group_id, f"ホワイトリスト:\n{whitelist_display}")

    elif text == '/bk':
        contact = get_last_sent_contact(group_id)
        if contact:
            add_to_blacklist(group_id, contact['mid'])
        else:
            client.sendMessage(group_id, "連絡先が見つかりません。")

    elif text == '/bkc':
        contact = get_last_sent_contact(group_id)
        if contact and contact['mid'] in blacklist:
            remove_from_blacklist(group_id, contact['mid'])
        else:
            client.sendMessage(group_id, "ブラックリストにそのメンバーはいません。")

    elif text == '/wh':
        contact = get_last_sent_contact(group_id)
        if contact and contact['mid'] not in blacklist:
            add_to_whitelist(group_id, contact['mid'])
        else:
            client.sendMessage(group_id, "ブラックリストにいるメンバーはホワイトリストに追加できません。")

    elif text == '/whc':
        contact = get_last_sent_contact(group_id)
        if contact and contact['mid'] in whitelist:
            remove_from_whitelist(group_id, contact['mid'])
        else:
            client.sendMessage(group_id, "ホワイトリストにそのメンバーはいません。")

# 最後に送信された連絡先を取得
def get_last_sent_contact(group_id):
    # 最新のメッセージを取得して、連絡先メッセージを抽出
    messages = client.getRecentMessages(group_id)
    for msg in reversed(messages):  # 最新のメッセージからチェック
        if msg['contentType'] == 'CONTACT':
            return msg['contentMetadata']  # 連絡先のメタデータを返す
    return None

# ブラックリストに追加
def add_to_blacklist(group_id, user_id):
    if user_id not in blacklist:
        blacklist.append(user_id)
        user_name = client.getContact(user_id)['displayName']
        client.sendMessage(group_id, f"{user_name} をブラックリストに追加しました。")

# ブラックリストから削除
def remove_from_blacklist(group_id, user_id):
    if user_id in blacklist:
        blacklist.remove(user_id)
        user_name = client.getContact(user_id)['displayName']
        client.sendMessage(group_id, f"{user_name} をブラックリストから削除しました。")

# ホワイトリストに追加
def add_to_whitelist(group_id, user_id):
    if user_id not in whitelist:
        whitelist.append(user_id)
        user_name = client.getContact(user_id)['displayName']
        client.sendMessage(group_id, f"{user_name} をホワイトリストに追加しました。")

# ホワイトリストから削除
def remove_from_whitelist(group_id, user_id):
    if user_id in whitelist:
        whitelist.remove(user_id)
        user_name = client.getContact(user_id)['displayName']
        client.sendMessage(group_id, f"{user_name} をホワイトリストから削除しました。")

# メインループ
if __name__ == '__main__':
    get_all_group_ids()  # 参加しているグループIDを取得
    monitor_groups()  # すべてのグループの監視を開始
