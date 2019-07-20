# stuff relating to managing channels on a server
import discord
from discord.ext import commands
from discord.ext.commands import has_permissions
import functions
import re
import asyncio


class Channels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    async def get_channel(ctx, *words):
        for i in range(len(words)):
            name = ' '.join(words[:i+1])
            for chan in ctx.guild.channels:
                if chan.name == name:
                    return chan
        return None

    @commands.group(pass_context=True)
    @has_permissions(manage_channels=True)  # permissions hinge on the parent command or can children get through?
    async def channel(self, ctx):
        """a collection of channel editing sub commands

        $channel <sub-command> <parameters>

        Parameters:
        <sub-command>
            required sub-command
            this command does nothing on its own - just a group
               sub-commands do all the work

        <parameter>
            required parameter
            all of the sub commands require a parameter
            see $help channel <subcommand> for more information

        Usages:
        $channel command param1 param2
            executes the named sub-command with param1 and param2

        see help page4, Sub-Commands for more information
        """
        pass

    @channel.command(pass_context=True)
    async def create(self, ctx, *name):  # tested
        """creates a text channel

        $channel create <name...>

        Parameters:
        <name...>
            required parameter
            all words given are assumed to become name
            replaces spaces with -

        Usages:
        $channel create new_channel
            creates the channel new_channel
        """
        if not name:
            await ctx.send('channels do require names you know....')
        await ctx.guild.create_text_channel(' '.join(name))

    @channel.command(pass_context=True)
    async def clone(self, ctx, name=None, *name2):  # tested
        """clones the a text channel

        $channel clone <name1> <name2...>

        Parameters:
        <name1>
            required parameter
            the channel to be cloned
            active discord channel names do not have spaces

        <name2...>
            required parameter
            the target channel name
            all words given are assumed to become name2
            replaces spaces with -

        Usages:
        $channel clone channel1 channel2
            creates the channel channel2 and copies:
                role/member permission overrides
                topic
                slowmode
                nsfw
                category
        """
        # have to do this manually...
        if name is None:
            return await ctx.send('I need to know what channel I am cloning....')
        chan = await Channels.get_channel(ctx, name)
        if chan is None:
            return await ctx.send(f'cannot find existing channel {name} to work with')
        if chan:  # then we have a channel to copy from
            print(chan, type(chan), dir(chan))
            chan2 = await ctx.guild.create_text_channel(' '.join(name2))
            chan2.nsfw = chan.is_nsfw()
            permits = chan.overwrites
            for perm in permits:
                await chan2.set_permissions(perm[0], overwrite=perm[1])
            await chan2.edit(topic=chan.topic,
                             position=chan.position,
                             nsfw=chan.is_nsfw(),
                             category=chan.category,
                             slowmode_delay=chan.slowmode_delay)

    @channel.command(pass_context=True)
    async def delete(self, ctx, *name):  # tested
        """deletes a text channel

        $channel delete <name...>

        Parameters:
        <name...>
            required parameter
            the target channel name
            all words given are assumed to become name2

        Usages:
        $channel clone channel1 channel2
            creates the channel channel2 and copies:
                role/member permission overrides
                topic
                slowmode
                nsfw
                category
        """
        chan = await Channels.get_channel(ctx, *name)
        if chan is None:
            return await ctx.send(f'cannot find existing channel {name} to work with')
        await chan.delete()

    @channel.group(pass_context=True)
    async def rename(self, ctx, name=None, *new):
        """renames the a text channel

        $channel rename <name1> <name2...>

        Parameters:
        <name1>
            required parameter
            the channel to be renamed
            active discord channel names do not have spaces

        <name2...>
            required parameter
            the name the channels is being renamed to
            all words given are assumed to become name2
            replaces spaces with -

        Usages:
        $channel rename name name two
            finds the channel named name,
            changes its name to name-two
        """
        if name is None:
            return await ctx.send('I need to know what channel I am renaming....')
        chan = await Channels.get_channel(ctx, name)
        if chan is None:
            return await ctx.send(f'cannot find existing channel {name} to work with')
        await chan.edit(name=' '.join(new))

    @channel.group(pass_context=True)
    async def topic(self, ctx, name=None, *topic):  # tested
        """sets a channel topic

        $channel topic <name> [topic...]

        Parameters:
        <name>
            required parameter
            the channel to be renamed
            active discord channel names do not have spaces

        [topic...]
            optional parameter
            all words given are assumed to become the topic

        Usages:
        $channel topic name this is the topic
            finds the channel named name,
            changes its topic to 'this is the topic'
        """
        if name is None:
            return await ctx.send('I need to know what channel I am giving a topic to....')
        chan = await Channels.get_channel(ctx, name)
        if chan is None:
            return await ctx.send(f'cannot find existing channel {name} to work with')
        await chan.edit(topic=' '.join(topic))

    @channel.group(pass_context=True)
    async def position(self, ctx, name=None, pos=None):  # tested
        """sets a channel position

        $channel position <name1> <pos>

        Parameters:
        <name>
            required parameter
            the channel to be renamed
            active discord channel names do not have spaces

        <pos>
            required parameter
            the new position of the channel
            integers only, no maximum
            large values are silently constrained to last position

        Usages:
        $channel position name 3
            finds the channel named name,
            moves it to the third spot in the list
        """
        if name is None:
            return await ctx.send('I need to know what channel I am moving....')
        if pos is None:
            return await ctx.send(f'I need to know what position I am moving {name} to....')
        chan = await Channels.get_channel(ctx, name)
        if chan is None:
            return await ctx.send(f'cannot find existing channel {name} to work with')
        try:
            pos = int(pos)
        except ValueError:
            return await ctx.send('position must be an integer')
        pos = min(pos, len(chan.category.channels) - 1)
        await chan.edit(position=pos)

    @channel.group(pass_context=True)
    async def nsfw(self, ctx, name=None, nsfw=None):  # tested
        """sets a channel's NSFW flag

        $channel nsfw <name> <setting>

        Parameters:
        <name>
            required parameter
            the channel whose nsfw flag is being set
            active discord channel names do not have spaces

        <setting>
            required parameter
            on is one of 'yes', 'y', 'true', 't', '1', 'enable', 'on', 'affirmative'
            off is on of 'no', 'n', 'false', 'f', '0', 'disable', 'off', 'negative'

        Usages:
        $channel nsfw channel 1
            enables nsfw on for channel

        $channel nsfw channel negative
            sets nsfw off for channel
        """
        if name is None:
            return await ctx.send('I need to know what channel I am changing NSFW for....')
        if nsfw is None:
            return await ctx.send(f'I need to know if we are turning {name}\'s NSFW setting on or off....')
        chan = await Channels.get_channel(ctx, name)
        if chan is None:
            return await ctx.send(f'cannot find existing channel {name} to work with')
        nsfw = functions.boolean(nsfw)
        if nsfw is None:
            return await ctx.send('invalid nsw setting')
        await chan.edit(nsfw=nsfw)

    @channel.group(pass_context=True)
    async def category(self, ctx, name=None, *category):  # tested
        """sets a channel's category

        $channel category <name> [category...]

        Parameters:
        <name>
            required parameter
            the channel whose nsfw flag is being set
            active discord channel names do not have spaces

        [category...]
            optional parameter
            the category the channels is being assigned to
            defaults to no category
            all words given are assumed to be a category name

        Usages:
        $channel category channel Text Channels
            moves channel to category 'Text Channels'
        """
        if name is None:
            return await ctx.send('I need to know what channel I am changing the category of....')
        chan = await Channels.get_channel(ctx, name)
        if chan is None:
            return await ctx.send(f'cannot find existing channel {name} to work with')
        chan2 = await Channels.get_channel(ctx, ' '.join(category))
        await chan.edit(category=chan2)

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
            content = re.sub(f'.*\{str(ctx.bot.command_prefix)}{str(ctx.command)}[ ]*', '', ctx.message.content)
            if content:
                return await ctx.send(f'"{content}" is neither a valid channel mention nor sub-command, aborting')
            channels = [ctx.message.channel]
        for channel in channels:
            sql_c.execute('insert or replace into ignoring (guild, channel) values (?, ?)',
                          (ctx.guild.id, str(channel.id),))
        database.commit()
        await ctx.send(f"No longer monitoring the following channels: {', '.join([c.name for c in channels])}")

    @ignore.command(pass_context=True, name='all')
    @has_permissions(manage_channels=True)
    async def _iall(self, ctx: discord.ext.commands.context.Context):
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
            content = re.sub(f'.*\{str(ctx.bot.command_prefix)}{str(ctx.command)}[ ]*', '', ctx.message.content)
            if content:
                return await ctx.send(f'"{content}" is neither a valid channel mention nor sub-command, aborting')
            channels = [ctx.message.channel]
        for channel in channels:
            sql_c.execute('delete from ignoring where guild=? and channel=?', (ctx.guild.id, channel.id,))
        database.commit()
        await ctx.send(f"Now monitoring the following channels: {', '.join([c.name for c in channels])}")

    @watch.command(pass_context=True, name='all')
    @has_permissions(manage_channels=True)
    async def _wall(self, ctx: discord.ext.commands.context.Context):
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
