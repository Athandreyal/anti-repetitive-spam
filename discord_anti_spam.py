import discord
import sqlite3
import datetime
import asyncio
from discord.ext import commands
from discord.ext.commands import has_permissions
from discord_token import token as token
import re
import os

# todo: publicly posted mod-bot auto response details, so users can know why it will do what it does.
#          include the full list of epithets that earn a 12hr server wide muting.
# todo: handle editing a message after the bot has trimmed the original from its database.
# todo: save warnings_only in the database, per server.

bot_name = 'Mod-Bot'

database = sqlite3.connect('messages.db')
sql_c = database.cursor()

bot = commands.Bot(command_prefix='$', description=f'I am {bot_name}.')

fast = False
if fast:
    escalate = {1: 3, 2: 27, 3: 216, 4: 1512, 5: 9072, 6: 45360}  # the mute durations for repeat offences
    deescalate_period = 6  # the duration between un-mute / de-escalate checks
    un_warn = 36  # wait 1 hour *after* penalties fully expire to un-warn a user.

else:
    escalate = {1: 300, 2: 2700, 3: 21600, 4: 151200, 5: 907200, 6: 4536000}  # the mute durations for repeat offences
    deescalate_period = 60  # the duration between un-mute / de-escalate checks
    un_warn = 3600  # wait 1 hour *after* penalties fully expire to un-warn a user.

message_logs_path = 'message logs/'
today = datetime.datetime.today().day
if not os.path.exists(message_logs_path):
    os.mkdir(message_logs_path)

logging_channel = 'mute-log'
warn_only = True
mutelogs = dict()

message_logs = dict()

warn_only_state = dict()


class Action:
    class Warn:
        name = 'Warn'
        color = 0x0000ff

    class Unmute:
        name = 'Unmute'
        color = 0x0000ff

    class Mute:
        name = 'Mute'
        color = 0xffff00

    class Kick:
        name = 'Kick'
        color = 0xff4500

    class Unban:
        name = 'Unban'
        color = 0x0000ff

    class Ban:
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
    sql_c.execute('create table if not exists warning_only('
                  'guild integer primary key,'
                  'warnings integer)')
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
        if warned:
            warned = warned[0][0]
        else:
            warned = False
        give_warning = warn_only or not warned
        if give_warning:
            if recent:
                why = 'recent message repetition threshold exceeded'
            else:
                why = 'last message repetition threshold exceeded'
            await warning(channel=message.channel, who=message.author, issuer='I am',
                          where=message.guild, why=why)
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
async def warn(ctx, *args):
    """warns the mentioned user(s) across all channels on the server
    $warn <@user> [@user...]
        <@user>
            required parameter, at least one @user must be mentioned
        [@user...]
            optional parameter(s), 0 or more additional users may be mentioned
            There is no maximum number of mentioned users

    eg:
        $warn @user
            gives user a server wide warning

        $warn @user1 @user2
            gives both user1 and user2 a server wide warning
    """
    users = ctx.message.mentions
    if not users:
        return await ctx.send('its rather necessary to say who is going to get warned.....')
    reason = [x for x in args if not re.match('.*(<[@|#]!?[0-9]{18}>).*', x)]

    if not reason:
        reason = ['No', 'Reason']
    for u in users:
        await warning(ctx=ctx, channel=ctx.channel, issuer=ctx.message.author.mention + ' is', who=u,
                      where=ctx.guild, why=reason)


