#!/usr/bin/env python3

import os
import discord
from redbot.core import commands, checks
import sqlite3 as sq


import pprint as pp

import pathlib
import random
import time

from pony import orm

from pony.orm import Optional, Required, db_session

import pathlib

BaseCog = getattr(commands, 'Cog', object)

# we're gonna keep track of last point given in memory
ONE_HOUR = 60 * 60
POINT_TIMINGS = {}
PROTECTIONS = {}
FARM_LIST = {}
MAX_FARM = 5
last_regen = 0
USER_ROLE = "Knights Belligerent"

the_chosen = [
    '195663495189102593', # snek
    '142431859148718080', # eris
    '223869486736867328' # relm
]

"""
Let's start by defining our database
"""

db_file = pathlib.Path().home() / 'battle.db'
db = orm.Database()

breaks = [
    0,
    300,
    900,
    2_700,
    6_500,
    14_000,
    23_000,
    34_000,
    48_000,
    64_000,
    85_000,
    100_000,
    120_000,
    140_000,
    165_000,
    195_000,
    225_000,
    265_000,
    305_000,
    355_000,
]

class User(db.Entity):
    userID = Required(str)
    points = Required(int, default=0)

    strength = Optional(int)
    wisdom = Optional(int)
    dexterity = Optional(int)
    charisma = Optional(int)
    intelligence = Optional(int)
    constitution = Optional(int)

    hp = Optional(int)
    current_hp = Optional(int)
    player_race = Optional(str)
    player_class = Optional(str)

    @property
    def st_mod(self): return int((self.strength - 10) / 2)

    @property
    def ws_mod(self): return int((self.wisdom - 10) / 2)

    @property
    def dx_mod(self): return int((self.dexterity - 10) / 2)

    @property
    def cr_mod(self): return int((self.charisma - 10) / 2)

    @property
    def in_mod(self): return int((self.intelligence - 10) / 2)

    @property
    def cn_mod(self): return int((self.constitution - 10) / 2)

    def generate_stat(self):
        rolls = sum(list(sorted(list(random.randint(1, 6) for _ in range(4))))[1:])
        return rolls

    @property
    def armor_class(self):
        return self.dx_mod + self.ws_mod + 10

    @property
    def attack_roll(self):
        return random.randint(1, 20) + self.proficiency + self.dx_mod

    @property
    def damage_roll(self):
        return random.randint(1, 4)

    @property
    def proficiency(self):
        breaks = [1, 5, 8, 12, 16, 21]
        level = self.level
        for i in range(len(breaks)):
            if breaks[i] <= level < breaks[i + 1]:
                return i + 2

    @property
    def level(self):
        for i in range(len(breaks)):
            if breaks[i] <= self.points < breaks[i + 1]:
                return i + 1

    @property
    def xp_to_next_level(self):
        for i in range(len(breaks)):
            if breaks[i] <= self.points < breaks[i + 1]:
                return breaks[i + 1] - breaks[i]

    def go_up_a_level(self):
        self.hp += max(3, random.randint(1, 6)) + self.cn_mod
        self.current_hp = self.hp

    def go_down_a_level(self):
        self.hp -= max(3, random.randint(1, 6)) + self.cn_mod
        if self.hp <=0: #Shouldn't happen but eh. Dice fall as they may.
            self.hp = max(3, random.randint(1, 6)) + self.cn_mod
        self.current_hp = self.hp

    def update_points(self, points: int) -> int:
        """
        A cleaner wrapper function for adding points and leveling users. Makes sure levels stay working
        :param points: How many points to add.
        :return: the change in level as applied i.e 0 if level stays the same. 1 if it goes up and -1 if it goes down.
        if for some reason level change by more then 1 that's fine too.
        """
        initial_level = self.level
        self.points += points
        if self.level > initial_level:
            self.go_up_a_level()
        elif self.level < initial_level:
            self.go_down_a_level()
        return self.level - initial_level

    def generate_user(self):
        self.strength = self.generate_stat()
        self.charisma = self.generate_stat()
        self.wisdom = self.generate_stat()
        self.dexterity = self.generate_stat()
        self.constitution = self.generate_stat()
        self.intelligence = self.generate_stat()

        self.hp = (max(3, random.randint(1, 6)) + self.cn_mod) * self.level

        self.current_hp = self.hp


