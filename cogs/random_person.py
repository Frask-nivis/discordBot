import secrets

import discord
from discord import app_commands
from discord.ext import commands

MAX_CANDIDATES = 10
VIEW_TIMEOUT = 180
random_source = secrets.SystemRandom()


def result_embed(
    selected: list[discord.User | discord.Member],
    candidates: list[discord.User | discord.Member],
    mode: str,
) -> discord.Embed:
    winners = "\n".join(f"{index}. {user.mention}" for index, user in enumerate(selected, 1))
    candidate_list = ", ".join(user.mention for user in candidates)
    embed = discord.Embed(
        title="Hasil pilihan acak",
        description=winners,
        colour=discord.Colour.blurple(),
    )
    embed.add_field(name="Mode", value=mode, inline=True)
    embed.add_field(name="Jumlah kandidat", value=str(len(candidates)), inline=True)
    embed.add_field(name="Kandidat yang ikut", value=candidate_list, inline=False)
    embed.set_footer(text="Gunakan tombol Pilih lagi untuk mengundi ulang pool ini.")
    return embed


class OwnedView(discord.ui.View):
    def __init__(self, owner_id: int) -> None:
        super().__init__(timeout=VIEW_TIMEOUT)
        self.owner_id = owner_id
        self.message: discord.InteractionMessage | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Wizard ini hanya bisa digunakan oleh orang yang memulainya.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            await self.message.edit(view=self)


class RandomPerson(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="choose-random-person",
        description="Buka wizard untuk memilih orang secara acak.",
    )
    @app_commands.describe(count="Jumlah orang yang ingin dipilih.")
    async def choose_random_person(
        self,
        interaction: discord.Interaction,
        count: app_commands.Range[int, 1, MAX_CANDIDATES] = 1,
    ) -> None:
        view = ModeView(self, interaction.user.id, count)
        await interaction.response.send_message(
            embed=discord.Embed(
                title="Pilih cara pengundian",
                description=(
                    f"Akan memilih **{count} orang**. Pilih mode di bawah ini "
                    "untuk melanjutkan."
                ),
                colour=discord.Colour.blurple(),
            ),
            view=view,
            ephemeral=True,
        )
        view.message = await interaction.original_response()

    @staticmethod
    def _unique_users(users: list[discord.User | discord.Member]) -> list[discord.User | discord.Member]:
        return list({user.id: user for user in users}.values())

    async def _automatic_candidates(
        self,
        interaction: discord.Interaction,
        source: str,
    ) -> list[discord.Member] | None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Mode otomatis hanya tersedia di server. Gunakan mode "
                "`Dari kandidat` untuk self-install.",
                ephemeral=True,
            )
            return None

        if source == "channel" and isinstance(interaction.channel, discord.VoiceChannel):
            if candidates := [member for member in interaction.channel.members if not member.bot]:
                return candidates

        if not self.bot.intents.members:
            await interaction.response.send_message(
                "Mode otomatis membutuhkan **Server Members Intent**. Aktifkan "
                "intent itu di Discord Developer Portal dan set "
                "`DISCORD_MEMBERS_INTENT=true`, atau gunakan mode `Dari kandidat`.",
                ephemeral=True,
            )
            return None

        try:
            members = [
                member
                async for member in interaction.guild.fetch_members(limit=None)
                if not member.bot
            ]
        except (discord.ClientException, discord.Forbidden, discord.HTTPException):
            await interaction.response.send_message(
                "Saya tidak bisa membaca daftar member otomatis. Pastikan bot "
                "ter-install di server dan Members Intent aktif.",
                ephemeral=True,
            )
            return None

        if source == "channel" and interaction.channel is not None:
            members = [
                member
                for member in members
                if getattr(interaction.channel.permissions_for(member), "view_channel", False)
            ]
        return members


class ModeView(OwnedView):
    def __init__(self, cog: RandomPerson, owner_id: int, count: int) -> None:
        super().__init__(owner_id)
        self.cog = cog
        self.count = count

    @discord.ui.button(label="Dari kandidat", style=discord.ButtonStyle.primary)
    async def candidate_mode(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        view = CandidateView(self.cog, self.owner_id, self.count)
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Pilih kandidat",
                description=(
                    f"Pilih 1 sampai {MAX_CANDIDATES} orang dari menu di bawah. "
                    f"Minimal {self.count} kandidat diperlukan."
                ),
                colour=discord.Colour.blurple(),
            ),
            view=view,
        )
        view.message = self.message

    @discord.ui.button(label="Otomatis", style=discord.ButtonStyle.secondary)
    async def automatic_mode(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        view = AutoView(self.cog, self.owner_id, self.count)
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="Pilih sumber otomatis",
                description="Pilih member dari channel saat ini atau seluruh server.",
                colour=discord.Colour.blurple(),
            ),
            view=view,
        )
        view.message = self.message


