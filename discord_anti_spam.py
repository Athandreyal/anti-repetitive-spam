import discord
import sqlite3
import datetime
import asyncio
from discord.ext import commands
from discord.ext.commands import has_permissions
from discord_token import token as token
import re
import os
import json

# todo: publicly posted mod-bot auto response details, so users can know why it will do what it does.
#          include the full list of epithets that earn a 12hr server wide muting.
# todo: handle editing a message after the bot has trimmed the original from its database.
# todo: expand the mute arguments list

database = sqlite3.connect('messages.db')
sql_c = database.cursor()

bot = commands.Bot(command_prefix='$', description='I am Mod-Bot.')

fast = False
if fast:
    escalate = {1: 3, 2: 27, 3: 216, 4: 1512, 5: 9072, 6: 45360}  # the mute durations for repeat offences
    deescalate_period = 6  # the duration between un-mute / de-escalate checks
    un_warn = 36   # wait 1 hour *after* penalties fully expire to unwarn a user.

else:
    escalate = {1: 300, 2: 2700, 3: 21600, 4: 151200, 5: 907200, 6: 4536000}  # the mute durations for repeat offences
    deescalate_period = 60  # the duration between un-mute / de-escalate checks
    un_warn = 3600   # wait 1 hour *after* penalties fully expire to unwarn a user.


message_logs_path = 'message logs/'
today = datetime.datetime.today().day
if not os.path.exists(message_logs_path):
    os.mkdir(message_logs_path)

logging_channel = 'mute-log'
warn_only = True
mutelogs = dict()

message_logs = dict()

class action:
    class unmute:
        name = 'Unmute'
        color = 0x0000ff
    class mute:
        name = 'Mute'
        color = 0xffff00
    class kick:
        name = 'Kick'
        color = 0xff4500
    class unban:
        name = 'Unban'
        color = 0x0000ff
    class ban:
        name = 'Ban'
        color = 0x8b0000


class NamedTuple:
    def __init__(self, **kwargs):
        for k in kwargs:
            setattr(self, k, kwargs[k])


def open_logfile(guild: str, filename: str, mode='a'):
    if not isinstance(guild, str):
        guild = str(guild)
    if not os.path.exists(message_logs_path + guild + '\\' + filename):
        f = open(message_logs_path + guild + '\\' + filename, mode, encoding='utf-8')
        f.write('# logging format is one of either:\n'
                '#   date1:date2 - guild(guild.id):channel(channel.id):user(user.id):message\n'
                '#   date1:date2 - dm:user(user.id):message\n'
                '# DM\'s use the second, normal guild/channel messages use the first\n'
                '# date1 is 2 digits each for year, month, day, hours(24hr), minutes, seconds: yymmddhhMMss\n'
                '# date2 is seconds since epoch ( time.time() ) and is the reference saved with the message in the '
                'database.\n'
                '# messages are saved to the database under the key (channel, uid), and are saved under m# as '
                'time2:message.content, where # is 1-5, representing one of the 5 active history messages\n\n')
        f.flush()
        return f
    else:
        return open(message_logs_path + guild + '\\' + filename, mode, encoding='utf-8')


@bot.event
async def on_command_error(ctx, error):
    # any command failure lands here.  use error.original to catch an inner exception.
    if isinstance(error, commands.errors.MissingPermissions):
        await ctx.send(ctx.author.mention + ', ' + str(error))
    elif hasattr(error, 'original') and isinstance(error.original, discord.Forbidden):
        # bot lacks permissions to do thing.
        await ctx.send(f'I\'m sorry {ctx.author.mention}, I\'m afraid I can\'t do that')
    else:
        raise error


