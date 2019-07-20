# stuff relating to managing channels on a server
import discord
from discord.ext import commands
from discord.ext.commands import has_permissions
import functions


class Channels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(pass_context=True)
    @has_permissions(manage_channels=True)
    async def channel(self, ctx):
        pass

    @channel.command(aliases=['new'])
    async def make(self, ctx, name):
        pass

    @commands.group(pass_context=True)
    @has_permissions(manage_channels=True)
    async def ignore(self, ctx):
        """$ignore [all command] [#channel...]

        marks a channel, or channels, as not monitored
        if no channels are mentioned, the current channel is assumed

        Parameters:
        [all command]
            optional sub-command
            [#channel...] is ignored if [all] is provided
            invokes the all sub-command:
                sets ignore for all channels on the server
        [#channel...]
            optional parameter
            zero or more channel mentions
            defaults to current channel if not given

        Usages:
        $ignore
            ignores the current channel

        $ignore all
            calls the all sub-command, ignores all text channels

        $ignore #channel1 #channel2
           ignores channel1 and channel2
            """
        if ctx.invoked_subcommand:
            return
        sql_c, database = functions.get_database()
        channels = ctx.message.channel_mentions
        if not channels:
            content = ctx.message.content.replace(f'{str(ctx.bot.command_prefix)}{str(ctx.command)} ', '')
            if content:
                return await ctx.send(f'"{content}" is neither a valid channel mention nor sub-command, aborting')
            channels = [ctx.message.channel]
        for channel in channels:
            sql_c.execute('insert or replace into ignoring (guild, channel) values (?, ?)',
                          (ctx.guild.id, str(channel.id),))
        database.commit()
        await ctx.send(f"No longer monitoring the following channels: {', '.join([c.name for c in channels])}")

    # noinspection PyShadowingBuiltins
    @staticmethod
    @ignore.command(pass_context=True)
    @has_permissions(manage_channels=True)
    async def all(ctx: discord.ext.commands.context.Context):
        """$ignore all

        marks all text channels as not monitored

        Parameters:
        no parameters

        Usages:
        $ignore all
            marks all text channels as not monitored
        """
        print(type(ctx.bot), ctx.bot)
        sql_c, database = functions.get_database()
        channels = [[x.id, x.name] for x in ctx.bot.get_all_channels()
                    if x.guild.id == ctx.guild.id and isinstance(x, discord.TextChannel)]
        for channel in channels:
            sql_c.execute('insert or replace into ignoring (guild, channel) values (?, ?)',
                          (ctx.guild.id, str(channel[0]),))
            database.commit()
        await ctx.send(f"No longer monitoring the following channels: {', '.join([c[1] for c in channels])}")

    del all

    @commands.group(pass_context=True)
    @has_permissions(manage_channels=True)
    async def watch(self, ctx):
        """marks a channel, or channels, as monitored
        if no channels are mentioned, the current channel is assumed
        $watch [all] [#channel...]

        Parameters:
            [all]
                optional sub-command
                [#channel...] is watched if [all] is provided
                invokes the all sub-command, which sets watch for all channels on the server
            [#channel...]
                optional parameter, zero or more channel mentions
                if no channel mentions are given, defaults to current channel

        Usages:
            $watch
                watches the current channel

            $watch all
                calls the all sub-command, watches all text channels

            $watch #channel1 #channel2
               watches channel1 and channel2
            """
        if ctx.invoked_subcommand:
            return
        sql_c, database = functions.get_database()
        channels = ctx.message.channel_mentions
        if not channels:
            content = ctx.message.content.replace(f'{str(ctx.bot.command_prefix)}{str(ctx.command)} ', '')
            if content:
                return await ctx.send(f'"{content}" is neither a valid channel mention nor sub-command, aborting')
            channels = [ctx.message.channel]
        #        return await ctx.send('its rather necessary to say what channel(s) are to be ignored.....')
        for channel in channels:
            sql_c.execute('delete from ignoring where guild=? and channel=?', (ctx.guild.id, channel.id,))
        database.commit()
        await ctx.send(f"Now monitoring the following channels: {', '.join([c.name for c in channels])}")

    # noinspection PyShadowingBuiltins
    @staticmethod
    @watch.command(pass_context=True)
    @has_permissions(manage_channels=True)
    async def all(ctx: discord.ext.commands.context.Context):
        """
        $watch all
        marks all text channels as monitored"""
        sql_c, database = functions.get_database()
        channels = [[x.id, x.name] for x in ctx.bot.get_all_channels()
                    if x.guild.id == ctx.guild.id and isinstance(x, discord.TextChannel)]
        for channel in channels:
            sql_c.execute('delete from ignoring where guild=? and channel=?', (ctx.guild.id, channel[0],))
            database.commit()
        await ctx.send(f"Now monitoring the following channels: {', '.join([c[1] for c in channels])}")

    del all

    @commands.command(pass_context=True)
    @has_permissions(manage_channels=True)
    async def ignored(self, ctx):
        """outputs a list of the text channels that are not being monitored"""
        sql_c, database = functions.get_database()
        ignoring = sql_c.execute('select * from ignoring where guild=?', (ctx.guild.id,)).fetchall()
        ignoring = [(self.bot.get_channel(int(x[1]))).name for x in ignoring]
        if ignoring:
            ignoring = ', '.join(ignoring)
        else:
            ignoring = 'None'
        await ctx.send('The following channels are not monitored for spam: ' + ignoring)


def setup(bot):
    bot.add_cog(Channels(bot))