class CandidateSelect(discord.ui.UserSelect):
    def __init__(self, parent: "CandidateView") -> None:
        super().__init__(
            placeholder="Pilih orang yang ikut diundi...",
            min_values=1,
            max_values=MAX_CANDIDATES,
        )
        self.parent_view = parent

    async def callback(self, interaction: discord.Interaction) -> None:
        self.parent_view.candidates = [user for user in self.values if not user.bot]
        await interaction.response.edit_message(
            embed=self.parent_view.build_embed(), view=self.parent_view
        )


class CandidateView(OwnedView):
    def __init__(self, cog: RandomPerson, owner_id: int, count: int) -> None:
        super().__init__(owner_id)
        self.cog = cog
        self.count = count
        self.candidates: list[discord.User | discord.Member] = []
        self.add_item(CandidateSelect(self))

    def build_embed(self) -> discord.Embed:
        selected = len(self.candidates)
        status = f"{selected} dipilih"
        if selected < self.count:
            status += f"; minimal {self.count}"
        return discord.Embed(
            title="Pilih kandidat",
            description=f"{status}. Setelah cukup, tekan **Konfirmasi**.",
            colour=discord.Colour.blurple(),
        )

    @discord.ui.button(label="Konfirmasi", style=discord.ButtonStyle.success, row=1)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if len(self.candidates) < self.count:
            await interaction.response.send_message(
                f"Pilih minimal {self.count} kandidat unik terlebih dahulu.",
                ephemeral=True,
            )
            return
        await show_result(interaction, self.owner_id, self.candidates, self.count, "Dari kandidat")
        self.stop()


class AutoView(OwnedView):
    def __init__(self, cog: RandomPerson, owner_id: int, count: int) -> None:
        super().__init__(owner_id)
        self.cog = cog
        self.count = count

    async def choose_source(self, interaction: discord.Interaction, source: str) -> None:
        candidates = await self.cog._automatic_candidates(interaction, source)
        if candidates is None:
            return
        if len(candidates) < self.count:
            await interaction.response.send_message(
                f"Hanya menemukan {len(candidates)} orang, tetapi perlu "
                f"{self.count} orang.",
                ephemeral=True,
            )
            return
        await show_result(interaction, self.owner_id, candidates, self.count, source)
        self.stop()

    @discord.ui.button(label="Channel saat ini", style=discord.ButtonStyle.primary)
    async def channel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.choose_source(interaction, "channel")

    @discord.ui.button(label="Seluruh server", style=discord.ButtonStyle.secondary)
    async def server(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.choose_source(interaction, "server")


class ResultView(OwnedView):
    def __init__(
        self,
        owner_id: int,
        candidates: list[discord.User | discord.Member],
        count: int,
        mode: str,
    ) -> None:
        super().__init__(owner_id)
        self.candidates = candidates
        self.count = count
        self.mode = mode

    @discord.ui.button(label="Pilih lagi", style=discord.ButtonStyle.primary)
    async def reroll(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.edit_message(
            embed=result_embed(
                random_source.sample(self.candidates, self.count),
                self.candidates,
                self.mode,
            ),
            view=self,
        )

    @discord.ui.button(label="Selesai", style=discord.ButtonStyle.secondary)
    async def finish(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()


async def show_result(
    interaction: discord.Interaction,
    owner_id: int,
    candidates: list[discord.User | discord.Member],
    count: int,
    mode: str,
) -> None:
    selected = random_source.sample(candidates, count)
    view = ResultView(owner_id, candidates, count, mode)
    if interaction.response.is_done():
        await interaction.edit_original_response(
            embed=result_embed(selected, candidates, mode), view=view
        )
    else:
        await interaction.response.send_message(
            embed=result_embed(selected, candidates, mode), view=view, ephemeral=True
        )
    view.message = await interaction.original_response()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RandomPerson(bot))