@bot.event
async def on_ready():
    for guild in bot.guilds:
        if not os.path.exists(message_logs_path + str(guild.id)):
            os.mkdir(message_logs_path + str(guild.id))
        message_logs[guild.id] = open_logfile(guild.id, datetime.datetime.utcnow().strftime('%y%m%d') + '.txt')


    sql_c.execute('create table if not exists messages (' +
                  'guild text, ' +
                  'channel text, ' +
                  'id text, ' +
                  'escalate integer, ' +
                  'muted integer, ' +
                  'expire integer, ' +
                  'messages integer, ' +
                  'm1 text, ' +
                  'm2 text, ' +
                  'm3 text, ' +
                  'm4 text, ' +
                  'm5 text,  ' +
                  'primary key (guild, channel, id));')
    sql_c.execute('create table if not exists ignoring (' +
                  'guild integer, ' +
                  'channel integer, ' +
                  'primary key (guild, channel));')
    sql_c.execute('pragma synchronous = 1')
    sql_c.execute('pragma journal_mode = wal')
    database.commit()
    bot.loop.create_task(process_task())
    logs = [x for x in bot.get_all_channels() if x.name == logging_channel]
    for c in logs:
        mutelogs[c.guild] = c

    await bot.change_presence(status=discord.Status.idle, activity=discord.Activity(type=4))
    print('ready')


def update_messages(saved, message, old_message=None):
    if old_message:
        if saved:
            for m in ['m1', 'm2', 'm3', 'm4', 'm5']:
                if old_message.content == getattr(saved, m).split(':', 1)[1]:
                    setattr(saved, m, str(int(datetime.datetime.utcnow().timestamp())) + ':' + message.content)
                    break
    else:
        if saved:
            saved.messages += 1
            saved.m5 = saved.m4
            saved.m4 = saved.m3
            saved.m3 = saved.m2
            saved.m2 = saved.m1
            saved.m1 = str(int(datetime.datetime.utcnow().timestamp())) + ':' + message.content
        else:
            saved = NamedTuple(guild=message.guild.id, channel=message.channel.id, uid=message.author.mention,
                               escalate=0, muted=0, expire=0, messages=1,
                               m1=str(int(datetime.datetime.utcnow().timestamp())) + ':' + message.content,
                               m2='', m3='', m4='', m5='')
    return saved


async def process_messages(message, old_message=None):
    channel = message.channel.id
    author = message.author.mention
    saved = read_messages_per_channel(channel, author)

    saved = update_messages(saved, message, old_message)
    rep = message_repetition(message.content)
    penalty = rep > 1
    recent = False

    if not penalty:
        recent_messages = []
        for m in ['m1', 'm2', 'm3', 'm4', 'm5']:
            msg = getattr(saved, m).split(':', 1)
            if len(msg) > 1:
                recent_messages.append(re.sub('(\^*){1,5}', '', msg[1]))
        rep = message_repetition(' '.join(recent_messages))
        penalty = rep > 1
        recent = penalty
    if penalty:  # muting
        warned = sql_c.execute('select sum(expire) from messages where guild=? and id=?',
                               (message.guild.id, message.author.mention,)).fetchall()
        print('warned1', warned)
        if warned:
            warned = warned[0][0]
        else:
            warned = False
        print('warned2', warned)
        give_warning = warn_only or not warned
        print('give_warning', give_warning)
        if give_warning:
            await warning(channel=message.channel, who=message.author, issuer='I am',
                          where=message.guild, why='repetition threshold exceeded.')
        else:  # warn, or escalate to muting.
            if not warn_only:
                saved.escalate = min(6, saved.escalate + 1)
                saved.muted = 1  # muted
                saved.expire = int(datetime.datetime.utcnow().timestamp()) + escalate[saved.escalate]
                await mute_user(channel=message.channel, guild=message.guild, member=message.author)
            else:
                saved.escalate = 1
                saved.expire = int(datetime.datetime.utcnow().timestamp()) + escalate[saved.escalate]
    write_database(saved)
    return not penalty


@bot.command(pass_context=True)
@has_permissions(ban_members=True, kick_members=True)
async def warn(ctx, target: discord.Member, *statement):
    if not statement:
        reason = 'No Reason'
    else:
        reason = ' '.join(statement)
    await warning(channel=ctx.channel, issuer=ctx.message.author.mention + ' is', who=target, where=ctx.guild,
                  why=reason)