async def warning(channel: discord.TextChannel, issuer, who: discord.Member, where: discord.Guild, why, ctx=None):
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
    await channel.send(f"{who.mention}, {issuer} giving you a warning.\nReason: {' '.join(why)}")
    if not ctx:
        ctx = channel
    await log_action(ctx=ctx, act=Action.Warn, who=who, why=why)


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
    query = f"select * from messages where expire > 0 or m1 != ''"
    expired = sql_c.execute(query).fetchall()
    if expired:
        for u in expired:
            u = full_row_to_named(u)
            # noinspection PyUnresolvedReferences
            channel = bot.get_channel(int(u.channel))
            try:
                # noinspection PyUnresolvedReferences
                author = bot.get_user(int(u.uid[2:-1]))
            except ValueError:
                # noinspection PyUnresolvedReferences
                author = bot.get_user(int(u.uid[3:-1]))  # some users have an ! in their username
            relax = now - u.expire
            if relax > 0:
                # noinspection PyUnresolvedReferences
                if u.muted:
                    # noinspection PyUnresolvedReferences,PyTypeChecker
                    await un_mute_user(channel, author, data=u)
                else:
                    # noinspection PyUnresolvedReferences,PyUnboundLocalVariable
                    if u.expire == 0:  # the bot no longer cares, start pruning their history
                        for m in ['m5', 'm4', 'm3', 'm2', 'm1']:
                            msg = getattr(u, m)
                            if msg:
                                age = int(msg.split(':', 1)[0])
                                if now - age >= 60:
                                    setattr(u, m, '')
                                    break
                    # noinspection PyUnresolvedReferences
                    elif u.escalate == 0 and relax > un_warn:
                        u.expire = 0
                    elif u.escalate > 0 and relax > escalate[u.escalate]:  # they've been good for a while
                        u.expire = now  # reset expiry to now to lapse the next escalation
                        # noinspection PyUnresolvedReferences
                        u.escalate -= 1  # deescalate
                    # noinspection PyTypeChecker
                    write_database(u)