db.bind(provider='sqlite', filename=str(db_file), create_db=True)
db.generate_mapping(create_tables=True)


@db_session
def get_user(uid):
    user = User.select(lambda u: u.userID == str(uid)).first()
    if user is None:
        user = User(userID=str(uid))

    if user.strength is None:
        user.generate_user()

    return user


@db_session
def heal_user(author):
    user = get_user(author.id)
    heal_amount = random.randint(1, 6)
    user.current_hp = min(user.hp, user.current_hp + heal_amount)

    return heal_amount


@db_session
def full_heal_user(author):
    user = get_user(author.id)
    user.current_hp = user.hp

    return user.hp


class Battle(BaseCog):
    def __init__(self, bot):
        self.bot = bot

        self.last_heal = {}

        # We need to count each message
        async def count_message(message, reaction=None, action=None):
            global last_regen

            # Prevent snek from voting on herself or counting
            clean_message = message.clean_content.lower()
            if not clean_message.startswith('.') and random.random() <= 0.1:
                heal_user(message.author)

            if bot.user.id == message.author.id:
                return

            # Prevent acting on DM's
            if message.guild is None:
                return

            server          = message.guild.id
            channel         = message.channel.id
            userID          = message.author.id
            message_channel = message.channel.name.lower()

            #NO XP for non players ideally
            if USER_ROLE not in reaction.message.author.roles:
                return

            # don't do the #battle channel
            if 'battle' in message_channel:
                return

            #New code for passive regeneration
            if time.time() > last_regen + ONE_HOUR:
                for member in message.guild.members:
                    for role in member.roles:
                        if role.name == USER_ROLE:
                            heal_user(member)

            add_points = False
            if (userID not in POINT_TIMINGS) or (time.time() - POINT_TIMINGS[userID] > 60):
                POINT_TIMINGS[userID] = time.time()
                add_points = True

            with db_session:
                user = get_user(userID)

                if add_points:
                    user.update_points(1)

        # We need to count each message
        async def count_reaction_add(reaction, _):
            # Prevent snek from voting on herself or counting
            if bot.user.id == reaction.message.author.id:
                return

            # Prevent acting on DM's
            if reaction.message.guild is None:
                return


            server          = reaction.message.guild.id
            channel         = reaction.message.channel.id
            userID          = reaction.message.author.id
            message_channel = reaction.message.channel.name.lower()

            #NO XP for non players ideally
            if USER_ROLE not in reaction.message.author.roles:
                return

            with db_session:
                user = get_user(userID)

                if reaction.emoji == '👎':
                    if user.points >=3:
                        user.update_points(-3)
                elif reaction.emoji == '👍':
                    user.update_points(3)

        # We need to count each message
        async def count_reaction_remove(reaction, _):
            # Prevent snek from voting on herself or counting
            if bot.user.id == reaction.message.author.id:
                return

            # Prevent acting on DM's
            if reaction.message.guild is None:
                return

            server          = reaction.message.guild.id
            channel         = reaction.message.channel.id
            userID          = reaction.message.author.id
            message_channel = reaction.message.channel.name.lower()
            #NO XP for non players ideally
            if USER_ROLE not in reaction.message.author.roles:
                return
            with db_session:
                user = get_user(userID)

                if reaction.emoji == '👎':
                    user.update_points(3)
                elif reaction.emoji == '👍':
                    if user.points >=3:
                        user.update_points(-3)

        bot.add_listener(count_message, 'on_message')
        bot.add_listener(count_reaction_add, 'on_reaction_add')
        bot.add_listener(count_reaction_remove, 'on_reaction_remove')


    @commands.command()
    async def status(self, ctx, user: discord.Member=None):
        """
        List status of user
        """
        with db_session:
            if user is None:
                user = ctx.message.author

            db_user = get_user(user.id)

            message = '\n'.join([
            'User {} has {} experience and is level {} with {}/{} hitpoints',
            'Armor Class: {}',
            'Strength: {} ({})',
            'Intelligence: {} ({})',
            'Dexterity: {} ({})',
            'Wisdom: {} ({})',
            'Charisma: {} ({})',
            'Constitution: {} ({})',
            ])

            await ctx.send(message.format(
                                user.mention,
                                db_user.points,
                                db_user.level,
                                db_user.current_hp,
                                db_user.hp,
                                db_user.armor_class,
                                db_user.strength,
                                db_user.st_mod,
                                db_user.intelligence,
                                db_user.in_mod,
                                db_user.dexterity,
                                db_user.dx_mod,
                                db_user.wisdom,
                                db_user.ws_mod,
                                db_user.charisma,
                                db_user.cr_mod,
                                db_user.constitution,
                                db_user.cn_mod,
                ))

    @commands.command()
    @checks.is_owner()
    async def reload_user(self, ctx, user: discord.Member=None):
        """
        reloads user stats
        """
        with db_session:
            author = get_user(ctx.message.author.id if user is None else user.id)

            author.generate_user()

    @commands.command()
    @checks.is_owner()
    async def heal_user(self, ctx, user: discord.Member=None):
        """
        reloads user stats
        """
        user = ctx.message.author if user is None else user
        heal_user(user)

    @commands.command()
    @checks.is_owner()
    async def full_heal_user(self, ctx, user: discord.Member=None):
        """
        reloads user stats
        """
        user = ctx.message.author if user is None else user
        full_heal_user(user)


    @commands.command()
    @checks.is_owner()
    async def elevate(self, ctx, user: discord.Member=None):
        """
        reloads user stats
        """
        user = ctx.message.author if user is None else user

        with db_session:
            target = get_user(user.id)
            target.update_points(target.xp_to_next_level + 1)

    @commands.command()
    @checks.is_owner()
    async def set_attribute(self, ctx, user: discord.Member=None, attribute=None, new_value=None):
        """
        Sets a chosen attribute

            * hp
            * points
            * strength
            * wisdom
            * dexterity
            * charisma
            * intelligence
            * constitution
        """
        with db_session:
            target = get_user(user.id)

            attributes = [
                'hp',
                'points',
                'strength',
                'wisdom',
                'dexterity',
                'charisma',
                'intelligence',
                'constitution',
            ]

            if attribute not in attributes:
                await ctx.send(f'Please chose one of {", ".join(attributes)}')
                return

            try:
                int(new_value)
            except ValueError:
                await ctx.send('Please enter an integer')
                return

            if attribute == 'hp':
                target.hp = int(new_value)
            elif attribute == 'points':
                target.points = int(new_value)
            elif attribute == 'strength':
                target.strength = int(new_value)
            elif attribute == 'wisdom':
                target.wisdom = int(new_value)
            elif attribute == 'dexterity':
                target.dexterity = int(new_value)
            elif attribute == 'charisma':
                target.charisma = int(new_value)
            elif attribute == 'intelligence':
                target.intelligence = int(new_value)
            elif attribute == 'constitution':
                target.constitution = int(new_value)

            orm.commit()


    @commands.command()
    async def protect(self, ctx, user: discord.Member=None):
        """
        reloads user stats
        """
        user = ctx.message.author if user is None else user

        ctime = time.time()

        PROTECTIONS[user.id] = ctime


    @commands.command()
    async def attack(self, ctx, user: discord.Member=None):
        """
        Battles another user!

        You can't attack if you're unconscious, and you have a 10% chance of healing for every message you send.

        In order to hit someone, you have to roll 1d20 + prof + dx_mod and beat 10 + dx_mod + ws_mod
        """
        protected = PROTECTIONS.get(ctx.message.author.id)
        punish_author = False

        # NO XP for non players ideally
        if USER_ROLE not in user.roles:
            await ctx.send(f'{user.mention} is not playing the game. Cannot be attacked!')
            return

        if protected is not None:
            if time.time() - protected <= ONE_HOUR:
                await ctx.send(f'{ctx.message.author.mention} is protected and cannot attack!')
                return
            else:
                del PROTECTIONS[ctx.message.author.id]
        target_protected = PROTECTIONS.get(user.id)

        if target_protected is not None:
            if time.time() - target_protected <= ONE_HOUR:
                await ctx.send(f'{user.mention} is protected!')
                return
            else:
                del PROTECTIONS[user.id]

        farmed = FARM_LIST.get(user.id)
        if farmed is not None:
            if farmed == MAX_FARM:
                await ctx.send(f'{user.mention} has been killed too many times since they last attacked.'
                                   f'They are now under farm protection')
            elif farmed > MAX_FARM:
                await ctx.send(f'Stop Farming {user.mention}! You get an asshole punishment!')
                punish_author = True
        with db_session:
            author = get_user(ctx.message.author.id)

            if user is None:
                author.current_hp -= author.attack_roll
                await ctx.send(f'{ctx.message.author.mention} hurt itself in its confusion!'
                               f' Current HP = {author.current_hp}')
                return
            if punish_author:
                author.current_hp -= author.attack_roll
                await ctx.send(f'{ctx.message.author.mention} is a jerk'
                               f' Current HP = {author.current_hp}')
                return

            if author.current_hp <= 0:
                await ctx.send(f'{ctx.message.author.mention} is unconscious and cannot attack!')
                return

            target = get_user(user.id)
            if author.attack_roll >= target.armor_class:
                #Once a user attacks successfully they are no longer under farm protection.
                farm_check = FARM_LIST.get(ctx.message.author.id)
                if farm_check is not None:
                    del FARM_LIST[ctx.message.author.id]
                roll = author.damage_roll
                target.current_hp = max(0, target.current_hp - roll)
                if target.current_hp == 0:
                    if farmed is None:
                        FARM_LIST[user.id] = 0
                    else:
                        FARM_LIST[user.id] += 1
                    new_xp = random.randint(1, 3) * target.level
                    level_diff=author.update_points(new_xp)
                    await ctx.send(f'{ctx.message.author.mention} attacks {user.mention} for {roll}!'
                                   f' {user.mention} is unconscious!')

                    await ctx.send(f'{ctx.message.author.mention} gains {new_xp} XP')
                    if level_diff:
                        await ctx.send(f'{ctx.message.author.mention} has leveled up and is now {author.level}')
                else:
                    await ctx.send(f'{ctx.message.author.mention} attacks {user.mention} for {roll}!'
                                   f' Current HP = {target.current_hp}')

                if str(user.id) in the_chosen:
                    roll = random.randint(1, 20)
                    author.current_hp -= roll
                    await ctx.send(f'{user.mention} is one of the chosen!'
                            f'{ctx.message.author.mention} is smited for {roll}')

                return
            else:
                await ctx.send('The attack misses!')
                return

    @commands.command()
    async def join_battle(self, ctx):
        user = ctx.message.author
        role = discord.utils.get(user.server.roles, name=USER_ROLE)
        await discord.Client.add_roles(user, role)

    @commands.command
    async def leave_battle(self, ctx):
        author = ctx.message.author
        user = get_user(author.id)
        role = discord.utils.get(author.server.roles, name=USER_ROLE)
        #Stop people from using role bounces after they leave
        user.hp=0
        await discord.Client.remove_roles(author, role)

    @commands.command
    async def get_target_list(self, ctx):
        author = ctx.message.author
        user = get_user(author.id)
        role = discord.utils.get(author.server.roles, name=USER_ROLE)
        message = ""
        for member in ctx.message.guild.members:
            status_string = ""
            if USER_ROLE in member.roles.name:
                if PROTECTIONS.get(member.id):
                    status_string += "Protected, "
                if FARM_LIST.get(member.id):
                    status_string += "Farm protection"
                if status_string =="":
                    status_string == "Valid"
            else:
                status_string = "not_playing"
            message += member.name + " | " + status_string + "\n"
        await discord.Client.send_message(author, message)