async def warning(channel: discord.TextChannel, issuer, who: discord.Member, where: discord.Guild, why):
    # warnings = sql_c.execute('select channel from messages where id=? and expire=0',
    #                          (who.mention, )).fetchall()
    # if not warnings:
    #     warnings = []
    # else:
    #     warnings = [x[0] for x in warnings]
    # channels = [x for x in where.channels if x.id in warnings]
    #
    # await channel.send(f'{who}, {issuer} giving you a warning.\nReason: {why}')
    # expire = int(datetime.datetime.utcnow().timestamp())
    # gid = where.id
    # print(expire, gid, who)
    # sql_c.execute(f'update messages set expire={expire} where guild="{gid}" and id="{who.mention}" and expire=0;')
    # database.commit()
    for warn_channel in where.channels:
        if isinstance(warn_channel, discord.TextChannel):
            data = read_messages_per_channel(warn_channel.id, who.mention)
            if data:
                data.expire = int(datetime.datetime.utcnow().timestamp())
            else:
                data = NamedTuple(guild=where.id, channel=warn_channel.id, uid=who.mention,
                                  escalate=0, muted=0, expire=int(datetime.datetime.utcnow().timestamp()),
                                  messages=0, m1='', m2='', m3='', m4='', m5='')
            # noinspection PyTypeChecker
            write_database(data)
    await channel.send(f'{who.mention}, {issuer} giving you a warning.\nReason: {why}')


def read_messages_per_channel(channel, uid):
    if not isinstance(channel, int):
        channel = channel.id
    if not isinstance(uid, str):
        uid = uid.mention
    d = sql_c.execute('select * from messages where channel=? and id=?;', (str(channel), uid,)).fetchall()
    if not d:
        return None
    return full_row_to_named(d[0])


def read_messages(uid):
    if not isinstance(uid, str):
        uid = uid.mention
    d = sql_c.execute('select * from messages where id=?;', (uid,)).fetchall()
    if not d:
        return None
    return [full_row_to_named(x) for x in d]


def write_database(row):
    sql_c.execute('insert or replace into messages (guild, channel, id, escalate, muted, expire, messages, m1, m2, m3, '
                  'm4, m5) values ("%s", "%s", "%s", %d, %d, %d, %d, "%s", "%s", "%s", "%s", "%s")' %
                  (row.guild, row.channel, row.uid, row.escalate, row.muted, row.expire, row.messages, row.m1, row.m2,
                   row.m3, row.m4, row.m5))
    database.commit()


def full_row_to_named(d):
    return NamedTuple(guild=d[0],
                      channel=d[1],
                      uid=d[2],
                      escalate=d[3],
                      muted=d[4],
                      expire=d[5],
                      messages=d[6],
                      m1=d[7],
                      m2=d[8],
                      m3=d[9],
                      m4=d[10],
                      m5=d[11]
                      )


async def process_expired():
    now = int(datetime.datetime.utcnow().timestamp())
#    query = f"select * from messages where escalate > 0 and expire <= {now} or m1 != ''"
    query = f"select * from messages where expire > 0 or m1 != ''"
    expired = sql_c.execute(query).fetchall()
    if expired:
        for user in expired:
            user = full_row_to_named(user)
            # noinspection PyUnresolvedReferences
            channel = bot.get_channel(int(user.channel))
            try:
                # noinspection PyUnresolvedReferences
                author = bot.get_user(int(user.uid[2:-1]))
            except ValueError:
                # noinspection PyUnresolvedReferences
                author = bot.get_user(int(user.uid[3:-1]))  # some users have an ! in their username
            relax = now - user.expire
            if relax > 0:
                # noinspection PyUnresolvedReferences
                if user.muted:
                    # noinspection PyUnresolvedReferences,PyTypeChecker
                    await un_mute_user(channel, author, data=user)
                else:
                    # noinspection PyUnresolvedReferences,PyUnboundLocalVariable
                    if user.expire == 0:  # the bot no longer cares, start pruning their history
                        for m in ['m5', 'm4', 'm3', 'm2', 'm1']:
                            msg = getattr(user, m)
                            if msg:
                                age = int(msg.split(':', 1)[0])
                                if now - age >= 60:
                                    setattr(user, m, '')
                                    break
                    # noinspection PyUnresolvedReferences
                    elif user.escalate == 0 and relax > un_warn:
                        user.expire = 0
                    elif user.escalate > 0 and relax > escalate[user.escalate]:  # they've been good for a while
                        user.expire = now  # reset expiry to now to lapse the next escalation
                        # noinspection PyUnresolvedReferences
                        user.escalate -= 1   # deescalate
                    # noinspection PyTypeChecker
                    write_database(user)