async def process_task():
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
        ignoring = []
        admin = False
        command = False
        owner = False
    else:
        admin = any((role.permissions.administrator for role in message.author.roles))
        ignoring = sql_c.execute('select * from ignoring where guild=?', (message.guild.id,)).fetchall()
        if ignoring:
            ignoring = [int(x[1]) for x in ignoring]
        else:
            ignoring = []
        command = (await bot.get_context(message)).valid
        owner = message.guild.owner.id == message.author.id
    penalty = False

    if not dm and message.channel.id not in ignoring and not admin and not command and not owner:
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
    """responds via dm, with the requested log file's attached.
    log files are requested via day offsets,
    $getlogs [days int]
        [days int]
            optional parameter, specifies how many days worth of logs
            integer only, defaults to 1, no maximum currently

    eg:
        $getlogs
            will dm you the current message log txt file
        $getlogs 5
            will dm you the last 5 message log txt files
                ie, today's and the previous 4.
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
async def mute(ctx, *args):
    """mutes the mentioned user(s) on the mentioned channel(s)
    $mute <@user> [@user...] [#channel...] [reason text] [days=int] [hours=int] [minutes=int] [seconds=int]
        <@user>
            required parameter, at least one @user mention is necessary
         [@user...]
             optional parameter, zero or more additional users may be mentioned
             there is no maximum number of user mentions
         [#channel...]
             optional parameter, zero or more channels may be mentioned
             there is no maximum number of channel mentions
         [reason text]
             optional parameter, will default to 'No Reason' if not provided
             the reason is taken left to right, from everything not recognised as:
                 a mention, users or channels
                 one of days=, hours=, minutes=, seconds
         [days=int
             optional parameter, adds the specified number of days, in seconds, to the mute duration
             integers only, defaults to zero, no maximum
         [hours=int]
             optional parameter, adds the specified number of hours, in seconds, to the mute duration
             integers only, defaults to zero, no maximum
         [minutes=int]
             optional parameter, adds the specified number of minutes, in seconds, to the mute duration
             integers only, defaults to zero, no maximum
         [seconds=int]
             optional parameter, adds the specified number of seconds to the mute duration
             integers only, defaults to zero, no maximum

    call with one of:
        $mute @user
            reason will default to No reason
            channel will default to current channel
            time will default to escalation settings
            mutes the mentioned user for default time, on current channel, with no reason

        $mute @user #channel
            reason will default to No reason
            time will default to escalation settings
            mutes the mentioned user for default time, on the mentioned channel, with no reason

        $mute @user #channel I want to
            time will default to escalation settings
            mutes the mentioned user for default time, on the mentioned channel, with the reason "I want to"

        $mute @user #channel I want to hours=3
            mutes the mentioned user for 3 hours, on the mentioned channel, with the reason "I want to"

        order of user mentions, channel mentions, reason and seconds/minutes/hours/days are not important
        multiple users may be mentioned in one call
        multiple channels may be mentioned in one call
        any, all, or none of days, hours, minutes and seconds may be used.

        anything not recognised as a mention, or seconds/minutes/hours/days assignment will become part of the reason

        for example, this works:
        $mute days=1 while @user1 hours=2 crazy #channel2 this @user2 minutes=3 does #channel1 work seconds=4

        this will:
            mute @user1 and @user2,
                on both #channel1 and #channel2,
                for 1 day, 2 hours, 3 minutes, 4 seconds
                with the reason: "while crazy this does work"
    """
    users = ctx.message.mentions
    if not users:
        return await ctx.send('its rather necessary to say who is going to get muted.....')
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
                return await ctx.send(f'{k} must be an integer, not {v}')
    for k in kwargs:
        args.remove(f'{k}={kwargs[k]}')

    channels = ctx.message.channel_mentions
    if not channels:
        channels = [ctx.channel]
    reason = [x for x in args if not re.match('.*(<[@|#]!?[0-9]{18}>).*', x)]
    for member in users:
        for mute_channel in channels:
            await mute_user(*reason, channel=mute_channel, guild=ctx.guild, member=member, ctx=ctx, time=time)


@bot.command(pass_context=True, hidden=True)
async def get_perms(message, member: discord.Member):
    overwrite = message.channel.overwrites_for(member)
    for k in dir(overwrite):
        if '_' != k[0]:
            print('\t', k, getattr(overwrite, k))


@bot.command(pass_context=True)
@has_permissions(manage_roles=True)
async def unmute(ctx, *args):
    """unmutes the mentioned user(s) on the mentioned channel(s)
    will reset the message history and begin the process of expiring escalations/warnings
    $unmute <@user> [@user...] [#channel...] [reason text]
        <@user>
            required parameter, at least one @user mention is necessary
         [@user...]
             optional parameter, zero or more additional users may be mentioned
             there is no maximum number of user mentions
         [#channel...]
             optional parameter, zero or more channels may be mentioned
             there is no maximum number of channel mentions
         [reason text]
             optional parameter, will default to 'No Reason' if not provided
             the reason is taken left to right, from everything not recognised as a mention

    call with one of:
        $unmute @user
            reason will default to No reason
            channel will default to current channel
            unmutes the mentioned user, on current channel, with no reason

        $unmute @user #channel
            reason will default to No reason
            unmutes the mentioned user now, on the mentioned channel, with no reason

        $unmute @user #channel I want to
            unmutes the mentioned user now, on the mentioned channel, with the reason "I want to"

        order of user mentions, channel mentions, and reason are not important
        multiple users may be mentioned in one call
        multiple channels may be mentioned in one call

        anything not recognised as a mention will become part of the reason

        for example, this works:
        $unmute because @user1 this #channel2 is @user2 useful #channel1

        this will:
            unmutes @user1 and @user2 now,
                on both #channel1 and #channel2,
                with the reason: "because this is useful"
    """
    users = ctx.message.mentions
    if not users:
        return await ctx.send('its rather necessary to say who is going to get muted.....')
    args = list(args)

    channels = ctx.message.channel_mentions
    if not channels:
        channels = [ctx.channel]
    reason = [x for x in args if not re.match('.*(<[@|#]!?[0-9]{18}>).*', x)]
    for member in users:
        for mute_channel in channels:
            await un_mute_user(channel=mute_channel, member=member, ctx=ctx, *reason)


async def mute_user(*reason, channel: discord.TextChannel = None, guild: discord.Guild = None,
                    member: discord.member = None, data=None, ctx=None, time=None):
    overwrite = channel.overwrites_for(member) or discord.PermissionOverwrite()
    # noinspection PyDunderSlots,PyUnresolvedReferences
    overwrite.send_messages = False
    # noinspection PyDunderSlots,PyUnresolvedReferences
    overwrite.send_tts_messages = False
    # noinspection PyDunderSlots,PyUnresolvedReferences
    overwrite.speak = False
    await channel.set_permissions(member, overwrite=overwrite)

    if not data:
        saved = read_messages_per_channel(channel, member.mention)
        if saved:
            saved.escalate = min(6, saved.escalate + 1)
            saved.muted = 1
        else:
            saved = NamedTuple(guild=guild.id,
                               channel=channel.id,
                               uid=member.mention,
                               escalate=1, muted=1, expire=0, messages=0,
                               m1='', m2='', m3='', m4='', m5='')
        data = saved
    if not time:
        time = escalate[data.escalate]
    data.expire = int(datetime.datetime.utcnow().timestamp()) + time

    write_database(data)
    # if not ctx:
    #     ctx = channel
    if not ctx:
        ctx = type('dummy ctx', (), {'channel': channel, 'guild': guild})
    await log_action(ctx, Action.Mute, member.mention, reason, where=channel, time=time)


async def un_mute_user(*reason, channel: discord.TextChannel = None, member: discord.Member = None,
                       data=None, ctx=None):
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
    await log_action(ctx, Action.Unmute, member.mention, reason, where=channel)


async def log_action(ctx, act, who, why, where=None, time=None):
    mutelog = mutelogs.get(ctx.guild, None)

    if mutelog:
        if hasattr(ctx, 'message'):
            if not why:
                why = ('No', 'Reason')
            if not isinstance(why, str):
                why = ' '.join(why)
            issuer = ctx.message.author.mention
        else:
            issuer = bot.user.name
            why = 'Spam threshold exceeded' if (act.name in ['Mute', 'Warn']) else 'Time served'
        if not where:
            where = ctx.channel
        embed = discord.Embed()
        embed.add_field(name='Issuer: ', value=issuer)
        embed.add_field(name='Action: ', value=act.name)
        embed.add_field(name='Who:    ', value=who)
        if time:
            embed.add_field(name='Duration', value=expire_str(time))
        if 'MUTE' in act.name.upper():
            embed.add_field(name='Where:  ', value=where)
        embed.add_field(name='Why:    ', value=why)
        embed.colour = act.color
        await mutelog.send(embed=embed)


@bot.command(pass_context=True)
@has_permissions(manage_messages=True)
async def messages(ctx, member: discord.Member = None):
    """prints the given user's recent messages
    shows oldest first, split across several messages if necessary
    $messages [@user]
        [@user]
            optional parameter, maximum of one user mention

    eg:
        $messages
            will show your recent messages

        $messages @user
            will show @user's recent messages
    """

    if not member:
        # return await ctx.send('A member name is required to see their recent messages')
        member = ctx.message.author
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

    await ctx.send(embed=embed1)
    if embed2:
        await ctx.send(embed=embed2)
    if embed3:
        await ctx.send(embed=embed3)


@bot.command(pass_context=True)
@has_permissions(ban_members=True)
async def ban(ctx, *args):
    """bans user(s) via mention from the current guild
    $ban <@user> [@user...] [reason] [delete=int]
        <@user>
            required parameter, at least one user mention is necessary
        [@user...]
            optional parameter, zero or more additional users may be mentioned
            there is no maximum number of user mentions
        [reason text]
            optional parameter, will default to 'No Reason' if not provided
            the reason is taken left to right, from everything not recognised as:
                a mention, users or channels
                delete=int
        [delete=int]
            optional parameter, deletes the user's messages, going back "delete" days
            integer only, maximum of 7

    order of arguments does not matter
    multiple users may be mentioned in one call

    eg:
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
            all messages the user posted over the last 3 days are removed
    """

    users = ctx.message.mentions
    if not users:
        return await ctx.send('its rather necessary to say who is going to get banned.....')
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
                return await ctx.send(f'{k} must be an integer, not {v}')
    for k in kwargs:
        args.remove(f'{k}={kwargs[k]}')

    reason = [x for x in args if not re.match('.*(<[@|#]!?[0-9]{18}>).*', x)]
    for member in users:
        await ctx.guild.ban(member, reason=' '.join(reason), delete_message_days=delete)
        await log_action(ctx, Action.Ban, member.mention, reason)


@bot.command(pass_context=True)
@has_permissions(ban_members=True)
async def banid(ctx, *args):
    """bans user(s) via uid from the current guild
    $ban <uid int> [uid int] [reason text] [delete=int]
        <uid int>
            required parameter, user id number of the target to ban
        [uid int...]
            optional parameter, zero or more additional user ID's may be given
            there is no maximum number of user id's
        [reason text]
            optional parameter, will default to 'No Reason' if not provided
            the reason is taken left to right, from everything not recognised as:
                an 18 digit integer which will be interpreted as a user id
                delete=int
        [delete=int]
            optional parameter, deletes the user's messages, going back "delete" days
            integer only, maximum of 7

    order of arguments does not matter
    multiple user id's may be given in one call

    integer values between 4 and 17 digits long, inclusive, will be discarded as erroneous UIDs

    eg:
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
            all messages the user posted over the last 3 days are removed
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
                return await ctx.send(f'{k} must be an integer, not {v}')

    # strip the delete parameter form the args
    for k in kwargs:
        args.remove(f'{k}={kwargs[k]}')
    # strip uids from args
    for user_obj in user_ids:
        args.remove(user_obj)
    # drop obviously too short user ids
    user_ids = [int(u) for u in user_ids if len(u) == 18]  # drop the too short uid values
    # what remains is assumed to be the reason
    reason = args

    for uid in user_ids:
        user_obj = discord.Object(id=uid)
        await ctx.guild.ban(user_obj, reason=' '.join(reason), delete_message_days=delete)
        bans = await ctx.guild.bans()
        for b in bans:
            if b.user.id == uid:
                user_obj = b.user
        if hasattr(user_obj, 'mention'):
            await log_action(ctx, Action.Ban, f'{user_obj.mention}', reason)
        elif hasattr(user_obj, 'name') and hasattr(user_obj, 'discriminator'):
            await log_action(ctx, Action.Ban, f'{user_obj.name}#{user_obj.discriminator}', reason)
        else:
            await log_action(ctx, Action.Ban, f'@<{uid}>', reason)


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
    return bot.get_user(uid)


@bot.command(pass_context=True)
@has_permissions(ban_members=True)
async def unban(ctx, uid, *reason):
    """unbans user(s) via uid from the current guild
    $unban <uid int> [uid int] [reason text]
        <uid int>
            required parameter, user id number of the user to unban
        [uid int...]
            optional parameter, zero or more additional user ID's may be given
            there is no maximum number of user id's
        [reason text]
            optional parameter, will default to 'No Reason' if not provided
            the reason is taken left to right, from everything not recognised as:
                an 18 digit integer which will be interpreted as a user id
                delete=int

    order of arguments does not matter
    multiple user id's may be given in one call

    eg:
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
            all messages the user posted over the last 3 days are removed
    """
    # async def unban(ctx, member, *reason):
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
                await log_action(ctx, Action.Unban, target.mention, reason)
                break


@bot.command(pass_context=True)
@has_permissions(ban_members=True)
async def banned(ctx, uid=None):
    """shows the banned user(s) and the reason given
    $banned [uid]
        [uid]
            optional user id

    eg:
        $banned
            shows the complete set of banned users
        $banned uid
            shows the banned user and the reason
        """
    bans = await ctx.guild.bans()
    if not bans:
        return await ctx.send('There are no banned users at this time')
    if uid:
        user_ban = [u for u in bans if u.user.id == uid]
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
            embed.add_field(name=str(user_ban.user) + '\n' + str(user_ban.user.id), value=user_ban.reason, inline=False)
        await ctx.send(embed=embed)


@bot.command(pass_context=True)
@has_permissions(kick_members=True)
async def kick(ctx, *args):
    """kicks user(s) via mention from the current guild
    $kick <@user> [@user...] [reason text]
        <@user>
            required parameter, at least one user mention is necessary
        [@user...]
            optional parameter, zero or more additional users may be mentioned
            there is no maximum number of user mentions
        [reason text]
            optional parameter, will default to 'No Reason' if not provided
            the reason is taken left to right, from everything not recognised as a user mention

    order of user mentions and reason is not important
    multiple users may be mentioned in one call

    eg:
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
        return await ctx.send('its rather necessary to say who is going to get kicked.....')
    args = list(args)

    #    reason = [x for x in args if not re.match('.*(<[@|#]!?[0-9]{18}>).*', x)]
    reason = [x for x in args if x not in users]
    for member in users:
        await ctx.guild.kick(member, reason=' '.join(reason))
        await log_action(ctx, Action.Kick, member.mention, reason)


def message_repetition(message):
    message = drop_domains(message)  # drop the domains from any urls in the message
    message = drop_code_blocks(message)  # drop any code blocks in the message
    mid_point = max(1, int(len(message) / 2 + 0.5))
    per = 1 / mid_point
    repeats = [0] * len(message)
    for i in range(mid_point):
        for j in range(1, len(message)):
            sub_str = message[i:j + i]
            if ' ' not in sub_str or j > 2:
                matches = message.count(sub_str, i) - 1
                repeats[j] += matches * j * per
    return sum(repeats) / mid_point


# noinspection RegExpRedundantEscape
def drop_domains(message):
    # hopefully splitting this across a few lines hasn't broken it
    pattern = re.compile(r'(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|'
                         r'\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|'
                         r'[^\s`!()\[\]{};:\'".,<>?\xab\xbb\u201c\u201d\u2018\u2019]))')
    matches = re.findall(pattern, message)
    matches2 = ['/'.join((x[0].split('/'))[:3]) for x in matches]
    for match in matches2:
        message = re.sub(match, '', message)
    return message


def drop_code_blocks(message):
    pattern = re.compile(r'```.*```')
    matches = re.findall(pattern, message)
    for match in matches:
        message = re.sub(match, '', message)
    return message


@bot.group()
@has_permissions(manage_channels=True)
async def ignore(ctx):
    """marks a channel, or channels, as not monitored
    if no channels are mentioned, the current channel is assumed

    $ignore [all command] [#channel...]
        [all command]
            optional sub-command
            [#channel...] is ignored if [all] is provided
            invokes the all sub-command, which sets ignore for all channels on the server
        [#channel...]
            optional parameter, zero or more channel mentions
            if no channel mentions are given, defaults to current channel

    eg:
        $ignore
            ignores the current channel

        $ignore all
            calls the all sub-command, ignores all text channels

        $ignore #channel1 #channel2
           ignores channel1 and channel2
        """
    if ctx.invoked_subcommand:
        return
    channels = ctx.message.channel_mentions
    if not channels:
        channels = [ctx.message.channel]
    for channel in channels:
        sql_c.execute('insert or replace into ignoring (guild, channel) values (?, ?)',
                      (ctx.guild.id, str(channel.id),))
    database.commit()
    await ctx.send(f"No longer monitoring the following channels: {', '.join([c.name for c in channels])}")


# noinspection PyShadowingBuiltins
@ignore.command()
@has_permissions(manage_channels=True)
async def all(ctx):
    """marks all text channels as not monitored"""
    channels = [[x.id, x.name] for x in bot.get_all_channels()
                if x.guild.id == ctx.guild.id and isinstance(x, discord.TextChannel)]
    for channel in channels:
        sql_c.execute('insert or replace into ignoring (guild, channel) values (?, ?)',
                      (ctx.guild.id, str(channel[0]),))
        database.commit()
    await ctx.send(f"No longer monitoring the following channels: {', '.join([c[1] for c in channels])}")


del all


@bot.group()
@has_permissions(manage_channels=True)
async def watch(ctx):
    """marks a channel, or channels, as monitored
    if no channels are mentioned, the current channel is assumed

    $watch [all] [#channel...]
        [all]
            optional sub-command
            [#channel...] is watched if [all] is provided
            invokes the all sub-command, which sets watch for all channels on the server
        [#channel...]
            optional parameter, zero or more channel mentions
            if no channel mentions are given, defaults to current channel

    eg:
        watch
            watches the current channel

        $watch all
            calls the all sub-command, watches all text channels

        watch #channel1 #channel2
           watches channel1 and channel2
        """
    if ctx.invoked_subcommand:
        return
    channels = ctx.message.channel_mentions
    if not channels:
        channels = [ctx.message.channel]
    #        return await ctx.send('its rather necessary to say what channel(s) are to be ignored.....')
    for channel in channels:
        sql_c.execute('delete from ignoring where guild=? and channel=?', (ctx.guild.id, channel.id,))
    database.commit()
    await ctx.send(f"Now monitoring the following channels: {', '.join([c.name for c in channels])}")


# noinspection PyShadowingBuiltins
@watch.command()
@has_permissions(manage_channels=True)
async def all(ctx):
    """marks all text channels as monitored"""
    channels = [[x.id, x.name] for x in bot.get_all_channels()
                if x.guild.id == ctx.guild.id and isinstance(x, discord.TextChannel)]
    for channel in channels:
        sql_c.execute('delete from ignoring where guild=? and channel=?', (ctx.guild.id, channel[0],))
        database.commit()
    await ctx.send(f"Now monitoring the following channels: {', '.join([c[1] for c in channels])}")


del all


def expire_str(duration):
    days = duration // 86400
    hours = (duration % 86400) // 3600
    minutes = (duration % 3600) // 60
    seconds = duration % 60
    d = '%d d, ' % days
    h = '%0dh, ' % hours
    m = '%0dm, ' % minutes
    s = '%0ds' % seconds
    if days:
        return d + h + m + s
    elif hours:
        return h + m + s
    elif minutes:
        return m + s
    else:
        return s


@bot.command(pass_context=True)
async def expire(ctx, member: discord.Member = None):
    """gets the current mute state of the user across all channels on the server
    $expire [@user]
        [@user]
            optional parameter, defaults to message author if not given

    eg:
        $expire
            gets the expiration state for the calling user

        $expire @user
            gets the expiration state of the mentioned user"""

    if member:
        target = member
    else:
        target = ctx.message.author
    entries = read_messages(target.mention)
    escalates = [x for x in entries if x.escalate > 0]
    warnings = [x for x in entries if x.expire > 0 and x.escalate == 0]
    now = int(datetime.datetime.utcnow().timestamp())

    if escalates:
        embed = discord.Embed(title=target.name + '\'s escalation state per channel')
        for muting in escalates:
            channel = bot.get_channel(int(muting.channel))
            s = 'Level %d\n' % muting.escalate
            if muting.muted:
                s += 'Muted: True\nExpires: ' + expire_str(muting.expire - now)
            else:
                s += 'Muted: False\nExpires: '
                if muting.escalate > 0:
                    s += expire_str(escalate[muting.escalate] - (now - muting.expire))
            embed.add_field(name=channel.name, value=s)
        await ctx.send(embed=embed)
    if warnings:
        embed = discord.Embed(title=target.name + '\'s warning state per channel')
        for w in warnings:
            embed.add_field(name=bot.get_channel(int(w.channel)),
                            value='Expires: ' + expire_str(un_warn + w.expire - now))
        await ctx.send(embed=embed)
    if not escalates and not warnings:
        await ctx.send(f'{target} has no escalations pending expiration')


@bot.command(pass_context=True)
@has_permissions(manage_channels=True)
async def ignored(ctx):
    """outputs a list of the text channels that are not being monitored"""
    ignoring = sql_c.execute('select * from ignoring where guild=?', (ctx.guild.id,)).fetchall()
    ignoring = [(bot.get_channel(int(x[1]))).name for x in ignoring]
    if ignoring:
        ignoring = ', '.join(ignoring)
    else:
        ignoring = 'None'
    await ctx.send('The following channels are not monitored for spam: ' + ignoring)


@bot.command(pass_context=True)
@has_permissions(manage_channels=True)
async def terminate(ctx):
    await ctx.send('shutting down')
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
        $setwarn [parameter]
            [parameter]
                optional parameter, indicates if the desired state is on or off.
                defaults to None
                on is one of 'yes', 'y', 'true', 't', '1', 'enable', 'on', 'affirmative'
                off is on of 'no', 'n', 'false', 'f', '0', 'disable', 'off', 'negative'
                case insensitive
    eg:
        $setwarn
            toggles the current warn_only state

        $setwarn t
            sets the current warning_only state to true
    """
    global warn_only
    if parameter is None:
        warn_only = not warn_only
        if warn_only:
            await ctx.send('Action will not be taken for infractions, only warnings given.')
        else:
            await ctx.send('Action will now be taken for infractions.')
    else:
        on = ['yes', 'y', 'true', 't', '1', 'enable', 'on', 'affirmative']
        off = ['no', 'n', 'false', 'f', '0', 'disable', 'off', 'negative']
        if parameter.lower() in on:
            warn_only = True
            await ctx.send('WARN_ONLY is now enabled.')
        elif parameter.lower() in off:
            warn_only = False
            await ctx.send('WARN_ONLY is now disabled.  Penalties may be applied for infractions.')
        else:
            await ctx.send(f"{parameter} is not recognised.  "
                           f"\n\tTo enable, use one of [{', '.join(on)}]"
                           f"\n\tTo disable, use one of [{', '.join(off)}]"
                           "parameter is not case sensitive")


@bot.command(hidden=True)
async def accept(ctx):
    # get members role
    member_role = [x for x in ctx.guild.roles if x.name.upper() == 'MEMBER'][0]
    await ctx.author.add_roles(member_role, reason='Accepted Rules')


@bot.command(hidden=True)
async def myhelp(ctx):
    print(bot.commands)
    for c in bot.commands:
        print(dir(c))
        print('name:', c.name)
        print('\taliases:', c.aliases)
        show = not c.hidden
        print('\tchecks:', c.checks)
        if c.checks:
            for check in c.checks:
                print('\t\tcheck_result:', check(ctx))
                show = show and check(ctx)
        print('\tshow:', show)
        print('\tcog:', c.cog)
        print('\tcog_name:', c.cog_name)
        print('\tdescription:', c.description)
        print('\tshort_doc:', c.short_doc)
        print('\tusage:', c.usage)
        if hasattr(c, 'command'):
            print('\t\tcommands:', c.commands)
        if hasattr(c, 'all_commands'):
            print('\t\tall_commands:', c.all_commands)


# help function customisation
for cmd in bot.commands:
    if cmd.name == 'ignore':
        cmd.usage = '[all command] [#channel...]'

bot.run(token())
