import os
import asyncio
import discord
from discord import app_commands
import traceback
from playwright.sync_api import sync_playwright

# =====================
# 環境変数
# =====================
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
TORITSU_USER_ID = os.environ["TORITSU_USER_ID"]
TORITSU_PASSWORD = os.environ["TORITSU_PASSWORD"]

TORITSU_URL = "https://kouen.sports.metro.tokyo.lg.jp/web/index.jsp"


# =====================
# Reservation Scraper
# =====================
class ReservationScraper:
    """
    都立公園予約サイトにログインし、
    現在の予約情報を取得するクラス
    """

    def fetch(self) -> list[dict]:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(TORITSU_URL, timeout=30000)

            try:
                # ログインボタン
                page.click("#btn-login")

                # ユーザーID / パスワード
                page.fill("#userId", TORITSU_USER_ID)
                page.fill("#password", TORITSU_PASSWORD)

                # ログイン実行
                page.click("#btn-go")

                # 「予約」リンク
                page.click("xpath=//a[span[text()='予約']]")

                # 「予約の確認」
                page.click(".modal-content a:text('予約の確認')")

                # テーブル行が出るまで待つ
                page.wait_for_selector("#rsvacceptlist tbody tr", timeout=20000)

                rows = page.query_selector_all("#rsvacceptlist tbody tr")

                reservations = []
                for row in rows:
                    tds = row.query_selector_all("td")
                    if len(tds) >= 4:
                        reservations.append({
                            "date": tds[1].inner_text().replace("利用日：", "").replace("\n", "").strip(),
                            "time": tds[2].inner_text().replace("時間：", "").replace("\n", "").strip(),
                            "facility": tds[3].inner_text().replace("公園・施設：", "").replace("\n", "").strip(),
                        })

                return reservations

            finally:
                browser.close()


# =====================
# Discord Bot Setup
# =====================
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


# =====================
# Embed Builder
# =====================
def reservations_to_embed(reservations: list[dict]) -> discord.Embed:
    """
    予約一覧を Discord Embed に変換する
    """
    embed = discord.Embed(
        title=f"📋 コート予約状況（{len(reservations)}件）",
        color=0x2ECC71
    )

    if not reservations:
        embed.description = "📭 現在、予約はありません"
        return embed

    for i, r in enumerate(reservations, start=1):
        embed.add_field(
            name=f"🧾 予約 {i}",
            value=(
                f"📅 {r['date']}\n"
                f"⏰ {r['time']}\n"
                f"🏞 {r['facility']}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            inline=False
        )

    return embed


# =====================
# Slash Command
# =====================
@tree.command(
    name="chk",
    description="現在のテニスコート予約状況を確認します"
)
async def chk(interaction: discord.Interaction):
    """
    /chk 実行時に予約状況を取得して返す。
    エラーが発生した場合は内容を Discord に通知する。
    """
    await interaction.response.defer(thinking=True)

    try:
        scraper = ReservationScraper()
        loop = asyncio.get_running_loop()

        reservations = await loop.run_in_executor(
            None,
            scraper.fetch
        )

        embed = reservations_to_embed(reservations)
        await interaction.followup.send(embed=embed)

    except Exception as e:
        error_text = "".join(
            traceback.format_exception(type(e), e, e.__traceback__)
        )

        # Discord は 2000 文字制限があるので切る
        error_text = error_text[-1800:]

        await interaction.followup.send(
            content=(
                "🚨 **エラーが発生しました**\n\n"
                "```python\n"
                f"{error_text}\n"
                "```"
            )
        )


# =====================
# Ready Event
# =====================
@client.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {client.user}")


# =====================
# Entry Point
# =====================
client.run(DISCORD_TOKEN)