async def process_task():
    global message_log
    global today
    while True:
        await asyncio.sleep(deescalate_period)
        await process_expired()
        if datetime.datetime.today().day != today:
            today = datetime.datetime.today().day
            # new log file time
            for guild in message_logs:
                message_logs[guild].close()
                message_logs[guild] = open_logfile(guild, datetime.datetime.utcnow().strftime('%y%m%d') + '.txt')


def log_message(message, dm, old=None):
    t = datetime.datetime.utcnow().strftime(f'%y%m%d%H%M%S:{int(datetime.datetime.utcnow().timestamp())} - ')
    s2 = '' if old is None else '====EDIT====\n\t====OLD====\n\t\t'
    if dm:
        if old:
            s2 += f'dm:{old.author}({old.author.id}):{old.content}\n\t====NEW====\n\t\t'
        s = f'dm:{message.author}({message.author.id}):{message.content}'
    else:
        if old:
            s2 += f'{old.guild.name}({old.guild.id}):{old.channel.name}({old.channel.id}):' + \
                  f'{old.author}({old.author.id}):{old.content}\n\t====NEW====\n\t\t'
        s = f'{message.guild.name}({message.guild.id}):{message.channel.name}({message.channel.id}):' + \
            f'{message.author}({message.author.id}):{message.content}'
        message_logs[message.guild.id].write(t + s2 + s + '\n')
        message_logs[message.guild.id].flush()
    print(t + s)


@bot.event
async def on_message(message):
    if message.author.bot:
        return
    penalty = await eval_message(message)
    if not penalty:
        await bot.process_commands(message)


@bot.event
async def on_message_edit(old_message, message):
    if message.author.bot:
        return
    await eval_message(message, original=old_message)


async def eval_message(message, original=None):
    t = tard(message.content)
    if t:
        await message.channel.send(t)
    dm = not hasattr(message.author, 'guild')
    log_message(message, dm, old=original)
    if dm:
        ignored = []
        admin = False
        command = False
        owner = False
    else:
        admin = any((role.permissions.administrator for role in message.author.roles))
        ignored = sql_c.execute('select * from ignoring where guild=?', (message.guild.id,)).fetchall()
        if ignored:
            ignored = [int(x[1]) for x in ignored]
        else:
            ignored = []
        command = (await bot.get_context(message)).valid
        owner = message.guild.owner.id == message.author.id
    penalty = False

    content = re.sub('(\^*){1,5}', '', message.content.upper())

    if not dm and message.channel.id not in ignored and not admin and not command and not owner:
        penalty = await process_messages(message, old_message=original)
    return penalty


def tard(message):
    match = re.findall('.*(reee+).*', message, re.IGNORECASE)
    if not match:
        return None
    match = match[0]
    s = 'T' if match[0] == 'R' else 't'
    for c in match[1:-2]:
        s += 'A' if c == c.upper() else 'a'
    s += 'R' if match[-2] == match[-2].upper() else 'r'
    s += 'D' if match[-1] == match[-1].upper() else 'd'
    return s


@bot.command(pass_context=True)
@has_permissions(ban_members=True, kick_members=True)
async def getlogs(ctx, days: int = None):
    """reponds via dm, with the requested log file's attached.
    log files are requested via day offsets,
    ie $getlogs 5 to get the last 5 days logs, or, today and the previous 4.
    """
    if not days:
        days = 1
    now = datetime.datetime.utcnow()
    while days > 0:
        delta = datetime.timedelta(days=days)
        then = now - delta
        path = message_logs_path + str(ctx.guild.id) + '\\' + then.strftime('%y%m%d') + '.txt'
        if not os.path.exists(path):
            await ctx.author.send('I have no logs for ' + path)
        else:
            await ctx.author.send('your file', file=discord.File(path))
        days -= 1


