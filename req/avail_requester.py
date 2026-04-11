import os
import discord
from discord import app_commands
import pandas as pd
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()

# =====================
# 環境変数
# =====================
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]

DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.expanduser("~"), "tokyo-tennis", "data"))
MERGED_PATH = os.path.join(DATA_DIR, "All", "latest_merged.csv")


# =====================
# 定数
# =====================
TIME_COLUMNS = ["7:00", "9:00", "11:00", "13:00", "15:00", "17:00", "19:00"]

COURTS = [
    "AriakeA_hard",
    "AriakeC_grass",
    "Kameido_grass",
    "Kiba_grass",
    "OihutoA_hard",
    "OihutoB_grass",
    "OihutoB_hard",
    "Sarue_grass",
    "Toneri_grass",
]


# =====================
# Discord Client / Tree
# =====================
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


# =====================
# CSV Loader
# =====================
def load_latest_csv() -> pd.DataFrame:
    return pd.read_csv(MERGED_PATH)


# =====================
# UI View
# =====================
class ControlView(discord.ui.View):
    """
    日付・コートを選択して空き状況を表示する UI
    """

    def __init__(self):
        super().__init__(timeout=None)
        self.date: str | None = None
        self.location: str = "all"

        # -------- 日付 Select（今日〜3週間）--------
        today = date.today()
        options = [
            discord.SelectOption(
                label=(today + timedelta(days=i)).strftime("%Y/%m/%d (%a)"),
                value=(today + timedelta(days=i)).strftime("%Y/%m/%d"),
            )
            for i in range(21)
        ]

        self.date_select = discord.ui.Select(
            placeholder="日付を選択（3週間）",
            options=options,
            row=0,
        )
        self.date_select.callback = self.on_date_selected
        self.add_item(self.date_select)

    async def on_date_selected(self, interaction: discord.Interaction):
        self.date = self.date_select.values[0]
        await interaction.response.edit_message(
            content=f"日付: {self.date}\nコート: {self.location}",
            view=self,
        )

    # -------- コート Select --------
    @discord.ui.select(
        placeholder="コートを選択",
        row=1,
        options=[
            discord.SelectOption(label="全て", value="all"),
            *[discord.SelectOption(label=c, value=c) for c in COURTS],
        ],
    )
    async def select_court(self, interaction: discord.Interaction, select):
        self.location = select.values[0]
        await interaction.response.edit_message(
            content=f"日付: {self.date}\nコート: {self.location}",
            view=self,
        )

    # -------- 実行ボタン --------
    @discord.ui.button(label="実行", style=discord.ButtonStyle.primary, row=2)
    async def run(self, interaction: discord.Interaction, button):
        if not self.date:
            await interaction.response.send_message(
                "⚠️ 先に日付を選択してください",
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True)

        try:
            df = load_latest_csv()
            df = df[df["date"] == self.date]

            if df.empty:
                embed = discord.Embed(
                    title=f"🎾 空き状況 ({self.date})",
                    description="🔴 **空きがありません。**",
                    color=0xE74C3C,
                )
                await interaction.followup.send(embed=embed)
                return

            for col in TIME_COLUMNS:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

            embed = discord.Embed(
                title=f"🎾 空き状況 ({self.date})",
                description=f"コート: {'全て' if self.location == 'all' else self.location}",
                color=0x2ECC71,
            )

            found_any = False

            if self.location == "all":
                for location, gdf in df.groupby("location"):
                    lines = []
                    for col in TIME_COLUMNS:
                        if col not in gdf.columns:
                            continue
                        count = int(gdf[col].sum())
                        if count > 0:
                            found_any = True
                            icon = "🟡" if count <= 2 else "🟢"
                            lines.append(f"{col} {icon} {count}件")

                    embed.add_field(
                        name=f"【{location}】",
                        value="\n".join(lines) if lines else "🔴 空きなし",
                        inline=False,
                    )
            else:
                df = df[df["location"] == self.location]
                for col in TIME_COLUMNS:
                    if col not in df.columns:
                        continue
                    count = int(df[col].sum())
                    if count > 0:
                        found_any = True
                        icon = "🟡" if count <= 2 else "🟢"
                        embed.add_field(
                            name=col,
                            value=f"{icon} {count}件",
                            inline=True,
                        )

            if not found_any:
                embed = discord.Embed(
                    title=f"🎾 空き状況 ({self.date})",
                    description="🔴 **空きがありません。**",
                    color=0xE74C3C,
                )

            executed_at = df["executed_at"].iloc[0] if "executed_at" in df.columns and not df.empty else "不明"
            embed.set_footer(text=f"データ取得日時: {executed_at}")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(
                f"❌ **エラーが発生しました**\n```{e}```",
                ephemeral=True,
            )


# =====================
# Slash Command
# =====================
@tree.command(name="req", description="直近のテニスコート空き状況を調査")
async def req(interaction: discord.Interaction):
    await interaction.response.send_message(
        "条件を選択してください",
        view=ControlView(),
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
