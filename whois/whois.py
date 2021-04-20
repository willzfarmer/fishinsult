import string
import sqlite3
import os
import json
import discord
from redbot.core import commands, data_manager, Config, checks, bot
import io
import pathlib
import sqlite3


BaseCog = getattr(commands, "Cog", object)


class WhoIs(BaseCog):
    def __init__(self, bot_instance):
        self.bot: bot = bot_instance


    @commands.command()
    async def iseveryone(self, ctx):
        con = sq.connect(WHOFILE)
        cursor = con.cursor()
        cursor.execute("SELECT userid, name " "FROM usernames")
        results = cursor.fetchall()
        results = [
            (ctx.guild.get_member(int(userid)), name) for userid, name in results
        ]

        max_character = 2000
        msg_size = 0
        msg = ""
        for (mention, name) in results:
            if mention is not "None":
                to_append = "{} is {}\n".format(mention, name)
                characters += len(to_append)
                if characters >= CHAR_LIMIT:
                    await ctx.send(msg)
                    msg = to_append
                    characters = len(to_append)
                else:
                    msg += to_append
        if msg is not "":
            await ctx.send(msg)
        con.close()
        data_dir = data_manager.bundled_data_path(self)


        self.config = Config.get_conf(
            self,
            identifier=746578326459283047523,
            force_registration=True,
            cog_name="whois",
        )

        default_guild = {"whois_dict": {}}
        self.config.register_guild(**default_guild)

    @commands.command()
    async def theyare(self, ctx, user: discord.Member, *name: str):
        async with self.config.guild(ctx.guild).whois_dict() as whois_dict:
            whois_dict[str(user.id)] = " ".join(name)

        await ctx.send("Done")

    @commands.command()
    async def whois(self, ctx, user: discord.Member = None):
        if user is None:
            user = ctx.message.author
        realname = await self.get_realname(ctx, str(user.id))

        await ctx.send(realname or "User not registered!")

    async def get_realname(self, ctx, userid: str):
        """
        Separate func here for others to use
        """
        async with self.config.guild(ctx.guild).whois_dict() as whois_dict:
            realname = whois_dict.get(userid, None)
        return realname

    @commands.command()
    async def iswho(self, ctx, realname: str):
        async with self.config.guild(ctx.guild).whois_dict() as whois_dict:
            matches = []
            for userid, name in whois_dict.items():
                if realname in name.lower():
                    matches.append(ctx.guild.get_member(int(userid)).mention)

        if len(matches) == 0:
            await ctx.send("No users found!")
        else:
            await ctx.send(f"The following users match: {', '.join(matches)}")

    @commands.command()
    async def iseveryone(self, ctx):
        async with self.config.guild(ctx.guild).whois_dict() as whois_dict:
            for userid, name in whois_dict.items():
                member: discord.Member = ctx.guild.get_member(int(userid))
                if member is not None:
                    await ctx.send(f"{member.display_name} is {name}")

    @commands.command()
    @checks.is_owner()
    async def import_whois(self, ctx):
        message: discord.Message = ctx.message
        file_to_import = None
        for attachment in message.attachments:
            if attachment.filename == "whois.json":
                file_to_import = attachment
                break
        if file_to_import is None:
            await ctx.send("Please provide a file attached to this command.")
            return

        try:
            new_whois_data = await file_to_import.read()
            new_whois_data = new_whois_data.decode("utf-8")
            new_whois_data = json.loads(new_whois_data)
        except:
            await ctx.send("Unable to parse input json!")
            return

        async with self.config.guild(ctx.guild).whois_dict() as whois_dict:
            for userid, name in new_whois_data.items():
                whois_dict[userid] = name

        await ctx.send("Done")

    @commands.command()
    @checks.is_owner()
    async def export_whois(self, ctx):
        async with self.config.guild(ctx.guild).whois_dict() as whois_dict:
            output = json.dumps(whois_dict)
            await ctx.send(
                file=discord.File(io.StringIO(output), filename="whois.json")
            )

    def convert_realname(self, realname: str):
        if realname is None:
            return realname

        if len(realname) > 32:
            realname = realname.split(" ")[0]
            realname = "".join(
                c for c in realname if c.lower() in string.ascii_lowercase
            )
            return realname
        else:
            return realname

    @commands.command(hidden=True)
    @checks.is_owner()
    async def import_from_legacy_db(self, ctx):
        WHOFILE = os.path.join(str(pathlib.Path.home()), "whois.db")
        with sqlite3.connect(WHOFILE) as con:
            cursor = con.cursor()
            cursor.execute("SELECT userid, name " "FROM usernames")
            results = cursor.fetchall()

            async with self.config.guild(ctx.guild).whois_dict() as whois_dict:
                for userid, name in results:
                    whois_dict[userid] = name

    @commands.command()
    async def avatar(self, ctx, user: discord.Member = None):
        if user is None:
            user = ctx.message.author
        await ctx.send(user.avatar_url)

    @commands.command()
    async def emoji(self, ctx, *args: discord.Emoji):
        for emoji in args:
            await ctx.send(emoji.url)