@bot.command(pass_context=True)
@has_permissions(manage_roles=True)
async def mute(ctx, member: discord.Member, *reason):
    """mutes the mentioned user on the channel the mute is called from
    will increment their current escalation and set the duration accordingly
    args is used to collect a 'reason' for the muting"""
    await mute_user(channel=ctx.channel, guild=ctx.guild, member=member, *reason, ctx=ctx)


@bot.command(pass_context=True, hidden=True)
async def get_perms(message, member: discord.Member):
    overwrite = message.channel.overwrites_for(member)
    for k in dir(overwrite):
        if '_' != k[0]:
            print('\t', k, getattr(overwrite, k))


@bot.command(pass_context=True)
@has_permissions(manage_roles=True)
async def unmute(ctx, member: discord.Member, *reason):
    """unmutes the mentioned user on the channel the mute is called from
    will reset the message history and start expiring
    args is used to collect a 'reason' for the unmuting"""
    await un_mute_user(ctx.channel, member, *reason, ctx=ctx)


async def mute_user(channel:discord.TextChannel, guild:discord.Guild, member: discord.member, *reason, data=None,
                    ctx=None):
    overwrite = channel.overwrites_for(member) or discord.PermissionOverwrite()
    # noinspection PyDunderSlots,PyUnresolvedReferences
    overwrite.send_messages = False
    # noinspection PyDunderSlots,PyUnresolvedReferences
    overwrite.send_tts_messages = False
    # noinspection PyDunderSlots,PyUnresolvedReferences
    overwrite.speak = False
    await channel.set_permissions(member, overwrite=overwrite)

    if not data:
        channel = channel.id
        author = member.mention
        saved = read_messages_per_channel(channel, author)
        if saved:
            saved.escalate = min(6, saved.escalate + 1)
            saved.muted = 1
        else:
            saved = [guild.id, channel, author, 1, 1, 0, 0, '', '', '', '', '']
            saved = NamedTuple(guild=guild.id, channel=channel.id, uid=author.mention,
                               escalate=1, muted=1, expire=0, messages=0,
                               m1='', m2='', m3='', m4='', m5='')
        saved.expire = int(datetime.datetime.utcnow().timestamp()) + escalate[saved.escalate]
        data = saved
    write_database(data)
    # if not ctx:
    #     ctx = channel
    if not ctx:
        ctx = type('dummy ctx', (), {'channel': channel, 'guild': guild})
    await log_action(ctx, action.mute, member.mention, reason)


async def un_mute_user(channel: discord.TextChannel, member: discord.Member, *reason, data=None, ctx=None):
    # noinspection PyTypeChecker
    await channel.set_permissions(member, overwrite=None)
    if not data:
        data = read_messages_per_channel(channel.id, member.mention)

    data.escalate = max(0, data.escalate - 1)
    data.muted = 0
    data.expire = int(datetime.datetime.utcnow().timestamp())
    data.m1 = ''  # clear recent message history, so it doesn't re-mute them as soon as they speak do to recent history
    data.m2 = ''
    data.m3 = ''
    data.m4 = ''
    data.m5 = ''
    write_database(data)
    if not ctx:
        ctx = type('dummy ctx', (), {'channel': channel, 'guild': channel.guild})
    await log_action(ctx, action.unmute, member.mention, reason)


async def log_action(ctx, act, who, why):
    mutelog = mutelogs.get(ctx.guild, None)

    if mutelog:
        if hasattr(ctx, 'message'):
            if not why:
                why = ('No', 'Reason')
            issuer = ctx.message.author.mention
            why = ' '.join(why)
        else:
            issuer = bot.user.name
            why = 'Spam threshold exceeded' if act.name == 'Mute' else 'Time served'

        embed = discord.Embed()
        embed.add_field(name='Issuer: ', value=issuer)
        embed.add_field(name='Action: ', value=act.name)
        embed.add_field(name='Who:    ', value=who)
        embed.add_field(name='Why:    ', value=why)
        embed.colour = act.color
        await mutelog.send(embed=embed)


