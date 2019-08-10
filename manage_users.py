# stuff relating to managing users on the server
import discord
from discord.ext import commands
from discord.ext.commands import has_permissions
import re
import datetime
import functions

bot_message_expire = functions.message_expire()


class Users(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(pass_context=True)
    @has_permissions(ban_members=True, kick_members=True)
    async def warn(self, ctx, *args):
        """$warn <@user> [@user...] [reason Text]

        warns the mentioned user(s) across all channels on the server

        Parameters:
        <@user>
            required parameter
            at least one @user must be mentioned
        [@user...]
            optional parameter(s)
            0 or more additional users may be mentioned
            There is no maximum number of mentioned users
        [reason Text]
            optional parameter
            will default to 'No Reason' if not provided
            the reason is taken left to right
                from everything not recognised as:
                    a mention, users or channels
                    one of days=, hours=, minutes=, seconds

        Usages:
        $warn @user
            gives user a server wide warning

        $warn @user1 @user2
            gives both user1 and user2 a server wide warning
        """
        users = ctx.message.mentions
        if not users:
            return await ctx.send('it might help if you told me *who*...', delete_after=bot_message_expire)
        reason = [x for x in args if not re.match('.*(<[@|#]!?[0-9]{18}>).*', x)]

        if not reason:
            reason = ['No', 'Reason']
        for u in users:
            await functions.warning(ctx=ctx, channel=ctx.channel,
                                    issuer=ctx.message.author.mention + ' is',
                                    who=u, where=ctx.guild, why=reason)

    @commands.command(pass_context=True)
    @has_permissions(manage_roles=True)
    async def mute(self, ctx, *args):
        """$mute <@user> [@user...] [#channel...] [reason text]
              [days=int] [hours=int] [minutes=int] [seconds=int]

        mutes the mentioned user(s) on the mentioned channel(s)

        Parameters:
        <@user>
            required parameter
            at least one @user mention is necessary
        [@user...]
            optional parameter
            zero or more additional users may be mentioned
            there is no maximum number of user mentions
        [#channel...]
            optional parameter
            zero or more channels may be mentioned
            there is no maximum number of channel mentions
        [reason text]
            optional parameter
            will default to 'No Reason' if not provided
            the reason is taken left to right
                from everything not recognised as:
                    a mention, users or channels
                    one of days=, hours=, minutes=, seconds
        [days=int]
            optional parameter
            adds the specified number of days, in seconds
            integers only, defaults to zero, no maximum
        [hours=int]
            optional parameter
            adds the specified number of hours, in seconds
            integers only, defaults to zero, no maximum
        [minutes=int]
            optional parameter
            adds the specified number of minutes, in seconds
            integers only, defaults to zero, no maximum
        [seconds=int]
            optional parameter
            adds the specified number of seconds
            integers only, defaults to zero, no maximum

        Usages:
        $mute @user
            reason will default to No reason
            channel will default to current channel
            time will default to escalation settings

        $mute @user #channel
            reason will default to No reason
            channel will be #channel
            time will default to escalation settings

        $mute @user #channel I want to
            reason will be 'I want to'
            channel will be #channel
            time will default to escalation settings

        $mute @user #channel I want to hours=3 minutes=30
            reason will be 'I want to'
            channel will be #channel
            time will be 3 hours, 30 minutes

        parameter order is not important
        multiple users may be mentioned in one call
        multiple channels may be mentioned in one call
        any, all, or none of days, hours, minutes, seconds

        for example, this works:
        $mute days=1 while @user1 hours=2 crazy #channel2 this
              @user2 minutes=3 does #channel1 work seconds=4

        this will:
            mute @user1 and @user2,
                on both #channel1 and #channel2,
                for 1 day, 2 hours, 3 minutes, 4 seconds
                with the reason: "while crazy this does work"
        """
        users = ctx.message.mentions
        if not users:
            return await ctx.send('it might help if you told me *who*...', delete_after=bot_message_expire)
        time = 0
        time_frames = {'days': 86400, 'hours': 3600, 'minutes': 60, 'seconds': 1}
        args = list(args)

        # trim the kwargs out of args, since the python discord api doesn't handle this itself
        kwargs = dict()
        for param in args:
            # noinspection Annotator
            if re.match('.*([DAY|HOUR|MINUTE|SECOND]S=).*', param.upper()):
                k, v = param.split('=', 1)
                try:
                    kwargs[k] = int(v)
                    time += (int(v) * time_frames[k])
                except ValueError:
                    return await ctx.send(f'{k} must be an integer, not {v}', delete_after=bot_message_expire)
        for k in kwargs:
            args.remove(f'{k}={kwargs[k]}')

        channels = ctx.message.channel_mentions
        if not channels:
            channels = [ctx.channel]
        reason = [x for x in args if not re.match('.*(<[@|#]!?[0-9]{18}>).*', x)]
        successful = {}
        for member in users:
            admin = any((role.permissions.administrator for role in member.roles))
            if admin or member.id == ctx.guild.owner.id:
                await ctx.send(f'I am unable to {ctx.command} {member.mention}', delete_after=bot_message_expire)
            else:
                for mute_channel in channels:
                    try:
                        await functions.mute_user(*reason, channel=mute_channel, guild=ctx.guild, member=member,
                                                  ctx=ctx, time=time)
                        try:
                            successful[member] += [mute_channel.name]
                        except KeyError:
                            successful[member] = [mute_channel.name]
                    except discord.Forbidden:
                        await ctx.send(f'I am unable to {ctx.command} {member.mention} in {mute_channel}',
                                       delete_after=bot_message_expire)

    @commands.command(pass_context=True)
    @has_permissions(manage_roles=True)
    async def unmute(self, ctx, *args):
        """$unmute <@user> [@user...] [#channel...] [reason text]

        unmutes the mentioned user(s) on the mentioned channel(s)
        will reset the message history
        begins the process of expiring escalations/warnings

        Parameters:
        <@user>
            required parameter
            at least one @user mention is necessary
        [@user...]
            optional parameter
            zero or more additional users may be mentioned
            there is no maximum number of user mentions
        [#channel...]
            optional parameter
            zero or more channels may be mentioned
            there is no maximum number of channel mentions
        [reason text]
            optional parameter
            will default to 'No Reason' if not provided
            the reason is taken left to right
                from everything not recognised as a mention

        Usages:
        $unmute @user
            reason will default to No reason
            channel will default to current channel

        $unmute @user #channel
            reason will default to No reason
            channel will be #channel

        $unmute @user #channel I want to
            reason will be 'I want to'
            channel will be #channel

        order of mentions and reason are not important
        multiple users may be mentioned in one call
        multiple channels may be mentioned in one call

        for example, this works:
        $unmute because @user1 this #channel2 is @user2 useful #channel1

        this will:
            unmute @user1 and @user2 now,
                on both #channel1 and #channel2,
                with the reason: "because this is useful"
        """
        users = ctx.message.mentions
        if not users:
            return await ctx.send('it might help if you told me *who*...', delete_after=bot_message_expire)
        args = list(args)

        channels = ctx.message.channel_mentions
        if not channels:
            channels = [ctx.channel]
        reason = [x for x in args if not re.match('.*(<[@|#]!?[0-9]{18}>).*', x)]
        for member in users:
            for mute_channel in channels:
                try:
                    await functions.un_mute_user(channel=mute_channel, member=member, ctx=ctx, *reason)
                except discord.Forbidden:
                    await ctx.send(f'I am unable to {ctx.command} {member.mention} in {mute_channel}',
                                   delete_after=bot_message_expire)

    @commands.command(pass_context=True)
    @has_permissions(manage_messages=True)
    async def messages(self, ctx, member: discord.Member = None):
        """$messages [@user]

        prints the given user's recent messages
        shows oldest first
        splits across several messages if necessary

        Parameters:
        [@user]
            optional parameter, maximum of one user mention

        Usages:
        $messages
            will show your recent messages

        $messages @user
            will show @user's recent messages
        """

        if not member:
            member = ctx.message.author
        sql_c, database = functions.get_database()
        query = 'select m5, m4, m3, m2, m1 from messages where channel=? and id=?;'
        recent = sql_c.execute(query, (ctx.channel.id, member.mention,)).fetchall()
        if recent:
            recent = recent[0]  # drop the outer array layer
        title = f'{member.display_name}\'s recent messages'
        embed = discord.Embed()
        embed1 = None
        embed2 = None
        embed3 = None
        length = 0
        for i, message in enumerate([m.split(':', 1) for m in recent]):
            if len(message) == 2 and isinstance(message, list):
                message = message[1]
            if message != '':
                if len(message) + length > 5500:
                    if embed1 and embed2:
                        embed3 = embed
                    elif embed1:
                        embed2 = embed
                    else:
                        embed1 = embed
                    embed = discord.Embed()
                    length = 0

                if len(message) > 1012:
                    embed.add_field(name=str(i - len(recent)) + '.1', inline=False, value=message[:1012])
                    embed.add_field(name=str(i - len(recent)) + '.2', inline=False, value=message[1012:])
                else:
                    embed.add_field(name=str(i - len(recent)), inline=False, value=message)
                length += len(message)

        if embed1 and embed2:
            embed3 = embed
        elif embed1:
            embed2 = embed
        else:
            embed1 = embed

        if embed3:
            embed1.title = title + ', part 1'
            embed2.title = title + ', part 2'
            embed3.title = title + ', part 3'
        elif embed2:
            embed1.title = title + ', part 1'
            embed2.title = title + ', part 2'
        else:
            embed1.title = title

        await ctx.send(embed=embed1, delete_after=bot_message_expire)
        if embed2:
            await ctx.send(embed=embed2, delete_after=bot_message_expire)
        if embed3:
            await ctx.send(embed=embed3, delete_after=bot_message_expire)

    @commands.command(pass_context=True)
    @has_permissions(ban_members=True)
    async def ban(self, ctx, *args):
        """$ban <@user> [@user...] [reason] [delete=int]

        bans user(s) via mention from the current guild

        Parameters:
        <@user>
            required parameter
            at least one user mention is necessary
        [@user...]
            optional parameter
            zero or more additional users may be mentioned
            there is no maximum number of user mentions
        [reason text]
            optional parameter
            will default to 'No Reason' if not provided
            the reason is taken left to right
                from everything not recognised as:
                    a mention, users or channels
                    delete=int
        [delete=int]
            optional parameter
            deletes the last 'delete' days of user's messages
            integer only, maximum of 7

        order of arguments does not matter
        multiple users may be mentioned in one call

        Usages:
        $ban @user
            bans user from the server
            reason defaults to 'No Reason'
            no messages are deleted from channels

        $ban @user I want to
            bans user from the server
            reason is 'I want to'
            no messages are deleted from channels

        $ban @user I want to delete=3
            bans user from the server
            reason is 'I want to'
            removes all of user's messages posted for the last 3 days
        """
        users = ctx.message.mentions
        if not users:
            return await ctx.send('it might help if you told me *who*...', delete_after=bot_message_expire)
        args = list(args)
        delete = 0
        kwargs = dict()
        for param in args:
            if re.match('.*(DELETE=).*', param.upper()):
                k, v = param.split('=', 1)
                try:
                    kwargs[k] = int(v)
                    delete = int(v)
                except ValueError:
                    return await ctx.send(f'{k} must be an integer, not {v}', delete_after=bot_message_expire)
        for k in kwargs:
            args.remove(f'{k}={kwargs[k]}')

        reason = [x for x in args if not re.match('.*(<[@|#]!?[0-9]{18}>).*', x)]
        for member in users:
            try:
                await ctx.guild.ban(member, reason=' '.join(reason), delete_message_days=delete)
                await functions.log_action(ctx, functions.Action.Ban, member.mention, reason)
                await ctx.send(f'{member.mention} has been banned')
            except discord.Forbidden:
                await ctx.send(f'I am unable to {ctx.command} {member.mention}', delete_after=bot_message_expire)

    @commands.command(pass_context=True)
    @has_permissions(ban_members=True)
    async def banid(self, ctx, *args):
        """$ban <uid int> [uid int] [reason text] [delete=int]

        bans user(s) via uid from the current guild

        Parameters:
        <uid int>
            required parameter
            user id number of the target to ban
        [uid int...]
            optional parameter
            zero or more additional user ID's may be given
            there is no maximum number of user id's
        [reason text]
            optional parameter
            will default to 'No Reason' if not provided
            the reason is taken left to right
                from everything not recognised as:
                    a 4-18 digit integer
                    delete=int
        [delete=int]
            optional parameter
            deletes the last 'delete' days of user's messages
            integer only, maximum of 7

        order of arguments does not matter
        multiple user id's may be given in one call

        integer values between 4 and 17 digits long, inclusive, will be discarded as erroneous UIDs

        Usages:
        $ban 012345678901234567
            bans a user with id=0123456789012345678 from the server
            reason defaults to 'No Reason'
            no messages are deleted from channels

        $ban 012345678901234567 I want to
            bans a user with id=0123456789012345678 from the server
            reason is 'I want to'
            no messages are deleted from channels

        $ban 012345678901234567 I want to delete=3
            bans a user with id=0123456789012345678 from the server
            reason is 'I want to'
            removes all of user's messages posted for the last 3 days
        """

        # ban them via discord.Object(id=uid)
        # then lookup their user object via ctx.guild.bans() since I can get it that way.

        # get the possible UID's, including obviously incorrect but potential typo UIDs that are too short
        args = list(args)

        user_ids = [x for x in args if x.isdigit() and len(x) > 4]

        # get the delete value
        delete = 0
        kwargs = dict()
        for param in args:
            if re.match('.*(DELETE=).*', param.upper()):
                k, v = param.split('=', 1)
                try:
                    kwargs[k] = int(v)
                    delete = int(v)
                except ValueError:
                    return await ctx.send(f'{k} must be an integer, not {v}', delete_after=bot_message_expire)

        # strip the delete parameter form the args
        for k in kwargs:
            args.remove(f'{k}={kwargs[k]}')
        # strip uids from args
        for user_obj in user_ids:
            args.remove(user_obj)
        # drop obviously too short user ids
        user_ids = [int(u) for u in user_ids if len(u) == 18]  # drop the too short uid values
        if not user_ids:
            return await ctx.send('it might help if you told me *who*...', delete_after=bot_message_expire)

        # what remains is assumed to be the reason
        reason = args

        for uid in user_ids:
            user_obj = discord.Object(id=uid)
            try:
                await ctx.guild.ban(user_obj, reason=' '.join(reason), delete_message_days=delete)
                bans = await ctx.guild.bans()
                for b in bans:
                    if b.user.id == uid:
                        user_obj = b.user
                if hasattr(user_obj, 'mention'):
                    await functions.log_action(ctx, functions.Action.Ban, f'{user_obj.mention}', reason)
                elif hasattr(user_obj, 'name') and hasattr(user_obj, 'discriminator'):
                    await functions.log_action(ctx, functions.Action.Ban,
                                               f'{user_obj.name}#{user_obj.discriminator}', reason)
                else:
                    await functions.log_action(ctx, functions.Action.Ban, f'@<{uid}>', reason)
            except discord.Forbidden:
                await ctx.send(f'I am unable to {ctx.command} {uid}', delete_after=bot_message_expire)

    @commands.command(pass_context=True)
    @has_permissions(ban_members=True)
    async def unban(self, ctx, *args):
        """$unban <uid int> [uid int] [reason text]

        unbans user(s) via uid from the current guild

        Parameters:
        <uid int>
            required parameter
            user id number of the user to unban
        [uid int...]
            optional parameter
            zero or more additional user ID's may be given
            there is no maximum number of user id's
        [reason text]
            optional parameter
            will default to 'No Reason' if not provided
            the reason is taken left to right
                from everything not recognised as:
                    an 18 digit integer
                    delete=int

        order of arguments does not matter
        multiple user id's may be given in one call

        Usages:
        $unban 012345678901234567
            unbans the user with that id from the server
            reason defaults to 'No Reason'

        $unban 012345678901234567 I want to
            unbans the user with that id from the server
            reason is 'I want to'
        """
        # async def unban(ctx, member, *reason):
        args = list(args)

        user_ids = [x for x in args if x.isdigit() and len(x) > 4]

        # strip uids from args
        for user_obj in user_ids:
            args.remove(user_obj)
        # drop obviously too short user ids
        user_ids = [int(u) for u in user_ids if len(u) == 18]  # drop the too short uid values
        if not user_ids:
            return await ctx.send('it might help if you told me *who*...', delete_after=bot_message_expire)

        # what remains is assumed to be the reason
        reason = args

        bans = await ctx.guild.bans()
        if bans:
            for u in bans:
                if u.user.id in user_ids:
                    target = u.user
                    try:
                        await ctx.guild.unban(target, reason=' '.join(reason))
                        await functions.log_action(ctx, functions.Action.Unban, target.mention, reason)
                        await ctx.send(f'{target.mention} has been un-banned')
                    except discord.Forbidden:
                        await ctx.send(f'I am unable to {ctx.command} {target.id}', delete_after=bot_message_expire)

    @commands.command(pass_context=True)
    @has_permissions(ban_members=True)
    async def banned(self, ctx, uid=None):
        """$banned [uid]

        shows the banned user(s) and the reason given

        Parameters:
        [uid]
            optional parameter
            if given, is used to get that users ban

        Usages:
        $banned
            shows the complete set of banned users

        $banned uid
            shows the banned user and the reason
            """
        bans = await ctx.guild.bans()
        if not bans:
            return await ctx.send('There are no banned users at this time')
        if uid:
            user_ban = [u for u in bans if int(u.user.id) == int(uid)]
            if not user_ban:
                return await ctx.send(f'User {uid} does not appear to be banned.')
            user_ban = user_ban[0]
            await ctx.send(f'{user_ban.user} was banned for {user_ban.reason}')
        else:
            embed = None
            for i, user_ban in enumerate(bans):
                if i % 25 == 0:
                    if embed:
                        await ctx.send(embed=embed)
                    embed = discord.Embed(title='Banned users')
                embed.add_field(name=str(user_ban.user) + '\n' + str(user_ban.user.id),
                                value=user_ban.reason, inline=False)
            await ctx.send(embed=embed)

    @commands.command(pass_context=True)
    @has_permissions(kick_members=True)
    async def kick(self, ctx, *args):
        """$kick <@user> [@user...] [reason text]

        kicks user(s) via mention from the current guild

        Parameters:
        <@user>
            required parameter
            at least one user mention is necessary
        [@user...]
            optional parameter
            zero or more additional users may be mentioned
            there is no maximum number of user mentions
        [reason text]
            optional parameter
            will default to 'No Reason' if not provided
            the reason is taken left to right
                from everything not recognised as a user mention

        order of user mentions and reason is not important
        multiple users may be mentioned in one call

        Usages:
        $kick @user
            kicks user from the server
            reason defaults to 'No Reason'

        $kick @user I want to
            kicks user from the server
            reason is 'I want to'

        $kick @user I want @user2 to
            kicks @user and @user2 from the server
            reason is 'I want to'
        """

        users = ctx.message.mentions
        if not users:
            return await ctx.send('it might help if you told me *who*...', delete_after=bot_message_expire)
        args = list(args)

        reason = [x for x in args if not re.match('.*(<[@|#]!?[0-9]{18}>).*', x)]
        for member in users:
            try:
                await ctx.guild.kick(member, reason=' '.join(reason))
                await functions.log_action(ctx, functions.Action.Kick, member.mention, reason)
                await ctx.send(f'{member.mention} has been kicked')
            except discord.Forbidden:
                await ctx.send(f'I am unable to {ctx.command} {member.mention}', delete_after=bot_message_expire)

    @commands.command(pass_context=True)
    async def expire(self, ctx, member: discord.Member = None):
        """$expire [@user]

        gets the current mute state of the user across all channels on the server

        Parameters:
            [@user]
                optional parameter, defaults to message author if not given

        Usages:
            $expire
                gets the expiration state for the calling user

            $expire @user
                gets the expiration state of the mentioned user"""

        if member:
            target = member
        else:
            target = ctx.message.author
        entries = functions.read_messages(target.mention)
        if entries:
            escalates = [x for x in entries if x.escalate > 0]
            warnings = [x for x in entries if x.expire > 0 and x.escalate == 0]
        else:
            escalates = []
            warnings = []
        now = int(datetime.datetime.utcnow().timestamp())

        if escalates:
            embed = discord.Embed(title=target.name + '\'s escalation state per channel')
            for muting in escalates:
                channel = self.bot.get_channel(int(muting.channel))
                s = 'Level %d\n' % muting.escalate
                if muting.muted:
                    s += 'Muted: True\nExpires: ' + functions.expire_str(muting.expire - now)
                else:
                    s += 'Muted: False\nExpires: '
                    if muting.escalate > 0:
                        s += functions.expire_str(functions.escalate[muting.escalate] - (now - muting.expire))
                embed.add_field(name=channel.name, value=s)
            await ctx.send(embed=embed)
        if warnings:
            embed = discord.Embed(title=target.name + '\'s warning state per channel')
            for w in warnings:
                embed.add_field(name=self.bot.get_channel(int(w.channel)),
                                value='Expires: ' + functions.expire_str(functions.un_warn + w.expire - now))
            await ctx.send(embed=embed)
        if not escalates and not warnings:
            await ctx.send(f'{target} has no escalations pending expiration')

    @commands.group(pass_context=True)
    @has_permissions(manage_roles=True)
    async def role(self, ctx):
        """collection of commands for setting roles

        $role <sub-command> [parameters...]

        Parameters:
        <sub-command>
            required parameter
            this command does nothing by itself

            a sub-command must be called
            sub-commands are invite, default, force_accept

        Usages:
        $role invite <role>
             will set the invite role
             see $help role invite for more info

        $role default <role>
             will set the default role for members
             see $help role default for more info

        $role force_accept <setting>
             will set whether accepting the rules is required
             see $help role force_accept for more info

        """
        pass

    @role.command(pass_context=True)
    async def invite(self, ctx, *role):
        """sets the role invited users receive

        $role invite <role>

        Parameters:
        <role>
            required parameter
            the name of the role to be assigned
            all words given are joined to form one role title

        Usages:
        $role invite new user
            will set any invited user to the role new user

        $role invite basic
            will set any invited user to the role basic
        """
        role2 = [r for r in ctx.guild.roles if r.name == ' '.join(role)]

        if role and not role2:
            role = ' '.join(role)
            return await ctx.send(f'I do not see {role} in the guild roles, cannot assign it',
                                  delete_after=bot_message_expire)

        if role2:
            role = role2[0].name

        sql_c, database = functions.get_database()
        saved_roles = sql_c.execute('select * from member_invite_roles where guild=?', (ctx.guild.id,)).fetchone()
        if saved_roles:
            saved_roles = list(saved_roles)
        else:
            saved_roles = [ctx.guild.id, '', '', 0]

        if role:
            saved_roles[1] = role
            sql_c.execute('insert or replace into member_invite_roles '
                          '(guild, role_new, role_default, accept) values (?, ?, ?, ?)', saved_roles)
            database.commit()
            await ctx.send(f'Role auto-assigned to newly invited users is {role}')
        else:
            role = role = saved_roles[1] if saved_roles[3] == 1 else saved_roles[2]
            role2 = [r for r in ctx.guild.roles if r.name == role]
            if role:
                await ctx.send(f'Role auto-assigned to newly invited users is {role2[0].mention}')
            else:
                await ctx.send(f'Role auto-assigned to newly invited users is not configured')

    @role.command(pass_context=True)
    async def default(self, ctx, *role):
        """sets the role members receive

        $role members <role>

        Parameters:
        <role>
            required parameter
            the name of the role to be assigned
            all words given are joined to form one role title

        Usages:
        $role invite new user
            will set any invited user to the role new user

        $role invite basic
            will set any invited user to the role basic
        """
        role2 = [r for r in ctx.guild.roles if r.name == ' '.join(role)]

        if role and not role2:
            role = ' '.join(role)
            return await ctx.send(f'I do not see {role} in the guild roles, cannot assign it',
                                  delete_after=bot_message_expire)

        if role2:
            role = role2[0].name

        sql_c, database = functions.get_database()
        saved_roles = sql_c.execute('select * from member_invite_roles where guild=?', (ctx.guild.id,)).fetchone()
        if saved_roles:
            saved_roles = list(saved_roles)
        else:
            saved_roles = [ctx.guild.id, '', '', 0]

        if role:
            saved_roles[2] = role
            print(saved_roles)
            sql_c.execute('insert or replace into member_invite_roles '
                          '(guild, role_new, role_default, accept) values (?, ?, ?, ?)', saved_roles)
            database.commit()
            await ctx.send(f'Role auto-assigned to new members is {role}')
        else:
            role = role = saved_roles[1] if saved_roles[3] == 1 else saved_roles[2]
            role2 = [r for r in ctx.guild.roles if r.name == role]
            if role:
                await ctx.send(f'Role auto-assigned to new members is {role2[0].mention}')
            else:
                await ctx.send(f'Role auto-assigned to new members is not configured')

    @role.command(pass_context=True)
    async def force_accept(self, ctx, parameter=None):
        """sets whether users must $acccept the rules
        if enabled, users are given the invite role first
            when they $accept, they are given the default role

        if disabled, they are given the default role.

        $role force_accept <setting>

        Parameters:
        <setting>
            required parameter
            on is one of 'yes', 'y', 'true', 't', '1', 'enable', 'on', 'affirmative'
            off is on of 'no', 'n', 'false', 'f', '0', 'disable', 'off', 'negative'
            case insensitive

        Usages:
        $role force_accept 1
            will force new users to $accept before being given the default role

        $role force_accept n
            will default new users to the default role without $accept-ing first
        """
        sql_c, database = functions.get_database()
        saved_roles = sql_c.execute('select * from member_invite_roles where guild=?', (ctx.guild.id,)).fetchone()
        if saved_roles:
            saved_roles = list(saved_roles)
        else:
            saved_roles = [ctx.guild.id, '', '', 0]
        setting = functions.boolean(parameter)
        if setting:
            saved_roles[3] = 1
        elif setting is not None:
            saved_roles = 0
        else:
            on, off = functions.boolean(show=True)
            await ctx.send(f"{parameter} is not recognised.  "
                           f"\n\tTo enable, use one of [{', '.join(on)}]"
                           f"\n\tTo disable, use one of [{', '.join(off)}]"
                           "\n\n\tparameter is not case sensitive", delete_after=bot_message_expire)

        if parameter and setting:  # gave a setting and it is recognised boolean
            saved_roles[3] = 1 if setting else 0
            sql_c.execute('insert or replace into member_invite_roles '
                          '(guild, role_new, role_default, accept) values (?, ?, ?, ?)', saved_roles)
            database.commit()


def setup(bot):
    bot.add_cog(Users(bot))
