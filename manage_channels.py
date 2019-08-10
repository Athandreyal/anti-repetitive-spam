# stuff relating to managing channels on a server
import discord
from discord.ext import commands
from discord.ext.commands import has_permissions
import functions
import re

bot_message_expire = functions.message_expire()


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
            await ctx.send('channels do require names you know....', delete_after=bot_message_expire)
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
            return await ctx.send('I need to know what channel I am cloning....', delete_after=bot_message_expire)
        chan = await Channels.get_channel(ctx, name)
        if chan is None:
            return await ctx.send(f'cannot find existing channel {name} to work with', delete_after=bot_message_expire)
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
            return await ctx.send(f'cannot find existing channel {name} to work with', delete_after=bot_message_expire)
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
            return await ctx.send('I need to know what channel I am renaming....', delete_after=bot_message_expire)
        chan = await Channels.get_channel(ctx, name)
        if chan is None:
            return await ctx.send(f'cannot find existing channel {name} to work with', delete_after=bot_message_expire)
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
            return await ctx.send('I need to know what channel I am giving a topic to....',
                                  delete_after=bot_message_expire)
        chan = await Channels.get_channel(ctx, name)
        if chan is None:
            return await ctx.send(f'cannot find existing channel {name} to work with', delete_after=bot_message_expire)
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
            return await ctx.send('I need to know what channel I am moving....', delete_after=bot_message_expire)
        if pos is None:
            return await ctx.send(f'I need to know what position I am moving {name} to....',
                                  delete_after=bot_message_expire)
        chan = await Channels.get_channel(ctx, name)
        if chan is None:
            return await ctx.send(f'cannot find existing channel {name} to work with', delete_after=bot_message_expire)
        try:
            pos = int(pos)
        except ValueError:
            return await ctx.send('position must be an integer', delete_after=bot_message_expire)
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
            return await ctx.send('I need to know what channel I am changing NSFW for....',
                                  delete_after=bot_message_expire)
        if nsfw is None:
            return await ctx.send(f'I need to know if we are turning {name}\'s NSFW setting on or off....',
                                  delete_after=bot_message_expire)
        chan = await Channels.get_channel(ctx, name)
        if chan is None:
            return await ctx.send(f'cannot find existing channel {name} to work with', delete_after=bot_message_expire)
        nsfw = functions.boolean(nsfw)
        if nsfw is None:
            return await ctx.send('invalid nsw setting', delete_after=bot_message_expire)
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
            return await ctx.send('I need to know what channel I am changing the category of....',
                                  delete_after=bot_message_expire)
        chan = await Channels.get_channel(ctx, name)
        if chan is None:
            return await ctx.send(f'cannot find existing channel {name} to work with', delete_after=bot_message_expire)
        chan2 = await Channels.get_channel(ctx, ' '.join(category))
        await chan.edit(category=chan2)

    @commands.group(pass_context=True)
    @has_permissions(manage_channels=True)
    async def ignore(self, ctx):
        """marks a channel, or channels, as not monitored
        if no channels are mentioned, the current channel is assumed

        $ignore [all command] [#channel...] [@role...] [@user...]

        Parameters:
        [all command]
            optional sub-command
            [#channel...] is not used if [all] is provided
            invokes the all sub-command:
                sets ignore for all channels on the server
        [#channel...]
            optional parameter
            zero or more channel mentions
            defaults to current channel if no other mentions are given

        [@role...]
            optional parameter
            zero or more role mentions
            ignored if not given

        [@user...]
            optional parameter
            zero or more user mentions
            ignored if not given

        Usages:
        $ignore
            ignores the current channel

        $ignore all
            calls the all sub-command, ignores all text channels

        $ignore #channel1 #channel2
            ignores channel1 and channel2

        $ignore #channel1 @everyone
            ignores channel1 and every member of the everyone role

        $ignore #channel1 @user
            ignores channel1 and @user
            """
        if ctx.invoked_subcommand:
            return
        sql_c, database = functions.get_database()
        channels = ctx.message.channel_mentions
        users = ctx.message.mentions
        roles = ctx.message.role_mentions
        mentions = channels + users + roles
        if not mentions:
            content = re.sub(f'.*\{str(ctx.bot.command_prefix)}{str(ctx.command)}[ ]*', '', ctx.message.content)
            if content:
                return await ctx.send(f'"{content}" is neither a valid channel/user/role mention nor sub-command, '
                                      f'aborting\n if this were an attempt to mention a role, it is necessary to '
                                      f'first enable mentioning this role.', delete_after=bot_message_expire)
            channels = [ctx.message.channel]
        for channel in channels:
            sql_c.execute('insert or replace into ignored_channels (guild, id) values (?, ?)',
                          (ctx.guild.id, channel.id,))
        for role in roles:
            sql_c.execute('insert or replace into ignored_roles (guild, id) values (?, ?)',
                          (ctx.guild.id, role.id,))
        for user in users:
            sql_c.execute('insert or replace into ignored_users (guild, id) values (?, ?)',
                          (ctx.guild.id, user.id,))
        database.commit()
        m = ['No longer monitoring the following']
        if channels:
            m += [f'Channels:        {", ".join([c.name for c in channels])}']
        if roles:
            m += [f'Roles:        {", ".join([c.name for c in roles])}']
        if users:
            m += [f'Users:        {", ".join([c.name for c in users])}']
        m = '\n'.join(m)
        await ctx.send(m)

    @ignore.command(pass_context=True, name='all')
    @has_permissions(manage_channels=True)
    async def _iall(self, ctx: discord.ext.commands.context.Context):
        """marks all text channels as not monitored

        $ignore all

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
            sql_c.execute('insert or replace into ignored_channel (guild, id) values (?, ?)',
                          (ctx.guild.id, channel[0],))
            database.commit()
        await ctx.send(f"No longer monitoring the following channels: {', '.join([c[1] for c in channels])}")

    @commands.group(pass_context=True)
    @has_permissions(manage_channels=True)
    async def watch(self, ctx):
        """marks a channel, or channels, monitored
        if no channels are mentioned, the current channel is assumed

        watch [all command] [#channel...] [@role...] [@user...]

        Parameters:
        [all command]
            optional sub-command
            [#channel...] is not used if [all] is provided
            invokes the all sub-command:
                sets watch for all channels on the server
        [#channel...]
            optional parameter
            zero or more channel mentions
            defaults to current channel if no other mentions are given

        [@role...]
            optional parameter
            zero or more role mentions
            ignored if not given

        [@user...]
            optional parameter
            zero or more user mentions
            ignored if not given

        Usages:
        $watch
            watches the current channel

        $watch all
            calls the all sub-command, watches all text channels

        $watch #channel1 #channel2
            watches channel1 and channel2

        $watch #channel1 @everyone
            watches channel1 and every member of the everyone role

        $watch #channel1 @user
            watches channel1 and @user
            """
        if ctx.invoked_subcommand:
            return
        sql_c, database = functions.get_database()
        channels = ctx.message.channel_mentions
        users = ctx.message.mentions
        roles = ctx.message.role_mentions
        mentions = channels + users + roles
        if not mentions:
            content = re.sub(f'.*\{str(ctx.bot.command_prefix)}{str(ctx.command)}[ ]*', '', ctx.message.content)
            if content:
                return await ctx.send(f'"{content}" is neither a valid channel/user/role mention nor sub-command, '
                                      f'aborting\n if this were an attempt to mention a role, it is necessary to '
                                      f'first enable mentioning this role.', delete_after=bot_message_expire)
            channels = [ctx.message.channel]
        for channel in channels:
            sql_c.execute('delete from ignored_channels where guild=? and id=?', (ctx.guild.id, channel.id,))
        for role in roles:
            sql_c.execute('delete from ignored_roles where guild=? and id=?', (ctx.guild.id, role.id,))
        for user in users:
            sql_c.execute('delete from ignored_users where guild=? and id=?', (ctx.guild.id, user.id,))
        database.commit()
        m = ['Now monitoring the following']
        if channels:
            m += [f'Channels:        {", ".join([c.name for c in channels])}']
        if roles:
            m += [f'Roles:        {", ".join([c.name for c in roles])}']
        if users:
            m += [f'Users:        {", ".join([c.name for c in users])}']
        m = '\n'.join(m)
        await ctx.send(m)

    @watch.command(pass_context=True, name='all')
    @has_permissions(manage_channels=True)
    async def _wall(self, ctx: discord.ext.commands.context.Context):
        """marks all text channels as monitored
        $watch all

        Parameters:
        no parameters

        Usages:
        watch all
            marks all text channels as monitored
        """
        sql_c, database = functions.get_database()
        channels = [[x.id, x.name] for x in ctx.bot.get_all_channels()
                    if x.guild.id == ctx.guild.id and isinstance(x, discord.TextChannel)]
        for channel in channels:
            sql_c.execute('delete from ignored_channels where guild=? and id=?', (ctx.guild.id, channel[0],))
            database.commit()
        await ctx.send(f"Now monitoring the following channels: {', '.join([c[1] for c in channels])}")

    @commands.command(pass_context=True)
    @has_permissions(manage_channels=True)
    async def ignored(self, ctx):
        """outputs a list of the text channels that are not being monitored"""
        sql_c, database = functions.get_database()
        ignoring_channels = sql_c.execute('select * from ignored_channels where guild=?', (ctx.guild.id,)).fetchall()
        ignoring_roles = sql_c.execute('select * from ignored_roles where guild=?', (ctx.guild.id,)).fetchall()
        ignoring_users = sql_c.execute('select * from ignored_users where guild=?', (ctx.guild.id,)).fetchall()
        channels = [(self.bot.get_channel(x[1])).name for x in ignoring_channels]
        roles = [discord.utils.get(ctx.guild.roles, id=x[1]).name for x in ignoring_roles]
        users = [(self.bot.get_user(x[1])).name for x in ignoring_users]
        ignoring = channels + roles + users
        m = ['The guild owner, admin privileged users, and this bot\'s commands are ignored by default\n'
             'The following are also not monitored:']
        if channels:
            m += [f'Channels:        {", ".join(channels)}']
        if roles:
            m += [f'Roles:        {", ".join(roles)}']
        if users:
            m += [f'Users:        {", ".join(users)}']
        if not ignoring:
            m += ['Nothing, all other roles/channels/users are being monitored.']
        m = '\n'.join(m)
        await ctx.send(m)


def setup(bot):
    bot.add_cog(Channels(bot))