@bot.command(pass_context=True)
@has_permissions(manage_messages=True)
async def showmessages(ctx, member: discord.Member = None):
    """prints the given user's recent messages, oldest first, split across several messages if necessary"""
    if not member:
        return await ctx.send('A member name is required to see their recent messages')
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
                embed.add_field(name=str(i-len(recent)), inline=False, value=message)
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

    await ctx.send(embed=embed1)
    if embed2:
        await ctx.send(embed=embed2)
    if embed3:
        await ctx.send(embed=embed3)


@bot.command(pass_context=True)
@has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *reason, delete=0):
    """bans a user via mention from the current guild
    delete_messages is how many days of previous messages to remove
    eg, ban @Traven shoes obsession delete=7
         bans Traven with the reason 'shoes obsession', and removes the last 7 days of his messages
    """
#    reason = ' '.join(reason)
#    try:
    await ctx.guild.ban(member, reason=' '.join(reason), delete_message_days=delete)
    await log_action(ctx, action.ban, member.mention, reason)
#    except discord.Forbidden:
#        await ctx.send(f'I\'m sorry {ctx.author.mention}, I\'m afraid I can\'t do that')



@bot.command(pass_context=True)
@has_permissions(ban_members=True)
async def banid(ctx, uid: int, *reason, delete=0):
    """bans a user via uid# from the current guild
    delete_messages is how many days of previous messages to remove
    eg, ban 598399316654292993 racism delete=7
         bans the user with that id with the reason 'racism', and removes the last 7 days of his messages
    """

    # ban them via discord.Object(id=uid)
    # then lookup their user object via ctx.guild.bans() since I can get it that way.
    user = discord.Object(id=uid)
    await ctx.guild.ban(user, reason=' '.join(reason), delete_message_days=delete)
    bans = await ctx.guild.bans()
    for b in bans:
        if b.user.id == uid:
            user = b.user
    if hasattr(user, 'mention'):
        await log_action(ctx, action.ban, f'{user.mention}', reason)
    elif hasattr(user, 'name') and hasattr(user, 'discriminator'):
        await log_action(ctx, action.ban, f'{user.name}#{user.discriminator}', reason)
    else:
        await log_action(ctx, action.ban, f'@<{uid}>', reason)


@bot.command(pass_context=True, hidden=True)
async def user(ctx, uid: int):
    await get_user(ctx, uid)


async def get_user(ctx, uid: int):
    if isinstance(uid, str) and '@' in uid:
        try:
            uid = int(uid[2:-1])
        except ValueError:
            try:
                uid = int(uid[3:-1])
            except ValueError:
                return await ctx.send(f'I can\'t find {uid} as a member of this server to reference via mention, '
                                      f'use their id instead')
    else:
        uid = int(uid)
    user = bot.get_user(uid)
    return user


@bot.command(pass_context=True)
@has_permissions(ban_members=True)
async def unban(ctx, uid, *reason):
    # async def unban(ctx, member, *reason):

    """un-bans a user from the current guild
    eg, unban uid because I want to?
         unbans the user for which  user.id == uid with the reason 'because I want to?'
    """
    if '@' in uid:
         try:
             uid = int(uid[2:-1])
         except ValueError:
             try:
                 uid = int(uid[3:-1])
             except ValueError:
                 return await ctx.send(f'I can\'t find {uid} as a member of this server to reference via mention, '
                                f'use their id instead')
    else:
        uid = int(uid)
    bans = await ctx.guild.bans()
    if bans:
        for u in bans:
            if u.user.id == uid:
                target = u.user
                await ctx.guild.unban(target, reason=' '.join(reason))
                await log_action(ctx, action.unban, target.mention, reason)
                break


@bot.command(pass_context=True)
@has_permissions(ban_members=True)
async def banned(ctx):
    """shows the banned users and the reason given"""
    bans = await ctx.guild.bans()
    if not bans:
        return await ctx.send('There are no banned users at this time')
    embed = None
    for i, userban in enumerate(bans):
        if i % 25 == 0:
            if embed:
                await ctx.send(embed=embed)
            embed = discord.Embed(title='Banned users')
        embed.add_field(name=str(userban.user)+'\n' + str(userban.user.id), value=userban.reason, inline=False)
    await ctx.send(embed=embed)


