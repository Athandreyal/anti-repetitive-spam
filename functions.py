# hosts the code needed by both the main bot, and its cogs.
import sqlite3
import discord
import datetime
from inspect import stack

database = sqlite3.connect('messages.db')
sql_c = database.cursor()
mutelogs = dict()
logging_channel = 'mute-log'
bot = None
escalate = None
un_warn = None


def set_bot(bot_):
    global bot
    bot = bot_


def set_escalate(esc_, un_):
    global escalate
    global un_warn
    escalate = esc_
    un_warn = un_


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


class Emotes:
    class Arrows:
        leftleft = '\U000023ea'
        leftleftbar = '\U000023ee'
        rightright = '\U000023e9'
        rightrightbar = '\U000023ed'
        upup = '\U000023eb'
        right = '\U000025ba'
        left = '\U000025c4'


class UserData:
    def __init__(self, data=None, **kwargs):
        if data:
            self.guild = data[0]
            self.channel = data[1]
            self.uid = data[2]
            self.escalate = data[3]
            self.muted = data[4]
            self.expire = data[5]
            self.messages = data[6]
            self.m1 = data[7]
            self.m2 = data[8]
            self.m3 = data[9]
            self.m4 = data[10]
            self.m5 = data[11]
        else:
            self.guild = kwargs.get('guild', '')
            self.channel = kwargs.get('channel', '')
            self.uid = kwargs.get('uid', '')
            self.escalate = kwargs.get('escalate', 0)
            self.muted = kwargs.get('muted', 0)
            self.expire = kwargs.get('expire', 0)
            self.messages = kwargs.get('messages', 0)
            self.m1 = kwargs.get('m1', '')
            self.m2 = kwargs.get('m2', '')
            self.m3 = kwargs.get('m3', '')
            self.m4 = kwargs.get('m4', '')
            self.m5 = kwargs.get('m5', '')


def get_database():
    return sql_c, database


def init_database():
    sql_c.execute('create table if not exists messages ('
                  'guild text, '
                  'channel text, '
                  'id text, '
                  'escalate integer, '
                  'muted integer, '
                  'expire integer, '
                  'messages integer, '
                  'm1 text, '
                  'm2 text, '
                  'm3 text, '
                  'm4 text, '
                  'm5 text,  '
                  'primary key (guild, channel, id));')
    sql_c.execute('create table if not exists ignoring ('
                  'guild integer, '
                  'channel integer, '
                  'primary key (guild, channel));')
    sql_c.execute('create table if not exists warning_only('
                  'guild integer primary key,'
                  'only_warn integer);')
    sql_c.execute('create table if not exists member_invite_roles('
                  'guild integer primary key, '
                  'role_new text, '
                  'role_default text, '
                  'accept integer);')
    sql_c.execute('pragma synchronous = 1')
    sql_c.execute('pragma journal_mode = wal')
    database.commit()


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
    try:
        sql_c.execute('insert or replace into messages (guild, channel, id, escalate, muted, expire, messages, m1, m2, '
                      'm3, m4, m5) values ("%s", "%s", "%s", %d, %d, %d, %d, "%s", "%s", "%s", "%s", "%s")' %
                      (row.guild, row.channel, row.uid, row.escalate, row.muted, row.expire, row.messages, row.m1,
                       row.m2, row.m3, row.m4, row.m5))
        database.commit()
    except sqlite3.OperationalError:
        print('sqlite3 operational error')
        print('\t', called_with())
        print(f'\ttype(row)={type(row)}, row={row}, dir(row)={dir(row)}')


def full_row_to_named(d):
    return UserData(d)


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
            if isinstance(ctx, discord.TextChannel):
                where = ctx
            else:
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


def init_mute_logs():
    logs = [x for x in bot.get_all_channels() if x.name == logging_channel]
    for c in logs:
        mutelogs[c.guild] = c


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


async def warning(channel: discord.TextChannel, issuer, who: discord.Member, where: discord.Guild, why, ctx=None):
    for warn_channel in where.channels:
        if isinstance(warn_channel, discord.TextChannel):
            data = read_messages_per_channel(warn_channel.id, who.mention)
            if data:
                data.expire = int(datetime.datetime.utcnow().timestamp())
            else:
                data = UserData(guild=where.id, channel=warn_channel.id, uid=who.mention,
                                escalate=0, muted=0, expire=int(datetime.datetime.utcnow().timestamp()),
                                messages=0, m1='', m2='', m3='', m4='', m5='')
            # noinspection PyTypeChecker
            write_database(data)
    if not isinstance(why, str):
        why = ' '.join(why)
    await channel.send(f"{who.mention}, {issuer} giving you a warning.\nReason: {why}")
    if not ctx:
        ctx = channel
    await log_action(ctx=ctx, act=Action.Warn, who=who, why=why)


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
            saved = UserData(guild=guild.id, channel=channel.id, uid=member.mention, escalate=1, muted=1, expire=0,
                             messages=0, m1='', m2='', m3='', m4='', m5='')
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
    print(f'un_mute_user releasing {member} in {channel}')
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


def called_with():
    text = stack()[2][4][0]  # stack()[1] is the caller, but as this is called to get a previous caller, use ()[2]
    if '#' in text:  # strip off the comment
        index = text.find('#')
        text = text[:index]
    return text.strip()  # toss leading/trailing spaces


def warn_only_servers():
    warn_guilds = sql_c.execute('select guild from warning_only where only_warn=1').fetchall()
    if not warn_guilds:
        return []
    return [x[0] for x in warn_guilds]


def boolean(value=None, show=False):
    true = ['yes', 'y', 'true', 't', '1', 'enable', 'on', 'affirmative']
    false = ['no', 'n', 'false', 'f', '0', 'disable', 'off', 'negative']

    if show:
        return [true, false]

    value = str(value).lower()
    if value in true:
        return True
    if value in false:
        return False
    return None