@bot.command(pass_context=True)
@has_permissions(ban_members=True)
async def banneduser(ctx, member: discord.Member):
    """gets a banned user and shows the reason why"""
    userban = await ctx.guild.fetch_ban(member)
    await ctx.send(f'{userban.user} was banned for {userban.reason}')


@bot.command(pass_context=True)
@has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *reason):
    """kicks a user from the channel"""
    await log_action(ctx, action.kick, member.mention, reason)
    reason = ' '.join(reason)
    await ctx.guild.kick(member, reason=reason)


def message_repetition(message):
    message = drop_domains(message)  # drop the domains from any urls in the msssage
    message = drop_code_blocks(message)  # drop any code blocks in the message
    mid_point = max(1, int(len(message) / 2 + 0.5))
    per = 1 / mid_point
    repeats = [0]*len(message)
    for i in range(mid_point):
        for j in range(1, len(message)):
            sub_str = message[i:j+i]
            if ' ' not in sub_str or j > 2:
                matches = message.count(sub_str, i) - 1
                repeats[j] += matches * j * per
    return sum(repeats) / mid_point


# noinspection RegExpRedundantEscape
def drop_domains(message):
    pattern = re.compile(
        r'(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:\'".,<>?\xab\xbb\u201c\u201d\u2018\u2019]))')
    matches = re.findall(pattern, message)
    matches2 = ['/'.join((x[0].split('/'))[:3]) for x in matches]
    for match in matches2:
        message = re.sub(match, '', message)
    return message


# noinspection RegExpRedundantEscape
def drop_urls(message):
    pattern = re.compile(
        r'(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:\'".,<>?\xab\xbb\u201c\u201d\u2018\u2019]))')
    matches = re.findall(pattern, message)
#    matches2 = ['/'.join((x[0].split('/'))[:3]) for x in matches]
    for match in matches:
        message = re.sub(match, '', message)
    return message


def drop_code_blocks(message):
    pattern = re.compile(r'```.*```')
    matches = re.findall(pattern, message)
    for match in matches:
        message = re.sub(match, '', message)
    return message


@bot.command(pass_context=True)
@has_permissions(manage_channels=True)
async def ignore(ctx, channel=None):
    """marks a channel as ignored by Anti-Spam
    ignored channels are not monitored at all."""
    if channel is None:
        ctx.send('channel is a required argument')
    channel = [x.id for x in bot.get_all_channels() if x.name == channel and x.guild.id == ctx.guild.id]
    if channel:
        channel = channel[0]

    sql_c.execute('insert or replace into ignoring (guild, channel) values (?, ?)', (ctx.guild.id, str(channel),))
    database.commit()


@bot.command(pass_context=True)
@has_permissions(manage_channels=True)
async def ignoreall(ctx, channel=None):
    """marks all channels as ignored by Anti-Spam
    ignored channels are not monitored at all."""
    channels = [x.id for x in bot.get_all_channels() if x.guild.id == ctx.guild.id]
    for channel in channels:
        sql_c.execute('insert or replace into ignoring (guild, channel) values (?, ?)', (ctx.guild.id, str(channel),))
        database.commit()


@bot.command(pass_context=True)
@has_permissions(manage_channels=True)
async def watchall(ctx, channel=None):
    """marks all channels as ignored by Anti-Spam
    ignored channels are not monitored at all."""
    channels = [x.id for x in bot.get_all_channels() if x.guild.id == ctx.guild.id]
    for channel in channels:
        sql_c.execute('delete from ignoring where guild=? and channel=?', (ctx.guild.id, channel,))
        database.commit()


@bot.command(pass_context=True)
@has_permissions(manage_channels=True)
async def watch(ctx, channel=None):
    """marks an ignored channel as being watched"""
    if channel is None:
        ctx.send('channel is a required argument')
    channel = [x.id for x in bot.get_all_channels() if x.name == channel and x.guild.id == ctx.guild.id]
    if channel:
        channel = channel[0]
    sql_c.execute('delete from ignoring where guild=? and channel=?', (ctx.guild.id, channel,))
    database.commit()


@bot.command(pass_context=True)
async def expire(ctx, member: discord.Member):
    """gets the current mute state of the user across all channels on the server"""
    author = member.mention
    entries = read_messages(author)
    escalates = [x for x in entries if x.escalate > 0]
    warnings = [x for x in entries if x.expire > 0 and x.escalate == 0]
    embed = discord.Embed(title=member.name + '\'s escalation state per channel')
    now = int(datetime.datetime.utcnow().timestamp())
    def expire_str(expire):
        e = 'Expires: '
        days = expire // 86400
        hours = (expire % 86400) // 3600
        minutes = (expire % 3600) // 60
        seconds = expire % 60
        d = '%d d, ' % days
        h = '%0dh, ' % hours
        m = '%0dm, ' % minutes
        s = '%0ds' % seconds
        if days:
            return d+h+m+s
        elif hours:
            return h+m+s
        elif minutes:
            return m+s
        else:
            return s

    if escalates:
        embed = discord.Embed(title=member.name + '\'s escalation state per channel')
        for mute in escalates:
            channel = bot.get_channel(int(mute.channel))
            s = 'Level %d\n' % mute.escalate
            if mute.muted:
                s += 'Muted: True\n' + expire_str(mute.expire - now)
            else:
                s += 'Muted: False\n'
                if mute.escalate > 0:
                    s += expire_str(escalate[mute.escalate] - (now - mute.expire))
            embed.add_field(name=channel.name, value=s)
        await ctx.send(embed=embed)
    if warnings:
        embed = discord.Embed(title=member.name + '\'s warning state per channel')
        for warning in warnings:
            embed.add_field(name=bot.get_channel(int(warning.channel)),
                            value=expire_str(un_warn + warning.expire - now))
        await ctx.send(embed=embed)
    if not escalates and not warnings:
        await ctx.send(f'{member} has no escalations pending expiration')


@bot.command(pass_context=True)
@has_permissions(manage_channels=True)
async def ignored(ctx):
    """outputs a list of the channels currently being ignored by Anti-Spam"""
    ignore = sql_c.execute('select * from ignoring where guild=?', (ctx.guild.id,)).fetchall()
    ignore = [(bot.get_channel(int(x[1]))).name for x in ignore]
    if ignore:
        ignore = ', '.join(ignore)
    else:
        ignore = 'None'
    await ctx.send('The following channels are not monitored for anti_spam: ' + ignore)


@bot.command(pass_context=True)
@has_permissions(manage_channels=True)
async def terminate(ctx):
    """terminates the bot's process with sys.exit(1)"""
    import sys
    sys.exit(1)


@bot.command(pass_context=True)
@has_permissions(manage_channels=True)
async def getwarn(ctx):
    """shows the current warnings_only setting"""
    if warn_only:
        await ctx.send('Warnings_only is ON\nAction will not be taken for infractions, only warnings are given.')
    else:
        await ctx.send('Warnings_only is OFF\nAction will be taken for infractions.')

@bot.command(pass_context=True)
@has_permissions(manage_channels=True)
async def setwarn(ctx, parameter=None):
    """toggles or shows the current warnings only setting
    parameter is expected to be the strings 'on' or 'off', case insensitive"""
    global warn_only
    if not parameter:
        warn_only = not warn_only
        if warn_only:
            await ctx.send('Action will not be taken for infractions, only warnings given.')
        else:
            await ctx.send('Action will now be taken for infractions.')
    else:
        if parameter.upper() == 'ON':
            warn_only = True
            await ctx.send('WARN_ONLY is now enabled.')
        elif parameter.upper() == 'OFF':
            warn_only = False
            await ctx.send('WARN_ONLY is now disabled.  Penalties may be applied for infractions.')
        else:
            await ctx.send(f'Parameter is expected to be either "on" or "off", {parameter} is not recognised')

@bot.command()
async def accept(ctx):
    # get members role
    member_role = [x for x in ctx.guild.roles if x.name.upper() == 'MEMBER'][0]
    await ctx.author.add_roles(member_role, reason='Accepted Rules')


bot.run(token())

